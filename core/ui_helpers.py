import tkinter as tk
from tkinter import filedialog


def escolher_pasta(titulo: str, pasta_inicial: str = "", parent=None) -> str | None:
    """
    =====================================================================
    Descrição:
    Abre uma janela nativa do Windows do tipo "Procurar pasta" e retorna
    o caminho escolhido. Funciona tanto de dentro de uma GUI Tkinter já
    aberta (passando `parent`) quanto de um script de linha de comando
    (sem `parent` - cria uma janela Tk oculta só para exibir o diálogo).
    =====================================================================
    Parâmetros:
    - titulo: título da janela do diálogo.
    - pasta_inicial: pasta sugerida ao abrir o diálogo.
    - parent: janela Tk pai (opcional). Se None, cria e destrói uma
      janela raiz temporária e invisível.
    =====================================================================
    Retorno:
    - Caminho escolhido, ou None se o usuário cancelar.
    =====================================================================
    """
    root_temporaria = None
    janela = parent

    if janela is None:
        root_temporaria = tk.Tk()
        root_temporaria.withdraw()
        root_temporaria.attributes("-topmost", True)
        janela = root_temporaria

    try:
        pasta = filedialog.askdirectory(
            title=titulo,
            initialdir=pasta_inicial or None,
            parent=janela,
        )
    finally:
        if root_temporaria is not None:
            root_temporaria.destroy()

    return pasta or None
