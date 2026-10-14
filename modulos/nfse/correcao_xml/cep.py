"""
Código do município (cMun, IBGE) a partir do CEP ou do CNPJ, com os caches do QG XML.

Ordem para um CEP:
  1. cache de CEPs inválidos (se o CEP está lá, nenhuma API é consultada);
  2. cache local de CEPs já resolvidos (cache_ceps.json);
  3. ViaCEP, que já devolve o código IBGE;
  4. BrasilAPI CEP V2;  5. BrasilAPI CEP V1;  6. OpenCEP;  7. AwesomeAPI;
  8. tabela local conferida manualmente.
Quando a API devolve só cidade e UF, o código é confirmado na API de Localidades do IBGE.

Só entra no cache de inválidos o CEP que alguma API declara inexistente ("não existe" ou
erro 404). Falha de rede ou de API não entra, porque pode ser temporária.

São serviços públicos da internet (não são endpoints internos, por isso ficam no código). A
verificação do certificado fica desligada por causa do proxy da rede, como no QG original.
"""
import json
import os
import re
import time
import unicodedata
from datetime import datetime

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TIMEOUT_API = 15
PAUSA_ENTRE_CONSULTAS = 0.2

# Última instância: CEPs já conferidos manualmente. "CEP": (cMun, município, UF)
FALLBACK_CEP_CMUN = {
    "68790000": ("1506500", "Santa Izabel do Pará", "PA"),
}


def normalizar_texto(texto) -> str:
    """Maiúsculas e sem acento, para comparar nomes de município."""
    texto = unicodedata.normalize("NFD", str(texto or "").strip().upper())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def _cidade_uf(dados, campos_cidade, campos_uf):
    """Cidade e UF de uma resposta JSON (cada provedor usa nomes de campo diferentes)."""
    cidade = next((str(dados[c]).strip() for c in campos_cidade if dados.get(c)), "")
    uf = next((str(dados[c]).strip().upper() for c in campos_uf if dados.get(c)), "")
    return cidade, uf


class ResolvedorMunicipio:
    def __init__(self, dados_dir, log=None, pausa=PAUSA_ENTRE_CONSULTAS):
        self.dados_dir = dados_dir
        self.log = log or (lambda _texto: None)
        self.pausa = pausa
        self.arquivo_cache = os.path.join(dados_dir, "cache_ceps.json")
        self.arquivo_invalidos = os.path.join(dados_dir, "cache_ceps_invalidos.json")
        self.cache = self._carregar(self.arquivo_cache)
        self.invalidos = self._carregar(self.arquivo_invalidos)
        self.municipios_por_uf = {}

    # ------------------------------------------------------------------ caches
    @staticmethod
    def _carregar(caminho) -> dict:
        try:
            with open(caminho, encoding="utf-8") as f:
                dados = json.load(f)
            return dados if isinstance(dados, dict) else {}
        except (OSError, ValueError):
            return {}

    def _salvar(self, caminho, dados):
        try:
            os.makedirs(self.dados_dir, exist_ok=True)
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(dados, f, indent=4, ensure_ascii=False)
        except OSError as erro:  # sem o cache o lote continua, só fica mais lento da próxima vez
            self.log(f"Não foi possível gravar {caminho}: {erro}")

    def _guardar(self, cep, cmun):
        self.cache[cep] = cmun
        self._salvar(self.arquivo_cache, self.cache)
        return cmun

    def _registrar_invalido(self, cep, motivo):
        self.invalidos[cep] = {"registrado_em": datetime.now().isoformat(timespec="seconds"), "motivo": str(motivo)}
        self._salvar(self.arquivo_invalidos, self.invalidos)

    # -------------------------------------------------------------------- HTTP
    def _json(self, url):
        try:
            resposta = requests.get(url, timeout=TIMEOUT_API, verify=False, headers={"User-Agent": "MegaQG-Vivo"})
        except Exception as erro:
            raise RuntimeError(f"Não foi possível acessar {url}: {erro}") from erro
        if resposta.status_code != 200:
            raise RuntimeError(f"Erro HTTP {resposta.status_code} ao consultar {url}")
        try:
            return resposta.json()
        except ValueError as erro:
            raise RuntimeError(f"A resposta de {url} não é um JSON válido.") from erro

    # -------------------------------------------------------------------- IBGE
    def cmun_por_municipio_uf(self, municipio, uf) -> str:
        """Código oficial do município na API de Localidades do IBGE."""
        municipio, uf = str(municipio or "").strip(), str(uf or "").strip().upper()
        if not municipio or len(uf) != 2:
            raise ValueError("Nome do município ou UF não disponíveis.")
        if uf not in self.municipios_por_uf:
            self.municipios_por_uf[uf] = self._json(
                f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios")
        procurado = normalizar_texto(municipio)
        simplificado = re.sub(r"[^A-Z0-9]", "", procurado)
        candidatos = [(normalizar_texto(item.get("nome", "")), str(item.get("id", "")).strip())
                      for item in self.municipios_por_uf[uf]]
        for nome, codigo in candidatos:
            if nome == procurado and codigo:
                return codigo
        for nome, codigo in candidatos:
            if re.sub(r"[^A-Z0-9]", "", nome) == simplificado and codigo:
                return codigo
        raise ValueError(f"Município '{municipio}/{uf}' não encontrado na API do IBGE.")

    def _confirmar_no_ibge(self, cidade, uf, origem) -> str:
        codigo = self.cmun_por_municipio_uf(cidade, uf)
        self.log(f"Cidade/UF por {origem} ({cidade}/{uf}); cMun {codigo} confirmado no IBGE.")
        return codigo

    # --------------------------------------------------------------- provedores
    def _viacep(self, cep):
        dados = self._json(f"https://viacep.com.br/ws/{cep}/json/")
        if dados.get("erro") in (True, "true"):
            raise LookupError("ViaCEP informou que o CEP não existe.")
        codigo = str(dados.get("ibge", "")).strip()
        if codigo:
            return codigo
        cidade, uf = _cidade_uf(dados, ("localidade", "cidade", "city"), ("uf", "state"))
        if cidade and uf:
            return self._confirmar_no_ibge(cidade, uf, "ViaCEP sem campo IBGE")
        raise ValueError("ViaCEP respondeu sem IBGE e sem cidade/UF.")

    def _brasilapi(self, versao):
        def consultar(cep):
            dados = self._json(f"https://brasilapi.com.br/api/cep/{versao}/{cep}")
            cidade, uf = _cidade_uf(dados, ("city", "cidade", "localidade"), ("state", "uf"))
            if not cidade or not uf:
                raise ValueError(f"BrasilAPI CEP {versao.upper()} não retornou cidade/UF.")
            return self._confirmar_no_ibge(cidade, uf, f"BrasilAPI CEP {versao.upper()}")
        return consultar

    def _opencep(self, cep):
        dados = self._json(f"https://opencep.com/v1/{cep}.json")
        codigo = str(dados.get("ibge", "")).strip()
        if codigo:
            return codigo
        cidade, uf = _cidade_uf(dados, ("localidade", "cidade", "city"), ("uf", "state"))
        if not cidade or not uf:
            raise ValueError("OpenCEP não retornou cidade/UF nem código IBGE.")
        return self._confirmar_no_ibge(cidade, uf, "OpenCEP")

    def _awesomeapi(self, cep):
        dados = self._json(f"https://cep.awesomeapi.com.br/json/{cep}")
        codigo = str(dados.get("city_ibge") or dados.get("ibge") or "").strip()
        if codigo:
            return codigo
        cidade, uf = _cidade_uf(dados, ("city", "cidade", "localidade"), ("state", "uf"))
        if not cidade or not uf:
            raise ValueError("AwesomeAPI não retornou cidade/UF nem código IBGE.")
        return self._confirmar_no_ibge(cidade, uf, "AwesomeAPI")

    # ------------------------------------------------------------------ consulta
    def cmun_por_cep(self, cep) -> str:
        """cMun do CEP, seguindo a ordem do topo deste arquivo. Levanta exceção se não resolver."""
        cep = re.sub(r"\D", "", cep or "")
        if cep in self.invalidos:
            data = self.invalidos[cep].get("registrado_em", "data desconhecida")
            raise RuntimeError(f"CEP {cep} está no cache de CEPs inválidos (registrado em {data}). "
                               "Consulta ignorada.")
        if cep in self.cache:
            return self.cache[cep]
        if len(cep) != 8:
            raise ValueError(f"CEP inválido: '{cep}'. O CEP precisa ter 8 números.")

        erros = []
        provedores = (("ViaCEP", self._viacep), ("BrasilAPI CEP V2", self._brasilapi("v2")),
                      ("BrasilAPI CEP V1", self._brasilapi("v1")), ("OpenCEP", self._opencep),
                      ("AwesomeAPI", self._awesomeapi))
        try:
            for nome, consultar in provedores:
                try:
                    codigo = consultar(cep)
                except LookupError as erro:
                    erros.append(str(erro))
                except Exception as erro:
                    erros.append(f"{nome}: {erro}")
                else:
                    self.log(f"CEP {cep} -> cMun {codigo} ({nome}).")
                    return self._guardar(cep, codigo)
        finally:
            time.sleep(self.pausa)  # pequena pausa entre CEPs diferentes, para não sobrecarregar as APIs

        if cep in FALLBACK_CEP_CMUN:
            codigo, municipio, uf = FALLBACK_CEP_CMUN[cep]
            self.log(f"CEP {cep}: tabela local conferida ({municipio}/{uf} -> {codigo}).")
            return self._guardar(cep, codigo)

        motivo = f"Não foi possível obter o cMun para o CEP {cep}. Detalhes: {' | '.join(erros)}"
        # Só memoriza CEP inexistente. Falha de rede/API é tentada de novo na próxima execução.
        if any("não existe" in erro.lower() or "http 404" in erro.lower() for erro in erros):
            self._registrar_invalido(cep, motivo)
        raise RuntimeError(motivo)

    def cmun_por_cnpj(self, cnpj):
        """cMun do emitente pelo CNPJ: BrasilAPI de CNPJ -> CEP -> cmun_por_cep. None se não resolver."""
        cnpj = re.sub(r"\D", "", cnpj or "")
        if len(cnpj) != 14:
            return None
        try:
            dados = self._json(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}")
            cep = re.sub(r"\D", "", str(dados.get("cep") or ""))
            return self.cmun_por_cep(cep) if cep else None
        except Exception as erro:
            self.log(f"CNPJ {cnpj}: não foi possível descobrir o município do emitente ({erro}).")
            return None
