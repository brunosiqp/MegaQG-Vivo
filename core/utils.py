import socket


def verificar_conexao(host: str = "8.8.8.8", port: int = 53, timeout: float = 3) -> bool:
    """
    =====================================================================
    Descrição:
    Verifica se há conexão com a internet, tentando abrir um socket
    para um DNS público (Google, por padrão).
    =====================================================================
    Retorno:
    - True se houver conexão, False caso contrário.
    =====================================================================
    """
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except OSError:
        return False
