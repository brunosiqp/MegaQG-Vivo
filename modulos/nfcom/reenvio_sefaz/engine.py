"""
Reenvio à SEFAZ (NFCom): envia os XMLs de uma pasta local.

Base portada do MEGA QG VIVO NFCom v2.3 (legado/NFCom preview/qg.py). Na v3.3 saiu do porte
automático (tools/portar_qgs.py) porque ganhou o reenvio por ID:

  XML do qual não dá para extrair a chave (sem <chNFCom>, malformado ou ilegível) não é mais
  ignorado. O nome do arquivo é o ID do documento no banco (ex.: 123456.xml), e esse ID é
  reenviado pela API de reenvio por ID (reenvio_sefaz_id_url_prd/_hml no config.json), com o
  corpo JSON [ID]. O código HTTP de cada reenvio aparece no log de execução.

Só continua ignorado o arquivo cujo nome não é um ID numérico, ou quando a URL de reenvio
por ID não está configurada.
"""
from modulos.nfcom.comum import *  # noqa: F401,F403 - imports/constantes do QG original


def id_do_arquivo(file):
    """ID do documento no banco a partir do nome do arquivo (123456.xml -> 123456).
    Vale só o nome formado apenas por dígitos; qualquer outro devolve None."""
    nome = os.path.splitext(os.path.basename(file))[0].strip()
    return int(nome) if nome.isascii() and nome.isdigit() else None


class ReenvioSefazEngine:
    def __init__(self, event_queue, stop_event, *, url, threads, log_dir, url_reenvio_id=""):
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.url = url
        self.url_reenvio_id = url_reenvio_id
        self.threads = max(1, threads)
        self.log_dir = log_dir
        self.log_lock = threading.Lock()
        self.log_file = None
        self.ok = 0
        self.erro = 0
        self.ignorados = 0
        self.id_ok = 0
        self.id_erro = 0
        self.codigos_id = {}  # "HTTP 200" / "HTTP 422" / "sem resposta" -> quantidade

    def emit(self, kind, **data):
        self.event_queue.put({"kind": kind, **data})

    def emit_log(self, text, status="INFO"):
        self.emit("log_line", text=text, status=status)

    def _emit_counts(self, done, total):
        self.emit("counts", ok=self.ok, erro=self.erro, id_ok=self.id_ok, id_erro=self.id_erro,
                  ignorados=self.ignorados, done=done, total=total)

    def _garantir_log(self):
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "integracao_sefaz_log.txt")

    def _log_arquivo(self, uf, chave, status, extra):
        linha = f"{datetime.now().isoformat()} | {uf} | {chave} | {status} | {extra}\n"
        with self.log_lock:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(linha)

    @staticmethod
    def get_xml_info(xml_str):
        try:
            root = ET.fromstring(xml_str)
            ch = root.find(".//ns:chNFCom", NFCOM_NS)
            if ch is None:
                return None, None
            chave = ch.text.strip()
            uf = UF_MAP.get(chave[:2], "??")
            return uf, chave
        except Exception:
            return None, None

    def api_post(self, xml_str):
        return requests.post(self.url, data=xml_str.encode("utf-8"),
                              headers={"Content-Type": "application/xml"}, timeout=60)

    def api_post_id(self, id_doc):
        # Corpo raw em JSON com o ID do documento: [123456]
        return requests.post(self.url_reenvio_id, json=[id_doc], timeout=60)

    def enviar(self, file, xml_str, uf, chave):
        if self.stop_event.is_set():
            return "CANCELLED"
        try:
            r = self.api_post(xml_str)
            if r is not None and str(r.status_code)[0] == "2":
                self._log_arquivo(uf, chave, "OK", r.text[:300])
                self.emit_log(f"OK    {file}  [{uf}] {chave}  HTTP {r.status_code}", "OK")
                return "OK"
            else:
                status = f"HTTP {r.status_code}" if r is not None else "FAIL_REQUEST"
                self._log_arquivo(uf, chave, status, r.text[:300] if r is not None else "")
                self.emit_log(f"ERRO  {file}  [{uf}] {chave}  {status}", "ERROR")
                return "ERROR"
        except Exception as e:
            self._log_arquivo(uf, chave, "ERROR_FINAL", str(e))
            self.emit_log(f"EXCEÇÃO {file}: {e}", "ERROR")
            return "ERROR"

    def reenviar_por_id(self, file, id_doc, motivo):
        """Reenvia pelo ID o documento cujo XML seria ignorado e mostra o código HTTP no log:
        2xx em verde, 4xx (ex.: 422) em amarelo, 5xx ou sem resposta em vermelho."""
        if self.stop_event.is_set():
            return "CANCELLED"
        try:
            r = self.api_post_id(id_doc)
        except Exception as e:
            self._contar_codigo("sem resposta")
            self._log_arquivo("ID", id_doc, "REENVIO_ID SEM_RESPOSTA", str(e))
            self.emit_log(f"POR ID  SEM RESPOSTA  {file}  (ID {id_doc}, {motivo}): {e}", "ERROR")
            return "ID_ERROR"
        codigo = r.status_code
        resposta = " ".join((r.text or "").split())[:200]
        self._contar_codigo(f"HTTP {codigo}")
        self._log_arquivo("ID", id_doc, f"REENVIO_ID HTTP {codigo}", resposta)
        if 200 <= codigo < 300:
            self.emit_log(f"POR ID  HTTP {codigo}  {file}  (ID {id_doc}, {motivo})", "OK")
            return "ID_OK"
        detalhe = f"  resposta: {resposta}" if resposta else ""
        self.emit_log(f"POR ID  HTTP {codigo}  {file}  (ID {id_doc}, {motivo}){detalhe}",
                      "WARN" if codigo < 500 else "ERROR")
        return "ID_ERROR"

    def _contar_codigo(self, codigo):
        with self.log_lock:
            self.codigos_id[codigo] = self.codigos_id.get(codigo, 0) + 1

    def _sem_chave(self, file, motivo, por_id):
        """XML que antes era só ignorado: vai para o reenvio por ID quando o nome do arquivo é
        um ID e a URL está configurada; senão continua ignorado, agora com o motivo no log."""
        id_doc = id_do_arquivo(file)
        if id_doc is not None and self.url_reenvio_id:
            por_id.append((file, id_doc, motivo))
            return
        self.ignorados += 1
        if id_doc is None:
            texto = f"IGNORADO  {file}: {motivo} e o nome do arquivo não é um ID numérico"
        else:
            texto = f"IGNORADO  {file}: {motivo} e o reenvio por ID não está configurado"
        self._log_arquivo("--", file, "IGNORADO", motivo)
        self.emit_log(texto, "WARN")

    def run(self, pasta):
        try:
            if not self.url:
                self.emit("fatal_error", text=(
                    "Endpoint de Reenvio à SEFAZ não configurado. Defina reenvio_sefaz_url_prd/"
                    "reenvio_sefaz_url_hml em config.json ou as variáveis de ambiente "
                    "MEGAQG_REENVIO_SEFAZ_URL_PRD / MEGAQG_REENVIO_SEFAZ_URL_HML."))
                return
            self._garantir_log()
            arquivos = [f for f in os.listdir(pasta) if f.lower().endswith(".xml")]
            contents = []
            por_id = []  # (arquivo, ID, motivo) dos XMLs sem chave
            for file in arquivos:
                dir_xml = os.path.join(pasta, file)
                try:
                    with open(dir_xml, "r", encoding="utf-8") as e:
                        xml_str = e.read()
                    uf, chave = self.get_xml_info(xml_str)
                    if not chave:
                        self._sem_chave(file, "sem chNFCom", por_id)
                        continue
                    contents.append((file, xml_str, uf, chave))
                except Exception as err:
                    self._sem_chave(file, f"erro ao ler ({type(err).__name__})", por_id)

            total = len(contents) + len(por_id)
            self.emit("total_itens", n=total)
            self.emit_log(f"{len(contents)} XML(s) válido(s) carregado(s) de {len(arquivos)} encontrados.", "INFO")
            if por_id:
                self.emit_log(f"{len(por_id)} XML(s) sem chave: em vez de ignorados, serão reenviados por ID "
                              f"(o ID é o nome do arquivo).", "INFO")
            if self.ignorados and not self.url_reenvio_id:
                self.emit_log("Reenvio por ID não configurado: defina reenvio_sefaz_id_url_prd/"
                              "reenvio_sefaz_id_url_hml em config.json para reenviar os XMLs sem chave.", "WARN")
            self._emit_counts(0, total)

            done = 0
            with ThreadPoolExecutor(max_workers=self.threads) as executor:
                futures = {executor.submit(self.enviar, file, xml_str, uf, chave): file
                           for file, xml_str, uf, chave in contents}
                futures.update({executor.submit(self.reenviar_por_id, file, id_doc, motivo): file
                                for file, id_doc, motivo in por_id})
                for future in as_completed(futures):
                    resultado = future.result()
                    done += 1
                    if resultado == "OK":
                        self.ok += 1
                    elif resultado == "ERROR":
                        self.erro += 1
                    elif resultado == "ID_OK":
                        self.id_ok += 1
                    elif resultado == "ID_ERROR":
                        self.id_erro += 1
                    self._emit_counts(done, total)

            if self.codigos_id:
                resumo = " | ".join(f"{codigo}: {n}" for codigo, n in sorted(self.codigos_id.items()))
                self.emit_log(f"Reenvio por ID, retornos: {resumo}", "INFO")
            self.emit("done", cancelled=self.stop_event.is_set(), ok=self.ok, erro=self.erro,
                       total=total, ignorados=self.ignorados, id_ok=self.id_ok, id_erro=self.id_erro,
                       codigos_id=dict(self.codigos_id))
        except Exception as e:
            self.emit("fatal_error", text=str(e))
