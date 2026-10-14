"""
Pokémon andando pela tela: a identidade visual que a logo do Pikachu já sugeria, espalhada pelo
app de forma discreta.

As animações (andar, golpe e pulo, em 8 direções) ficam em assets/pokemon: uma folha PNG por
Pokémon e animação, com uma linha por direção, e animacoes.json com o tamanho, o tempo de cada
quadro e onde cada animação fica em relação ao corpo. Vêm do PMD SpriteCollab (sprites no estilo
de Pokémon Mystery Dungeon, muitos deles os originais do jogo), preparadas por
tools/preparar_pokemon.py. Créditos e licença em assets/pokemon/CREDITOS.md.

Dois usos:
  - Bando: no hub, os Pokémon andam sem parar, para um lado e para o outro e para cima e para
    baixo, só nas áreas livres: em volta do bloco central (título, busca e dica) e nas margens
    dos cards, nunca por cima deles. Cada um é um item do Canvas, abaixo dos widgets e dos
    textos. A quantidade acompanha o espaço livre e eles se revezam pelas laterais.
    Interações:
      * o ponteiro passa bem perto (ou por cima) de um deles: às vezes ele começa a seguir o
        ponteiro por alguns segundos; senão, dá um pulinho com um coração ou uma nota;
      * clique (em qualquer lugar do app) com Pokémon seguindo: eles dão um golpe na direção do
        ponteiro, junto com o clique, e sai uma faísca no ponto clicado;
      * clique em cima de um deles, no fundo do início: ele pula feliz (e às vezes vem junto);
      * dois que se encontram às vezes param, se olham e se cumprimentam.
    O clique é só observado (bind_all com add): nunca é consumido, então tudo continua
    funcionando igual por baixo dos Pokémon.
  - Companheiro: um Pokémon pequeno no canto direito do cabeçalho de cada tela de operação,
    andando de um lado para o outro num espaço só dele; pula ao passar o mouse e dá um golpe
    quando clicado.

Os dois só se mexem com a tela visível e com as animações ligadas (ver ui.animacao); com
movimento reduzido ficam parados, de frente, e não reagem. Com a visão para o cliente ligada
(janela de temas, ver App.definir_visao_cliente) nenhum deles aparece.
"""
import functools
import json
import math
import os
import random
import sys
import tkinter as tk
from collections import namedtuple

from core import preferencias
from ui import animacao
from ui.theme import COLORS, misturar

Pokemon = namedtuple("Pokemon", "arquivo numero nome grupo")

# Os 50 mais icônicos, por grupo. Número = Pokédex nacional (de onde vem o sprite).
POKEMON = tuple(Pokemon(*p) for p in (
    # Iniciais
    ("bulbasaur", 1, "Bulbasaur", "Inicial"),
    ("venusaur", 3, "Venusaur", "Inicial"),
    ("charmander", 4, "Charmander", "Inicial"),
    ("charizard", 6, "Charizard", "Inicial"),
    ("squirtle", 7, "Squirtle", "Inicial"),
    ("blastoise", 9, "Blastoise", "Inicial"),
    ("cyndaquil", 155, "Cyndaquil", "Inicial"),
    ("totodile", 158, "Totodile", "Inicial"),
    ("blaziken", 257, "Blaziken", "Inicial"),
    ("mudkip", 258, "Mudkip", "Inicial"),
    ("piplup", 393, "Piplup", "Inicial"),
    ("greninja", 658, "Greninja", "Inicial"),
    # Lendários
    ("articuno", 144, "Articuno", "Lendário"),
    ("zapdos", 145, "Zapdos", "Lendário"),
    ("moltres", 146, "Moltres", "Lendário"),
    ("mewtwo", 150, "Mewtwo", "Lendário"),
    ("suicune", 245, "Suicune", "Lendário"),
    ("lugia", 249, "Lugia", "Lendário"),
    ("hooh", 250, "Ho-Oh", "Lendário"),
    ("kyogre", 382, "Kyogre", "Lendário"),
    ("groudon", 383, "Groudon", "Lendário"),
    ("rayquaza", 384, "Rayquaza", "Lendário"),
    ("dialga", 483, "Dialga", "Lendário"),
    ("palkia", 484, "Palkia", "Lendário"),
    ("giratina", 487, "Giratina", "Lendário"),
    ("reshiram", 643, "Reshiram", "Lendário"),
    ("zekrom", 644, "Zekrom", "Lendário"),
    # Míticos
    ("mew", 151, "Mew", "Mítico"),
    ("celebi", 251, "Celebi", "Mítico"),
    ("jirachi", 385, "Jirachi", "Mítico"),
    ("deoxys", 386, "Deoxys", "Mítico"),
    ("darkrai", 491, "Darkrai", "Mítico"),
    ("arceus", 493, "Arceus", "Mítico"),
    ("victini", 494, "Victini", "Mítico"),
    # Clássicos e favoritos
    ("pikachu", 25, "Pikachu", "Clássico"),
    ("jigglypuff", 39, "Jigglypuff", "Clássico"),
    ("meowth", 52, "Meowth", "Clássico"),
    ("psyduck", 54, "Psyduck", "Clássico"),
    ("gengar", 94, "Gengar", "Clássico"),
    ("gyarados", 130, "Gyarados", "Clássico"),
    ("lapras", 131, "Lapras", "Clássico"),
    ("eevee", 133, "Eevee", "Clássico"),
    ("snorlax", 143, "Snorlax", "Clássico"),
    ("dragonite", 149, "Dragonite", "Clássico"),
    ("umbreon", 197, "Umbreon", "Clássico"),
    ("tyranitar", 248, "Tyranitar", "Clássico"),
    ("garchomp", 445, "Garchomp", "Clássico"),
    ("lucario", 448, "Lucario", "Clássico"),
    ("sylveon", 700, "Sylveon", "Clássico"),
    ("mimikyu", 778, "Mimikyu", "Clássico"),
))
POR_ARQUIVO = {p.arquivo: p for p in POKEMON}

# Animações usadas: nome aqui -> nome no PMD SpriteCollab
ANIMACOES = {"andar": "Walk", "golpe": "Attack", "pulo": "Hop"}

# Linhas das folhas, nesta ordem, e o passo (dx, dy) de cada direção
DIRECOES = ("baixo", "baixo-direita", "direita", "cima-direita", "cima", "cima-esquerda", "esquerda", "baixo-esquerda")
VETORES = ((0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1))
BAIXO, DIREITA, CIMA, ESQUERDA = 0, 2, 4, 6

FAIXA_LIVRE = 64         # px entre a dica e os cards no hub: o corredor por onde eles cruzam de um lado ao outro
ALTURA_COMPANHEIRO = 48  # os companheiros são sorteados entre os que cabem nesta altura

# Balõezinhos que aparecem sobre a cabeça (cores que funcionam no tema claro e no escuro)
CORES_EMOTE = {"♥": "#e8457b", "♪": "#3a9be0", "!": "#e09a00", "?": "#8a94a6", "…": "#8a94a6", "✦": "#f0a800"}
EMOTE_MS = 1100


_visao = {"escondidos": None}  # visão para o cliente (lida da preferência na 1ª vez)


def escondidos() -> bool:
    """Visão para o cliente ligada: nenhum Pokémon aparece (a tela pode estar sendo
    compartilhada com o cliente). Ver App.definir_visao_cliente."""
    if _visao["escondidos"] is None:
        _visao["escondidos"] = preferencias.obter("visao_cliente", False) is True
    return _visao["escondidos"]


def esconder(raiz, sim: bool):
    """Liga ou desliga a visão para o cliente na hora, sem recriar as telas: o bando some (ou
    volta) do início e os companheiros saem (ou voltam) dos cabeçalhos."""
    _visao["escondidos"] = bool(sim)
    for bando in list(getattr(raiz, "_pokemon_bandos", [])):
        try:
            bando.atualizar_visibilidade()
        except tk.TclError:  # hub já destruído
            pass
    vivos = []
    for companheiro in getattr(raiz, "_pokemon_companheiros", []):
        try:
            if companheiro.winfo_exists():
                companheiro.atualizar_visibilidade()
                vivos.append(companheiro)
        except tk.TclError:
            pass
    raiz._pokemon_companheiros = vivos


def pasta() -> str:
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(getattr(sys, "_MEIPASS", raiz), "assets", "pokemon")


def caminho(arquivo: str, anim: str = "andar") -> str:
    return os.path.join(pasta(), f"{arquivo}-{anim}.png")


@functools.lru_cache(maxsize=None)
def _dados():
    try:
        with open(os.path.join(pasta(), "animacoes.json"), encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return {}


def disponiveis():
    """Pokémon do catálogo com todas as animações presentes."""
    dados = _dados()
    return [p.arquivo for p in POKEMON
            if p.arquivo in dados and all(os.path.exists(caminho(p.arquivo, a)) for a in ANIMACOES)]


def tamanho(arquivo):
    """(largura, altura) do Pokémon andando (a mesma nas 8 direções)."""
    largura, altura, _dx, _dy = _dados()[arquivo]["andar"]["linhas"][0]
    return largura, altura


def companheiros():
    """Os que cabem no cabeçalho das telas."""
    return [a for a in disponiveis() if tamanho(a)[1] <= ALTURA_COMPANHEIRO]


def direcao_para(vx, vy):
    """A direção (das 8) mais parecida com o vetor (vx, vy)."""
    if not vx and not vy:
        return BAIXO
    return max(range(len(VETORES)), key=lambda d: (VETORES[d][0] * vx + VETORES[d][1] * vy)
               / math.hypot(*VETORES[d]))


class Animacao:
    """Os quadros de uma animação de um Pokémon: quadros[direção][i]. Cada direção tem o seu
    tamanho de quadro e o seu (dx, dy): onde o canto do quadro fica em relação ao centro do
    corpo, o mesmo ponto em todas as animações. No andar, tamanho e (dx, dy) são os mesmos nas
    8 direções (largura, altura, dx e dy)."""

    def __init__(self, master, arquivo, nome, guardar=False):
        dados = _dados()[arquivo][nome]
        self.duracoes = dados["duracoes"]  # ms de cada quadro
        self.linhas = [tuple(linha) for linha in dados["linhas"]]  # (largura, altura, dx, dy) por direção
        self.largura, self.altura, self.dx, self.dy = self.linhas[0]
        self.impacto = dados.get("impacto")  # no golpe: o quadro em que ele "acerta"
        self._guardiao = _guardiao(master) if guardar else None
        self._guardados = []
        folha = tk.PhotoImage(master=master, file=caminho(arquivo, nome))
        self.quadros = []
        topo = 0
        for largura, altura, _dx, _dy in self.linhas:
            fila = []
            for coluna in range(len(self.duracoes)):
                quadro = tk.PhotoImage(master=master, width=largura, height=altura)
                x = coluna * largura
                quadro.tk.call(quadro, "copy", folha, "-from", x, topo, x + largura, topo + altura)
                fila.append(quadro)
                if self._guardiao is not None:
                    # O Tk descarta a versão pronta para a tela de uma imagem que deixou de ser
                    # usada e a refaz no próximo uso: trocar de quadro a cada passo custaria isso
                    # toda vez. Um item por quadro num Canvas que nunca é mostrado mantém todas
                    # prontas. (Só no andar, que troca de quadro o tempo todo; golpe e pulo são
                    # raros e curtos.)
                    self._guardados.append(self._guardiao.create_image(0, 0, image=quadro))
            self.quadros.append(fila)
            topo += altura

    def deslocamento(self, direcao):
        return self.linhas[direcao][2:]

    def liberar(self):
        if self._guardados:
            try:
                self._guardiao.delete(*self._guardados)
            except tk.TclError:
                pass
        self._guardados, self.quadros = [], []

    def quadro_em(self, ms):
        """Índice do quadro no instante `ms` desde o início, ou None se a animação acabou."""
        for i, duracao in enumerate(self.duracoes):
            if ms < duracao:
                return i
            ms -= duracao
        return None


def _guardiao(master) -> tk.Canvas:
    raiz = master._root()
    if not hasattr(raiz, "_pokemon_guardiao"):
        raiz._pokemon_guardiao = tk.Canvas(raiz)  # nunca entra no layout
    return raiz._pokemon_guardiao


class _Animacoes(dict):
    """As animações de um Pokémon ({nome: Animacao}), cada uma carregada na primeira vez que é
    usada (golpe e pulo podem nem chegar a ser)."""

    def __init__(self, raiz, arquivo):
        super().__init__()
        self.raiz, self.arquivo, self.usos = raiz, arquivo, 0

    def __missing__(self, nome):
        anim = self[nome] = Animacao(self.raiz, self.arquivo, nome, guardar=nome == "andar")
        return anim

    def liberar(self):
        for anim in self.values():
            anim.liberar()
        self.clear()


def pegar(master, arquivo) -> _Animacoes:
    """As animações de um Pokémon, compartilhadas na janela principal (o hub e as telas usam as
    mesmas). Quem pega devolve com soltar(): quando ninguém mais usa, a memória é liberada (são
    50 Pokémon, mas só os que estão na tela ficam carregados)."""
    raiz = master._root()
    if not hasattr(raiz, "_pokemon_animacoes"):
        raiz._pokemon_animacoes = {}
    if arquivo not in raiz._pokemon_animacoes:
        raiz._pokemon_animacoes[arquivo] = _Animacoes(raiz, arquivo)
    anims = raiz._pokemon_animacoes[arquivo]
    anims.usos += 1
    return anims


def soltar(master, arquivo):
    raiz = master._root()
    anims = getattr(raiz, "_pokemon_animacoes", {}).get(arquivo)
    if anims is not None:
        anims.usos -= 1
        if anims.usos <= 0:
            anims.liberar()
            del raiz._pokemon_animacoes[arquivo]


class _Passos:
    """Avança os quadros da animação de andar conforme o tempo de cada um."""

    def __init__(self, anim):
        self.anim = anim
        self.quadro = 0
        self.no_quadro = random.randint(0, self.anim.duracoes[0])  # desencontra os passos de um e outro

    def avancar(self, ms) -> bool:
        self.no_quadro += ms
        mudou = False
        while self.no_quadro >= self.anim.duracoes[self.quadro]:
            self.no_quadro -= self.anim.duracoes[self.quadro]
            self.quadro = (self.quadro + 1) % len(self.anim.duracoes)
            mudou = True
        return mudou


def _cruza(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _excesso(caixa, limites):
    """Quanto a caixa passa dos limites (0 = toda dentro)."""
    return (max(0, limites[0] - caixa[0]) + max(0, caixa[2] - limites[2])
            + max(0, limites[1] - caixa[1]) + max(0, caixa[3] - limites[3]))


def _segmento_cruza(x0, y0, x1, y1, r):
    """O segmento (x0, y0)-(x1, y1) passa pelo retângulo r? (Liang-Barsky)"""
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - r[0]), (dx, r[2] - x0), (-dy, y0 - r[1]), (dy, r[3] - y0)):
        if p == 0:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return False
    return True


def _rota(inicio, alvo, largura, altura, limites, proibidos, grade):
    """Caminho (lista de centros) numa grade de `grade` px, só por onde uma caixa largura x
    altura cabe, de `inicio` até o ponto alcançável mais perto de `alvo` (busca em largura, com
    diagonais sem cortar quina). Lista vazia: já está no ponto mais perto."""
    x0, y0 = limites[0], limites[1]
    colunas = max(1, int((limites[2] - x0) // grade))
    linhas = max(1, int((limites[3] - y0) // grade))

    def centro(c):
        return x0 + (c[0] + 0.5) * grade, y0 + (c[1] + 0.5) * grade

    livres = {}

    def livre(c):
        if c not in livres:
            cx, cy = centro(c)
            caixa = (cx - largura / 2, cy - altura / 2, cx + largura / 2, cy + altura / 2)
            livres[c] = (0 <= c[0] < colunas and 0 <= c[1] < linhas and _excesso(caixa, limites) == 0
                         and not any(_cruza(caixa, p) for p in proibidos))
        return livres[c]

    def celula(x, y):
        return (min(colunas - 1, max(0, int((x - x0) // grade))), min(linhas - 1, max(0, int((y - y0) // grade))))

    comeco, destino = celula(*inicio), celula(*alvo)
    anterior = {comeco: None}
    fila = [comeco]
    melhor, melhor_dist = comeco, math.dist(centro(comeco), alvo)
    for atual in fila:  # a lista cresce durante o laço: é a fila da busca em largura
        if atual == destino:
            melhor = atual
            break
        for dx, dy in VETORES:
            vizinha = (atual[0] + dx, atual[1] + dy)
            if vizinha in anterior or not livre(vizinha):
                continue
            if dx and dy and not (livre((atual[0] + dx, atual[1])) and livre((atual[0], atual[1] + dy))):
                continue
            anterior[vizinha] = atual
            fila.append(vizinha)
            distancia = math.dist(centro(vizinha), alvo)
            if distancia < melhor_dist:
                melhor, melhor_dist = vizinha, distancia
    caminho = []
    while melhor is not None and melhor != comeco:
        caminho.append(centro(melhor))
        melhor = anterior[melhor]
    return caminho[::-1]


class Andarilho:
    """Um Pokémon do bando: anda numa direção, vira de tempos em tempos e desvia do que é
    proibido (bloco central e cards) e das bordas da área visível. Também segue o ponteiro,
    golpeia, pula e cumprimenta (ver Bando)."""

    def __init__(self, bando, arquivo, x, y, direcao, entrando=False):
        self.bando, self.arquivo = bando, arquivo
        self.anims = pegar(bando.canvas, arquivo)
        self.folha = self.anims["andar"]  # a animação de andar: a caixa dela é a que anda e colide
        self.passos = _Passos(self.folha)
        self.x, self.y = float(x), float(y)  # canto da caixa de andar
        self.direcao = direcao
        self.entrando, self.saindo, self.saiu = entrando, False, False
        self.velocidade = random.uniform(*Bando.VELOCIDADE)
        self.ate_virar = random.randint(*Bando.VIRA_MS)
        self.ate_sair = random.randint(*Bando.PERMANENCIA_MS)
        self.parado_ms = 0           # preso sem conseguir andar (vai embora se durar)
        self.acao, self.acao_ms, self._ao_acertar = None, 0, None  # golpe ou pulo em curso
        self.seguindo_ms = 0         # > 0: seguindo o ponteiro
        self.sem_ponteiro_ms = 0
        self.espera_ms = 0           # descanso: não reage ao ponteiro de novo logo em seguida
        self.encontro_ms = random.randint(4000, 12000)  # até poder cumprimentar outro
        self.pausa_ms = 0            # parado de propósito (cumprimentando)
        self.desvio = random.choice((1, -1))  # para que lado contorna um obstáculo ao seguir
        self._caminho, self._caminho_ms = [], 0  # rota até o ponteiro quando a linha reta está bloqueada
        self.emote = None            # [item, ms restantes]
        self.item = bando.canvas.create_image(0, 0, anchor="nw", image=self._imagem(), tags=("pokemon",))
        bando.canvas.tag_lower(self.item)  # atrás de todos os textos
        self._posicionar()

    # ------------------------------------------------------------- posição
    @property
    def caixa(self):
        return (self.x, self.y, self.x + self.folha.largura, self.y + self.folha.altura)

    @property
    def centro(self):
        return self.x + self.folha.largura / 2, self.y + self.folha.altura / 2

    def _anim(self):
        return self.anims[self.acao] if self.acao else self.folha

    def _imagem(self):
        if self.acao:
            anim = self.anims[self.acao]
            return anim.quadros[self.direcao][anim.quadro_em(self.acao_ms) or 0]
        return self.folha.quadros[self.direcao][self.passos.quadro]

    def _posicionar(self):
        """Põe o item no lugar: o centro do corpo é o mesmo em todas as animações."""
        dx, dy = self._anim().deslocamento(self.direcao)
        x = self.x - self.folha.dx + dx
        y = self.y - self.folha.dy + dy
        self.bando.canvas.coords(self.item, round(x), round(y))
        if self.emote:
            self._posicionar_emote()

    # -------------------------------------------------------- movimentação
    def _pode(self, x, y, limites, proibidos):
        caixa = (x, y, x + self.folha.largura, y + self.folha.altura)
        if any(_cruza(caixa, p) for p in proibidos):
            return False
        if self.saindo:  # saindo: pode deixar a área visível
            return True
        fora = _excesso(caixa, limites)
        return fora == 0 or fora < _excesso(self.caixa, limites)  # fora dos limites, só voltando para dentro

    def _livre(self, direcao, limites, proibidos):
        """Livre para dar um passo e ainda alguns adiante (para não ficar batendo e voltando)."""
        dx, dy = self._passo(direcao)
        return self._pode(self.x + dx, self.y + dy, limites, proibidos) and \
            self._pode(self.x + 6 * dx, self.y + 6 * dy, limites, proibidos)

    def _passo(self, direcao, rapido=False):
        dx, dy = VETORES[direcao]
        fator = self.velocidade * (Bando.RAPIDO if rapido else 1) / (math.sqrt(2) if dx and dy else 1)
        return dx * fator, dy * fator

    def _escolher(self, limites, proibidos, evitar=None):
        opcoes = [d for d in range(len(DIRECOES)) if d != evitar]
        random.shuffle(opcoes)
        livres = [d for d in opcoes if self._livre(d, limites, proibidos)]
        return livres[0] if livres else None

    def _rumo_da_saida(self):
        return ESQUERDA if self.centro[0] < self.bando.canvas.winfo_width() / 2 else DIREITA

    def _vagar(self, ms, limites, proibidos):
        """Passo de quem está passeando (ou indo embora). Devolve (dx, dy)."""
        if not self.saindo:
            self.ate_sair -= ms
            self.ate_virar -= ms
            if self.ate_sair <= 0 or self.parado_ms > 1500:  # deu o tempo dele (ou ficou preso): vai embora
                self.saindo = True
                self.direcao = self._rumo_da_saida()
            elif self.ate_virar <= 0:
                self.ate_virar = random.randint(*Bando.VIRA_MS)
                self.direcao = self._escolher(limites, proibidos, evitar=self.direcao) or self.direcao
        elif self.direcao != self._rumo_da_saida():  # contornando algo: volta ao rumo da saída assim que der
            rumo = self._rumo_da_saida()
            dx, dy = self._passo(rumo)
            if self._pode(self.x + dx, self.y + dy, limites, proibidos):
                self.direcao = rumo
        dx, dy = self._passo(self.direcao)
        if not self._pode(self.x + dx, self.y + dy, limites, proibidos):
            # caminho fechado: outro rumo livre (quem está saindo tenta antes os que levam à lateral)
            if self.saindo:
                rumo = self._rumo_da_saida()
                tentativas = ((rumo + 1) % 8, (rumo - 1) % 8, BAIXO, CIMA)
                nova = next((d for d in tentativas if self._livre(d, limites, proibidos)), None)
            else:
                nova = self._escolher(limites, proibidos)
            if nova is None:
                self.parado_ms += ms
                return 0, 0
            self.direcao = nova
            dx, dy = self._passo(nova)
        self.parado_ms = 0
        return dx, dy

    def _rumo_ao_ponteiro(self, ms, limites, proibidos, ponteiro):
        """Passo de quem está seguindo o ponteiro. Para perto dele, olhando para ele; contorna o
        que estiver no caminho (sem nunca entrar no bloco central nem nos cards)."""
        self.seguindo_ms -= ms
        self.sem_ponteiro_ms = 0 if ponteiro else self.sem_ponteiro_ms + ms
        if self.seguindo_ms <= 0 or self.sem_ponteiro_ms > 1500:
            self.parar_de_seguir()
            return 0, 0
        if ponteiro is None:
            return 0, 0
        cx, cy = self.centro
        vx, vy = ponteiro[0] - cx, ponteiro[1] - cy
        if math.hypot(vx, vy) < Bando.DISTANCIA_DO_PONTEIRO + self.folha.largura / 2:
            self.direcao = direcao_para(vx, vy)  # chegou: fica olhando para o ponteiro
            self._caminho = []
            return 0, 0
        # Linha reta livre até o ponteiro (considerando o tamanho dele)? Vai direto. Senão (o
        # bloco central ou os cards no meio), segue um caminho pela grade das áreas livres,
        # refeito no máximo a cada CAMINHO_MS.
        meia_w, meia_h = self.folha.largura / 2, self.folha.altura / 2
        bloqueado = any(_segmento_cruza(cx, cy, ponteiro[0], ponteiro[1],
                                        (p[0] - meia_w, p[1] - meia_h, p[2] + meia_w, p[3] + meia_h))
                        for p in proibidos)
        alvo = ponteiro
        if bloqueado:
            self._caminho_ms -= ms
            if self._caminho_ms <= 0 or not self._caminho:
                self._caminho = _rota((cx, cy), ponteiro, self.folha.largura, self.folha.altura,
                                      limites, proibidos, Bando.GRADE)
                self._caminho_ms = Bando.CAMINHO_MS
            while self._caminho and math.dist(self._caminho[0], (cx, cy)) < Bando.GRADE / 2:
                self._caminho.pop(0)
            if not self._caminho:  # já está no ponto alcançável mais perto (ponteiro sobre um card, por ex.)
                self.direcao = direcao_para(vx, vy)
                return 0, 0
            alvo = self._caminho[0]
        else:
            self._caminho = []
        self.direcao = direcao_para(alvo[0] - cx, alvo[1] - cy)
        for virada in (0, self.desvio, -self.desvio, 2 * self.desvio, -2 * self.desvio):
            direcao = (self.direcao + virada) % 8
            dx, dy = self._passo(direcao, rapido=True)
            if self._pode(self.x + dx, self.y + dy, limites, proibidos):
                if virada:
                    self.direcao = direcao
                return dx, dy
        self.desvio = -self.desvio  # encurralado: na próxima tenta contornar pelo outro lado
        return 0, 0

    # ------------------------------------------------------------- interações
    def fazer(self, acao, direcao=None, ao_acertar=None):
        """Começa um golpe ou um pulo (no lugar, sem andar), na direção dada."""
        if direcao is not None:
            self.direcao = direcao
        self.acao, self.acao_ms, self._ao_acertar = acao, 0, ao_acertar
        self._atualizar()

    def mostrar(self, simbolo):
        """Balãozinho sobre a cabeça (♥, ♪, !, ?...), que sobe um pouco e some."""
        canvas = self.bando.canvas
        if self.emote:
            canvas.delete(self.emote[0])
        item = canvas.create_text(0, 0, text=simbolo, fill=CORES_EMOTE.get(simbolo, COLORS["accent"]),
                                  font=("Segoe UI Symbol", 13, "bold"), anchor="s", tags=("pokemon_fx",))
        self.emote = [item, EMOTE_MS]
        self._posicionar_emote()

    def _posicionar_emote(self):
        item, resta = self.emote
        sobe = (1 - resta / EMOTE_MS) * 8
        self.bando.canvas.coords(item, round(self.centro[0]), round(self.y - 1 - sobe))

    def reagir(self, simbolo=None):
        """Pulinho com um balão (o ponteiro passou por cima, ou clicaram nele)."""
        self.mostrar(simbolo or random.choice("♥♪!"))
        self.fazer("pulo")

    def comecar_a_seguir(self):
        self.seguindo_ms = random.randint(*Bando.SEGUIR_MS)
        self.sem_ponteiro_ms = 0
        self.mostrar("!")
        self.fazer("pulo")

    def parar_de_seguir(self):
        self.seguindo_ms = 0
        self.espera_ms = random.randint(*Bando.DESCANSO_MS)  # cansou: um tempo sem seguir de novo
        self.ate_virar = 0
        self.mostrar(random.choice("?…"))

    def cumprimentar(self, outro):
        """Encontrou outro: olha para ele, pula e mostra um balão; depois cada um segue seu rumo."""
        self.direcao = DIREITA if outro.centro[0] > self.centro[0] else ESQUERDA
        self.pausa_ms = 1300
        self.encontro_ms = random.randint(*Bando.ENCONTRO_MS)
        self.mostrar(random.choice("♥♪!"))
        self.fazer("pulo")

    @property
    def ocupado(self):
        return bool(self.acao or self.seguindo_ms > 0 or self.pausa_ms > 0 or self.saindo or self.entrando)

    # ----------------------------------------------------------------- quadro
    def _atualizar(self):
        self.bando.canvas.itemconfigure(self.item, image=self._imagem())
        self._posicionar()

    def andar(self, ms, limites, proibidos, ponteiro=None):
        self.espera_ms = max(0, self.espera_ms - ms)
        self.encontro_ms -= ms
        if self.emote:
            self.emote[1] -= ms
            if self.emote[1] <= 0:
                self.bando.canvas.delete(self.emote[0])
                self.emote = None
            else:
                self._posicionar_emote()
        if self.acao:  # golpe ou pulo: só a animação, no lugar
            anim = self.anims[self.acao]
            antes = anim.quadro_em(self.acao_ms)
            self.acao_ms += ms
            agora = anim.quadro_em(self.acao_ms)
            if self._ao_acertar and anim.impacto is not None and (agora is None or agora >= anim.impacto):
                self._ao_acertar()
                self._ao_acertar = None
            if agora is None:
                self.acao = None
                self._atualizar()
            elif agora != antes:
                self.bando.canvas.itemconfigure(self.item, image=self._imagem())
            return
        direcao_antes = self.direcao
        if self.pausa_ms > 0:
            self.pausa_ms -= ms
            if self.pausa_ms <= 0:
                self.ate_virar = 0
            dx = dy = 0
        elif self.seguindo_ms > 0:
            dx, dy = self._rumo_ao_ponteiro(ms, limites, proibidos, ponteiro)
        else:
            dx, dy = self._vagar(ms, limites, proibidos)
        if dx or dy:
            self.x += dx
            self.y += dy
            self._posicionar()
        if self.entrando and _excesso(self.caixa, limites) == 0:
            self.entrando = False
        if self.saindo:
            self.saiu = self.x + self.folha.largura < limites[0] or self.x > limites[2] or not _cruza(self.caixa, limites)
        andou = self.passos.avancar(ms) if (dx or dy) else False
        if not (dx or dy) and self.passos.quadro:  # parado: de pé
            self.passos.quadro, andou = 0, True
        if andou or self.direcao != direcao_antes:
            self.bando.canvas.itemconfigure(self.item, image=self._imagem())

    def parado(self):
        """Movimento reduzido: de frente, sem andar."""
        if self.acao or self.direcao != BAIXO or self.passos.quadro:
            self.acao, self.direcao, self.passos.quadro = None, BAIXO, 0
            self.seguindo_ms = 0
            self._atualizar()
        if self.emote:
            self.bando.canvas.delete(self.emote[0])
            self.emote = None

    def apagar(self):
        self.bando.canvas.delete(self.item)
        if self.emote:
            self.bando.canvas.delete(self.emote[0])
        soltar(self.bando.canvas, self.arquivo)


def _registrar_clique(bando):
    """Um só bind_all por janela, que repassa o clique aos bandos vivos (o hub é recriado na
    troca de tema). Só observa: nunca devolve "break", o clique segue para o widget."""
    raiz = bando.canvas._root()
    if not hasattr(raiz, "_pokemon_bandos"):
        raiz._pokemon_bandos = []

        def ao_clicar(evento):
            vivos = []
            for b in raiz._pokemon_bandos:
                try:
                    if b.canvas.winfo_exists():
                        vivos.append(b)
                        b.clique(evento.x_root, evento.y_root, evento.widget)
                except tk.TclError:
                    pass
            raiz._pokemon_bandos = vivos

        raiz.bind_all("<Button-1>", ao_clicar, add="+")
    raiz._pokemon_bandos.append(bando)


class Bando:
    """Os Pokémon que andam pelo hub. `area` é uma função que devolve (limites, proibidos): o
    retângulo visível onde eles podem andar e os retângulos que eles nunca cobrem, o primeiro
    deles o bloco central com os textos (ver _passo)."""

    TICK_MS = 66                        # 15 quadros por segundo: suficiente para pixel art, leve para a CPU
    AREA_POR_POKEMON = 12000            # px² de área livre por Pokémon na tela (maior = menos Pokémon)
    PERMANENCIA_MS = (60000, 150000)    # quanto tempo cada um passeia antes de sair e dar a vez
    VIRA_MS = (1200, 4000)              # de quanto em quanto tempo escolhe outra direção
    VELOCIDADE = (1.3, 2.4)             # px por quadro (20 a 36 px por segundo)
    RAPIDO = 1.6                        # seguindo o ponteiro andam mais rápido
    FOLGA = 4                           # px de distância dos retângulos proibidos
    PERTO = 14                          # px: quão perto o ponteiro precisa passar para notarem
    CHANCE_SEGUIR = 0.45                # chance de seguir (senão, só pula)
    MAX_SEGUIDORES = 3
    SEGUIR_MS = (6000, 14000)           # quanto tempo seguem
    DESCANSO_MS = (15000, 30000)        # depois de seguir, até poder seguir de novo
    DISTANCIA_DO_PONTEIRO = 14          # px entre a borda do Pokémon e o ponteiro, ao parar
    GRADE = 20                          # px da grade usada para contornar o bloco central e os cards
    CAMINHO_MS = 500                    # de quanto em quanto tempo a rota é refeita (o ponteiro se mexe)
    ENCONTRO_MS = (20000, 40000)        # depois de cumprimentar, até poder cumprimentar de novo
    CHANCE_CUMPRIMENTO = 0.4

    def __init__(self, canvas, area):
        self.canvas = canvas
        self.area = area
        self.andarilhos = []
        self.efeitos = []  # faíscas e ondas dos cliques: [item, ms, duração, tipo, x, y]
        self._fila = []
        self._tick = 0
        self._povoado = False
        _registrar_clique(self)
        canvas.bind("<Destroy>", self._ao_destruir, add="+")
        animacao.depois(canvas, 200, self._quadro)

    def _ao_destruir(self, evento):
        """Hub recriado (troca de tema) ou app fechando: devolve as animações de todos."""
        if evento.widget is self.canvas:
            for a in self.andarilhos:
                soltar(self.canvas, a.arquivo)
            self.andarilhos = []

    # ---------------------------------------------------------------- quem anda
    def _proximo(self):
        """Próximo da fila sorteada; só repete depois de todos passarem (e nunca dois iguais na tela)."""
        na_tela = {a.arquivo for a in self.andarilhos}
        for _ in range(2):
            while self._fila:
                arquivo = self._fila.pop()
                if arquivo not in na_tela:
                    return arquivo
            self._fila = disponiveis()
            random.shuffle(self._fila)
        return None

    def quantos_cabem(self, limites, proibidos):
        largura, altura = limites[2] - limites[0], limites[3] - limites[1]
        livre = largura * altura
        for p in proibidos:
            dx = max(0, min(p[2], limites[2]) - max(p[0], limites[0]))
            dy = max(0, min(p[3], limites[3]) - max(p[1], limites[1]))
            livre -= dx * dy
        return max(0, min(len(disponiveis()), int(livre // self.AREA_POR_POKEMON)))

    def _lugar_livre(self, w, h, limites, proibidos, tentativas=200):
        for _ in range(tentativas):
            x = random.uniform(limites[0], max(limites[0], limites[2] - w))
            y = random.uniform(limites[1], max(limites[1], limites[3] - h))
            caixa = (x, y, x + w, y + h)
            if _excesso(caixa, limites) == 0 and not any(_cruza(caixa, p) for p in proibidos) \
                    and not any(_cruza(caixa, a.caixa) for a in self.andarilhos):
                return x, y
        return None

    def _entrada(self, w, h, limites, proibidos):
        """Um ponto logo fora de uma das laterais, de onde dá para entrar andando."""
        for _ in range(60):
            da_esquerda = random.random() < 0.5
            y = random.uniform(limites[1], max(limites[1], limites[3] - h))
            x = limites[0] - w if da_esquerda else limites[2]
            x_dentro = limites[0] if da_esquerda else limites[2] - w
            corredor = (min(x, x_dentro), y, max(x, x_dentro) + w, y + h)
            if not any(_cruza(corredor, p) for p in proibidos):
                return x, y, DIREITA if da_esquerda else ESQUERDA
        return None

    def _povoar(self, limites, proibidos):
        alvo = self.quantos_cabem(limites, proibidos)
        ativos = [a for a in self.andarilhos if not a.saindo]
        if len(ativos) > alvo:  # a janela diminuiu: os que sobram vão embora
            for a in ativos[alvo:]:
                a.saindo, a.seguindo_ms = True, 0
        elif len(ativos) < alvo:
            # na primeira vez já aparecem espalhados; depois, entra um de cada vez pela lateral
            for _ in range(alvo - len(ativos) if not self._povoado else 1):
                arquivo = self._proximo()
                if arquivo is None:
                    break
                w, h = tamanho(arquivo)
                if not self._povoado:
                    lugar = self._lugar_livre(w, h, limites, proibidos)
                    if lugar:
                        self.andarilhos.append(Andarilho(self, arquivo, *lugar, random.randrange(len(DIRECOES))))
                else:
                    entrada = self._entrada(w, h, limites, proibidos)
                    if entrada:
                        self.andarilhos.append(Andarilho(self, arquivo, *entrada, entrando=True))
        self._povoado = True

    def _ordenar(self, grupo):
        """Quem está mais embaixo passa na frente (profundidade), e todos ficam atrás dos textos.
        Só mexe na ordem quando ela mudou (mexer faz o Tk redesenhar)."""
        posicao = {item: i for i, item in enumerate(self.canvas.find_all())}
        desejada = sorted(grupo, key=lambda a: a.y + a.folha.altura)
        if desejada != sorted(grupo, key=lambda a: posicao.get(a.item, 0)):
            for a in reversed(desejada):  # cada um vai para o fundo: o de cima por último
                self.canvas.tag_lower(a.item)

    # ----------------------------------------------------------- ponteiro e clique
    def _para_canvas(self, x_tela, y_tela):
        """Ponto da tela em coordenadas do canvas, ou None se estiver fora dele."""
        c = self.canvas
        x, y = x_tela - c.winfo_rootx(), y_tela - c.winfo_rooty()
        if not (0 <= x < c.winfo_width() and 0 <= y < c.winfo_height()):
            return None
        return c.canvasx(x), c.canvasy(y)

    def _ponteiro(self):
        """Onde está o ponteiro no canvas (None se estiver fora dele, ou com outra janela por cima)."""
        x, y = self.canvas.winfo_pointerxy()
        ponto = self._para_canvas(x, y)
        if ponto is None or self.canvas.winfo_containing(x, y) is None:
            return None
        return ponto

    def _notar(self, ponteiro):
        """O ponteiro passou bem perto ou por cima: alguns começam a seguir, os outros pulam."""
        px, py = ponteiro
        seguidores = sum(1 for a in self.andarilhos if a.seguindo_ms > 0)
        for a in self.andarilhos:
            if a.espera_ms > 0 or a.ocupado:
                continue
            x0, y0, x1, y1 = a.caixa
            if x0 - self.PERTO <= px <= x1 + self.PERTO and y0 - self.PERTO <= py <= y1 + self.PERTO:
                if seguidores < self.MAX_SEGUIDORES and random.random() < self.CHANCE_SEGUIR:
                    a.comecar_a_seguir()
                    seguidores += 1
                else:
                    a.reagir()
                    a.espera_ms = 4000

    def clique(self, x_tela, y_tela, widget=None):
        """Clique em qualquer lugar do app (repassado pelo bind_all): quem está seguindo golpeia
        na direção do ponteiro, junto com o clique; clicar em cima de um, no fundo do início,
        faz ele pular feliz."""
        if escondidos() or not animacao.ativas() or not self.canvas.winfo_viewable():
            return
        ponto = self._para_canvas(x_tela, y_tela)
        if ponto is None:
            return
        seguidores = [a for a in self.andarilhos if a.seguindo_ms > 0 and not a.acao]
        for a in seguidores:
            cx, cy = a.centro
            a.seguindo_ms += 1500  # o clique prende a atenção dele mais um pouco
            a.fazer("golpe", direcao_para(ponto[0] - cx, ponto[1] - cy),
                    ao_acertar=lambda: self._efeito("faisca", *ponto))
        if seguidores:
            self._efeito("onda", *ponto)
        if widget is self.canvas:  # no fundo do início (não num card, botão ou campo)
            for a in self.andarilhos:
                x0, y0, x1, y1 = a.caixa
                if x0 - 4 <= ponto[0] <= x1 + 4 and y0 - 4 <= ponto[1] <= y1 + 4 and not a.acao \
                        and not a.saindo and not a.entrando:
                    a.reagir("♥")
                    if a.seguindo_ms <= 0 and random.random() < 0.6 and \
                            sum(1 for b in self.andarilhos if b.seguindo_ms > 0) < self.MAX_SEGUIDORES:
                        a.seguindo_ms = random.randint(*self.SEGUIR_MS)

    def _efeito(self, tipo, x, y):
        """Onda (anel que abre e some) no clique, faísca (✦) quando o golpe acerta."""
        c = self.canvas
        if tipo == "onda":
            item = c.create_oval(x - 3, y - 3, x + 3, y + 3, outline=COLORS["accent"], width=2, tags=("pokemon_fx",))
            duracao = 420
        else:
            x += random.uniform(-6, 6)
            y += random.uniform(-6, 6)
            item = c.create_text(x, y, text="✦", fill=CORES_EMOTE["✦"], font=("Segoe UI Symbol", 14, "bold"),
                                 tags=("pokemon_fx",))
            duracao = 380
        self.efeitos.append([item, 0, duracao, tipo, x, y])

    def _animar_efeitos(self, ms):
        vivos = []
        for efeito in self.efeitos:
            item, passado, duracao, tipo, x, y = efeito
            passado += ms
            if passado >= duracao:
                self.canvas.delete(item)
                continue
            efeito[1] = passado
            p = passado / duracao
            cor_base = COLORS["accent"] if tipo == "onda" else CORES_EMOTE["✦"]
            cor = misturar(cor_base, COLORS["bg"], 1 - p)
            if tipo == "onda":
                raio = 3 + 19 * (1 - (1 - p) ** 2)
                self.canvas.coords(item, x - raio, y - raio, x + raio, y + raio)
                self.canvas.itemconfigure(item, outline=cor)
            else:
                self.canvas.coords(item, x, y - 10 * p)
                self.canvas.itemconfigure(item, fill=cor)
            vivos.append(efeito)
        self.efeitos = vivos

    def _encontros(self):
        """Dois que passeiam e se esbarram às vezes param para se cumprimentar."""
        livres = [a for a in self.andarilhos if not a.ocupado and a.encontro_ms <= 0]
        for i, a in enumerate(livres):
            ax, ay = a.centro
            for b in livres[i + 1:]:
                if b.encontro_ms > 0:
                    continue
                bx, by = b.centro
                if abs(ax - bx) < (a.folha.largura + b.folha.largura) / 2 + 10 and abs(ay - by) < 16:
                    if random.random() < self.CHANCE_CUMPRIMENTO:
                        a.cumprimentar(b)
                        b.cumprimentar(a)
                    else:
                        a.encontro_ms = b.encontro_ms = 3000
                    break

    # ------------------------------------------------------------------ quadros
    def _quadro(self):
        espera = self.TICK_MS
        try:
            espera = self._passo()
        finally:  # um erro num quadro não pode parar o bando de vez
            animacao.depois(self.canvas, espera, self._quadro)

    def atualizar_visibilidade(self):
        """Visão para o cliente: some com todos (e os efeitos) na hora. Ao voltar, o próximo
        quadro já os põe espalhados de novo."""
        if escondidos():
            for a in self.andarilhos:
                a.apagar()
            for efeito in self.efeitos:
                self.canvas.delete(efeito[0])
            self.andarilhos, self.efeitos = [], []
        self._povoado = False
        self._tick = 0  # povoa no próximo quadro

    def _passo(self):
        """Um quadro: povoa, anda e devolve quantos ms esperar até o próximo."""
        if escondidos():  # visão para o cliente: nenhum Pokémon
            if self.andarilhos or self.efeitos:
                self.atualizar_visibilidade()
            return 400
        if not self.canvas.winfo_viewable():  # hub escondido: não gasta nada, só confere de novo
            return 300
        limites, proibidos = self.area()
        if limites[2] - limites[0] < 50 or limites[3] - limites[1] < 50:  # ainda sem tamanho
            return 200
        proibidos = [(p[0] - self.FOLGA, p[1] - self.FOLGA, p[2] + self.FOLGA, p[3] + self.FOLGA) for p in proibidos]
        ativas = animacao.ativas()
        if self._tick % 20 == 0 and (ativas or not self._povoado):  # a cada segundo
            self._povoar(limites, proibidos)
        self._tick += 1
        if not ativas:
            for a in self.andarilhos:
                a.parado()
            return 500
        ponteiro = self._ponteiro()
        if ponteiro:
            self._notar(ponteiro)
        if self._tick % 10 == 0:
            self._encontros()
        conferir = self._tick % 5 == 0
        for grupo in self._grupos(proibidos[0]):
            for a in grupo:
                # perdido: ficou fora da área visível (rolagem) ou embaixo do que é proibido (mudou o layout)
                perdido = conferir and not a.entrando and not a.saindo and (
                    not _cruza(a.caixa, limites) or any(_cruza(a.caixa, p) for p in proibidos))
                a.andar(self.TICK_MS, limites, proibidos, ponteiro)
                if a.saiu or perdido:
                    a.apagar()
                    self.andarilhos.remove(a)
            if self._tick % 10 == 0:
                self._ordenar([a for a in grupo if a in self.andarilhos])
            # O Tk redesenha de uma vez o retângulo que cobre tudo o que mudou. Com os Pokémon dos
            # dois lados, esse retângulo passaria pelo título, e redesenhar o texto grande a cada
            # quadro é o que mais pesa. Redesenhando grupo a grupo, o texto fica de fora.
            self.canvas.update_idletasks()
        if self.efeitos:
            self._animar_efeitos(self.TICK_MS)
        return self.TICK_MS

    def _grupos(self, centro):
        """Os andarilhos à esquerda, à direita e abaixo do bloco central (o primeiro proibido).
        Cada grupo é redesenhado sozinho, então o retângulo redesenhado nunca pega os textos.
        (Grupos menores saem mais caros: cada redesenho tem um custo fixo maior que o da área.)"""
        esquerda, direita, abaixo = [], [], []
        meio = (centro[0] + centro[2]) / 2
        for a in self.andarilhos:
            if a.y >= centro[3]:
                abaixo.append(a)
            elif a.x + a.folha.largura / 2 < meio:
                esquerda.append(a)
            else:
                direita.append(a)
        return esquerda, direita, abaixo


class Companheiro(tk.Canvas):
    """Pokémon pequeno num espaço próprio (cabeçalho das telas), andando de um lado para o
    outro. Pula com um balão quando o ponteiro passa por ele e dá um golpe quando clicado."""

    LARGURA = 150     # px da pista onde ele anda
    TOPO = 16         # px livres acima dele, para o balão e o pulinho
    TICK_MS = 66
    VELOCIDADE = 1.3  # px por quadro (20 px por segundo)
    PULO_MS, PULO_PX = 380, 7

    def __init__(self, master, nome=None, bg=None):
        self.nome = nome or random.choice(companheiros())
        self.anims = pegar(master, self.nome)
        self.folha = self.anims["andar"]
        self.chao = ALTURA_COMPANHEIRO + self.TOPO
        super().__init__(master, width=self.LARGURA, height=self.chao, bg=bg,
                         highlightthickness=0, bd=0, takefocus=0)
        self.bind("<Destroy>", lambda e: e.widget is self and soltar(self, self.nome), add="+")
        self._empacotamento = None  # como estava no cabeçalho, para voltar depois da visão para o cliente
        raiz = master._root()
        raiz._pokemon_companheiros = getattr(raiz, "_pokemon_companheiros", []) + [self]
        self.passos = _Passos(self.folha)
        self.x = random.uniform(0, self.LARGURA - self.folha.largura)
        self.direcao = random.choice((DIREITA, ESQUERDA))
        self.acao, self.acao_ms = None, 0
        self.pulo_ms = 0
        self.emote = None
        self.espera_ms = 0
        self.item = self.create_image(0, 0, anchor="nw", image=self._imagem())
        self._posicionar()
        self.bind("<Enter>", self._ao_passar)
        self.bind("<Button-1>", self._ao_clicar)
        animacao.depois(self, self.TICK_MS, self._viver)

    def atualizar_visibilidade(self):
        """Visão para o cliente: sai do cabeçalho (sem deixar espaço vazio); ao desligar, volta
        ao mesmo lugar. Chamada também logo depois de ele ser posto no cabeçalho."""
        if escondidos():
            if self.winfo_manager():
                self._empacotamento = self.pack_info()
                self.pack_forget()
        elif not self.winfo_manager() and self._empacotamento:
            self.pack(**self._empacotamento)

    def _anim(self):
        return self.anims[self.acao] if self.acao else self.folha

    def _imagem(self):
        if self.acao:
            anim = self.anims[self.acao]
            return anim.quadros[self.direcao][anim.quadro_em(self.acao_ms) or 0]
        return self.folha.quadros[self.direcao][self.passos.quadro]

    def _posicionar(self):
        altura_pulo = 0
        if self.pulo_ms > 0:
            altura_pulo = self.PULO_PX * math.sin(math.pi * (1 - self.pulo_ms / self.PULO_MS))
        y_caixa = self.chao - self.folha.altura - altura_pulo  # canto da caixa de andar
        dx, dy = self._anim().deslocamento(self.direcao)
        self.coords(self.item, round(self.x - self.folha.dx + dx), round(y_caixa - self.folha.dy + dy))
        if self.emote:
            # sobre a cabeça, mas sem sair do canvas (o texto ocupa uns 20 px de altura)
            sobe = (1 - self.emote[1] / EMOTE_MS) * 4
            self.coords(self.emote[0], round(self.x + self.folha.largura / 2), round(max(19, y_caixa + 4) - sobe))

    def _mostrar(self, simbolo):
        if self.emote:
            self.delete(self.emote[0])
        item = self.create_text(0, 0, text=simbolo, fill=CORES_EMOTE.get(simbolo, COLORS["accent"]),
                                font=("Segoe UI Symbol", 11, "bold"), anchor="s")
        self.emote = [item, EMOTE_MS]

    def _ao_passar(self, _evento=None):
        if animacao.ativas() and self.espera_ms <= 0 and not self.acao:
            self.pulo_ms = self.PULO_MS
            self.espera_ms = 1500
            self._mostrar(random.choice("♥♪!"))
            self._posicionar()

    def _ao_clicar(self, _evento=None):
        if animacao.ativas() and not self.acao:
            self.acao, self.acao_ms = "golpe", 0
            self._mostrar("✦")
            self.itemconfigure(self.item, image=self._imagem())
            self._posicionar()

    def _viver(self):
        if not animacao.ativas():  # movimento reduzido: parado, de frente
            if self.direcao != BAIXO or self.passos.quadro or self.acao:
                self.direcao, self.passos.quadro, self.acao, self.pulo_ms = BAIXO, 0, None, 0
                self.itemconfigure(self.item, image=self._imagem())
                self._posicionar()
            animacao.depois(self, 500, self._viver)
            return
        if not self.winfo_viewable():
            animacao.depois(self, 400, self._viver)
            return
        self.espera_ms = max(0, self.espera_ms - self.TICK_MS)
        if self.emote:
            self.emote[1] -= self.TICK_MS
            if self.emote[1] <= 0:
                self.delete(self.emote[0])
                self.emote = None
        self.pulo_ms = max(0, self.pulo_ms - self.TICK_MS)
        if self.acao:  # golpe: no lugar
            self.acao_ms += self.TICK_MS
            if self.anims[self.acao].quadro_em(self.acao_ms) is None:
                self.acao = None
        else:
            if self.direcao not in (DIREITA, ESQUERDA):
                self.direcao = random.choice((DIREITA, ESQUERDA))
            fim = self.LARGURA - self.folha.largura
            self.x += self.VELOCIDADE if self.direcao == DIREITA else -self.VELOCIDADE
            if self.x <= 0 or self.x >= fim or random.random() < 0.003:  # chegou na ponta (ou mudou de ideia): vira
                self.x = min(max(self.x, 0), fim)
                self.direcao = ESQUERDA if self.direcao == DIREITA else DIREITA
            self.passos.avancar(self.TICK_MS)
        self.itemconfigure(self.item, image=self._imagem())
        self._posicionar()
        animacao.depois(self, self.TICK_MS, self._viver)
