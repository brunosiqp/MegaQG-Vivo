"""
Hub (tela inicial) do MegaQG Vivo: seções por área, busca e cards com o estado
da configuração de cada operação no ambiente escolhido.

Tudo fica num único Canvas rolável: o cabeçalho (título, subtítulo, busca e dica) é desenhado
direto nele e as seções de cards entram como uma janela embutida logo abaixo. Isso dá:
  - um fundo onde os Pokémon andam (ver ui.pokemon.Bando), sempre em volta do bloco central
    e fora dos cards, por trás dos textos, sem nunca cobrir nada clicável;
  - posição horizontal estável: a grade de cards é responsiva (3, 2 ou 1 coluna, conforme a
    largura) e nada fica em coordenada negativa. Antes o conteúdo, centralizado e mais largo
    que o Canvas em janelas estreitas, "vazava" para a esquerda e a área de rolagem horizontal
    prendia a vista ora numa ponta, ora na outra: a cada troca de tema os cards pulavam de lado.
"""
import tkinter as tk
import unicodedata
from tkinter import messagebox, ttk

from core import config
from core.versao import APP_NOME, APP_VERSION, CHANGELOG
from modulos.registro import AREAS, OPERACOES, pendencias
from ui import animacao, pokemon
from ui.theme import COLORS, escala, misturar, retangulo_arredondado
from ui.widgets import rolar_canvas


def _normalizar(texto: str) -> str:
    """Minúsculas e sem acento: "canc" acha "Cancelamento", "relatorio" acha "Relatório"."""
    texto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


class HubPage(tk.Frame):
    CARD_W = 312
    CARD_H = 200
    COLUNAS = 3          # máximo; a grade usa menos quando a largura não comporta
    MARGEM_CARD = 8      # espaço em volta de cada card (de cada lado)
    ELEVACAO = 3         # quanto o card "sobe" ao passar o mouse (a sombra aparece embaixo)

    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLORS["bg"])
        self.controller = controller
        self.colunas = self.COLUNAS
        self._secoes_cards = []  # cards de cada seção, para reorganizar a grade sem recriar
        self._altura_total = 1
        self._chao = 0
        self.busca_var = tk.StringVar()
        self.busca_var.trace_add("write", lambda *_: self.atualizar(animar=False))

        # Rodapé reservado primeiro (pack bottom), para nunca ficar por cima dos cards
        rodape = tk.Frame(self, bg=COLORS["bg"])
        rodape.pack(side="bottom", fill="x", pady=(4, 8))
        versao = tk.Label(rodape, text=f"{APP_NOME}  ·  {APP_VERSION}  ·  novidades  ·  Bruno Siqueira e Abel Fonseca",
                          bg=COLORS["bg"], fg=COLORS["fg_muted"], font=("Segoe UI", 8), cursor="hand2")
        versao.pack()
        versao.bind("<Button-1>", lambda _e: self._mostrar_changelog())
        versao.bind("<Enter>", lambda _e: animacao.cor(versao, {"fg": COLORS["accent"]}))
        versao.bind("<Leave>", lambda _e: animacao.cor(versao, {"fg": COLORS["fg_muted"]}))

        # Área rolável única: cabeçalho desenhado + seções embutidas
        self.canvas = tk.Canvas(self, bg=COLORS["bg"], highlightthickness=0, bd=0)
        barra = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=barra.set)
        barra.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self._montar_cabecalho()
        self.secoes = tk.Frame(self.canvas, bg=COLORS["bg"])
        self._janela = self.canvas.create_window(0, 0, window=self.secoes, anchor="n")
        self.canvas.bind("<Configure>", lambda e: self._ao_redimensionar(e.width))
        self.secoes.bind("<Configure>", lambda _e: self._posicionar())

        self.bando = pokemon.Bando(self.canvas, self._area_dos_pokemon)

    # ------------------------------------------------------------- cabeçalho
    def _montar_cabecalho(self):
        c = self.canvas
        self._titulo = c.create_text(0, 0, text="Central de Operações Fiscais", fill=COLORS["fg"],
                                     font=("Segoe UI Light", 26), anchor="n")
        self._subtitulo = c.create_text(0, 0, text="NFCom  ·  NFSe  ·  NFCe  ·  Relatórios", fill=COLORS["fg_muted"],
                                        font=("Segoe UI", 10), anchor="n")

        # Busca: campo sem moldura, só uma linha embaixo que acende na cor de destaque com o foco
        self.busca = busca = tk.Frame(c, bg=COLORS["bg"])
        linha_busca = tk.Frame(busca, bg=COLORS["bg"])
        linha_busca.pack()
        tk.Label(linha_busca, text="🔎", bg=COLORS["bg"], fg=COLORS["fg_muted"],
                 font=("Segoe UI", 11)).pack(side="left", padx=(4, 6))
        self.busca_entry = tk.Entry(linha_busca, textvariable=self.busca_var, width=44, bg=COLORS["bg"],
                                    fg=COLORS["fg"], insertbackground=COLORS["accent"], relief="flat",
                                    font=("Segoe UI", 12), selectbackground=COLORS["accent_soft"],
                                    selectforeground=COLORS["fg"])
        self.busca_entry.pack(side="left", ipady=6, padx=(0, 4))
        sublinhado = tk.Frame(busca, bg=COLORS["card_border"], height=1)
        sublinhado.pack(fill="x")
        self.busca_entry.bind("<FocusIn>", lambda _e: animacao.cor(sublinhado, {"bg": COLORS["accent"]}))
        self.busca_entry.bind("<FocusOut>", lambda _e: animacao.cor(sublinhado, {"bg": COLORS["card_border"]}))
        self._busca_item = c.create_window(0, 0, window=busca, anchor="n")
        self._dica = c.create_text(0, 0, text="Digite para filtrar as operações (ex.: cancel, xml, dps)",
                                   fill=COLORS["fg_muted"], font=("Segoe UI", 8), anchor="n")

    def _ao_redimensionar(self, largura):
        """Escolhe quantas colunas cabem e reposiciona tudo no centro (sem nada negativo)."""
        k = escala(self)
        por_card = int((self.CARD_W + 2 * self.MARGEM_CARD) * k)
        colunas = max(1, min(self.COLUNAS, (largura - int(24 * k)) // por_card))
        if colunas != self.colunas:
            self.colunas = colunas
            self._reorganizar_grade()
        self._posicionar(largura)

    def _posicionar(self, largura=None):
        """Coloca cabeçalho, faixa dos Pokémon e seções; a área de rolagem só cresce para baixo."""
        c = self.canvas
        largura = largura or c.winfo_width()
        k = escala(self)
        conteudo = max(largura, self.secoes.winfo_reqwidth())
        centro = conteudo // 2
        y = int(26 * k)
        c.coords(self._titulo, centro, y)
        y = c.bbox(self._titulo)[3] + int(2 * k)
        c.coords(self._subtitulo, centro, y)
        y = c.bbox(self._subtitulo)[3] + int(16 * k)
        c.coords(self._busca_item, centro, y)
        y += self.busca.winfo_reqheight() + int(6 * k)
        c.coords(self._dica, centro, y)
        self._chao = c.bbox(self._dica)[3] + int(8 * k)  # corredor por onde os Pokémon cruzam de um lado ao outro
        y = self._chao + pokemon.FAIXA_LIVRE + int(4 * k)
        c.coords(self._janela, centro, y)
        self._altura_total = y + self.secoes.winfo_reqheight() + int(20 * k)
        c.configure(scrollregion=(0, 0, conteudo, max(self._altura_total, c.winfo_height())))
        if c.xview()[0] != 0.0:
            c.xview_moveto(0)

    def _area_dos_pokemon(self):
        """Onde os Pokémon andam: a parte visível do canvas, menos o bloco central (título,
        subtítulo, busca e dica, com uma margem; vem primeiro, ver ui.pokemon.Bando) e a área
        dos cards."""
        c = self.canvas
        topo = c.canvasy(0)
        limites = (0, topo, c.winfo_width(), topo + c.winfo_height())
        caixas = [b for b in (c.bbox(item) for item in (self._titulo, self._subtitulo, self._busca_item, self._dica)) if b]
        if not caixas:
            return limites, [limites]  # ainda sem layout: ninguém anda
        margem = int(10 * escala(self))
        centro = (min(b[0] for b in caixas) - margem, min(b[1] for b in caixas) - margem,
                  max(b[2] for b in caixas) + margem, max(b[3] for b in caixas) + margem)
        return limites, [centro, c.bbox(self._janela)]

    def rolar_roda(self, delta) -> bool:
        """Roda do mouse em qualquer ponto do hub (ver ui.widgets.ativar_roda)."""
        return rolar_canvas(self.canvas, delta, self._altura_total)

    # ----------------------------------------------------------------- cards
    def atualizar(self, animar=True):
        """Redesenha as seções (ao abrir o hub, ao trocar o ambiente e ao buscar). Com
        animar=True os cards entram em sequência, com um fade-in curto."""
        for filho in self.secoes.winfo_children():
            filho.destroy()
        self._secoes_cards = []
        termo = _normalizar(self.busca_var.get().strip())
        ambiente = self.controller.ambiente_var.get()
        algum = False
        ordem = 0

        for area, cor_area in AREAS:
            ops = [op for op in OPERACOES if op["area"] == area and
                   (not termo or termo in _normalizar(f"{op['title']} {op['desc']} {area}"))]
            if not ops:
                continue
            algum = True
            # Cabeçalho da seção: nome da área em caixa alta, contagem e uma linha fina até o fim
            cab = tk.Frame(self.secoes, bg=COLORS["bg"])
            cab.pack(fill="x", padx=12, pady=(18, 4))
            tk.Frame(cab, bg=COLORS[cor_area], width=3, height=14).pack(side="left", padx=(0, 10))
            tk.Label(cab, text=area.upper(), bg=COLORS["bg"], fg=COLORS["fg"],
                     font=("Segoe UI", 10, "bold")).pack(side="left")
            ativas = [op for op in ops if not op.get("em_construcao")]
            contagem = f"{len(ativas):02d}" if ativas else "próxima etapa"
            tk.Label(cab, text=contagem, bg=COLORS["bg"], fg=COLORS[cor_area],
                     font=("Segoe UI", 9)).pack(side="left", padx=(8, 12))
            tk.Frame(cab, bg=COLORS["card_border"], height=1).pack(side="left", fill="x", expand=True)

            grade = tk.Frame(self.secoes, bg=COLORS["bg"])
            grade.pack(anchor="w")
            cards = [self._card(grade, i, op, pendencias(op, ambiente), mostrar_area=bool(termo))
                     for i, op in enumerate(ops)]
            self._ajustar_altura(cards)
            self._secoes_cards.append(cards)
            if animar:
                for card in cards:
                    animacao.revelar(card["canvas"], COLORS["bg"], atraso=min(ordem, 10) * 35)
                    ordem += 1

        if not algum:
            tk.Label(self.secoes, text="Nenhuma operação encontrada.", bg=COLORS["bg"],
                     fg=COLORS["fg_muted"], font=("Segoe UI", 11)).pack(pady=30)
        self.canvas.yview_moveto(0)

    def _reorganizar_grade(self):
        for cards in self._secoes_cards:
            for i, card in enumerate(cards):
                linha, coluna = divmod(i, self.colunas)
                card["canvas"].grid(row=linha, column=coluna)

    def _card(self, parent, idx, op, faltando, mostrar_area=False):
        """Card desenhado num Canvas (sem widgets filhos: hover sem tremor, técnica do hub
        do QG NFCom). Layout: chip do ícone + área + título, descrição, divisória e rodapé
        com o estado (Pronto / Configurar / Em construção) e "Abrir →". Todas as posições
        vêm do tamanho medido de cada texto, então nada se sobrepõe em escala > 100%.
        Os itens do card têm a tag "card"; a sombra, desenhada em _ajustar_altura, não."""
        row, col = divmod(idx, self.colunas)
        k = escala(self)
        w, pad, raio = int(self.CARD_W * k), int(20 * k), int(10 * k)
        accent = COLORS[op["accent"]]
        em_construcao = bool(op.get("em_construcao"))
        pronto = not faltando and not em_construcao
        fundo, fundo_hover = COLORS["panel"], misturar(accent, COLORS["panel"], 0.07)
        card, rodape = ("card",), ("card", "rodape")

        canvas = tk.Canvas(parent, width=w, height=int(self.CARD_H * k), bg=COLORS["bg"],
                           highlightthickness=0, bd=0, cursor="hand2")
        canvas.grid(row=row, column=col, padx=int(self.MARGEM_CARD * k), pady=int(self.MARGEM_CARD * k),
                    sticky="n")
        corpo = canvas.create_polygon(retangulo_arredondado(1, 1, w - 1, 100, raio), smooth=True,
                                      fill=fundo, outline=COLORS["card_border"], width=1, tags=card)

        # Chip do ícone (fundo na cor da operação, bem suave)
        chip = int(46 * k)
        canvas.create_polygon(retangulo_arredondado(pad, pad, pad + chip, pad + chip, int(11 * k)), smooth=True,
                              fill=misturar(accent, fundo, 0.16), outline="", tags=card)
        canvas.create_text(pad + chip // 2, pad + chip // 2, text=op["icon"], fill=accent,
                           font=("Segoe UI Emoji", 17), tags=card)

        x = pad + chip + int(14 * k)
        if mostrar_area:  # na busca as áreas se misturam: o rótulo diz de onde é a operação
            area = canvas.create_text(x, pad + int(2 * k), text=op["area"].upper(), fill=accent,
                                      font=("Segoe UI", 7, "bold"), anchor="nw", tags=card)
            titulo = canvas.create_text(x, canvas.bbox(area)[3] + int(3 * k), text=op["title"], fill=COLORS["fg"],
                                        font=("Segoe UI Semibold", 12), anchor="nw", width=w - x - pad, tags=card)
        else:
            titulo = canvas.create_text(x, pad + chip // 2, text=op["title"], fill=COLORS["fg"],
                                        font=("Segoe UI Semibold", 12), anchor="w", width=w - x - pad, tags=card)
        y = max(pad + chip, canvas.bbox(titulo)[3]) + int(14 * k)
        desc = canvas.create_text(pad, y, text=op["desc"], fill=COLORS["fg_muted"], font=("Segoe UI", 9),
                                  anchor="nw", width=w - 2 * pad, justify="left", tags=card)

        # Rodapé (tag "rodape": desce junto quando os cards da seção são igualados)
        y = canvas.bbox(desc)[3] + int(16 * k)
        canvas.create_line(pad, y, w - pad, y, fill=COLORS["card_border"], tags=rodape)
        y += int(12 * k)
        if em_construcao:
            estado, cor_estado = "Em construção", COLORS["teal"]
        elif pronto:
            estado, cor_estado = "Pronto", COLORS["success"]
        else:
            estado, cor_estado = "Configurar", COLORS["warning"]
        texto_pilula = canvas.create_text(pad + int(10 * k), y + int(4 * k), text=f"●  {estado}", fill=cor_estado,
                                          font=("Segoe UI", 8, "bold"), anchor="nw", tags=rodape)
        x0, y0, x1, y1 = canvas.bbox(texto_pilula)
        pilula = canvas.create_polygon(
            retangulo_arredondado(pad, y, x1 + int(10 * k), y1 + int(4 * k), int(9 * k)), smooth=True,
            fill=misturar(cor_estado, fundo, 0.14), outline="", tags=rodape)
        canvas.tag_raise(texto_pilula, pilula)
        fim = y1 + int(4 * k)
        if pronto:
            canvas.create_text(w - pad, (y + fim) // 2, text="Abrir  →", fill=accent,
                               font=("Segoe UI", 9, "bold"), anchor="e", tags=rodape)
        elif not em_construcao:
            detalhe = canvas.create_text(pad, fim + int(8 * k), text="Falta no config.json: " + ", ".join(faltando),
                                         fill=COLORS["fg_muted"], font=("Segoe UI", 8), anchor="nw",
                                         width=w - 2 * pad, tags=rodape)
            fim = canvas.bbox(detalhe)[3]
        altura = fim + pad
        dados = dict(canvas=canvas, corpo=corpo, altura=altura, w=w, raio=raio, elevado=0)

        def hover(dentro):
            """Card sobe alguns pixels (a sombra aparece embaixo) e a borda acende na cor da
            operação, numa transição curta: o equivalente a :hover com transform e box-shadow."""
            elevacao = int(self.ELEVACAO * escala(self))
            animacao.cor(canvas, {"fill": fundo_hover if dentro else fundo,
                                  "outline": accent if dentro else COLORS["card_border"]}, item=corpo)

            def passo(p):
                alvo = round(elevacao * (p if dentro else 1 - p))
                canvas.move("card", 0, dados["elevado"] - alvo)
                dados["elevado"] = alvo

            animacao.animar(canvas, "elevar", 160, passo)

        canvas.bind("<Enter>", lambda _e: hover(True))
        canvas.bind("<Leave>", lambda _e: hover(False))
        canvas.bind("<Button-1>", lambda _e: self.controller.abrir(op["id"]))
        return dados

    def _ajustar_altura(self, cards):
        """Todos os cards da seção ficam com a altura do maior; o rodapé desce para a base.
        Cada card ganha alguns pixels por cima (espaço para subir no hover) e uma sombra que só
        aparece quando ele sobe."""
        if not cards:
            return
        elevacao = int(self.ELEVACAO * escala(self))
        altura = max(c["altura"] for c in cards)
        sombra = misturar("#000000", COLORS["bg"], 0.35)
        for c in cards:
            cv = c["canvas"]
            cv.configure(height=altura + elevacao)
            cv.coords(c["corpo"], *retangulo_arredondado(1, 1, c["w"] - 1, altura - 1, c["raio"]))
            cv.move("rodape", 0, altura - c["altura"])
            cv.move("card", 0, elevacao)
            c["sombra"] = cv.create_polygon(
                retangulo_arredondado(2, elevacao + 1, c["w"] - 2, altura - 1 + elevacao, c["raio"]), smooth=True,
                fill=sombra, outline="")
            cv.tag_lower(c["sombra"])

    def _mostrar_changelog(self):
        partes = []
        for versao, itens in CHANGELOG.items():
            partes.append(versao)
            partes.extend(f"  • {item}" for item in itens)
            partes.append("")
        partes.append(f"Configuração: {config.origem()}")
        messagebox.showinfo(f"Novidades — {APP_VERSION}", "\n".join(partes).strip())
