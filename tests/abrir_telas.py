"""
Teste de abertura e da interface: cria o app, abre todas as operações do registro, alterna o
ambiente, troca por todos os temas, cria/edita/exclui um tema, recolhe a barra lateral e
confere a rolagem pela roda do mouse. Pega erro de import/layout em qualquer tela sem
precisar de VPN nem endpoint (nenhuma operação é iniciada).

As preferências do teste vão para um arquivo temporário: o tema do usuário não é alterado.

Rode: python tests/abrir_telas.py [pasta_para_prints]
Com uma pasta, salva print do hub (PRD e HML) e de cada tela (precisa do Pillow).
"""
import math
import os
import sys
import tempfile
import time
import traceback
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["MEGAQG_PREFERENCIAS"] = os.path.join(tempfile.mkdtemp(), "preferencias.json")

from core import config, preferencias  # noqa: E402
from modulos.registro import operacoes_ativas  # noqa: E402

OPERACOES = operacoes_ativas()
from ui import temas  # noqa: E402
from ui.app import App  # noqa: E402
from ui.theme import COLORS  # noqa: E402
from ui.widgets import rolar_sob  # noqa: E402

PASTA_PRINTS = sys.argv[1] if len(sys.argv) > 1 else None
erros = []
erros_de_fundo = []  # exceções em callbacks do Tk (after, eventos), que não derrubam o teste sozinhas


def print_janela(app, nome):
    if not PASTA_PRINTS:
        return
    from PIL import ImageGrab
    app.update()
    x, y = app.winfo_rootx(), app.winfo_rooty()
    w, h = app.winfo_width(), app.winfo_height()
    ImageGrab.grab((x, y, x + w, y + h), all_screens=True).save(os.path.join(PASTA_PRINTS, f"{nome}.png"))


def etapa(nome, fn):
    try:
        fn()
        print(f"OK    {nome}")
    except Exception:
        erros.append(nome)
        print(f"ERRO  {nome}\n{traceback.format_exc()}")


def abrir_operacoes(app):
    for i, op in enumerate(OPERACOES, start=1):
        try:
            app.abrir(op["id"])
            app.update()
            print_janela(app, f"{i:02d}_{op['id'].replace('.', '_')}")
            # Retorno de Contingência NFCe: a tela muda de cor conforme o tipo escolhido
            pagina = app.paginas[op["id"]]
            for tipo in getattr(pagina, "opcoes", {}):
                pagina._escolher_tipo(tipo)
                app.update()
                assert pagina.tipo == tipo
                print_janela(app, f"{i:02d}_{op['id'].replace('.', '_')}_{tipo}")
            print(f"OK    {op['id']}")
        except Exception:
            erros.append(op["id"])
            print(f"ERRO  {op['id']}\n{traceback.format_exc()}")


def conferir_temas(app):
    """Cada tema redesenha a janela com as telas abertas; o ambiente continua trocando depois."""
    for tema_id in list(temas.PRONTOS) + [temas.PADRAO]:
        assert app.aplicar_tema(tema_id), tema_id
        assert temas.ativo() == tema_id and preferencias.obter("tema") == tema_id
        assert app.cget("bg") == COLORS["bg"] == temas.completar(temas.PRONTOS[tema_id]["cores"])["bg"]
        for op in OPERACOES:  # todas as telas abrem em todos os temas (inclusive no claro)
            app.abrir(op["id"], perguntar=False)
        app.update()
        assert app.atual == OPERACOES[-1]["id"] and len(app.paginas) == len(OPERACOES)
    for ambiente in (config.AMBIENTE_HML, config.AMBIENTE_PRD):
        app.ambiente_var.set(ambiente)
        app.update()
        assert app.ambiente_var.get() == ambiente


def conferir_dialogo(app):
    """Janela de temas: aplica um tema pronto, cria um tema, edita e exclui."""
    app.show_hub()
    app.abrir_temas()
    dialogo = app._dialogo_temas
    dialogo.update()
    dialogo._escolher("aurora")
    assert temas.ativo() == "aurora"
    dialogo._abrir_editor(None)
    dialogo.nome_var.set("Teste Laranja")
    dialogo._definir_cor("accent", "#ff7a1a")
    dialogo._campos["bg"][1].set("isto não é cor")
    dialogo._digitou("bg")  # código inválido: volta para a cor que estava
    assert dialogo.cores["bg"] == temas.PRONTOS["aurora"]["cores"]["bg"]
    dialogo.update()
    dialogo._salvar()
    criado = temas.ativo()
    assert criado in temas.personalizados() and COLORS["accent"] == "#ff7a1a", criado
    dialogo._abrir_editor(criado)
    dialogo._definir_cor("accent", "#00ffaa")
    dialogo._salvar()
    assert temas.ativo() == criado and COLORS["accent"] == "#00ffaa" and len(temas.personalizados()) == 1
    with mock.patch("tkinter.messagebox.askyesno", return_value=True):
        dialogo._excluir()
    assert temas.ativo() == temas.PADRAO and not temas.personalizados()
    dialogo.destroy()
    app.update()


def conferir_lateral(app):
    """A alça da borda recolhe a barra para só os ícones e a mostra de novo, de uma vez (sem
    animação); a escolha fica guardada."""
    app.update()
    larga = app.lateral.winfo_width()
    assert app.alca.cget("text") == "‹" and abs(int(app.alca.place_info()["x"]) - larga) <= 1
    assert app.alca.bind("<Button-1>"), "a alça precisa responder ao clique"
    app.alternar_lateral()  # o que o clique na alça (ou Ctrl+B) chama
    assert int(app.lateral.cget("width")) < larga / 2  # já na largura final, sem quadros intermediários
    app.update()
    estreita = app.lateral.winfo_width()
    assert app.lateral_recolhida and estreita < larga / 2, estreita
    assert app.alca.cget("text") == "›" and abs(int(app.alca.place_info()["x"]) - estreita) <= 1
    assert preferencias.obter("lateral_recolhida") is True
    app.abrir(OPERACOES[0]["id"], perguntar=False)  # navega pelos ícones
    app.update()
    app.alternar_lateral()
    assert int(app.lateral.cget("width")) == larga
    app.update()
    assert not app.lateral_recolhida and app.lateral.winfo_width() == larga
    assert app.alca.cget("text") == "‹" and preferencias.obter("lateral_recolhida") is False


def garantir_janela_normal(app):
    """A janela do teste aparece por cima de tudo; se alguém a minimizar ou maximizar durante o
    teste (fora do app), as medidas de posição perdem o sentido. Restaura e avisa."""
    app.update()
    if app.state() != "normal":
        print(f"      (janela estava '{app.state()}' por ação de fora do teste; restaurada)")
        app.state("normal")
        app.lift()
        app.update()


def _posicoes_hub(app):
    """Onde estão, em pixels da janela, a busca e cada card do hub."""
    garantir_janela_normal(app)
    base = app.winfo_rootx()
    cards = [c["canvas"].winfo_rootx() - base for cards in app.hub._secoes_cards for c in cards]
    return app.hub.busca_entry.winfo_rootx() - base, cards


def conferir_tema_sem_deslocar(app):
    """Bug corrigido: trocar o tema várias vezes (claro <-> escuro) não pode mover os cards nem a
    busca para o lado, em nenhuma largura de janela, com a barra lateral aberta ou recolhida."""
    app.show_hub()
    for recolhida in (False, True):
        if app.lateral_recolhida != recolhida:
            app.alternar_lateral()
        for largura in (app.minsize()[0], 1280, 1366, 1600, 1920):
            app.geometry(f"{largura}x{app.minsize()[1]}")
            app.update()
            antes = _posicoes_hub(app)
            canvas = app.hub.canvas
            esperado = 1 if canvas.winfo_width() < 2 * 330 else (2 if canvas.winfo_width() < 3 * 335 else 3)
            assert app.hub.colunas in (esperado, esperado - 1, esperado + 1), (largura, app.hub.colunas)
            for i in range(6):
                assert app.aplicar_tema("claro" if i % 2 == 0 else temas.PADRAO)
                assert _posicoes_hub(app) == antes, (largura, recolhida, i, antes, _posicoes_hub(app))
                assert app.hub.canvas.xview()[0] == 0.0  # nenhuma rolagem horizontal escondida
            # nada do conteúdo fica fora da área visível, nem para a esquerda nem para a direita
            app.update()
            canvas = app.hub.canvas  # o hub foi recriado pela troca de tema
            esquerda = min(app.hub.secoes.winfo_rootx(), app.hub.busca.winfo_rootx())
            direita = max(app.hub.secoes.winfo_rootx() + app.hub.secoes.winfo_width(),
                          app.hub.busca.winfo_rootx() + app.hub.busca.winfo_width())
            assert canvas.winfo_rootx() <= esquerda and direita <= canvas.winfo_rootx() + canvas.winfo_width(), \
                (largura, recolhida, esquerda, direita)
    app.alternar_lateral()
    app.geometry(f"{app.minsize()[0]}x{app.minsize()[1]}")
    app.update()


def _rodar(app, segundos):
    """Deixa o app rodar. Se a janela for minimizada de fora no meio (ex.: "Mostrar área de
    trabalho"), restaura: minimizada, os Pokémon pausam de propósito e as conferências de tempo
    perderiam o sentido."""
    fim = time.monotonic() + segundos
    while time.monotonic() < fim:
        if app.state() == "iconic":
            app.deiconify()
        app.update()
        app.after(10)


def conferir_pokemon(app):
    """Pokémon decorativos: no hub andam sem parar, só fora do bloco central e dos cards, atrás
    de tudo e sem clique próprio; o das telas anda num espaço só dele."""
    from ui import pokemon
    garantir_janela_normal(app)
    app.show_hub()
    _rodar(app, 1.5)
    bando, canvas = app.hub.bando, app.hub.canvas
    assert len(bando.andarilhos) >= 4, len(bando.andarilhos)
    assert len({a.arquivo for a in bando.andarilhos}) == len(bando.andarilhos)  # nenhum repetido na tela
    assert all(canvas.type(a.item) == "image" for a in bando.andarilhos)
    itens = canvas.find_all()
    assert set(itens[:len(bando.andarilhos)]) == {a.item for a in bando.andarilhos}  # atrás de todos os textos
    assert not canvas.tag_bind("pokemon") and not canvas.bind("<Button-1>")  # sem clique próprio

    # andam (posição e quadro mudam) e nunca entram no bloco central nem nos cards
    antes = {a.arquivo: (a.x, a.y) for a in bando.andarilhos}
    direcoes = set()
    for _ in range(60):
        _rodar(app, 0.05)
        _limites, proibidos = app.hub._area_dos_pokemon()
        for a in bando.andarilhos:
            direcoes.add(a.direcao)
            assert not any(pokemon._cruza(a.caixa, p) for p in proibidos), (a.arquivo, a.caixa, proibidos)
    moveram = [a for a in bando.andarilhos if a.arquivo in antes and (a.x, a.y) != antes[a.arquivo]]
    assert len(moveram) >= len(antes) // 2, (len(moveram), len(antes))
    assert len(direcoes) >= 3, direcoes  # para os lados e para cima e para baixo

    # um Pokémon posto em cima da busca não pega o clique: a busca é uma janela embutida, que o
    # Tk sempre desenha por cima dos itens do canvas
    entrada = app.hub.busca_entry
    cx, cy = entrada.winfo_rootx() + entrada.winfo_width() // 2, entrada.winfo_rooty() + entrada.winfo_height() // 2
    alguem = bando.andarilhos[0]
    canvas.coords(alguem.item, cx - canvas.winfo_rootx() - 10, cy - canvas.winfo_rooty() - 10)
    app.update()
    na_tela = app.winfo_containing(cx, cy)
    if na_tela is not None:  # None quando outra janela do Windows está por cima neste momento
        assert na_tela is entrada, na_tela

    # revezamento: quem deu o tempo sai pela lateral e outro entra no lugar
    largura = canvas.winfo_width()
    quem_sai = min(bando.andarilhos, key=lambda a: min(a.x, largura - a.x))  # o mais perto de uma lateral
    quem_sai.ate_sair = 0
    _rodar(app, 0.2)
    assert quem_sai.saindo
    for _ in range(600):
        if quem_sai not in bando.andarilhos:
            break
        _rodar(app, 0.05)
    assert quem_sai not in bando.andarilhos, "deveria ter saído pela lateral"
    for _ in range(60):  # entra um novo (que ainda não estava na tela) pela lateral
        if any(a.arquivo not in antes for a in bando.andarilhos):
            break
        _rodar(app, 0.05)
    assert any(a.arquivo not in antes for a in bando.andarilhos), "outro deveria entrar no lugar"

    # a fila passa pelos 50 antes de repetir
    bando._fila = []
    na_tela = {a.arquivo for a in bando.andarilhos}
    vistos = set()
    for _ in range(len(pokemon.POKEMON)):
        vistos.add(bando._proximo())
    assert vistos | na_tela == set(pokemon.POR_ARQUIVO), "a fila deveria passar por todos"

    # hub escondido: ninguém anda
    app.abrir("nfcom.consulta_sefaz", perguntar=False)
    app.update()
    parados = {a.arquivo: (a.x, a.y) for a in bando.andarilhos}
    _rodar(app, 0.5)
    assert parados == {a.arquivo: (a.x, a.y) for a in bando.andarilhos}

    for op_id in ("nfcom.download_xmls", "nfse.correcao_xml", "nfce.download_xmls", "relatorios.exportador"):
        app.abrir(op_id, perguntar=False)
        app.update()
        companheiros = [w for w in app.paginas[op_id].winfo_children()[0].winfo_children()
                        if isinstance(w, pokemon.Companheiro)]
        assert len(companheiros) == 1 and companheiros[0].nome in pokemon.companheiros(), (op_id, companheiros)
        companheiro = companheiros[0]
        assert int(companheiro.cget("height")) == pokemon.ALTURA_COMPANHEIRO + companheiro.TOPO
        x0 = companheiro.x
        _rodar(app, 0.4)
        assert companheiro.x != x0 and companheiro.direcao in (pokemon.DIREITA, pokemon.ESQUERDA)
        assert 0 <= companheiro.x <= companheiro.LARGURA - companheiro.folha.largura
        # passar o mouse: pulinho com balão; clicar: golpe (o clique é dele, num espaço só dele)
        companheiro._ao_passar()
        assert companheiro.pulo_ms > 0 and companheiro.emote is not None
        companheiro._ao_clicar()
        assert companheiro.acao == "golpe"
        _rodar(app, 0.8)
        assert companheiro.acao is None and companheiro.pulo_ms == 0  # voltou a andar
    app.show_hub()


def _companheiros_vivos(app):
    from ui import pokemon
    vistos, pilha = [], [app]
    while pilha:
        w = pilha.pop()
        if isinstance(w, pokemon.Companheiro) and w.winfo_exists():
            vistos.append(w)
        pilha.extend(w.winfo_children())
    return vistos


def conferir_interacoes(app):
    """Seguir o ponteiro (perto dele, sem entrar no bloco central nem nos cards), golpear junto
    com o clique (com faísca), parar de seguir depois de um tempo, pular quando o ponteiro passa,
    pular ao ser clicado, cumprimentar outro, e o clique continuar indo para o widget."""
    from unittest import mock as _mock
    from ui import pokemon
    garantir_janela_normal(app)
    app.show_hub()
    _rodar(app, 1.0)
    bando, canvas = app.hub.bando, app.hub.canvas
    for a in bando.andarilhos:  # todos livres para reagir (o povoamento pode ter acabado de pôr um entrando)
        a.espera_ms, a.seguindo_ms, a.acao, a.pausa_ms, a.entrando, a.saindo = 0, 0, None, 0, False, False

    def na_tela(ponto):
        return (canvas.winfo_rootx() + round(ponto[0] - canvas.canvasx(0)),
                canvas.winfo_rooty() + round(ponto[1] - canvas.canvasy(0)))

    # o ponteiro passa por cima de um: com a sorte a favor, ele começa a seguir
    seguidor = bando.andarilhos[0]
    ponteiro = {"ponto": seguidor.centro}
    with _mock.patch.object(bando, "_ponteiro", lambda: ponteiro["ponto"]):
        with _mock.patch("random.random", return_value=0.0):
            bando._notar(ponteiro["ponto"])
        assert seguidor.seguindo_ms > 0 and seguidor.acao == "pulo" and seguidor.emote is not None
        # o ponteiro vai para um lugar livre que ele alcança (a rota chega lá), a 120-300 px: ele vai
        # atrás, sem nunca invadir o bloco central nem os cards
        limites, proibidos = app.hub._area_dos_pokemon()
        proibidos = [(p[0] - bando.FOLGA, p[1] - bando.FOLGA, p[2] + bando.FOLGA, p[3] + bando.FOLGA) for p in proibidos]
        w, h = seguidor.folha.largura, seguidor.folha.altura
        alvo = None
        for _ in range(300):
            lugar = bando._lugar_livre(w, h, limites, proibidos)
            if lugar is None:
                continue
            candidato = (lugar[0] + w / 2, lugar[1] + h / 2)
            rota = pokemon._rota(seguidor.centro, candidato, w, h, limites, proibidos, bando.GRADE)
            if 120 <= math.dist(seguidor.centro, candidato) <= 300 and rota and math.dist(rota[-1], candidato) < bando.GRADE:
                alvo = candidato
                break
        assert alvo, "sem lugar alcançável para testar"
        ponteiro["ponto"] = alvo
        seguidor.seguindo_ms = 60000
        distancia = math.dist(seguidor.centro, ponteiro["ponto"])
        for _ in range(60):
            _rodar(app, 0.05)
            assert not any(pokemon._cruza(seguidor.caixa, p) for p in proibidos), seguidor.caixa
        assert math.dist(seguidor.centro, ponteiro["ponto"]) < distancia - 40, "deveria ter ido atrás do ponteiro"

        # do outro lado do bloco central, a rota contorna o bloco por baixo (o caminho reto está fechado)
        bloco = proibidos[0]
        de, ate = (bloco[0] - 30, bloco[1] + 20), (bloco[2] + 30, bloco[1] + 20)
        rota = pokemon._rota(de, ate, 24, 24, limites, proibidos, bando.GRADE)
        assert rota and math.dist(rota[-1], ate) < bando.GRADE and max(y for _x, y in rota) > bloco[3], rota[:5]

        # clique: quem segue golpeia na direção do ponteiro, sai uma onda e, no acerto, uma faísca
        _rodar(app, 0.3)
        bando.clique(*na_tela(ponteiro["ponto"]))
        assert seguidor.acao == "golpe", seguidor.acao
        assert any(e[3] == "onda" for e in bando.efeitos)
        faisca = False
        for _ in range(20):
            _rodar(app, 0.05)
            faisca = faisca or any(e[3] == "faisca" for e in bando.efeitos)
        assert faisca and seguidor.acao is None and seguidor.seguindo_ms > 0
        _rodar(app, 0.5)
        assert not bando.efeitos  # efeitos somem sozinhos

        # o tempo de seguir acaba: ele para, mostra um balão e descansa antes de seguir de novo
        seguidor.acao, seguidor.seguindo_ms = None, 1  # (fora de um golpe ou pulo, que não deixam o tempo correr)
        _rodar(app, 0.15)
        assert seguidor.seguindo_ms == 0 and seguidor.espera_ms > 0 and seguidor.emote is not None

        # o ponteiro passa por cima de outro, sem a sorte de seguir: ele só pula com um balão
        outro = next(a for a in bando.andarilhos if a is not seguidor and not a.ocupado)
        outro.espera_ms = 0  # pode ter reagido ao ponteiro há pouco (descanso de 4 s)
        ponteiro["ponto"] = outro.centro
        with _mock.patch("random.random", return_value=0.99):
            bando._notar(ponteiro["ponto"])
        assert outro.acao == "pulo" and outro.seguindo_ms == 0 and outro.emote is not None

    # clique em cima de um, no fundo do início: pula com um coração
    _rodar(app, 0.6)
    clicado = next(a for a in bando.andarilhos if not a.ocupado)
    with _mock.patch("random.random", return_value=0.99):
        bando.clique(*na_tela(clicado.centro), widget=canvas)
    assert clicado.acao == "pulo" and canvas.itemcget(clicado.emote[0], "text") == "♥"

    # dois que se esbarram: param, se olham e se cumprimentam
    _rodar(app, 0.6)
    a, b = [x for x in bando.andarilhos if not x.ocupado][:2]
    b.x, b.y = a.x + a.folha.largura + 2, a.y + (a.folha.altura - b.folha.altura) / 2
    a.encontro_ms = b.encontro_ms = 0
    with _mock.patch("random.random", return_value=0.0):
        bando._encontros()
    assert a.pausa_ms > 0 and b.pausa_ms > 0 and a.acao == b.acao == "pulo"
    assert a.direcao == pokemon.DIREITA and b.direcao == pokemon.ESQUERDA  # um olhando para o outro

    # o clique é só observado: um clique na busca chega na busca, e o bando também fica sabendo
    entrada = app.hub.busca_entry
    recebidos = []
    funcao = entrada.bind("<Button-1>", lambda _e: recebidos.append("busca"), add="+")
    with _mock.patch.object(bando, "clique", lambda *a, **k: recebidos.append("bando")):
        entrada.event_generate("<Button-1>", x=5, y=5)
        entrada.event_generate("<ButtonRelease-1>", x=5, y=5)
        app.update()
    entrada.unbind("<Button-1>", funcao)
    assert recebidos == ["busca", "bando"], recebidos

    # só ficam carregadas as animações de quem está na tela (hub e companheiros)
    em_uso = {x.arquivo for x in bando.andarilhos} | {c.nome for c in _companheiros_vivos(app)}
    assert set(getattr(app, "_pokemon_animacoes", {})) == em_uso, \
        set(getattr(app, "_pokemon_animacoes", {})) ^ em_uso


def conferir_visao_cliente(app):
    """Visão para o cliente (botão na janela de temas): na hora, logo e ícone da Vivo e nenhum
    Pokémon (início e cabeçalhos), inclusive nas telas abertas depois e após trocar o tema; fica
    guardada; desligada, tudo volta como estava."""
    from core import preferencias as prefs
    from ui import pokemon
    from ui.tema_dialogo import DialogoTemas
    garantir_janela_normal(app)
    app.abrir("nfcom.download_xmls", perguntar=False)  # uma tela com companheiro, aberta antes
    app.show_hub()
    _rodar(app, 1.2)
    assert not app.visao_cliente and app._arquivo_logo() == "pikachu_logo.png"
    assert app.hub.bando.andarilhos, "deveria haver Pokémon antes de ligar"
    companheiro = [c for c in _companheiros_vivos(app)][0]
    assert companheiro.winfo_manager() == "pack"
    logo_antes = app._logo_label.cget("image")

    dialogo = DialogoTemas(app)  # o botão fica na janela de temas
    dialogo.botao_visao_cliente.invoke()
    app.update()
    assert app.visao_cliente and prefs.obter("visao_cliente") is True
    assert "ligada" in dialogo.botao_visao_cliente.cget("text")
    dialogo.destroy()
    assert app._arquivo_logo() == "vivo_logo.png" and app._logo_label.cget("image") != logo_antes
    canvas = app.hub.canvas
    assert not app.hub.bando.andarilhos and not canvas.find_withtag("pokemon")  # sumiram na hora
    assert companheiro.winfo_manager() == ""  # saiu do cabeçalho
    _rodar(app, 1.5)
    assert not app.hub.bando.andarilhos and not canvas.find_withtag("pokemon")  # e não voltam sozinhos
    app.hub.bando.clique(canvas.winfo_rootx() + 20, canvas.winfo_rooty() + 20, widget=canvas)
    assert not app.hub.bando.efeitos
    app.abrir("nfse.correcao_xml", perguntar=False)  # tela aberta depois: já sem companheiro
    app.update()
    assert all(c.winfo_manager() == "" for c in _companheiros_vivos(app))

    assert app.aplicar_tema(temas.PADRAO)  # recriar as telas mantém a visão para o cliente
    app.show_hub()
    _rodar(app, 1.2)
    assert app._arquivo_logo() == "vivo_logo.png" and not app.hub.bando.andarilhos
    assert all(c.winfo_manager() == "" for c in _companheiros_vivos(app))

    app.definir_visao_cliente(False)
    app.update()
    assert not app.visao_cliente and prefs.obter("visao_cliente") is False
    assert app._arquivo_logo() == "pikachu_logo.png"
    assert _companheiros_vivos(app) and all(c.winfo_manager() == "pack" for c in _companheiros_vivos(app))
    _rodar(app, 1.5)
    assert app.hub.bando.andarilhos, "os Pokémon deveriam voltar ao desligar"
    assert pokemon.escondidos() is False


def conferir_sprites(app):
    """As 50 animações (andar, golpe e pulo) estão em assets/pokemon, com as 8 direções, num
    tamanho que não domina a tela; e nada fica na memória depois de solto."""
    from ui import pokemon
    assert len(pokemon.POKEMON) == 50 and len(pokemon.POR_ARQUIVO) == 50
    assert pokemon.disponiveis() == [p.arquivo for p in pokemon.POKEMON], "faltam animações em assets/pokemon"
    assert len(pokemon.companheiros()) >= 8
    antes = set(getattr(app, "_pokemon_animacoes", {}))
    for p in pokemon.POKEMON:
        anims = pokemon.pegar(app, p.arquivo)
        try:
            for nome in pokemon.ANIMACOES:
                anim = anims[nome]
                assert len(anim.quadros) == len(pokemon.DIRECOES) == 8, (p.arquivo, nome)
                assert all(len(fila) == len(anim.duracoes) >= 2 for fila in anim.quadros), (p.arquivo, nome)
                assert all(d > 0 for d in anim.duracoes), (p.arquivo, nome)
                for direcao, fila in enumerate(anim.quadros):
                    largura, altura, _dx, _dy = anim.linhas[direcao]
                    assert all((q.width(), q.height()) == (largura, altura) for q in fila), (p.arquivo, nome)
            andar = anims["andar"]
            assert len(set(andar.linhas)) == 1, p.arquivo  # a mesma caixa nas 8 direções
            assert 28 <= andar.altura <= 72 and andar.largura <= 90, (p.arquivo, andar.largura, andar.altura)
            assert anims["golpe"].impacto is not None, p.arquivo
            primeiro = andar.quadros[pokemon.BAIXO][0]
            visiveis = sum(not primeiro.transparency_get(x, y) for x in range(0, andar.largura, 2)
                           for y in range(0, andar.altura, 2))
            assert visiveis > 20, (p.arquivo, "quadro vazio")
        finally:
            pokemon.soltar(app, p.arquivo)
    assert set(getattr(app, "_pokemon_animacoes", {})) == antes  # soltou tudo o que pegou


def conferir_movimento_reduzido(app):
    """Com movimento reduzido (Windows ou a opção da janela de temas), nada anda nem esmaece:
    as transições vão direto ao estado final e os Pokémon ficam parados, de frente."""
    from unittest import mock as _mock
    from ui import animacao, pokemon
    garantir_janela_normal(app)
    with _mock.patch.object(animacao, "ativas", return_value=False):
        app.show_hub()
        _rodar(app, 0.8)
        bando = app.hub.bando
        posicoes = {a.arquivo: (a.x, a.y) for a in bando.andarilhos}
        _rodar(app, 1.2)
        assert posicoes == {a.arquivo: (a.x, a.y) for a in bando.andarilhos}  # ninguém andou
        assert all(a.direcao == pokemon.BAIXO and a.passos.quadro == 0 for a in bando.andarilhos)
        rotulo = app.hub.busca_entry
        animacao.cor(rotulo, {"bg": "#123456"})
        assert rotulo.cget("bg") == "#123456"  # direto, sem quadros intermediários
        assert app.aplicar_tema(temas.PADRAO)
        assert float(app.attributes("-alpha")) == 1.0  # a troca de tema não esmaece
    animacao.definir_preferencia(False)
    assert not animacao.ativas()
    animacao.definir_preferencia(True)


def conferir_contador(app):
    """Contador acende quando o valor muda e volta à cor dele."""
    from ui.widgets import stat_box
    app.abrir("nfce.download_xmls", perguntar=False)
    pagina = app.paginas["nfce.download_xmls"]
    contador = pagina.count_labels["ok"]
    cor = contador.cget("fg")
    contador["text"] = "7"
    assert contador.cget("text") == "7" and contador.cget("fg") != cor  # acendeu na hora
    for _ in range(40):
        app.update()
        app.after(20)
    assert contador.cget("fg") == cor  # voltou
    box, valor = stat_box(pagina, "TESTE", "#33aa55")
    valor.configure(fg="#ff0000")
    valor["text"] = "3"
    for _ in range(40):
        app.update()
        app.after(20)
    assert valor.cget("fg") == "#ff0000"  # a cor nova da tela vale
    box.destroy()
    app.show_hub()


def conferir_roda(app):
    """A roda rola a tela a partir de qualquer widget dela, até o fim, e volta."""
    app.geometry(f"{app.winfo_width()}x{app.minsize()[1]}")  # janela baixa: toda tela precisa rolar
    app.update()
    for op_id in ("nfce.reprocessamento", "relatorios.exportador"):
        app.abrir(op_id, perguntar=False)
        app.update()
        moldura, pagina = app._molduras[op_id], app.paginas[op_id]
        fundo = [w for w in pagina.winfo_children()][0]
        while fundo.winfo_children():  # o widget mais interno do cabeçalho (era onde a roda não pegava)
            fundo = fundo.winfo_children()[0]
        assert moldura.canvas.yview()[0] == 0
        assert rolar_sob(fundo, -120), op_id
        app.update()
        assert moldura.canvas.yview()[0] > 0, op_id
        for _ in range(60):
            rolar_sob(fundo, -120)
        assert moldura.canvas.yview()[1] == 1.0, op_id
        for _ in range(60):
            rolar_sob(fundo, 120)
        assert moldura.canvas.yview()[0] == 0, op_id
    app.show_hub()
    app.update()
    cartao = app.hub.secoes.winfo_children()[1].winfo_children()[0]  # um card do hub
    assert rolar_sob(cartao, -120) and app.hub.canvas.yview()[0] > 0


def main():
    if PASTA_PRINTS and sys.platform == "win32":
        # Só para o print sair com as coordenadas certas em telas com escala > 100%
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    # Sem perguntas na tela durante o teste (config incompleta -> abre mesmo assim)
    with mock.patch("tkinter.messagebox.askyesno", return_value=True), \
         mock.patch("tkinter.messagebox.showwarning"):
        app = App()
        app.report_callback_exception = lambda tipo, valor, tb: erros_de_fundo.append(
            "".join(traceback.format_exception(tipo, valor, tb)))
        app.tk.createcommand("bgerror", lambda mensagem: erros_de_fundo.append(str(mensagem)))
        if PASTA_PRINTS:  # o print copia a tela: a janela precisa estar visível, por cima de tudo
            app.geometry("+0+0")
            app.lift()
            app.attributes("-topmost", True)
        else:  # fora da área visível: não aparece por cima do trabalho de ninguém (nem é minimizada no meio)
            app.geometry("+4000+0")
        app.update()
        print_janela(app, "00_hub_producao")

        abrir_operacoes(app)

        app.show_hub()
        app.ambiente_var.set(config.AMBIENTE_HML)
        app.update()
        assert app.ambiente_var.get() == config.AMBIENTE_HML
        print_janela(app, "00_hub_homologacao")

        app.hub.busca_var.set("cancel")
        app.update()
        print_janela(app, "00_hub_busca")

        app.hub.busca_var.set("nfce")
        app.update()
        print_janela(app, "00_hub_nfce")
        app.hub.busca_var.set("")

        etapa("interface: todos os temas, com as telas abertas", lambda: conferir_temas(app))
        etapa("interface: janela de temas (aplicar, criar, editar, excluir)", lambda: conferir_dialogo(app))
        etapa("interface: barra lateral recolhida e mostrada", lambda: conferir_lateral(app))
        etapa("interface: roda do mouse rola a tela de qualquer ponto", lambda: conferir_roda(app))
        etapa("interface: trocar o tema várias vezes não desloca os cards (várias larguras)",
              lambda: conferir_tema_sem_deslocar(app))
        etapa("interface: Pokémon decorativos não bloqueiam clique", lambda: conferir_pokemon(app))
        etapa("interface: Pokémon seguem o ponteiro, golpeiam no clique e se cumprimentam",
              lambda: conferir_interacoes(app))
        etapa("interface: as 50 animações dos Pokémon (andar, golpe, pulo) estão completas",
              lambda: conferir_sprites(app))
        etapa("interface: visão para o cliente troca a logo e some com os Pokémon (e volta)",
              lambda: conferir_visao_cliente(app))
        etapa("interface: movimento reduzido desliga as animações", lambda: conferir_movimento_reduzido(app))
        etapa("interface: contadores acendem quando o valor muda", lambda: conferir_contador(app))

        # Dá tempo de qualquer after() esquecido das telas recriadas disparar (e aparecer como erro)
        for _ in range(40):
            app.update()
            app.after(10)
        app.destroy()

    if erros_de_fundo:
        erros.append("erros em callbacks do Tk")
        print("ERRO  callbacks do Tk:\n" + "\n".join(erros_de_fundo[:5]))
    print(f"\n{len(OPERACOES)} telas e 11 conferências de interface; {len(erros)} erro(s).")
    sys.exit(1 if erros else 0)


if __name__ == "__main__":
    main()
