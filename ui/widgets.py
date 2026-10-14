"""Widgets comuns às telas (vindos dos QGs NFCom/NFSe, que tinham cópias iguais)."""
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk

from ui import animacao
from ui.theme import COLORS, escala


class ScrolledText(tk.Text):
    """Mesmo uso do tkinter.scrolledtext.ScrolledText, mas com a barra de rolagem do
    tema escuro (a do tkinter é a barra nativa clara do Windows). pack/grid/place
    posicionam o conjunto texto + barra."""

    def __init__(self, master=None, **kw):
        self.frame = tk.Frame(master, bg=kw.get("bg", COLORS["card"]))
        kw.setdefault("selectbackground", COLORS["accent_soft"])
        kw.setdefault("selectforeground", COLORS["fg"])
        super().__init__(self.frame, **kw)
        self.vbar = ttk.Scrollbar(self.frame, orient="vertical", command=self.yview)
        self.vbar.pack(side="right", fill="y")
        tk.Text.pack(self, side="left", fill="both", expand=True)
        self.configure(yscrollcommand=self.vbar.set)

    def pack(self, *args, **kw):
        self.frame.pack(*args, **kw)

    def grid(self, *args, **kw):
        self.frame.grid(*args, **kw)

    def place(self, *args, **kw):
        self.frame.place(*args, **kw)

    def pack_forget(self):
        self.frame.pack_forget()


class PaginaRolavel(tk.Frame):
    """Moldura que deixa uma tela de operação rolar na vertical quando o conteúdo não cabe
    na janela (notebook, escala 150%) e ocupar a altura toda quando cabe (o log estica).
    Uso: moldura = PaginaRolavel(pai); tela = Tela(moldura.interior, ...); moldura.conter(tela).
    A roda do mouse rola a moldura em qualquer ponto dela (ver ativar_roda).

    A tela fica dentro de `interior`, ao lado de uma escora invisível com a altura da área
    visível: assim `interior` pede sempre o maior entre a altura da tela e a da janela, e
    cresce sozinho quando a tela cresce (a área de rolagem acompanha, sem altura fixa que
    ficasse desatualizada)."""

    def __init__(self, master, cor=None, mostrar_barra=True):
        cor = cor or COLORS["bg"]
        super().__init__(master, bg=cor)
        self.mostrar_barra = mostrar_barra
        self.canvas = tk.Canvas(self, bg=cor, highlightthickness=0, bd=0)
        self.barra = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.barra.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.interior = tk.Frame(self.canvas, bg=cor)
        self._escora = tk.Frame(self.interior, bg=cor, width=1, height=1)
        self._escora.pack(side="left", fill="y")
        self._janela = self.canvas.create_window((0, 0), window=self.interior, anchor="nw")
        self.canvas.bind("<Configure>", lambda _e: self._ajustar())
        self.interior.bind("<Configure>", lambda _e: self._ajustar())

    def conter(self, conteudo):
        conteudo.pack(side="left", fill="both", expand=True)

    def altura_total(self) -> int:
        return self.interior.winfo_reqheight()

    def _precisa_rolar(self) -> bool:
        return self.altura_total() > self.canvas.winfo_height() + 1

    def _ajustar(self):
        largura, altura = self.canvas.winfo_width(), self.canvas.winfo_height()
        self._escora.configure(height=altura)
        self.canvas.itemconfigure(self._janela, width=largura)
        self.canvas.configure(scrollregion=(0, 0, largura, max(altura, self.altura_total())))
        if self._precisa_rolar():
            if self.mostrar_barra and not self.barra.winfo_ismapped():
                self.barra.pack(side="right", fill="y", before=self.canvas)
        else:
            if self.barra.winfo_ismapped():
                self.barra.pack_forget()
            self.canvas.yview_moveto(0)

    def rolar_roda(self, delta) -> bool:
        """Roda do mouse (ver ativar_roda). Devolve False se não há o que rolar (o conteúdo cabe)."""
        if not self._precisa_rolar():
            return False
        return rolar_canvas(self.canvas, delta, self.altura_total())


def rolar_canvas(canvas, delta, altura_total) -> bool:
    """Rola o canvas cerca de três linhas por passo da roda, parando exatamente no início e no
    fim. Em pixels (e não em "unidades" do canvas) para que uma sobra pequena também role."""
    visivel = canvas.winfo_height()
    if altura_total <= visivel:
        return False
    passo = int(90 * escala(canvas)) * (-1 if delta > 0 else 1)
    topo = canvas.yview()[0] * altura_total
    novo = min(max(topo + passo, 0), altura_total - visivel)
    canvas.yview_moveto(novo / altura_total)
    return True


def rolar_sob(widget, delta) -> bool:
    """Rola a área rolável mais próxima que contém `widget` (sobe pelos pais até achar quem
    tenha rolar_roda). Um log (Text) que ainda tenha o que rolar naquele sentido rola sozinho;
    quando chega ao fim, a tela assume. Devolve True se a tela rolou."""
    while widget is not None:
        if isinstance(widget, ttk.Scrollbar):
            return False
        if isinstance(widget, tk.Text):
            inicio, fim = widget.yview()
            if (delta > 0 and inicio > 0) or (delta < 0 and fim < 1):
                return False
        rolar = getattr(widget, "rolar_roda", None)
        if rolar is not None and rolar(delta):
            return True
        widget = getattr(widget, "master", None)
    return False


def ativar_roda(raiz):
    """Faz a roda do mouse rolar a área rolável que estiver embaixo do ponteiro, em qualquer
    ponto dela (antes só funcionava com o ponteiro fora dos campos e botões).

    Listas e campos numéricos deixam de mudar de valor com a roda, para não trocar o mês ou
    o dia sem querer ao rolar a tela."""

    def ao_rolar(evento):
        try:
            widget = raiz.winfo_containing(evento.x_root, evento.y_root)
        except (KeyError, tk.TclError):
            return  # ponteiro sobre a lista aberta de um combobox (ela rola sozinha)
        rolar_sob(widget, evento.delta)

    raiz.bind_all("<MouseWheel>", ao_rolar)
    for classe in ("TCombobox", "TSpinbox"):
        raiz.unbind_class(classe, "<MouseWheel>")


class Dica:
    """Texto curto que aparece ao parar o mouse sobre um widget (usado na barra lateral recolhida)."""

    def __init__(self, widget, texto, espera=350):
        self.widget, self.texto, self.espera = widget, texto, espera
        self._agendado = None
        self._janela = None
        widget.bind("<Enter>", self._agendar, add="+")
        widget.bind("<Leave>", self._fechar, add="+")
        widget.bind("<ButtonPress>", self._fechar, add="+")
        widget.bind("<Destroy>", self._fechar, add="+")

    def _agendar(self, _evento=None):
        self._fechar()
        self._agendado = self.widget.after(self.espera, self._mostrar)

    def _mostrar(self):
        self._agendado = None
        if self._janela is not None or not self.widget.winfo_exists():
            return
        self._janela = janela = tk.Toplevel(self.widget)
        janela.wm_overrideredirect(True)
        janela.configure(bg=COLORS["card_border"])
        tk.Label(janela, text=self.texto, bg=COLORS["card"], fg=COLORS["fg"], font=("Segoe UI", 9),
                 padx=10, pady=5).pack(padx=1, pady=1)
        x = self.widget.winfo_rootx() + self.widget.winfo_width() + 8
        y = self.widget.winfo_rooty() + max(0, (self.widget.winfo_height() - janela.winfo_reqheight()) // 2)
        janela.wm_geometry(f"+{x}+{y}")

    def _fechar(self, _evento=None):
        if self._agendado is not None:
            try:
                self.widget.after_cancel(self._agendado)
            except tk.TclError:
                pass
            self._agendado = None
        if self._janela is not None:
            try:
                self._janela.destroy()
            except tk.TclError:
                pass
            self._janela = None


def centralizar(janela, largura, altura):
    """Posiciona uma janela (modal) no centro da janela principal do app."""
    principal = janela.master.winfo_toplevel()
    principal.update_idletasks()
    x = principal.winfo_rootx() + max(0, (principal.winfo_width() - largura) // 2)
    y = principal.winfo_rooty() + max(0, (principal.winfo_height() - altura) // 3)
    janela.geometry(f"{largura}x{altura}+{x}+{y}")
    animacao.aparecer(janela)  # abre com um fade-in curto


class Contador(tk.Label):
    """Número de um contador. Quando o valor muda, ele acende por um instante e volta à cor
    normal (feedback de que algo aconteceu), sem que as telas precisem fazer nada: elas
    continuam usando label["text"] = ... como sempre."""

    def __init__(self, master, cor, **kw):
        super().__init__(master, fg=cor, **kw)
        self._cor = cor

    def configure(self, cnf=None, **kw):
        novos = dict(cnf or {}, **kw)
        if "fg" in novos:  # a tela trocou a cor do contador: vale a nova
            animacao.cancelar(self, "pulsar:fg")
            self._cor = novos["fg"]
        anterior = super().cget("text") if "text" in novos else None
        resultado = super().configure(cnf, **kw)
        if "text" in novos and str(novos["text"]) != str(anterior) and str(novos["text"]) not in ("", "0"):
            # a animação pinta direto no Label, sem passar por este configure
            animacao.pulsar(self, self._cor, aplicar=lambda cor: tk.Label.configure(self, fg=cor))
        return resultado

    config = configure

    def __setitem__(self, chave, valor):
        self.configure({chave: valor})


def stat_box(parent, label, color):
    """Contador de uma tela: filete na cor do contador, rótulo discreto e o número em destaque."""
    box = tk.Frame(parent, bg=COLORS["card"], highlightbackground=COLORS["card_border"],
                   highlightthickness=1)
    tk.Frame(box, bg=color, width=3).pack(side="left", fill="y")
    corpo = tk.Frame(box, bg=COLORS["card"])
    corpo.pack(side="left", fill="both", expand=True)
    tk.Label(corpo, text=label, bg=COLORS["card"], fg=COLORS["fg_muted"],
             font=("Segoe UI", 7, "bold")).pack(anchor="w", padx=(10, 14), pady=(8, 0))
    val = Contador(corpo, color, text="0", bg=COLORS["card"], font=("Segoe UI Semibold", 17))
    val.pack(anchor="w", padx=(10, 14), pady=(0, 7))
    return box, val


def _open_folder(path):
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def back_button(parent, controller, title, subtitle):
    """Cabeçalho da tela de operação: "← Início" + título. Mesma assinatura dos
    QGs originais; volta para o hub do MegaQG Vivo."""
    header = tk.Frame(parent, bg=COLORS["bg"])
    header.pack(fill="x", padx=18, pady=(16, 8))

    btn = tk.Label(header, text="←  Início", bg=COLORS["bg"], fg=COLORS["fg_muted"],
                   font=("Segoe UI", 10), cursor="hand2")
    btn.pack(side="left")
    btn.bind("<Button-1>", lambda _e: controller.show_hub())
    btn.bind("<Enter>", lambda _e: animacao.cor(btn, {"fg": COLORS["accent"]}))
    btn.bind("<Leave>", lambda _e: animacao.cor(btn, {"fg": COLORS["fg_muted"]}))

    tk.Frame(header, bg=COLORS["card_border"], width=1).pack(side="left", fill="y", padx=14, pady=3)
    tk.Label(header, text=title, bg=COLORS["bg"], fg=COLORS["fg"],
             font=("Segoe UI Semibold", 15)).pack(side="left")
    if subtitle:
        tk.Label(header, text=subtitle, bg=COLORS["bg"], fg=COLORS["fg_muted"],
                 font=("Segoe UI", 9)).pack(side="left", padx=(12, 0))
    # Um Pokémon pequeno andando no canto do cabeçalho, sorteado a cada tela (decorativo, num
    # espaço só dele: não fica por cima de nada clicável)
    from ui import pokemon
    if pokemon.companheiros():
        companheiro = pokemon.Companheiro(header, bg=COLORS["bg"])
        companheiro.pack(side="right", padx=(12, 0))
        companheiro.atualizar_visibilidade()  # com a visão para o cliente ligada, já sai de cena
    return header
