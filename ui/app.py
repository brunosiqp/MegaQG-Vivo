"""
Janela principal do MegaQG Vivo: barra do topo (temas e ambiente global), linha fina de
ambiente, barra lateral com todas as operações (a alça no meio da borda a recolhe para só os
ícones) e a área de conteúdo, que mostra uma tela por vez (mesmo modelo de página única dos
QGs originais).

A aparência vem do tema ativo (ui/temas.py). Trocar de tema redesenha a janela inteira com as
cores novas; por isso a troca fica bloqueada enquanto uma operação roda.
"""
import os
import sys
import tkinter as tk
from tkinter import messagebox

from core import config, preferencias
from core.versao import APP_NOME, APP_VERSION
from modulos.registro import AREAS, OPERACOES, carregar_pagina, pendencias
from ui import animacao, pokemon, temas
from ui.hub import HubPage
from ui.theme import COLORS, aplicar_estilos, escala, misturar
from ui.widgets import Dica, PaginaRolavel, ativar_roda

ID_INICIO = "inicio"
LARGURA_LATERAL, LARGURA_RECOLHIDA = 250, 58


def caminho_asset(nome: str) -> str:
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(getattr(sys, "_MEIPASS", raiz), "assets", nome)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NOME} {APP_VERSION}")
        prefs = preferencias.carregar()
        temas.ativar(prefs.get("tema"), salvar=False)
        self.lateral_recolhida = bool(prefs.get("lateral_recolhida"))
        aplicar_estilos(self)
        k = escala(self)
        largura, altura = int(1360 * k), int(900 * k)
        altura = min(altura, self.winfo_screenheight() - int(60 * k))
        self.geometry(f"{min(largura, self.winfo_screenwidth())}x{altura}")
        self.minsize(int(1180 * k), int(700 * k))
        self._logo_label = None
        self._aplicar_icone()

        # Ambiente global (Produção/Homologação): todas as telas usam esta variável
        self.ambiente_var = tk.StringVar(value=config.AMBIENTE_PRD)
        self._ambiente_anterior = self.ambiente_var.get()
        self.ambiente_var.trace_add("write", lambda *_: self._ambiente_mudou())

        self.paginas = {}  # id da operação -> tela (criada na 1ª vez que é aberta)
        self._molduras = {}  # id da operação -> moldura rolável que contém a tela
        self.atual = ID_INICIO
        self._dialogo_temas = None
        self._montar()
        self.show_hub()

        ativar_roda(self)
        self.bind_all("<Control-b>", lambda _e: self.alternar_lateral())
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # --------------------------------------------------------------- estrutura
    def _montar(self):
        """Cria o topo, a linha do ambiente, a barra lateral e o hub com as cores do tema ativo."""
        k = escala(self)
        self.topo = tk.Frame(self, bg=COLORS["panel"])
        self.topo.pack(fill="x")
        self._montar_topo()
        # Indicador discreto do ambiente: linha fina na cor do ambiente, logo abaixo do topo
        self.faixa = tk.Frame(self, height=2)
        self.faixa.pack(fill="x")

        self.corpo = tk.Frame(self, bg=COLORS["bg"])
        self.corpo.pack(fill="both", expand=True)
        self.lateral = tk.Frame(self.corpo, bg=COLORS["panel"], width=int(LARGURA_LATERAL * k))
        self.lateral.pack(side="left", fill="y")
        self.lateral.pack_propagate(False)
        tk.Frame(self.corpo, bg=COLORS["card_border"], width=1).pack(side="left", fill="y")
        self.container = tk.Frame(self.corpo, bg=COLORS["bg"])
        self.container.pack(side="left", fill="both", expand=True)

        self.hub = HubPage(self.container, self)
        self.hub.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Alça no meio da borda da barra lateral: a seta recolhe ou mostra a barra
        self.alca = tk.Label(self.corpo, font=("Segoe UI", 15, "bold"), bg=COLORS["card"], fg=COLORS["fg_muted"],
                             cursor="hand2", highlightthickness=1, highlightbackground=COLORS["card_border"],
                             padx=0, pady=0, bd=0)
        self.alca.bind("<Button-1>", lambda _e: self.alternar_lateral())
        self.alca.bind("<Enter>", lambda _e: animacao.cor(self.alca, {"fg": COLORS["accent"],
                                                                      "highlightbackground": COLORS["accent"]}))
        self.alca.bind("<Leave>", lambda _e: animacao.cor(self.alca, {"fg": COLORS["fg_muted"],
                                                                      "highlightbackground": COLORS["card_border"]}))
        self._dica_alca = Dica(self.alca, "")

        self._itens_lateral = {}
        self._montar_lateral()
        self._atualizar_faixa()

    # ------------------------------------------------------------------ topo
    def _botao_topo(self, parent, texto, comando, dica=None, fonte=("Segoe UI", 10)):
        """Botão discreto do topo: só o texto, que acende na cor de destaque ao passar o mouse."""
        botao = tk.Label(parent, text=texto, bg=COLORS["panel"], fg=COLORS["fg_muted"], font=fonte,
                         cursor="hand2", padx=10, pady=6)
        botao.bind("<Button-1>", lambda _e: comando())
        botao.bind("<Enter>", lambda _e: animacao.cor(botao, {"fg": COLORS["accent"], "bg": COLORS["card"]}), add="+")
        botao.bind("<Leave>", lambda _e: animacao.cor(botao, {"fg": COLORS["fg_muted"], "bg": COLORS["panel"]}),
                   add="+")
        if dica:
            Dica(botao, dica)
        return botao

    def _montar_topo(self):
        topo = self.topo
        esquerda = tk.Frame(topo, bg=COLORS["panel"])
        esquerda.pack(side="left", padx=(16, 14), pady=7)
        try:
            self._logo = tk.PhotoImage(file=caminho_asset(self._arquivo_logo())).subsample(2)
            logo = tk.Label(esquerda, image=self._logo, bg=COLORS["panel"], cursor="hand2")
            logo.pack(side="left", padx=(0, 10))
            logo.bind("<Button-1>", lambda _e: self.show_hub())
            self._logo_label = logo
        except Exception:
            self._logo_label = None
        titulo = tk.Frame(esquerda, bg=COLORS["panel"], cursor="hand2")
        titulo.pack(side="left")
        nome = tk.Label(titulo, text=APP_NOME.upper(), bg=COLORS["panel"], fg=COLORS["fg"],
                        font=("Segoe UI Semibold", 12), cursor="hand2")
        nome.pack(anchor="w")
        sub = tk.Label(titulo, text="Central de Operações Fiscais", bg=COLORS["panel"], fg=COLORS["fg_muted"],
                       font=("Segoe UI", 8), cursor="hand2")
        sub.pack(anchor="w")
        for w in (titulo, nome, sub):
            w.bind("<Button-1>", lambda _e: self.show_hub())

        direita = tk.Frame(topo, bg=COLORS["panel"])
        direita.pack(side="right", padx=14)
        self._botao_topo(direita, "◐  Tema", self.abrir_temas, "Trocar de tema ou criar o seu").pack(
            side="left", padx=(0, 6))
        tk.Frame(direita, bg=COLORS["card_border"], width=1).pack(side="left", fill="y", pady=8, padx=(0, 14))
        textos = tk.Frame(direita, bg=COLORS["panel"])
        textos.pack(side="left", padx=(0, 10))
        tk.Label(textos, text="AMBIENTE", bg=COLORS["panel"], fg=COLORS["fg_muted"],
                 font=("Segoe UI", 7, "bold"), anchor="e").pack(anchor="e")
        self.ambiente_dica = tk.Label(textos, text="", bg=COLORS["panel"], fg=COLORS["fg_muted"],
                                      font=("Segoe UI", 8), anchor="e")
        self.ambiente_dica.pack(anchor="e")

        # Seletor de ambiente: o selecionado ganha fundo suave e texto/borda na cor do
        # ambiente (sem bloco de cor cheia, para não roubar a atenção do resto da tela)
        self._botoes_ambiente = {}
        for valor, cor, suave in ((config.AMBIENTE_PRD, COLORS["prd"], COLORS["prd_soft"]),
                                  (config.AMBIENTE_HML, COLORS["hml"], COLORS["hml_soft"])):
            botao = tk.Label(direita, text=valor, font=("Segoe UI", 9, "bold"), padx=12, pady=5,
                             width=13, cursor="hand2", highlightthickness=1)
            botao.pack(side="left", padx=(0, 6))
            botao.bind("<Button-1>", lambda _e, v=valor: self.ambiente_var.set(v))
            self._botoes_ambiente[valor] = (botao, cor, suave)

    def _atualizar_faixa(self):
        atual = self.ambiente_var.get()
        for valor, (botao, cor, suave) in self._botoes_ambiente.items():
            if valor == atual:
                botao.configure(text=f"●  {valor}", bg=suave, fg=cor, highlightbackground=cor)
            else:
                botao.configure(text=valor, bg=COLORS["panel"], fg=COLORS["fg_muted"],
                                highlightbackground=COLORS["card_border"])
        cor_atual = self._botoes_ambiente[atual][1]
        self.faixa.configure(bg=cor_atual)
        dica = "Operações no ambiente real" if atual == config.AMBIENTE_PRD else "Ambiente de testes"
        self.ambiente_dica.configure(text=dica)

    def _ambiente_mudou(self):
        novo = self.ambiente_var.get()
        if novo == self._ambiente_anterior:
            return
        if self.operacao_em_andamento():
            messagebox.showwarning("Operação em andamento",
                                   "Há uma operação rodando. Pare ou espere ela terminar antes de trocar o ambiente.")
            self.ambiente_var.set(self._ambiente_anterior)
            return
        self._ambiente_anterior = novo
        self._atualizar_faixa()
        self._atualizar_lateral()
        if self.atual == ID_INICIO:
            self.hub.atualizar(animar=False)

    # --------------------------------------------------------------- lateral
    def _largura_lateral(self, recolhida) -> int:
        return int((LARGURA_RECOLHIDA if recolhida else LARGURA_LATERAL) * escala(self))

    def _posicionar_alca(self, largura):
        """A alça fica centrada na borda da barra lateral, na metade da altura."""
        k = escala(self)
        self.alca.configure(text="›" if self.lateral_recolhida else "‹")
        self.alca.place(x=largura, rely=0.5, anchor="center", width=int(18 * k), height=int(64 * k))
        self.alca.lift()
        self._dica_alca.texto = ("Mostrar o menu (Ctrl+B)" if self.lateral_recolhida
                                 else "Recolher o menu (Ctrl+B)")

    def _montar_lateral(self):
        """(Re)desenha a barra lateral: completa (ícone + nome) ou recolhida (só ícones, com
        o nome aparecendo ao parar o mouse). Rola com a roda quando não cabe na janela."""
        for filho in self.lateral.winfo_children():
            filho.destroy()
        self._itens_lateral = {}
        largura = self._largura_lateral(self.lateral_recolhida)
        self.lateral.configure(width=largura)
        self._posicionar_alca(largura)
        moldura = PaginaRolavel(self.lateral, cor=COLORS["panel"], mostrar_barra=False)
        moldura.pack(fill="both", expand=True)
        lista = tk.Frame(moldura.interior, bg=COLORS["panel"])
        moldura.conter(lista)

        tk.Frame(lista, bg=COLORS["panel"], height=8).pack(fill="x")
        self._item_lateral(lista, ID_INICIO, "🏠", "Início", COLORS["accent"], self.show_hub)
        for area, cor in AREAS:
            if self.lateral_recolhida:
                tk.Frame(lista, bg=COLORS["card_border"], height=1).pack(fill="x", padx=14, pady=8)
            else:
                tk.Label(lista, text=area.upper(), bg=COLORS["panel"], fg=COLORS[cor],
                         font=("Segoe UI", 7, "bold"), anchor="w").pack(fill="x", padx=18, pady=(16, 3))
            for op in OPERACOES:
                if op["area"] == area:
                    self._item_lateral(lista, op["id"], op["icon"], op["title"], COLORS[op["accent"]],
                                       lambda i=op["id"]: self.abrir(i), em_construcao=op.get("em_construcao"),
                                       area=area)
        tk.Frame(lista, bg=COLORS["panel"], height=10).pack(fill="x")
        self._atualizar_lateral()

    def _item_lateral(self, parent, item_id, icone, texto, cor, comando, em_construcao=False, area=None):
        linha = tk.Frame(parent, bg=COLORS["panel"], cursor="hand2")
        linha.pack(fill="x", padx=(0, 8), pady=1)
        marca = tk.Frame(linha, bg=COLORS["panel"], width=3)
        marca.pack(side="left", fill="y")
        if self.lateral_recolhida:
            lbl = tk.Label(linha, text=icone, bg=COLORS["panel"], fg=COLORS["fg"], font=("Segoe UI Emoji", 12),
                           anchor="center", pady=5)
            lbl.pack(side="left", fill="x", expand=True)
            Dica(lbl, f"{area}  ·  {texto}" if area else texto)
        else:
            lbl = tk.Label(linha, text=f"{icone}   {texto.replace(' em construção', '')}", bg=COLORS["panel"],
                           fg=COLORS["fg"], font=("Segoe UI", 10), anchor="w", padx=12, pady=5)
            lbl.pack(side="left", fill="x", expand=True)
            if em_construcao:
                tk.Label(linha, text="EM CONSTRUÇÃO", bg=COLORS["card"], fg=COLORS["teal"],
                         font=("Segoe UI", 7, "bold"), padx=6, pady=1).pack(side="right", padx=(0, 6))
        for w in (linha, lbl):
            w.bind("<Button-1>", lambda _e: comando())
            w.bind("<Enter>", lambda _e, i=item_id: self._hover_lateral(i, True), add="+")
            w.bind("<Leave>", lambda _e, i=item_id: self._hover_lateral(i, False), add="+")
        self._itens_lateral[item_id] = dict(linha=linha, lbl=lbl, marca=marca, cor=cor,
                                            em_construcao=bool(em_construcao))

    def _cor_fundo_lateral(self, item_id, hover=False):
        if item_id == self.atual:
            return misturar(self._itens_lateral[item_id]["cor"], COLORS["panel"], 0.14)
        return COLORS["card"] if hover else COLORS["panel"]

    def _hover_lateral(self, item_id, dentro):
        item = self._itens_lateral.get(item_id)
        if item is None:
            return
        fundo = self._cor_fundo_lateral(item_id, dentro)
        for w in (item["linha"], item["lbl"]):
            animacao.cor(w, {"bg": fundo}, duracao=120)

    def _atualizar_lateral(self):
        ambiente = self.ambiente_var.get()
        for item_id, item in self._itens_lateral.items():
            ativo = item_id == self.atual
            fundo = self._cor_fundo_lateral(item_id)
            op = next((o for o in OPERACOES if o["id"] == item_id), None)
            pronto = (op is None or not pendencias(op, ambiente)) and not item["em_construcao"]
            item["linha"].configure(bg=fundo)
            item["lbl"].configure(bg=fundo, fg=item["cor"] if ativo else (COLORS["fg"] if pronto
                                                                            else COLORS["fg_muted"]))
            if not self.lateral_recolhida:
                item["lbl"].configure(font=("Segoe UI Semibold" if ativo else "Segoe UI", 10))
            item["marca"].configure(bg=item["cor"] if ativo else fundo)

    def alternar_lateral(self):
        """Recolhe a barra lateral para só os ícones, ou a mostra inteira de novo (troca direta,
        sem animação)."""
        self.lateral_recolhida = not self.lateral_recolhida
        preferencias.definir("lateral_recolhida", self.lateral_recolhida)
        self._montar_lateral()

    # ------------------------------------------------------------------ temas
    def abrir_temas(self):
        from ui.tema_dialogo import DialogoTemas
        if self._dialogo_temas is not None and self._dialogo_temas.winfo_exists():
            self._dialogo_temas.lift()
            return
        self._dialogo_temas = DialogoTemas(self)

    # ------------------------------------------------------- visão para o cliente
    @property
    def visao_cliente(self) -> bool:
        """Visão para o cliente (compartilhar a tela): logo e ícone da Vivo, nenhum Pokémon."""
        return pokemon.escondidos()

    def _arquivo_logo(self):
        return "vivo_logo.png" if self.visao_cliente else "pikachu_logo.png"

    def _aplicar_icone(self):
        """Ícone da janela, da barra de tarefas e das janelas filhas (vale para as novas também)."""
        try:
            self.iconbitmap(default=caminho_asset("vivo.ico" if self.visao_cliente else "megaqg_vivo.ico"))
        except Exception:
            pass  # ícone é cosmético

    def definir_visao_cliente(self, ligada: bool):
        """Liga ou desliga a visão para o cliente na hora, sem recriar as telas (nada do que está
        preenchido se perde). A escolha fica guardada para a próxima vez que o app abrir."""
        preferencias.definir("visao_cliente", bool(ligada))
        pokemon.esconder(self, ligada)
        self._aplicar_icone()
        if self._logo_label is not None and self._logo_label.winfo_exists():
            try:
                self._logo = tk.PhotoImage(file=caminho_asset(self._arquivo_logo())).subsample(2)
                self._logo_label.configure(image=self._logo)
            except Exception:
                pass

    def aplicar_tema(self, tema_id) -> bool:
        """Troca o tema e redesenha a janela. As telas abertas são recriadas (os campos
        preenchidos voltam ao início), por isso não troca com uma operação rodando."""
        if self.operacao_em_andamento():
            messagebox.showwarning("Operação em andamento",
                                   "Há uma operação rodando. Pare ou espere ela terminar antes de trocar o tema.")
            return False
        temas.ativar(tema_id)
        aplicar_estilos(self)
        self._reconstruir()
        # A janela é redesenhada atrás de um esmaecimento e volta a ficar opaca suavemente,
        # em vez de piscar enquanto os widgets são recriados
        animacao.voltar_a_opacidade(self)
        return True

    def _reconstruir(self):
        atual = self.atual
        for parte in (self.topo, self.faixa, self.corpo):
            self._cancelar_agendamentos(parte)
        # As telas antigas observavam o ambiente: sem elas, só o observador da janela continua
        for modo, observador in self.ambiente_var.trace_info():
            self.ambiente_var.trace_remove(modo, observador)
        for parte in (self.topo, self.faixa, self.corpo):
            parte.destroy()
        self.paginas, self._molduras = {}, {}
        self.ambiente_var.trace_add("write", lambda *_: self._ambiente_mudou())
        self._montar()
        if atual == ID_INICIO:
            self.show_hub()
        else:
            self.abrir(atual, perguntar=False)

    def _cancelar_agendamentos(self, widget):
        """Cancela os after() pendentes dos widgets que vão ser destruídos (cada tela consulta a
        própria fila de eventos de tempos em tempos)."""
        comandos = set()

        def juntar(w):
            comandos.update(getattr(w, "_tclCommands", None) or [])
            for filho in w.winfo_children():
                juntar(filho)

        juntar(widget)
        for ident in self.tk.splitlist(self.tk.call("after", "info")):
            try:
                script = str(self.tk.splitlist(self.tk.call("after", "info", ident))[0])
            except tk.TclError:
                continue
            if script in comandos:
                self.tk.call("after", "cancel", ident)

    # ------------------------------------------------------------- navegação
    def _mostrar(self, vista):
        """Deixa só a vista pedida (hub ou uma tela) na área de conteúdo. As outras saem da tela
        sem ser destruídas: assim só uma é redimensionada quando a janela ou a barra lateral muda.

        A vista que entra desliza alguns pixels da direita para o lugar (transição de página).
        Só a posição muda, o tamanho não: nada é recalculado durante o movimento."""
        ja_visivel = vista.winfo_manager() == "place"
        for outra in (self.hub, *self._molduras.values()):
            if outra is not vista:
                # uma entrada ainda em andamento não pode recolocar na tela a vista que sai
                animacao.cancelar(outra, "entrada")
                if outra.winfo_manager():
                    outra.place_forget()
        if ja_visivel:
            return
        deslocamento = int(16 * escala(self)) if animacao.ativas() else 0
        vista.place(relx=0, rely=0, relwidth=1, relheight=1, x=deslocamento)

        def deslizar(p):
            if vista.winfo_manager() == "place":
                vista.place_configure(x=round(deslocamento * (1 - p)))

        if deslocamento:
            animacao.animar(vista, "entrada", 220, deslizar)

    def show_hub(self):
        self.atual = ID_INICIO
        self.hub.atualizar()
        self._mostrar(self.hub)
        self._atualizar_lateral()

    def show(self, _pagina=None):
        """Compatibilidade com as telas dos QGs originais (controller.show(HubPage))."""
        self.show_hub()

    def abrir(self, op_id: str, perguntar: bool = True):
        op = next(o for o in OPERACOES if o["id"] == op_id)
        if op.get("em_construcao"):
            messagebox.showinfo(op["title"], "As operações de NFCe são a próxima etapa do MegaQG Vivo "
                                             "e estão em desenvolvimento.")
            return
        faltando = pendencias(op, self.ambiente_var.get())
        if perguntar and faltando and op_id not in self.paginas:
            if not messagebox.askyesno(
                "Configuração incompleta",
                f"{op['title']} precisa destas chaves no config.json para rodar em "
                f"{self.ambiente_var.get()}:\n\n  " + "\n  ".join(faltando)
                + f"\n\nArquivo: {config.caminho_arquivo()}\n\nAbrir a tela mesmo assim?",
            ):
                return
        if op_id not in self.paginas:
            # Cada tela fica dentro de uma moldura que rola quando o conteúdo não cabe na janela
            moldura = PaginaRolavel(self.container)
            pagina = carregar_pagina(op)(moldura.interior, self)
            moldura.conter(pagina)
            self.paginas[op_id] = pagina
            self._molduras[op_id] = moldura
        self.atual = op_id
        self._mostrar(self._molduras[op_id])
        self._atualizar_lateral()

    # ------------------------------------------------------------- encerrar
    def operacao_em_andamento(self) -> bool:
        for pagina in self.paginas.values():
            thread = getattr(pagina, "worker_thread", None)
            if thread is not None and thread.is_alive():
                return True
        return False

    def on_close(self):
        if self.operacao_em_andamento():
            if not messagebox.askyesno("Sair", "Há uma operação em andamento. Deseja cancelar e sair?"):
                return
            for pagina in self.paginas.values():
                evento = getattr(pagina, "stop_event", None)
                if evento is not None:
                    evento.set()
        self.destroy()

    def destroy(self):
        """Cancela os after() ainda pendentes (quadros de animação, Pokémon, filas das telas)
        antes de fechar, para nenhum disparar depois que os widgets deixaram de existir."""
        try:
            for ident in self.tk.splitlist(self.tk.call("after", "info")):
                self.tk.call("after", "cancel", ident)
        except tk.TclError:
            pass
        super().destroy()
