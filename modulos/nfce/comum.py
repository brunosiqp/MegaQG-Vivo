"""
Configuração e constantes da área NFCe (banco de NFCe, separado do de NFCom).

Chaves do config.json (servidor e base por ambiente; usuário e senha comuns):
  nfce_db_server_prd, nfce_db_database_prd, nfce_db_server_hml, nfce_db_database_hml,
  nfce_db_user, nfce_db_password, nfce_db_auth_type ("sql" | "windows"), nfce_db_trust_cert
Download de XMLs (não usa o banco): nfce_download_url_prd, nfce_download_url_hml
Reprocessamento (banco + download + envio): nfce_reprocessamento_url_prd, nfce_reprocessamento_url_hml
"""
from core import config

TAMANHO_CHAVE = 44

# Tabela temporária com as chaves (A_ID) de um arquivo ou de um bloco, para o JOIN com INTERF_NFE
SQL_CRIAR_TEMP = "IF OBJECT_ID('tempdb..{t}') IS NOT NULL DROP TABLE {t}; CREATE TABLE {t} (A_ID VARCHAR(60) COLLATE DATABASE_DEFAULT NOT NULL PRIMARY KEY);"
SQL_CARREGAR_TEMP = "INSERT INTO {t} (A_ID) VALUES (?)"


class ConfigNfceIncompleta(Exception):
    pass


def carregar_temp(cursor, tabela, chaves):
    """(Re)cria a tabela temporária e carrega as chaves nela."""
    cursor.execute(SQL_CRIAR_TEMP.format(t=tabela))
    if chaves:
        try:
            cursor.fast_executemany = True
        except AttributeError:
            pass
        cursor.executemany(SQL_CARREGAR_TEMP.format(t=tabela), [(c,) for c in chaves])


def ler_chaves(arquivo: str) -> dict:
    """Lê o .txt (UTF-8 com/sem BOM ou Windows-1252) e separa válidas, inválidas e duplicadas.
    Chave válida = 44 dígitos (chave de acesso da NFCe, A_ID)."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            with open(arquivo, encoding=encoding) as f:
                linhas = f.read().splitlines()
            break
        except UnicodeDecodeError:
            continue
    validas, invalidas, vistas, duplicadas = [], [], set(), 0
    for linha in linhas:
        chave = linha.strip().replace(" ", "")
        if not chave:
            continue
        if len(chave) != TAMANHO_CHAVE or not chave.isdigit():
            invalidas.append(chave)
        elif chave in vistas:
            duplicadas += 1
        else:
            vistas.add(chave)
            validas.append(chave)
    return {"validas": validas, "invalidas": invalidas, "duplicadas": duplicadas, "lidas": len(linhas)}


def db_config_nfce(ambiente: str) -> dict:
    """Configuração de conexão do banco de NFCe para core.database.sql_conn."""
    sufixo = "prd" if ambiente == config.AMBIENTE_PRD else "hml"
    auth_type = config.obter("nfce_db_auth_type", default="sql") or "sql"
    obrigatorias = [f"nfce_db_server_{sufixo}", f"nfce_db_database_{sufixo}"]
    if auth_type != "windows":
        obrigatorias += ["nfce_db_user", "nfce_db_password"]
    faltando = config.faltando(obrigatorias)
    if faltando:
        raise ConfigNfceIncompleta(
            f"Banco de NFCe ({ambiente}) não configurado em {config.caminho_arquivo()}: "
            f"preencha {', '.join(faltando)}."
        )
    return {
        "server": config.obter(f"nfce_db_server_{sufixo}"),
        "database": config.obter(f"nfce_db_database_{sufixo}"),
        "user": config.obter("nfce_db_user"),
        "password": config.obter("nfce_db_password"),
        "auth_type": auth_type,
        "trust_cert": config.obter("nfce_db_trust_cert", default="yes").lower() in ("yes", "true", "1", "sim"),
    }
