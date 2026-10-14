"""Tela do Download massivo de XMLs de NFCe (mesmo desenho do Download de XMLs de NFCom)."""
import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from core import config
from modulos.nfce.download_xmls.engine import DownloadXmlsNfceEngine
from ui.theme import COLORS
from ui.widgets import ScrolledText, _open_folder, back_button, stat_box

THREADS = 8  # fixo, como no Download de XMLs de NFCom


class DownloadXmlsNfcePage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLORS["bg"])
        self.controller = controller

        self.event_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread = None

        self.ambiente_var = controller.ambiente_var  # ambiente global do MegaQG Vivo
        self.arquivo_var = tk.StringVar()
        self.pasta_saida_var = tk.StringVar()
        self.log_dir_var = tk.StringVar(value=config.log_dir())

        self.count_labels = {}

        back_button(self, controller, "📥 Download de XMLs NFCe",
                    "baixa em massa os XMLs de emissão a partir de um .txt de chaves")
        self._build_ui()
        self._poll_queue()

    def _build_ui(self):
        pad = {"padx": 18, "pady": 6}

        cfg = ttk.LabelFrame(self, text="PARÂMETROS")
        cfg.pack(fill="x", **pad)
        body = tk.Frame(cfg, bg=COLORS["panel"])
        body.pack(fill="x", padx=10, pady=10)
        body.grid_columnconfigure(0, weight=1)

        ttk.Label(body, text="Ambiente", style="PanelMuted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(body, textvariable=self.ambiente_var, style="Ambiente.TLabel").grid(row=1, column=0, sticky="ew")

        ttk.Label(body, text="Arquivo .txt com as chaves de acesso (44 dígitos, uma por linha)",
                  style="PanelMuted.TLabel").grid(row=2, column=0, sticky="w", pady=(10, 0))
        row_arq = tk.Frame(body, bg=COLORS["panel"])
        row_arq.grid(row=3, column=0, sticky="ew", pady=(2, 10))
        ttk.Entry(row_arq, textvariable=self.arquivo_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row_arq, text="Procurar...", command=self._browse_arquivo).pack(side="left", padx=(6, 0))

        ttk.Label(body, text="Pasta de saída dos XMLs", style="PanelMuted.TLabel").grid(row=4, column=0, sticky="w")
        row_saida = tk.Frame(body, bg=COLORS["panel"])
        row_saida.grid(row=5, column=0, sticky="ew", pady=(2, 10))
        ttk.Entry(row_saida, textvariable=self.pasta_saida_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row_saida, text="Procurar...", command=self._browse_pasta_saida).pack(side="left", padx=(6, 0))

        ttk.Label(body, text="Pasta de log", style="PanelMuted.TLabel").grid(row=6, column=0, sticky="w")
        row_log = tk.Frame(body, bg=COLORS["panel"])
        row_log.grid(row=7, column=0, sticky="ew", pady=(2, 0))
        ttk.Entry(row_log, textvariable=self.log_dir_var, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(row_log, text="Abrir pasta", command=self._open_log_dir).pack(side="left", padx=(6, 0))

        controls = tk.Frame(self, bg=COLORS["bg"])
        controls.pack(fill="x", **pad)
        self.start_btn = ttk.Button(controls, text="▶  Iniciar Download", style="Teal.TButton", command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(controls, text="■  Parar", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Abrir pasta de saída", command=self._open_pasta_saida).pack(
            side="left", padx=(8, 0))

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
                                  ("invalidas", "CHAVES INVÁLIDAS", COLORS["warning"])]:
            box, val = stat_box(stats_row, label, color)
            box.pack(side="left", padx=(0, 10))
            self.count_labels[key] = val

        log_frame = ttk.LabelFrame(self, text="LOG DE EXECUÇÃO")
        log_frame.pack(fill="both", expand=True, **pad)
        self.log_text = ScrolledText(log_frame, height=10, state="disabled", font=("Consolas", 9),
                                     bg=COLORS["card"], fg=COLORS["fg"], insertbackground=COLORS["fg"],
                                     borderwidth=0, highlightthickness=0)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
        for tag, cor in (("OK", COLORS["success"]), ("INFO", COLORS["fg_muted"]), ("WARN", COLORS["warning"]),
                         ("ERROR", COLORS["danger"])):
            self.log_text.tag_config(tag, foreground=cor)

    def _browse_arquivo(self):
        path = filedialog.askopenfilename(title="Selecione o .txt com as chaves de acesso",
                                          filetypes=[("Arquivo de texto", "*.txt"), ("Todos", "*.*")])
        if path:
            self.arquivo_var.set(path)

    def _browse_pasta_saida(self):
        path = filedialog.askdirectory(title="Selecione a pasta de saída dos XMLs")
        if path:
            self.pasta_saida_var.set(path)

    def _open_log_dir(self):
        path = self.log_dir_var.get()
        if not os.path.exists(path):
            messagebox.showwarning("Pasta não encontrada", "A pasta de log ainda não existe.")
            return
        _open_folder(path)

    def _open_pasta_saida(self):
        path = self.pasta_saida_var.get().strip()
        if not path or not os.path.isdir(path):
            messagebox.showwarning("Pasta não encontrada", "A pasta de saída ainda não existe.")
            return
        _open_folder(path)

    def _start(self):
        arquivo = self.arquivo_var.get().strip()
        pasta_saida = self.pasta_saida_var.get().strip()
        if not arquivo or not os.path.isfile(arquivo):
            messagebox.showwarning("Arquivo inválido", "Selecione um .txt válido com as chaves de acesso.")
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

        engine = DownloadXmlsNfceEngine(
            self.event_queue, self.stop_event, ambiente=self.ambiente_var.get(),
            pasta_saida=pasta_saida, threads=THREADS, log_dir=self.log_dir_var.get().strip())
        self.worker_thread = threading.Thread(target=engine.run, args=(arquivo,), daemon=True)
        self.worker_thread.start()

    def _stop(self):
        self.stop_event.set()
        self.stop_btn["state"] = "disabled"
        self._append_log("Parada solicitada, aguardando downloads em andamento...", "INFO")

    def _poll_queue(self):
        try:
            while True:
                self._handle_event(self.event_queue.get_nowait())
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
            for key in ("ok", "erro", "invalidas"):
                self.count_labels[key]["text"] = str(event[key])
            self.progress_bar["maximum"] = max(event["total"], 1)
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
                return
            self._append_log(f"Finalizado. Sucesso={event['ok']} | Erro={event['erro']} | "
                             f"Inválidas={event['invalidas']} | Log: {event['log_file']}", "INFO")
            msg = (f"Download finalizado.\n\nSucesso: {event['ok']}\nErro: {event['erro']}\n"
                   f"Chaves inválidas: {event['invalidas']}\n\nXMLs em:\n{event['pasta']}")
            if event["erro"]:
                messagebox.showwarning("Concluído com erros",
                                       msg + f"\n\nChaves com erro em:\n{event['arquivo_erro']}")
            else:
                messagebox.showinfo("Concluído", msg)

    def _append_log(self, text, status):
        tag = status if status in ("OK", "INFO", "WARN", "ERROR") else "INFO"
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{datetime.now():%H:%M:%S}] {text}\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
