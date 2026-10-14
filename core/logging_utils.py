import logging
import os
import queue
from datetime import datetime

from colorama import Fore, Style


def _iniciar_colorama_com_seguranca():
    """Inicializa o colorama só quando necessário (console=True), protegido
    contra ambientes onde sys.stdout é None - como um .exe compilado com
    PyInstaller em modo --windowed (sem console anexado), que travaria
    o app inteiro se o colorama fosse inicializado incondicionalmente
    na importação do módulo."""
    try:
        from colorama import init as colorama_init
        colorama_init(autoreset=True)
    except Exception:
        pass  # sem console disponível - segue sem cor, não é crítico


class ColorFormatter(logging.Formatter):
    """Formatter que colore a saída do console conforme o nível do log."""

    CORES = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.RED + Style.BRIGHT,
    }

    def format(self, record):
        cor = self.CORES.get(record.levelno, "")
        mensagem = super().format(record)
        return f"{cor}{mensagem}{Style.RESET_ALL}"


class QueueHandler(logging.Handler):
    """Handler que envia registros de log para uma queue.Queue, para serem
    consumidos por uma thread de UI (ex: Tkinter) sem violar thread-safety.
    Cada item da fila é uma tupla (levelno, mensagem_formatada)."""

    def __init__(self, log_queue: "queue.Queue"):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        try:
            msg = self.format(record)
            self.log_queue.put((record.levelno, msg))
        except Exception:
            self.handleError(record)


def add_queue_handler(log_queue: "queue.Queue", level: int = logging.INFO) -> QueueHandler:
    """Adiciona um QueueHandler ao logger raiz (além dos handlers já
    configurados por setup_logging) e retorna o handler criado."""
    fmt_texto = "%(asctime)s | %(levelname)-8s | %(message)s"
    datefmt = "%H:%M:%S"

    handler = QueueHandler(log_queue)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(fmt_texto, datefmt=datefmt))
    logging.getLogger().addHandler(handler)
    return handler


def setup_logging(logs_folder: str, nome_execucao: str = "execucao", console: bool = True) -> str:
    """
    =====================================================================
    Descrição:
    Configura logging com saída colorida no console (colorama) e saída
    em arquivo (texto puro, sem códigos de cor) dentro de `logs_folder`.
    Cada execução gera um arquivo novo, identificado por data/hora, então
    o histórico de execuções fica preservado.
    =====================================================================
    Parâmetros:
    - logs_folder: pasta onde os arquivos .log serão salvos diretamente
      (a pasta é criada se não existir; nenhuma subpasta é adicionada).
    - nome_execucao: prefixo do nome do arquivo de log.
    - console: se False, não adiciona handler de console (útil para a
      GUI Tkinter rodando via pythonw.exe, sem console anexado).
    =====================================================================
    Retorno:
    - log_file: caminho do arquivo de log criado.
    =====================================================================
    """
    os.makedirs(logs_folder, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_file = os.path.join(logs_folder, f"{nome_execucao}_{timestamp}.log")

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.handlers.clear()  # evita handlers duplicados se chamado mais de uma vez

    fmt_texto = "%(asctime)s | %(levelname)-8s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    if console:
        _iniciar_colorama_com_seguranca()
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(ColorFormatter(fmt_texto, datefmt=datefmt))
        logger.addHandler(console_handler)

    # Arquivo, sem cor
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(fmt_texto, datefmt=datefmt))
    logger.addHandler(file_handler)

    logging.info(f"Log desta execução sendo salvo em: {log_file}")
    return log_file
