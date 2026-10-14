"""
Reprocessamento de documentos NFCe: o operador informa só as chaves (A_ID) num .txt e, para
cada nota, o app baixa o XML de emissão, muda o IND_STATUS_NFE para 3 e reenvia o XML completo
(o <NFe> que está dentro do XML baixado) para a API de recepção síncrona.

Fluxo: previa(arquivo) -> reprocessar(simular=True/False). Em blocos de até 200 chaves:

  1. baixa o XML de cada chave (nfce_download_url_*) e separa o <NFe> de dentro dele;
  2. só para as chaves com XML em mãos: localiza o NUM_SEQ_NFE pelo A_ID e executa
         UPDATE INTERF_NFE SET IND_STATUS_NFE = 3 WHERE NUM_SEQ_NFE IN (...)
     numa transação por bloco;
  3. envia cada XML por POST (nfce_reprocessamento_url_*), corpo raw em XML, e registra o
     código HTTP e o retorno (cStat/xMotivo, quando a resposta traz).

O download vem antes do UPDATE de propósito: se o XML não puder ser baixado, o status da nota
não é alterado. Proteções, no padrão do Retorno de Contingência:
  - prévia somente leitura antes de qualquer alteração;
  - notas já autorizadas (IND_STATUS_NFE = 6) são puladas (pode ser desligado);
  - simulação: baixa os XMLs, executa o UPDATE e faz ROLLBACK; nada é gravado nem enviado.

Não depende de Tkinter: conversa com a tela por event_queue, como as demais engines.
"""
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests
import urllib3

from core.config import AMBIENTE_PRD, url_por_ambiente
from core.database import sql_conn
from modulos.nfce.comum import carregar_temp, db_config_nfce, ler_chaves
from modulos.nfce.download_xmls.engine import extrair_xml, montar_url

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

STATUS_REPROCESSAR = 3  # INTERF_NFE.IND_STATUS_NFE que libera o reprocessamento
STATUS_AUTORIZADA = 6
TAMANHO_BLOCO = 200
TIMEOUT_DOWNLOAD = 30
TIMEOUT_ENVIO = 120  # a recepção é síncrona: a resposta só vem depois do retorno da SEFAZ
NS_NFE = b"http://www.portalfiscal.inf.br/nfe"

# Situações da prévia
SERA_REPROCESSADA = "SERA_REPROCESSADA"
NAO_ENCONTRADA = "NAO_ENCONTRADA"
JA_AUTORIZADA = "JA_AUTORIZADA"

SQL_PREVIA = """
SELECT C.A_ID, I.NUM_SEQ_NFE, I.IND_STATUS_NFE
FROM #chaves C
LEFT JOIN INTERF_NFE I
       ON I.A_ID = C.A_ID
      AND I.IND_TIPO_PROCES = 'E'
"""

# A_ID -> NUM_SEQ_NFE do bloco. Sem parâmetros (as constantes vêm do código) para a tabela
# temporária continuar existindo na sessão depois do comando.
SQL_SELECIONAR_SEQ = """
IF OBJECT_ID('tempdb..#seq') IS NOT NULL DROP TABLE #seq;
SELECT I.A_ID, I.NUM_SEQ_NFE
INTO #seq
FROM INTERF_NFE I
JOIN #bloco B ON B.A_ID = I.A_ID
WHERE I.IND_TIPO_PROCES = 'E'
  AND ({pular} = 0 OR I.IND_STATUS_NFE IS NULL OR I.IND_STATUS_NFE <> {autorizada})
"""
SQL_LER_SEQ = "SELECT A_ID, NUM_SEQ_NFE FROM #seq"
SQL_UPDATE = (f"UPDATE INTERF_NFE SET IND_STATUS_NFE = {STATUS_REPROCESSAR} "
              "WHERE NUM_SEQ_NFE IN (SELECT NUM_SEQ_NFE FROM #seq)")

_RE_NFE = re.compile(rb"<NFe[\s>].*</NFe\s*>", re.DOTALL)
# cStat/xMotivo da resposta, em XML (<cStat>100</cStat>) ou em JSON ("cStat": "100")
_RE_CSTAT = re.compile(r'<cStat>\s*(\d{3})\s*</cStat>|"cStat"\s*:\s*"?(\d{3})', re.IGNORECASE)
_RE_XMOTIVO = re.compile(r'<xMotivo>([^<]{1,200})</xMotivo>|"xMotivo"\s*:\s*"([^"]{1,200})"', re.IGNORECASE)


def extrair_nfe(xml: bytes) -> bytes | None:
    """O <NFe>...</NFe> de dentro do XML baixado (que pode vir embrulhado num nfeProc), pronto
    para o corpo da requisição. Os bytes do <NFe> não são alterados, para a assinatura continuar
    válida; só entra o xmlns quando ele estava declarado apenas no elemento de fora."""
    achado = _RE_NFE.search(xml or b"")
    if not achado:
        return None
    nfe = achado.group(0)
    if b"xmlns" not in nfe[:nfe.index(b">")]:
        nfe = b'<NFe xmlns="' + NS_NFE + b'"' + nfe[len(b"<NFe"):]
    return b'<?xml version="1.0" encoding="utf-8"?>' + nfe


def retorno_sefaz(texto: str) -> str:
    """Retorno da SEFAZ que vier na resposta, no formato 'cStat 100 Autorizado o uso da NF-e'
    (vale o último cStat, que é o do protocolo). Vazio se a resposta não trouxer cStat."""
    codigos = ["".join(grupos) for grupos in _RE_CSTAT.findall(texto or "")]
    if not codigos:
        return ""
    motivos = ["".join(grupos).strip() for grupos in _RE_XMOTIVO.findall(texto)]
    return f"cStat {codigos[-1]}" + (f" {motivos[-1]}" if motivos else "")


def _resumo(texto, limite=200):
    return " ".join((texto or "").split())[:limite]


class ReprocessamentoNfceEngine:
    def __init__(self, event_queue, stop_event, *, ambiente=AMBIENTE_PRD, pular_autorizadas=True, threads=8,
                 log_dir, conectar=None):
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.ambiente = ambiente
        self.pular_autorizadas = pular_autorizadas
        self.threads = max(1, threads)
        self.log_dir = log_dir
        self.url_download = url_por_ambiente("nfce_download_url", ambiente)
        self.url_envio = url_por_ambiente("nfce_reprocessamento_url", ambiente)
        # conectar() -> conexão pyodbc; injetável nos testes
        self.conectar = conectar or (lambda: sql_conn(db_config_nfce(self.ambiente)))
        self.log_lock = threading.Lock()
        self.log_file = None
        self.leitura = None
        self.situacoes = {}  # A_ID -> situação da prévia
        self.status_atual = {}  # IND_STATUS_NFE -> quantidade de notas encontradas
        self.listas = {}
        self.retornos = []  # (chave, NUM_SEQ_NFE, status HTTP, retorno SEFAZ, resposta)
        self.codigos = {}  # "HTTP 200" / "sem resposta" -> quantidade

    # ---------------------------------------------------------------- eventos/log
    def emit(self, kind, **data):
        self.event_queue.put({"kind": kind, **data})

    def emit_log(self, text, status="INFO"):
        self._log_arquivo(f"{status:<5} | {text}")
        self.emit("log_line", text=text, status=status)

    def _log_arquivo(self, linha):
        with self.log_lock:
            if not self.log_file:
                os.makedirs(self.log_dir, exist_ok=True)
                self.log_file = os.path.join(self.log_dir, f"nfce-reprocessamento_{datetime.now():%Y-%m-%d_%H%M%S}.log")
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {linha}\n")

    def lista(self, situacao):
        return [c for c, s in self.situacoes.items() if s == situacao]

    def _config_faltando(self):
        sufixo = "prd" if self.ambiente == AMBIENTE_PRD else "hml"
        return [f"{chave}_{sufixo}" for chave, valor in (("nfce_download_url", self.url_download),
                                                         ("nfce_reprocessamento_url", self.url_envio)) if not valor]

    # ---------------------------------------------------------------------- prévia
    def previa(self, arquivo):
        """Lê o arquivo e consulta o banco (somente leitura). Emite 'previa' com as contagens."""
        try:
            faltando = self._config_faltando()
            if faltando:
                self.emit("fatal_error", text=f"Reprocessamento de NFCe não configurado para {self.ambiente}: "
                                              f"preencha {', '.join(faltando)} em config.json.")
                return
            self.leitura = ler_chaves(arquivo)
            validas = self.leitura["validas"]
            self.emit_log(
                f"Arquivo: {len(validas)} chave(s) válida(s), {len(self.leitura['invalidas'])} inválida(s), "
                f"{self.leitura['duplicadas']} repetida(s) ignorada(s).", "INFO")
            if not validas:
                self.emit("fatal_error", text="Nenhuma chave válida no arquivo (A_ID com 44 dígitos).")
                return
            self.emit_log(f"Consultando {len(validas)} chave(s) no banco ({self.ambiente})...", "INFO")
            conn = self.conectar()
            try:
                cur = conn.cursor()
                carregar_temp(cur, "#chaves", validas)
                cur.execute(SQL_PREVIA)
                linhas = cur.fetchall()
            finally:
                conn.rollback()
                conn.close()

            por_chave = {}
            for a_id, seq, status in linhas:
                por_chave.setdefault(str(a_id).strip(), []).append((seq, status))
            self.situacoes, self.status_atual, multiplas = {}, {}, 0
            for chave in validas:
                encontradas = [(seq, status) for seq, status in por_chave.get(chave, []) if seq is not None]
                for _seq, status in encontradas:
                    rotulo = "vazio" if status is None else str(int(status))
                    self.status_atual[rotulo] = self.status_atual.get(rotulo, 0) + 1
                elegiveis = [seq for seq, status in encontradas
                             if not (self.pular_autorizadas and status is not None
                                     and int(status) == STATUS_AUTORIZADA)]
                if not encontradas:
                    self.situacoes[chave] = NAO_ENCONTRADA
                elif not elegiveis:
                    self.situacoes[chave] = JA_AUTORIZADA
                else:
                    self.situacoes[chave] = SERA_REPROCESSADA
                    multiplas += len(elegiveis) > 1
            if multiplas:
                self.emit_log(f"{multiplas} chave(s) têm mais de uma linha em INTERF_NFE: o UPDATE altera todas "
                              f"as linhas de emissão da chave.", "WARN")
            if self.status_atual:
                self.emit_log("Status atual (IND_STATUS_NFE) das notas encontradas: " + " | ".join(
                    f"{status}: {n}" for status, n in sorted(self.status_atual.items())), "INFO")

            contagem = {s: len(self.lista(s)) for s in (SERA_REPROCESSADA, NAO_ENCONTRADA, JA_AUTORIZADA)}
            self.emit_log(
                f"Prévia: {contagem[SERA_REPROCESSADA]} serão reprocessada(s), {contagem[NAO_ENCONTRADA]} não "
                f"encontrada(s), {contagem[JA_AUTORIZADA]} já autorizada(s) (puladas).",
                "OK" if contagem[SERA_REPROCESSADA] else "WARN")
            self.emit("previa", invalidas=len(self.leitura["invalidas"]), duplicadas=self.leitura["duplicadas"],
                      validas=len(validas), status_atual=dict(self.status_atual), **contagem)
        except Exception as e:
            self.emit_log(f"Falha na prévia: {e}", "ERROR")
            self.emit("fatal_error", text=str(e))

    # -------------------------------------------------------------------- download
    def _baixar(self, chave):
        """(chave, <NFe> pronto para envio ou None, motivo da falha)."""
        if self.stop_event.is_set():
            return chave, None, None
        try:
            r = requests.get(montar_url(self.url_download, chave), timeout=TIMEOUT_DOWNLOAD, verify=False)
        except Exception as e:
            return chave, None, f"download sem resposta: {e}"
        if not 200 <= r.status_code < 300:
            return chave, None, f"download HTTP {r.status_code} {_resumo(r.text)}".rstrip()
        nfe = extrair_nfe(extrair_xml(r.content))
        if nfe is None:
            return chave, None, f"download HTTP {r.status_code}: a resposta não traz um <NFe>"
        if b"NFe" + chave.encode() not in nfe:
            return chave, None, "o XML baixado é de outra chave"
        return chave, nfe, None

    def _baixar_bloco(self, bloco, pasta_xmls):
        xmls = {}
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            for chave, nfe, motivo in executor.map(self._baixar, bloco):
                if nfe is not None:
                    xmls[chave] = nfe
                    with open(os.path.join(pasta_xmls, f"{chave}.xml"), "wb") as f:
                        f.write(nfe)
                elif motivo:
                    self.listas["erro_download"].append(chave)
                    self.emit_log(f"ERRO  {chave}  {motivo} (status da nota não foi alterado)", "ERROR")
        return xmls

    # ----------------------------------------------------------------------- envio
    def _enviar(self, chave, xml, seq):
        """Envia o XML e devolve "OK", "ERROR" ou "CANCELLED". O código HTTP vai para o log:
        2xx em verde, 4xx em amarelo, 5xx ou sem resposta em vermelho."""
        if self.stop_event.is_set():
            return "CANCELLED"
        try:
            r = requests.post(self.url_envio, data=xml, headers={"Content-Type": "application/xml"},
                              timeout=TIMEOUT_ENVIO, verify=False)
        except Exception as e:
            self._registrar_retorno(chave, seq, "sem resposta", "", str(e))
            self.emit_log(f"SEM RESPOSTA  {chave}: {e}", "ERROR")
            return "ERROR"
        codigo, sefaz = r.status_code, retorno_sefaz(r.text)
        self._registrar_retorno(chave, seq, f"HTTP {codigo}", sefaz, _resumo(r.text, 300))
        detalhe = sefaz or _resumo(r.text, 120)
        texto = f"HTTP {codigo}  {chave}" + (f"  {detalhe}" if detalhe else "")
        if 200 <= codigo < 300:
            self.emit_log(texto, "OK")
            return "OK"
        self.emit_log(texto, "WARN" if codigo < 500 else "ERROR")
        return "ERROR"

    def _registrar_retorno(self, chave, seq, status, sefaz, resposta):
        with self.log_lock:
            self.retornos.append((chave, seq, status, sefaz, resposta))
            self.codigos[status] = self.codigos.get(status, 0) + 1

    # ---------------------------------------------------------------- reprocessar
    def reprocessar(self, simular, pasta_saida):
        """Baixa, atualiza o status e envia as chaves "será reprocessada" da última prévia.
        simular=True: baixa os XMLs, executa o UPDATE e faz ROLLBACK; nada é gravado nem enviado."""
        modo = "SIMULAÇÃO" if simular else "REPROCESSAMENTO"
        try:
            chaves = self.lista(SERA_REPROCESSADA)
            blocos = [chaves[i:i + TAMANHO_BLOCO] for i in range(0, len(chaves), TAMANHO_BLOCO)]
            pasta = os.path.join(pasta_saida, f"reprocessamento_{'simulacao_' if simular else ''}"
                                              f"{datetime.now():%Y-%m-%d_%H%M%S}")
            pasta_xmls = os.path.join(pasta, "xmls")
            os.makedirs(pasta_xmls, exist_ok=True)
            self.listas = {nome: [] for nome in ("enviadas", "erro_download", "erro_atualizacao", "erro_envio",
                                                 "status3_nao_enviadas", "nao_processadas", "simuladas")}
            self.retornos, self.codigos = [], {}
            self._baixados = self._linhas_atualizadas = self._feitas = 0
            self._total = len(chaves)
            self.emit("total_itens", n=len(chaves))
            self.emit_log(f"{modo}: {len(chaves)} chave(s) em {len(blocos)} bloco(s) de até {TAMANHO_BLOCO}.", "INFO")
            sql_selecionar = SQL_SELECIONAR_SEQ.format(pular=1 if self.pular_autorizadas else 0,
                                                       autorizada=STATUS_AUTORIZADA)

            conn = self.conectar()
            try:
                cur = conn.cursor()
                for n, bloco in enumerate(blocos, start=1):
                    if self.stop_event.is_set():
                        self.listas["nao_processadas"] += [c for b in blocos[n - 1:] for c in b]
                        self.emit_log("Parada solicitada: blocos seguintes não foram executados.", "WARN")
                        break
                    prefixo = f"Bloco {n}/{len(blocos)}"

                    # 1) XML em mãos antes de mexer no status
                    xmls = self._baixar_bloco(bloco, pasta_xmls)
                    self._baixados += len(xmls)
                    self._feitas += sum(1 for c in bloco if c in self.listas["erro_download"])
                    if self.stop_event.is_set():
                        falhas = set(self.listas["erro_download"])
                        self.listas["nao_processadas"] += [c for c in bloco if c not in falhas]
                        self.listas["nao_processadas"] += [c for b in blocos[n:] for c in b]
                        self.emit_log(f"{prefixo}: parada solicitada durante o download; o status das notas "
                                      f"deste bloco não foi alterado.", "WARN")
                        break
                    com_xml = [c for c in bloco if c in xmls]
                    self.emit_log(f"{prefixo}: {len(com_xml)} XML(s) baixado(s) de {len(bloco)}.",
                                  "OK" if len(com_xml) == len(bloco) else "WARN")
                    self._contagem()
                    if not com_xml:
                        continue

                    # 2) IND_STATUS_NFE = 3 para as notas com XML
                    try:
                        carregar_temp(cur, "#bloco", com_xml)
                        cur.execute(sql_selecionar)
                        cur.execute(SQL_LER_SEQ)
                        seqs = {}
                        for a_id, seq in cur.fetchall():
                            seqs.setdefault(str(a_id).strip(), []).append(seq)
                        cur.execute(SQL_UPDATE)
                        afetadas = max(cur.rowcount, 0)
                        if simular:
                            conn.rollback()
                        else:
                            conn.commit()
                    except Exception as e:
                        conn.rollback()
                        self.listas["erro_atualizacao"] += com_xml
                        self._feitas += len(com_xml)
                        self.emit_log(f"{prefixo}: UPDATE falhou e foi desfeito; nada deste bloco foi enviado: {e}",
                                      "ERROR")
                        self._contagem()
                        continue
                    self._linhas_atualizadas += afetadas
                    sem_linha = [c for c in com_xml if c not in seqs]
                    if sem_linha:
                        self.listas["erro_atualizacao"] += sem_linha
                        self._feitas += len(sem_linha)
                        self.emit_log(f"{prefixo}: {len(sem_linha)} chave(s) sem linha para atualizar agora (a nota "
                                      f"mudou desde a prévia); não foram enviadas.", "WARN")
                    atualizadas = [c for c in com_xml if c in seqs]
                    self.emit_log(f"{prefixo}: IND_STATUS_NFE = {STATUS_REPROCESSAR} em {afetadas} linha(s)"
                                  f"{' (desfeito: simulação)' if simular else ''}.", "OK")
                    if simular:
                        self.listas["simuladas"] += atualizadas
                        self._feitas += len(atualizadas)
                        self._contagem()
                        continue

                    # 3) envio do XML completo
                    with ThreadPoolExecutor(max_workers=self.threads) as executor:
                        futures = {executor.submit(self._enviar, c, xmls[c], seqs[c][0]): c for c in atualizadas}
                        for future in as_completed(futures):
                            chave, resultado = futures[future], future.result()
                            destino = {"OK": "enviadas", "ERROR": "erro_envio"}.get(resultado, "status3_nao_enviadas")
                            self.listas[destino].append(chave)
                            self._feitas += 1
                            self._contagem()
                    if self.listas["status3_nao_enviadas"]:
                        self.emit_log(f"{prefixo}: parada solicitada durante o envio; "
                                      f"{len(self.listas['status3_nao_enviadas'])} nota(s) ficaram com status "
                                      f"{STATUS_REPROCESSAR} sem envio.", "WARN")
            finally:
                conn.close()

            if self.codigos:
                self.emit_log("Retornos do envio: " + " | ".join(
                    f"{codigo}: {n}" for codigo, n in sorted(self.codigos.items())), "INFO")
            self._gravar_resultado(pasta, simular)
            erros = sum(len(self.listas[nome]) for nome in ("erro_download", "erro_atualizacao", "erro_envio"))
            self.emit("done", cancelled=self.stop_event.is_set(), simular=simular, baixados=self._baixados,
                      atualizadas=self._linhas_atualizadas, enviadas=len(self.listas["enviadas"]), erro=erros,
                      pendentes=len(self.listas["status3_nao_enviadas"]), codigos=dict(self.codigos), pasta=pasta,
                      log_file=str(self.log_file))
        except Exception as e:
            self.emit_log(f"Falha no {modo.lower()}: {e}", "ERROR")
            self.emit("fatal_error", text=str(e))

    def _contagem(self):
        erros = sum(len(self.listas[nome]) for nome in ("erro_download", "erro_atualizacao", "erro_envio"))
        self.emit("counts", done=self._feitas, total=self._total, baixados=self._baixados,
                  atualizadas=self._linhas_atualizadas, enviadas=len(self.listas["enviadas"]), erro=erros)

    def _gravar_resultado(self, pasta, simular):
        arquivos = {
            "enviadas.txt": self.listas["enviadas"],
            "seriam_reprocessadas.txt": self.listas["simuladas"],
            "erro_download.txt": self.listas["erro_download"],
            "erro_atualizacao.txt": self.listas["erro_atualizacao"],
            "erro_envio.txt": self.listas["erro_envio"],
            "status3_nao_enviadas.txt": self.listas["status3_nao_enviadas"],
            "nao_processadas.txt": self.listas["nao_processadas"],
            "nao_encontradas.txt": self.lista(NAO_ENCONTRADA),
            "ja_autorizadas.txt": self.lista(JA_AUTORIZADA),
            "invalidas.txt": self.leitura["invalidas"] if self.leitura else [],
        }
        for nome, chaves in arquivos.items():
            if chaves:
                with open(os.path.join(pasta, nome), "w", encoding="utf-8") as f:
                    f.write("\n".join(chaves) + "\n")
        if self.retornos:
            with open(os.path.join(pasta, "retornos.txt"), "w", encoding="utf-8-sig") as f:
                f.write("A_ID | NUM_SEQ_NFE | HTTP | RETORNO SEFAZ | RESPOSTA\n")
                for linha in sorted(self.retornos):
                    f.write(" | ".join(str(campo) for campo in linha) + "\n")
        resumo = [
            "Operação: Reprocessamento de documentos NFCe",
            f"Modo: {'SIMULAÇÃO (nada foi gravado nem enviado)' if simular else 'REPROCESSAMENTO'}",
            f"Ambiente: {self.ambiente}",
            f"UPDATE INTERF_NFE SET IND_STATUS_NFE = {STATUS_REPROCESSAR} WHERE NUM_SEQ_NFE IN (<notas do arquivo>)",
            f"Pular notas já autorizadas (IND_STATUS_NFE = {STATUS_AUTORIZADA}): "
            f"{'sim' if self.pular_autorizadas else 'não'}",
            f"Usuário do Windows: {os.environ.get('USERNAME', '?')}",
            f"Data/hora: {datetime.now():%d/%m/%Y %H:%M:%S}",
            "",
            f"XMLs baixados: {self._baixados} (pasta xmls)",
            f"Linhas {'que seriam atualizadas' if simular else 'atualizadas'} para status {STATUS_REPROCESSAR}: "
            f"{self._linhas_atualizadas}",
            f"Enviadas com HTTP 2xx: {len(self.listas['enviadas'])}",
            f"Erro no download: {len(self.listas['erro_download'])} | erro no UPDATE: "
            f"{len(self.listas['erro_atualizacao'])} | erro no envio: {len(self.listas['erro_envio'])}",
            f"Com status {STATUS_REPROCESSAR} e sem envio (parada): {len(self.listas['status3_nao_enviadas'])} | "
            f"não processadas: {len(self.listas['nao_processadas'])}",
            f"Não encontradas: {len(arquivos['nao_encontradas.txt'])} | já autorizadas (puladas): "
            f"{len(arquivos['ja_autorizadas.txt'])} | inválidas: {len(arquivos['invalidas.txt'])}",
            "Retornos do envio: " + (" | ".join(f"{c}: {n}" for c, n in sorted(self.codigos.items())) or "nenhum"),
            f"Log: {self.log_file}",
        ]
        with open(os.path.join(pasta, "resumo.txt"), "w", encoding="utf-8-sig") as f:
            f.write("\n".join(resumo) + "\n")
