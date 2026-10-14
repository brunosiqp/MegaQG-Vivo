"""Engine portada sem alteração de lógica do MEGA QG VIVO NFCom v2.3 (legado/NFCom preview/qg.py)."""
from modulos.nfcom.comum import *  # noqa: F401,F403 - imports/constantes do QG original


class DownloadXmlsEngine:
    """
    Transcrição fiel do main.py + operations.py de download: para cada ID,
    monta a URL (Produção ou Homologação) com o placeholder {ID_DOC}, faz
    GET (verify=False, igual ao original -- o servidor usa certificado que
    o requests não valida por padrão) e salva o conteúdo em
    pasta_saida/{id}.xml. Em caso de exceção, grava o ID em arquivo_erro,
    exatamente como o operations.py original.
    """

    URL_PRD = _endpoint("download_url_prd", "MEGAQG_DOWNLOAD_URL_PRD")
    URL_HML = _endpoint("download_url_hml", "MEGAQG_DOWNLOAD_URL_HML")

    def __init__(self, event_queue, stop_event, *, url_base, pasta_saida, arquivo_erro, threads, log_dir):
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.url_base = url_base
        self.pasta_saida = pasta_saida
        self.arquivo_erro = arquivo_erro
        self.threads = max(1, threads)
        self.log_dir = log_dir
        self.log_file = None
        self.erro_lock = threading.Lock()
        self.log_lock = threading.Lock()
        self.ok = 0
        self.erro = 0

    def emit(self, kind, **data):
        self.event_queue.put({"kind": kind, **data})

    def emit_log(self, text, status="INFO"):
        self.emit("log_line", text=text, status=status)

    def _garantir_log(self):
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "download_xmls_log.txt")

    def _log_arquivo(self, id_doc, status, extra=""):
        linha = f"{datetime.now().isoformat()} | {id_doc} | {status} | {extra}\n"
        with self.log_lock:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(linha)

    def execute(self, id_doc):
        if self.stop_event.is_set():
            return "CANCELLED"
        url = self.url_base.format(ID_DOC=id_doc)
        try:
            response = requests.get(url, timeout=15, verify=False)
            conteudo = response.content
            file_path = os.path.join(self.pasta_saida, f"{id_doc}.xml")
            with open(file_path, "wb") as file:
                file.write(conteudo)
            self._log_arquivo(id_doc, "OK", file_path)
            self.emit_log(f"OK    {id_doc}  ->  {file_path}", "OK")
            return "OK"
        except Exception as e:
            if self.arquivo_erro:
                with self.erro_lock:
                    with open(self.arquivo_erro, "a", encoding="utf-8") as file_erro:
                        file_erro.write(f"{id_doc}\n")
            self._log_arquivo(id_doc, "ERROR", str(e))
            self.emit_log(f"ERRO  {id_doc}: {e}", "ERROR")
            return "ERROR"

    def run(self, arquivo_entrada):
        try:
            if not self.url_base:
                self.emit("fatal_error", text=(
                    "Endpoint de Download de XMLs não configurado. Defina download_url_prd/"
                    "download_url_hml em config.json ou as variáveis de ambiente "
                    "MEGAQG_DOWNLOAD_URL_PRD / MEGAQG_DOWNLOAD_URL_HML."))
                return
            self._garantir_log()
            with open(arquivo_entrada, encoding="utf-8") as f:
                ids = [l.strip() for l in f if l.strip()]

            total = len(ids)
            self.emit("total_itens", n=total)
            self.emit_log(f"{total} ID(s) carregado(s). Iniciando download...", "INFO")

            os.makedirs(self.pasta_saida, exist_ok=True)
            if self.arquivo_erro:
                open(self.arquivo_erro, "a", encoding="utf-8").close()

            done = 0
            with ThreadPoolExecutor(max_workers=self.threads) as executor:
                futures = {executor.submit(self.execute, id_doc): id_doc for id_doc in ids}
                for future in as_completed(futures):
                    resultado = future.result()
                    done += 1
                    if resultado == "OK":
                        self.ok += 1
                    elif resultado == "ERROR":
                        self.erro += 1
                    self.emit("counts", ok=self.ok, erro=self.erro, done=done, total=total)

            self.emit("done", cancelled=self.stop_event.is_set(), ok=self.ok, erro=self.erro, total=total,
                       log_file=str(self.log_file))
        except Exception as e:
            self.emit("fatal_error", text=str(e))
