"""
Banco do NFCom (tabela documento_fiscal), por ambiente, para core.database.sql_conn.

Mantido à mão: fica fora de modulos/nfcom/comum.py, que é gerado de novo pelo porte automático
(tools/portar_qgs.py).

Produção: chaves nfcom_db_server_prd / nfcom_db_database_prd; vazias, valem as do Exportador de
Relatório (relatorio_db_*), que já apontam para o banco do NFCom de produção. Homologação:
nfcom_db_server_hml / nfcom_db_database_hml. Usuário, senha, tipo de autenticação e certificado:
nfcom_db_* ou, vazias, relatorio_db_*.
"""
from core import config


class ConfigBancoNfcomIncompleta(Exception):
    pass


def db_config_nfcom(ambiente: str) -> dict:
    """Configuração de conexão do banco do NFCom no ambiente dado. Levanta
    ConfigBancoNfcomIncompleta dizendo quais chaves faltam."""
    producao = ambiente == config.AMBIENTE_PRD
    sufixo = "prd" if producao else "hml"

    def valor(chave, reserva=None):
        return config.obter(chave) or (config.obter(reserva) if reserva else "") or ""

    server = valor(f"nfcom_db_server_{sufixo}", "relatorio_db_server" if producao else None)
    database = valor(f"nfcom_db_database_{sufixo}", "relatorio_db_database" if producao else None)
    user = valor("nfcom_db_user", "relatorio_db_user")
    password = valor("nfcom_db_password", "relatorio_db_password")
    auth_type = valor("nfcom_db_auth_type", "relatorio_db_auth_type") or "sql"
    faltando = [nome for nome, v in ((f"nfcom_db_server_{sufixo}", server), (f"nfcom_db_database_{sufixo}", database))
                if not v]
    if auth_type != "windows":
        faltando += [nome for nome, v in (("nfcom_db_user", user), ("nfcom_db_password", password)) if not v]
    if faltando:
        raise ConfigBancoNfcomIncompleta(
            f"Banco do NFCom ({ambiente}) não configurado em {config.caminho_arquivo()}: "
            f"preencha {', '.join(faltando)}.")
    return {
        "server": server,
        "database": database,
        "user": user,
        "password": password,
        "auth_type": auth_type,
        "trust_cert": (valor("nfcom_db_trust_cert", "relatorio_db_trust_cert") or "yes").lower()
        in ("yes", "true", "1", "sim"),
    }
