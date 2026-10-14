"""
Temas do MegaQG Vivo: os prontos, os criados pelo usuário e a troca do tema ativo.

Um tema é uma paleta com as 17 cores de CHAVES. As cores "suaves" (fundos de seleção e de
aviso) são calculadas a partir delas em completar(), então quem cria um tema só escolhe as
cores principais. Os temas do usuário ficam nas preferências (core/preferencias.py).
"""
import re
import unicodedata

from core import preferencias
from ui.theme import COLORS, misturar

# (chave em COLORS, nome mostrado no editor, grupo)
CHAVES = [
    ("bg", "Fundo da janela", "Base"),
    ("panel", "Painéis e barras", "Base"),
    ("card", "Cartões e campos", "Base"),
    ("card_border", "Linhas e bordas", "Base"),
    ("fg", "Texto", "Base"),
    ("fg_muted", "Texto secundário", "Base"),
    ("accent", "Destaque", "Destaque e avisos"),
    ("success", "Sucesso", "Destaque e avisos"),
    ("warning", "Aviso", "Destaque e avisos"),
    ("danger", "Erro / perigo", "Destaque e avisos"),
    ("prd", "Ambiente Produção", "Destaque e avisos"),
    ("hml", "Ambiente Homologação", "Destaque e avisos"),
    ("purple", "Roxo", "Cores das operações"),
    ("teal", "Verde-água", "Cores das operações"),
    ("cyan", "Ciano", "Cores das operações"),
    ("indigo", "Índigo", "Cores das operações"),
    ("blue", "Azul", "Cores das operações"),
]
NOMES_CHAVES = [chave for chave, _nome, _grupo in CHAVES]
PADRAO = "nebulosa"


def _paleta(bg, panel, card, card_border, fg, fg_muted, accent, success, warning, danger, prd, hml,
            purple, teal, cyan, indigo, blue) -> dict:
    return dict(zip(NOMES_CHAVES, (bg, panel, card, card_border, fg, fg_muted, accent, success, warning,
                                   danger, prd, hml, purple, teal, cyan, indigo, blue)))


PRONTOS = {
    "nebulosa": {"nome": "Nebulosa", "descricao": "Azul-noite profundo com destaque elétrico (padrão)",
                 "cores": _paleta("#07090e", "#0c1018", "#121824", "#1f2838", "#e7ecf5", "#7d889d",
                                  "#4da3ff", "#3ddc84", "#f7b13c", "#ff5468", "#ff6b78", "#f5b444",
                                  "#a678ff", "#2ddcc3", "#30d5f2", "#8a93ff", "#4b8dff")},
    "neon": {"nome": "Neon", "descricao": "Preto absoluto com ciano e magenta",
             "cores": _paleta("#030305", "#08080d", "#0e0e16", "#20202e", "#f3f3fa", "#8686a0",
                              "#00e5ff", "#39ff88", "#ffd23f", "#ff3d6e", "#ff4d7a", "#ffd23f",
                              "#d05bff", "#00f5c4", "#5ce1ff", "#7c83ff", "#3d9bff")},
    "aurora": {"nome": "Aurora", "descricao": "Verde-petróleo com destaque esmeralda",
               "cores": _paleta("#061012", "#0a181b", "#0f2125", "#1b363b", "#e4f2ef", "#7a9a98",
                                "#2ee6a6", "#5be37d", "#f2c14e", "#ff6b6b", "#ff7a7a", "#f2c14e",
                                "#b08cff", "#34e0d0", "#4fd8f0", "#8fa0ff", "#55a2ff")},
    "violeta": {"nome": "Violeta", "descricao": "Roxo escuro, na cor da marca",
                "cores": _paleta("#0b0812", "#120d1c", "#191227", "#2c2044", "#efe9fb", "#9488ad",
                                 "#b57bff", "#47d98a", "#f5b03e", "#ff5a7a", "#ff6b88", "#f5b85a",
                                 "#d18cff", "#3dd9c1", "#5ccdf5", "#9a8cff", "#6f9bff")},
    "grafite": {"nome": "Grafite", "descricao": "Cinza neutro e monocromático, cores discretas",
                "cores": _paleta("#0c0c0d", "#131314", "#1a1a1c", "#2b2b2f", "#ececee", "#8b8b93",
                                 "#e2e2e8", "#7fd39a", "#e3b667", "#ef7a85", "#ef7a85", "#e3b667",
                                 "#a99bd6", "#6fcfc0", "#7cc7dd", "#9aa3e0", "#7fa8e6")},
    "classico": {"nome": "Clássico", "descricao": "O visual das versões até a v3.3",
                 "cores": _paleta("#0d0f14", "#151822", "#1b1f2b", "#2a3040", "#e8eaf2", "#8890a6",
                                  "#5b8cff", "#33d17a", "#f5a623", "#ff4d5e", "#ff6b78", "#f5b444",
                                  "#a56bff", "#2dd4bf", "#22d3ee", "#818cf8", "#3b82f6")},
    "claro": {"nome": "Claro", "descricao": "Fundo claro, para ambientes bem iluminados",
              "cores": _paleta("#f3f5f9", "#ffffff", "#edf0f5", "#d3d9e4", "#131722", "#5d687c",
                               "#2563eb", "#15803d", "#b45309", "#dc2626", "#dc2626", "#b45309",
                               "#7c3aed", "#0d9488", "#0e7490", "#4f46e5", "#1d4ed8")},
}

_ativo = PADRAO


def validar_cor(texto) -> str | None:
    """Cor no formato #1a2b3c a partir do que o usuário digitou ("1A2B3C", "#1a2b3c", "#abc");
    None se não for uma cor."""
    texto = str(texto or "").strip().lstrip("#").lower()
    if re.fullmatch(r"[0-9a-f]{3}", texto):
        texto = "".join(letra * 2 for letra in texto)
    return f"#{texto}" if re.fullmatch(r"[0-9a-f]{6}", texto) else None


def completar(cores: dict) -> dict:
    """Paleta inteira de COLORS: as 17 cores escolhidas mais os fundos suaves calculados."""
    base = PRONTOS[PADRAO]["cores"]
    p = {chave: validar_cor(cores.get(chave)) or base[chave] for chave in NOMES_CHAVES}
    p["accent_soft"] = misturar(p["accent"], p["bg"], 0.26)
    p["danger_soft"] = misturar(p["danger"], p["bg"], 0.18)
    p["cyan_soft"] = misturar(p["cyan"], p["bg"], 0.20)
    p["prd_soft"] = misturar(p["prd"], p["bg"], 0.15)
    p["hml_soft"] = misturar(p["hml"], p["bg"], 0.15)
    return p


def personalizados() -> dict:
    """Temas criados pelo usuário: id -> {"nome", "cores"} (só os que estão bem formados)."""
    salvos = preferencias.obter("temas", {})
    if not isinstance(salvos, dict):
        return {}
    return {tema_id: {"nome": str(tema.get("nome") or tema_id), "descricao": "Tema criado por você",
                      "cores": tema["cores"], "personalizado": True}
            for tema_id, tema in salvos.items()
            if isinstance(tema, dict) and isinstance(tema.get("cores"), dict) and tema_id not in PRONTOS}


def todos() -> dict:
    """Prontos primeiro, depois os do usuário."""
    return {**PRONTOS, **personalizados()}


def ativo() -> str:
    return _ativo


def ativar(tema_id=None, salvar=True) -> str:
    """Troca os valores de COLORS pelo tema pedido (ou o padrão, se ele não existir) e
    devolve o id que ficou ativo. Quem chama reaplica os estilos e redesenha as telas."""
    global _ativo
    temas = todos()
    if tema_id not in temas:
        tema_id = PADRAO
    COLORS.update(completar(temas[tema_id]["cores"]))
    _ativo = tema_id
    if salvar:
        preferencias.definir("tema", tema_id)
    return tema_id


def _novo_id(nome: str, existentes) -> str:
    texto = unicodedata.normalize("NFKD", nome.lower())
    base = "meu-" + (re.sub(r"[^a-z0-9]+", "-", "".join(c for c in texto if not unicodedata.combining(c)))
                     .strip("-") or "tema")
    tema_id, n = base, 2
    while tema_id in existentes:
        tema_id, n = f"{base}-{n}", n + 1
    return tema_id


def salvar_personalizado(nome: str, cores: dict, tema_id=None) -> str:
    """Grava (ou atualiza, se tema_id for de um tema do usuário) e devolve o id do tema."""
    nome = " ".join(str(nome).split()) or "Meu tema"
    salvos = preferencias.obter("temas", {})
    if not isinstance(salvos, dict):
        salvos = {}
    if tema_id not in salvos:
        tema_id = _novo_id(nome, set(salvos) | set(PRONTOS))
    paleta = completar(cores)
    salvos[tema_id] = {"nome": nome, "cores": {chave: paleta[chave] for chave in NOMES_CHAVES}}
    preferencias.definir("temas", salvos)
    return tema_id


def excluir_personalizado(tema_id: str) -> bool:
    salvos = preferencias.obter("temas", {})
    if not isinstance(salvos, dict) or tema_id not in salvos:
        return False
    del salvos[tema_id]
    preferencias.definir("temas", salvos)
    return True
