import csv
import logging
import os
import time
from datetime import datetime

import pandas as pd

from core.dataframe_utils import iterar_query_em_chunks

# Separador ';' porque é o padrão que o Excel em pt-BR espera (já que a
# vírgula é usada como separador decimal no Brasil).
SEPARADOR_CSV = ";"

# A partir de quantas linhas um arquivo CSV do dia é fechado e um novo é
# aberto (mesma pasta do dia, sufixo _parte2, _parte3...). Facilita abrir
# no Excel/editor e manusear o espaço em disco em dias muito grandes.
LIMITE_LINHAS_POR_ARQUIVO = 3_000_000


def _com_retry(callable_sem_args, tentativas: int = 5, espera_inicial: float = 2.0, descricao: str = "operação de arquivo"):
    """
    Executa uma função sem argumentos, com retentativas em caso de erro de
    acesso negado transitório - muito comum quando a pasta de saída está
    dentro de uma área sincronizada (OneDrive, Desktop redirecionado) ou
    sendo escaneada por antivírus logo após um arquivo grande ser criado.
    """
    ultimo_erro = None
    for tentativa in range(1, tentativas + 1):
        try:
            return callable_sem_args()
        except (PermissionError, OSError) as e:
            ultimo_erro = e
            eh_erro_acesso = isinstance(e, PermissionError) or getattr(e, "winerror", None) in (5, 32)
            if not eh_erro_acesso or tentativa == tentativas:
                raise
            espera = espera_inicial * tentativa
            logging.warning(
                f"Acesso negado ao tentar {descricao} (tentativa {tentativa}/{tentativas}) - "
                f"provavelmente OneDrive ou antivírus segurando o arquivo/pasta. "
                f"Tentando de novo em {espera:.1f}s..."
            )
            time.sleep(espera)
    raise ultimo_erro


def verificar_pasta_gravavel(pasta: str) -> tuple[bool, str]:
    """
    Testa rapidamente se dá pra escrever na pasta de saída, ANTES de
    começar a exportação de verdade (evita descobrir um problema de
    permissão só depois de vários minutos baixando XML).
    Retorna (ok, mensagem_erro_ou_vazio).
    """
    try:
        os.makedirs(pasta, exist_ok=True)
        arquivo_teste = os.path.join(pasta, ".teste_escrita_vivo_nfcom.tmp")
        with open(arquivo_teste, "w") as f:
            f.write("teste")
        os.remove(arquivo_teste)
        return True, ""
    except Exception as e:
        return False, str(e)


class ExportacaoCancelada(Exception):
    """Levantada quando o usuário cancela no meio de um relatório (entre blocos)."""

    def __init__(self, arquivos_parciais: list[str]):
        super().__init__("Exportação cancelada pelo usuário.")
        self.arquivos_parciais = arquivos_parciais


def exportar_relatorio_csv(
    query_sql: str,
    out_folder: str,
    nome_base: str,
    conn,
    colunas_texto: list[str] | None = None,
    pos_processamento_chunk_fn=None,
    chunksize: int = 50_000,
    progress_callback_chunk=None,
    deve_cancelar=None,
) -> list[str]:
    """
    =====================================================================
    Descrição:
    Gera um relatório em CSV, processando em BLOCOS (chunks) para
    manter o uso de memória controlado mesmo com milhões de notas. Cada
    bloco é lido do banco, processado (ex: XML adicionado) e
    IMEDIATAMENTE gravado no arquivo - nunca acumula tudo em memória.

    Quando o relatório ultrapassa LIMITE_LINHAS_POR_ARQUIVO linhas, o
    arquivo atual é fechado e um novo é aberto na MESMA pasta, com sufixo
    _parte2, _parte3, etc. (ex: 01-07-2026.csv, 01-07-2026_parte2.csv...).
    =====================================================================
    Parâmetros:
    - query_sql: consulta SQL já montada.
    - out_folder: pasta onde salvar o(s) arquivo(s) (é criada se faltar).
    - nome_base: nome do arquivo (ex: "01-07-2026.csv").
    - conn: conexão de banco já aberta.
    - colunas_texto: colunas a forçar como string (ex: CNPJ).
    - pos_processamento_chunk_fn: função opcional que recebe um bloco
      (DataFrame) e retorna o bloco modificado - usada para adicionar a
      coluna de XML, aplicada bloco a bloco.
    - chunksize: quantidade de linhas processadas por vez.
    - progress_callback_chunk: função opcional chamada como
      progress_callback_chunk(linhas_processadas_no_relatorio) após cada bloco.
    - deve_cancelar: função opcional sem argumentos; se retornar True entre
      um bloco e outro, para e levanta ExportacaoCancelada.
    =====================================================================
    Retorno:
    - lista com o(s) caminho(s) do(s) arquivo(s) gerado(s)
      (1 item se coube tudo num arquivo só, vários se precisou dividir).
    =====================================================================
    """
    _com_retry(lambda: os.makedirs(out_folder, exist_ok=True), descricao=f"criar pasta {out_folder}")

    nome_sem_ext, ext = os.path.splitext(nome_base)

    def caminho_da_parte(numero_parte: int) -> str:
        if numero_parte == 1:
            return os.path.join(out_folder, nome_base)
        return os.path.join(out_folder, f"{nome_sem_ext}_parte{numero_parte}{ext}")

    total_linhas = 0           # total do relatório (todos os arquivos somados)
    linhas_arquivo_atual = 0   # total só do arquivo que está sendo escrito agora
    numero_parte = 1
    out_file = caminho_da_parte(numero_parte)
    primeiro_bloco_do_arquivo = True
    arquivos_gerados = []

    for chunk in iterar_query_em_chunks(query_sql, conn, chunksize=chunksize, colunas_texto=colunas_texto):
        if deve_cancelar and deve_cancelar():
            raise ExportacaoCancelada(arquivos_gerados)
        if pos_processamento_chunk_fn:
            chunk = pos_processamento_chunk_fn(chunk)

        modo = "w" if primeiro_bloco_do_arquivo else "a"
        # BOM (utf-8-sig) só na primeira escrita de CADA arquivo - se repetir
        # em todo append, o Excel vê um BOM no meio do arquivo e corrompe a leitura.
        encoding = "utf-8-sig" if primeiro_bloco_do_arquivo else "utf-8"

        _com_retry(
            lambda: chunk.to_csv(
                out_file,
                mode=modo,
                header=primeiro_bloco_do_arquivo,
                index=False,
                sep=SEPARADOR_CSV,
                encoding=encoding,
                quoting=csv.QUOTE_MINIMAL,
            ),
            descricao=f"gravar bloco em {os.path.basename(out_file)}",
        )

        if primeiro_bloco_do_arquivo:
            arquivos_gerados.append(out_file)
        primeiro_bloco_do_arquivo = False

        total_linhas += len(chunk)
        linhas_arquivo_atual += len(chunk)

        logging.info(
            f"  ... {linhas_arquivo_atual} linhas em {os.path.basename(out_file)} "
            f"({total_linhas} no relatório até agora)"
        )
        if progress_callback_chunk:
            progress_callback_chunk(total_linhas)

        if linhas_arquivo_atual >= LIMITE_LINHAS_POR_ARQUIVO:
            logging.info(
                f"Arquivo {os.path.basename(out_file)} atingiu {linhas_arquivo_atual} linhas "
                f"(limite {LIMITE_LINHAS_POR_ARQUIVO}) - iniciando novo arquivo na mesma pasta."
            )
            numero_parte += 1
            out_file = caminho_da_parte(numero_parte)
            linhas_arquivo_atual = 0
            primeiro_bloco_do_arquivo = True

    if not arquivos_gerados:
        # Query não retornou nenhuma linha - gera arquivo vazio (só cabeçalho
        # não é possível sem saber as colunas, então gera um CSV realmente vazio).
        _com_retry(lambda: open(out_file, "w", encoding="utf-8-sig").close(), descricao=f"criar {out_file} vazio")
        arquivos_gerados.append(out_file)

    if len(arquivos_gerados) == 1:
        logging.info(f"Relatório gerado: {arquivos_gerados[0]} ({total_linhas} linhas)")
    else:
        logging.info(
            f"Relatório gerado em {len(arquivos_gerados)} arquivos "
            f"(total {total_linhas} linhas, acima do limite de {LIMITE_LINHAS_POR_ARQUIVO} por arquivo): "
            + ", ".join(os.path.basename(a) for a in arquivos_gerados)
        )

    return arquivos_gerados
