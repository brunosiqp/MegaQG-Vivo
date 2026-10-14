import pyodbc
import logging
from core.utils import verificar_conexao


def sql_conn(config: dict) -> pyodbc.Connection:
    """
    =====================================================================
    Descrição:
    Estabelece uma conexão com o banco de dados SQL Server usando o
    driver ODBC 17. Genérica: recebe as credenciais via dicionário,
    então serve para qualquer cliente (Shein, Vivo, etc.), bastando
    trocar o config.
    =====================================================================
    Parâmetros:
    - config: dict no formato:
        {
            "server": r"<servidor>\\<instancia>",
            "database": "<base>",
            "user": "<usuario>",
            "password": "...",
            "port": 1433,              # opcional, default 1433
            "trust_cert": True,        # opcional, default True
        }
    =====================================================================
    Retorno:
    - conn: objeto de conexão com o banco de dados.
    =====================================================================
    Exceções:
    - pyodbc.Error: se ocorrer um erro na conexão (relançada após log).
    =====================================================================
    Exemplo de uso:
    conn = sql_conn(DB_CONFIG)
    =====================================================================
    """

    port = config.get("port")
    trust_cert = "yes" if config.get("trust_cert", True) else "no"
    auth_type = config.get("auth_type", "sql")  # "sql" ou "windows"

    # Se o server tem instância nomeada (contém \) e nenhuma porta foi
    # forçada explicitamente, NÃO anexa porta — deixa o driver resolver
    # via SQL Browser (mesmo comportamento usado no Shein). Forçar uma
    # porta fixa junto com instância nomeada pode apontar pro listener
    # errado e gerar falha de login (18456) mesmo com senha correta.
    instancia_nomeada = "\\" in config["server"]
    if port and not instancia_nomeada:
        server_str = f"{config['server']},{port}"
    elif port and config.get("forcar_porta"):
        server_str = f"{config['server']},{port}"
    else:
        server_str = config["server"]

    if auth_type == "windows":
        # Autenticação Windows/domínio (usa o usuário logado na máquina,
        # não usa user/password do config).
        conn_str = (
            "DRIVER={ODBC Driver 17 for SQL Server};"
            f"SERVER={server_str};"
            f"DATABASE={config['database']};"
            "Trusted_Connection=yes;"
            f"TrustServerCertificate={trust_cert};"
        )
    else:
        conn_str = (
            "DRIVER={ODBC Driver 17 for SQL Server};"
            f"SERVER={server_str};"
            f"DATABASE={config['database']};"
            f"UID={config['user']};"
            f"PWD={config['password']};"
            f"TrustServerCertificate={trust_cert};"
        )

    try:
        conn = pyodbc.connect(conn_str)
        logging.info(f"Conexão com banco de dados '{config['database']}' estabelecida.")
        return conn
    except Exception as e:
        erro_str = str(e)

        if not verificar_conexao():
            logging.error(f"Erro ao conectar com o banco de dados por falha na internet: ({e})")
        elif "18456" in erro_str:
            logging.error(
                f"Falha de autenticação (18456) para o usuário/modo '{auth_type}'. "
                "Possíveis causas: senha incorreta/expirada, conta bloqueada, ou essa "
                "conta exige autenticação Windows em vez de SQL Login (tente trocar "
                "\"auth_type\": \"sql\" para \"auth_type\": \"windows\" em config.py). "
                f"Detalhe: {e}"
            )
        elif "08001" in erro_str or "timeout" in erro_str.lower():
            logging.error(
                f"Não foi possível alcançar o servidor '{config['server']}'. "
                f"Confira se está na VPN/rede correta e se o servidor/porta estão certos. Detalhe: {e}"
            )
        else:
            logging.error(f"Erro ao conectar com o banco de dados: ({e})")
        raise
