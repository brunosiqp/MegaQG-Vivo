"""
Imports compartilhados pelas operações NFSe (vindos do topo do MEGA QG VIVO
NFSe v2.0). URLs e pasta de log agora vêm do config.json via core.config.
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

DEFAULT_LOG_DIR = config.log_dir()  # no original era fixo: C:\\ScriptPS\\logs

__all__ = [n for n in dir() if not n.startswith("__")]
