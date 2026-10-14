"""Engine portada sem alteração de lógica do MEGA QG VIVO NFCom v2.3 (legado/NFCom preview/qg.py)."""
from modulos.nfcom.comum import *  # noqa: F401,F403 - imports/constantes do QG original


class WebhookResendEngine:
    BASE_URL_CREATE_PRD = _endpoint("webhook_create_url_prd", "MEGAQG_WEBHOOK_CREATE_URL_PRD")
    BASE_URL_RESEND_PRD = _endpoint("webhook_resend_url_prd", "MEGAQG_WEBHOOK_RESEND_URL_PRD")
    # v2.1: Homologação adicionada -- TODO CONFIRMAR host de HML com o time
    # de infra (segue o mesmo padrão de host do Reenvio à SEFAZ em HML; não
    # há garantia de que web-hooks exista nesse mesmo host).
    BASE_URL_CREATE_HML = _endpoint("webhook_create_url_hml", "MEGAQG_WEBHOOK_CREATE_URL_HML")
    BASE_URL_RESEND_HML = _endpoint("webhook_resend_url_hml", "MEGAQG_WEBHOOK_RESEND_URL_HML")

    OPCOES_CREATE = {
        "1": "Validada em contingência / Autorizada e Rejeitada em contingência",
        "2": "Autorizada / Rejeitada em modo normal",
        "3": "Eventos fiscais",
        "4": "Não criar",
    }

    # Mesma regra de subscrição do CREATE original; para "4 - Não criar" o
    # script pedia reenvio apenas da subscrição 1.
    SUBS_POR_TIPO = {
        "1": [1, 4],
        "2": [1],
        "3": [2],
        "4": [1],
    }

    def __init__(self, event_queue, stop_event, *, tipo_create, max_workers, timeout, log_dir,
                 ambiente="Produção"):
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.tipo_create = tipo_create
        self.max_workers = max(1, max_workers)
        self.timeout = timeout
        self.log_dir = log_dir
        self.log_file = None
        self.log_lock = threading.Lock()

        # v2.1: escolhe as URLs de acordo com o ambiente selecionado.
        if ambiente == "Produção":
            self.base_url_create = self.BASE_URL_CREATE_PRD
            self.base_url_resend = self.BASE_URL_RESEND_PRD
        else:
            self.base_url_create = self.BASE_URL_CREATE_HML
            self.base_url_resend = self.BASE_URL_RESEND_HML

        self.ok_req = 0
        self.error_req = 0
        self.ignorado_req = 0
        self.ok_events = 0

    def emit(self, kind, **data):
        self.event_queue.put({"kind": kind, **data})

    def emit_log(self, text, status="INFO"):
        self.emit("log_line", text=text, status=status)

    def _preparar_log(self):
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "reenvio_webhook_log.txt")

    def _log_arquivo(self, id_doc, msg, response=None):
        ts = datetime.now().isoformat()
        with self.log_lock:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] ID: {id_doc} | {msg}\n")
                if response:
                    f.write(f"RESPONSE: {response}\n")
                f.write("\n")

    @staticmethod
    def carregar_ids(path):
        with open(path, "r", encoding="utf-8") as f:
            return [x.strip() for x in f if x.strip()]

    @staticmethod
    def criar_session():
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=50, pool_maxsize=50)
        session.mount("http://", adapter)
        return session

    def executar_create(self, session, ids):
        tipo = self.tipo_create
        if tipo == "4":
            self.emit_log("CREATE pulado (opção 4 - Não criar).", "INFO")
            return

        subs_alvo = self.SUBS_POR_TIPO.get(tipo)
        if not subs_alvo:
            self.emit_log("Opção de CREATE inválida - etapa pulada.", "WARN")
            return

        ids_join = ",".join(ids)
        self.emit_log(f"Executando CREATE nas subscrições: {subs_alvo}", "INFO")

        for sub in subs_alvo:
            if self.stop_event.is_set():
                return
            try:
                url = self.base_url_create.format(sub=sub)
                r = session.post(url, params={"id-cte-xml[in]": ids_join}, timeout=self.timeout)
                self._log_arquivo("BATCH", f"CREATE SUB {sub} | HTTP {r.status_code}", r.text)
                self.emit_log(f"CREATE sub {sub}: HTTP {r.status_code}",
                              "OK" if r.status_code == 200 else "WARN")
            except Exception as e:
                self._log_arquivo("BATCH", f"CREATE EXCEPTION | SUB {sub} | {e}")
                self.emit_log(f"CREATE sub {sub}: exceção - {e}", "ERROR")

    def request_resend(self, session, id_doc, sub):
        if self.stop_event.is_set():
            return "CANCELLED", 0
        url = self.base_url_resend.format(sub=sub)
        try:
            r = session.post(url, params={"id-doc-fiscal": id_doc}, timeout=self.timeout)
            response_text = r.text

            if r.status_code != 200:
                self._log_arquivo(id_doc, f"RESEND ERRO HTTP {r.status_code} | SUB {sub}", response_text)
                return "erro", 0

            data = r.json()
            qtd = data.get("dados", {}).get("quantidadeEventosReenviados", 0)

            if qtd > 0:
                self._log_arquivo(id_doc, f"RESEND SUCESSO | SUB {sub} | EVENTOS {qtd}", response_text)
                return "ok", qtd
            else:
                self._log_arquivo(id_doc, f"RESEND IGNORADO | SUB {sub} | EVENTOS 0", response_text)
                return "ignorado", 0
        except Exception as e:
            self._log_arquivo(id_doc, f"RESEND EXCEPTION | SUB {sub} | {e}")
            return "erro", 0

    def run(self, arquivo_ids):
        try:
            if not self.base_url_create or not self.base_url_resend:
                self.emit("fatal_error", text=(
                    "Endpoint de Reenvio de WebHook não configurado. Defina "
                    "webhook_create_url_prd/_hml e webhook_resend_url_prd/_hml em config.json "
                    "ou as variáveis de ambiente MEGAQG_WEBHOOK_CREATE_URL_PRD / _HML e "
                    "MEGAQG_WEBHOOK_RESEND_URL_PRD / _HML."))
                return
            self._preparar_log()
            ids = self.carregar_ids(arquivo_ids)
            if not ids:
                self.emit("fatal_error", text="Nenhum ID encontrado no arquivo.")
                return

            session = self.criar_session()
            self.executar_create(session, ids)

            if self.stop_event.is_set():
                self.emit("done", cancelled=True, ok_req=self.ok_req, error_req=self.error_req,
                           ignorado_req=self.ignorado_req, ok_events=self.ok_events, total=0,
                           log_file=str(self.log_file))
                return

            subs_resend = self.SUBS_POR_TIPO.get(self.tipo_create, [1])
            total = len(ids) * len(subs_resend)
            self.emit("total_itens", n=total)
            self.emit_log(
                f"Iniciando RESEND na(s) subscrição(ões) {subs_resend}... {len(ids)} ID(s) "
                f"= {total} requisições", "INFO")

            done = 0
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = [
                    executor.submit(self.request_resend, session, id_doc, sub)
                    for id_doc in ids
                    for sub in subs_resend
                ]
                for future in as_completed(futures):
                    status, qtd = future.result()
                    done += 1
                    if status == "ok":
                        self.ok_req += 1
                        self.ok_events += qtd
                    elif status == "erro":
                        self.error_req += 1
                    elif status == "ignorado":
                        self.ignorado_req += 1
                    self.emit("counts", ok_req=self.ok_req, error_req=self.error_req,
                               ignorado_req=self.ignorado_req, ok_events=self.ok_events,
                               done=done, total=total)

            self.emit("done", cancelled=self.stop_event.is_set(), ok_req=self.ok_req,
                       error_req=self.error_req, ignorado_req=self.ignorado_req,
                       ok_events=self.ok_events, total=total, log_file=str(self.log_file))
        except Exception as e:
            self.emit("fatal_error", text=str(e))
