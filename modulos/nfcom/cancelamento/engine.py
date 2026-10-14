"""Engine portada sem alteração de lógica do MEGA QG VIVO NFCom v2.3 (legado/NFCom preview/qg.py)."""
from modulos.nfcom.comum import *  # noqa: F401,F403 - imports/constantes do QG original


class CancelamentoMassivoEngine:
    """
    Transcrição do CancelamentoMassivoNFCom_v2.2.0.py. Mesma URL, mesmo
    payload (JSON com xmlNFcom em base64), mesma validação de chave (44
    dígitos numéricos) e mesmo formato de log em arquivo. Única diferença:
    o envio roda em um ThreadPoolExecutor (o script original processava
    sequencialmente) para acompanhar o padrão de desempenho do restante
    do QG -- ajuste "Threads" para 1 se quiser o comportamento 100% serial
    original.
    """

    def __init__(self, event_queue, stop_event, *, url, tp_amb, justificativa, log_dir, threads):
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.url = url
        self.tp_amb = tp_amb
        self.justificativa = justificativa
        self.log_dir = log_dir
        self.threads = max(1, threads)
        self.log_lock = threading.Lock()
        self.log_file = None
        self.ok = 0
        self.erro = 0

    def emit(self, kind, **data):
        self.event_queue.put({"kind": kind, **data})

    def emit_log(self, text, status="INFO"):
        self.emit("log_line", text=text, status=status)

    def _garantir_log(self):
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "cancelnfcom_log.txt")

    def _log_arquivo(self, msg):
        with self.log_lock:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(msg + "\n")

    def gerar_xml(self, chave):
        cnpj = chave[6:20]
        return (
            "<eventoNFCom>\n"
            "    <infEvento>\n"
            f"        <tpAmb>{self.tp_amb}</tpAmb>\n"
            f"        <CNPJ>{cnpj}</CNPJ>\n"
            f"        <chNFCom>{chave}</chNFCom>\n"
            f"        <cOrgao>{chave[:2]}</cOrgao>\n"
            "        <tpEvento>110111</tpEvento>\n"
            f"        <detEvento><evCancNFCom><xJust>{self.justificativa}</xJust></evCancNFCom></detEvento>\n"
            "    </infEvento>\n"
            "</eventoNFCom>"
        )

    def cancelar(self, chave):
        if self.stop_event.is_set():
            return "CANCELLED"

        if len(chave) != 44 or not chave.isdigit():
            self.emit_log(f"Chave inválida (ignorada): {chave}", "WARN")
            return "INVALID"

        xml64 = base64.b64encode(self.gerar_xml(chave).encode()).decode()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            r = requests.post(
                self.url,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                json={"xmlNFcom": xml64},
                timeout=60
            )
            self._log_arquivo(f"{ts} | {chave} | Status: {r.status_code} | {r.text}")
            if r.ok:
                self.emit_log(f"OK    {chave}   (HTTP {r.status_code})", "OK")
                return "OK"
            else:
                self.emit_log(f"ERRO  {chave}   (HTTP {r.status_code})", "ERROR")
                return "ERROR"
        except Exception as e:
            self._log_arquivo(f"{ts} | {chave} | EXCEPTION | {e}")
            self.emit_log(f"EXCEÇÃO {chave}: {e}", "ERROR")
            return "ERROR"

    def run(self, arquivo_chaves):
        try:
            if not self.url:
                self.emit("fatal_error", text=(
                    "Endpoint de Cancelamento não configurado. Defina cancelamento_url_prd/"
                    "cancelamento_url_hml em config.json ou as variáveis de ambiente "
                    "MEGAQG_CANCELAMENTO_URL_PRD / MEGAQG_CANCELAMENTO_URL_HML."))
                return
            self._garantir_log()
            with open(arquivo_chaves, encoding="utf-8") as f:
                chaves = [l.strip() for l in f if l.strip()]

            total = len(chaves)
            self.emit("total_itens", n=total)
            self.emit_log(f"{total} chave(s) carregada(s). Iniciando processamento...", "INFO")

            done = 0
            with ThreadPoolExecutor(max_workers=self.threads) as executor:
                futures = {executor.submit(self.cancelar, chave): chave for chave in chaves}
                for future in as_completed(futures):
                    resultado = future.result()
                    done += 1
                    if resultado == "OK":
                        self.ok += 1
                    elif resultado in ("ERROR", "INVALID"):
                        self.erro += 1
                    self.emit("counts", ok=self.ok, erro=self.erro, done=done, total=total)

            self.emit("done", cancelled=self.stop_event.is_set(), ok=self.ok, erro=self.erro,
                       total=total, log_file=str(self.log_file))
        except Exception as e:
            self.emit("fatal_error", text=str(e))
