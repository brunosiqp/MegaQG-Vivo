"""
Monta o pacote de implantação do MegaQG Vivo para o servidor on-premise.

Saída (dentro de dist/, fora do git):
  dist/MegaQGVivo_<versão>_<data>/
      MegaQGVivo.exe          (config.json embutido pelo build)
      config.example.json     (modelo, sem valores, para sobrescrever o embutido se preciso)
      LEIA-ME.txt             (passo a passo de implantação e teste)
      SHA256SUMS.txt          (conferência de integridade após copiar)
  dist/MegaQGVivo_<versão>_<data>.zip

Uso (depois do build): python tools/empacotar_deploy.py
"""
import hashlib
import os
import shutil
import sys
import zipfile
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from core.versao import APP_VERSION  # noqa: E402
from modulos.registro import operacoes_ativas  # noqa: E402

LEIA_ME = """MegaQG Vivo {versao} - pacote de implantação ({data})
==================================================================

Conteúdo
--------
  MegaQGVivo.exe        aplicativo
  config.json           CONFIGURAÇÃO REAL: URLs de NFCom/NFSe e dados dos bancos (editável)
  config.example.json   modelo de configuração, sem valores
  SHA256SUMS.txt        códigos para conferir que a cópia chegou íntegra

Requisitos do servidor
----------------------
  - Windows 64 bits.
  - ODBC Driver 17 for SQL Server (só para o Exportador de Relatório).
  - Acesso de rede aos endpoints de NFCom/NFSe e ao banco (mesma rede dos QGs atuais).

Implantação
-----------
  1. Copie a pasta inteira para o servidor, por exemplo C:\\MegaQGVivo\\.
  2. Confira a integridade (PowerShell, dentro da pasta):
        Get-FileHash .\\MegaQGVivo.exe -Algorithm SHA256
     O código tem que ser igual ao do SHA256SUMS.txt.
  3. Rode o autoteste (abre todas as telas e fecha sozinho):
        .\\MegaQGVivo.exe --autoteste
     Resultado em C:\\ScriptPS\\logs\\autoteste.txt: a última linha deve ser "{telas}/{telas} telas abriram".
     (Todas as operações gravam log nessa mesma pasta fixa.)
  4. Abra o MegaQGVivo.exe normalmente. A primeira abertura pode levar alguns segundos
     (o antivírus verifica o exe novo).

Configuração
------------
  O config.json desta pasta tem todas as URLs e os dados dos bancos e é o que o app usa
  (o exe também leva uma cópia embutida, usada só se o config.json for apagado).
  Para trocar um endpoint ou uma senha, edite o config.json no Bloco de Notas e reabra o app:
  não precisa recompilar.

  Situação deste pacote:
{situacao}

  Os cards do hub mostram "Configurar" e a chave que falta enquanto o endpoint
  não estiver preenchido.

Roteiro de teste sugerido
-------------------------
  1. Ambiente em HOMOLOGAÇÃO (seletor no topo).
  2. Download de XMLs (NFCom e NFSe) com um .txt de 2 ou 3 IDs conhecidos.
  3. Consulta SEFAZ / Consulta DPS com poucas chaves.
  4. Exportador de Relatório: 1 dia, sem XML; depois com XML.
  5. Comparar os resultados com os QGs atuais (mesmos arquivos de entrada).
  6. Só então repetir em PRODUÇÃO. Cancelamento por último, com poucas chaves.

Segurança
---------
  O exe contém as credenciais do banco. Não copie o exe ou o pacote para fora da rede
  interna, não anexe em e-mail/chat e não suba no GitHub.

Reverter
--------
  Os QGs atuais continuam funcionando em paralelo. Para voltar, basta não usar esta pasta.
"""


def sha256(caminho: str) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def situacao_config() -> str:
    """Quais grupos de chaves estão preenchidos no config.json que foi embutido (sem mostrar valores)."""
    from core import config
    from modulos.registro import operacoes_ativas, pendencias

    linhas = [f"    Configuração embutida: {'sim' if os.path.exists(os.path.join(RAIZ, 'config.json')) else 'NÃO'}"]
    for ambiente in (config.AMBIENTE_PRD, config.AMBIENTE_HML):
        faltando = [op["title"] + f" ({op['area']})" for op in operacoes_ativas() if pendencias(op, ambiente)]
        if faltando:
            linhas.append(f"    {ambiente}: falta configurar " + ", ".join(faltando))
        else:
            linhas.append(f"    {ambiente}: todas as operações configuradas")
    return "\n".join(linhas)


def main():
    exe = os.path.join(RAIZ, "dist", "MegaQGVivo.exe")
    if not os.path.exists(exe):
        sys.exit("dist/MegaQGVivo.exe não encontrado: rode o build antes.")

    data = datetime.now().strftime("%Y-%m-%d")
    nome = f"MegaQGVivo_{APP_VERSION}_{data}"
    pasta = os.path.join(RAIZ, "dist", nome)
    shutil.rmtree(pasta, ignore_errors=True)
    os.makedirs(pasta)

    shutil.copy2(exe, os.path.join(pasta, "MegaQGVivo.exe"))
    shutil.copy2(os.path.join(RAIZ, "config.example.json"), os.path.join(pasta, "config.example.json"))
    if os.path.exists(os.path.join(RAIZ, "config.json")):
        shutil.copy2(os.path.join(RAIZ, "config.json"), os.path.join(pasta, "config.json"))
    with open(os.path.join(pasta, "LEIA-ME.txt"), "w", encoding="utf-8-sig") as f:
        f.write(LEIA_ME.format(versao=APP_VERSION, data=data, situacao=situacao_config(), telas=len(operacoes_ativas())))
    with open(os.path.join(pasta, "SHA256SUMS.txt"), "w", encoding="utf-8") as f:
        for arquivo in ("MegaQGVivo.exe", "config.json", "config.example.json", "LEIA-ME.txt"):
            if not os.path.exists(os.path.join(pasta, arquivo)):
                continue
            f.write(f"{sha256(os.path.join(pasta, arquivo))}  {arquivo}\n")

    zip_path = pasta + ".zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for arquivo in sorted(os.listdir(pasta)):
            z.write(os.path.join(pasta, arquivo), arcname=f"{nome}/{arquivo}")

    print(f"Pacote: {pasta}")
    print(f"Zip:    {zip_path} ({os.path.getsize(zip_path) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
