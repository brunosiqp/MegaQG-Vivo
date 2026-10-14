"""
Tela do piloto NFCe: Retorno de Contingência. Uma tela só para os dois retornos; o operador
escolhe se grava Retorno Cupom (autorizada) ou Retorno de Rejeitados.

O tipo não tem padrão: precisa ser escolhido antes da prévia, e a tela inteira (faixa, etapas,
botão de gravar, barra) assume a cor do tipo escolhido. Trocar o tipo descarta a prévia.

Etapas visíveis no topo e uma ação por etapa: o operador só consegue simular ou gravar
depois de ver a prévia, e a gravação pede confirmação mostrando tipo, ambiente e quantidade.
"""
import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from core import config
from modulos.nfce.retorno_contingencia.engine import (
    IND_ACAO,
    TIPOS,
    RetornoContingenciaEngine,
    dsc_param_sufixo,
)
from ui.theme import COLORS, escala, misturar, sobre
from ui.widgets import ScrolledText, _open_folder, back_button, centralizar, stat_box

ETAPAS = ["Tipo e arquivo", "Prévia no banco", "Confirmação", "Execução", "Resultado"]

# Aparência de cada tipo de retorno (cor = chave de COLORS e prefixo dos estilos ttk)
VISUAL = {
    "autorizada": {"icone": "✅", "cor": "success", "estilo": "Success", "nome": "Retorno Cupom"},
    "rejeitada": {"icone": "⛔", "cor": "warning", "estilo": "Warning", "nome": "Retorno de Rejeitados"},
}
COR_SEM_TIPO = "teal"  # cor da área NFCe, enquanto o tipo não foi escolhido


class RetornoContingenciaPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLORS["bg"])
        self.controller = controller
        self.tipo = None  # "autorizada" | "rejeitada": escolhido pelo operador, sem padrão
        self.event_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.engine = None
        self.etapa = 0
        self.ocupado = False  # True enquanto a prévia ou a gravação roda (controlado pelos eventos)
        self.pasta_resultado = None

        self.arquivo_var = tk.StringVar()
        self.saida_var = tk.StringVar(value=os.path.join(config.pasta_saida_padrao(), "NFCe retornos"))
        self.trava_var = tk.BooleanVar(value=True)
        self.count_labels = {}
        self.opcoes = {}

        back_button(self, controller, "🧾 Retorno de Contingência NFCe",
                    "grava comandos na COMANDO_NFEPACK a partir de um .txt de chaves")
        self._faixa_identificacao()
        self._etapas()
        self._build_ui()
        self.controller.ambiente_var.trace_add("write", lambda *_: self._ambiente_mudou())
        self._aplicar_tipo()
        self._poll_queue()

    @property
    def cor(self):
        return COLORS[VISUAL[self.tipo]["cor"] if self.tipo else COR_SEM_TIPO]

    # ------------------------------------------------------------------ layout
    def _faixa_identificacao(self):
        """O que esta tela grava, sempre visível (na cor do tipo escolhido, sem alarme)."""
        self.faixa = tk.Frame(self, highlightthickness=1)
        self.faixa.pack(fill="x", padx=18, pady=(2, 8))
        self.faixa_lbl = tk.Label(self.faixa, fg=COLORS["fg"], font=("Segoe UI", 9), justify="left", anchor="w",
                                  text="")
        self.faixa_lbl.pack(fill="x", padx=12, pady=8)

    def _atualizar_faixa(self):
        fundo = misturar(self.cor, COLORS["bg"], 0.12)
        self.faixa.configure(bg=fundo, highlightbackground=misturar(self.cor, COLORS["bg"], 0.4))
        self.faixa_lbl.configure(bg=fundo)
        ambiente = self.controller.ambiente_var.get()
        base = config.obter("nfce_db_database_" + ("prd" if ambiente == config.AMBIENTE_PRD else "hml")) \
            or "não configurada"
        if self.tipo:
            tipo = TIPOS[self.tipo]
            texto = (
                f"Grava em COMANDO_NFEPACK:  IND_ACAO = {IND_ACAO}  ·  STATUS_COMAND = 0  ·  "
                f"DSC_PARAM = <NUM_SEQ_NFE>{dsc_param_sufixo(self.tipo)}\n"
                f"Origem: INTERF_NFE com IND_TIPO_PROCES = 'E'  ·  status esperado: IND_STATUS_NFE = "
                f"{tipo['status_nfe']} ({tipo['rotulo'].lower()})"
            )
        else:
            texto = (
                "Escolha abaixo o tipo de retorno: Autorizada (Retorno Cupom) ou Rejeitada (Retorno de "
                "Rejeitados).\nO comando gravado na COMANDO_NFEPACK e o status esperado da nota dependem "
                "dessa escolha."
            )
        self.faixa_lbl.configure(text=f"{texto}\nBase: {base}  ·  Ambiente: {ambiente}")

    def _etapas(self):
        linha = tk.Frame(self, bg=COLORS["bg"])
        linha.pack(fill="x", padx=18, pady=(0, 6))
        self.etapa_lbls = []
        for i, nome in enumerate(ETAPAS):
            if i:
                tk.Label(linha, text="──", bg=COLORS["bg"], fg=COLORS["card_border"],
                         font=("Segoe UI", 9)).pack(side="left", padx=4)
            lbl = tk.Label(linha, text=f" {i + 1}  {nome} ", bg=COLORS["card"], fg=COLORS["fg_muted"],
                           font=("Segoe UI", 9, "bold"), padx=8, pady=3)
            lbl.pack(side="left")
            self.etapa_lbls.append(lbl)

    def _build_ui(self):
        pad = {"padx": 18, "pady": 6}
        cfg = ttk.LabelFrame(self, text="1 · TIPO DE RETORNO E ARQUIVO DE CHAVES")
        cfg.pack(fill="x", **pad)
        body = tk.Frame(cfg, bg=COLORS["panel"])
        body.pack(fill="x", padx=10, pady=10)
        body.grid_columnconfigure(0, weight=1)

        ttk.Label(body, text="Tipo de retorno a gravar (escolha um)", style="PanelMuted.TLabel").grid(
            row=0, column=0, sticky="w")
        opcoes = tk.Frame(body, bg=COLORS["panel"])
        opcoes.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        for coluna, tipo in enumerate(TIPOS):
            opcoes.grid_columnconfigure(coluna, weight=1, uniform="tipo")
            cartao = tk.Frame(opcoes, cursor="hand2", highlightthickness=1)
            cartao.grid(row=0, column=coluna, sticky="ew", padx=(0, 8) if coluna == 0 else 0)
            titulo = tk.Label(cartao, font=("Segoe UI", 11, "bold"), anchor="w", cursor="hand2")
            titulo.pack(fill="x", padx=12, pady=(8, 0))
            detalhe = tk.Label(cartao, font=("Segoe UI", 8), anchor="w", cursor="hand2",
                               text=f"DSC_PARAM {TIPOS[tipo]['dsc']}  ·  IND_STATUS_NFE = "
                                    f"{TIPOS[tipo]['status_nfe']}")
            detalhe.pack(fill="x", padx=12, pady=(0, 8))
            for widget in (cartao, titulo, detalhe):
                widget.bind("<Button-1>", lambda _e, t=tipo: self._escolher_tipo(t))
            self.opcoes[tipo] = (cartao, titulo, detalhe)

        ttk.Label(body, text="Arquivo .txt com um A_ID (chave da nota, 44 dígitos) por linha",
                  style="PanelMuted.TLabel").grid(row=2, column=0, sticky="w")
        linha = tk.Frame(body, bg=COLORS["panel"])
        linha.grid(row=3, column=0, sticky="ew", pady=(2, 10))
        ttk.Entry(linha, textvariable=self.arquivo_var).pack(side="left", fill="x", expand=True)
        ttk.Button(linha, text="Procurar...", command=self._browse_arquivo).pack(side="left", padx=(6, 0))

        ttk.Label(body, text="Pasta onde salvar o resultado (listas de chaves e resumo)",
                  style="PanelMuted.TLabel").grid(row=4, column=0, sticky="w")
        linha = tk.Frame(body, bg=COLORS["panel"])
        linha.grid(row=5, column=0, sticky="ew", pady=(2, 10))
        ttk.Entry(linha, textvariable=self.saida_var).pack(side="left", fill="x", expand=True)
        ttk.Button(linha, text="Procurar...", command=self._browse_saida).pack(side="left", padx=(6, 0))

        self.trava_chk = ttk.Checkbutton(body, variable=self.trava_var, command=self._invalidar_previa)
        self.trava_chk.grid(row=6, column=0, sticky="w")

        acoes = tk.Frame(self, bg=COLORS["bg"])
        acoes.pack(fill="x", **pad)
        self.previa_btn = ttk.Button(acoes, text="🔎  Validar e consultar prévia", style="Accent.TButton",
                                     command=self._previa)
        self.previa_btn.pack(side="left")
        self.simular_btn = ttk.Button(acoes, text="Simular (sem gravar)", command=lambda: self._confirmar(True))
        self.simular_btn.pack(side="left", padx=(8, 0))
        self.gravar_btn = ttk.Button(acoes, text="Gravar comandos", command=lambda: self._confirmar(False))
        self.gravar_btn.pack(side="left", padx=(8, 0))
        self.parar_btn = ttk.Button(acoes, text="■  Parar", command=self._parar)
        self.parar_btn.pack(side="left", padx=(8, 0))
        self.resultado_btn = ttk.Button(acoes, text="Abrir pasta do resultado", command=self._abrir_resultado)
        self.resultado_btn.pack(side="left", padx=(8, 0))

        previa = ttk.LabelFrame(self, text="2 · PRÉVIA NO BANCO (SOMENTE LEITURA)")
        previa.pack(fill="x", **pad)
        linha = tk.Frame(previa, bg=COLORS["panel"])
        linha.pack(fill="x", padx=10, pady=10)
        for chave, rotulo, cor in [("SERA_INSERIDA", "SERÃO INSERIDAS", COLORS["success"]),
                                   ("NAO_ENCONTRADA", "NÃO ENCONTRADAS", COLORS["fg_muted"]),
                                   ("STATUS_DIVERGENTE", "STATUS DIVERGENTE", COLORS["warning"]),
                                   ("JA_PENDENTE", "JÁ PENDENTES", COLORS["blue"]),
                                   ("invalidas", "INVÁLIDAS", COLORS["warning"]),
                                   ("duplicadas", "REPETIDAS NO ARQUIVO", COLORS["fg_muted"])]:
            box, val = stat_box(linha, rotulo, cor)
            box.pack(side="left", padx=(0, 8))
            self.count_labels[chave] = val

        execucao = ttk.LabelFrame(self, text="3 · EXECUÇÃO")
        execucao.pack(fill="x", **pad)
        corpo = tk.Frame(execucao, bg=COLORS["panel"])
        corpo.pack(fill="x", padx=10, pady=10)
        self.barra = ttk.Progressbar(corpo, maximum=1, value=0)
        self.barra.pack(fill="x", side="left", expand=True)
        self.barra_lbl = ttk.Label(corpo, text="0 / 0", style="Panel.TLabel", width=12, anchor="e")
        self.barra_lbl.pack(side="left", padx=(8, 0))
        linha = tk.Frame(execucao, bg=COLORS["panel"])
        linha.pack(fill="x", padx=10, pady=(0, 10))
        for chave, rotulo, cor in [("gravadas", "COMANDOS GRAVADOS", self.cor), ("erro", "CHAVES COM ERRO",
                                                                                   COLORS["danger"])]:
            box, val = stat_box(linha, rotulo, cor)
            box.pack(side="left", padx=(0, 8))
            self.count_labels[chave] = val
        self.modo_lbl = tk.Label(linha, text="", bg=COLORS["panel"], fg=COLORS["warning"],
                                 font=("Segoe UI", 10, "bold"))
        self.modo_lbl.pack(side="left", padx=(12, 0))

        log = ttk.LabelFrame(self, text="LOG DE EXECUÇÃO")
        log.pack(fill="both", expand=True, **pad)
        self.log_text = ScrolledText(log, height=8, state="disabled", font=("Consolas", 9), bg=COLORS["card"],
                                     fg=COLORS["fg"], insertbackground=COLORS["fg"], borderwidth=0,
                                     highlightthickness=0)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
        for tag, cor in (("OK", COLORS["success"]), ("INFO", COLORS["fg_muted"]), ("WARN", COLORS["warning"]),
                         ("ERROR", COLORS["danger"])):
            self.log_text.tag_config(tag, foreground=cor)

    # ---------------------------------------------------------- tipo de retorno
    def _escolher_tipo(self, tipo):
        if tipo == self.tipo:
            return
        if self.ocupado:
            self._append_log("Espere a operação terminar para trocar o tipo de retorno.", "WARN")
            return
        self.tipo = tipo
        self._append_log(f"Tipo de retorno: {TIPOS[tipo]['rotulo'].upper()} ({VISUAL[tipo]['nome']}).", "INFO")
        self._aplicar_tipo()
        self._invalidar_previa()

    def _aplicar_tipo(self):
        """Pinta a tela com a cor do tipo escolhido (ou a cor da área NFCe, sem tipo)."""
        for tipo, (cartao, titulo, detalhe) in self.opcoes.items():
            visual = VISUAL[tipo]
            cor = COLORS[visual["cor"]]
            marcado = tipo == self.tipo
            fundo = misturar(cor, COLORS["panel"], 0.16) if marcado else COLORS["card"]
            borda = cor if marcado else COLORS["card_border"]
            cartao.configure(bg=fundo, highlightbackground=borda, highlightcolor=borda)
            titulo.configure(bg=fundo, fg=cor if marcado else COLORS["fg"],
                             text=f"{'●' if marcado else '○'}  {visual['icone']}  {TIPOS[tipo]['rotulo']}"
                                  f"  ·  {visual['nome']}")
            detalhe.configure(bg=fundo, fg=COLORS["fg"] if marcado else COLORS["fg_muted"])
        if self.tipo:
            estilo = VISUAL[self.tipo]["estilo"]
            self.gravar_btn.configure(style=f"{estilo}.TButton")
            self.barra.configure(style=f"{estilo}.Horizontal.TProgressbar")
            self.trava_chk.configure(text=f"Gravar só notas com IND_STATUS_NFE = {TIPOS[self.tipo]['status_nfe']} "
                                          f"({TIPOS[self.tipo]['rotulo'].lower()}) — recomendado")
        else:
            self.gravar_btn.configure(style="TButton")
            self.barra.configure(style="Teal.Horizontal.TProgressbar")
            self.trava_chk.configure(text="Gravar só notas com o status esperado do tipo escolhido — recomendado")
        self.count_labels["gravadas"].configure(fg=self.cor)
        self._atualizar_faixa()
        self._ir_para(self.etapa)

    # -------------------------------------------------------------- etapas
    def _ir_para(self, etapa):
        """Atualiza o indicador de etapas e quais botões ficam habilitados."""
        self.etapa = etapa
        for i, lbl in enumerate(self.etapa_lbls):
            if i < etapa:
                lbl.configure(bg=misturar(self.cor, COLORS["card"], 0.18), fg=self.cor)
            elif i == etapa:
                lbl.configure(bg=self.cor, fg=sobre(self.cor))
            else:
                lbl.configure(bg=COLORS["card"], fg=COLORS["fg_muted"])
        rodando = self.ocupado
        tem_previa = self.engine is not None and bool(self.engine.lista("SERA_INSERIDA"))
        self.previa_btn.configure(state="disabled" if rodando else "normal")
        for btn in (self.simular_btn, self.gravar_btn):
            btn.configure(state="normal" if (tem_previa and not rodando and etapa >= 1) else "disabled")
        self.parar_btn.configure(state="normal" if rodando and etapa == 3 else "disabled")
        self.resultado_btn.configure(state="normal" if self.pasta_resultado else "disabled")
        if tem_previa:
            n = self.engine.lista("SERA_INSERIDA")
            self.gravar_btn.configure(text=f"Gravar comandos ({len(n)} chave(s))")
        else:
            self.gravar_btn.configure(text="Gravar comandos")

    def _invalidar_previa(self):
        """Mudou algo que afeta a prévia (tipo, arquivo, trava, ambiente): precisa consultar de novo."""
        if self.engine is not None and not self.ocupado:
            self.engine = None
            for chave in ("SERA_INSERIDA", "NAO_ENCONTRADA", "STATUS_DIVERGENTE", "JA_PENDENTE",
                          "invalidas", "duplicadas"):
                self.count_labels[chave]["text"] = "0"
            self._append_log("Parâmetros mudaram: consulte a prévia de novo antes de gravar.", "WARN")
            self._ir_para(0)

    def _ambiente_mudou(self):
        self._atualizar_faixa()
        self._invalidar_previa()

    # -------------------------------------------------------------- ações
    def _browse_arquivo(self):
        path = filedialog.askopenfilename(title="Selecione o .txt com as chaves (A_ID)",
                                          filetypes=[("Arquivo de texto", "*.txt"), ("Todos", "*.*")])
        if path:
            self.arquivo_var.set(path)
            self._invalidar_previa()

    def _browse_saida(self):
        path = filedialog.askdirectory(title="Pasta para o resultado")
        if path:
            self.saida_var.set(path)

    def _abrir_resultado(self):
        if self.pasta_resultado and os.path.isdir(self.pasta_resultado):
            _open_folder(self.pasta_resultado)

    def _novo_engine(self):
        return RetornoContingenciaEngine(
            self.event_queue, self.stop_event, tipo=self.tipo, ambiente=self.controller.ambiente_var.get(),
            exigir_status=self.trava_var.get(), log_dir=config.log_dir())

    def _previa(self):
        if self.tipo is None:
            messagebox.showwarning("Escolha o tipo de retorno",
                                   "Escolha se o retorno é de notas AUTORIZADAS (Retorno Cupom) ou REJEITADAS "
                                   "(Retorno de Rejeitados) antes de consultar a prévia.")
            return
        arquivo = self.arquivo_var.get().strip()
        if not arquivo or not os.path.isfile(arquivo):
            messagebox.showwarning("Arquivo inválido", "Selecione o .txt com as chaves (A_ID).")
            return
        self.stop_event = threading.Event()
        self.engine = self._novo_engine()
        self._limpar_log()
        self._append_log(f"Tipo de retorno: {TIPOS[self.tipo]['rotulo'].upper()} ({VISUAL[self.tipo]['nome']}).",
                         "INFO")
        self.ocupado = True
        self.worker_thread = threading.Thread(target=self.engine.previa, args=(arquivo,), daemon=True)
        self.worker_thread.start()
        self._ir_para(1)

    def _confirmar(self, simular):
        chaves = self.engine.lista("SERA_INSERIDA")
        self._ir_para(2)
        if simular:
            texto = (f"Simular o retorno de {len(chaves)} chave(s) como {TIPOS[self.tipo]['rotulo'].upper()}?\n\n"
                     "O INSERT é executado e desfeito em seguida (ROLLBACK): nada fica gravado.")
            if messagebox.askyesno("Simular", texto):
                self._executar(True)
            else:
                self._ir_para(1)
            return
        if self._modal_gravar(len(chaves)):
            self._executar(False)
        else:
            self._append_log("Gravação não autorizada pelo usuário.", "WARN")
            self._ir_para(1)

    def _modal_gravar(self, n):
        k = escala(self)
        modal = tk.Toplevel(self)
        modal.title("Confirmar gravação")
        fundo = misturar(self.cor, COLORS["bg"], 0.10)
        modal.configure(bg=fundo)
        modal.resizable(False, False)
        modal.transient(self.winfo_toplevel())
        centralizar(modal, int(620 * k), int(380 * k))
        modal.grab_set()
        tk.Frame(modal, bg=self.cor, height=5).pack(fill="x")
        corpo = tk.Frame(modal, bg=fundo)
        corpo.pack(fill="both", expand=True, padx=26, pady=20)
        ambiente = self.controller.ambiente_var.get()
        tk.Label(corpo, text=f"Gravar {n} comando(s) — {TIPOS[self.tipo]['rotulo']}", bg=fundo, fg=self.cor,
                 font=("Segoe UI", 15, "bold")).pack(anchor="w")
        texto = (
            f"Tipo de retorno: {TIPOS[self.tipo]['rotulo'].upper()} ({VISUAL[self.tipo]['nome']})\n"
            f"Ambiente: {ambiente.upper()}\n"
            f"Arquivo: {os.path.basename(self.arquivo_var.get())}\n"
            f"Tabela: COMANDO_NFEPACK  ·  IND_ACAO {IND_ACAO}  ·  DSC_PARAM <NUM_SEQ_NFE>{dsc_param_sufixo(self.tipo)}\n\n"
            "Os comandos serão processados pelo NFePack. Confira a prévia antes de continuar."
        )
        tk.Label(corpo, text=texto, bg=fundo, fg=COLORS["fg"], font=("Segoe UI", 10), justify="left",
                 wraplength=int(560 * k)).pack(anchor="w", pady=(12, 16))
        resultado = {"ok": False}
        botoes = tk.Frame(corpo, bg=fundo)
        botoes.pack(fill="x", side="bottom")

        def fechar(ok):
            resultado["ok"] = ok
            modal.destroy()

        ttk.Button(botoes, text="Voltar", command=lambda: fechar(False)).pack(side="left")
        ttk.Button(botoes, text=f"Gravar {n} comando(s)", style=f"{VISUAL[self.tipo]['estilo']}.TButton",
                   command=lambda: fechar(True)).pack(side="right")
        modal.protocol("WM_DELETE_WINDOW", lambda: fechar(False))
        self.wait_window(modal)
        return resultado["ok"]

    def _executar(self, simular):
        pasta = self.saida_var.get().strip()
        if not pasta:
            messagebox.showwarning("Pasta obrigatória", "Escolha a pasta para o resultado.")
            self._ir_para(1)
            return
        self.stop_event.clear()
        self.count_labels["gravadas"]["text"] = "0"
        self.count_labels["erro"]["text"] = "0"
        self.modo_lbl.configure(text="SIMULAÇÃO — nada será gravado" if simular else "")
        self.ocupado = True
        self.worker_thread = threading.Thread(target=self.engine.gravar, args=(simular, pasta), daemon=True)
        self.worker_thread.start()
        self._ir_para(3)

    def _parar(self):
        self.stop_event.set()
        self.parar_btn.configure(state="disabled")
        self._append_log("Parada solicitada: o bloco em andamento termina e os próximos não são executados.", "WARN")

    # -------------------------------------------------------------- eventos
    def _poll_queue(self):
        try:
            while True:
                self._evento(self.event_queue.get_nowait())
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)

    def _evento(self, e):
        kind = e["kind"]
        if kind == "log_line":
            self._append_log(e["text"], e["status"])
        elif kind == "previa":
            for chave in ("SERA_INSERIDA", "NAO_ENCONTRADA", "STATUS_DIVERGENTE", "JA_PENDENTE", "invalidas",
                          "duplicadas"):
                self.count_labels[chave]["text"] = str(e[chave])
            self.ocupado = False
            self._ir_para(1)
        elif kind == "total_itens":
            self.barra.configure(maximum=max(e["n"], 1), value=0)
            self.barra_lbl["text"] = f"0 / {e['n']}"
        elif kind == "counts":
            self.barra.configure(value=e["done"])
            self.barra_lbl["text"] = f"{e['done']} / {e['total']}"
            self.count_labels["gravadas"]["text"] = str(e["inseridas"])
            self.count_labels["erro"]["text"] = str(e["erro"])
        elif kind == "done":
            self.pasta_resultado = e["pasta"]
            self.ocupado = False
            self._ir_para(4)
            verbo = "seriam gravados" if e["simular"] else "gravados"
            msg = f"{e['inseridas']} comando(s) {verbo}.\nChaves com erro: {e['erro']}.\n\nResultado em:\n{e['pasta']}"
            if e["erro"]:
                messagebox.showwarning("Concluído com erros", msg)
            else:
                messagebox.showinfo("Simulação concluída" if e["simular"] else "Gravação concluída", msg)
        elif kind == "fatal_error":
            self.ocupado = False
            self._ir_para(0 if self.engine is None or not self.engine.situacoes else 1)
            messagebox.showerror("Erro", e["text"])

    def _limpar_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _append_log(self, text, status):
        tag = status if status in ("OK", "INFO", "WARN", "ERROR") else "INFO"
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{datetime.now():%H:%M:%S}] {text}\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
