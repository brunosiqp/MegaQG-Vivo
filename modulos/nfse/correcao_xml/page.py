"""Tela da Correção de XMLs de NFSe (QG XML): pastas, correções a aplicar, progresso e log."""
import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from core import config, preferencias
from modulos.nfse.correcao_xml.correcoes import CORRECOES, CST_PADRAO
from modulos.nfse.correcao_xml.engine import (
    PASTA_CORRIGIDOS,
    PASTA_PENDENTES,
    PASTA_PENDENTES_SEM_CEP,
    CorrecaoXmlEngine,
)
from ui.theme import COLORS
from ui.widgets import ScrolledText, _open_folder, back_button, stat_box

CONTADORES = ("corrigidos", "sem_alteracao", "pendentes_cep", "pendentes_erro")


class CorrecaoXmlPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLORS["bg"])
        self.controller = controller

        self.event_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread = None

        self.entrada_var = tk.StringVar()
        self.saida_var = tk.StringVar(value=os.path.join(config.pasta_saida_padrao(), "NFSe correção de XMLs"))
        self.cst_var = tk.StringVar(value=CST_PADRAO)
        self.correcao_vars = {identificador: tk.BooleanVar(value=True) for identificador, _n, _d in CORRECOES}
        self.count_labels = {}

        back_button(self, controller, "🔧 Correção de XMLs", "corrige em lote os XMLs de DPS de uma pasta local")
        nota = tk.Label(self, text=(
            "Os arquivos da pasta de entrada não são alterados. Dentro da pasta de saída ficam: "
            f"\"{PASTA_CORRIGIDOS}\" (só as notas que mudaram), \"{PASTA_PENDENTES_SEM_CEP}\" e "
            f"\"{PASTA_PENDENTES}\" (originais para correção manual)."),
            bg=COLORS["bg"], fg=COLORS["fg_muted"], font=("Segoe UI", 8, "italic"), justify="left",
            wraplength=980)
        nota.pack(fill="x", padx=18, pady=(0, 6))
        self._build_ui()
        self._poll_queue()

    # ------------------------------------------------------------------ layout
    def _build_ui(self):
        pad = {"padx": 18, "pady": 6}

        cfg = ttk.LabelFrame(self, text="PARÂMETROS")
        cfg.pack(fill="x", **pad)
        body = tk.Frame(cfg, bg=COLORS["panel"])
        body.pack(fill="x", padx=10, pady=10)
        body.grid_columnconfigure(0, weight=1)

        for linha, (rotulo, variavel, comando) in enumerate((
                ("Pasta com os XMLs a corrigir", self.entrada_var, self._browse_entrada),
                ("Pasta de saída", self.saida_var, self._browse_saida))):
            ttk.Label(body, text=rotulo, style="PanelMuted.TLabel").grid(row=linha * 2, column=0, sticky="w")
            campo = tk.Frame(body, bg=COLORS["panel"])
            campo.grid(row=linha * 2 + 1, column=0, sticky="ew", pady=(2, 10))
            ttk.Entry(campo, textvariable=variavel).pack(side="left", fill="x", expand=True)
            ttk.Button(campo, text="Procurar...", command=comando).pack(side="left", padx=(6, 0))

        correcoes = ttk.LabelFrame(self, text="CORREÇÕES A APLICAR")
        correcoes.pack(fill="x", **pad)
        grade = tk.Frame(correcoes, bg=COLORS["panel"])
        grade.pack(fill="x", padx=10, pady=(8, 4))
        for coluna in range(2):
            grade.grid_columnconfigure(coluna, weight=1, uniform="correcao")
        metade = (len(CORRECOES) + 1) // 2
        for i, (identificador, nome, detalhe) in enumerate(CORRECOES):
            item = tk.Frame(grade, bg=COLORS["panel"])
            item.grid(row=i % metade, column=i // metade, sticky="ew", padx=(0, 16), pady=(0, 4))
            ttk.Checkbutton(item, text=f"{i + 1} · {nome}", variable=self.correcao_vars[identificador]).pack(anchor="w")
            tk.Label(item, text=detalhe, bg=COLORS["panel"], fg=COLORS["fg_muted"], font=("Segoe UI", 8),
                     anchor="w", justify="left", wraplength=470).pack(fill="x", padx=(26, 0))
        rodape = tk.Frame(correcoes, bg=COLORS["panel"])
        rodape.pack(fill="x", padx=10, pady=(4, 10))
        ttk.Label(rodape, text="CST de PIS/COFINS quando falta o CST e há base, alíquotas ou valores:",
                  style="PanelMuted.TLabel").pack(side="left")
        ttk.Entry(rodape, textvariable=self.cst_var, width=5).pack(side="left", padx=(8, 0))
        tk.Label(rodape, text="confirme conforme a tributação real da operação", bg=COLORS["panel"],
                 fg=COLORS["warning"], font=("Segoe UI", 8)).pack(side="left", padx=(10, 0))

        controls = tk.Frame(self, bg=COLORS["bg"])
        controls.pack(fill="x", **pad)
        self.start_btn = ttk.Button(controls, text="▶  Iniciar Correção", style="Cyan.TButton", command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(controls, text="■  Parar", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Abrir pasta de saída", command=self._abrir_saida).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Abrir pasta do histórico", command=self._abrir_logs).pack(side="left", padx=(8, 0))

        progress_frame = ttk.LabelFrame(self, text="PROGRESSO")
        progress_frame.pack(fill="x", **pad)
        pbody = tk.Frame(progress_frame, bg=COLORS["panel"])
        pbody.pack(fill="x", padx=10, pady=10)
        self.progress_bar = ttk.Progressbar(pbody, style="Cyan.Horizontal.TProgressbar", maximum=100, value=0)
        self.progress_bar.pack(fill="x", side="left", expand=True)
        self.progress_label = ttk.Label(pbody, text="0 / 0", style="Panel.TLabel", width=12, anchor="e")
        self.progress_label.pack(side="left", padx=(8, 0))

        stats_row = tk.Frame(progress_frame, bg=COLORS["panel"])
        stats_row.pack(fill="x", padx=10, pady=(0, 10))
        for chave, rotulo, cor in [("corrigidos", "CORRIGIDOS", COLORS["success"]),
                                   ("sem_alteracao", "SEM ALTERAÇÕES", COLORS["fg_muted"]),
                                   ("pendentes_cep", "PENDENTES SEM CEP", COLORS["warning"]),
                                   ("pendentes_erro", "PENDENTES POR ERRO", COLORS["danger"])]:
            box, val = stat_box(stats_row, rotulo, cor)
            box.pack(side="left", padx=(0, 10))
            self.count_labels[chave] = val

        log_frame = ttk.LabelFrame(self, text="LOG DE EXECUÇÃO")
        log_frame.pack(fill="both", expand=True, **pad)
        self.log_text = ScrolledText(log_frame, height=10, state="disabled", font=("Consolas", 9),
                                     bg=COLORS["card"], fg=COLORS["fg"], insertbackground=COLORS["fg"],
                                     borderwidth=0, highlightthickness=0)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
        for tag, cor in (("OK", COLORS["success"]), ("INFO", COLORS["fg_muted"]), ("WARN", COLORS["warning"]),
                         ("ERROR", COLORS["danger"])):
            self.log_text.tag_config(tag, foreground=cor)

    # -------------------------------------------------------------- ações
    def _browse_entrada(self):
        path = filedialog.askdirectory(title="Selecione a pasta com os XMLs a corrigir")
        if path:
            self.entrada_var.set(path)

    def _browse_saida(self):
        path = filedialog.askdirectory(title="Selecione a pasta de saída")
        if path:
            self.saida_var.set(path)

    def _abrir_saida(self):
        path = self.saida_var.get().strip()
        if not path or not os.path.isdir(path):
            messagebox.showwarning("Pasta não encontrada", "A pasta de saída ainda não existe.")
            return
        _open_folder(path)

    def _abrir_logs(self):
        if not os.path.exists(config.log_dir()):
            messagebox.showwarning("Pasta não encontrada", "A pasta de log ainda não existe.")
            return
        _open_folder(config.log_dir())

    def _start(self):
        entrada, saida = self.entrada_var.get().strip(), self.saida_var.get().strip()
        if not entrada or not os.path.isdir(entrada):
            messagebox.showwarning("Pasta inválida", "Selecione uma pasta válida contendo os XMLs.")
            return
        if not saida:
            messagebox.showwarning("Pasta de saída não definida", "Escolha a pasta onde os resultados serão salvos.")
            return
        escolhidas = [identificador for identificador, variavel in self.correcao_vars.items() if variavel.get()]
        if not escolhidas:
            messagebox.showwarning("Nenhuma correção", "Marque pelo menos uma correção.")
            return
        cst = self.cst_var.get().strip()
        if "piscofins" in escolhidas and not (cst.isdigit() and 1 <= len(cst) <= 2):
            messagebox.showwarning("CST inválido", "Informe o CST de PIS/COFINS com até dois dígitos (ex.: 01).")
            return

        self.stop_event = threading.Event()
        for chave in CONTADORES:
            self.count_labels[chave]["text"] = "0"
        self.progress_bar["value"] = 0
        self.progress_bar["maximum"] = 100
        self.progress_label["text"] = "0 / 0"
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.start_btn["state"] = "disabled"
        self.stop_btn["state"] = "normal"

        engine = CorrecaoXmlEngine(
            self.event_queue, self.stop_event, pasta_entrada=entrada, pasta_saida=saida,
            log_dir=config.log_dir(), dados_dir=os.path.dirname(preferencias.caminho()),
            correcoes=escolhidas, cst_padrao=cst)
        self.worker_thread = threading.Thread(target=engine.run, daemon=True)
        self.worker_thread.start()

    def _stop(self):
        self.stop_event.set()
        self.stop_btn["state"] = "disabled"
        self._append_log("Parada solicitada: o arquivo em andamento termina e os próximos não são processados.",
                         "INFO")

    # -------------------------------------------------------------- eventos
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
            self.progress_bar["maximum"] = max(event["n"], 1)
            self.progress_label["text"] = f"0 / {event['n']}"
        elif kind == "counts":
            for chave in CONTADORES:
                self.count_labels[chave]["text"] = str(event[chave])
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
            pendentes = event["pendentes_cep"] + event["pendentes_erro"]
            self._append_log(
                f"{'Parado' if event['cancelled'] else 'Finalizado'} em {event['duracao']}. "
                f"Processados={event['processados']} de {event['total']} | Corrigidos={event['corrigidos']} | "
                f"Sem alterações={event['sem_alteracao']} | Pendentes={pendentes} | Histórico: {event['historico']}",
                "INFO")
            if event["cancelled"]:
                return
            msg = (f"Correção finalizada.\n\nTotal: {event['total']}\nCorrigidos: {event['corrigidos']}\n"
                   f"Sem alterações: {event['sem_alteracao']}\nPendentes sem CEP: {event['pendentes_cep']}\n"
                   f"Pendentes por erro: {event['pendentes_erro']}\n\nResultados em:\n{event['pasta']}")
            if pendentes:
                messagebox.showwarning("Concluído com pendentes", msg)
            else:
                messagebox.showinfo("Concluído", msg)

    def _append_log(self, text, status):
        tag = status if status in ("OK", "INFO", "WARN", "ERROR") else "INFO"
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{datetime.now():%H:%M:%S}] {text}\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
