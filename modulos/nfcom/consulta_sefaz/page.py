"""Tela portada do MEGA QG VIVO NFCom v2.3 (legado/NFCom preview/qg.py). Na v3.8 ganhou os
contadores do reenvio das chaves com HTTP 422 (ver engine) e saiu do porte automático."""
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from core.config import AMBIENTE_HML, AMBIENTE_PRD
from ui.theme import COLORS, escala
from ui.widgets import ScrolledText, _open_folder, back_button, centralizar, stat_box
from modulos.nfcom.comum import *  # noqa: F401,F403 - imports/constantes do QG original
from modulos.nfcom.consulta_sefaz.engine import CheckSefazEngine


class ChecksefazPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLORS["bg"])
        self.controller = controller

        self.event_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread = None

        self.file_path = tk.StringVar()
        self.log_dir = tk.StringVar(value=DEFAULT_LOG_DIR)
        self.ambiente_var = controller.ambiente_var  # ambiente global do MegaQG Vivo  # v2.1

        self.group_bars = {}
        self.group_labels = {}
        self.group_wait_labels = {}
        self.status_counts = {}
        self.count_labels = {}
        self.group_remaining = {}  # v2.1: ETA (segundos) por grupo ainda ativo

        back_button(self, controller, "🔎 Consulta SEFAZ", "checagem em lote de chaves NFCom")
        self._build_ui()
        self._poll_queue()

    def _build_ui(self):
        pad = {"padx": 18, "pady": 6}

        file_frame = ttk.LabelFrame(self, text="ARQUIVO DE CHAVES NFCOM")
        file_frame.pack(fill="x", **pad)

        row1 = tk.Frame(file_frame, bg=COLORS["panel"])
        row1.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Entry(row1, textvariable=self.file_path, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(row1, text="Procurar...", command=self._browse_file).pack(side="left", padx=(6, 0))

        row2 = tk.Frame(file_frame, bg=COLORS["panel"])
        row2.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(row2, text="Pasta de log:", style="PanelMuted.TLabel").pack(side="left")
        ttk.Entry(row2, textvariable=self.log_dir, state="readonly").pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row2, text="Abrir pasta", command=self._open_log_dir).pack(side="left", padx=(6, 0))

        # v2.1: seletor de ambiente (Produção/Homologação).
        row3 = tk.Frame(file_frame, bg=COLORS["panel"])
        row3.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(row3, text="Ambiente:", style="PanelMuted.TLabel").pack(side="left")
        ttk.Label(row3, textvariable=self.ambiente_var, style="Ambiente.TLabel").pack(side="left", padx=6)

        controls = tk.Frame(self, bg=COLORS["bg"])
        controls.pack(fill="x", **pad)
        self.start_btn = ttk.Button(controls, text="▶  Iniciar", style="Accent.TButton", command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(controls, text="■  Parar", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))
        self.total_label = ttk.Label(controls, text="", style="Muted.TLabel")
        self.total_label.pack(side="left", padx=(16, 0))

        groups_frame = ttk.LabelFrame(self, text="PROGRESSO POR GRUPO")
        groups_frame.pack(fill="x", **pad)

        for nome in GROUP_ORDER:
            row = tk.Frame(groups_frame, bg=COLORS["panel"])
            row.pack(fill="x", padx=10, pady=5)
            ttk.Label(row, text=nome, width=6, style="Panel.TLabel",
                      font=("Segoe UI", 10, "bold")).pack(side="left")
            bar = ttk.Progressbar(row, maximum=100, value=0)
            bar.pack(side="left", fill="x", expand=True, padx=6)
            self.group_bars[nome] = bar
            lbl = ttk.Label(row, text="0 / 0", width=12, anchor="e", style="Panel.TLabel")
            lbl.pack(side="left")
            self.group_labels[nome] = lbl
            wait_lbl = ttk.Label(row, text="", width=22, style="PanelMuted.TLabel", anchor="w")
            wait_lbl.pack(side="left", padx=(6, 0))
            self.group_wait_labels[nome] = wait_lbl

        summary = ttk.LabelFrame(self, text="RESUMO")
        summary.pack(fill="x", **pad)
        summary_row = tk.Frame(summary, bg=COLORS["panel"])
        summary_row.pack(fill="x", padx=10, pady=8)

        for status, color in [("OK", COLORS["success"]), ("HTTP_ERR", COLORS["warning"]),
                                ("FAIL_TIMEOUT", COLORS["danger"]), ("ERROR_FINAL", COLORS["danger"]),
                                # v3.8: reenvio pelo ID das chaves que voltaram HTTP 422
                                ("REENVIADAS", COLORS["success"]), ("REENVIO C/ ERRO", COLORS["warning"])]:
            box, val = stat_box(summary_row, status, color)
            box.pack(side="left", padx=(0, 10))
            self.count_labels[status] = val
            self.status_counts[status] = 0

        # v2.1: card de ETA (tempo estimado de conclusão), atualizado em
        # tempo real a partir do throughput observado em cada grupo ativo.
        eta_box, eta_val = stat_box(summary_row, "ETA (conclusão)", COLORS["accent"])
        eta_box.pack(side="left", padx=(0, 10))
        self.eta_label = eta_val
        self.eta_label["text"] = "--:--"

        log_frame = ttk.LabelFrame(self, text="LOG DE EXECUÇÃO")
        log_frame.pack(fill="both", expand=True, **pad)
        self.log_text = ScrolledText(log_frame, height=10, state="disabled",
                                                    font=("Consolas", 9), bg=COLORS["card"],
                                                    fg=COLORS["fg"], insertbackground=COLORS["fg"],
                                                    borderwidth=0, highlightthickness=0)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
        self.log_text.tag_config("OK", foreground=COLORS["success"])
        self.log_text.tag_config("INFO", foreground=COLORS["fg_muted"])
        self.log_text.tag_config("HTTP", foreground=COLORS["warning"])
        self.log_text.tag_config("ERR", foreground=COLORS["danger"])
        self.log_text.tag_config("DEFAULT", foreground=COLORS["fg"])

    def _browse_file(self):
        path = filedialog.askopenfilename(title="Selecione o .txt com as chaves NFCom",
                                           filetypes=[("Arquivo de texto", "*.txt"), ("Todos", "*.*")])
        if path:
            self.file_path.set(path)

    def _browse_log_dir(self):
        path = filedialog.askdirectory(title="Selecione a pasta de log")
        if path:
            self.log_dir.set(path)

    def _open_log_dir(self):
        path = self.log_dir.get()
        if not os.path.exists(path):
            messagebox.showwarning("Pasta não encontrada", "A pasta de log ainda não existe.")
            return
        _open_folder(path)

    def _start(self):
        path = self.file_path.get().strip()
        if not path:
            messagebox.showwarning("Arquivo não selecionado", "Selecione o arquivo .txt com as chaves NFCom.")
            return
        if not os.path.exists(path):
            messagebox.showerror("Arquivo não encontrado", f"Não foi possível localizar:\n{path}")
            return

        self.stop_event = threading.Event()
        for nome in GROUP_ORDER:
            self.group_bars[nome]["value"] = 0
            self.group_bars[nome]["maximum"] = 100
            self.group_labels[nome]["text"] = "0 / 0"
            self.group_wait_labels[nome]["text"] = ""
        for status in self.status_counts:
            self.status_counts[status] = 0
            self.count_labels[status]["text"] = "0"
        self.group_remaining = {}
        self.eta_label["text"] = "--:--"
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.total_label["text"] = ""

        self.start_btn["state"] = "disabled"
        self.stop_btn["state"] = "normal"

        engine = CheckSefazEngine(self.event_queue, self.stop_event, self.log_dir.get(),
                                   ambiente=self.ambiente_var.get())
        self.worker_thread = threading.Thread(target=engine.run, args=(path,), daemon=True)
        self.worker_thread.start()

    def _stop(self):
        self.stop_event.set()
        self.stop_btn["state"] = "disabled"
        self._append_log("Cancelamento solicitado, aguardando threads em andamento...", "INFO")

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
        if kind == "total_keys":
            grupos = event["grupos"]
            self.total_label["text"] = f"Total: {event['n']} chaves  (" + \
                ", ".join(f"{k}: {v}" for k, v in grupos.items()) + ")"
            for nome in GROUP_ORDER:
                total = grupos.get(nome, 0)
                self.group_bars[nome]["maximum"] = max(total, 1)
                self.group_labels[nome]["text"] = f"0 / {total}"
        elif kind == "group_start":
            self.group_wait_labels[event["grupo"]]["text"] = "processando..."
        elif kind == "progress":
            nome, done, total = event["grupo"], event["done"], event["total"]
            self.group_bars[nome]["value"] = done
            self.group_labels[nome]["text"] = f"{done} / {total}"
            # v2.1: eta_seconds já vem calculado pela engine (throughput real
            # observado até agora), então só guardamos e recalculamos o
            # card de resumo.
            self.group_remaining[nome] = event.get("eta_seconds")
            self._update_eta_label()
        elif kind == "wait_tick":
            nome, remaining = event["grupo"], event["remaining"]
            if remaining > 0:
                m, s = divmod(remaining, 60)
                self.group_wait_labels[nome]["text"] = f"aguardando {m:02d}:{s:02d}"
                # v2.1: durante a pausa obrigatória, o grupo com certeza
                # ainda vai levar pelo menos "remaining" segundos -- usamos
                # isso como piso para o ETA ir contando ao vivo mesmo sem
                # nenhum "progress" novo chegando.
                atual = self.group_remaining.get(nome) or 0
                self.group_remaining[nome] = max(remaining, atual)
            else:
                self.group_wait_labels[nome]["text"] = "processando..."
            self._update_eta_label()
        elif kind == "group_done":
            nome = event["grupo"]
            self.group_wait_labels[nome]["text"] = "cancelado" if event["cancelled"] else "concluído"
            self.group_remaining.pop(nome, None)
            self._update_eta_label()
        elif kind == "status_count":
            status = event["status"]
            if status.startswith("REENVIO"):
                bucket = "REENVIADAS" if status == "REENVIO_OK" else "REENVIO C/ ERRO"
            else:
                bucket = status if status in self.status_counts else ("HTTP_ERR" if status.startswith("HTTP") else None)
            if bucket:
                self.status_counts[bucket] += 1
                self.count_labels[bucket]["text"] = str(self.status_counts[bucket])
        elif kind == "log_line":
            self._append_log(event["text"], event["status"])
        elif kind == "fatal_error":
            self._append_log(f"ERRO FATAL: {event['text']}", "ERROR_FINAL")
            messagebox.showerror("Erro", event["text"])
            self.start_btn["state"] = "normal"
            self.stop_btn["state"] = "disabled"
        elif kind == "all_done":
            self.start_btn["state"] = "normal"
            self.stop_btn["state"] = "disabled"
            msg = "Processo cancelado pelo usuário." if event["cancelled"] else "Processo finalizado."
            self._append_log(msg, "INFO")
            if not event["cancelled"]:
                texto = "Consulta de todas as chaves finalizada."
                reenviadas, com_erro = self.status_counts["REENVIADAS"], self.status_counts["REENVIO C/ ERRO"]
                if reenviadas or com_erro:
                    texto += (f"\n\nReenvio das chaves com HTTP 422: {reenviadas} reenviada(s), "
                              f"{com_erro} com erro (detalhes no log).")
                messagebox.showinfo("Concluído", texto)

    def _update_eta_label(self):
        # v2.1: os grupos rodam em paralelo (uma thread cada), então o
        # processo inteiro só termina quando o grupo MAIS lento terminar --
        # por isso o ETA geral é o maior valor entre os grupos ainda ativos,
        # não a soma.
        candidatos = [v for v in self.group_remaining.values() if v is not None]
        if not candidatos:
            self.eta_label["text"] = "--:--" if self.group_remaining else "concluído"
            return
        segundos = max(0, int(max(candidatos)))
        m, s = divmod(segundos, 60)
        self.eta_label["text"] = f"{m:02d}:{s:02d}"

    def _append_log(self, text, status):
        if status.startswith("REENVIO"):  # v3.8: 2xx verde, outro código amarelo, sem ID/sem resposta vermelho
            tag = {"REENVIO_OK": "OK", "REENVIO_HTTP": "HTTP"}.get(status, "ERR")
        elif status.startswith("HTTP"):
            tag = "HTTP"
        elif "TIMEOUT" in status or "ERROR" in status:
            tag = "ERR"
        elif status in ("OK", "INFO"):
            tag = status
        else:
            tag = "DEFAULT"
        self.log_text.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {text}\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
