"""
Download massivo de XMLs de NFCe: para cada chave de acesso de um .txt, consulta a API de XML
de emissão e salva <chave>.xml na pasta escolhida pelo usuário.

URL em nfce_download_url_prd/_hml (config.json). A chave entra no lugar do marcador {CHAVE};
se a URL não tiver o marcador, a chave vai no fim (formato ".../XMLEmissao?chave=").

Só vira arquivo a resposta HTTP 2xx que traz um XML. Qualquer outra (404, 500, corpo vazio,
sem resposta) conta como erro, aparece no log com o código HTTP e a chave vai para
_chaves_com_erro_<data>.txt na pasta de saída, pronta para reprocessar.

Não depende de Tkinter: conversa com a tela por event_queue, como as demais engines.
"""
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests
import urllib3

from core.config import AMBIENTE_PRD, url_por_ambiente
from modulos.nfce.comum import ler_chaves

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MARCADOR = "{CHAVE}"
TIMEOUT = 30


def montar_url(url_base: str, chave: str) -> str:
    return url_base.replace(MARCADOR, chave) if MARCADOR in url_base else url_base + chave


def extrair_xml(conteudo: bytes) -> bytes | None:
    """XML da resposta, ou None se ela não trouxer um XML. Aceita o XML puro ou uma
    string JSON com o XML dentro ("<?xml ...>")."""
    corpo = conteudo.lstrip(b"\xef\xbb\xbf \t\r\n")
    if corpo.startswith(b"<"):
        return conteudo
    if corpo.startswith(b'"'):
        try:
            texto = json.loads(corpo.decode("utf-8"))
        except ValueError:
            return None
        if isinstance(texto, str) and texto.lstrip().startswith("<"):
            return texto.encode("utf-8")
    return None


class DownloadXmlsNfceEngine:
    def __init__(self, event_queue, stop_event, *, ambiente=AMBIENTE_PRD, pasta_saida, threads, log_dir):
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.ambiente = ambiente
        self.url_base = url_por_ambiente("nfce_download_url", ambiente)
        self.pasta_saida = pasta_saida
        self.threads = max(1, threads)
        self.log_dir = log_dir
        self.log_file = None
        self.lock = threading.Lock()
        self.ok = 0
        self.erro = 0
        self.com_erro = []

    def emit(self, kind, **data):
        self.event_queue.put({"kind": kind, **data})

    def emit_log(self, text, status="INFO"):
        self.emit("log_line", text=text, status=status)

    def _log_arquivo(self, chave, status, extra=""):
        linha = f"{datetime.now().isoformat()} | {chave} | {status} | {extra}\n"
        with self.lock:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(linha)

    def _falha(self, chave, status, detalhe):
        with self.lock:
            self.com_erro.append(chave)
        self._log_arquivo(chave, f"ERRO {status}", detalhe)
        self.emit_log(f"ERRO  {chave}  {status}" + (f"  {detalhe}" if detalhe else ""), "ERROR")
        return "ERROR"

    def baixar(self, chave):
        if self.stop_event.is_set():
            return "CANCELLED"
        try:
            r = requests.get(montar_url(self.url_base, chave), timeout=TIMEOUT, verify=False)
        except Exception as e:
            return self._falha(chave, "SEM RESPOSTA", str(e))
        status = f"HTTP {r.status_code}"
        resposta = " ".join((r.text or "").split())[:200]
        if not 200 <= r.status_code < 300:
            return self._falha(chave, status, resposta)
        xml = extrair_xml(r.content)
        if xml is None:
            return self._falha(chave, status, "resposta sem XML: " + (resposta or "(vazia)"))
        try:
            caminho = os.path.join(self.pasta_saida, f"{chave}.xml")
            with open(caminho, "wb") as f:
                f.write(xml)
        except OSError as e:
            return self._falha(chave, status, f"não foi possível gravar o arquivo: {e}")
        self._log_arquivo(chave, f"OK {status}", caminho)
        self.emit_log(f"OK    {chave}  {status}", "OK")
        return "OK"

    def _gravar_lista(self, nome, chaves):
        if not chaves:
            return None
        caminho = os.path.join(self.pasta_saida, f"_{nome}_{datetime.now():%Y-%m-%d_%H%M%S}.txt")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("\n".join(chaves) + "\n")
        return caminho

    def run(self, arquivo_entrada):
        try:
            if not self.url_base:
                sufixo = "prd" if self.ambiente == AMBIENTE_PRD else "hml"
                self.emit("fatal_error", text=(
                    f"Endpoint de Download de XMLs de NFCe não configurado para {self.ambiente}. Defina "
                    f"nfce_download_url_{sufixo} em config.json ou a variável de ambiente "
                    f"MEGAQG_NFCE_DOWNLOAD_URL_{sufixo.upper()}."))
                return
            os.makedirs(self.log_dir, exist_ok=True)
            self.log_file = os.path.join(self.log_dir, "nfce_download_xmls_log.txt")

            leitura = ler_chaves(arquivo_entrada)
            chaves, invalidas = leitura["validas"], leitura["invalidas"]
            self.emit_log(f"Arquivo: {len(chaves)} chave(s) válida(s), {len(invalidas)} inválida(s), "
                          f"{leitura['duplicadas']} repetida(s) ignorada(s).", "INFO")
            for chave in invalidas[:20]:
                self.emit_log(f"INVÁLIDA  {chave}  (a chave de acesso tem 44 dígitos)", "WARN")
            if len(invalidas) > 20:
                self.emit_log(f"... e mais {len(invalidas) - 20} chave(s) inválida(s).", "WARN")
            if not chaves:
                self.emit("fatal_error", text="Nenhuma chave válida no arquivo (chave de acesso com 44 dígitos).")
                return

            total = len(chaves)
            os.makedirs(self.pasta_saida, exist_ok=True)
            self.emit("total_itens", n=total)
            self.emit("counts", ok=0, erro=0, invalidas=len(invalidas), done=0, total=total)
            self.emit_log(f"Iniciando o download de {total} XML(s) em {self.pasta_saida} ({self.ambiente})...", "INFO")

            done = 0
            nao_processadas = []
            with ThreadPoolExecutor(max_workers=self.threads) as executor:
                futures = {executor.submit(self.baixar, chave): chave for chave in chaves}
                for future in as_completed(futures):
                    resultado = future.result()
                    done += 1
                    if resultado == "OK":
                        self.ok += 1
                    elif resultado == "ERROR":
                        self.erro += 1
                    else:
                        nao_processadas.append(futures[future])
                    self.emit("counts", ok=self.ok, erro=self.erro, invalidas=len(invalidas), done=done,
                              total=total)

            arquivo_erro = self._gravar_lista("chaves_com_erro", self.com_erro)
            arquivo_pendentes = self._gravar_lista("chaves_nao_processadas", nao_processadas)
            self._gravar_lista("chaves_invalidas", invalidas)
            if arquivo_erro:
                self.emit_log(f"Chaves com erro gravadas em {arquivo_erro}", "WARN")
            if arquivo_pendentes:
                self.emit_log(f"Parado antes do fim: {len(nao_processadas)} chave(s) não processada(s) em "
                              f"{arquivo_pendentes}", "WARN")
            self.emit("done", cancelled=self.stop_event.is_set(), ok=self.ok, erro=self.erro,
                      invalidas=len(invalidas), total=total, pasta=self.pasta_saida, arquivo_erro=arquivo_erro,
                      log_file=str(self.log_file))
        except Exception as e:
            self.emit("fatal_error", text=str(e))
