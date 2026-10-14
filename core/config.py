"""
Configuração única do MegaQG Vivo: endpoints, credenciais e pastas.

Nenhuma URL, host ou senha fica no código. Cada valor é procurado nesta ordem
(o primeiro que existir vale):

  1. variável de ambiente MEGAQG_<CHAVE EM MAIÚSCULAS> (ex.: MEGAQG_DOWNLOAD_URL_PRD);
  2. config.json ao lado do .exe (compilado) ou na raiz do repositório (rodando como .py)
     -> permite trocar endpoint/senha no servidor sem recompilar;
  3. config.json embutido dentro do .exe (o build empacota o config.json local)
     -> o exe roda sozinho no servidor on-premise.

O formato é o mesmo do config.json dos QGs NFCom/NFSe originais (veja
config.example.json), então um config.json de produção existente continua valendo.
"""
import json
import os
import sys

NOME_ARQUIVO = "config.json"

# Pasta de logs FIXA de todas as operações (padrão dos scripts da equipe; não é configurável)
LOG_DIR = r"C:\ScriptPS\logs"

AMBIENTE_PRD = "Produção"
AMBIENTE_HML = "Homologação"


def pasta_base() -> str:
    """Pasta onde o app "mora": ao lado do .exe (compilado) ou raiz do repositório."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def caminho_arquivo() -> str:
    return os.path.join(pasta_base(), NOME_ARQUIVO)


def caminhos_candidatos() -> list[str]:
    """config.json externo primeiro (sobrescreve), depois o embutido no exe."""
    caminhos = [caminho_arquivo()]
    pasta_embutida = getattr(sys, "_MEIPASS", None)
    if pasta_embutida:
        caminhos.append(os.path.join(pasta_embutida, NOME_ARQUIVO))
    return caminhos


def _ler_json(caminho: str) -> dict:
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, dict) else {}
    except Exception as e:
        # Não trava o app por um config.json malformado, mas deixa registrado:
        # sem isso, um JSON com erro de sintaxe parece "não configurado".
        ERROS_LEITURA.append(f"Não foi possível ler {caminho}: {e}")
        return {}


ERROS_LEITURA: list[str] = []
_dados: dict = {}
_origem: str = "nenhuma"


def recarregar() -> None:
    """(Re)lê o config.json. Chamado no import e pela tela de configurações."""
    global _dados, _origem
    ERROS_LEITURA.clear()
    _dados, _origem = {}, "nenhuma"
    for caminho in caminhos_candidatos():
        if os.path.exists(caminho):
            _dados = _ler_json(caminho)
            _origem = "embutido no executável" if caminho != caminho_arquivo() else caminho
            break


def origem() -> str:
    """De onde a configuração veio (para log/tela, nunca mostra valores)."""
    return _origem


def obter(chave: str, variavel_ambiente: str | None = None, default: str = "") -> str:
    """Valor de uma chave. Mesma assinatura do _endpoint() dos QGs originais."""
    variavel_ambiente = variavel_ambiente or f"MEGAQG_{chave.upper()}"
    valor = os.environ.get(variavel_ambiente)
    if valor:
        return valor
    valor = _dados.get(chave, default)
    return valor if isinstance(valor, str) else str(valor)


def url_por_ambiente(chave_base: str, ambiente: str) -> str:
    """Ex.: url_por_ambiente("download_url", "Produção") -> obter("download_url_prd")."""
    sufixo = "prd" if ambiente == AMBIENTE_PRD else "hml"
    return obter(f"{chave_base}_{sufixo}")


def faltando(chaves: list[str]) -> list[str]:
    """Quais chaves obrigatórias estão vazias (para o hub mostrar o que falta)."""
    return [c for c in chaves if not obter(c)]


def log_dir() -> str:
    """Pasta de logs: sempre LOG_DIR (fixa, igual em todas as máquinas)."""
    return LOG_DIR


def pasta_saida_padrao() -> str:
    return obter("pasta_saida_padrao") or os.path.join(os.path.expanduser("~"), "Desktop", "Vivo NFCom")


recarregar()
