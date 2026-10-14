"""
Animações da interface: o equivalente, no Tk, às transições de CSS.

O Tk não tem CSS, opacidade por widget nem pointer-events. Por isso cada animação aqui é uma
sequência curta de quadros agendados com after() que só muda cor (como uma transition de
color/background), desloca itens de um Canvas (como um transform: translate) ou muda a
opacidade da janela inteira (-alpha, que o Windows compõe na placa de vídeo). Nenhuma delas
recalcula o layout das telas, o que é o que deixa uma animação "travada" no Tk.

Movimento reduzido (o equivalente a prefers-reduced-motion): toda transição vira troca direta e
os Pokémon ficam parados. Quem decide, nesta ordem:
  1. a opção "Animações e Pokémon" da janela de temas, se o usuário já mexeu nela (ligada vale
     mesmo com o Windows desligado; desligada vale sempre);
  2. senão, o Windows: "Efeitos de animação" desligado (Configurações > Acessibilidade > Efeitos
     visuais) liga o movimento reduzido. Exceto em Área de Trabalho Remota: lá o Windows desliga
     as animações para economizar banda (não é uma escolha de acessibilidade), e o app animava
     "travado" em servidores e máquinas acessadas remotamente.
"""
import sys
import time

from core import preferencias
from ui.theme import misturar

QUADRO_MS = 16  # ~60 quadros por segundo; a duração é medida no relógio, não em quadros
_estado = {"ativas": None, "lido_em": 0.0}


def movimento_do_sistema_ligado() -> bool:
    """False quando o Windows está com as animações desligadas (SPI_GETCLIENTAREAANIMATION)."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        valor = ctypes.c_int(1)
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(valor), 0):
            return bool(valor.value)
    except Exception:
        pass
    return True


def sessao_remota() -> bool:
    """True numa sessão de Área de Trabalho Remota (GetSystemMetrics(SM_REMOTESESSION))."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetSystemMetrics(0x1000))
    except Exception:
        return False


def windows_desliga() -> bool:
    """O Windows pede movimento reduzido (e não é só a Área de Trabalho Remota economizando banda)?"""
    return not movimento_do_sistema_ligado() and not sessao_remota()


def _calcular() -> bool:
    escolha = preferencias.obter("animacoes", None)  # None: o usuário nunca mexeu na opção
    if escolha is not None:
        return escolha is not False
    return not windows_desliga()


def ativas() -> bool:
    """Animações ligadas? Relê a preferência e o Windows a cada 10 s, no máximo."""
    agora = time.monotonic()
    if _estado["ativas"] is None or agora - _estado["lido_em"] > 10:
        _estado["ativas"] = _calcular()
        _estado["lido_em"] = agora
    return _estado["ativas"]


def preferencia_ligada() -> bool:
    """O que a opção "Animações e Pokémon" mostra: o estado que vale agora."""
    return _calcular()


def definir_preferencia(ligadas: bool):
    """Escolha explícita do usuário: vale acima do Windows."""
    preferencias.definir("animacoes", bool(ligadas))
    _estado["ativas"] = None


# --------------------------------------------------------------------- curvas
def sair_suave(p):
    """ease-out (cubic): começa rápido e assenta devagar. Para entradas e hover."""
    return 1 - (1 - p) ** 3


def suave(p):
    """ease-in-out: acelera e freia. Para opacidade e trocas de estado."""
    return p * p * (3 - 2 * p)


# ------------------------------------------------------------------- motor
def _agenda(widget) -> dict:
    return widget.__dict__.setdefault("_animacoes", {})


def _existe(widget) -> bool:
    try:
        return bool(widget.winfo_exists())
    except Exception:
        return False


def depois(widget, ms, funcao):
    """after() agendado na janela principal, não no widget: se o widget for destruído antes
    (card recriado, troca de tema), o quadro seguinte só confere que ele não existe mais e
    para, em vez de virar um "invalid command name" do Tcl."""
    return widget._root().after(ms, lambda: _existe(widget) and funcao())


def cancelar(widget, chave):
    agenda = _agenda(widget)
    if chave in agenda:
        try:
            widget._root().after_cancel(agenda.pop(chave))
        except Exception:
            pass


def animar(widget, chave, duracao, passo, curva=sair_suave, atraso=0, fim=None):
    """Chama passo(p) com p de 0 a 1 (já passado pela curva) durante `duracao` ms.
    Uma nova animação com a mesma chave no mesmo widget substitui a anterior. Com
    movimento reduzido, vai direto ao estado final."""
    cancelar(widget, chave)
    if not ativas() or duracao <= 0:
        passo(1.0)
        if fim:
            fim()
        return
    agenda = _agenda(widget)
    inicio = [None]

    def quadro():
        if inicio[0] is None:
            inicio[0] = time.perf_counter()
        p = min(1.0, (time.perf_counter() - inicio[0]) * 1000 / duracao)
        passo(curva(p))
        if p < 1.0:
            agenda[chave] = depois(widget, QUADRO_MS, quadro)
        else:
            agenda.pop(chave, None)
            if fim:
                fim()

    if atraso > 0:
        passo(0.0)
        agenda[chave] = depois(widget, int(atraso), quadro)
    else:
        quadro()


# -------------------------------------------------------------------- cores
def _hex(cor) -> bool:
    return isinstance(cor, str) and len(cor) == 7 and cor.startswith("#")


def cor(widget, opcoes, duracao=150, item=None):
    """Transição de cor. opcoes = {"bg": "#...", "fg": "#..."} (ou fill/outline de um item de Canvas).
    Equivale a transition: background-color .15s ease-out."""
    atual = {}
    for opcao, destino in opcoes.items():
        valor = widget.itemcget(item, opcao) if item is not None else widget.cget(opcao)
        atual[opcao] = (str(valor), destino)

    def aplicar(p):
        novos = {opcao: (misturar(destino, de, p) if _hex(de) and _hex(destino) else destino)
                 for opcao, (de, destino) in atual.items()}
        if item is not None:
            widget.itemconfigure(item, **novos)
        else:
            widget.configure(**novos)

    animar(widget, f"cor:{item}:{','.join(sorted(opcoes))}", duracao, aplicar)


def revelar(canvas, fundo, atraso=0, duracao=260):
    """Entrada de um Canvas desenhado (card): os itens nascem da cor do fundo e chegam à
    cor final, como um fade-in. Equivale a @keyframes de opacity 0 -> 1."""
    alvos = []
    for item in canvas.find_all():
        if canvas.type(item) == "image":
            continue
        for opcao in ("fill", "outline"):
            try:
                valor = canvas.itemcget(item, opcao)
            except Exception:
                continue
            if _hex(valor):
                alvos.append((item, opcao, valor))
    if not alvos or not ativas():
        return

    def aplicar(p):
        for item, opcao, final in alvos:
            canvas.itemconfigure(item, **{opcao: misturar(final, fundo, p)})

    animar(canvas, "revelar", duracao, aplicar, curva=sair_suave, atraso=atraso)


def pulsar(widget, cor_final, opcao="fg", duracao=480, aplicar=None):
    """Destaque rápido quando um valor muda (contadores): acende e volta à cor normal.
    `aplicar(cor)` troca a cor; por padrão, widget.configure(opcao=cor)."""
    if not _hex(cor_final):
        return
    aplicar = aplicar or (lambda valor: widget.configure(**{opcao: valor}))
    brilho = misturar("#ffffff", cor_final, 0.5)
    animar(widget, f"pulsar:{opcao}", duracao, lambda p: aplicar(misturar(cor_final, brilho, p)), curva=suave)


# -------------------------------------------------------------------- janelas
def aparecer(janela, duracao=180):
    """Janela que abre com fade-in (opacidade da janela inteira, sem custo de layout)."""
    if not ativas():
        return
    try:
        janela.attributes("-alpha", 0.0)
    except Exception:
        return
    animar(janela, "alpha", duracao, lambda p: janela.attributes("-alpha", p), curva=suave)


def sumir(janela, depois, duracao=130):
    """Fade-out e depois `depois()` (normalmente destroy)."""
    if not ativas():
        depois()
        return
    try:
        inicial = float(janela.attributes("-alpha"))
    except Exception:
        depois()
        return
    animar(janela, "alpha", duracao, lambda p: janela.attributes("-alpha", inicial * (1 - p)), curva=suave,
           fim=depois)


def voltar_a_opacidade(janela, de=0.55, duracao=240):
    """Depois de uma troca grande (tema), a janela volta de semitransparente para opaca: a
    reconstrução acontece "por trás" de um esmaecimento, sem piscar."""
    if not ativas():
        return
    try:
        janela.attributes("-alpha", de)
    except Exception:
        return
    animar(janela, "alpha", duracao, lambda p: janela.attributes("-alpha", de + (1 - de) * p), curva=suave)
