"""Tela portada do MEGA QG VIVO NFCom v2.3 (legado/NFCom preview/qg.py)."""
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from core.config import AMBIENTE_HML, AMBIENTE_PRD
from ui.theme import COLORS, escala
from ui.widgets import ScrolledText, _open_folder, back_button, centralizar, stat_box
from modulos.nfcom.comum import *  # noqa: F401,F403 - imports/constantes do QG original
from modulos.nfcom.cancelamento.engine import CancelamentoMassivoEngine


class CancelamentoPage(tk.Frame):
    URL_PRD = _endpoint("cancelamento_url_prd", "MEGAQG_CANCELAMENTO_URL_PRD")
    # v2.1: Homologação adicionada -- TODO CONFIRMAR host de HML com o time
    # de infra (segue o mesmo padrão de host usado no Download de XMLs/
    # Consulta SEFAZ em HML; não há garantia de que EventosFiscais exista
    # nesse mesmo host).
    URL_HML = _endpoint("cancelamento_url_hml", "MEGAQG_CANCELAMENTO_URL_HML")

    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLORS["bg"])
        self.controller = controller

        self.event_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread = None

        self.arquivo_var = tk.StringVar()
        self.ambiente_var = controller.ambiente_var  # ambiente global do MegaQG Vivo
        self.justificativa_var = tk.StringVar(value="Cancelamento homologado")
        self.log_dir_var = tk.StringVar(value=DEFAULT_LOG_DIR)

        self.count_labels = {}

        back_button(self, controller, "🛑 Cancelamento de Notas",
                    "CancelamentoMassivoNFCom_v2.2.0 — envio de eventos (110111)")
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

        ttk.Label(body, text="Arquivo .txt com as chaves NFCom (44 dígitos)", style="PanelMuted.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w")
        row_arq = tk.Frame(body, bg=COLORS["panel"])
        row_arq.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(2, 10))
        ttk.Entry(row_arq, textvariable=self.arquivo_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row_arq, text="Procurar...", command=self._browse_arquivo).pack(side="left", padx=(6, 0))

        ttk.Label(body, text="Ambiente", style="PanelMuted.TLabel").grid(row=2, column=0, sticky="w")
        ttk.Label(body, textvariable=self.ambiente_var, style="Ambiente.TLabel").grid(row=3, column=0, sticky="ew", padx=(0, 8))

        ttk.Label(body, text="Justificativa (xJust)", style="PanelMuted.TLabel").grid(
            row=2, column=1, columnspan=3, sticky="w")
        ttk.Entry(body, textvariable=self.justificativa_var).grid(
            row=3, column=1, columnspan=3, sticky="ew", padx=(8, 0))

        ttk.Label(body, text="Pasta de log", style="PanelMuted.TLabel").grid(
            row=4, column=0, columnspan=4, sticky="w", pady=(10, 0))
        row_log = tk.Frame(body, bg=COLORS["panel"])
        row_log.grid(row=5, column=0, columnspan=4, sticky="ew")
        ttk.Entry(row_log, textvariable=self.log_dir_var, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(row_log, text="Abrir pasta", command=self._open_log_dir).pack(side="left", padx=(6, 0))

        controls = tk.Frame(self, bg=COLORS["bg"])
        controls.pack(fill="x", **pad)
        self.start_btn = ttk.Button(controls, text="🛑  Iniciar Cancelamento", style="Danger.TButton",
                                     command=self._on_start_clicked)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(controls, text="■  Parar", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))

        progress_frame = ttk.LabelFrame(self, text="PROGRESSO")
        progress_frame.pack(fill="x", **pad)
        pbody = tk.Frame(progress_frame, bg=COLORS["panel"])
        pbody.pack(fill="x", padx=10, pady=10)

        self.progress_bar = ttk.Progressbar(pbody, style="Danger.Horizontal.TProgressbar", maximum=100, value=0)
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
        self.log_text.tag_config("WARN", foreground=COLORS["warning"])
        self.log_text.tag_config("ERROR", foreground=COLORS["danger"])

    def _browse_arquivo(self):
        path = filedialog.askopenfilename(title="Selecione o .txt com as chaves NFCom",
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

    def _on_start_clicked(self):
        arquivo = self.arquivo_var.get().strip()

        if not arquivo or not os.path.exists(arquivo):
            messagebox.showwarning("Arquivo inválido", "Selecione um .txt válido com as chaves NFCom.")
            return

        try:
            with open(arquivo, encoding="utf-8") as f:
                total_chaves = len([l for l in f if l.strip()])
        except Exception as e:
            messagebox.showerror("Erro ao ler arquivo", str(e))
            return

        if total_chaves == 0:
            messagebox.showwarning("Arquivo vazio", "O arquivo selecionado não contém chaves.")
            return

        self._show_confirm_dialog(arquivo, total_chaves)

    def _show_confirm_dialog(self, arquivo, total_chaves):
        modal = tk.Toplevel(self)
        modal.title("Confirmação obrigatória")
        modal.configure(bg=COLORS["danger_soft"])
        k = escala(self)
        centralizar(modal, int(600 * k), int(380 * k))
        modal.resizable(False, False)
        modal.transient(self.winfo_toplevel())
        modal.grab_set()

        tk.Frame(modal, bg=COLORS["danger"], height=6).pack(fill="x")

        body = tk.Frame(modal, bg=COLORS["danger_soft"])
        body.pack(fill="both", expand=True, padx=26, pady=22)

        tk.Label(body, text="⚠  ATENÇÃO", bg=COLORS["danger_soft"], fg=COLORS["danger"],
                 font=("Segoe UI", 18, "bold")).pack(anchor="w")

        msg = (f"Você está prestes a enviar eventos de CANCELAMENTO para "
               f"{total_chaves} chave(s) NFCom no ambiente de {self.ambiente_var.get().upper()}, listadas em:\n\n{arquivo}\n\n"
               "Esta ação dispara o evento 110111 junto ao SEFAZ e é IRREVERSÍVEL. "
               "Certifique-se de que essas notas realmente devem ser canceladas antes de prosseguir.")
        tk.Label(body, text=msg, bg=COLORS["danger_soft"], fg=COLORS["fg"], font=("Segoe UI", 10),
                 justify="left", wraplength=int(540 * k)).pack(anchor="w", pady=(12, 20))

        btns = tk.Frame(body, bg=COLORS["danger_soft"])
        btns.pack(fill="x", side="bottom")

        result = {"ok": False}

        def aceitar():
            result["ok"] = True
            modal.destroy()

        def recusar():
            result["ok"] = False
            modal.destroy()

        ttk.Button(btns, text="Cancelar operação", command=recusar).pack(side="left")
        ttk.Button(btns, text="Sim, autorizo o cancelamento", style="Danger.TButton",
                   command=aceitar).pack(side="right")

        modal.protocol("WM_DELETE_WINDOW", recusar)
        self.wait_window(modal)

        if result["ok"]:
            self._begin_processing(arquivo)
        else:
            self._append_log("Operação de cancelamento NÃO autorizada pelo usuário.", "WARN")

    def _begin_processing(self, arquivo):
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

        is_producao = self.ambiente_var.get().startswith("Produção")
        tp_amb = "1" if is_producao else "2"
        url = self.URL_PRD if is_producao else self.URL_HML  # v2.1

        # Threads fixo (não exposto na tela).
        threads = 8

        engine = CancelamentoMassivoEngine(
            self.event_queue, self.stop_event,
            url=url,
            tp_amb=tp_amb,
            justificativa=self.justificativa_var.get().strip(),
            log_dir=self.log_dir_var.get().strip(),
            threads=threads,
        )

        self._append_log("Cancelamento AUTORIZADO pelo usuário. Iniciando processamento...", "INFO")
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
                self._append_log("Processo cancelado pelo usuário.", "WARN")
            else:
                total = max(event["total"], 1)
                pct = event["ok"] / total * 100
                self._append_log(
                    f"Finalizado. Sucesso={event['ok']} | Erro={event['erro']} | "
                    f"% Sucesso={pct:.2f}% | Log: {event['log_file']}", "INFO")
                messagebox.showinfo("Concluído",
                                     f"Cancelamento finalizado.\n\nSucesso: {event['ok']}\n"
                                     f"Erro: {event['erro']}\n% Sucesso: {pct:.2f}%")

    def _append_log(self, text, status):
        tag = status if status in ("OK", "INFO", "WARN", "ERROR") else "INFO"
        self.log_text.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {text}\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
