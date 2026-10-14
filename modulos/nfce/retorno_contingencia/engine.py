"""
Retorno de Contingência NFCe (piloto): grava comandos na COMANDO_NFEPACK para as notas
de um arquivo de chaves (A_ID), como autorizadas ou como rejeitadas.

O INSERT é o mesmo usado manualmente pela equipe (documentação interna do piloto), com três
proteções a mais:
  - prévia somente leitura antes de gravar (o que será inserido, o que não existe, etc.);
  - trava de status: "autorizada" só grava notas com IND_STATUS_NFE = 6 e "rejeitada"
    só com 8 (pode ser desligada);
  - não grava de novo um comando igual que ainda esteja pendente (STATUS_COMAND = '0').

Fluxo: previa(arquivo) -> gravar(simular=True/False). Cada etapa abre a própria conexão.
Gravação em blocos de até 1.000 chaves, uma transação por bloco. Na simulação, cada bloco
executa o INSERT e faz ROLLBACK (nada fica gravado).

Não depende de Tkinter: conversa com a tela por event_queue, como as demais engines.
"""
import os
import threading
from datetime import datetime

from core.config import AMBIENTE_PRD
from core.database import sql_conn
from modulos.nfce.comum import carregar_temp, db_config_nfce, ler_chaves

TIPOS = {
    "autorizada": {"rotulo": "Autorizada", "dsc": "RetornoContingencia_Autorizada", "status_nfe": 6},
    "rejeitada": {"rotulo": "Rejeitada", "dsc": "RetornoContingencia_Rejeitada", "status_nfe": 8},
}
IND_ACAO = 10  # COMANDO_NFEPACK.IND_ACAO é int
STATUS_COMAND_PENDENTE = 0  # COMANDO_NFEPACK.STATUS_COMAND é int
SUFIXO_USUARIO = "nfepackadm"
TAMANHO_BLOCO = 1000

# Situações da prévia
SERA_INSERIDA = "SERA_INSERIDA"
NAO_ENCONTRADA = "NAO_ENCONTRADA"
STATUS_DIVERGENTE = "STATUS_DIVERGENTE"
JA_PENDENTE = "JA_PENDENTE"

# Mesmo comando já pendente para a mesma nota (evita gravar duplicado)
_JA_PENDENTE = """EXISTS (
        SELECT 1 FROM COMANDO_NFEPACK P
        WHERE P.IND_ACAO = ?
          AND P.STATUS_COMAND = ?
          AND P.NUM_CNPJ_EMISSOR = I.NUM_CNPJ_ESTAB_GERDOR
          AND P.NUM_SERIE_DOCTO_FISCAL = I.NUM_SERIE_DOCTO_FISCAL
          AND P.NUM_DOCTO_FISCAL = I.NUM_DOCTO_FISCAL
          AND P.DSC_PARAM = CAST(I.NUM_SEQ_NFE AS varchar) + ?
    )"""

SQL_PREVIA = f"""
SELECT C.A_ID,
       I.IND_STATUS_NFE,
       CASE
           WHEN I.A_ID IS NULL THEN '{NAO_ENCONTRADA}'
           WHEN ? = 1 AND (I.IND_STATUS_NFE IS NULL OR I.IND_STATUS_NFE <> ?) THEN '{STATUS_DIVERGENTE}'
           WHEN {_JA_PENDENTE} THEN '{JA_PENDENTE}'
           ELSE '{SERA_INSERIDA}'
       END AS SITUACAO
FROM #chaves C
LEFT JOIN INTERF_NFE I
       ON I.A_ID = C.A_ID
      AND I.IND_TIPO_PROCES = 'E'
"""

SQL_INSERT_BLOCO = f"""
INSERT INTO COMANDO_NFEPACK (IND_ACAO, STATUS_COMAND, NUM_CNPJ_EMISSOR, NUM_SERIE_DOCTO_FISCAL,
                             NUM_DOCTO_FISCAL, DAT_HOR_AGEN_COMAND, DSC_PARAM)
SELECT ?,
       ?,
       I.NUM_CNPJ_ESTAB_GERDOR,
       I.NUM_SERIE_DOCTO_FISCAL,
       I.NUM_DOCTO_FISCAL,
       GETDATE(),
       CAST(I.NUM_SEQ_NFE AS varchar) + ?
FROM INTERF_NFE I
JOIN #bloco B ON B.A_ID = I.A_ID
WHERE I.IND_TIPO_PROCES = 'E'
  AND (? = 0 OR I.IND_STATUS_NFE = ?)
  AND NOT {_JA_PENDENTE}
"""


def dsc_param_sufixo(tipo: str) -> str:
    """Parte fixa do DSC_PARAM (o banco prefixa com NUM_SEQ_NFE)."""
    return f"|{TIPOS[tipo]['dsc']}|{SUFIXO_USUARIO}"


class RetornoContingenciaEngine:
    def __init__(self, event_queue, stop_event, *, tipo, ambiente=AMBIENTE_PRD, exigir_status=True,
                 log_dir, conectar=None):
        if tipo not in TIPOS:
            raise ValueError(f"tipo inválido: {tipo}")
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.tipo = tipo
        self.ambiente = ambiente
        self.exigir_status = exigir_status
        self.log_dir = log_dir
        # conectar() -> conexão pyodbc; injetável nos testes
        self.conectar = conectar or (lambda: sql_conn(db_config_nfce(self.ambiente)))
        self.log_lock = threading.Lock()
        self.log_file = None
        self.leitura = None
        self.situacoes = {}  # A_ID -> situação da prévia

    # ---------------------------------------------------------------- eventos/log
    def emit(self, kind, **data):
        self.event_queue.put({"kind": kind, **data})

    def emit_log(self, text, status="INFO"):
        self._log_arquivo(f"{status:<5} | {text}")
        self.emit("log_line", text=text, status=status)

    def _log_arquivo(self, linha):
        if not self.log_file:
            os.makedirs(self.log_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            self.log_file = os.path.join(self.log_dir, f"nfce-retorno-{self.tipo}_{ts}.log")
        with self.log_lock, open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | {linha}\n")

    # --------------------------------------------------------------------- helpers
    _carregar_temp = staticmethod(carregar_temp)

    def _parametros_pendente(self):
        return [IND_ACAO, STATUS_COMAND_PENDENTE, dsc_param_sufixo(self.tipo)]

    def lista(self, situacao):
        return [c for c, s in self.situacoes.items() if s == situacao]

    # ---------------------------------------------------------------------- prévia
    def previa(self, arquivo):
        """Lê o arquivo e consulta o banco (somente leitura). Emite 'previa' com as contagens."""
        try:
            self.leitura = ler_chaves(arquivo)
            validas = self.leitura["validas"]
            self.emit_log(
                f"Arquivo: {len(validas)} chave(s) válida(s), {len(self.leitura['invalidas'])} inválida(s), "
                f"{self.leitura['duplicadas']} repetida(s) ignorada(s).", "INFO")
            if not validas:
                self.emit("fatal_error", text="Nenhuma chave válida no arquivo (A_ID com 44 dígitos).")
                return
            self.emit_log(f"Consultando {len(validas)} chave(s) no banco ({self.ambiente})...", "INFO")
            conn = self.conectar()
            try:
                cur = conn.cursor()
                self._carregar_temp(cur, "#chaves", validas)
                status = TIPOS[self.tipo]["status_nfe"]
                cur.execute(SQL_PREVIA, [1 if self.exigir_status else 0, status] + self._parametros_pendente())
                linhas = cur.fetchall()
            finally:
                conn.rollback()
                conn.close()

            # Uma chave pode ter mais de uma linha em INTERF_NFE: prevalece "será inserida"
            prioridade = {SERA_INSERIDA: 0, JA_PENDENTE: 1, STATUS_DIVERGENTE: 2, NAO_ENCONTRADA: 3}
            self.situacoes, linhas_por_chave = {}, {}
            for a_id, _status, situacao in linhas:
                atual = self.situacoes.get(a_id)
                if atual is None or prioridade[situacao] < prioridade[atual]:
                    self.situacoes[a_id] = situacao
                if situacao == SERA_INSERIDA:
                    linhas_por_chave[a_id] = linhas_por_chave.get(a_id, 0) + 1
            multiplas = sum(1 for n in linhas_por_chave.values() if n > 1)
            if multiplas:
                self.emit_log(f"{multiplas} chave(s) têm mais de uma linha em INTERF_NFE: o INSERT gera um "
                              f"comando por linha, como no SQL manual.", "WARN")

            contagem = {s: len(self.lista(s)) for s in prioridade}
            self.emit_log(
                f"Prévia: {contagem[SERA_INSERIDA]} serão inserida(s), {contagem[NAO_ENCONTRADA]} não encontrada(s), "
                f"{contagem[STATUS_DIVERGENTE]} com status divergente, {contagem[JA_PENDENTE]} já pendente(s).",
                "OK" if contagem[SERA_INSERIDA] else "WARN")
            self.emit("previa", invalidas=len(self.leitura["invalidas"]), duplicadas=self.leitura["duplicadas"],
                      validas=len(validas), comandos=sum(linhas_por_chave.values()), **contagem)
        except Exception as e:
            self.emit_log(f"Falha na prévia: {e}", "ERROR")
            self.emit("fatal_error", text=str(e))

    # --------------------------------------------------------------------- gravar
    def gravar(self, simular, pasta_saida):
        """Executa o INSERT para as chaves "será inserida" da última prévia, em blocos.
        simular=True: cada bloco faz ROLLBACK (nada fica gravado)."""
        modo = "SIMULAÇÃO" if simular else "GRAVAÇÃO"
        try:
            chaves = self.lista(SERA_INSERIDA)
            blocos = [chaves[i:i + TAMANHO_BLOCO] for i in range(0, len(chaves), TAMANHO_BLOCO)]
            self.emit("total_itens", n=len(chaves))
            self.emit_log(f"{modo}: {len(chaves)} chave(s) em {len(blocos)} bloco(s) "
                          f"(DSC_PARAM <NUM_SEQ_NFE>{dsc_param_sufixo(self.tipo)}).", "INFO")
            status = TIPOS[self.tipo]["status_nfe"]
            parametros = ([IND_ACAO, STATUS_COMAND_PENDENTE, dsc_param_sufixo(self.tipo),
                           1 if self.exigir_status else 0, status] + self._parametros_pendente())
            inseridas, com_erro, linhas_inseridas, feitas = [], [], 0, 0

            conn = self.conectar()
            try:
                cur = conn.cursor()
                for n, bloco in enumerate(blocos, start=1):
                    if self.stop_event.is_set():
                        self.emit_log("Parada solicitada: blocos seguintes não foram executados.", "WARN")
                        break
                    try:
                        self._carregar_temp(cur, "#bloco", bloco)
                        cur.execute(SQL_INSERT_BLOCO, parametros)
                        afetadas = max(cur.rowcount, 0)
                        if simular:
                            conn.rollback()
                        else:
                            conn.commit()
                        inseridas += bloco
                        linhas_inseridas += afetadas
                        self.emit_log(f"Bloco {n}/{len(blocos)}: {afetadas} comando(s) "
                                      f"{'seriam gravados' if simular else 'gravados'}.", "OK")
                    except Exception as e:
                        conn.rollback()
                        com_erro += bloco
                        self.emit_log(f"Bloco {n}/{len(blocos)} falhou e foi desfeito: {e}", "ERROR")
                    feitas += len(bloco)
                    self.emit("counts", done=feitas, total=len(chaves), inseridas=linhas_inseridas,
                              erro=len(com_erro))
            finally:
                conn.close()

            pasta = self._gravar_resultado(pasta_saida, simular, inseridas, com_erro, linhas_inseridas)
            self.emit("done", cancelled=self.stop_event.is_set(), simular=simular, inseridas=linhas_inseridas,
                      erro=len(com_erro), pasta=pasta, log_file=str(self.log_file))
        except Exception as e:
            self.emit_log(f"Falha na {modo.lower()}: {e}", "ERROR")
            self.emit("fatal_error", text=str(e))

    def _gravar_resultado(self, pasta_saida, simular, inseridas, com_erro, linhas_inseridas):
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        pasta = os.path.join(pasta_saida, f"retorno_{self.tipo}_{'simulacao_' if simular else ''}{ts}")
        os.makedirs(pasta, exist_ok=True)
        listas = {
            "inseridas.txt" if not simular else "seriam_inseridas.txt": inseridas,
            "nao_encontradas.txt": self.lista(NAO_ENCONTRADA),
            "status_divergente.txt": self.lista(STATUS_DIVERGENTE),
            "ja_pendentes.txt": self.lista(JA_PENDENTE),
            "invalidas.txt": self.leitura["invalidas"] if self.leitura else [],
            "erro.txt": com_erro,
        }
        for nome, chaves in listas.items():
            if chaves:
                with open(os.path.join(pasta, nome), "w", encoding="utf-8") as f:
                    f.write("\n".join(chaves) + "\n")
        resumo = [
            f"Operação: Retorno de Contingência NFCe - {TIPOS[self.tipo]['rotulo']}",
            f"Modo: {'SIMULAÇÃO (nada foi gravado)' if simular else 'GRAVAÇÃO'}",
            f"Ambiente: {self.ambiente}",
            f"IND_ACAO: {IND_ACAO} | STATUS_COMAND: {STATUS_COMAND_PENDENTE} | "
            f"DSC_PARAM: <NUM_SEQ_NFE>{dsc_param_sufixo(self.tipo)}",
            f"Trava de status (IND_STATUS_NFE = {TIPOS[self.tipo]['status_nfe']}): "
            f"{'ligada' if self.exigir_status else 'desligada'}",
            f"Usuário do Windows: {os.environ.get('USERNAME', '?')}",
            f"Data/hora: {datetime.now():%d/%m/%Y %H:%M:%S}",
            "",
            f"Comandos {'que seriam gravados' if simular else 'gravados'}: {linhas_inseridas}",
            f"Chaves processadas: {len(inseridas)} | com erro: {len(com_erro)}",
            f"Não encontradas: {len(listas['nao_encontradas.txt'])} | status divergente: "
            f"{len(listas['status_divergente.txt'])} | já pendentes: {len(listas['ja_pendentes.txt'])} | "
            f"inválidas: {len(listas['invalidas.txt'])}",
            f"Log: {self.log_file}",
        ]
        with open(os.path.join(pasta, "resumo.txt"), "w", encoding="utf-8-sig") as f:
            f.write("\n".join(resumo) + "\n")
        return pasta
