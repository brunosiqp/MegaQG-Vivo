"""
Tela do Reprocessamento de documentos NFCe (mesmo desenho do Retorno de Contingência).

Etapas visíveis no topo e uma ação por etapa: o operador só consegue simular ou reprocessar
depois de ver a prévia, e o reprocessamento pede confirmação mostrando ambiente e quantidade.
"""
import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from core import config
from modulos.nfce.reprocessamento.engine import (
    STATUS_AUTORIZADA,
    STATUS_REPROCESSAR,
    ReprocessamentoNfceEngine,
)
from ui.theme import COLORS, escala, misturar, sobre
from ui.widgets import ScrolledText, _open_folder, back_button, centralizar, stat_box

ETAPAS = ["Arquivo", "Prévia no banco", "Confirmação", "Execução", "Resultado"]
PREVIA = ("SERA_REPROCESSADA", "NAO_ENCONTRADA", "JA_AUTORIZADA", "invalidas", "duplicadas")
EXECUCAO = ("baixados", "atualizadas", "enviadas", "erro")


class ReprocessamentoNfcePage(tk.Frame):
    COR = "indigo"

    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLORS["bg"])
        self.controller = controller
        self.cor = COLORS[self.COR]
        self.event_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.engine = None
        self.etapa = 0
        self.ocupado = False  # True enquanto a prévia ou o reprocessamento roda (controlado pelos eventos)
        self.pasta_resultado = None

        self.arquivo_var = tk.StringVar()
        self.saida_var = tk.StringVar(value=os.path.join(config.pasta_saida_padrao(), "NFCe reprocessamento"))
        self.pular_var = tk.BooleanVar(value=True)
        self.count_labels = {}

        back_button(self, controller, "♻️ Reprocessamento NFCe",
                    "baixa o XML, muda o status da nota e reenvia, a partir de um .txt de chaves")
        self._faixa_identificacao()
        self._etapas()
        self._build_ui()
        self.controller.ambiente_var.trace_add("write", lambda *_: self._ambiente_mudou())
        self._ir_para(0)
        self._poll_queue()

    # ------------------------------------------------------------------ layout
    def _faixa_identificacao(self):
        """O que esta tela altera, sempre visível."""
        fundo = misturar(self.cor, COLORS["bg"], 0.12)
        faixa = tk.Frame(self, bg=fundo, highlightthickness=1, highlightbackground=misturar(self.cor, COLORS["bg"], 0.4))
        faixa.pack(fill="x", padx=18, pady=(2, 8))
        self.faixa_lbl = tk.Label(faixa, bg=fundo, fg=COLORS["fg"], font=("Segoe UI", 9), justify="left",
                                  anchor="w", text="")
        self.faixa_lbl.pack(fill="x", padx=12, pady=8)
        self._atualizar_faixa()

    def _atualizar_faixa(self):
        ambiente = self.controller.ambiente_var.get()
        base = config.obter("nfce_db_database_" + ("prd" if ambiente == config.AMBIENTE_PRD else "hml")) \
            or "não configurada"
        self.faixa_lbl.configure(text=(
            f"Para cada chave (A_ID):  1) baixa o XML de emissão  ·  2) localiza o NUM_SEQ_NFE e grava "
            f"IND_STATUS_NFE = {STATUS_REPROCESSAR} em INTERF_NFE  ·  3) envia o XML completo (<NFe>) para a recepção\n"
            f"O status só é alterado para as notas cujo XML foi baixado. Origem: INTERF_NFE com IND_TIPO_PROCES = 'E'\n"
            f"Base: {base}  ·  Ambiente: {ambiente}"))

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
        cfg = ttk.LabelFrame(self, text="1 · ARQUIVO DE CHAVES")
        cfg.pack(fill="x", **pad)
        body = tk.Frame(cfg, bg=COLORS["panel"])
        body.pack(fill="x", padx=10, pady=10)
        body.grid_columnconfigure(0, weight=1)

        ttk.Label(body, text="Arquivo .txt com um A_ID (chave da nota, 44 dígitos) por linha",
                  style="PanelMuted.TLabel").grid(row=0, column=0, sticky="w")
        linha = tk.Frame(body, bg=COLORS["panel"])
        linha.grid(row=1, column=0, sticky="ew", pady=(2, 10))
        ttk.Entry(linha, textvariable=self.arquivo_var).pack(side="left", fill="x", expand=True)
        ttk.Button(linha, text="Procurar...", command=self._browse_arquivo).pack(side="left", padx=(6, 0))

        ttk.Label(body, text="Pasta onde salvar o resultado (XMLs enviados, retornos, listas de chaves e resumo)",
                  style="PanelMuted.TLabel").grid(row=2, column=0, sticky="w")
        linha = tk.Frame(body, bg=COLORS["panel"])
        linha.grid(row=3, column=0, sticky="ew", pady=(2, 10))
        ttk.Entry(linha, textvariable=self.saida_var).pack(side="left", fill="x", expand=True)
        ttk.Button(linha, text="Procurar...", command=self._browse_saida).pack(side="left", padx=(6, 0))

        ttk.Checkbutton(body, variable=self.pular_var, command=self._invalidar_previa,
                        text=f"Não reprocessar notas já autorizadas (IND_STATUS_NFE = {STATUS_AUTORIZADA}) "
                             f"— recomendado").grid(row=4, column=0, sticky="w")

        acoes = tk.Frame(self, bg=COLORS["bg"])
        acoes.pack(fill="x", **pad)
        self.previa_btn = ttk.Button(acoes, text="🔎  Validar e consultar prévia", style="Accent.TButton",
                                     command=self._previa)
        self.previa_btn.pack(side="left")
        self.simular_btn = ttk.Button(acoes, text="Simular (sem gravar nem enviar)",
                                      command=lambda: self._confirmar(True))
        self.simular_btn.pack(side="left", padx=(8, 0))
        self.executar_btn = ttk.Button(acoes, text="Reprocessar", style="Indigo.TButton",
                                       command=lambda: self._confirmar(False))
        self.executar_btn.pack(side="left", padx=(8, 0))
        self.parar_btn = ttk.Button(acoes, text="■  Parar", command=self._parar)
        self.parar_btn.pack(side="left", padx=(8, 0))
        self.resultado_btn = ttk.Button(acoes, text="Abrir pasta do resultado", command=self._abrir_resultado)
        self.resultado_btn.pack(side="left", padx=(8, 0))

        previa = ttk.LabelFrame(self, text="2 · PRÉVIA NO BANCO (SOMENTE LEITURA)")
        previa.pack(fill="x", **pad)
        linha = tk.Frame(previa, bg=COLORS["panel"])
        linha.pack(fill="x", padx=10, pady=10)
        for chave, rotulo, cor in [("SERA_REPROCESSADA", "SERÃO REPROCESSADAS", COLORS["success"]),
                                   ("NAO_ENCONTRADA", "NÃO ENCONTRADAS", COLORS["fg_muted"]),
                                   ("JA_AUTORIZADA", "JÁ AUTORIZADAS (PULADAS)", COLORS["blue"]),
                                   ("invalidas", "INVÁLIDAS", COLORS["warning"]),
                                   ("duplicadas", "REPETIDAS NO ARQUIVO", COLORS["fg_muted"])]:
            box, val = stat_box(linha, rotulo, cor)
            box.pack(side="left", padx=(0, 8))
            self.count_labels[chave] = val

        execucao = ttk.LabelFrame(self, text="3 · EXECUÇÃO")
        execucao.pack(fill="x", **pad)
        corpo = tk.Frame(execucao, bg=COLORS["panel"])
        corpo.pack(fill="x", padx=10, pady=10)
        self.barra = ttk.Progressbar(corpo, style="Indigo.Horizontal.TProgressbar", maximum=1, value=0)
        self.barra.pack(fill="x", side="left", expand=True)
        self.barra_lbl = ttk.Label(corpo, text="0 / 0", style="Panel.TLabel", width=12, anchor="e")
        self.barra_lbl.pack(side="left", padx=(8, 0))
        linha = tk.Frame(execucao, bg=COLORS["panel"])
        linha.pack(fill="x", padx=10, pady=(0, 10))
        for chave, rotulo, cor in [("baixados", "XMLS BAIXADOS", COLORS["cyan"]),
                                   ("atualizadas", f"LINHAS COM STATUS {STATUS_REPROCESSAR}", self.cor),
                                   ("enviadas", "ENVIADAS (HTTP 2XX)", COLORS["success"]),
                                   ("erro", "CHAVES COM ERRO", COLORS["danger"])]:
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
        chaves = self.engine.lista("SERA_REPROCESSADA") if self.engine is not None else []
        self.previa_btn.configure(state="disabled" if rodando else "normal")
        for btn in (self.simular_btn, self.executar_btn):
            btn.configure(state="normal" if (chaves and not rodando and etapa >= 1) else "disabled")
        self.parar_btn.configure(state="normal" if rodando and etapa == 3 else "disabled")
        self.resultado_btn.configure(state="normal" if self.pasta_resultado else "disabled")
        self.executar_btn.configure(text=f"Reprocessar ({len(chaves)} chave(s))" if chaves else "Reprocessar")

    def _invalidar_previa(self):
        """Mudou algo que afeta a prévia (arquivo, opção, ambiente): precisa consultar de novo."""
        if self.engine is not None and not self.ocupado:
            self.engine = None
            for chave in PREVIA:
                self.count_labels[chave]["text"] = "0"
            self._append_log("Parâmetros mudaram: consulte a prévia de novo antes de reprocessar.", "WARN")
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

    def _previa(self):
        arquivo = self.arquivo_var.get().strip()
        if not arquivo or not os.path.isfile(arquivo):
            messagebox.showwarning("Arquivo inválido", "Selecione o .txt com as chaves (A_ID).")
            return
        self.stop_event = threading.Event()
        self.engine = ReprocessamentoNfceEngine(
            self.event_queue, self.stop_event, ambiente=self.controller.ambiente_var.get(),
            pular_autorizadas=self.pular_var.get(), log_dir=config.log_dir())
        self._limpar_log()
        self.ocupado = True
        self.worker_thread = threading.Thread(target=self.engine.previa, args=(arquivo,), daemon=True)
        self.worker_thread.start()
        self._ir_para(1)

    def _confirmar(self, simular):
        n = len(self.engine.lista("SERA_REPROCESSADA"))
        self._ir_para(2)
        if simular:
            texto = (f"Simular o reprocessamento de {n} chave(s)?\n\n"
                     f"Os XMLs são baixados e o UPDATE é executado e desfeito em seguida (ROLLBACK). "
                     f"Nada fica gravado e nada é enviado.")
            if messagebox.askyesno("Simular", texto):
                self._executar(True)
            else:
                self._ir_para(1)
            return
        if self._modal_confirmar(n):
            self._executar(False)
        else:
            self._append_log("Reprocessamento não autorizado pelo usuário.", "WARN")
            self._ir_para(1)

    def _modal_confirmar(self, n):
        k = escala(self)
        modal = tk.Toplevel(self)
        modal.title("Confirmar reprocessamento")
        fundo = misturar(self.cor, COLORS["bg"], 0.10)
        modal.configure(bg=fundo)
        modal.resizable(False, False)
        modal.transient(self.winfo_toplevel())
        centralizar(modal, int(640 * k), int(400 * k))
        modal.grab_set()
        tk.Frame(modal, bg=self.cor, height=5).pack(fill="x")
        corpo = tk.Frame(modal, bg=fundo)
        corpo.pack(fill="both", expand=True, padx=26, pady=20)
        ambiente = self.controller.ambiente_var.get()
        tk.Label(corpo, text=f"Reprocessar {n} nota(s) de NFCe", bg=fundo, fg=self.cor,
                 font=("Segoe UI", 15, "bold")).pack(anchor="w")
        texto = (
            f"Ambiente: {ambiente.upper()}\n"
            f"Arquivo: {os.path.basename(self.arquivo_var.get())}\n\n"
            f"Para cada nota com XML baixado, o app grava IND_STATUS_NFE = {STATUS_REPROCESSAR} em INTERF_NFE "
            f"e envia o XML completo para a recepção síncrona.\n\n"
            f"Nota com erro no envio fica com status {STATUS_REPROCESSAR} e entra em erro_envio.txt. "
            f"Confira a prévia antes de continuar."
        )
        tk.Label(corpo, text=texto, bg=fundo, fg=COLORS["fg"], font=("Segoe UI", 10), justify="left",
                 wraplength=int(580 * k)).pack(anchor="w", pady=(12, 16))
        resultado = {"ok": False}
        botoes = tk.Frame(corpo, bg=fundo)
        botoes.pack(fill="x", side="bottom")

        def fechar(ok):
            resultado["ok"] = ok
            modal.destroy()

        ttk.Button(botoes, text="Voltar", command=lambda: fechar(False)).pack(side="left")
        ttk.Button(botoes, text=f"Reprocessar {n} nota(s)", style="Indigo.TButton",
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
        for chave in EXECUCAO:
            self.count_labels[chave]["text"] = "0"
        self.modo_lbl.configure(text="SIMULAÇÃO — nada será gravado nem enviado" if simular else "")
        self.ocupado = True
        self.worker_thread = threading.Thread(target=self.engine.reprocessar, args=(simular, pasta), daemon=True)
        self.worker_thread.start()
        self._ir_para(3)

    def _parar(self):
        self.stop_event.set()
        self.parar_btn.configure(state="disabled")
        self._append_log("Parada solicitada: os envios em andamento terminam e os próximos não são feitos.", "WARN")

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
            for chave in PREVIA:
                self.count_labels[chave]["text"] = str(e[chave])
            self.ocupado = False
            self._ir_para(1)
        elif kind == "total_itens":
            self.barra.configure(maximum=max(e["n"], 1), value=0)
            self.barra_lbl["text"] = f"0 / {e['n']}"
        elif kind == "counts":
            self.barra.configure(value=e["done"])
            self.barra_lbl["text"] = f"{e['done']} / {e['total']}"
            for chave in EXECUCAO:
                self.count_labels[chave]["text"] = str(e[chave])
        elif kind == "done":
            self.pasta_resultado = e["pasta"]
            self.ocupado = False
            self._ir_para(4)
            for chave in EXECUCAO:
                self.count_labels[chave]["text"] = str(e[chave])
            if e["simular"]:
                msg = (f"Simulação: {e['baixados']} XML(s) baixado(s) e {e['atualizadas']} linha(s) seriam "
                       f"atualizadas para status {STATUS_REPROCESSAR}. Nada foi gravado nem enviado.\n"
                       f"Chaves com erro: {e['erro']}.")
            else:
                retornos = "".join(f"\n    {codigo}: {n}" for codigo, n in sorted(e["codigos"].items()))
                msg = (f"Enviadas com HTTP 2xx: {e['enviadas']}\nChaves com erro: {e['erro']}\n"
                       f"Linhas atualizadas para status {STATUS_REPROCESSAR}: {e['atualizadas']}"
                       + (f"\nCom status {STATUS_REPROCESSAR} e sem envio (parada): {e['pendentes']}"
                          if e["pendentes"] else "")
                       + (f"\n\nRetornos do envio:{retornos}" if retornos else ""))
            msg += f"\n\nResultado em:\n{e['pasta']}"
            if e["erro"] or e["pendentes"]:
                messagebox.showwarning("Concluído com pendências", msg)
            else:
                messagebox.showinfo("Simulação concluída" if e["simular"] else "Reprocessamento concluído", msg)
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
