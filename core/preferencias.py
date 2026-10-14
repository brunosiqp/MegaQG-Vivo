"""
Preferências de aparência de cada usuário (tema escolhido, temas criados, barra lateral
recolhida). Ficam em %APPDATA%\\MegaQGVivo\\preferencias.json, fora do config.json: o config
tem endpoints e senhas e é igual para todos; a aparência é de cada pessoa.

Se o arquivo não puder ser lido ou gravado, o app segue com o padrão (nada trava por isso).
A variável MEGAQG_PREFERENCIAS aponta outro arquivo (usada nos testes).
"""
import json
import os


def caminho() -> str:
    indicado = os.environ.get("MEGAQG_PREFERENCIAS")
    if indicado:
        return indicado
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "MegaQGVivo", "preferencias.json")


def carregar() -> dict:
    try:
        with open(caminho(), encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, dict) else {}
    except Exception:
        return {}


def salvar(dados: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(caminho()), exist_ok=True)
        with open(caminho(), "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def obter(chave: str, default=None):
    return carregar().get(chave, default)


def definir(chave: str, valor) -> bool:
    dados = carregar()
    dados[chave] = valor
    return salvar(dados)
