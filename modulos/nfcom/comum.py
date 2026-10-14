"""
Imports e constantes compartilhadas pelas operações NFCom (vindos do topo do
MEGA QG VIVO NFCom v2.3). Endpoints vêm do config.json via core.config.
"""
import base64
import calendar
import csv
import json
import os
import queue
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests
import urllib3

from core import config
from core.config import AMBIENTE_PRD, url_por_ambiente

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_endpoint = config.obter  # mesma assinatura do _endpoint() original
DEFAULT_LOG_DIR = config.log_dir()

NFCOM_NS = {"ns": "http://www.portalfiscal.inf.br/nfcom"}
UF_MAP = {
    '12': 'AC', '27': 'AL', '13': 'AM', '16': 'AP', '29': 'BA', '23': 'CE',
    '53': 'DF', '32': 'ES', '52': 'GO', '21': 'MA', '31': 'MG', '50': 'MS',
    '51': 'MT', '15': 'PA', '25': 'PB', '26': 'PE', '22': 'PI', '41': 'PR',
    '33': 'RJ', '24': 'RN', '11': 'RO', '14': 'RR', '43': 'RS', '42': 'SC',
    '28': 'SE', '35': 'SP', '17': 'TO'
}

# ===========================================================================
# ENGINE 1 - CONSULTA CHECKSEFAZ
# ===========================================================================
# v2.1: Homologação adicionada -- TODO CONFIRMAR host de HML com o time de
# infra (segue o mesmo padrão de host usado no Download de XMLs em HML).
CHECKSEFAZ_URL_PRD = _endpoint("checksefaz_url_prd", "MEGAQG_CHECKSEFAZ_URL_PRD")
CHECKSEFAZ_URL_HML = _endpoint("checksefaz_url_hml", "MEGAQG_CHECKSEFAZ_URL_HML")
BASE_LOG_NAME = "checksefaz_log"
WAIT_SVRS = 3
# v2.1: MG/MS/MT passaram de 60 notas/5min (300s) para 30 notas/2min (120s).
# SVRS mantido sem alteração (lotes de 2 a cada WAIT_SVRS segundos).
INTERVAL_PROPRIAS = 120
LIMITS = {"MG": 30, "MS": 30, "MT": 30}
UF_PROPRIAS = {"MG", "MS", "MT"}
GROUP_ORDER = ["SVRS", "MG", "MS", "MT"]


def time_sleep_1():
    import time
    time.sleep(1)


__all__ = [n for n in dir() if not n.startswith("__")]
