"""
Consulta SEFAZ (NFCom): status de processamento de chaves NFCom em lote.

Base portada do MEGA QG VIVO NFCom v2.3 (legado/NFCom preview/qg.py). Na v3.8 saiu do porte
automático (tools/portar_qgs.py) porque ganhou o reenvio das chaves que voltam HTTP 422:

  Terminada a consulta, as chaves que voltaram 422 têm o ID buscado no banco do NFCom
  (SELECT id FROM documento_fiscal WHERE chave_nf = <chave>, ver modulos.nfcom.banco) e esses
  IDs são reenviados pela API de reenvio (checksefaz_reenvio_url_prd/_hml no config.json, a
  .../Helper/documents/resend), num POST com o corpo raw JSON [id, id, ...], em lotes. O código
  HTTP de cada lote aparece no log; um lote que volta 422 (ou outro erro) fica registrado e o
  reenvio segue normalmente com os próximos.
"""
from modulos.nfcom.comum import *  # noqa: F401,F403 - imports/constantes do QG original
from core.database import sql_conn
from modulos.nfcom.banco import db_config_nfcom

LOTE_REENVIO = 100        # IDs por POST na API de reenvio
BLOCO_CONSULTA_BANCO = 500  # chaves por SELECT (o SQL Server aceita até 2100 parâmetros)


class CheckSefazEngine:
    def __init__(self, event_queue, stop_event, log_dir, ambiente="Produção", conectar=None):
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.log_dir = log_dir
        self.log_lock = threading.Lock()
        self.current_log_file = None
        # v2.1: escolhe a URL de acordo com o ambiente selecionado na tela.
        self.base_url = CHECKSEFAZ_URL_PRD if ambiente == "Produção" else CHECKSEFAZ_URL_HML
        # v3.8: reenvio pelo ID das chaves que voltam HTTP 422
        self.ambiente = ambiente
        self.url_reenvio = url_por_ambiente("checksefaz_reenvio_url", ambiente)
        self.conectar = conectar or (lambda: sql_conn(db_config_nfcom(ambiente)))
        self.chaves_422 = []
        self.lock_422 = threading.Lock()
        # v2.1: timestamp de início de cada grupo, usado para estimar o ETA
        # (tempo restante) com base no throughput real observado até agora
        # -- já incorpora, sozinho, as pausas obrigatórias entre lotes.
        self.group_start_ts = {}

    def emit(self, kind, **data):
        self.event_queue.put({"kind": kind, **data})

    @staticmethod
    def _estimar_eta(start_ts, done, total):
        """Estima segundos restantes com base no throughput observado até
        agora (done/elapsed). Retorna None enquanto não há dado suficiente."""
        import time
        if done <= 0 or total <= 0 or done >= total:
            return None
        elapsed = time.time() - start_ts
        if elapsed <= 0:
            return None
        taxa = done / elapsed  # itens por segundo
        restante = total - done
        return restante / taxa if taxa > 0 else None

    def _gerar_nome_log(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(self.log_dir, f"{BASE_LOG_NAME}_{ts}.txt")

    def garantir_diretorio_log(self):
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir, exist_ok=True)
        default_file = os.path.join(self.log_dir, f"{BASE_LOG_NAME}.txt")
        try:
            with open(default_file, "a", encoding="utf-8"):
                pass
            self.current_log_file = default_file
        except OSError:
            self.current_log_file = self._gerar_nome_log()
            self.emit("log_line", text=f"[LOG] Criado novo arquivo: {self.current_log_file}", status="INFO")

    def log(self, chave, grupo, status, extra=""):
        linha = f"{datetime.now().isoformat()} | {grupo} | {chave} | {status} | {extra}\n"
        with self.log_lock:
            try:
                with open(self.current_log_file, "a", encoding="utf-8") as f:
                    f.write(linha)
            except OSError:
                self.current_log_file = self._gerar_nome_log()
                self.emit("log_line", text=f"[LOG] Alternando para novo arquivo: {self.current_log_file}", status="INFO")
                with open(self.current_log_file, "a", encoding="utf-8") as f:
                    f.write(linha)
        self.emit("log_line", text=f"{grupo} | {chave} | {status}", status=status)
        self.emit("status_count", status=status)

    @staticmethod
    def carregar_chaves(path):
        with open(path, 'r', encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip()]

    @staticmethod
    def separar_grupos(chaves):
        grupos = {"SVRS": [], "MG": [], "MS": [], "MT": []}
        for chave in chaves:
            uf = UF_MAP.get(chave[:2])
            if not uf:
                continue
            if uf in UF_PROPRIAS:
                grupos[uf].append(chave)
            else:
                grupos["SVRS"].append(chave)
        return grupos

    def consultar(self, chave, grupo):
        if self.stop_event.is_set():
            return "CANCELLED"
        attempts = 0
        backoff = [1, 2, 4]
        while attempts < 3:
            if self.stop_event.is_set():
                return "CANCELLED"
            try:
                r = requests.get(self.base_url + chave, timeout=10)
                if r.status_code == 200:
                    self.log(chave, grupo, "OK", r.text)
                    return "OK"
                elif r.status_code >= 500:
                    raise Exception(f"HTTP {r.status_code}")
                else:
                    status = f"HTTP {r.status_code}"
                    self.log(chave, grupo, status, r.text)
                    if r.status_code == 422:  # v3.8: reenviada pelo ID no fim da consulta
                        with self.lock_422:
                            self.chaves_422.append(chave)
                    return status
            except requests.exceptions.Timeout:
                if attempts == 2:
                    self.log(chave, grupo, "FAIL_TIMEOUT", "timeout final")
                    return "FAIL_TIMEOUT"
            except Exception as e:
                if attempts == 2:
                    self.log(chave, grupo, "ERROR_FINAL", str(e))
                    return "ERROR_FINAL"
            self.stop_event.wait(backoff[attempts])
            attempts += 1

    def _wait_interruptible(self, grupo, seconds):
        remaining = seconds
        while remaining > 0 and not self.stop_event.is_set():
            self.emit("wait_tick", grupo=grupo, remaining=remaining)
            time_sleep_1()
            remaining -= 1
        self.emit("wait_tick", grupo=grupo, remaining=0)

    def processar_grupo(self, nome, lista):
        if not lista:
            return
        import time
        self.group_start_ts[nome] = time.time()
        self.emit("group_start", grupo=nome, total=len(lista))
        done = 0
        total = len(lista)

        if nome == "SVRS":
            index = 0
            while index < len(lista):
                if self.stop_event.is_set():
                    break
                lote = lista[index:index + 2]
                with ThreadPoolExecutor(max_workers=2) as executor:
                    futures = [executor.submit(self.consultar, chave, nome) for chave in lote]
                    for f in as_completed(futures):
                        _ = f.result()
                        done += 1
                        eta = self._estimar_eta(self.group_start_ts[nome], done, total)
                        self.emit("progress", grupo=nome, done=done, total=total, eta_seconds=eta)
                index += 2
                if index < len(lista) and not self.stop_event.is_set():
                    self._wait_interruptible(nome, WAIT_SVRS)
        else:
            limite = LIMITS[nome]
            index = 0
            while index < len(lista):
                if self.stop_event.is_set():
                    break
                lote = lista[index:index + limite]
                with ThreadPoolExecutor(max_workers=limite) as executor:
                    futures = [executor.submit(self.consultar, chave, nome) for chave in lote]
                    for f in as_completed(futures):
                        _ = f.result()
                        done += 1
                        eta = self._estimar_eta(self.group_start_ts[nome], done, total)
                        self.emit("progress", grupo=nome, done=done, total=total, eta_seconds=eta)
                index += limite
                if index < len(lista) and not self.stop_event.is_set():
                    self._wait_interruptible(nome, INTERVAL_PROPRIAS)

        self.emit("group_done", grupo=nome, cancelled=self.stop_event.is_set())

    def run(self, path):
        try:
            if not self.base_url:
                self.emit("fatal_error", text=(
                    "Endpoint de Consulta SEFAZ não configurado. Defina checksefaz_url_prd/"
                    "checksefaz_url_hml em config.json ou as variáveis de ambiente "
                    "MEGAQG_CHECKSEFAZ_URL_PRD / MEGAQG_CHECKSEFAZ_URL_HML."))
                return
            self.garantir_diretorio_log()
            if not os.path.exists(path):
                self.emit("fatal_error", text="Arquivo não encontrado.")
                return
            chaves = self.carregar_chaves(path)
            grupos = self.separar_grupos(chaves)
            self.emit("total_keys", n=len(chaves), grupos={k: len(v) for k, v in grupos.items()})

            threads = []
            for nome, lista in grupos.items():
                t = threading.Thread(target=self.processar_grupo, args=(nome, lista), daemon=True)
                t.start()
                threads.append(t)
            for t in threads:
                t.join()

            if self.chaves_422:
                if self.stop_event.is_set():
                    self.emit("log_line", status="INFO", text=(
                        f"[REENVIO] {len(set(self.chaves_422))} chave(s) com HTTP 422 não foram reenviadas: "
                        "a consulta foi interrompida."))
                else:
                    self.reenviar_422()

            self.emit("all_done", cancelled=self.stop_event.is_set())
        except Exception as e:
            self.emit("fatal_error", text=str(e))

    # ------------------------------------------------------------------ v3.8
    def buscar_ids(self, chaves):
        """{chave: [id, ...]} pela documento_fiscal (chave_nf = chave), em blocos de chaves."""
        ids = {}
        conn = self.conectar()
        try:
            cursor = conn.cursor()
            for i in range(0, len(chaves), BLOCO_CONSULTA_BANCO):
                bloco = chaves[i:i + BLOCO_CONSULTA_BANCO]
                marcas = ",".join("?" * len(bloco))
                cursor.execute(f"SELECT id, chave_nf FROM documento_fiscal WHERE chave_nf IN ({marcas})", bloco)
                for id_doc, chave in cursor.fetchall():
                    ids.setdefault(str(chave).strip(), []).append(int(id_doc))
        finally:
            conn.close()
        return ids

    def _log_reenvio(self, chave, status, texto_tela, detalhe=""):
        """Linha do reenvio no arquivo de log e na tela; status: REENVIO_OK (2xx), REENVIO_HTTP
        (outro código, ex.: 422) ou REENVIO_FALHA (sem ID no banco ou sem resposta)."""
        linha = f"{datetime.now().isoformat()} | REENVIO | {chave} | {status} | {detalhe}\n"
        with self.log_lock:
            try:
                with open(self.current_log_file, "a", encoding="utf-8") as f:
                    f.write(linha)
            except OSError:
                pass
        self.emit("log_line", text=texto_tela, status=status)
        self.emit("status_count", status=status)

    def reenviar_422(self):
        """Reenvia pelo ID as chaves que voltaram HTTP 422 na consulta: busca os IDs no banco e
        manda um POST por lote com o corpo raw JSON [id, id, ...]. Lote que volta 422 (ou outro
        erro) fica no log e o reenvio continua com os próximos."""
        chaves = list(dict.fromkeys(self.chaves_422))
        self.emit("log_line", status="INFO", text=(
            f"[REENVIO] {len(chaves)} chave(s) voltaram HTTP 422: buscando o ID de cada uma no banco..."))
        if not self.url_reenvio:
            self.emit("log_line", status="ERROR_FINAL", text=(
                "[REENVIO] API de reenvio não configurada: defina checksefaz_reenvio_url_prd/"
                "checksefaz_reenvio_url_hml em config.json. As chaves com 422 não foram reenviadas."))
            return
        try:
            ids_por_chave = self.buscar_ids(chaves)
        except Exception as e:
            self.emit("log_line", status="ERROR_FINAL",
                      text=f"[REENVIO] Não foi possível buscar os IDs no banco: {e}")
            return
        for chave in chaves:
            if chave not in ids_por_chave:
                self._log_reenvio(chave, "REENVIO_FALHA", f"REENVIO | {chave} | sem ID: chave não está na documento_fiscal",
                                  "chave não encontrada na documento_fiscal")
        pares = [(chave, id_doc) for chave in chaves for id_doc in dict.fromkeys(ids_por_chave.get(chave, []))]
        if not pares:
            return
        lotes = [pares[i:i + LOTE_REENVIO] for i in range(0, len(pares), LOTE_REENVIO)]
        self.emit("log_line", status="INFO", text=(
            f"[REENVIO] {len(pares)} ID(s) encontrados; reenviando em {len(lotes)} lote(s) de até {LOTE_REENVIO}."))
        for numero, lote in enumerate(lotes, 1):
            if self.stop_event.is_set():
                self.emit("log_line", status="INFO", text="[REENVIO] Interrompido: os lotes restantes não foram enviados.")
                break
            ids = [id_doc for _chave, id_doc in lote]
            try:
                r = requests.post(self.url_reenvio, json=ids, timeout=120)
                codigo, resposta = r.status_code, " ".join((r.text or "").split())[:300]
            except Exception as e:
                codigo, resposta = None, str(e)
            if codigo is None:
                status, rotulo = "REENVIO_FALHA", "sem resposta"
            else:
                status, rotulo = ("REENVIO_OK" if 200 <= codigo < 300 else "REENVIO_HTTP"), f"HTTP {codigo}"
            detalhe = f"  resposta: {resposta}" if resposta and status != "REENVIO_OK" else ""
            self.emit("log_line", status=status,
                      text=f"[REENVIO] lote {numero}/{len(lotes)} ({len(ids)} IDs): {rotulo}{detalhe}")
            for chave, id_doc in lote:
                self._log_reenvio(chave, status, f"REENVIO | {chave} | ID {id_doc} | {rotulo}",
                                  f"id={id_doc} {rotulo} {resposta}")
