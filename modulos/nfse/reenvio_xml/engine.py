"""Engine portada do MEGA QG VIVO NFSe v2.0 (legado/NFSe/qg.py); só a URL passou a vir do config.json."""
from modulos.nfse.comum import *  # noqa: F401,F403 - imports do QG original


class ReenvioXmlEngine:

    def __init__(self, event_queue, stop_event, *, ambiente=AMBIENTE_PRD, log_dir, threads):
        # MegaQG Vivo: URL vem do config.json (nfse_reenvio_url_prd/_hml), não mais fixa no código
        self.BASE_URL = url_por_ambiente("nfse_reenvio_url", ambiente)
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.log_dir = log_dir
        self.threads = max(1, threads)
        self.log_lock = threading.Lock()
        self.log_file = None
        self.erro_file = None
        self.sucesso = []
        self.erro = []

    def emit(self, kind, **data):
        self.event_queue.put({"kind": kind, **data})

    def emit_log(self, text, status="INFO"):
        self.emit("log_line", text=text, status=status)

    def _preparar_log(self):
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "reenvio_xml_log_nfse.txt")
        self.erro_file = os.path.join(self.log_dir, "xml_com_erro_nfse.txt")

    def _log_arquivo(self, nivel, msg):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        with self.log_lock:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"{ts} - {nivel} - {msg}\n")

    def reenviar_xml(self, xml_conteudo):
        try:
            r = requests.post(self.BASE_URL, data=xml_conteudo,
                               headers={"Content-Type": "application/xml"}, timeout=60)
            return r.status_code, r.text
        except requests.exceptions.Timeout:
            return None, "Timeout na requisição com a API"
        except requests.exceptions.ConnectionError:
            return None, "Erro de conexão com a API"
        except requests.exceptions.RequestException as e:
            return None, f"Erro na requisição: {e}"
        except Exception as e:
            return None, f"Erro inesperado: {e}"

    def enviar(self, arquivo, caminho_xml):
        if self.stop_event.is_set():
            return "CANCELLED", arquivo

        try:
            with open(caminho_xml, "r", encoding="utf-8") as f:
                xml_conteudo = f.read()
        except Exception as e:
            self._log_arquivo("ERROR", f"{arquivo} | ERRO AO LER XML | {e}")
            self.emit_log(f"ERRO  {arquivo}: falha ao ler o XML - {e}", "ERROR")
            return "ERROR", arquivo

        status, resposta = self.reenviar_xml(xml_conteudo)

        if status is None:
            self._log_arquivo("ERROR", f"{arquivo} | ERRO DE CONEXÃO | {resposta}")
            self.emit_log(f"ERRO  {arquivo}: {resposta}", "ERROR")
            return "ERROR", arquivo
        elif 200 <= status < 300:
            self._log_arquivo("INFO", f"{arquivo} | SUCESSO | Status: {status} | Resposta: {resposta}")
            self.emit_log(f"OK    {arquivo}  HTTP {status}", "OK")
            return "OK", arquivo
        else:
            self._log_arquivo("ERROR", f"{arquivo} | ERRO API | Status: {status} | Resposta: {resposta}")
            self.emit_log(f"ERRO  {arquivo}  HTTP {status}", "ERROR")
            return "ERROR", arquivo

    def run(self, pasta):
        try:
            self._preparar_log()
            arquivos = [f for f in os.listdir(pasta) if f.lower().endswith(".xml")]
            total = len(arquivos)

            if total == 0:
                self.emit("fatal_error", text="Nenhum XML encontrado na pasta.")
                return

            self.emit("total_itens", n=total)
            self.emit_log(f"Total de XMLs encontrados: {total}. Iniciando reenvio...", "INFO")

            done = 0
            with ThreadPoolExecutor(max_workers=self.threads) as executor:
                futures = {
                    executor.submit(self.enviar, arquivo, os.path.join(pasta, arquivo)): arquivo
                    for arquivo in arquivos
                }
                for future in as_completed(futures):
                    resultado, arquivo = future.result()
                    done += 1
                    if resultado == "OK":
                        self.sucesso.append(arquivo)
                    elif resultado == "ERROR":
                        self.erro.append(arquivo)
                    self.emit("counts", ok=len(self.sucesso), erro=len(self.erro), done=done, total=total)

            if self.erro:
                with open(self.erro_file, "w", encoding="utf-8") as f:
                    for item in self.erro:
                        f.write(item + "\n")
                self.emit_log(f"Lista de XMLs com erro salva em: {self.erro_file}", "WARN")

            self.emit("done", cancelled=self.stop_event.is_set(), ok=len(self.sucesso),
                       erro=len(self.erro), total=total, log_file=str(self.log_file),
                       erro_file=str(self.erro_file) if self.erro else None)
        except Exception as e:
            self.emit("fatal_error", text=str(e))
