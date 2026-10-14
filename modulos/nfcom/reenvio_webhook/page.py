"""Tela portada do MEGA QG VIVO NFCom v2.3 (legado/NFCom preview/qg.py)."""
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from core.config import AMBIENTE_HML, AMBIENTE_PRD
from ui.theme import COLORS, escala
from ui.widgets import ScrolledText, _open_folder, back_button, centralizar, stat_box
from modulos.nfcom.comum import *  # noqa: F401,F403 - imports/constantes do QG original
from modulos.nfcom.reenvio_webhook.engine import WebhookResendEngine


class ReenvioWebhookPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLORS["bg"])
        self.controller = controller

        self.event_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread = None

        self.arquivo_var = tk.StringVar()
        self.create_var = tk.StringVar(value="4 - Não criar")
        self.timeout_var = tk.StringVar(value="8")
        self.log_dir_var = tk.StringVar(value=DEFAULT_LOG_DIR)
        self.ambiente_var = controller.ambiente_var  # ambiente global do MegaQG Vivo  # v2.1

        self.count_labels = {}

        back_button(self, controller, "🔔 Reenvio de WebHook", "CREATE opcional + RESEND por subscrição")
        self._build_ui()
        self._poll_queue()

    def _build_ui(self):
        pad = {"padx": 18, "pady": 6}

        cfg = ttk.LabelFrame(self, text="PARÂMETROS")
        cfg.pack(fill="x", **pad)
        body = tk.Frame(cfg, bg=COLORS["panel"])
        body.pack(fill="x", padx=10, pady=10)
        for col in range(4):
            body.grid_columnconfigure(col, weight=1)

        ttk.Label(body, text="Arquivo .txt com os IDs", style="PanelMuted.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w")
        row_arq = tk.Frame(body, bg=COLORS["panel"])
        row_arq.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(2, 10))
        ttk.Entry(row_arq, textvariable=self.arquivo_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row_arq, text="Procurar...", command=self._browse_arquivo).pack(side="left", padx=(6, 0))

        ttk.Label(body, text="Criar WebHooks antes do reenvio?", style="PanelMuted.TLabel").grid(
            row=2, column=0, columnspan=4, sticky="w")
        opcoes = [f"{k} - {v}" for k, v in WebhookResendEngine.OPCOES_CREATE.items()]
        ttk.Combobox(body, textvariable=self.create_var, state="readonly", values=opcoes).grid(
            row=3, column=0, columnspan=4, sticky="ew", pady=(2, 4))

        ttk.Label(body, text=(
            "As subscrições do reenvio são definidas automaticamente pela opção acima "
            "(1→[1,4]  ·  2→[1]  ·  3→[2]  ·  Não criar→[1])."),
            style="PanelMuted.TLabel", font=("Segoe UI", 8, "italic")).grid(
            row=4, column=0, columnspan=4, sticky="w", pady=(0, 10))

        ttk.Label(body, text="Timeout (s)", style="PanelMuted.TLabel").grid(row=5, column=0, sticky="w")
        ttk.Spinbox(body, textvariable=self.timeout_var, from_=1, to=120, width=8).grid(
            row=6, column=0, sticky="w", padx=(0, 8))

        # v2.1: seletor de ambiente (Produção/Homologação).
        ttk.Label(body, text="Ambiente", style="PanelMuted.TLabel").grid(row=5, column=1, sticky="w")
        ttk.Label(body, textvariable=self.ambiente_var, style="Ambiente.TLabel").grid(row=6, column=1, sticky="ew", padx=(0, 8))

        ttk.Label(body, text="Pasta de log", style="PanelMuted.TLabel").grid(
            row=7, column=0, columnspan=4, sticky="w", pady=(10, 0))
        row_log = tk.Frame(body, bg=COLORS["panel"])
        row_log.grid(row=8, column=0, columnspan=4, sticky="ew")
        ttk.Entry(row_log, textvariable=self.log_dir_var, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(row_log, text="Abrir pasta", command=self._open_log_dir).pack(side="left", padx=(6, 0))

        controls = tk.Frame(self, bg=COLORS["bg"])
        controls.pack(fill="x", **pad)
        self.start_btn = ttk.Button(controls, text="🔔  Iniciar Reenvio", style="Warning.TButton",
                                     command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(controls, text="■  Parar", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))

        progress_frame = ttk.LabelFrame(self, text="PROGRESSO")
        progress_frame.pack(fill="x", **pad)
        pbody = tk.Frame(progress_frame, bg=COLORS["panel"])
        pbody.pack(fill="x", padx=10, pady=10)

        self.progress_bar = ttk.Progressbar(pbody, style="Warning.Horizontal.TProgressbar", maximum=100, value=0)
        self.progress_bar.pack(fill="x", side="left", expand=True)
        self.progress_label = ttk.Label(pbody, text="0 / 0", style="Panel.TLabel", width=12, anchor="e")
        self.progress_label.pack(side="left", padx=(8, 0))

        stats_row = tk.Frame(progress_frame, bg=COLORS["panel"])
        stats_row.pack(fill="x", padx=10, pady=(0, 10))
        for key, label, color in [("ok_req", "SUCESSO", COLORS["success"]),
                                    ("ignorado_req", "IGNORADO", COLORS["warning"]),
                                    ("error_req", "ERRO", COLORS["danger"]),
                                    ("ok_events", "EVENTOS REENVIADOS", COLORS["accent"])]:
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

    def _browse_arquivo(self):
        path = filedialog.askopenfilename(title="Selecione o .txt com os IDs",
                                           filetypes=[("Arquivo de texto", "*.txt"), ("Todos", "*.*")])
        if path:
            self.arquivo_var.set(path)

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
        arquivo = self.arquivo_var.get().strip()
        if not arquivo or not os.path.exists(arquivo):
            messagebox.showwarning("Arquivo inválido", "Selecione um .txt válido com os IDs.")
            return

        tipo_create = self.create_var.get().split(" - ")[0].strip()

        # Max workers fixo em 10 (não exposto na tela) -- igual ao
        # MAX_WORKERS do script original.
        max_workers = 10

        try:
            timeout = int(self.timeout_var.get())
        except ValueError:
            messagebox.showerror("Parâmetro inválido", "Timeout deve ser um número inteiro.")
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

        engine = WebhookResendEngine(
            self.event_queue, self.stop_event,
            tipo_create=tipo_create,
            max_workers=max_workers, timeout=timeout, log_dir=self.log_dir_var.get().strip(),
            ambiente=self.ambiente_var.get(),
        )
        self.worker_thread = threading.Thread(target=engine.run, args=(arquivo,), daemon=True)
        self.worker_thread.start()

    def _stop(self):
        self.stop_event.set()
        self.stop_btn["state"] = "disabled"
        self._append_log("Parada solicitada, aguardando requisições em andamento...", "WARN")

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
            self.count_labels["ok_req"]["text"] = str(event["ok_req"])
            self.count_labels["ignorado_req"]["text"] = str(event["ignorado_req"])
            self.count_labels["error_req"]["text"] = str(event["error_req"])
            self.count_labels["ok_events"]["text"] = str(event["ok_events"])
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
            if event["cancelled"]:
                self._append_log("Processo cancelado pelo usuário.", "WARN")
            else:
                self._append_log(
                    f"Finalizado. Sucesso={event['ok_req']} | Ignorado={event['ignorado_req']} | "
                    f"Erro={event['error_req']} | Eventos reenviados={event['ok_events']} | "
                    f"Log: {event.get('log_file', '')}", "INFO")
                messagebox.showinfo("Concluído",
                                     f"Reenvio de WebHook finalizado.\n\n"
                                     f"Sucesso: {event['ok_req']}\nIgnorado: {event['ignorado_req']}\n"
                                     f"Erro: {event['error_req']}\nEventos reenviados: {event['ok_events']}")

    def _append_log(self, text, status):
        tag = status if status in ("OK", "INFO", "WARN", "ERROR") else "INFO"
        self.log_text.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {text}\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
