"""Tela portada do MEGA QG VIVO NFCom v2.3 (legado/NFCom preview/qg.py)."""
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from core.config import AMBIENTE_HML, AMBIENTE_PRD
from ui.theme import COLORS, escala
from ui.widgets import ScrolledText, _open_folder, back_button, centralizar, stat_box
from modulos.nfcom.comum import *  # noqa: F401,F403 - imports/constantes do QG original
from modulos.nfcom.download_xmls.engine import DownloadXmlsEngine


class DownloadXmlsPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLORS["bg"])
        self.controller = controller

        self.event_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread = None

        self.ambiente_var = controller.ambiente_var  # ambiente global do MegaQG Vivo
        self.pasta_saida_var = tk.StringVar()
        self.arquivo_var = tk.StringVar()
        self.arquivo_erro_var = tk.StringVar()
        self.log_dir_var = tk.StringVar(value=DEFAULT_LOG_DIR)

        self.count_labels = {}

        back_button(self, controller, "📥 Download de XMLs", "baixa XMLs de NFCom por lista de IDs")
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

        ttk.Label(body, text="Ambiente", style="PanelMuted.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(body, textvariable=self.ambiente_var, style="Ambiente.TLabel").grid(row=1, column=0, columnspan=2, sticky="ew")

        ttk.Label(body, text="Pasta de saída dos XMLs", style="PanelMuted.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        row_saida = tk.Frame(body, bg=COLORS["panel"])
        row_saida.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        ttk.Entry(row_saida, textvariable=self.pasta_saida_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row_saida, text="Procurar...", command=self._browse_pasta_saida).pack(side="left", padx=(6, 0))

        ttk.Label(body, text="Arquivo .txt com os IDs das notas a baixar", style="PanelMuted.TLabel").grid(
            row=4, column=0, columnspan=2, sticky="w")
        row_arq = tk.Frame(body, bg=COLORS["panel"])
        row_arq.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        ttk.Entry(row_arq, textvariable=self.arquivo_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row_arq, text="Procurar...", command=self._browse_arquivo).pack(side="left", padx=(6, 0))

        ttk.Label(body, text="Arquivo .txt para gravar IDs com erro (opcional)", style="PanelMuted.TLabel").grid(
            row=6, column=0, columnspan=2, sticky="w")
        row_err = tk.Frame(body, bg=COLORS["panel"])
        row_err.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        ttk.Entry(row_err, textvariable=self.arquivo_erro_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row_err, text="Escolher...", command=self._browse_erro).pack(side="left", padx=(6, 0))

        ttk.Label(body, text="Pasta de log", style="PanelMuted.TLabel").grid(
            row=8, column=0, columnspan=2, sticky="w")
        row_log = tk.Frame(body, bg=COLORS["panel"])
        row_log.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        ttk.Entry(row_log, textvariable=self.log_dir_var, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(row_log, text="Abrir pasta", command=self._open_log_dir).pack(side="left", padx=(6, 0))

        controls = tk.Frame(self, bg=COLORS["bg"])
        controls.pack(fill="x", **pad)
        self.start_btn = ttk.Button(controls, text="▶  Iniciar Download", style="Purple.TButton",
                                     command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(controls, text="■  Parar", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))

        progress_frame = ttk.LabelFrame(self, text="PROGRESSO")
        progress_frame.pack(fill="x", **pad)
        pbody = tk.Frame(progress_frame, bg=COLORS["panel"])
        pbody.pack(fill="x", padx=10, pady=10)

        self.progress_bar = ttk.Progressbar(pbody, style="Purple.Horizontal.TProgressbar", maximum=100, value=0)
        self.progress_bar.pack(fill="x", side="left", expand=True)
        self.progress_label = ttk.Label(pbody, text="0 / 0", style="Panel.TLabel", width=12, anchor="e")
        self.progress_label.pack(side="left", padx=(8, 0))

        stats_row = tk.Frame(progress_frame, bg=COLORS["panel"])
        stats_row.pack(fill="x", padx=10, pady=(0, 10))
        for key, label, color in [("ok", "SUCESSO", COLORS["success"]), ("erro", "ERRO", COLORS["danger"])]:
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
        self.log_text.tag_config("ERROR", foreground=COLORS["danger"])

    def _browse_pasta_saida(self):
        path = filedialog.askdirectory(title="Selecione a pasta de saída dos XMLs")
        if path:
            self.pasta_saida_var.set(path)

    def _browse_arquivo(self):
        path = filedialog.askopenfilename(title="Selecione o .txt com os IDs das notas",
                                           filetypes=[("Arquivo de texto", "*.txt"), ("Todos", "*.*")])
        if path:
            self.arquivo_var.set(path)

    def _browse_erro(self):
        path = filedialog.asksaveasfilename(title="Escolha onde gravar os IDs com erro",
                                             defaultextension=".txt",
                                             filetypes=[("Arquivo de texto", "*.txt")])
        if path:
            self.arquivo_erro_var.set(path)

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
        pasta_saida = self.pasta_saida_var.get().strip()
        arquivo = self.arquivo_var.get().strip()
        arquivo_erro = self.arquivo_erro_var.get().strip() or None

        if not arquivo or not os.path.exists(arquivo):
            messagebox.showwarning("Arquivo inválido", "Selecione um .txt válido com os IDs das notas.")
            return
        if not pasta_saida:
            messagebox.showwarning("Pasta de saída não definida", "Escolha a pasta onde os XMLs serão salvos.")
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

        # Threads fixo (não exposto na tela).
        threads = 8

        url_base = DownloadXmlsEngine.URL_PRD if self.ambiente_var.get() == "Produção" else DownloadXmlsEngine.URL_HML

        engine = DownloadXmlsEngine(
            self.event_queue, self.stop_event,
            url_base=url_base, pasta_saida=pasta_saida, arquivo_erro=arquivo_erro, threads=threads,
            log_dir=self.log_dir_var.get().strip()
        )
        self.worker_thread = threading.Thread(target=engine.run, args=(arquivo,), daemon=True)
        self.worker_thread.start()

    def _stop(self):
        self.stop_event.set()
        self.stop_btn["state"] = "disabled"
        self._append_log("Parada solicitada, aguardando downloads em andamento...", "INFO")

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
            self.count_labels["ok"]["text"] = str(event["ok"])
            self.count_labels["erro"]["text"] = str(event["erro"])
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
                self._append_log("Processo cancelado pelo usuário.", "INFO")
            else:
                self._append_log(
                    f"Finalizado. Sucesso={event['ok']} | Erro={event['erro']} | "
                    f"Log: {event.get('log_file', '')}", "INFO")
                messagebox.showinfo("Concluído",
                                     f"Download finalizado.\n\nSucesso: {event['ok']}\nErro: {event['erro']}")

    def _append_log(self, text, status):
        tag = status if status in ("OK", "INFO", "ERROR") else "INFO"
        self.log_text.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {text}\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
