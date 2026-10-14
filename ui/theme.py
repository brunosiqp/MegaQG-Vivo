"""
Aparência do MegaQG Vivo: a paleta ativa (COLORS), utilitários de cor e os estilos ttk.

COLORS é sempre o mesmo dicionário: trocar de tema (ui/temas.py) só muda os valores dele e
reaplica os estilos, então as telas continuam lendo COLORS["..."] como sempre. As cores de
texto sobre botões, realces e bordas são calculadas a partir da paleta, por isso qualquer
tema (escuro, claro ou criado pelo usuário) fica legível sem ajuste manual.
"""
import tkinter as tk
from tkinter import ttk

ESCURO, CLARO = "#0b0e14", "#ffffff"  # texto sobre uma cor cheia (escolhido pelo contraste)

# Cores cheias que têm botão e barra de progresso próprios: "Accent.TButton", "Teal.Horizontal.TProgressbar"...
ESTILOS_DE_COR = {"Accent": "accent", "Danger": "danger", "Purple": "purple", "Teal": "teal",
                  "Warning": "warning", "Success": "success", "Cyan": "cyan", "Indigo": "indigo", "Blue": "blue"}


def escala(widget) -> float:
    """Fator de escala da tela (1.0 = 100%). Tamanhos em pixels fixos (cards,
    barra lateral, janela) são multiplicados por ele para acompanhar o tamanho
    das fontes quando o Windows está com escala > 100%."""
    try:
        return max(1.0, widget.winfo_fpixels("1i") / 96.0)
    except Exception:
        return 1.0


def misturar(cor_a: str, cor_b: str, proporcao_a: float) -> str:
    """Mistura duas cores #rrggbb (proporcao_a de cor_a). Gera os fundos suaves dos
    chips e pílulas a partir da cor de cada operação, sem precisar de transparência."""
    a = [int(cor_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(cor_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * proporcao_a + y * (1 - proporcao_a)):02x}" for x, y in zip(a, b))


def luminancia(cor: str) -> float:
    """Luminância relativa (0 = preto, 1 = branco), a mesma conta do contraste de acessibilidade."""
    canais = []
    for i in (1, 3, 5):
        v = int(cor[i:i + 2], 16) / 255
        canais.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * canais[0] + 0.7152 * canais[1] + 0.0722 * canais[2]


def sobre(cor: str) -> str:
    """Cor do texto que se lê melhor em cima de `cor` (escuro ou branco)."""
    return ESCURO if luminancia(cor) > 0.179 else CLARO


def tema_escuro() -> bool:
    return luminancia(COLORS["bg"]) < 0.25


def realcar(cor: str, proporcao: float = 0.22) -> str:
    """A mesma cor um pouco mais viva (passar o mouse): clareia no tema escuro, escurece no claro."""
    return misturar("#ffffff" if tema_escuro() else "#000000", cor, proporcao)


def retangulo_arredondado(x1, y1, x2, y2, r) -> list:
    """Pontos de um retângulo de cantos arredondados para Canvas.create_polygon(smooth=True)."""
    r = max(0, min(r, (x2 - x1) // 2, (y2 - y1) // 2))
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


# Paleta ativa. Começa no tema padrão e é trocada por ui.temas.ativar() (mesmo dicionário, valores novos).
COLORS = {
    "bg": "#07090e",
    "panel": "#0c1018",
    "card": "#121824",
    "card_border": "#1f2838",
    "fg": "#e7ecf5",
    "fg_muted": "#7d889d",
    "accent": "#4da3ff",
    "accent_soft": "#1a3350",
    "purple": "#a678ff",
    "teal": "#2ddcc3",
    "success": "#3ddc84",
    "warning": "#f7b13c",
    "danger": "#ff5468",
    "danger_soft": "#34151c",
    "cyan": "#30d5f2",
    "cyan_soft": "#103039",
    "indigo": "#8a93ff",
    "blue": "#4b8dff",
    # Ambiente (indicador discreto no topo: linha fina + seletor com fundo suave)
    "prd": "#ff6b78",
    "prd_soft": "#2a141a",
    "hml": "#f5b444",
    "hml_soft": "#292012",
}


def aplicar_estilos(root):
    """(Re)aplica os estilos ttk a partir da paleta ativa. Chamado na abertura e a cada troca de tema."""
    c = COLORS
    root.configure(bg=c["bg"])
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    k = escala(root)
    borda = c["card_border"]

    style.configure(".", background=c["bg"], foreground=c["fg"], fieldbackground=c["card"],
                    bordercolor=borda, font=("Segoe UI", 10), borderwidth=0)

    style.configure("TFrame", background=c["bg"])
    style.configure("Panel.TFrame", background=c["panel"])
    style.configure("Card.TFrame", background=c["card"])

    style.configure("TLabel", background=c["bg"], foreground=c["fg"])
    style.configure("Panel.TLabel", background=c["panel"], foreground=c["fg"])
    style.configure("Card.TLabel", background=c["card"], foreground=c["fg"])
    style.configure("Muted.TLabel", background=c["bg"], foreground=c["fg_muted"])
    style.configure("PanelMuted.TLabel", background=c["panel"], foreground=c["fg_muted"], font=("Segoe UI", 9))
    style.configure("Title.TLabel", background=c["bg"], foreground=c["fg"], font=("Segoe UI Light", 22))
    style.configure("Subtitle.TLabel", background=c["bg"], foreground=c["fg_muted"], font=("Segoe UI", 11))
    # Ambiente mostrado dentro das telas (troca só no seletor do topo)
    style.configure("Ambiente.TLabel", background=c["panel"], foreground=c["fg"], font=("Segoe UI", 10, "bold"))

    # Molduras (PARÂMETROS, PROGRESSO, LOG): linha fina e título discreto
    style.configure("TLabelframe", background=c["panel"], foreground=c["fg"], bordercolor=borda,
                    lightcolor=c["panel"], darkcolor=c["panel"], relief="solid", borderwidth=1, padding=4)
    style.configure("TLabelframe.Label", background=c["panel"], foreground=c["fg_muted"],
                    font=("Segoe UI", 8, "bold"))

    # Botão comum: contorno fino; ao passar o mouse, contorno e texto na cor de destaque
    contorno = misturar(c["fg_muted"], c["card_border"], 0.35)
    style.configure("TButton", background=c["card"], foreground=c["fg"], bordercolor=contorno,
                    lightcolor=c["card"], darkcolor=c["card"], focuscolor=c["card"],
                    relief="raised", borderwidth=1, padding=(14, 7), font=("Segoe UI", 10))
    style.map("TButton",
              background=[("disabled", c["panel"]), ("pressed", c["accent_soft"]), ("active", c["card"])],
              lightcolor=[("disabled", c["panel"]), ("pressed", c["accent_soft"]), ("active", c["card"])],
              darkcolor=[("disabled", c["panel"]), ("pressed", c["accent_soft"]), ("active", c["card"])],
              foreground=[("disabled", misturar(c["fg_muted"], c["panel"], 0.6)), ("active", c["accent"])],
              bordercolor=[("disabled", borda), ("active", c["accent"])],
              relief=[("pressed", "raised")])

    # Botões de ação: cor cheia da operação, texto na cor de maior contraste
    for nome, chave in ESTILOS_DE_COR.items():
        cor, viva = c[chave], realcar(c[chave])
        style.configure(f"{nome}.TButton", background=cor, foreground=sobre(cor), bordercolor=cor,
                        lightcolor=cor, darkcolor=cor, focuscolor=cor, padding=(18, 8),
                        relief="raised", borderwidth=1, font=("Segoe UI", 10, "bold"))
        style.map(f"{nome}.TButton",
                  background=[("disabled", c["panel"]), ("active", viva)],
                  lightcolor=[("disabled", c["panel"]), ("active", viva)],
                  darkcolor=[("disabled", c["panel"]), ("active", viva)],
                  bordercolor=[("disabled", borda), ("active", viva)],
                  foreground=[("disabled", misturar(c["fg_muted"], c["panel"], 0.6)), ("active", sobre(viva))])

    # Campos de texto, listas e números: linha fina, foco na cor de destaque
    seta = misturar(c["fg"], c["fg_muted"], 0.5)
    for nome in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(nome, fieldbackground=c["card"], foreground=c["fg"], background=c["card"],
                        bordercolor=borda, lightcolor=borda, darkcolor=borda, insertcolor=c["fg"],
                        arrowcolor=seta, padding=6, selectbackground=c["accent_soft"], selectforeground=c["fg"])
        style.map(nome,
                  lightcolor=[("focus", c["accent"])], darkcolor=[("focus", c["accent"])],
                  bordercolor=[("focus", c["accent"])],
                  fieldbackground=[("readonly", c["panel"]), ("disabled", c["panel"])],
                  foreground=[("disabled", c["fg_muted"])],
                  background=[("active", borda), ("pressed", borda)],
                  arrowcolor=[("disabled", borda)])
    style.configure("TCombobox", arrowsize=int(14 * k))
    style.configure("TSpinbox", arrowsize=int(10 * k))
    # Combobox só-leitura é uma lista de escolha: fundo de campo normal, texto claro
    style.map("TCombobox", fieldbackground=[("readonly", c["card"])], foreground=[("readonly", c["fg"])],
              selectbackground=[("readonly", c["card"])], selectforeground=[("readonly", c["fg"])])
    root.option_add("*TCombobox*Listbox.background", c["card"])
    root.option_add("*TCombobox*Listbox.foreground", c["fg"])
    root.option_add("*TCombobox*Listbox.selectBackground", c["accent_soft"])
    root.option_add("*TCombobox*Listbox.selectForeground", c["fg"])

    # Caixas de seleção e opções: indicador na cor do cartão, marcado na cor de destaque
    for nome in ("TCheckbutton", "TRadiobutton"):
        style.configure(nome, background=c["panel"], foreground=c["fg"], focuscolor=c["panel"],
                        font=("Segoe UI", 10), indicatorbackground=c["card"], indicatorforeground=c["fg"],
                        upperbordercolor=borda, lowerbordercolor=borda, indicatormargin=(0, 0, 8, 0),
                        padding=(2, 4))
        style.map(nome,
                  indicatorbackground=[("selected", c["accent"]), ("!selected", c["card"])],
                  indicatorforeground=[("selected", sobre(c["accent"]))],
                  indicatorcolor=[("selected", c["accent"]), ("!selected", c["card"])],
                  upperbordercolor=[("selected", c["accent"])], lowerbordercolor=[("selected", c["accent"])],
                  background=[("active", c["panel"])], foreground=[("disabled", c["fg_muted"])])

    # Barras de progresso: finas, sem relevo
    for prefixo, chave in [("", "accent")] + [(f"{nome}.", chave) for nome, chave in ESTILOS_DE_COR.items()]:
        cor = c[chave]
        style.configure(f"{prefixo}Horizontal.TProgressbar", thickness=6, troughcolor=c["card"],
                        background=cor, bordercolor=c["card"], lightcolor=cor, darkcolor=cor)

    # Barra de rolagem: só o trilho e o cursor, sem setas
    style.layout("Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
        ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    cursor = misturar(c["fg_muted"], c["bg"], 0.35)
    style.configure("Vertical.TScrollbar", background=cursor, troughcolor=c["bg"], bordercolor=c["bg"],
                    lightcolor=cursor, darkcolor=cursor, arrowcolor=c["fg_muted"], gripcount=0,
                    width=int(10 * k))
    style.map("Vertical.TScrollbar", background=[("active", c["fg_muted"]), ("pressed", c["accent"])],
              lightcolor=[("active", c["fg_muted"]), ("pressed", c["accent"])],
              darkcolor=[("active", c["fg_muted"]), ("pressed", c["accent"])])
    return style


apply_dark_theme = aplicar_estilos  # nome antigo, usado pelos QGs originais
