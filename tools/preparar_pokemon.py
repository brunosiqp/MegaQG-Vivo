"""
Baixa e prepara as animações dos Pokémon do app (assets/pokemon), a partir do PMD SpriteCollab
(https://github.com/PMDCollab/SpriteCollab, licença CC BY-NC 4.0).

Para cada Pokémon do catálogo (ui/pokemon.py, POKEMON) e cada animação usada (ANIMACOES: andar,
golpe e pulo):
  - baixa a folha da animação (8 linhas, uma por direção), AnimData.xml (tamanho e tempo de cada
    quadro) e credits.txt (quem fez o sprite);
  - recorta os quadros no menor retângulo que contém o Pokémon (as folhas vêm com muita sobra
    transparente): no andar, o mesmo retângulo nas 8 direções (é a caixa que anda e colide); no
    golpe e no pulo, um por direção (o golpe avança para um lado só, e um retângulo comum às 8
    direções ficaria enorme). Guarda onde cada retângulo fica em relação ao centro do quadro: é
    o que alinha uma animação com a outra na hora de trocar (o centro do quadro é o mesmo ponto
    do corpo em todas as animações);
  - muda o tamanho conforme tamanho_na_tela: os pequenos crescem, os grandes quase não, para
    nenhum dominar a tela;
  - grava assets/pokemon/<arquivo>-<animação>.png (com paleta: pixel art tem poucas cores, e o
    arquivo fica bem menor que o PNG em cores completas que o Tk grava),
    assets/pokemon/animacoes.json (tempos e, por direção, tamanho e deslocamento do quadro, e o
    quadro do golpe que "acerta") e assets/pokemon/CREDITOS.md.

Só usa a biblioteca padrão (o Tk lê o PNG; a gravação é feita aqui). Uso, a partir da raiz do
projeto:
    python tools/preparar_pokemon.py [pasta_de_cache]
Os arquivos baixados ficam na pasta de cache (por padrão, %TEMP%/megaqg_pmd) e não são
baixados de novo.
"""
import glob
import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import tkinter as tk
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from collections import OrderedDict

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from ui.pokemon import ANIMACOES, DIRECOES, POKEMON, pasta  # noqa: E402

FONTE = "https://raw.githubusercontent.com/PMDCollab/SpriteCollab/master"
PAGINA = "https://sprites.pmdcollab.org/#/{numero:04d}"
FUNDO = "#fe00fe"    # cor que não aparece nos sprites: marca os pixels transparentes
MS_POR_TICK = 1000 / 60  # os tempos do AnimData são em quadros do jogo (60 por segundo)


def tamanho_na_tela(altura):
    """Altura com que o Pokémon aparece, a partir da altura original (recortada) dele andando:
    até 36 px cresce 45%; acima disso cresce cada vez menos (os lendários ficam por volta de
    60 px), para nenhum dominar a tela."""
    return 1.45 * altura if altura <= 36 else 52.2 + (altura - 36) * 0.35


def baixar(url, destino):
    if os.path.exists(destino):
        return
    try:
        with urllib.request.urlopen(url, timeout=60) as resposta, open(destino, "wb") as f:
            f.write(resposta.read())
    except Exception:
        # Em redes que inspecionam HTTPS o Python pode recusar o certificado; o curl do Windows
        # usa o repositório de certificados do sistema (sem checar revogação, que a rede bloqueia)
        subprocess.run(["curl", "-fsS", "--ssl-no-revoke", "-m", "60", "-o", destino, url], check=True)


def ler_animacao(xml, nome):
    """(largura do quadro, altura do quadro, tempos, quadro de impacto ou None) de uma animação."""
    anims = {a.findtext("Name"): a for a in ET.parse(xml).getroot().iter("Anim")}
    anim = anims[nome]
    while anim.find("CopyOf") is not None:
        anim = anims[anim.findtext("CopyOf")]
    duracoes = [int(d.text) for d in anim.iter("Duration")]
    impacto = anim.findtext("HitFrame")
    return (int(anim.findtext("FrameWidth")), int(anim.findtext("FrameHeight")), duracoes,
            int(impacto) if impacto is not None else None)


def pixels(raiz, imagem):
    """Matriz de cores ("#rrggbb", ou None no transparente) da imagem inteira, numa chamada só."""
    linhas = raiz.tk.call(imagem, "data", "-background", FUNDO)
    return [[None if c == FUNDO else c for c in str(linha).split()] for linha in linhas]


def recorte(px, largura_q, altura_q, colunas, linhas):
    """Menor retângulo (relativo ao quadro) com algum pixel visível em qualquer quadro das
    linhas (direções) dadas."""
    x0 = y0 = 10 ** 9
    x1 = y1 = -1
    for linha in linhas:
        for coluna in range(colunas):
            ox, oy = coluna * largura_q, linha * altura_q
            for y in range(altura_q):
                fila = px[oy + y][ox:ox + largura_q]
                xs = [x for x, c in enumerate(fila) if c is not None]
                if xs:
                    x0, x1 = min(x0, xs[0]), max(x1, xs[-1])
                    y0, y1 = min(y0, y), max(y1, y)
    if x1 < 0:  # direção sem nenhum pixel: um quadro de 1 px
        return 0, 0, 1, 1
    return x0, y0, x1 + 1, y1 + 1


def _luma(r, g, b):
    return 0.3 * r + 0.59 * g + 0.11 * b


def redimensionar(bloco, fator):
    """Muda o tamanho de um quadro. Para cima, vizinho mais próximo (pixel art continua nítida).
    Para baixo, por área: o pixel fica visível se a maior parte da área for, com a cor que
    predomina na área (ou a do contorno, se houver contorno escuro suficiente, para o contorno
    não sumir). Sem misturar cores, a paleta continua a do sprite original: nítido e com poucas
    cores (o PNG com paleta fica pequeno)."""
    h, w = len(bloco), len(bloco[0])
    largura, altura = max(1, round(w * fator)), max(1, round(h * fator))
    if fator >= 1:
        return [[bloco[min(h - 1, int((y + 0.5) / fator))][min(w - 1, int((x + 0.5) / fator))]
                 for x in range(largura)] for y in range(altura)]
    saida = []
    for y in range(altura):
        ya, yb = y / fator, (y + 1) / fator
        fila = []
        for x in range(largura):
            xa, xb = x / fator, (x + 1) / fator
            total, cores = 0.0, []
            for sy in range(int(ya), min(h, math.ceil(yb))):
                peso_y = min(yb, sy + 1) - max(ya, sy)
                for sx in range(int(xa), min(w, math.ceil(xb))):
                    peso = peso_y * (min(xb, sx + 1) - max(xa, sx))
                    total += peso
                    if bloco[sy][sx]:
                        c = bloco[sy][sx]
                        cores.append((peso, int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)))
            visivel = sum(c[0] for c in cores)
            if not cores or visivel < total * 0.5:
                fila.append(None)
                continue
            escura = min(cores, key=lambda c: _luma(*c[1:]))
            if _luma(*escura[1:]) < 60 and escura[0] >= visivel * 0.25:
                r, g, b = escura[1:]
            else:
                pesos = {}
                for peso, *rgb in cores:
                    pesos[tuple(rgb)] = pesos.get(tuple(rgb), 0) + peso
                r, g, b = max(pesos, key=pesos.get)
            fila.append(f"#{r:02x}{g:02x}{b:02x}")
        saida.append(fila)
    return saida


def gravar_png(caminho, matriz):
    """Grava a matriz de cores (None = transparente) como PNG. Com até 255 cores usa paleta
    (o índice 0 é o transparente) e a menor profundidade que couber; senão, RGBA."""
    altura, largura = len(matriz), len(matriz[0])
    cores = sorted({c for fila in matriz for c in fila if c})
    if len(cores) <= 255:
        indice = {c: i + 1 for i, c in enumerate(cores)}
        n = len(cores) + 1
        bits = 1 if n <= 2 else 2 if n <= 4 else 4 if n <= 16 else 8
        por_byte = 8 // bits
        bruto = bytearray()
        for fila in matriz:
            valores = [indice[c] if c else 0 for c in fila]
            bruto.append(0)  # filtro 0 (o recomendado para paleta)
            for i in range(0, largura, por_byte):
                byte = 0
                for j, v in enumerate(valores[i:i + por_byte]):
                    byte |= v << (8 - bits * (j + 1))
                bruto.append(byte)
        pedacos = [(b"IHDR", struct.pack(">IIBBBBB", largura, altura, bits, 3, 0, 0, 0)),
                   (b"PLTE", bytes(3) + b"".join(bytes.fromhex(c[1:]) for c in cores)),
                   (b"tRNS", bytes(1))]
    else:
        bruto = bytearray()
        for fila in matriz:
            bruto.append(0)
            for c in fila:
                bruto += bytes.fromhex(c[1:] + "ff") if c else bytes(4)
        pedacos = [(b"IHDR", struct.pack(">IIBBBBB", largura, altura, 8, 6, 0, 0, 0))]
    pedacos += [(b"IDAT", zlib.compress(bytes(bruto), 9)), (b"IEND", b"")]
    with open(caminho, "wb") as f:
        f.write(bytes.fromhex("89504e470d0a1a0a"))  # assinatura do PNG
        for tipo, dados in pedacos:
            f.write(struct.pack(">I", len(dados)) + tipo + dados
                    + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF))


def nomes_dos_creditos(cache):
    nomes = {}
    with open(os.path.join(cache, "credit_names.txt"), encoding="utf-8") as f:
        next(f)
        for linha in f:
            partes = linha.rstrip("\n").split("\t")
            if len(partes) >= 2:
                nomes[partes[1]] = (partes[0], partes[2] if len(partes) > 2 else "")
    return nomes


def creditos(arquivo, nomes, anims):
    """Quem fez as animações usadas (ou, se ninguém estiver marcado nelas, quem fez o sprite)."""
    usadas, todos = OrderedDict(), OrderedDict()
    with open(arquivo, encoding="utf-8") as f:
        for linha in f:
            partes = linha.rstrip("\n").split("\t")
            if len(partes) < 2:
                continue
            nome = nomes.get(partes[1], (partes[1].strip("<@!>"), ""))[0]
            todos[nome] = True
            if len(partes) >= 5 and set(partes[4].split(",")) & set(anims):
                usadas[nome] = True
    return list(usadas or todos)


def preparar(raiz, p, anim_pmd, local, fator):
    """Recorta e redimensiona uma animação; devolve a folha pronta (matriz de cores, uma faixa
    por direção) e os dados dela para o JSON."""
    largura_q, altura_q, duracoes, impacto = ler_animacao(local["AnimData.xml"], anim_pmd)
    folha = tk.PhotoImage(master=raiz, file=local[f"{anim_pmd}-Anim.png"])
    colunas, linhas = folha.width() // largura_q, folha.height() // altura_q
    assert colunas == len(duracoes) and linhas == len(DIRECOES), (p.arquivo, anim_pmd, colunas, linhas)
    px = pixels(raiz, folha)
    if anim_pmd == "Walk":  # andar: a mesma caixa nas 8 direções (é a que anda e colide)
        caixas = [recorte(px, largura_q, altura_q, colunas, range(linhas))] * linhas
    else:
        caixas = [recorte(px, largura_q, altura_q, colunas, [linha]) for linha in range(linhas)]
    faixas, info = [], []
    for linha, (x0, y0, x1, y1) in enumerate(caixas):
        quadros = []
        for coluna in range(colunas):
            ox, oy = coluna * largura_q + x0, linha * altura_q + y0
            quadros.append(redimensionar([px[oy + y][ox:ox + x1 - x0] for y in range(y1 - y0)], fator))
        largura, altura = len(quadros[0][0]), len(quadros[0])
        faixas.append(quadros)
        # tamanho do quadro e onde o canto dele fica em relação ao centro do quadro original (o
        # mesmo ponto do corpo em todas as animações), já no tamanho da tela
        info.append([largura, altura, round((x0 - largura_q / 2) * fator), round((y0 - altura_q / 2) * fator)])
    largura_folha = max(largura * colunas for largura, _altura, _dx, _dy in info)
    matriz = [[None] * largura_folha for _ in range(sum(altura for _largura, altura, _dx, _dy in info))]
    topo = 0
    for (largura, altura, _dx, _dy), quadros in zip(info, faixas):
        for coluna, quadro in enumerate(quadros):
            for y in range(altura):
                matriz[topo + y][coluna * largura:(coluna + 1) * largura] = quadro[y]
        topo += altura
    return matriz, {"duracoes": [round(d * MS_POR_TICK) for d in duracoes], "linhas": info,
                    **({"impacto": impacto} if impacto is not None else {})}


def main():
    cache = sys.argv[1] if len(sys.argv) > 1 else os.path.join(tempfile.gettempdir(), "megaqg_pmd")
    os.makedirs(cache, exist_ok=True)
    destino = pasta()
    os.makedirs(destino, exist_ok=True)
    baixar(f"{FONTE}/credit_names.txt", os.path.join(cache, "credit_names.txt"))
    nomes = nomes_dos_creditos(cache)
    raiz = tk.Tk()
    raiz.withdraw()
    dados, linhas_creditos, gerados = OrderedDict(), [], set()
    for p in POKEMON:
        arquivos = ["AnimData.xml", "credits.txt"] + [f"{a}-Anim.png" for a in ANIMACOES.values()]
        local = {f: os.path.join(cache, f"{p.arquivo}__{f}") for f in arquivos}
        for f, caminho in local.items():
            baixar(f"{FONTE}/sprite/{p.numero:04d}/{f}", caminho)
        # o tamanho na tela sai da altura dele andando e vale para todas as animações dele
        largura_q, altura_q, duracoes, _ = ler_animacao(local["AnimData.xml"], "Walk")
        andar = tk.PhotoImage(master=raiz, file=local["Walk-Anim.png"])
        _x0, y0, _x1, y1 = recorte(pixels(raiz, andar), largura_q, altura_q, len(duracoes), range(len(DIRECOES)))
        fator = tamanho_na_tela(y1 - y0) / (y1 - y0)
        dados[p.arquivo] = OrderedDict()
        for nossa, do_pmd in ANIMACOES.items():
            matriz, info = preparar(raiz, p, do_pmd, local, fator)
            nome_png = f"{p.arquivo}-{nossa}.png"
            gravar_png(os.path.join(destino, nome_png), matriz)
            gerados.add(nome_png)
            dados[p.arquivo][nossa] = info
        autores = creditos(local["credits.txt"], nomes, ANIMACOES.values())
        linhas_creditos.append(f"| {p.nome} | #{p.numero:04d} | {', '.join(autores)} | "
                               f"[página do sprite]({PAGINA.format(numero=p.numero)}) |")
        largura, altura = dados[p.arquivo]["andar"]["linhas"][0][:2]
        print(f"{p.arquivo:11} {largura:3}x{altura:<3} (x{fator:.2f})")
    raiz.destroy()

    for velho in glob.glob(os.path.join(destino, "*.png")):  # sobras de versões anteriores
        if os.path.basename(velho) not in gerados:
            os.remove(velho)
    if os.path.exists(os.path.join(destino, "andar.json")):
        os.remove(os.path.join(destino, "andar.json"))
    with open(os.path.join(destino, "animacoes.json"), "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    with open(os.path.join(destino, "CREDITOS.md"), "w", encoding="utf-8") as f:
        f.write(CABECALHO_CREDITOS + "\n".join(linhas_creditos) + "\n")
    print(f"{len(dados)} Pokémon em {destino}")


CABECALHO_CREDITOS = """# Créditos dos sprites de Pokémon

As animações em `assets/pokemon/*.png` (andar, golpe e pulo) vêm do **PMD SpriteCollab**
(https://github.com/PMDCollab/SpriteCollab), a coleção de sprites no estilo de Pokémon Mystery
Dungeon mantida pela comunidade, sob a licença **Creative Commons Atribuição-NãoComercial 4.0**
(CC BY-NC 4.0, https://creativecommons.org/licenses/by-nc/4.0/). "CHUNSOFT" indica os sprites
originais dos jogos Pokémon Mystery Dungeon.

Alterações feitas aqui (tools/preparar_pokemon.py): só as animações de andar (Walk), golpe
(Attack) e pulo (Hop); quadros recortados no menor retângulo que contém o Pokémon; tamanho
ajustado (os pequenos ampliados, os grandes reduzidos).

Pokémon e os nomes dos Pokémon são marcas de Nintendo, Creatures Inc. e GAME FREAK inc. Os
sprites são usados apenas como decoração desta ferramenta interna, sem fins comerciais.

| Pokémon | Pokédex | Autores das animações | Fonte |
|---|---|---|---|
"""

if __name__ == "__main__":
    main()
