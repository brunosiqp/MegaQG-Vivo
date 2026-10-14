"""Engine portada do MEGA QG VIVO NFSe v2.0 (legado/NFSe/qg.py); só a URL passou a vir do config.json."""
from modulos.nfse.comum import *  # noqa: F401,F403 - imports do QG original


class ConsultaDpsEngine:

    def __init__(self, event_queue, stop_event, *, ambiente=AMBIENTE_PRD, log_dir, threads):
        # MegaQG Vivo: URL vem do config.json (nfse_consulta_dps_url_prd/_hml), não mais fixa no código
        self.BASE_URL = url_por_ambiente("nfse_consulta_dps_url", ambiente)
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.log_dir = log_dir
        self.threads = max(1, threads)
        self.log_lock = threading.Lock()
        self.log_file = None
        self.ok = 0
        self.http_erro = 0
        self.erro = 0

    def emit(self, kind, **data):
        self.event_queue.put({"kind": kind, **data})

    def emit_log(self, text, status="INFO"):
        self.emit("log_line", text=text, status=status)

    def _preparar_log(self):
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "consulta_dps_log_nfse.txt")

    def _log_arquivo(self, dps, status, resposta):
        ts = datetime.now().isoformat()
        with self.log_lock:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] DPS: {dps} | Status: {status} | Resposta: {resposta}\n")

    def consultar_dps(self, identificador_dps):
        try:
            r = requests.get(self.BASE_URL, params={"chaveDPS": identificador_dps}, timeout=30)
            return r.status_code, r.text
        except Exception as e:
            return "erro", str(e)

    def executar(self, dps):
        if self.stop_event.is_set():
            return "CANCELLED"

        status, resposta = self.consultar_dps(dps)
        self._log_arquivo(dps, status, resposta)

        if status == "erro":
            self.emit_log(f"ERRO  DPS {dps}: {resposta}", "ERROR")
            return "ERROR"
        elif status == 200:
            self.emit_log(f"OK    DPS {dps}  HTTP {status}", "OK")
            return "OK"
        else:
            self.emit_log(f"HTTP  DPS {dps}  Status {status}", "WARN")
            return "HTTP_ERR"

    def run(self, arquivo_dps):
        try:
            self._preparar_log()
            with open(arquivo_dps, encoding="utf-8") as f:
                dps_lista = [l.strip() for l in f if l.strip()]

            total = len(dps_lista)
            self.emit("total_itens", n=total)
            self.emit_log(f"{total} identificador(es) DPS carregado(s). Iniciando consulta...", "INFO")

            done = 0
            with ThreadPoolExecutor(max_workers=self.threads) as executor:
                futures = {executor.submit(self.executar, dps): dps for dps in dps_lista}
                for future in as_completed(futures):
                    resultado = future.result()
                    done += 1
                    if resultado == "OK":
                        self.ok += 1
                    elif resultado == "HTTP_ERR":
                        self.http_erro += 1
                    elif resultado == "ERROR":
                        self.erro += 1
                    self.emit("counts", ok=self.ok, http_erro=self.http_erro, erro=self.erro,
                               done=done, total=total)

            self.emit("done", cancelled=self.stop_event.is_set(), ok=self.ok, http_erro=self.http_erro,
                       erro=self.erro, total=total, log_file=str(self.log_file))
        except Exception as e:
            self.emit("fatal_error", text=str(e))
