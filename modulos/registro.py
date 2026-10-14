"""
Registro único das operações do MegaQG Vivo: o hub, a barra lateral e o teste de
abertura de telas leem daqui. Nova operação = nova entrada nesta lista.

Campos:
  id          identificador estável (área.operação)
  area        seção do hub e da barra lateral
  icon, title, desc, accent   aparência do card (accent = chave de ui.theme.COLORS)
  page        "pacote.modulo:Classe" da tela (importada só quando aberta pela 1ª vez)
  urls        chaves de URL que dependem do ambiente (sem _prd/_hml)
  chaves      chaves fixas obrigatórias do config.json
  em_construcao  True = aparece no hub/barra lateral como próxima etapa, sem tela ainda
"""
import importlib

from core import config

AREAS = [
    ("NFCom", "accent"),
    ("NFSe", "cyan"),
    ("NFCe", "teal"),
    ("Relatórios", "success"),
]

OPERACOES = [
    # ----- NFCom (MEGA QG VIVO NFCom v2.3) -----
    dict(id="nfcom.consulta_sefaz", area="NFCom", icon="🔎", title="Consulta SEFAZ", accent="accent",
         desc="Status de processamento de chaves NFCom em lote (SVRS / MG / MS / MT). Chave com HTTP 422 "
              "é reenviada pelo ID.",
         page="modulos.nfcom.consulta_sefaz.page:ChecksefazPage", urls=["checksefaz_url", "checksefaz_reenvio_url"]),
    dict(id="nfcom.cancelamento", area="NFCom", icon="🛑", title="Cancelamento de Notas", accent="danger",
         desc="Eventos de cancelamento (110111) em lote a partir de uma lista de chaves. Irreversível.",
         page="modulos.nfcom.cancelamento.page:CancelamentoPage", urls=["cancelamento_url"]),
    dict(id="nfcom.download_xmls", area="NFCom", icon="📥", title="Download de XMLs", accent="purple",
         desc="Baixa XMLs de NFCom por lista de IDs e registra as falhas para reprocessar.",
         page="modulos.nfcom.download_xmls.page:DownloadXmlsPage", urls=["download_url"]),
    dict(id="nfcom.reenvio_sefaz", area="NFCom", icon="🔁", title="Reenvio à SEFAZ", accent="teal",
         desc="Reenvia os XMLs de uma pasta local para a SEFAZ. XML sem chave é reenviado pelo ID do arquivo.",
         page="modulos.nfcom.reenvio_sefaz.page:ReenvioSefazPage",
         urls=["reenvio_sefaz_url", "reenvio_sefaz_id_url"]),
    dict(id="nfcom.reenvio_webhook", area="NFCom", icon="🔔", title="Reenvio de WebHook", accent="warning",
         desc="Cria (opcional) e reenvia webhooks por subscrição a partir de uma lista de IDs.",
         page="modulos.nfcom.reenvio_webhook.page:ReenvioWebhookPage", urls=["webhook_create_url", "webhook_resend_url"]),

    # ----- NFSe (MEGA QG VIVO NFSe v2.0) -----
    dict(id="nfse.download_xmls", area="NFSe", icon="📥", title="Download de XMLs", accent="cyan",
         desc="Baixa XMLs de NFSe por lista de IDs, com opção de separar em COM CEP / SEM CEP.",
         page="modulos.nfse.download_xmls.page:DownloadXmlsPage", urls=["nfse_download_url"]),
    dict(id="nfse.relatorio_dps", area="NFSe", icon="📊", title="Relatório DPS sem Endereço", accent="purple",
         desc="Planilha com DPS, nome e CPF agrupados por cliente, a partir dos XMLs sem CEP.",
         page="modulos.nfse.relatorio_dps.page:RelatorioSemCepPage"),
    dict(id="nfse.expandir_csv", area="NFSe", icon="🧩", title="Expandir DPS no CSV", accent="indigo",
         desc="Desmembra um CSV com DPS agrupadas por vírgula em uma linha por DPS.",
         page="modulos.nfse.expandir_csv.page:ExpandirDpsCsvPage"),
    dict(id="nfse.reenvio_xml", area="NFSe", icon="🔁", title="Reenvio de XML", accent="blue",
         desc="Reenvia os XMLs de uma pasta local para o processamento, com lista de erros.",
         page="modulos.nfse.reenvio_xml.page:ReenvioXmlPage", urls=["nfse_reenvio_url"]),
    dict(id="nfse.consulta_dps", area="NFSe", icon="🔍", title="Consulta DPS", accent="warning",
         desc="Status de processamento de identificadores DPS junto à prefeitura, em lote.",
         page="modulos.nfse.consulta_dps.page:ConsultaDpsPage", urls=["nfse_consulta_dps_url"]),
    # QG XML v4 (não veio do legado/NFSe/qg.py: não passa por tools/portar_qgs.py)
    dict(id="nfse.correcao_xml", area="NFSe", icon="🔧", title="Correção de XMLs", accent="teal",
         desc="Corrige em lote os XMLs de DPS: encoding, endereço, cMun pelo CEP, PIS/COFINS, ISS e competência.",
         page="modulos.nfse.correcao_xml.page:CorrecaoXmlPage"),

    # ----- NFCe (piloto: Retorno de Contingência; Download de XMLs; Reprocessamento) -----
    dict(id="nfce.retorno_contingencia", area="NFCe", icon="🧾", title="Retorno de Contingência", accent="success",
         desc="Grava o retorno Autorizada (Retorno Cupom) ou Rejeitada, escolhido na tela, na COMANDO_NFEPACK "
              "para as chaves de um .txt.",
         page="modulos.nfce.retorno_contingencia.page:RetornoContingenciaPage",
         urls=["nfce_db_server", "nfce_db_database"]),
    dict(id="nfce.download_xmls", area="NFCe", icon="📥", title="Download de XMLs", accent="teal",
         desc="Baixa em massa os XMLs de emissão de NFCe a partir de um .txt de chaves de acesso.",
         page="modulos.nfce.download_xmls.page:DownloadXmlsNfcePage", urls=["nfce_download_url"]),
    dict(id="nfce.reprocessamento", area="NFCe", icon="♻️", title="Reprocessamento", accent="indigo",
         desc="Para as chaves de um .txt: baixa o XML, muda o status da nota para 3 e reenvia o XML completo.",
         page="modulos.nfce.reprocessamento.page:ReprocessamentoNfcePage",
         urls=["nfce_db_server", "nfce_db_database", "nfce_download_url", "nfce_reprocessamento_url"]),

    # ----- Relatórios -----
    dict(id="relatorios.exportador", area="Relatórios", icon="📄", title="Exportador de Relatório", accent="success",
         desc="CSV de NFCom direto do banco: por dia ou período único, todas ou só canceladas, XML opcional.",
         page="modulos.exportador_relatorio.page:ExportadorRelatorioPage",
         chaves=["relatorio_db_server", "relatorio_db_database"]),
]


def operacoes_ativas() -> list[dict]:
    """Operações que já têm tela (exclui as marcadas como em construção)."""
    return [op for op in OPERACOES if not op.get("em_construcao")]


def pendencias(op: dict, ambiente: str) -> list[str]:
    """Chaves do config.json que faltam para a operação rodar no ambiente dado."""
    if op.get("em_construcao"):
        return []
    sufixo = "prd" if ambiente == config.AMBIENTE_PRD else "hml"
    chaves = [f"{u}_{sufixo}" for u in op.get("urls", [])] + list(op.get("chaves", []))
    if op["id"] == "relatorios.exportador" and config.obter("relatorio_db_auth_type", default="sql") != "windows":
        chaves += ["relatorio_db_user", "relatorio_db_password"]
    # Só as operações de NFCe que usam o banco (o Download de XMLs usa só a URL)
    if "nfce_db_server" in op.get("urls", []) and config.obter("nfce_db_auth_type", default="sql") != "windows":
        chaves += ["nfce_db_user", "nfce_db_password"]
    return config.faltando(chaves)


def carregar_pagina(op: dict):
    modulo, classe = op["page"].split(":")
    return getattr(importlib.import_module(modulo), classe)
