"""
Testa se a API de download de XML aceita MÚLTIPLOS IDs numa única chamada
(ex: ids=101,102,103), em vez de 1 requisição por ID. Isso é essencial pra
performance em volumes grandes (40 milhões de notas/mês = 40 milhões de
requisições HTTP se for 1 por vez).

Rode: python tools/test_xml_batch.py   (usa download_url_prd do config.json)
"""
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import config  # noqa: E402

# Mesma URL do Download de XMLs NFCom; o placeholder {ID_DOC} vira {ids} aqui
URL_BASE = config.url_por_ambiente("download_url", config.AMBIENTE_PRD).replace("{ID_DOC}", "{ids}")
if not URL_BASE:
    sys.exit(f"Preencha download_url_prd em {config.caminho_arquivo()}")

# Troque pelos IDs reais de 2-3 notas que você já sabe que existem
# (pegue da coluna "ID Mensageria" de algum relatório já gerado)
IDS_TESTE = ["COLOQUE_UM_ID_AQUI", "COLOQUE_OUTRO_ID_AQUI"]


def testar_individual():
    print("=== Teste 1: download individual (1 ID por chamada) ===")
    tamanhos = {}
    for id_doc in IDS_TESTE:
        url = URL_BASE.format(ids=id_doc)
        print(f"\nGET {url}")
        try:
            resp = requests.get(url, timeout=30)
            print(f"Status: {resp.status_code}")
            print(f"Tamanho da resposta: {len(resp.text)} caracteres")
            print(f"Primeiros 200 caracteres:\n{resp.text[:200]}")
            tamanhos[id_doc] = len(resp.text)
        except Exception as e:
            print(f"Erro: {e}")
    return tamanhos


def testar_em_lote():
    print("\n\n=== Teste 2: múltiplos IDs separados por vírgula, numa única chamada ===")
    ids_juntos = ",".join(IDS_TESTE)
    url = URL_BASE.format(ids=ids_juntos)
    print(f"GET {url}")
    try:
        resp = requests.get(url, timeout=30)
        print(f"Status: {resp.status_code}")
        print(f"Tamanho da resposta: {len(resp.text)} caracteres")
        print(f"Content-Type: {resp.headers.get('Content-Type')}")
        print(f"Content-Disposition: {resp.headers.get('Content-Disposition')}")
        print(f"Primeiros 500 caracteres:\n{resp.text[:500]}")
        return resp
    except Exception as e:
        print(f"Erro: {e}")
        return None


def main():
    tamanhos_individuais = testar_individual()
    resp_lote = testar_em_lote()

    print("\n\n=== Análise ===")
    if resp_lote is None:
        print("A chamada em lote falhou - provavelmente a API NÃO suporta múltiplos IDs.")
    elif resp_lote.status_code != 200:
        print(f"A chamada em lote retornou status {resp_lote.status_code} - provavelmente NÃO suporta lote.")
    else:
        soma_individuais = sum(tamanhos_individuais.values())
        tamanho_lote = len(resp_lote.text)
        print(f"Soma dos tamanhos individuais: {soma_individuais} caracteres")
        print(f"Tamanho da resposta em lote:    {tamanho_lote} caracteres")
        if tamanho_lote >= soma_individuais * 0.7:
            print("\n>>> PARECE SUPORTAR LOTE: a resposta é grande o suficiente pra conter os XMLs de todos os IDs.")
            print(">>> Verifique manualmente o conteúdo (pode ser um .zip, ou XMLs concatenados, ou um <lote> com vários <NFCom>).")
            print(">>> Me manda esse resultado que eu adapto o downloader pra usar lote e acelerar MUITO o processo.")
        else:
            print("\n>>> PROVAVELMENTE NÃO suporta lote: a resposta em lote é do tamanho de 1 XML só")
            print(">>> (a API pode estar ignorando os IDs extras e devolvendo só o primeiro).")

    input("\nPressione ENTER para sair...")


if __name__ == "__main__":
    main()
