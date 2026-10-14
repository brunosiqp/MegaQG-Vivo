"""
Parâmetros do Exportador de Relatório (Vivo). Servidor, base, usuário, senha e
URLs de XML NÃO ficam aqui: vêm do config.json (core.config), chaves
relatorio_db_* e download_url_prd/_hml.
"""
from core import config


class ConfigIncompleta(Exception):
    pass


def db_config() -> dict:
    """Configuração de conexão para core.database.sql_conn, lida do config.json.
    Levanta ConfigIncompleta dizendo exatamente quais chaves faltam."""
    auth_type = config.obter("relatorio_db_auth_type", default="sql") or "sql"
    obrigatorias = ["relatorio_db_server", "relatorio_db_database"]
    if auth_type != "windows":
        obrigatorias += ["relatorio_db_user", "relatorio_db_password"]
    faltando = config.faltando(obrigatorias)
    if faltando:
        raise ConfigIncompleta(
            f"Configuração do banco incompleta em {config.caminho_arquivo()}: preencha {', '.join(faltando)}."
        )
    return {
        "server": config.obter("relatorio_db_server"),
        "database": config.obter("relatorio_db_database"),
        "user": config.obter("relatorio_db_user"),
        "password": config.obter("relatorio_db_password"),
        "auth_type": auth_type,
        "trust_cert": config.obter("relatorio_db_trust_cert", default="yes").lower() in ("yes", "true", "1", "sim"),
    }


def url_xml(ambiente: str) -> str:
    """URL da API de download de XML (mesmo endpoint do Download de XMLs NFCom)."""
    return config.url_por_ambiente("download_url", ambiente)


# Status considerados no relatório (mesmos do SELECT manual: 6, 9, 10)
STATUS_FILTRO = (6, 9, 10)

# Status usado na opção "Somente canceladas" (IND_STATUS = 9 na documento_fiscal)
STATUS_CANCELADAS = (9,)

# Filtros de status disponíveis: chave -> (status, prefixo do arquivo gerado).
# O prefixo evita que o relatório de canceladas sobrescreva o completo.
FILTROS_STATUS = {
    "todas": (STATUS_FILTRO, ""),
    "canceladas": (STATUS_CANCELADAS, "canceladas_"),
}

# Coluna do relatório que contém o ID usado na API de download (é o mesmo
# "ID" retornado pela query SQL, renomeado para "ID Mensageria")
COLUNA_ID_XML = "ID Mensageria"

# Threads simultâneas para baixar XML
MAX_WORKERS_XML = 8

# Quantidade de linhas processadas por vez (streaming). Cada bloco é lido
# do banco, tem o XML baixado e é gravado no CSV antes do próximo começar -
# controla o uso de memória em dias com milhões de notas.
CHUNK_SIZE_PROCESSAMENTO = 50_000
