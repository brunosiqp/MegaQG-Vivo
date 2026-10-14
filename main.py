"""
MegaQG Vivo - ponto de entrada.

Rode: python main.py              (hub com todas as operações NFCom, NFSe e relatórios)
      python main.py --cli        (modo terminal do Exportador de Relatório)
      MegaQGVivo.exe --autoteste  (abre todas as telas, grava logs/autoteste.txt e fecha;
                                   serve para conferir um exe recém-instalado no servidor)
"""
import os
import sys
import traceback


def ativar_nitidez() -> None:
    """Avisa o Windows que o app sabe lidar com escala de tela (125%, 150%...). Sem isso o
    Windows "estica" a janela e o texto fica borrado. Precisa vir antes de criar a janela."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def autoteste() -> int:
    """Abre cada tela do registro e fecha o app. Não inicia nenhuma operação."""
    from core import config
    from modulos.registro import operacoes_ativas
    from ui.app import App

    linhas, erros = [f"Configuração: {config.origem()}"], 0
    app = App()
    app.withdraw()
    OPERACOES = operacoes_ativas()
    for op in OPERACOES:
        try:
            app.abrir(op["id"], perguntar=False)
            app.update()
            linhas.append(f"OK    {op['id']}")
        except Exception:
            erros += 1
            linhas.append(f"ERRO  {op['id']}\n{traceback.format_exc()}")
    app.destroy()
    linhas.append(f"{len(OPERACOES) - erros}/{len(OPERACOES)} telas abriram")
    from ui import animacao, pokemon  # confere que as animações dos Pokémon foram embutidas no exe
    animacoes = len(pokemon.disponiveis())
    linhas.append(f"{animacoes}/{len(pokemon.POKEMON)} animações de Pokémon")
    erros += animacoes < len(pokemon.POKEMON)
    # por que os Pokémon andam (ou ficam parados) nesta máquina
    linhas.append(f"Animações {'ligadas' if animacao.ativas() else 'desligadas (movimento reduzido)'}: "
                  f"Windows com efeitos de animação = {'sim' if animacao.movimento_do_sistema_ligado() else 'não'}, "
                  f"Área de Trabalho Remota = {'sim' if animacao.sessao_remota() else 'não'}, "
                  f"opção da janela de temas = {animacao.preferencias.obter('animacoes', None)}")
    os.makedirs(config.log_dir(), exist_ok=True)
    with open(os.path.join(config.log_dir(), "autoteste.txt"), "w", encoding="utf-8-sig") as f:
        f.write("\n".join(linhas) + "\n")
    return 1 if erros else 0


def main():
    if "--cli" in sys.argv:
        from modulos.exportador_relatorio.cli import main as main_cli
        main_cli()
        return
    ativar_nitidez()
    if "--autoteste" in sys.argv:
        sys.exit(autoteste())

    from ui.app import App
    App().mainloop()


if __name__ == "__main__":
    main()
