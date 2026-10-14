"""Engine portada do MEGA QG VIVO NFSe v2.0 (legado/NFSe/qg.py); só a URL passou a vir do config.json."""
from modulos.nfse.comum import *  # noqa: F401,F403 - imports do QG original


class ExpandirDpsCsvEngine:
    """
    Transcrição do script PowerShell que, apesar do apelido "concatenador",
    faz o inverso: pega um CSV (ex.: a planilha do Relatório DPS sem
    Endereço, já exportada e preenchida com o endereço) onde uma coluna
    (por padrão "DPS") pode conter vários valores separados por vírgula --
    exatamente o formato que o Relatório DPS sem Endereço gera ao agrupar
    por cliente -- e "explode" cada linha em uma linha por valor, duplicando
    as demais colunas em cada uma. Resultado: um CSV pronto pra reprocessar
    DPS a DPS.
    """

    def __init__(self, event_queue, stop_event, *, arquivo_entrada, arquivo_saida,
                 delimitador, coluna, encoding_entrada, log_dir):
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.arquivo_entrada = arquivo_entrada
        self.arquivo_saida = arquivo_saida
        self.delimitador = delimitador
        self.coluna = coluna
        self.encoding_entrada = encoding_entrada
        self.log_dir = log_dir
        self.log_file = None

    def emit(self, kind, **data):
        self.event_queue.put({"kind": kind, **data})

    def emit_log(self, text, status="INFO"):
        self.emit("log_line", text=text, status=status)

    def _garantir_log(self):
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "expandir_dps_csv_log_nfse.txt")

    def _log_arquivo(self, msg):
        ts = datetime.now().isoformat()
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")

    def run(self):
        try:
            self._garantir_log()
            self._log_arquivo(
                f"INICIO | entrada={self.arquivo_entrada} | saida={self.arquivo_saida} | "
                f"coluna={self.coluna} | delimitador={self.delimitador!r} | "
                f"encoding={self.encoding_entrada}")

            with open(self.arquivo_entrada, encoding=self.encoding_entrada, newline="") as f:
                reader = csv.DictReader(f, delimiter=self.delimitador)
                fieldnames = reader.fieldnames
                linhas = list(reader)

            if not fieldnames:
                self._log_arquivo("ERRO | não foi possível ler o cabeçalho do CSV")
                self.emit("fatal_error", text="Não foi possível ler o cabeçalho do CSV.")
                return
            if self.coluna not in fieldnames:
                self._log_arquivo(f"ERRO | coluna '{self.coluna}' não encontrada")
                self.emit("fatal_error", text=(
                    f"Coluna \"{self.coluna}\" não encontrada. Colunas disponíveis: "
                    f"{', '.join(fieldnames)}"))
                return

            total = len(linhas)
            self.emit("total_itens", n=total)
            self.emit_log(f"{total} linha(s) lida(s) de {self.arquivo_entrada}.", "INFO")

            resultado = []
            done = 0
            for linha in linhas:
                if self.stop_event.is_set():
                    self._log_arquivo("CANCELADO pelo usuário")
                    self.emit("done", cancelled=True)
                    return

                valor = (linha.get(self.coluna) or "").strip()
                lista = [v.strip() for v in valor.split(",")] if valor else [""]
                for v in lista:
                    nova_linha = dict(linha)
                    nova_linha[self.coluna] = v
                    resultado.append(nova_linha)

                done += 1
                self.emit("progress", done=done, total=total)

            pasta_saida = os.path.dirname(os.path.abspath(self.arquivo_saida))
            os.makedirs(pasta_saida, exist_ok=True)
            with open(self.arquivo_saida, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=self.delimitador)
                writer.writeheader()
                writer.writerows(resultado)

            self._log_arquivo(f"OK | {total} linha(s) de entrada -> {len(resultado)} linha(s) de saída")
            self.emit_log(f"{len(resultado)} linha(s) gerada(s) em {self.arquivo_saida}.", "OK")
            self.emit("done", cancelled=False, linhas_entrada=total, linhas_saida=len(resultado),
                       arquivo=self.arquivo_saida, log_file=str(self.log_file))
        except Exception as e:
            if self.log_file:
                self._log_arquivo(f"ERRO FATAL | {e}")
            self.emit("fatal_error", text=str(e))
