"""
Janela de temas: escolher um tema pronto, criar um tema próprio a partir de qualquer outro,
editar ou excluir os temas criados. A troca é aplicada na hora, na janela inteira.
"""
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

from ui import animacao, temas
from ui.theme import COLORS, escala, misturar, sobre
from ui.widgets import PaginaRolavel, centralizar

COLUNAS = 3


class DialogoTemas(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Temas")
        self.transient(app)
        self.resizable(False, False)
        k = escala(self)
        centralizar(self, int(900 * k), int(600 * k))
        self.modo = "lista"
        self.editando = None  # id do tema do usuário em edição (None = tema novo)
        self.cores = {}
        self.nome_var = tk.StringVar()
        self._campos = {}
        self._montar()
        self.grab_set()
        self.bind("<Escape>", lambda _e: self._voltar_ou_fechar())
        self.protocol("WM_DELETE_WINDOW", self.fechar)

    def fechar(self):
        """Fecha com um fade-out curto (direto, com movimento reduzido)."""
        self.grab_release()
        animacao.sumir(self, self.destroy)

    # ----------------------------------------------------------------- base
    def _montar(self):
        """Redesenha a janela inteira com as cores do tema ativo (chamado a cada troca de tema)."""
        for filho in self.winfo_children():
            filho.destroy()
        self.configure(bg=COLORS["bg"])
        if self.modo == "lista":
            self._montar_lista()
        else:
            self._montar_editor()

    def _cabecalho(self, titulo, subtitulo):
        topo = tk.Frame(self, bg=COLORS["bg"])
        topo.pack(fill="x", padx=26, pady=(22, 10))
        tk.Label(topo, text=titulo, bg=COLORS["bg"], fg=COLORS["fg"], font=("Segoe UI Light", 20)).pack(anchor="w")
        tk.Label(topo, text=subtitulo, bg=COLORS["bg"], fg=COLORS["fg_muted"], font=("Segoe UI", 9),
                 justify="left").pack(anchor="w", pady=(2, 0))

    def _rodape(self):
        rodape = tk.Frame(self, bg=COLORS["panel"])
        rodape.pack(side="bottom", fill="x")
        tk.Frame(self, bg=COLORS["card_border"], height=1).pack(side="bottom", fill="x")
        interno = tk.Frame(rodape, bg=COLORS["panel"])
        interno.pack(fill="x", padx=22, pady=12)
        return interno

    def _voltar_ou_fechar(self):
        if self.modo == "editor":
            self.modo = "lista"
            self._montar()
        else:
            self.fechar()

    # ---------------------------------------------------------------- lista
    def _montar_lista(self):
        rodape = self._rodape()
        ativo = temas.ativo()
        do_usuario = ativo in temas.personalizados()
        ttk.Button(rodape, text="＋  Criar tema a partir deste", style="Accent.TButton",
                   command=lambda: self._abrir_editor(None)).pack(side="left")
        if do_usuario:
            ttk.Button(rodape, text="Editar cores", command=lambda: self._abrir_editor(ativo)).pack(
                side="left", padx=(8, 0))
            ttk.Button(rodape, text="Excluir tema", command=self._excluir).pack(side="left", padx=(8, 0))
        ttk.Button(rodape, text="Fechar", command=self.fechar).pack(side="right")
        # Animações e Pokémon decorativos. Sem escolha do usuário, segue o Windows (movimento
        # reduzido); marcar ou desmarcar aqui vale acima do Windows (ver ui.animacao).
        self.animacoes_var = tk.BooleanVar(value=animacao.preferencia_ligada())
        ttk.Checkbutton(rodape, text="Animações e Pokémon", variable=self.animacoes_var,
                        command=lambda: animacao.definir_preferencia(self.animacoes_var.get())).pack(
            side="right", padx=(0, 16))
        if animacao.windows_desliga():
            tk.Label(rodape, text="o Windows está com os efeitos de animação desligados; marque para ligar aqui",
                     bg=COLORS["panel"], fg=COLORS["fg_muted"], font=("Segoe UI", 8)).pack(side="right", padx=(0, 6))

        self._cabecalho("Temas", "Clique num tema para aplicar. As telas abertas são recriadas com as cores novas "
                                 "(os campos preenchidos voltam ao início).")
        self._bloco_visao_cliente()
        moldura = PaginaRolavel(self)
        moldura.pack(fill="both", expand=True, padx=(18, 8), pady=(0, 8))
        grade = tk.Frame(moldura.interior, bg=COLORS["bg"])
        moldura.conter(grade)
        for coluna in range(COLUNAS):
            grade.grid_columnconfigure(coluna, weight=1, uniform="tema")
        for i, (tema_id, tema) in enumerate(temas.todos().items()):
            self._cartao(grade, tema_id, tema, tema_id == ativo).grid(
                row=i // COLUNAS, column=i % COLUNAS, sticky="nsew", padx=8, pady=8)

    def _bloco_visao_cliente(self):
        """Botão da visão para o cliente: fica aqui, e não no topo do app, para não estar à vista
        de quem está vendo a tela compartilhada."""
        bloco = tk.Frame(self, bg=COLORS["bg"])
        bloco.pack(fill="x", padx=26, pady=(0, 8))
        ligada = self.app.visao_cliente
        self.botao_visao_cliente = ttk.Button(
            bloco, text="Visão para o cliente: ligada" if ligada else "Ativar visão para o cliente",
            style="Accent.TButton" if ligada else "TButton", command=self._alternar_visao_cliente)
        self.botao_visao_cliente.pack(side="left")
        tk.Label(bloco, text=("Para compartilhar a tela com o cliente: logo e ícone da Vivo no lugar do Pikachu e "
                              "nenhum Pokémon. Vale na hora, sem perder o que está preenchido; clique de novo para "
                              "voltar." if not ligada else
                              "Ligada: logo e ícone da Vivo, sem Pokémon. Clique para voltar ao normal."),
                 bg=COLORS["bg"], fg=COLORS["fg_muted"], font=("Segoe UI", 9), justify="left",
                 wraplength=int(620 * escala(self))).pack(side="left", padx=(12, 0))

    def _alternar_visao_cliente(self):
        self.app.definir_visao_cliente(not self.app.visao_cliente)
        self._montar()  # o botão mostra o estado novo

    def _cartao(self, parent, tema_id, tema, ativo):
        """Cartão de um tema: miniatura desenhada com as cores dele, nome e descrição."""
        k = escala(self)
        p = temas.completar(tema["cores"])
        borda = COLORS["accent"] if ativo else COLORS["card_border"]
        cartao = tk.Frame(parent, bg=COLORS["panel"], highlightthickness=1, highlightbackground=borda,
                          highlightcolor=borda, cursor="hand2")
        largura, altura = int(250 * k), int(96 * k)
        mini = tk.Canvas(cartao, width=largura, height=altura, bg=p["bg"], highlightthickness=0, cursor="hand2")
        mini.pack(fill="x", padx=10, pady=(10, 8))
        # Miniatura: topo, linha do ambiente, barra lateral, dois cartões e as cores de aviso
        mini.create_rectangle(0, 0, largura * 2, int(16 * k), fill=p["panel"], outline="")
        mini.create_rectangle(0, int(16 * k), largura * 2, int(18 * k), fill=p["prd"], outline="")
        mini.create_rectangle(0, int(18 * k), int(46 * k), altura, fill=p["panel"], outline="")
        mini.create_rectangle(0, int(30 * k), int(2 * k), int(40 * k), fill=p["accent"], outline="")
        for n in range(4):
            y = int((30 + n * 14) * k)
            mini.create_rectangle(int(8 * k), y + int(3 * k), int(38 * k), y + int(6 * k),
                                  fill=p["accent"] if n == 0 else p["fg_muted"], outline="")
        for n, cor in enumerate((p["accent"], p["teal"])):
            x = int((58 + n * 96) * k)
            mini.create_rectangle(x, int(30 * k), x + int(84 * k), int(72 * k), fill=p["card"],
                                  outline=p["card_border"])
            mini.create_rectangle(x + int(8 * k), int(38 * k), x + int(20 * k), int(50 * k), fill=cor, outline="")
            mini.create_rectangle(x + int(26 * k), int(42 * k), x + int(70 * k), int(46 * k), fill=p["fg"], outline="")
            mini.create_rectangle(x + int(8 * k), int(58 * k), x + int(60 * k), int(61 * k), fill=p["fg_muted"],
                                  outline="")
        for n, chave in enumerate(("success", "warning", "danger", "purple", "cyan")):
            x = int((58 + n * 14) * k)
            mini.create_oval(x, int(80 * k), x + int(8 * k), int(88 * k), fill=p[chave], outline="")

        linha = tk.Frame(cartao, bg=COLORS["panel"], cursor="hand2")
        linha.pack(fill="x", padx=12)
        nome = tk.Label(linha, text=tema["nome"], bg=COLORS["panel"], fg=COLORS["fg"],
                        font=("Segoe UI Semibold", 11), anchor="w", cursor="hand2")
        nome.pack(side="left")
        if ativo:
            tk.Label(linha, text="●  ATIVO", bg=COLORS["panel"], fg=COLORS["accent"],
                     font=("Segoe UI", 7, "bold")).pack(side="right")
        elif tema.get("personalizado"):
            tk.Label(linha, text="SEU TEMA", bg=COLORS["panel"], fg=COLORS["fg_muted"],
                     font=("Segoe UI", 7, "bold")).pack(side="right")
        descricao = tk.Label(cartao, text=tema.get("descricao", ""), bg=COLORS["panel"], fg=COLORS["fg_muted"],
                             font=("Segoe UI", 8), anchor="w", justify="left", wraplength=int(240 * k),
                             cursor="hand2")
        descricao.pack(fill="x", padx=12, pady=(1, 12))
        for w in (cartao, mini, linha, nome, descricao):
            w.bind("<Button-1>", lambda _e, i=tema_id: self._escolher(i))
            if not ativo:
                w.bind("<Enter>", lambda _e: animacao.cor(cartao, {"highlightbackground": COLORS["fg_muted"]}),
                       add="+")
                w.bind("<Leave>", lambda _e: animacao.cor(cartao, {"highlightbackground": COLORS["card_border"]}),
                       add="+")
        return cartao

    def _escolher(self, tema_id):
        if tema_id != temas.ativo() and self.app.aplicar_tema(tema_id):
            self._montar()

    def _excluir(self):
        ativo = temas.ativo()
        nome = temas.todos()[ativo]["nome"]
        if not messagebox.askyesno("Excluir tema", f"Excluir o tema \"{nome}\"?\n\nO tema padrão volta a ser usado.",
                                   parent=self):
            return
        if self.app.aplicar_tema(temas.PADRAO):
            temas.excluir_personalizado(ativo)
            self._montar()

    # --------------------------------------------------------------- editor
    def _abrir_editor(self, tema_id):
        """Editor de cores: tema novo (cópia do ativo) ou um tema do usuário já existente."""
        self.editando = tema_id
        origem = temas.todos()[tema_id or temas.ativo()]
        self.cores = {chave: temas.completar(origem["cores"])[chave] for chave in temas.NOMES_CHAVES}
        self.nome_var.set(origem["nome"] if tema_id else f"Meu {origem['nome']}")
        self.modo = "editor"
        self._montar()

    def _montar_editor(self):
        k = escala(self)
        rodape = self._rodape()
        ttk.Button(rodape, text="←  Voltar", command=self._voltar_ou_fechar).pack(side="left")
        ttk.Button(rodape, text="Salvar e aplicar", style="Accent.TButton", command=self._salvar).pack(side="right")

        self._cabecalho("Editar tema" if self.editando else "Novo tema",
                        "Clique no quadrado de uma cor para escolher, ou digite o código (ex.: #4da3ff). "
                        "A prévia ao lado muda na hora.")
        linha_nome = tk.Frame(self, bg=COLORS["bg"])
        linha_nome.pack(fill="x", padx=26, pady=(0, 10))
        tk.Label(linha_nome, text="Nome do tema", bg=COLORS["bg"], fg=COLORS["fg_muted"],
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 10))
        ttk.Entry(linha_nome, textvariable=self.nome_var, width=34).pack(side="left")

        corpo = tk.Frame(self, bg=COLORS["bg"])
        corpo.pack(fill="both", expand=True, padx=(18, 22), pady=(0, 10))
        self._previa_frame = tk.Frame(corpo, width=int(300 * k), highlightthickness=1)
        self._previa_frame.pack(side="right", fill="y", padx=(12, 0))
        self._previa_frame.pack_propagate(False)

        moldura = PaginaRolavel(corpo)
        moldura.pack(side="left", fill="both", expand=True)
        lista = tk.Frame(moldura.interior, bg=COLORS["bg"])
        moldura.conter(lista)
        self._campos = {}
        grupo_atual = None
        for chave, nome, grupo in temas.CHAVES:
            if grupo != grupo_atual:
                grupo_atual = grupo
                tk.Label(lista, text=grupo.upper(), bg=COLORS["bg"], fg=COLORS["fg_muted"],
                         font=("Segoe UI", 7, "bold"), anchor="w").pack(fill="x", padx=8, pady=(10, 4))
            self._linha_cor(lista, chave, nome)
        self._montar_previa()

    def _linha_cor(self, parent, chave, nome):
        linha = tk.Frame(parent, bg=COLORS["bg"])
        linha.pack(fill="x", padx=8, pady=2)
        amostra = tk.Label(linha, width=4, bg=self.cores[chave], cursor="hand2", highlightthickness=1,
                           highlightbackground=COLORS["card_border"])
        amostra.pack(side="left", ipady=3)
        amostra.bind("<Button-1>", lambda _e: self._escolher_cor(chave, nome))
        tk.Label(linha, text=nome, bg=COLORS["bg"], fg=COLORS["fg"], font=("Segoe UI", 10),
                 anchor="w").pack(side="left", padx=(12, 0))
        variavel = tk.StringVar(value=self.cores[chave])
        campo = ttk.Entry(linha, textvariable=variavel, width=10, font=("Consolas", 10))
        campo.pack(side="right")
        campo.bind("<Return>", lambda _e: self._digitou(chave))
        campo.bind("<FocusOut>", lambda _e: self._digitou(chave))
        self._campos[chave] = (amostra, variavel)

    def _definir_cor(self, chave, cor):
        self.cores[chave] = cor
        amostra, variavel = self._campos[chave]
        amostra.configure(bg=cor)
        variavel.set(cor)
        self._atualizar_previa()

    def _escolher_cor(self, chave, nome):
        _rgb, cor = colorchooser.askcolor(color=self.cores[chave], title=nome, parent=self)
        if cor:
            self._definir_cor(chave, temas.validar_cor(cor) or self.cores[chave])

    def _digitou(self, chave):
        """Aceita o código digitado se for uma cor; senão volta para a cor que estava."""
        _amostra, variavel = self._campos[chave]
        self._definir_cor(chave, temas.validar_cor(variavel.get()) or self.cores[chave])

    def _salvar(self):
        for chave in self._campos:
            self._digitou(chave)
        nome = " ".join(self.nome_var.get().split())
        if not nome:
            messagebox.showwarning("Nome do tema", "Dê um nome ao tema.", parent=self)
            return
        if self.app.operacao_em_andamento():
            messagebox.showwarning("Operação em andamento", "Há uma operação rodando. Pare ou espere ela terminar "
                                   "antes de salvar e aplicar o tema.", parent=self)
            return
        tema_id = temas.salvar_personalizado(nome, self.cores, self.editando)
        if self.app.aplicar_tema(tema_id):
            self.modo = "lista"
            self._montar()

    # ---------------------------------------------------------------- prévia
    def _montar_previa(self):
        """Miniatura de uma tela (topo, menu, cartão, botão, contadores e log) com as cores em edição."""
        for filho in self._previa_frame.winfo_children():
            filho.destroy()
        f = self._previa_frame
        self._p = p = {}
        p["topo"] = tk.Frame(f, height=30)
        p["topo"].pack(fill="x")
        p["topo"].pack_propagate(False)
        p["marca"] = tk.Label(p["topo"], text="MEGAQG VIVO", font=("Segoe UI Semibold", 8))
        p["marca"].pack(side="left", padx=10)
        p["ambiente"] = tk.Label(p["topo"], text="● Produção", font=("Segoe UI", 7, "bold"), padx=6)
        p["ambiente"].pack(side="right", padx=8, pady=6)
        p["hml"] = tk.Label(p["topo"], text="Homologação", font=("Segoe UI", 7, "bold"), padx=6)
        p["hml"].pack(side="right", pady=6)
        p["faixa"] = tk.Frame(f, height=2)
        p["faixa"].pack(fill="x")
        meio = tk.Frame(f)
        meio.pack(fill="both", expand=True)
        p["meio"] = meio
        p["menu"] = tk.Frame(meio, width=78)
        p["menu"].pack(side="left", fill="y")
        p["menu"].pack_propagate(False)
        p["item_ativo"] = tk.Label(p["menu"], text="Consulta", font=("Segoe UI Semibold", 8), anchor="w", padx=8)
        p["item_ativo"].pack(fill="x", pady=(10, 1))
        p["item"] = tk.Label(p["menu"], text="Download", font=("Segoe UI", 8), anchor="w", padx=8)
        p["item"].pack(fill="x")
        p["divisor"] = tk.Frame(meio, width=1)
        p["divisor"].pack(side="left", fill="y")
        area = tk.Frame(meio)
        area.pack(side="left", fill="both", expand=True)
        p["area"] = area
        p["titulo"] = tk.Label(area, text="Download de XMLs", font=("Segoe UI Semibold", 11), anchor="w")
        p["titulo"].pack(fill="x", padx=12, pady=(12, 0))
        p["sub"] = tk.Label(area, text="texto secundário", font=("Segoe UI", 8), anchor="w")
        p["sub"].pack(fill="x", padx=12)
        p["cartao"] = tk.Frame(area, highlightthickness=1)
        p["cartao"].pack(fill="x", padx=12, pady=10)
        p["campo"] = tk.Label(p["cartao"], text="C:\\pasta\\chaves.txt", font=("Segoe UI", 8), anchor="w", padx=6,
                              pady=3, highlightthickness=1)
        p["campo"].pack(fill="x", padx=8, pady=8)
        botoes = tk.Frame(p["cartao"])
        botoes.pack(fill="x", padx=8, pady=(0, 8))
        p["botoes"] = botoes
        p["botao"] = tk.Label(botoes, text="▶ Iniciar", font=("Segoe UI", 8, "bold"), padx=10, pady=3)
        p["botao"].pack(side="left")
        p["botao2"] = tk.Label(botoes, text="Parar", font=("Segoe UI", 8), padx=10, pady=3, highlightthickness=1)
        p["botao2"].pack(side="left", padx=(6, 0))
        contadores = tk.Frame(area)
        contadores.pack(fill="x", padx=12)
        p["contadores"] = contadores
        for chave, texto in (("success", "128"), ("warning", "4"), ("danger", "2")):
            p[f"n_{chave}"] = tk.Label(contadores, text=texto, font=("Segoe UI Semibold", 13), padx=8, pady=2,
                                       highlightthickness=1)
            p[f"n_{chave}"].pack(side="left", padx=(0, 6))
        p["log"] = tk.Frame(area, highlightthickness=1)
        p["log"].pack(fill="both", expand=True, padx=12, pady=10)
        for chave, texto in (("success", "OK    HTTP 200"), ("warning", "AVISO HTTP 422"),
                             ("danger", "ERRO  HTTP 500"), ("fg_muted", "Finalizado.")):
            p[f"log_{chave}"] = tk.Label(p["log"], text=texto, font=("Consolas", 8), anchor="w")
            p[f"log_{chave}"].pack(fill="x", padx=6)
        pontos = tk.Frame(area)
        pontos.pack(fill="x", padx=12, pady=(0, 10))
        p["pontos"] = pontos
        for chave in ("purple", "teal", "cyan", "indigo", "blue"):
            p[f"op_{chave}"] = tk.Label(pontos, text="  ", font=("Segoe UI", 6))
            p[f"op_{chave}"].pack(side="left", padx=(0, 5))
        self._atualizar_previa()

    def _atualizar_previa(self):
        c, p = temas.completar(self.cores), self._p
        self._previa_frame.configure(bg=c["bg"], highlightbackground=COLORS["card_border"])
        for nome in ("topo", "menu"):
            p[nome].configure(bg=c["panel"])
        for nome in ("meio", "area", "contadores", "pontos"):
            p[nome].configure(bg=c["bg"])
        p["marca"].configure(bg=c["panel"], fg=c["fg"])
        p["ambiente"].configure(bg=c["prd_soft"], fg=c["prd"])
        p["hml"].configure(bg=c["panel"], fg=c["hml"])
        p["faixa"].configure(bg=c["prd"])
        p["item_ativo"].configure(bg=misturar(c["accent"], c["panel"], 0.14), fg=c["accent"])
        p["item"].configure(bg=c["panel"], fg=c["fg"])
        p["divisor"].configure(bg=c["card_border"])
        p["titulo"].configure(bg=c["bg"], fg=c["fg"])
        p["sub"].configure(bg=c["bg"], fg=c["fg_muted"])
        p["cartao"].configure(bg=c["panel"], highlightbackground=c["card_border"])
        p["botoes"].configure(bg=c["panel"])
        p["campo"].configure(bg=c["card"], fg=c["fg"], highlightbackground=c["card_border"])
        p["botao"].configure(bg=c["accent"], fg=sobre(c["accent"]))
        p["botao2"].configure(bg=c["panel"], fg=c["fg"], highlightbackground=c["card_border"])
        for chave in ("success", "warning", "danger"):
            p[f"n_{chave}"].configure(bg=c["card"], fg=c[chave], highlightbackground=c["card_border"])
        p["log"].configure(bg=c["card"], highlightbackground=c["card_border"])
        for chave in ("success", "warning", "danger", "fg_muted"):
            p[f"log_{chave}"].configure(bg=c["card"], fg=c[chave])
        for chave in ("purple", "teal", "cyan", "indigo", "blue"):
            p[f"op_{chave}"].configure(bg=c[chave])
