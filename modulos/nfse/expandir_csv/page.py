"""Tela portada do MEGA QG VIVO NFSe v2.0 (legado/NFSe/qg.py)."""
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from core.config import AMBIENTE_HML, AMBIENTE_PRD
from ui.theme import COLORS, escala
from ui.widgets import ScrolledText, _open_folder, back_button, centralizar, stat_box
from modulos.nfse.comum import *  # noqa: F401,F403 - imports do QG original
from modulos.nfse.expandir_csv.engine import ExpandirDpsCsvEngine


class ExpandirDpsCsvPage(tk.Frame):
    ENCODINGS = {
        "Windows-1252 (padrão Excel BR)": "cp1252",
        "UTF-8": "utf-8",
        "UTF-8 com BOM (CSV UTF-8 do Excel)": "utf-8-sig",
    }

    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLORS["bg"])
        self.controller = controller

        self.event_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread = None

        self.arquivo_var = tk.StringVar()
        self.saida_var = tk.StringVar()
        self.delimitador_var = tk.StringVar(value=";")
        self.coluna_var = tk.StringVar(value="DPS")
        self.encoding_var = tk.StringVar(value="Windows-1252 (padrão Excel BR)")
        self.log_dir_var = tk.StringVar(value=DEFAULT_LOG_DIR)

        self.count_labels = {}

        back_button(self, controller, "🧩 Expandir DPS no CSV",
                    "uma linha por DPS a partir de uma coluna agrupada")

        note = tk.Label(self, text=(
            "Pega um CSV (ex.: a planilha do Relatório DPS sem Endereço, já preenchida com o "
            "endereço) onde a coluna escolhida tem vários valores separados por vírgula, e gera "
            "um novo CSV com uma linha por valor, duplicando as demais colunas. Se o arquivo veio "
            "de um \"Salvar como CSV\" do Excel no Brasil, a codificação normalmente é Windows-1252."),
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

        ttk.Label(body, text="Arquivo CSV de entrada", style="PanelMuted.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w")
        row_arq = tk.Frame(body, bg=COLORS["panel"])
        row_arq.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        ttk.Entry(row_arq, textvariable=self.arquivo_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row_arq, text="Procurar...", command=self._browse_arquivo).pack(side="left", padx=(6, 0))

        ttk.Label(body, text="Arquivo CSV de saída", style="PanelMuted.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w")
        row_saida = tk.Frame(body, bg=COLORS["panel"])
        row_saida.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        ttk.Entry(row_saida, textvariable=self.saida_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row_saida, text="Escolher...", command=self._browse_saida).pack(side="left", padx=(6, 0))

        ttk.Label(body, text="Coluna a expandir", style="PanelMuted.TLabel").grid(row=4, column=0, sticky="w")
        ttk.Entry(body, textvariable=self.coluna_var).grid(row=5, column=0, sticky="ew", padx=(0, 8))

        ttk.Label(body, text="Delimitador", style="PanelMuted.TLabel").grid(row=4, column=1, sticky="w")
        ttk.Combobox(body, textvariable=self.delimitador_var, state="readonly",
                     values=[";", ","]).grid(row=5, column=1, sticky="ew", padx=(8, 0))

        ttk.Label(body, text="Codificação do arquivo de entrada", style="PanelMuted.TLabel").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Combobox(body, textvariable=self.encoding_var, state="readonly",
                     values=list(self.ENCODINGS.keys())).grid(
            row=7, column=0, columnspan=2, sticky="ew")

        ttk.Label(body, text="Pasta de log", style="PanelMuted.TLabel").grid(
            row=8, column=0, columnspan=2, sticky="w", pady=(10, 0))
        row_log = tk.Frame(body, bg=COLORS["panel"])
        row_log.grid(row=9, column=0, columnspan=2, sticky="ew")
        ttk.Entry(row_log, textvariable=self.log_dir_var, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(row_log, text="Abrir pasta", command=self._open_log_dir).pack(side="left", padx=(6, 0))

        controls = tk.Frame(self, bg=COLORS["bg"])
        controls.pack(fill="x", **pad)
        self.start_btn = ttk.Button(controls, text="▶  Expandir CSV", style="Indigo.TButton",
                                     command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(controls, text="■  Parar", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))

        progress_frame = ttk.LabelFrame(self, text="PROGRESSO")
        progress_frame.pack(fill="x", **pad)
        pbody = tk.Frame(progress_frame, bg=COLORS["panel"])
        pbody.pack(fill="x", padx=10, pady=10)

        self.progress_bar = ttk.Progressbar(pbody, style="Indigo.Horizontal.TProgressbar", maximum=100, value=0)
        self.progress_bar.pack(fill="x", side="left", expand=True)
        self.progress_label = ttk.Label(pbody, text="0 / 0", style="Panel.TLabel", width=12, anchor="e")
        self.progress_label.pack(side="left", padx=(8, 0))

        stats_row = tk.Frame(progress_frame, bg=COLORS["panel"])
        stats_row.pack(fill="x", padx=10, pady=(0, 10))
        for key, label, color in [("linhas_entrada", "LINHAS LIDAS", COLORS["fg_muted"]),
                                    ("linhas_saida", "LINHAS GERADAS", COLORS["indigo"])]:
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
        self.log_text.tag_config("OK", foreground=COLORS["indigo"])
        self.log_text.tag_config("INFO", foreground=COLORS["fg_muted"])
        self.log_text.tag_config("ERROR", foreground=COLORS["danger"])

    def _browse_arquivo(self):
        path = filedialog.askopenfilename(title="Selecione o CSV de entrada",
                                           filetypes=[("CSV", "*.csv"), ("Todos", "*.*")])
        if path:
            self.arquivo_var.set(path)
            if not self.saida_var.get().strip():
                base, ext = os.path.splitext(path)
                self.saida_var.set(f"{base}_tratado.csv")

    def _browse_saida(self):
        path = filedialog.asksaveasfilename(title="Escolha onde salvar o CSV expandido",
                                             defaultextension=".csv",
                                             filetypes=[("CSV", "*.csv")])
        if path:
            self.saida_var.set(path)

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
        saida = self.saida_var.get().strip()
        coluna = self.coluna_var.get().strip()
        delimitador = self.delimitador_var.get()

        if not arquivo or not os.path.exists(arquivo):
            messagebox.showwarning("Arquivo inválido", "Selecione um CSV de entrada válido.")
            return
        if not saida:
            messagebox.showwarning("Saída não definida", "Escolha onde o CSV expandido será salvo.")
            return
        if not coluna:
            messagebox.showwarning("Coluna não definida", "Informe o nome da coluna a expandir.")
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

        encoding_entrada = self.ENCODINGS[self.encoding_var.get()]

        engine = ExpandirDpsCsvEngine(
            self.event_queue, self.stop_event,
            arquivo_entrada=arquivo, arquivo_saida=saida, delimitador=delimitador,
            coluna=coluna, encoding_entrada=encoding_entrada,
            log_dir=self.log_dir_var.get().strip()
        )
        self.worker_thread = threading.Thread(target=engine.run, daemon=True)
        self.worker_thread.start()

    def _stop(self):
        self.stop_event.set()
        self.stop_btn["state"] = "disabled"
        self._append_log("Parada solicitada...", "INFO")

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
            self.count_labels["linhas_entrada"]["text"] = str(n)
        elif kind == "progress":
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
                self.count_labels["linhas_saida"]["text"] = str(event["linhas_saida"])
                self._append_log(
                    f"Finalizado. {event['linhas_entrada']} linha(s) de entrada -> "
                    f"{event['linhas_saida']} linha(s) de saída. Arquivo: {event['arquivo']} | "
                    f"Log: {event.get('log_file', '')}", "OK")
                messagebox.showinfo("Concluído",
                                     f"CSV expandido com sucesso!\n\n{event['arquivo']}\n\n"
                                     f"{event['linhas_entrada']} linha(s) -> {event['linhas_saida']} linha(s)")

    def _append_log(self, text, status):
        tag = status if status in ("OK", "INFO", "ERROR") else "INFO"
        self.log_text.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {text}\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
