import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
from requests.adapters import HTTPAdapter

# Quantas falhas individuais logar em detalhe antes de só contar em silêncio
# (evita inundar o log/tela em cenários de falha em massa, ex: rede fora do ar)
LIMITE_FALHAS_DETALHADAS = 15

# Sessões HTTP são criadas 1x por thread (não 1x por requisição). Isso é o
# que evita o esgotamento de portas TCP no Windows (WinError 10048) - a
# conexão fica "keep-alive" e é reaproveitada entre downloads, em vez de
# abrir/fechar uma conexão nova pra cada nota.
_sessao_por_thread = threading.local()


def _obter_sessao() -> requests.Session:
    sessao = getattr(_sessao_por_thread, "sessao", None)
    if sessao is None:
        sessao = requests.Session()
        adapter = HTTPAdapter(pool_connections=4, pool_maxsize=4, max_retries=0)
        sessao.mount("http://", adapter)
        sessao.mount("https://", adapter)
        _sessao_por_thread.sessao = sessao
    return sessao


def _normalizar_id(valor) -> str:
    """Normaliza um ID para string, removendo '.0' que o pandas às vezes
    adiciona quando a coluna vira float por causa de valores nulos."""
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto


def _baixar_um_xml(id_doc: str, url_base: str, timeout: int = 30, tentativas: int = 3):
    """Baixa o XML de um único ID, reaproveitando a conexão HTTP da thread
    (evita esgotamento de portas) e com pequeno backoff entre retentativas."""
    sessao = _obter_sessao()
    url = url_base.format(ID_DOC=id_doc)
    ultimo_erro = "Erro desconhecido"

    for tentativa in range(1, tentativas + 1):
        try:
            resp = sessao.get(url, timeout=timeout)
            resp.raise_for_status()
            conteudo = resp.text
            if not conteudo or not conteudo.strip():
                raise ValueError("Resposta vazia da API")
            return id_doc, True, conteudo
        except Exception as e:
            ultimo_erro = str(e)
            if tentativa < tentativas:
                time.sleep(0.4 * tentativa)  # pequeno respiro antes de tentar de novo

    return id_doc, False, ultimo_erro


def baixar_xmls_em_lote(
    ids: list,
    url_base: str,
    max_workers: int = 8,
    progress_callback=None,
) -> tuple[dict, dict]:
    """
    =====================================================================
    Descrição:
    Baixa os XMLs de uma lista de IDs em paralelo (ThreadPoolExecutor),
    reaproveitando conexões HTTP por thread (evita esgotamento de portas
    TCP em volumes grandes).
    =====================================================================
    Parâmetros:
    - ids: lista de IDs (qualquer tipo; serão normalizados para string).
    - url_base: URL da API com o placeholder {ID_DOC}.
    - max_workers: número de threads simultâneas.
    - progress_callback: função opcional progress_callback(concluidos, total).
    =====================================================================
    Retorno:
    - (xml_por_id, falhas): dois dicts, {id: conteudo_xml} e {id: erro}.
    =====================================================================
    """
    ids_unicos = list(dict.fromkeys(_normalizar_id(i) for i in ids if str(i).strip() not in ("", "-", "nan")))
    total = len(ids_unicos)
    xml_por_id = {}
    falhas = {}
    falhas_detalhadas_logadas = 0

    if total == 0:
        return xml_por_id, falhas

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_baixar_um_xml, id_doc, url_base): id_doc for id_doc in ids_unicos}
        concluidos = 0
        for future in as_completed(futures):
            id_doc, sucesso, resultado = future.result()
            concluidos += 1
            if sucesso:
                xml_por_id[id_doc] = resultado
            else:
                falhas[id_doc] = resultado
                if falhas_detalhadas_logadas < LIMITE_FALHAS_DETALHADAS:
                    logging.warning(f"Falha ao baixar XML do ID {id_doc}: {resultado}")
                    falhas_detalhadas_logadas += 1
                elif falhas_detalhadas_logadas == LIMITE_FALHAS_DETALHADAS:
                    logging.warning(
                        "Mais falhas de download ocorrendo neste bloco - suprimindo "
                        "detalhes individuais dos próximos (o total aparece no resumo abaixo)."
                    )
                    falhas_detalhadas_logadas += 1
            if progress_callback:
                progress_callback(concluidos, total)

    logging.info(f"XMLs baixados: {len(xml_por_id)}/{total} (falhas: {len(falhas)})")
    return xml_por_id, falhas


def adicionar_coluna_xml(
    df: pd.DataFrame,
    coluna_id: str,
    url_base: str,
    max_workers: int = 8,
    nome_coluna_xml: str = "XML",
    progress_callback=None,
) -> pd.DataFrame:
    """
    =====================================================================
    Descrição:
    Baixa os XMLs correspondentes aos IDs de `coluna_id` e adiciona uma
    nova coluna `nome_coluna_xml` no DataFrame, com o XML certo casado
    com a linha certa (via ID). Linhas cujo download falhar ficam com a
    célula vazia (a falha já fica registrada no log). Sem limite/truncamento
    de tamanho - isso só fazia sentido para Excel; em CSV não há essa
    restrição, e truncar um XML fiscal poderia corromper o documento.
    =====================================================================
    """
    if df.empty:
        df[nome_coluna_xml] = ""
        return df

    if coluna_id not in df.columns:
        logging.error(f"Coluna '{coluna_id}' não encontrada no DataFrame; XML não será baixado.")
        df[nome_coluna_xml] = ""
        return df

    ids = df[coluna_id].tolist()
    xml_por_id, _falhas = baixar_xmls_em_lote(ids, url_base, max_workers=max_workers, progress_callback=progress_callback)

    df[nome_coluna_xml] = df[coluna_id].map(lambda v: xml_por_id.get(_normalizar_id(v), ""))
    return df
