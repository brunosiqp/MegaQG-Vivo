import calendar
import logging
import os
from datetime import datetime, timedelta

from clientes.vivo.config import (
    CHUNK_SIZE_PROCESSAMENTO,
    COLUNA_ID_XML,
    FILTROS_STATUS,
    MAX_WORKERS_XML,
    db_config,
    url_xml,
)
from modulos.exportador_relatorio.queries import query
from core import config
from core.database import sql_conn
from core.exportador import ExportacaoCancelada, exportar_relatorio_csv, verificar_pasta_gravavel
from core.xml_downloader import adicionar_coluna_xml

COLUNAS_TEXTO = ["CNPJ Emissor"]

# Modos de agrupamento do relatório
MODO_DIARIO = "diario"     # 1 arquivo por dia (filtro de 1 dia por consulta)
MODO_PERIODO = "periodo"   # 1 arquivo único para o período (mês inteiro ou dia X a Y), numa consulta só
MODO_MENSAL = MODO_PERIODO  # nome antigo, mantido por compatibilidade


def dias_validos_no_range(ano: int, mes: int, dia_ini: int, dia_fim: int) -> list[datetime]:
    """Retorna a lista de datetimes válidos entre dia_ini e dia_fim (inclusive)
    para o ano/mês dados, ignorando silenciosamente dias que não existem
    no mês (ex: pedir até dia 31 em abril)."""
    ultimo_dia_mes = calendar.monthrange(ano, mes)[1]
    dia_fim = min(dia_fim, ultimo_dia_mes)
    dias = []
    for dia in range(dia_ini, dia_fim + 1):
        try:
            dias.append(datetime(ano, mes, dia))
        except ValueError:
            continue
    return dias


def montar_periodos(modo: str, ano: int, mes: int, dia_ini: int, dia_fim: int, prefixo: str = "") -> list[dict]:
    """
    Monta a lista de relatórios a gerar. Cada item tem o filtro de datas
    (inicio inclusivo, fim exclusivo), o rótulo para o log e onde salvar
    (subpasta relativa à pasta de saída + nome do arquivo).

    - MODO_DIARIO: um item por dia válido do range -> <Mês>/dd-mm-aaaa/dd-mm-aaaa.csv
    - MODO_PERIODO: um item só, do dia_ini ao dia_fim, numa consulta só ->
      <Mês>/mes-mm-aaaa.csv (mês inteiro) ou <Mês>/periodo-dd-a-dd-mm-aaaa.csv
    """
    if modo == MODO_PERIODO:
        dias = dias_validos_no_range(ano, mes, dia_ini, dia_fim)
        if not dias:
            return []
        inicio, fim = dias[0], dias[-1] + timedelta(days=1)
        mes_inteiro = dias[0].day == 1 and len(dias) == calendar.monthrange(ano, mes)[1]
        if mes_inteiro:
            rotulo, arquivo = f"mês {mes:02d}/{ano}", f"{prefixo}mes-{mes:02d}-{ano}.csv"
        else:
            d1, d2 = dias[0].day, dias[-1].day
            rotulo = f"{d1:02d} a {d2:02d}/{mes:02d}/{ano}"
            arquivo = f"{prefixo}periodo-{d1:02d}-a-{d2:02d}-{mes:02d}-{ano}.csv"
        return [{
            "inicio": inicio,
            "fim": fim,
            "rotulo": rotulo,
            "subpasta": inicio.strftime("%B"),
            "arquivo": arquivo,
        }]

    periodos = []
    for data in dias_validos_no_range(ano, mes, dia_ini, dia_fim):
        nome = data.strftime("%d-%m-%Y")
        periodos.append({
            "inicio": data,
            "fim": data + timedelta(days=1),
            "rotulo": data.strftime("%d/%m/%Y"),
            "subpasta": os.path.join(data.strftime("%B"), nome),
            "arquivo": f"{prefixo}{nome}.csv",
        })
    return periodos


def _log_progresso_xml(concluidos: int, total: int) -> None:
    # Loga em ~10 pontos ao longo do bloco, não a cada ID (evita poluir o log)
    intervalo = max(1, total // 10)
    if total and (concluidos % intervalo == 0 or concluidos == total):
        logging.info(f"    XMLs baixados neste bloco: {concluidos}/{total}")


def _pos_processamento_com_xml(url_api: str):
    def processar(chunk):
        return adicionar_coluna_xml(
            chunk,
            coluna_id=COLUNA_ID_XML,
            url_base=url_api,
            max_workers=MAX_WORKERS_XML,
            progress_callback=_log_progresso_xml,
        )
    return processar


def rodar_exportacao(
    ano: int,
    mes: int,
    dia_ini: int,
    dia_fim: int,
    output_base_path: str | None = None,
    progress_callback=None,
    deve_cancelar=None,
    baixar_xml: bool = True,
    modo: str = MODO_DIARIO,
    filtro_status: str = "todas",
    progress_linhas_callback=None,
    ambiente_xml: str = config.AMBIENTE_PRD,
) -> dict:
    """
    =====================================================================
    Descrição:
    Roda a exportação de relatórios NFCom (CSV) de um mês/ano,
    reaproveitável tanto pelo script de linha de comando quanto pela
    interface gráfica. Processa cada relatório em blocos (chunks), então
    mesmo períodos com 10+ milhões de notas não estouram a memória.
    =====================================================================
    Parâmetros:
    - ano, mes: período a exportar.
    - dia_ini, dia_fim: range de dias (inclusive) dentro do mês.
    - output_base_path: pasta onde salvar os relatórios. Se None, usa a
      pasta_saida_padrao do config.json.
    - progress_callback: função opcional chamada como
      progress_callback(indice_atual, total, rotulo) após cada relatório.
    - deve_cancelar: função opcional sem argumentos que retorna True se a
      execução deve ser interrompida (usado pelo botão Cancelar da GUI).
      É checada entre relatórios e também entre blocos de um relatório.
    - baixar_xml: se True (padrão), baixa o XML de cada nota via API e
      adiciona como coluna extra no relatório (por bloco, nunca salvo em
      disco fisicamente - vai direto para a célula do CSV).
    - modo: MODO_DIARIO (1 arquivo por dia) ou MODO_PERIODO (1 arquivo
      único para o período, numa consulta só).
    - filtro_status: chave de FILTROS_STATUS ("todas" = 6, 9, 10;
      "canceladas" = só 9, arquivos com prefixo "canceladas_").
    - progress_linhas_callback: função opcional chamada como
      progress_linhas_callback(linhas_no_relatorio_atual, rotulo) após cada bloco.
    - ambiente_xml: config.AMBIENTE_PRD ou AMBIENTE_HML (URL de download do XML).
    =====================================================================
    Retorno:
    - dict: {"sucesso": [...], "falhas": [...], "total": int, "cancelado": bool}
    =====================================================================
    """
    output_base_path = output_base_path or config.pasta_saida_padrao()
    status, prefixo = FILTROS_STATUS[filtro_status]

    periodos = montar_periodos(modo, ano, mes, dia_ini, dia_fim, prefixo)
    total = len(periodos)
    sucesso = []
    falhas = []
    cancelado = False

    if modo == MODO_PERIODO:
        rotulo_unico = periodos[0]["rotulo"] if periodos else f"{mes:02d}/{ano}"
        descricao_periodo = f"{rotulo_unico} em 1 arquivo único"
    else:
        descricao_periodo = (
            f"{mes:02d}/{ano}, dias {dia_ini} a {dia_fim} ({total} dia(s) válido(s)), 1 arquivo por dia"
        )
    logging.info(
        f"Exportando NFCom: {descricao_periodo}. "
        f"Status: {', '.join(str(s) for s in status)}"
        f"{' (somente canceladas)' if filtro_status == 'canceladas' else ''}. "
        f"Pasta de saída: {output_base_path}. "
        f"Formato: CSV (streaming em blocos de {CHUNK_SIZE_PROCESSAMENTO} linhas). "
        f"Download de XML: {'sim (direto no CSV, sem salvar em disco)' if baixar_xml else 'não'}."
    )

    pasta_ok, erro_pasta = verificar_pasta_gravavel(output_base_path)
    if not pasta_ok:
        logging.critical(
            f"Não é possível escrever na pasta de saída '{output_base_path}': {erro_pasta}. "
            f"Verifique permissões, ou se a pasta está sincronizando no OneDrive/sendo "
            f"escaneada por antivírus. Abortando execução antes de gastar tempo com download."
        )
        return {"sucesso": [], "falhas": [], "total": total, "cancelado": False}

    pos_processamento_fn = None
    if baixar_xml:
        url_api = url_xml(ambiente_xml)
        if not url_api:
            logging.critical(
                f"URL de download de XML ({ambiente_xml}) não configurada: preencha "
                f"download_url_{'prd' if ambiente_xml == config.AMBIENTE_PRD else 'hml'} no config.json, "
                f"ou desmarque 'Baixar XML'."
            )
            return {"sucesso": [], "falhas": [], "total": total, "cancelado": False}
        pos_processamento_fn = _pos_processamento_com_xml(url_api)

    try:
        logging.info(f"Configuração: {config.origem()}")
        conn = sql_conn(db_config())
    except Exception as e:
        logging.critical(f"Não foi possível conectar ao banco. Abortando execução. {e}")
        return {"sucesso": sucesso, "falhas": falhas, "total": total, "cancelado": False}

    try:
        for i, periodo in enumerate(periodos, start=1):
            rotulo = periodo["rotulo"]
            if deve_cancelar and deve_cancelar():
                logging.warning("Execução cancelada pelo usuário.")
                cancelado = True
                break

            callback_linhas = None
            if progress_linhas_callback:
                callback_linhas = lambda linhas, r=rotulo: progress_linhas_callback(linhas, r)

            try:
                logging.info(f"Processando {rotulo}...")
                arquivos_gerados = exportar_relatorio_csv(
                    query_sql=query(periodo["inicio"], periodo["fim"], status),
                    out_folder=os.path.join(output_base_path, periodo["subpasta"]),
                    nome_base=periodo["arquivo"],
                    conn=conn,
                    colunas_texto=COLUNAS_TEXTO,
                    pos_processamento_chunk_fn=pos_processamento_fn,
                    chunksize=CHUNK_SIZE_PROCESSAMENTO,
                    progress_callback_chunk=callback_linhas,
                    deve_cancelar=deve_cancelar,
                )
                if len(arquivos_gerados) == 1:
                    logging.info(f"OK: {arquivos_gerados[0]}")
                else:
                    logging.info(f"OK: {len(arquivos_gerados)} arquivos gerados para {rotulo}")
                sucesso.append(rotulo)
            except ExportacaoCancelada as e:
                logging.warning(
                    f"Execução cancelada pelo usuário durante {rotulo}. "
                    f"Arquivo(s) incompleto(s): {', '.join(e.arquivos_parciais) or 'nenhum'}"
                )
                cancelado = True
                break
            except Exception as e:
                logging.error(f"Falha ao processar {rotulo}: {e}")
                falhas.append(rotulo)
            finally:
                if progress_callback:
                    progress_callback(i, total, rotulo)
    finally:
        conn.close()

    logging.info("=== Resumo da execução ===")
    logging.info(f"Relatórios gerados com sucesso: {len(sucesso)}")
    if falhas:
        logging.warning(f"Com falha ({len(falhas)}): {', '.join(falhas)}")
    if not falhas and not cancelado:
        logging.info("Nenhuma falha durante a execução.")

    return {"sucesso": sucesso, "falhas": falhas, "total": total, "cancelado": cancelado}
