"""
Porta as operações dos QGs originais (legado/) para modulos/nfcom e modulos/nfse.

Cada engine/página é extraída do qg.py original pela árvore de sintaxe (ast),
exatamente como está, e recebe só ajustes mecânicos:
  - imports da base comum (core.config, ui.theme, ui.widgets);
  - ambiente PRD/HML global do MegaQG Vivo (controller.ambiente_var);
  - NFSe: URLs fixas no código passam a vir do config.json, com PRD e HML;
  - NFSe: cor de destaque ciano preservada (estilos Cyan.*).

Uso (na raiz do repositório): python tools/portar_qgs.py
Requer legado/NFCom preview/qg.py e legado/NFSe/qg.py (cópias locais, fora do git).
"""
import ast
import os
import re
import textwrap

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGEM_NFCOM = os.path.join(RAIZ, "legado", "NFCom preview", "qg.py")
ORIGEM_NFSE = os.path.join(RAIZ, "legado", "NFSe", "qg.py")

NFCOM_OPERACOES = {
    "cancelamento": (["CancelamentoMassivoEngine"], ["CancelamentoPage"]),
    "download_xmls": (["DownloadXmlsEngine"], ["DownloadXmlsPage"]),
    "reenvio_webhook": (["WebhookResendEngine"], ["ReenvioWebhookPage"]),
}
# reenvio_sefaz saiu do porte automático na v3.3: modulos/nfcom/reenvio_sefaz ganhou o reenvio
# por ID dos XMLs sem chave e passou a ser mantido à mão. Portar de novo apagaria essa mudança.
# consulta_sefaz saiu na v3.8: as chaves que voltam HTTP 422 são reenviadas pelo ID (buscado na
# documento_fiscal). Também é mantida à mão; portar de novo apagaria essa mudança.
NFSE_OPERACOES = {
    "download_xmls": (["DownloadXmlsEngine", "DownloadComSemCepEngine"], ["DownloadXmlsPage"]),
    "expandir_csv": (["ExpandirDpsCsvEngine"], ["ExpandirDpsCsvPage"]),
    "reenvio_xml": (["ReenvioXmlEngine"], ["ReenvioXmlPage"]),
    "consulta_dps": (["ConsultaDpsEngine"], ["ConsultaDpsPage"]),
}
# relatorio_dps saiu do porte automático na v3.6: a planilha passou a ter uma linha por DPS, as
# abas "DPS sem endereço" / "Dados de endereço" e o nome com a data do dia.
# Portar de novo apagaria essa mudança.
# NFSe: engine -> (atributo de classe que tinha a URL fixa, chave do config.json sem _prd/_hml)
NFSE_URL_POR_ENGINE = {
    "DownloadXmlsEngine": ("BASE_URL_DOWNLOAD", "nfse_download_url"),
    "DownloadComSemCepEngine": ("BASE_URL_DOWNLOAD", "nfse_download_url"),
    "ReenvioXmlEngine": ("BASE_URL", "nfse_reenvio_url"),
    "ConsultaDpsEngine": ("BASE_URL", "nfse_consulta_dps_url"),
}


class Fonte:
    def __init__(self, caminho):
        self.texto = open(caminho, encoding="utf-8").read()
        self.linhas = self.texto.splitlines()
        self.arvore = ast.parse(self.texto)

    def no(self, nome):
        for n in self.arvore.body:
            if getattr(n, "name", None) == nome:
                return n
            if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == nome for t in n.targets):
                return n
        raise KeyError(nome)

    def trecho(self, nome):
        n = self.no(nome)
        inicio = n.lineno
        # inclui decorators, se houver
        if getattr(n, "decorator_list", None):
            inicio = min(d.lineno for d in n.decorator_list)
        return "\n".join(self.linhas[inicio - 1:n.end_lineno])

    def entre(self, primeiro, ultimo):
        """Todos os nós de primeiro a ultimo (inclusive), com o que houver entre eles."""
        a, b = self.no(primeiro), self.no(ultimo)
        return "\n".join(self.linhas[a.lineno - 1:b.end_lineno])


def escrever(rel, conteudo):
    caminho = os.path.join(RAIZ, rel)
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="\n") as f:
        f.write(conteudo.rstrip() + "\n")


def garantir_init(rel_pasta):
    caminho = os.path.join(RAIZ, rel_pasta, "__init__.py")
    if not os.path.exists(caminho):
        escrever(os.path.join(rel_pasta, "__init__.py"), "")


IMPORTS_ENGINE = """\
import base64
import calendar
import csv
import json
import os
import queue
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests
import urllib3

from core import config
from core.config import AMBIENTE_PRD, url_por_ambiente
"""

IMPORTS_PAGE = """\
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from core.config import AMBIENTE_HML, AMBIENTE_PRD
from ui.theme import COLORS, escala
from ui.widgets import ScrolledText, _open_folder, back_button, centralizar, stat_box
"""


def ajustar_cancelamento(codigo):
    """Cancelamento (irreversível) usa o ambiente global e mostra o ambiente na confirmação."""
    trocas = [
        ('self.ambiente_var = tk.StringVar(value="Produção (1)")',
         "self.ambiente_var = controller.ambiente_var  # ambiente global do MegaQG Vivo"),
        ('f"{total_chaves} chave(s) NFCom listadas em:',
         'f"{total_chaves} chave(s) NFCom no ambiente de {self.ambiente_var.get().upper()}, listadas em:'),
        ('modal.geometry("520x330")',
         'k = escala(self)\n        centralizar(modal, int(600 * k), int(380 * k))'),
        ("justify=\"left\", wraplength=460)", "justify=\"left\", wraplength=int(540 * k))"),
        # Texto do aviso na cor de texto do tema (o rosa fixo ficava ilegível em tema claro)
        ('bg=COLORS["danger_soft"], fg="#ffd7db"', 'bg=COLORS["danger_soft"], fg=COLORS["fg"]'),
    ]
    for antigo, novo in trocas:
        assert codigo.count(antigo) == 1, antigo
        codigo = codigo.replace(antigo, novo)
    return codigo


def ajustar_pagina(codigo):
    # Ambiente PRD/HML global: todas as telas compartilham a mesma variável
    codigo = re.sub(
        r'self\.ambiente_var = tk\.StringVar\(value="Produção"\)',
        "self.ambiente_var = controller.ambiente_var  # ambiente global do MegaQG Vivo",
        codigo,
    )
    # O seletor de ambiente de cada tela vira um rótulo (o ambiente se troca só no topo do app)
    codigo = re.sub(
        r'ttk\.Combobox\((\w+), textvariable=self\.ambiente_var, state="readonly",(?: width=\d+,)?\s*values=\[[^\]]*\]\)',
        r'ttk.Label(\1, textvariable=self.ambiente_var, style="Ambiente.TLabel")',
        codigo,
    )
    # Pasta de log fixa (C:\ScriptPS\logs): campo só leitura e sem o botão "Alterar..."
    codigo = re.sub(r'\n[ \t]*ttk\.Button\(\w+, text="Alterar\.\.\.", command=self\._browse_log_dir\)\.pack\(.*\)(?=\n)',
                    "", codigo)
    codigo = re.sub(r"ttk\.Entry\((\w+), textvariable=self\.(log_dir_var|log_dir)\)",
                    r'ttk.Entry(\1, textvariable=self.\2, state="readonly")', codigo)
    # Log com barra de rolagem escura (ui.widgets.ScrolledText) no lugar da barra clara do Windows
    codigo = codigo.replace("scrolledtext.ScrolledText(", "ScrolledText(")
    return codigo


def portar_nfcom():
    fonte = Fonte(ORIGEM_NFCOM)
    comum = '"""\nImports e constantes compartilhadas pelas operações NFCom (vindos do topo do\nMEGA QG VIVO NFCom v2.3). Endpoints vêm do config.json via core.config.\n"""\n'
    comum += IMPORTS_ENGINE + "\nurllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)\n\n"
    comum += "_endpoint = config.obter  # mesma assinatura do _endpoint() original\n"
    comum += "DEFAULT_LOG_DIR = config.log_dir()\n\n"
    comum += fonte.entre("NFCOM_NS", "CHECKSEFAZ_URL_HML") + "\n"
    # BASE_LOG_NAME ... GROUP_ORDER (pula DEFAULT_LOG_DIR original, relativo ao script)
    comum += fonte.entre("BASE_LOG_NAME", "GROUP_ORDER") + "\n\n\n"
    comum += fonte.trecho("time_sleep_1") + "\n\n\n"
    comum += "__all__ = [n for n in dir() if not n.startswith(\"__\")]\n"
    escrever("modulos/nfcom/comum.py", comum)
    garantir_init("modulos/nfcom")

    for pasta, (engines, paginas) in NFCOM_OPERACOES.items():
        rel = f"modulos/nfcom/{pasta}"
        garantir_init(rel)
        cab = '"""Engine portada sem alteração de lógica do MEGA QG VIVO NFCom v2.3 (legado/NFCom preview/qg.py)."""\n'
        corpo = "\n\n\n".join(fonte.trecho(e) for e in engines)
        escrever(f"{rel}/engine.py", cab + "from modulos.nfcom.comum import *  # noqa: F401,F403 - imports/constantes do QG original\n\n\n" + corpo)

        cab = '"""Tela portada do MEGA QG VIVO NFCom v2.3 (legado/NFCom preview/qg.py)."""\n'
        corpo = "\n\n\n".join(ajustar_pagina(fonte.trecho(p)) for p in paginas)
        if pasta == "cancelamento":
            corpo = ajustar_cancelamento(corpo)
        escrever(
            f"{rel}/page.py",
            cab + IMPORTS_PAGE
            + "from modulos.nfcom.comum import *  # noqa: F401,F403 - imports/constantes do QG original\n"
            + f"from modulos.nfcom.{pasta}.engine import {', '.join(engines)}\n\n\n" + corpo,
        )


def ajustar_engine_nfse(nome, codigo):
    if nome not in NFSE_URL_POR_ENGINE:
        return codigo
    atributo, chave = NFSE_URL_POR_ENGINE[nome]
    # remove a URL fixa do atributo de classe
    codigo, n = re.subn(rf'\n    {atributo} = "http[^"]*"\n', "\n", codigo)
    assert n == 1, (nome, atributo)
    # __init__ recebe o ambiente e lê a URL do config.json
    codigo, n = re.subn(
        r"def __init__\(self, event_queue, stop_event, \*, ",
        "def __init__(self, event_queue, stop_event, *, ambiente=AMBIENTE_PRD, ",
        codigo,
    )
    assert n == 1, nome
    linhas = codigo.split("\n")
    for i, linha in enumerate(linhas):
        if linha.strip().startswith("def __init__("):
            j = i
            while not linhas[j].rstrip().endswith(":"):
                j += 1
            linhas.insert(j + 1, f'        # MegaQG Vivo: URL vem do config.json ({chave}_prd/_hml), não mais fixa no código\n'
                                 f'        self.{atributo} = url_por_ambiente("{chave}", ambiente)')
            break
    return "\n".join(linhas)


def ajustar_pagina_nfse(codigo):
    codigo = ajustar_pagina(codigo)
    # Engines com URL recebem o ambiente global
    for nome in NFSE_URL_POR_ENGINE:
        codigo = re.sub(
            rf"\b{nome}\(\s*self\.event_queue,\s*self\.stop_event,",
            f"{nome}(\n            self.event_queue, self.stop_event, ambiente=self.controller.ambiente_var.get(),",
            codigo,
        )
    # Cor de assinatura do NFSe (ciano) preservada
    codigo = codigo.replace('COLORS["accent"]', 'COLORS["cyan"]').replace('COLORS["accent_soft"]', 'COLORS["cyan_soft"]')
    codigo = codigo.replace('style="Accent.TButton"', 'style="Cyan.TButton"')
    codigo = re.sub(r"ttk\.Progressbar\(([^()]*)\)",
                    lambda m: m.group(0) if "style=" in m.group(1)
                    else f'ttk.Progressbar({m.group(1)}, style="Cyan.Horizontal.TProgressbar")', codigo)
    return codigo


def portar_nfse():
    fonte = Fonte(ORIGEM_NFSE)
    comum = '"""\nImports compartilhados pelas operações NFSe (vindos do topo do MEGA QG VIVO\nNFSe v2.0). URLs e pasta de log agora vêm do config.json via core.config.\n"""\n'
    comum += IMPORTS_ENGINE + "\n"
    comum += "DEFAULT_LOG_DIR = config.log_dir()  # no original era fixo: C:\\\\ScriptPS\\\\logs\n\n"
    comum += "__all__ = [n for n in dir() if not n.startswith(\"__\")]\n"
    escrever("modulos/nfse/comum.py", comum)
    garantir_init("modulos/nfse")

    for pasta, (engines, paginas) in NFSE_OPERACOES.items():
        rel = f"modulos/nfse/{pasta}"
        garantir_init(rel)
        cab = '"""Engine portada do MEGA QG VIVO NFSe v2.0 (legado/NFSe/qg.py); só a URL passou a vir do config.json."""\n'
        corpo = "\n\n\n".join(ajustar_engine_nfse(e, fonte.trecho(e)) for e in engines)
        escrever(f"{rel}/engine.py", cab + "from modulos.nfse.comum import *  # noqa: F401,F403 - imports do QG original\n\n\n" + corpo)

        cab = '"""Tela portada do MEGA QG VIVO NFSe v2.0 (legado/NFSe/qg.py)."""\n'
        corpo = "\n\n\n".join(ajustar_pagina_nfse(fonte.trecho(p)) for p in paginas)
        escrever(
            f"{rel}/page.py",
            cab + IMPORTS_PAGE
            + "from modulos.nfse.comum import *  # noqa: F401,F403 - imports do QG original\n"
            + f"from modulos.nfse.{pasta}.engine import {', '.join(engines)}\n\n\n" + corpo,
        )


if __name__ == "__main__":
    portar_nfcom()
    portar_nfse()
    print("Operações portadas para modulos/nfcom e modulos/nfse.")
