"""
Correção de XMLs de NFSe (DPS) em lote: o QG XML v4 dentro do MegaQG Vivo.

Para cada .xml da pasta de entrada aplica as correções escolhidas (correcoes.py) e:
  - nota alterada   -> salva em <saída>/xmls corrigidos (UTF-8, reindentada com 2 espaços);
  - nota sem alteração -> não é copiada;
  - CEP ausente ou sem resolução -> original copiado para <saída>/xmls não corrigidos sem cep;
  - XML inválido, falta de permissão ou erro inesperado -> original copiado para
    <saída>/xmls não corrigidos.
A pasta de entrada nunca é alterada.

O histórico (log_dir/nfse_correcao_xml_historico.txt) registra, para cada nota, data e hora,
nome, status e todas as alterações; ele é renovado quando completa 7 dias.

O arquivo é regravado mantendo os namespaces como estavam no original (sem trocar para ns0:).

Não depende de Tkinter: conversa com a tela por event_queue, como as demais engines.
"""
import os
import shutil
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from xml.sax.saxutils import escape, quoteattr

from modulos.nfse.correcao_xml.cep import PAUSA_ENTRE_CONSULTAS, ResolvedorMunicipio
from modulos.nfse.correcao_xml.correcoes import (
    CORRECOES,
    CST_PADRAO,
    IDS_CORRECOES,
    ErroCorrecaoCep,
    corrigir_documento,
    nome_local,
    obter_namespace,
)

PASTA_CORRIGIDOS = "xmls corrigidos"
PASTA_PENDENTES = "xmls não corrigidos"
PASTA_PENDENTES_SEM_CEP = "xmls não corrigidos sem cep"
ARQUIVO_HISTORICO = "nfse_correcao_xml_historico.txt"
RETENCAO_HISTORICO = timedelta(days=7)
NOMES_CORRECOES = {identificador: nome for identificador, nome, _detalhe in CORRECOES}


def _serializar(elemento, namespace_pai, partes):
    """Escreve o elemento redeclarando o xmlns só onde ele muda, como nos XMLs fiscais
    (<DPS xmlns="...nfse"> ... <Signature xmlns="...xmldsig#">), sem criar prefixos."""
    namespace, nome = obter_namespace(elemento.tag), nome_local(elemento.tag)
    partes.append(f"<{nome}")
    if namespace != namespace_pai:
        partes.append(f" xmlns={quoteattr(namespace)}")
    for chave, valor in elemento.attrib.items():
        partes.append(f" {chave}={quoteattr(valor)}")
    if len(elemento) == 0 and not elemento.text:
        partes.append("/>")
    else:
        partes.append(">" + escape(elemento.text or ""))
        for filho in elemento:
            _serializar(filho, namespace, partes)
        partes.append(f"</{nome}>")
    partes.append(escape(elemento.tail or ""))


def gravar_xml(arvore, caminho_original, caminho_saida):
    """Regrava o XML em UTF-8, reindentado com 2 espaços e com os namespaces como estavam.

    XML que só usa xmlns padrão (o caso dos XMLs fiscais) sai sem nenhum prefixo. Se o
    original declara prefixos ou tem atributos com namespace, quem grava é o ElementTree,
    mantendo o xmlns da raiz e os prefixos declarados."""
    raiz = arvore.getroot()
    ET.indent(arvore, space="  ")
    declarados = [ns for _evento, ns in ET.iterparse(caminho_original, events=("start-ns",))]
    so_xmlns_padrao = all(prefixo == "" for prefixo, _uri in declarados) and not any(
        chave.startswith("{") for elemento in raiz.iter() for chave in elemento.attrib)
    if so_xmlns_padrao:
        partes = ['<?xml version="1.0" encoding="UTF-8"?>\n']
        _serializar(raiz, "", partes)
        with open(caminho_saida, "w", encoding="utf-8", newline="\n") as f:
            f.write("".join(partes).rstrip() + "\n")
        return
    namespace_raiz = obter_namespace(raiz.tag)
    if namespace_raiz and ("", namespace_raiz) in declarados:
        ET.register_namespace("", namespace_raiz)
    for prefixo, uri in declarados:
        if prefixo:
            try:
                ET.register_namespace(prefixo, uri)
            except ValueError:
                pass  # prefixo reservado (ns0, ns1...): o ElementTree escolhe um
    arvore.write(caminho_saida, encoding="utf-8", xml_declaration=True)


class CorrecaoXmlEngine:
    def __init__(self, event_queue, stop_event, *, pasta_entrada, pasta_saida, log_dir, dados_dir,
                 correcoes=None, cst_padrao=CST_PADRAO, pausa=PAUSA_ENTRE_CONSULTAS):
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.pasta_entrada = pasta_entrada
        self.pasta_saida = pasta_saida
        self.log_dir = log_dir
        self.correcoes = [c for c in IDS_CORRECOES if correcoes is None or c in correcoes]
        self.cst_padrao = (cst_padrao or CST_PADRAO).strip().zfill(2)
        self.resolvedor = ResolvedorMunicipio(dados_dir, log=lambda texto: self.emit_log(f"  {texto}", "INFO"),
                                              pausa=pausa)
        self.cache_ceps = {}  # CEPs resolvidos neste lote
        self.historico = os.path.join(log_dir, ARQUIVO_HISTORICO)
        self.contagem = {"corrigidos": 0, "sem_alteracao": 0, "pendentes_cep": 0, "pendentes_erro": 0}
        self.por_correcao = {identificador: 0 for identificador in self.correcoes}

    # ---------------------------------------------------------------- eventos/log
    def emit(self, kind, **data):
        self.event_queue.put({"kind": kind, **data})

    def emit_log(self, text, status="INFO"):
        self.emit("log_line", text=text, status=status)

    def _preparar_historico(self):
        """Um histórico só, reiniciado quando completa 7 dias."""
        os.makedirs(self.log_dir, exist_ok=True)
        if os.path.exists(self.historico):
            criado_em = datetime.fromtimestamp(os.path.getctime(self.historico))
            if datetime.now() - criado_em >= RETENCAO_HISTORICO:
                os.remove(self.historico)
        if not os.path.exists(self.historico):
            with open(self.historico, "w", encoding="utf-8") as f:
                f.write("MEGAQG VIVO - CORREÇÃO DE XMLs NFSe - HISTÓRICO DE NOTAS\n"
                        f"Criado em: {datetime.now():%d/%m/%Y %H:%M:%S}\n" + "=" * 60 + "\n")

    def _registrar(self, nome, status, mensagens):
        linhas = ["", f"Data/hora: {datetime.now():%d/%m/%Y %H:%M:%S}", f"DPS: {nome}", f"Status: {status}",
                  "Detalhes:"]
        linhas.extend(f"- {mensagem}" for mensagem in mensagens)
        if not mensagens:
            linhas.append("- Nenhuma alteração foi realizada.")
        with open(self.historico, "a", encoding="utf-8") as f:
            f.write("\n".join(linhas) + "\n" + "-" * 60 + "\n")

    # --------------------------------------------------------------- uma nota
    def processar_arquivo(self, caminho_entrada, caminho_saida):
        """Corrige um XML. Devolve (alterou, mensagens, alterações por correção); só grava
        o arquivo de saída se houve alguma alteração."""
        arvore = ET.parse(caminho_entrada)
        alteracoes, mensagens, por_correcao = corrigir_documento(
            arvore.getroot(), self.resolvedor, self.cache_ceps, self.correcoes, self.cst_padrao)
        if alteracoes:
            gravar_xml(arvore, caminho_entrada, caminho_saida)
        return bool(alteracoes), mensagens, por_correcao

    def _pendente(self, arquivo, pasta, chave, status, detalhe, nivel):
        """Copia o original para a pasta de correção manual e registra no histórico."""
        self.contagem[chave] += 1
        mensagens = [detalhe]
        try:
            destino = os.path.join(self.pasta_saida, pasta)
            os.makedirs(destino, exist_ok=True)
            shutil.copy2(os.path.join(self.pasta_entrada, arquivo), os.path.join(destino, arquivo))
        except Exception as erro_copia:
            mensagens.append(f"Também não foi possível copiar para '{pasta}': {erro_copia}")
        resumo = " | ".join(mensagens)
        if len(resumo) > 200:  # na tela vai o começo; o texto inteiro fica no histórico
            resumo = resumo[:200].rstrip() + "… (detalhes no histórico)"
        self.emit_log(f"PENDENTE  {arquivo}: {resumo}", nivel)
        self._registrar(arquivo, status, mensagens)

    # ------------------------------------------------------------------- lote
    def run(self):
        inicio = time.perf_counter()
        try:
            if not self.correcoes:
                self.emit("fatal_error", text="Marque pelo menos uma correção.")
                return
            arquivos = sorted(f for f in os.listdir(self.pasta_entrada) if f.lower().endswith(".xml"))
            if not arquivos:
                self.emit("fatal_error", text=f"Nenhum arquivo .xml encontrado em {self.pasta_entrada}.")
                return
            destino = os.path.join(self.pasta_saida, PASTA_CORRIGIDOS)
            os.makedirs(destino, exist_ok=True)
            self._preparar_historico()

            total = len(arquivos)
            self.emit("total_itens", n=total)
            self.emit_log(f"{total} XML(s) em {self.pasta_entrada}. Correções: "
                          + ", ".join(NOMES_CORRECOES[c] for c in self.correcoes) + ".", "INFO")
            feitos = 0
            for arquivo in arquivos:
                if self.stop_event.is_set():
                    self.emit_log(f"Parada solicitada: {total - feitos} arquivo(s) não foram processados.", "WARN")
                    break
                try:
                    alterado, mensagens, por_correcao = self.processar_arquivo(
                        os.path.join(self.pasta_entrada, arquivo), os.path.join(destino, arquivo))
                    for identificador, quantidade in por_correcao.items():
                        self.por_correcao[identificador] += quantidade
                    if alterado:
                        self.contagem["corrigidos"] += 1
                        resumo = ", ".join(f"{NOMES_CORRECOES[c]}: {n}" for c, n in por_correcao.items() if n)
                        self.emit_log(f"CORRIGIDA  {arquivo}  ({resumo})", "OK")
                    else:
                        self.contagem["sem_alteracao"] += 1
                        self.emit_log(f"SEM ALTERAÇÃO  {arquivo}", "INFO")
                    self._registrar(arquivo, "Corrigida" if alterado else "Sem alterações", mensagens)
                except ErroCorrecaoCep as erro:
                    self._pendente(arquivo, PASTA_PENDENTES_SEM_CEP, "pendentes_cep",
                                   "Pendente: CEP inválido ou sem resolução",
                                   f"CEP inválido ou sem resolução: {erro}", "WARN")
                except ET.ParseError as erro:
                    self._pendente(arquivo, PASTA_PENDENTES, "pendentes_erro", "Pendente: XML inválido",
                                   f"XML inválido: {erro}", "ERROR")
                except PermissionError as erro:
                    self._pendente(arquivo, PASTA_PENDENTES, "pendentes_erro", "Erro de permissão",
                                   f"Sem permissão para ler ou salvar o arquivo: {erro}", "ERROR")
                except Exception as erro:
                    self._pendente(arquivo, PASTA_PENDENTES, "pendentes_erro", "Pendente: erro inesperado",
                                   f"Erro inesperado: {erro}", "ERROR")
                feitos += 1
                self.emit("counts", done=feitos, total=total, **self.contagem)

            duracao = int(time.perf_counter() - inicio)
            self.emit_log("Alterações por correção: " + (" | ".join(
                f"{NOMES_CORRECOES[c]}: {n}" for c, n in self.por_correcao.items() if n) or "nenhuma"), "INFO")
            self.emit("done", cancelled=self.stop_event.is_set(), total=total, processados=feitos,
                      por_correcao=dict(self.por_correcao), ceps=len(self.cache_ceps), pasta=self.pasta_saida,
                      historico=self.historico, duracao=f"{duracao // 3600:02d}:{duracao % 3600 // 60:02d}:"
                                                        f"{duracao % 60:02d}", **self.contagem)
        except Exception as erro:
            self.emit("fatal_error", text=str(erro))
