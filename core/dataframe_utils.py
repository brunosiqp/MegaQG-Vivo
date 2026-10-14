import pandas as pd
import warnings
import logging

warnings.filterwarnings("ignore", category=UserWarning)


def dataframe(
    query: str,
    conn: object,
    colunas_texto: list[str] | None = None,
) -> pd.DataFrame:
    """
    =====================================================================
    Descrição:
    Executa uma consulta SQL e retorna um DataFrame do Pandas.
    Genérica: recebe a lista de colunas que devem ser forçadas para
    string (ex: CNPJs, que não podem virar número/notação científica
    no Excel), então serve para qualquer cliente sem alterar o código.
    ATENÇÃO: carrega o resultado INTEIRO em memória de uma vez. Para
    volumes grandes (milhões de linhas), use `iterar_query_em_chunks`.
    =====================================================================
    Parâmetros:
    - query: string, consulta SQL a ser executada.
    - conn: objeto de conexão com o banco de dados.
    - colunas_texto: lista de nomes de colunas a converter para string.
      Se None, nenhuma conversão é feita. Colunas que não existirem no
      resultado são ignoradas silenciosamente (evita KeyError quando a
      query muda de cliente para cliente).
    =====================================================================
    Retorno:
    - df: DataFrame do Pandas contendo os resultados da consulta.
    =====================================================================
    Exemplo de uso:
    df = dataframe(query, conn, colunas_texto=["CNPJ Emissor"])
    =====================================================================
    """

    try:
        df = pd.read_sql(query, conn)
    except Exception as e:
        logging.error(f"Erro ao executar a consulta SQL: {e}")
        raise

    df.fillna('-', inplace=True)

    if colunas_texto:
        for col in colunas_texto:
            if col in df.columns:
                df[col] = df[col].astype(str)

    return df


def iterar_query_em_chunks(
    query: str,
    conn: object,
    chunksize: int = 50_000,
    colunas_texto: list[str] | None = None,
):
    """
    =====================================================================
    Descrição:
    Executa a consulta SQL e itera em BLOCOS (chunks) de `chunksize`
    linhas, sem carregar o resultado inteiro em memória de uma vez.
    Essencial para dias com milhões de notas - sem isso, baixar o XML
    de 10 milhões de linhas de uma vez pode facilmente estourar a
    memória RAM disponível.
    =====================================================================
    Parâmetros:
    - query: consulta SQL a ser executada.
    - conn: conexão de banco já aberta.
    - chunksize: quantidade de linhas por bloco.
    - colunas_texto: mesma lógica de `dataframe()`, aplicada em cada bloco.
    =====================================================================
    Retorno:
    - generator que produz DataFrames (um por bloco).
    =====================================================================
    """
    try:
        for chunk in pd.read_sql(query, conn, chunksize=chunksize):
            chunk.fillna('-', inplace=True)
            if colunas_texto:
                for col in colunas_texto:
                    if col in chunk.columns:
                        chunk[col] = chunk[col].astype(str)
            yield chunk
    except Exception as e:
        logging.error(f"Erro ao executar a consulta SQL (streaming em chunks): {e}")
        raise
