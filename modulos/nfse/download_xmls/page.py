"""Tela portada do MEGA QG VIVO NFSe v2.0 (legado/NFSe/qg.py)."""
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from core.config import AMBIENTE_HML, AMBIENTE_PRD
from ui.theme import COLORS, escala
from ui.widgets import ScrolledText, _open_folder, back_button, centralizar, stat_box
from modulos.nfse.comum import *  # noqa: F401,F403 - imports do QG original
from modulos.nfse.download_xmls.engine import DownloadXmlsEngine, DownloadComSemCepEngine


class DownloadXmlsPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLORS["bg"])
        self.controller = controller

        self.event_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread = None

        self.modo_var = tk.StringVar(value="lote")
        self.arquivo_var = tk.StringVar()
        self.pasta_var = tk.StringVar()
        self.arquivo_erro_var = tk.StringVar()
        self.log_dir_var = tk.StringVar(value=DEFAULT_LOG_DIR)

        self.count_labels = {}

        back_button(self, controller, "📥 Download de XMLs",
                    "download em lote, com separação opcional por CEP")
        self._build_ui()
        self._poll_queue()

    def _build_ui(self):
        pad = {"padx": 18, "pady": 6}

        modo_frame = ttk.LabelFrame(self, text="MÉTODO DE DOWNLOAD")
        modo_frame.pack(fill="x", **pad)
        modo_body = tk.Frame(modo_frame, bg=COLORS["panel"])
        modo_body.pack(fill="x", padx=10, pady=10)

        self.radio_lote = ttk.Radiobutton(
            modo_body, text="Lote simples — baixa todos os XMLs direto na pasta de destino",
            variable=self.modo_var, value="lote", command=self._on_modo_change)
        self.radio_lote.pack(anchor="w")

        self.radio_cep = ttk.Radiobutton(
            modo_body, text="Separar por endereço — cria as subpastas COM CEP / SEM CEP automaticamente",
            variable=self.modo_var, value="cep", command=self._on_modo_change)
        self.radio_cep.pack(anchor="w", pady=(4, 0))

        cfg = ttk.LabelFrame(self, text="PARÂMETROS")
        cfg.pack(fill="x", **pad)
        body = tk.Frame(cfg, bg=COLORS["panel"])
        body.pack(fill="x", padx=10, pady=10)
        for col in range(2):
            body.grid_columnconfigure(col, weight=1)

        ttk.Label(body, text="Arquivo .txt com os IDs das notas", style="PanelMuted.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w")
        row_arq = tk.Frame(body, bg=COLORS["panel"])
        row_arq.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        ttk.Entry(row_arq, textvariable=self.arquivo_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row_arq, text="Procurar...", command=self._browse_arquivo).pack(side="left", padx=(6, 0))

        self.pasta_label = ttk.Label(body, text="Pasta onde salvar os XMLs", style="PanelMuted.TLabel")
        self.pasta_label.grid(row=2, column=0, columnspan=2, sticky="w")
        row_pasta = tk.Frame(body, bg=COLORS["panel"])
        row_pasta.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        ttk.Entry(row_pasta, textvariable=self.pasta_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row_pasta, text="Procurar...", command=self._browse_pasta).pack(side="left", padx=(6, 0))

        ttk.Label(body, text="Arquivo .txt para gravar IDs com erro (opcional)", style="PanelMuted.TLabel").grid(
            row=4, column=0, columnspan=2, sticky="w")
        row_err = tk.Frame(body, bg=COLORS["panel"])
        row_err.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        ttk.Entry(row_err, textvariable=self.arquivo_erro_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row_err, text="Escolher...", command=self._browse_erro).pack(side="left", padx=(6, 0))

        ttk.Label(body, text="Pasta de log", style="PanelMuted.TLabel").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(10, 0))
        row_log = tk.Frame(body, bg=COLORS["panel"])
        row_log.grid(row=7, column=0, columnspan=2, sticky="ew")
        ttk.Entry(row_log, textvariable=self.log_dir_var, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(row_log, text="Abrir pasta", command=self._open_log_dir).pack(side="left", padx=(6, 0))

        controls = tk.Frame(self, bg=COLORS["bg"])
        controls.pack(fill="x", **pad)
        self.start_btn = ttk.Button(controls, text="▶  Iniciar Download", style="Cyan.TButton",
                                     command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(controls, text="■  Parar", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))

        progress_frame = ttk.LabelFrame(self, text="PROGRESSO")
        progress_frame.pack(fill="x", **pad)
        pbody = tk.Frame(progress_frame, bg=COLORS["panel"])
        pbody.pack(fill="x", padx=10, pady=10)

        self.progress_bar = ttk.Progressbar(pbody, maximum=100, value=0, style="Cyan.Horizontal.TProgressbar")
        self.progress_bar.pack(fill="x", side="left", expand=True)
        self.progress_label = ttk.Label(pbody, text="0 / 0", style="Panel.TLabel", width=12, anchor="e")
        self.progress_label.pack(side="left", padx=(8, 0))

        self.stats_row = tk.Frame(progress_frame, bg=COLORS["panel"])
        self.stats_row.pack(fill="x", padx=10, pady=(0, 10))
        self._build_stats_lote()

        log_frame = ttk.LabelFrame(self, text="LOG DE EXECUÇÃO")
        log_frame.pack(fill="both", expand=True, **pad)
        self.log_text = ScrolledText(log_frame, height=10, state="disabled",
                                                    font=("Consolas", 9), bg=COLORS["card"],
                                                    fg=COLORS["fg"], insertbackground=COLORS["fg"],
                                                    borderwidth=0, highlightthickness=0)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
        self.log_text.tag_config("OK", foreground=COLORS["cyan"])
        self.log_text.tag_config("INFO", foreground=COLORS["fg_muted"])
        self.log_text.tag_config("ERROR", foreground=COLORS["danger"])

    def _clear_stats_row(self):
        for w in self.stats_row.winfo_children():
            w.destroy()
        self.count_labels = {}

    def _build_stats_lote(self):
        self._clear_stats_row()
        for key, label, color in [("ok", "SUCESSO", COLORS["cyan"]), ("erro", "ERRO", COLORS["danger"])]:
            box, val = stat_box(self.stats_row, label, color)
            box.pack(side="left", padx=(0, 10))
            self.count_labels[key] = val

    def _build_stats_cep(self):
        self._clear_stats_row()
        for key, label, color in [("ok_com", "COM CEP", COLORS["purple"]),
                                    ("ok_sem", "SEM CEP", COLORS["warning"]),
                                    ("erro", "ERRO", COLORS["danger"])]:
            box, val = stat_box(self.stats_row, label, color)
            box.pack(side="left", padx=(0, 10))
            self.count_labels[key] = val

    def _on_modo_change(self):
        if self.modo_var.get() == "lote":
            self.pasta_label["text"] = "Pasta onde salvar os XMLs"
            self._build_stats_lote()
        else:
            self.pasta_label["text"] = "Pasta base de saída (subpastas COM CEP / SEM CEP criadas automaticamente)"
            self._build_stats_cep()

    def _browse_arquivo(self):
        path = filedialog.askopenfilename(title="Selecione o .txt com os IDs",
                                           filetypes=[("Arquivo de texto", "*.txt"), ("Todos", "*.*")])
        if path:
            self.arquivo_var.set(path)

    def _browse_pasta(self):
        titulo = "Selecione a pasta base de saída" if self.modo_var.get() == "cep" \
            else "Selecione a pasta onde salvar os XMLs"
        path = filedialog.askdirectory(title=titulo)
        if path:
            self.pasta_var.set(path)

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
        arquivo = self.arquivo_var.get().strip()
        pasta = self.pasta_var.get().strip()
        arquivo_erro = self.arquivo_erro_var.get().strip() or None
        modo = self.modo_var.get()

        if not arquivo or not os.path.exists(arquivo):
            messagebox.showwarning("Arquivo inválido", "Selecione um .txt válido com os IDs.")
            return
        if not pasta:
            messagebox.showwarning("Pasta não definida", "Escolha a pasta de destino.")
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
        self.radio_lote["state"] = "disabled"
        self.radio_cep["state"] = "disabled"

        # Threads fixo (não exposto na tela) -- mantém o desempenho sem
        # expor um parâmetro que poderia sobrecarregar o servidor se mal
        # configurado.
        threads = 8

        if modo == "lote":
            engine = DownloadXmlsEngine(
            self.event_queue, self.stop_event, ambiente=self.controller.ambiente_var.get(),
                pasta_destino=pasta, arquivo_erro=arquivo_erro, threads=threads,
                log_dir=self.log_dir_var.get().strip()
            )
        else:
            engine = DownloadComSemCepEngine(
            self.event_queue, self.stop_event, ambiente=self.controller.ambiente_var.get(),
                pasta_destino=pasta, arquivo_erro=arquivo_erro, threads=threads,
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
            if "ok_com" in event:
                self.count_labels["ok_com"]["text"] = str(event["ok_com"])
                self.count_labels["ok_sem"]["text"] = str(event["ok_sem"])
                self.count_labels["erro"]["text"] = str(event["erro"])
            else:
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
            self.radio_lote["state"] = "normal"
            self.radio_cep["state"] = "normal"
        elif kind == "done":
            self.start_btn["state"] = "normal"
            self.stop_btn["state"] = "disabled"
            self.radio_lote["state"] = "normal"
            self.radio_cep["state"] = "normal"
            if event["cancelled"]:
                self._append_log("Processo cancelado pelo usuário.", "INFO")
            else:
                if "ok_com" in event:
                    self._append_log(
                        f"Finalizado. COM CEP={event['ok_com']} | SEM CEP={event['ok_sem']} | "
                        f"Erro={event['erro']} | Log: {event.get('log_file', '')}", "INFO")
                    messagebox.showinfo("Concluído",
                                         f"Download finalizado.\n\nCOM CEP: {event['ok_com']}\n"
                                         f"SEM CEP: {event['ok_sem']}\nErro: {event['erro']}")
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
