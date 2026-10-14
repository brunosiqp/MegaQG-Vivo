"""Tela do Relatório DPS sem Endereço: portada do MEGA QG VIVO NFSe v2.0 (legado/NFSe/qg.py) e,
desde a v3.6, com uma linha por DPS, as abas novas e o nome padrão com a data (ver engine.py)."""
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from core.config import AMBIENTE_HML, AMBIENTE_PRD
from ui.theme import COLORS, escala
from ui.widgets import ScrolledText, _open_folder, back_button, centralizar, stat_box
from modulos.nfse.comum import *  # noqa: F401,F403 - imports do QG original
from modulos.nfse.relatorio_dps.engine import (
    NOME_ABA1,
    NOME_ABA2,
    RelatorioSemCepEngine,
    eh_nome_padrao,
    nome_padrao_planilha,
)


class RelatorioSemCepPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLORS["bg"])
        self.controller = controller

        self.event_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread = None

        self.pasta_var = tk.StringVar()
        self.saida_var = tk.StringVar()
        self.aba1_var = tk.StringVar(value=NOME_ABA1)
        self.aba2_var = tk.StringVar(value=NOME_ABA2)
        self.log_dir_var = tk.StringVar(value=DEFAULT_LOG_DIR)

        self.count_labels = {}

        back_button(self, controller, "📊 Relatório DPS sem Endereço",
                    "planilha com uma linha por DPS pendente de endereço")

        note = tk.Label(self, text=(
            "Lê os XMLs de uma pasta (normalmente a saída \"SEM CEP\" do Download de XMLs) "
            "e gera um .xlsx com uma linha por DPS: na 1ª aba DPS, Nome e CPF do tomador; na 2ª, a "
            "mesma DPS com os dados de endereço que vieram no XML. XMLs repetidos da mesma DPS viram uma "
            "linha só. O nome padrão do arquivo leva a data do dia (Planilha -dd-mm-aaaa)."),
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

        ttk.Label(body, text="Pasta com os XMLs a analisar", style="PanelMuted.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w")
        row_pasta = tk.Frame(body, bg=COLORS["panel"])
        row_pasta.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        ttk.Entry(row_pasta, textvariable=self.pasta_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row_pasta, text="Procurar...", command=self._browse_pasta).pack(side="left", padx=(6, 0))

        ttk.Label(body, text="Planilha de saída (.xlsx)", style="PanelMuted.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w")
        row_saida = tk.Frame(body, bg=COLORS["panel"])
        row_saida.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 10))
        ttk.Entry(row_saida, textvariable=self.saida_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row_saida, text="Escolher...", command=self._browse_saida).pack(side="left", padx=(6, 0))

        ttk.Label(body, text="Nome da 1ª aba (dados encontrados)", style="PanelMuted.TLabel").grid(
            row=4, column=0, sticky="w")
        ttk.Entry(body, textvariable=self.aba1_var).grid(row=5, column=0, sticky="ew", padx=(0, 8))

        ttk.Label(body, text="Nome da 2ª aba (dados de endereço)", style="PanelMuted.TLabel").grid(
            row=4, column=1, sticky="w")
        ttk.Entry(body, textvariable=self.aba2_var).grid(row=5, column=1, sticky="ew", padx=(8, 0))

        ttk.Label(body, text="Pasta de log", style="PanelMuted.TLabel").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(10, 0))
        row_log = tk.Frame(body, bg=COLORS["panel"])
        row_log.grid(row=7, column=0, columnspan=2, sticky="ew")
        ttk.Entry(row_log, textvariable=self.log_dir_var, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(row_log, text="Abrir pasta", command=self._open_log_dir).pack(side="left", padx=(6, 0))

        controls = tk.Frame(self, bg=COLORS["bg"])
        controls.pack(fill="x", **pad)
        self.start_btn = ttk.Button(controls, text="▶  Gerar Planilha", style="Purple.TButton",
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
        for key, label, color in [("total_xml", "XMLs LIDOS", COLORS["fg_muted"]),
                                    ("validos", "COM CPF/NOME", COLORS["purple"]),
                                    ("agrupados", "DPS NA PLANILHA", COLORS["warning"]),
                                    ("repetidas", "REPETIDAS CONSOLIDADAS", COLORS["fg_muted"])]:
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
        self.log_text.tag_config("OK", foreground=COLORS["purple"])
        self.log_text.tag_config("INFO", foreground=COLORS["fg_muted"])
        self.log_text.tag_config("ERROR", foreground=COLORS["danger"])

    def _browse_pasta(self):
        path = filedialog.askdirectory(title="Selecione a pasta com os XMLs")
        if path:
            self.pasta_var.set(path)
            atual = self.saida_var.get().strip()
            if not atual or eh_nome_padrao(atual):
                self.saida_var.set(os.path.join(os.path.dirname(path.rstrip("\\/")), nome_padrao_planilha()))

    def _browse_saida(self):
        path = filedialog.asksaveasfilename(title="Escolha onde salvar a planilha",
                                             defaultextension=".xlsx", initialfile=nome_padrao_planilha(),
                                             filetypes=[("Planilha Excel", "*.xlsx")])
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
        pasta = self.pasta_var.get().strip()
        saida = self.saida_var.get().strip()

        if not pasta or not os.path.isdir(pasta):
            messagebox.showwarning("Pasta inválida", "Selecione uma pasta válida contendo os XMLs.")
            return
        if not saida:
            messagebox.showwarning("Saída não definida", "Escolha onde a planilha (.xlsx) será salva.")
            return
        if eh_nome_padrao(saida):  # nome padrão: sempre com a data do momento da geração
            saida = os.path.join(os.path.dirname(saida), nome_padrao_planilha())
            self.saida_var.set(saida)

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

        engine = RelatorioSemCepEngine(
            self.event_queue, self.stop_event,
            pasta=pasta, arquivo_saida=saida,
            nome_aba1=self.aba1_var.get().strip(), nome_aba2=self.aba2_var.get().strip(),
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
            self.count_labels["total_xml"]["text"] = str(n)
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
                self.count_labels["validos"]["text"] = str(event["validos"])
                self.count_labels["agrupados"]["text"] = str(event["agrupados"])
                self.count_labels["repetidas"]["text"] = str(event.get("repetidas", 0))
                self._append_log(
                    f"Finalizado. {event['validos']} registro(s) válido(s), "
                    f"{event['agrupados']} DPS na planilha (uma linha por DPS). Planilha: {event['arquivo']} | "
                    f"Log: {event.get('log_file', '')}", "OK")
                messagebox.showinfo("Concluído",
                                     f"Planilha gerada com sucesso!\n\n{event['arquivo']}\n\n"
                                     f"DPS na planilha: {event['agrupados']}")

    def _append_log(self, text, status):
        tag = status if status in ("OK", "INFO", "ERROR") else "INFO"
        self.log_text.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {text}\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
