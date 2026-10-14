"""
Diagnóstico isolado de conexão com o banco da Vivo (usa o config.json, chaves relatorio_db_*).
Rode: python tools/test_connection.py
"""
import os
import sys

import pyodbc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from clientes.vivo.config import db_config  # noqa: E402

print("=== Drivers ODBC instalados ===")
for d in pyodbc.drivers():
    print(" -", d)

CRED = db_config()
SERVER = CRED["server"]
DATABASE = CRED["database"]
BASE = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    f"SERVER={SERVER};"
    f"UID={CRED['user']};"
    f"PWD={CRED['password']};"
)

TENTATIVAS = [
    ("sem porta, TrustServerCertificate=yes", f"DATABASE={DATABASE};TrustServerCertificate=yes;"),
    ("sem TrustServerCertificate", f"DATABASE={DATABASE};"),
    ("com Encrypt=no explicito", f"DATABASE={DATABASE};Encrypt=no;"),
    ("banco 'master' (isola se o problema e a base)", "DATABASE=master;TrustServerCertificate=yes;"),
]

for i, (descricao, extra) in enumerate(TENTATIVAS, start=1):
    print(f"\n=== Tentativa {i}: {descricao} ===")
    try:
        conn = pyodbc.connect(BASE + extra, timeout=15)
        print("SUCESSO!")
        conn.close()
    except Exception as e:
        print("FALHOU:", e)

input("\nPressione ENTER para sair...")
