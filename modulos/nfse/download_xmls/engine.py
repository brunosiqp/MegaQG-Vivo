"""Engine portada do MEGA QG VIVO NFSe v2.0 (legado/NFSe/qg.py); só a URL passou a vir do config.json."""
from modulos.nfse.comum import *  # noqa: F401,F403 - imports do QG original


class DownloadXmlsEngine:

    def __init__(self, event_queue, stop_event, *, ambiente=AMBIENTE_PRD, pasta_destino, arquivo_erro, threads, log_dir):
        # MegaQG Vivo: URL vem do config.json (nfse_download_url_prd/_hml), não mais fixa no código
        self.BASE_URL_DOWNLOAD = url_por_ambiente("nfse_download_url", ambiente)
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.pasta_destino = pasta_destino
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
        self.log_file = os.path.join(self.log_dir, "download_xmls_log_nfse.txt")

    def _log_arquivo(self, id_nota, status, extra=""):
        linha = f"{datetime.now().isoformat()} | {id_nota} | {status} | {extra}\n"
        with self.log_lock:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(linha)

    def baixar_xml(self, id_nota):
        try:
            response = requests.get(
                self.BASE_URL_DOWNLOAD,
                params={"ids": id_nota, "formato": "xml"},
                timeout=60
            )
            if response.status_code == 200:
                return True, response.content
            else:
                return False, response.text
        except Exception as e:
            return False, str(e)

    def execute(self, id_nota):
        if self.stop_event.is_set():
            return "CANCELLED"

        ok, resultado = self.baixar_xml(id_nota)
        if ok:
            caminho_xml = os.path.join(self.pasta_destino, f"{id_nota}.xml")
            with open(caminho_xml, "wb") as f:
                f.write(resultado)
            self._log_arquivo(id_nota, "OK", caminho_xml)
            self.emit_log(f"OK    {id_nota}  ->  {caminho_xml}", "OK")
            return "OK"
        else:
            if self.arquivo_erro:
                with self.erro_lock:
                    with open(self.arquivo_erro, "a", encoding="utf-8") as f:
                        f.write(f"{id_nota}\n")
            self._log_arquivo(id_nota, "ERROR", str(resultado))
            self.emit_log(f"ERRO  {id_nota}: {resultado}", "ERROR")
            return "ERROR"

    def run(self, arquivo_ids):
        try:
            self._garantir_log()
            with open(arquivo_ids, encoding="utf-8") as f:
                ids = [l.strip() for l in f if l.strip()]

            total = len(ids)
            self.emit("total_itens", n=total)
            self.emit_log(f"{total} ID(s) carregado(s). Iniciando download...", "INFO")

            os.makedirs(self.pasta_destino, exist_ok=True)
            if self.arquivo_erro:
                open(self.arquivo_erro, "a", encoding="utf-8").close()

            done = 0
            with ThreadPoolExecutor(max_workers=self.threads) as executor:
                futures = {executor.submit(self.execute, id_nota): id_nota for id_nota in ids}
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


class DownloadComSemCepEngine:

    def __init__(self, event_queue, stop_event, *, ambiente=AMBIENTE_PRD, pasta_destino, arquivo_erro, threads, log_dir):
        # MegaQG Vivo: URL vem do config.json (nfse_download_url_prd/_hml), não mais fixa no código
        self.BASE_URL_DOWNLOAD = url_por_ambiente("nfse_download_url", ambiente)
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.pasta_destino = pasta_destino
        self.arquivo_erro = arquivo_erro
        self.threads = max(1, threads)
        self.log_dir = log_dir
        self.log_file = None
        self.erro_lock = threading.Lock()
        self.log_lock = threading.Lock()
        self.ok_com = 0
        self.ok_sem = 0
        self.erro = 0

    def emit(self, kind, **data):
        self.event_queue.put({"kind": kind, **data})

    def emit_log(self, text, status="INFO"):
        self.emit("log_line", text=text, status=status)

    def _garantir_log(self):
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "download_com_sem_cep_log_nfse.txt")

    def _log_arquivo(self, id_nota, status, extra=""):
        linha = f"{datetime.now().isoformat()} | {id_nota} | {status} | {extra}\n"
        with self.log_lock:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(linha)

    def baixar_xml(self, id_nota):
        try:
            response = requests.get(
                self.BASE_URL_DOWNLOAD,
                params={"ids": id_nota, "formato": "xml"},
                timeout=60
            )
            if response.status_code == 200:
                return True, response.content
            else:
                return False, response.text
        except Exception as e:
            return False, str(e)

    @staticmethod
    def endereco_tem_cep(xml_bytes):
        try:
            root = ET.fromstring(xml_bytes)

            def verificar_endereco(path):
                end = root.find(path)
                if end is None:
                    return False

                cep = end.find(".//CEP")
                xLgr = end.find(".//xLgr")
                nro = end.find(".//nro")
                bairro = end.find(".//xBairro")

                if cep is None or cep.text is None:
                    return False
                if cep.text.strip() == "" or cep.text.strip() == "00000000":
                    return False
                if xLgr is None or not xLgr.text:
                    return False
                if nro is None or not nro.text:
                    return False
                if bairro is None or not bairro.text:
                    return False
                return True

            toma_ok = verificar_endereco(".//toma/end")
            dest_ok = verificar_endereco(".//dest/end")
            return toma_ok and dest_ok
        except Exception:
            return False

    def execute(self, id_nota, pasta_com, pasta_sem):
        if self.stop_event.is_set():
            return "CANCELLED"

        ok, resultado = self.baixar_xml(id_nota)
        if ok:
            tem_cep = self.endereco_tem_cep(resultado)
            destino = pasta_com if tem_cep else pasta_sem
            caminho_xml = os.path.join(destino, f"{id_nota}.xml")
            with open(caminho_xml, "wb") as f:
                f.write(resultado)
            self._log_arquivo(id_nota, "OK_COM" if tem_cep else "OK_SEM", caminho_xml)
            self.emit_log(f"OK    {id_nota}  ->  {'COM CEP' if tem_cep else 'SEM CEP'}", "OK")
            return "OK_COM" if tem_cep else "OK_SEM"
        else:
            if self.arquivo_erro:
                with self.erro_lock:
                    with open(self.arquivo_erro, "a", encoding="utf-8") as f:
                        f.write(f"{id_nota}\n")
            self._log_arquivo(id_nota, "ERROR", str(resultado))
            self.emit_log(f"ERRO  {id_nota}: {resultado}", "ERROR")
            return "ERROR"

    def run(self, arquivo_ids):
        try:
            self._garantir_log()
            with open(arquivo_ids, encoding="utf-8") as f:
                ids = [l.strip() for l in f if l.strip()]

            total = len(ids)
            self.emit("total_itens", n=total)
            self.emit_log(f"{total} ID(s) carregado(s). Iniciando download...", "INFO")

            pasta_com = os.path.join(self.pasta_destino, "COM CEP")
            pasta_sem = os.path.join(self.pasta_destino, "SEM CEP")
            os.makedirs(pasta_com, exist_ok=True)
            os.makedirs(pasta_sem, exist_ok=True)
            if self.arquivo_erro:
                open(self.arquivo_erro, "a", encoding="utf-8").close()

            done = 0
            with ThreadPoolExecutor(max_workers=self.threads) as executor:
                futures = {executor.submit(self.execute, id_nota, pasta_com, pasta_sem): id_nota
                           for id_nota in ids}
                for future in as_completed(futures):
                    resultado = future.result()
                    done += 1
                    if resultado == "OK_COM":
                        self.ok_com += 1
                    elif resultado == "OK_SEM":
                        self.ok_sem += 1
                    elif resultado == "ERROR":
                        self.erro += 1
                    self.emit("counts", ok_com=self.ok_com, ok_sem=self.ok_sem, erro=self.erro,
                               done=done, total=total)

            self.emit("done", cancelled=self.stop_event.is_set(), ok_com=self.ok_com,
                       ok_sem=self.ok_sem, erro=self.erro, total=total, log_file=str(self.log_file))
        except Exception as e:
            self.emit("fatal_error", text=str(e))
