"""Tela do Reenvio à SEFAZ: portada do MEGA QG VIVO NFCom v2.3 (legado/NFCom preview/qg.py) e,
desde a v3.3, com os contadores do reenvio por ID dos XMLs sem chave (ver engine.py)."""
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from core.config import AMBIENTE_HML, AMBIENTE_PRD
from ui.theme import COLORS, escala
from ui.widgets import ScrolledText, _open_folder, back_button, centralizar, stat_box
from modulos.nfcom.comum import *  # noqa: F401,F403 - imports/constantes do QG original
from modulos.nfcom.reenvio_sefaz.engine import ReenvioSefazEngine


class ReenvioSefazPage(tk.Frame):
    URL_PRD = _endpoint("reenvio_sefaz_url_prd", "MEGAQG_REENVIO_SEFAZ_URL_PRD")
    URL_HML = _endpoint("reenvio_sefaz_url_hml", "MEGAQG_REENVIO_SEFAZ_URL_HML")

    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLORS["bg"])
        self.controller = controller

        self.event_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread = None

        self.pasta_var = tk.StringVar()
        self.ambiente_var = controller.ambiente_var  # ambiente global do MegaQG Vivo
        self.log_dir_var = tk.StringVar(value=DEFAULT_LOG_DIR)

        self.count_labels = {}

        back_button(self, controller, "🔁 Reenvio à SEFAZ", "reenvio de XMLs de uma pasta local")

        note = tk.Label(self, text=(
            "Este é o antigo ItgrVivo: reenvia notas para a SEFAZ a partir de uma pasta de XMLs, em Produção "
            "ou Homologação. XML sem chNFCom (ou ilegível) não é mais ignorado: o documento é reenviado pelo "
            "ID, que é o nome do arquivo (ex.: 123456.xml), e o código HTTP do retorno aparece no log."),
            bg=COLORS["bg"], fg=COLORS["fg_muted"], font=("Segoe UI", 8, "italic"),
            justify="left", wraplength=980)
        note.pack(fill="x", padx=18, pady=(0, 6))

        self._build_ui()
        self._poll_queue()

    def _build_ui(self):
        pad = {"padx": 18, "pady": 6}

        cfg = ttk.LabelFrame(self, text="PARÂMETROS")
        cfg.pack(fill="x", **pad)
        body = tk.Frame(cfg, bg=COLORS["panel"])
        body.pack(fill="x", padx=10, pady=10)
        for col in range(2):
            body.grid_columnconfigure(col, weight=1)

        ttk.Label(body, text="Pasta com os XMLs", style="PanelMuted.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w")
        row_pasta = tk.Frame(body, bg=COLORS["panel"])
        row_pasta.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        ttk.Entry(row_pasta, textvariable=self.pasta_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row_pasta, text="Procurar...", command=self._browse_pasta).pack(side="left", padx=(6, 0))

        ttk.Label(body, text="Ambiente", style="PanelMuted.TLabel").grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Label(body, textvariable=self.ambiente_var, style="Ambiente.TLabel").grid(row=3, column=0, columnspan=2, sticky="ew")

        ttk.Label(body, text="Pasta de log", style="PanelMuted.TLabel").grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))
        row_log = tk.Frame(body, bg=COLORS["panel"])
        row_log.grid(row=5, column=0, columnspan=2, sticky="ew")
        ttk.Entry(row_log, textvariable=self.log_dir_var, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(row_log, text="Abrir pasta", command=self._open_log_dir).pack(side="left", padx=(6, 0))

        controls = tk.Frame(self, bg=COLORS["bg"])
        controls.pack(fill="x", **pad)
        self.start_btn = ttk.Button(controls, text="▶  Iniciar Reenvio", style="Teal.TButton", command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(controls, text="■  Parar", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))

        progress_frame = ttk.LabelFrame(self, text="PROGRESSO")
        progress_frame.pack(fill="x", **pad)
        pbody = tk.Frame(progress_frame, bg=COLORS["panel"])
        pbody.pack(fill="x", padx=10, pady=10)

        self.progress_bar = ttk.Progressbar(pbody, style="Teal.Horizontal.TProgressbar", maximum=100, value=0)
        self.progress_bar.pack(fill="x", side="left", expand=True)
        self.progress_label = ttk.Label(pbody, text="0 / 0", style="Panel.TLabel", width=12, anchor="e")
        self.progress_label.pack(side="left", padx=(8, 0))

        stats_row = tk.Frame(progress_frame, bg=COLORS["panel"])
        stats_row.pack(fill="x", padx=10, pady=(0, 10))
        for key, label, color in [("ok", "SUCESSO", COLORS["success"]), ("erro", "ERRO", COLORS["danger"]),
                                    ("id_ok", "REENVIADOS POR ID", COLORS["cyan"]),
                                    ("id_erro", "ERRO NO REENVIO POR ID", COLORS["danger"]),
                                    ("ignorados", "IGNORADOS", COLORS["warning"])]:
            box, val = stat_box(stats_row, label, color)
            box.pack(side="left", padx=(0, 10))
            self.count_labels[key] = val

        log_frame = ttk.LabelFrame(self, text="LOG DE EXECUÇÃO")
        log_frame.pack(fill="both", expand=True, **pad)
        self.log_text = ScrolledText(log_frame, height=10, state="disabled",
                                                    font=("Consolas", 9), bg=COLORS["card"],
                                                    fg=COLORS["fg"], insertbackground=COLORS["fg"],
                                                    borderwidth=0, highlightthickness=0)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
        self.log_text.tag_config("OK", foreground=COLORS["success"])
        self.log_text.tag_config("INFO", foreground=COLORS["fg_muted"])
        self.log_text.tag_config("WARN", foreground=COLORS["warning"])
        self.log_text.tag_config("ERROR", foreground=COLORS["danger"])

    def _browse_pasta(self):
        path = filedialog.askdirectory(title="Selecione a pasta com os XMLs")
        if path:
            self.pasta_var.set(path)

    def _browse_log_dir(self):
        path = filedialog.askdirectory(title="Selecione a pasta de log")
        if path:
            self.log_dir_var.set(path)

    def _open_log_dir(self):
        path = self.log_dir_var.get()
        if not os.path.exists(path):
            messagebox.showwarning("Pasta não encontrada", "A pasta de log ainda não existe.")
            return
        _open_folder(path)

    def _start(self):
        pasta = self.pasta_var.get().strip()
        if not pasta or not os.path.isdir(pasta):
            messagebox.showwarning("Pasta inválida", "Selecione uma pasta válida contendo os XMLs.")
            return

        self.stop_event = threading.Event()
        for key in self.count_labels:
            self.count_labels[key]["text"] = "0"
        self.progress_bar["value"] = 0
        self.progress_bar["maximum"] = 100
        self.progress_label["text"] = "0 / 0"
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

        self.start_btn["state"] = "disabled"
        self.stop_btn["state"] = "normal"

        # Threads fixo em 5 (não exposto na tela) -- fiel ao max_workers=5
        # do Itgr.py original.
        threads = 5

        url = self.URL_PRD if self.ambiente_var.get() == "Produção" else self.URL_HML
        # Reenvio por ID dos XMLs sem chave (reenvio_sefaz_id_url_prd/_hml)
        url_reenvio_id = url_por_ambiente("reenvio_sefaz_id_url", self.ambiente_var.get())

        engine = ReenvioSefazEngine(
            self.event_queue, self.stop_event,
            url=url, threads=threads, log_dir=self.log_dir_var.get().strip(),
            url_reenvio_id=url_reenvio_id
        )
        self.worker_thread = threading.Thread(target=engine.run, args=(pasta,), daemon=True)
        self.worker_thread.start()

    def _stop(self):
        self.stop_event.set()
        self.stop_btn["state"] = "disabled"
        self._append_log("Parada solicitada, aguardando requisições em andamento...", "INFO")

    def _poll_queue(self):
        try:
            while True:
                event = self.event_queue.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _handle_event(self, event):
        kind = event["kind"]
        if kind == "total_itens":
            n = event["n"]
            self.progress_bar["maximum"] = max(n, 1)
            self.progress_label["text"] = f"0 / {n}"
        elif kind == "counts":
            for key in ("ok", "erro", "id_ok", "id_erro", "ignorados"):
                self.count_labels[key]["text"] = str(event.get(key, 0))
            total = max(event["total"], 1)
            self.progress_bar["maximum"] = total
            self.progress_bar["value"] = event["done"]
            self.progress_label["text"] = f"{event['done']} / {event['total']}"
        elif kind == "log_line":
            self._append_log(event["text"], event["status"])
        elif kind == "fatal_error":
            self._append_log(f"ERRO FATAL: {event['text']}", "ERROR")
            messagebox.showerror("Erro", event["text"])
            self.start_btn["state"] = "normal"
            self.stop_btn["state"] = "disabled"
        elif kind == "done":
            self.start_btn["state"] = "normal"
            self.stop_btn["state"] = "disabled"
            self.count_labels["ignorados"]["text"] = str(event.get("ignorados", 0))
            if event["cancelled"]:
                self._append_log("Processo cancelado pelo usuário.", "INFO")
            else:
                self._append_log(
                    f"Finalizado. Sucesso={event['ok']} | Erro={event['erro']} | "
                    f"Reenviados por ID={event.get('id_ok', 0)} | Erro no reenvio por ID={event.get('id_erro', 0)} | "
                    f"Ignorados={event.get('ignorados', 0)}", "INFO")
                codigos = event.get("codigos_id") or {}
                retornos = "".join(f"\n    {codigo}: {n}" for codigo, n in sorted(codigos.items()))
                messagebox.showinfo("Concluído",
                                     f"Reenvio finalizado.\n\nSucesso: {event['ok']}\nErro: {event['erro']}\n"
                                     f"Reenviados por ID: {event.get('id_ok', 0)}\n"
                                     f"Erro no reenvio por ID: {event.get('id_erro', 0)}\n"
                                     f"Ignorados: {event.get('ignorados', 0)}"
                                     + (f"\n\nRetornos do reenvio por ID:{retornos}" if retornos else ""))

    def _append_log(self, text, status):
        tag = status if status in ("OK", "INFO", "WARN", "ERROR") else "INFO"
        self.log_text.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {text}\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
