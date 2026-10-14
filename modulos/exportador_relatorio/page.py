"""
Tela do Exportador de Relatório dentro do hub do MegaQG Vivo.

Une as duas versões que existiam: a deste repositório (1 por dia / período único,
todas ou só canceladas, cancelar no meio do bloco) e o card do QG NFCom v2.3
(XML em Produção ou Homologação, período consolidado com dia inicial e final).
O ambiente do XML é o ambiente global escolhido no topo do app.
"""
import calendar
import logging
import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from core import config
from core.logging_utils import add_queue_handler, setup_logging
from modulos.exportador_relatorio.runner import (
    MODO_DIARIO,
    MODO_PERIODO,
    dias_validos_no_range,
    montar_periodos,
    rodar_exportacao,
)
from ui.theme import COLORS, misturar
from ui.widgets import ScrolledText, _open_folder, back_button, stat_box

MESES = [
    "01 - Janeiro", "02 - Fevereiro", "03 - Março", "04 - Abril",
    "05 - Maio", "06 - Junho", "07 - Julho", "08 - Agosto",
    "09 - Setembro", "10 - Outubro", "11 - Novembro", "12 - Dezembro",
]

TAG_POR_NIVEL = {
    logging.DEBUG: "INFO",
    logging.INFO: "INFO",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "ERROR",
}


class ExportadorRelatorioPage(tk.Frame):
    LIMITE_LINHAS_LOG = 5000  # a tela guarda só as últimas N linhas; o .log tem tudo

    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLORS["bg"])
        self.controller = controller

        self.event_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.relatorios = (0, 0)  # (concluídos, total) da execução atual

        hoje = datetime.now()
        self.pasta_saida_var = tk.StringVar(value=config.pasta_saida_padrao())
        self.modo_var = tk.StringVar(value=MODO_DIARIO)
        self.status_var = tk.StringVar(value="todas")
        self.ano_var = tk.StringVar(value=str(hoje.year))
        self.mes_var = tk.StringVar(value=MESES[hoje.month - 1])
        self.mes_inteiro_var = tk.BooleanVar(value=True)
        self.dia_ini_var = tk.StringVar(value="1")
        self.dia_fim_var = tk.StringVar(value="31")
        self.xml_var = tk.BooleanVar(value=True)

        self.count_labels = {}

        back_button(self, controller, "📄 Exportador de Relatório", "CSV de NFCom direto do banco")
        self._build_ui()
        self._atualizar_dias()
        self.controller.ambiente_var.trace_add("write", lambda *_: self._atualizar_resumo())
        self._poll_queue()

    # ------------------------------------------------------------------ layout
    def _build_ui(self):
        pad = {"padx": 18, "pady": 6}

        cfg = ttk.LabelFrame(self, text="PARÂMETROS")
        cfg.pack(fill="x", **pad)
        body = tk.Frame(cfg, bg=COLORS["panel"])
        body.pack(fill="x", padx=10, pady=10)
        body.grid_columnconfigure(0, weight=1)

        ttk.Label(body, text="Pasta de saída dos relatórios", style="PanelMuted.TLabel").grid(row=0, column=0, sticky="w")
        linha = tk.Frame(body, bg=COLORS["panel"])
        linha.grid(row=1, column=0, sticky="ew", pady=(2, 10))
        ttk.Entry(linha, textvariable=self.pasta_saida_var).pack(side="left", fill="x", expand=True)
        ttk.Button(linha, text="Procurar...", command=self._browse_pasta).pack(side="left", padx=(6, 0))

        self._segmento(body, 2, "Tipo de relatório", self.modo_var, [
            (MODO_DIARIO, "📅  1 relatório por DIA", "Um arquivo por dia, cada um na pasta do dia"),
            (MODO_PERIODO, "🗓  1 relatório ÚNICO para o período", "Uma consulta só: mês inteiro ou dia X a Y"),
        ])
        self._segmento(body, 4, "Notas", self.status_var, [
            ("todas", "Todas as notas", "Status 6, 9 e 10"),
            ("canceladas", "Somente CANCELADAS", "Status 9 (arquivo com prefixo canceladas_)"),
        ])

        periodo = tk.Frame(body, bg=COLORS["panel"])
        periodo.grid(row=6, column=0, sticky="ew")

        ttk.Label(periodo, text="Ano", style="PanelMuted.TLabel").grid(row=0, column=0, sticky="w")
        ano = ttk.Spinbox(periodo, from_=2015, to=2100, textvariable=self.ano_var, width=7,
                          command=self._atualizar_dias)
        ano.grid(row=1, column=0, sticky="w", padx=(0, 16))
        ano.bind("<KeyRelease>", lambda _e: self._atualizar_dias())

        ttk.Label(periodo, text="Mês", style="PanelMuted.TLabel").grid(row=0, column=1, sticky="w")
        mes = ttk.Combobox(periodo, textvariable=self.mes_var, values=MESES, state="readonly", width=14)
        mes.grid(row=1, column=1, sticky="w", padx=(0, 16))
        mes.bind("<<ComboboxSelected>>", lambda _e: self._atualizar_dias())

        ttk.Label(periodo, text="Dia inicial", style="PanelMuted.TLabel").grid(row=0, column=2, sticky="w")
        self.sp_dia_ini = ttk.Spinbox(periodo, from_=1, to=31, textvariable=self.dia_ini_var, width=5,
                                      command=self._atualizar_resumo)
        self.sp_dia_ini.grid(row=1, column=2, sticky="w", padx=(0, 16))
        ttk.Label(periodo, text="Dia final", style="PanelMuted.TLabel").grid(row=0, column=3, sticky="w")
        self.sp_dia_fim = ttk.Spinbox(periodo, from_=1, to=31, textvariable=self.dia_fim_var, width=5,
                                      command=self._atualizar_resumo)
        self.sp_dia_fim.grid(row=1, column=3, sticky="w", padx=(0, 16))
        for sp in (self.sp_dia_ini, self.sp_dia_fim):
            sp.bind("<KeyRelease>", lambda _e: self._atualizar_resumo())

        ttk.Checkbutton(periodo, text="Todos os dias do mês", variable=self.mes_inteiro_var,
                        command=self._atualizar_dias).grid(row=1, column=4, sticky="w", padx=(0, 16))
        ttk.Checkbutton(periodo, text="Baixar XML das notas (coluna extra)", variable=self.xml_var,
                        command=self._atualizar_resumo).grid(row=1, column=5, sticky="w")

        self.resumo_lbl = tk.Label(body, text="", bg=COLORS["panel"], fg=COLORS["success"],
                                   font=("Segoe UI", 10, "bold"), anchor="w", justify="left")
        self.resumo_lbl.grid(row=7, column=0, sticky="ew", pady=(12, 0))

        controls = tk.Frame(self, bg=COLORS["bg"])
        controls.pack(fill="x", **pad)
        self.start_btn = ttk.Button(controls, text="▶  Iniciar Exportação", style="Success.TButton",
                                    command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(controls, text="■  Parar", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Abrir pasta de saída", command=self._abrir_saida).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Abrir pasta de logs", command=self._abrir_logs).pack(side="left", padx=(8, 0))

        progress_frame = ttk.LabelFrame(self, text="PROGRESSO")
        progress_frame.pack(fill="x", **pad)
        pbody = tk.Frame(progress_frame, bg=COLORS["panel"])
        pbody.pack(fill="x", padx=10, pady=10)
        self.progress_bar = ttk.Progressbar(pbody, style="Success.Horizontal.TProgressbar", maximum=100, value=0)
        self.progress_bar.pack(fill="x", side="left", expand=True)
        self.progress_label = ttk.Label(pbody, text="0 / 0", style="Panel.TLabel", width=12, anchor="e")
        self.progress_label.pack(side="left", padx=(8, 0))

        stats = tk.Frame(progress_frame, bg=COLORS["panel"])
        stats.pack(fill="x", padx=10, pady=(0, 10))
        for key, label, color in [("ok", "RELATÓRIOS OK", COLORS["success"]),
                                  ("erro", "FALHAS", COLORS["danger"]),
                                  ("linhas", "LINHAS NO RELATÓRIO ATUAL", COLORS["fg"])]:
            box, val = stat_box(stats, label, color)
            box.pack(side="left", padx=(0, 10))
            self.count_labels[key] = val

        log_frame = ttk.LabelFrame(self, text="LOG DE EXECUÇÃO")
        log_frame.pack(fill="both", expand=True, **pad)
        self.log_text = ScrolledText(log_frame, height=8, state="disabled",
                                                  font=("Consolas", 9), bg=COLORS["card"],
                                                  fg=COLORS["fg"], insertbackground=COLORS["fg"],
                                                  borderwidth=0, highlightthickness=0)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
        self.log_text.tag_config("OK", foreground=COLORS["success"])
        self.log_text.tag_config("INFO", foreground=COLORS["fg_muted"])
        self.log_text.tag_config("WARN", foreground=COLORS["warning"])
        self.log_text.tag_config("ERROR", foreground=COLORS["danger"])

    def _segmento(self, parent, row, titulo, variavel, opcoes):
        """Botões lado a lado, só um ativo (destacado): deixa a escolha bem visível."""
        ttk.Label(parent, text=titulo, style="PanelMuted.TLabel").grid(row=row, column=0, sticky="w")
        linha = tk.Frame(parent, bg=COLORS["panel"])
        linha.grid(row=row + 1, column=0, sticky="ew", pady=(2, 10))
        for i, (valor, titulo_opcao, detalhe) in enumerate(opcoes):
            tk.Radiobutton(
                linha, text=f"{titulo_opcao}\n{detalhe}", variable=variavel, value=valor,
                indicatoron=0, command=self._atualizar_dias, justify="left", anchor="w",
                font=("Segoe UI", 10), padx=14, pady=7,
                bg=COLORS["card"], fg=COLORS["fg"], selectcolor=misturar(COLORS["success"], COLORS["card"], 0.28),
                activebackground=COLORS["accent_soft"], activeforeground=COLORS["fg"],
                relief="flat", bd=0, highlightthickness=1, highlightbackground=COLORS["card_border"],
                cursor="hand2",
            ).grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
            linha.grid_columnconfigure(i, weight=1, uniform="seg")

    # ------------------------------------------------------------- período
    def _ano_mes(self):
        try:
            ano = int(self.ano_var.get())
        except ValueError:
            ano = datetime.now().year
        return ano, int(self.mes_var.get().split(" - ")[0])

    def _atualizar_dias(self):
        ano, mes = self._ano_mes()
        try:
            ultimo = calendar.monthrange(ano, mes)[1]
        except Exception:
            return
        for sp in (self.sp_dia_ini, self.sp_dia_fim):
            sp.configure(to=ultimo)
        if self.mes_inteiro_var.get():
            self.dia_ini_var.set("1")
            self.dia_fim_var.set(str(ultimo))
        estado = "disabled" if self.mes_inteiro_var.get() else "normal"
        self.sp_dia_ini.configure(state=estado)
        self.sp_dia_fim.configure(state=estado)
        self._atualizar_resumo()

    def _parametros(self):
        ano, mes = self._ano_mes()
        dia_ini, dia_fim = int(self.dia_ini_var.get()), int(self.dia_fim_var.get())
        return ano, mes, dia_ini, dia_fim

    def _atualizar_resumo(self):
        """Frase que diz exatamente o que vai ser gerado (muda com cada escolha)."""
        try:
            ano, mes, dia_ini, dia_fim = self._parametros()
            periodos = montar_periodos(self.modo_var.get(), ano, mes, dia_ini, dia_fim)
        except (ValueError, KeyError):
            self.resumo_lbl.configure(text="Verifique ano, mês e dias.", fg=COLORS["danger"])
            return
        if not periodos:
            self.resumo_lbl.configure(text="Nenhum dia válido no período.", fg=COLORS["danger"])
            return
        quais = "somente CANCELADAS (status 9)" if self.status_var.get() == "canceladas" else "todas as notas (6, 9, 10)"
        if self.modo_var.get() == MODO_PERIODO:
            oque = f"1 arquivo único para {periodos[0]['rotulo']}"
        else:
            oque = f"{len(periodos)} arquivo(s), 1 por dia ({periodos[0]['rotulo']} a {periodos[-1]['rotulo']})"
        xml = f"com XML ({self.controller.ambiente_var.get()})" if self.xml_var.get() else "sem XML"
        self.resumo_lbl.configure(text=f"Vai gerar: {oque} · {quais} · {xml}", fg=COLORS["success"])

    # ------------------------------------------------------------- ações
    def _browse_pasta(self):
        path = filedialog.askdirectory(title="Selecione a pasta de saída dos relatórios",
                                       initialdir=self.pasta_saida_var.get() or None)
        if path:
            self.pasta_saida_var.set(path)

    def _abrir_saida(self):
        pasta = self.pasta_saida_var.get().strip()
        if pasta:
            os.makedirs(pasta, exist_ok=True)
            _open_folder(pasta)

    def _abrir_logs(self):
        os.makedirs(config.log_dir(), exist_ok=True)
        _open_folder(config.log_dir())

    def _start(self):
        pasta = self.pasta_saida_var.get().strip()
        if not pasta:
            messagebox.showwarning("Pasta obrigatória", "Escolha a pasta de saída dos relatórios.")
            return
        try:
            ano, mes, dia_ini, dia_fim = self._parametros()
        except ValueError:
            messagebox.showwarning("Entrada inválida", "Verifique ano, mês e dias.")
            return
        if dia_ini > dia_fim:
            messagebox.showwarning("Período inválido", "O dia inicial não pode ser maior que o dia final.")
            return
        if not dias_validos_no_range(ano, mes, dia_ini, dia_fim):
            messagebox.showwarning("Nada a exportar", "Nenhum dia válido no período selecionado.")
            return
        if not messagebox.askyesno("Confirmar exportação", self.resumo_lbl.cget("text") + "\n\nIniciar?"):
            return

        try:
            os.makedirs(pasta, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Pasta inválida", f"Não foi possível usar essa pasta:\n{e}")
            return

        self.stop_event = threading.Event()
        for label in self.count_labels.values():
            label["text"] = "0"
        self.progress_bar.configure(value=0, maximum=1)
        self.progress_label["text"] = "0 / 0"
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.start_btn["state"] = "disabled"
        self.stop_btn["state"] = "normal"

        log_file = setup_logging(config.log_dir(), nome_execucao="exportador-relatorio-log", console=False)
        add_queue_handler(self.event_queue)
        self._append_log(f"Log desta execução: {log_file}", "INFO")

        kwargs = dict(
            output_base_path=pasta,
            progress_callback=lambda i, total, rotulo: self.event_queue.put(("__progress__", (i, total))),
            progress_linhas_callback=lambda linhas, rotulo: self.event_queue.put(("__linhas__", linhas)),
            deve_cancelar=self.stop_event.is_set,
            baixar_xml=self.xml_var.get(),
            modo=self.modo_var.get(),
            filtro_status=self.status_var.get(),
            ambiente_xml=self.controller.ambiente_var.get(),
        )
        self.worker_thread = threading.Thread(target=self._executar, args=(ano, mes, dia_ini, dia_fim, kwargs),
                                              daemon=True)
        self.worker_thread.start()

    def _executar(self, ano, mes, dia_ini, dia_fim, kwargs):
        try:
            resultado = rodar_exportacao(ano, mes, dia_ini, dia_fim, **kwargs)
        except Exception as e:
            logging.error(f"Erro inesperado durante a execução: {e}")
            resultado = {"sucesso": [], "falhas": [], "total": 0, "cancelado": False}
        self.event_queue.put(("__done__", resultado))

    def _stop(self):
        self.stop_event.set()
        self.stop_btn["state"] = "disabled"
        self._append_log("Parada solicitada: aguardando o bloco atual terminar...", "WARN")

    # ------------------------------------------------------------- eventos
    def _poll_queue(self):
        linhas = []
        try:
            for _ in range(300):  # protege a tela numa rajada de logs
                item = self.event_queue.get_nowait()
                if item[0] == "__progress__":
                    feitos, total = item[1]
                    self.progress_bar.configure(value=feitos, maximum=max(total, 1))
                    self.progress_label["text"] = f"{feitos} / {total}"
                elif item[0] == "__linhas__":
                    self.count_labels["linhas"]["text"] = f"{item[1]:,}".replace(",", ".")
                elif item[0] == "__done__":
                    self._finalizar(item[1])
                else:
                    nivel, msg = item
                    linhas.append((msg, TAG_POR_NIVEL.get(nivel, "INFO")))
        except queue.Empty:
            pass
        finally:
            if linhas:
                self._escrever_log(linhas)
            self.after(120, self._poll_queue)

    def _finalizar(self, resultado):
        self.start_btn["state"] = "normal"
        self.stop_btn["state"] = "disabled"
        sucesso, falhas = resultado.get("sucesso", []), resultado.get("falhas", [])
        self.count_labels["ok"]["text"] = str(len(sucesso))
        self.count_labels["erro"]["text"] = str(len(falhas))
        if resultado.get("cancelado"):
            self._append_log(f"Cancelado. {len(sucesso)} relatório(s) gerado(s).", "WARN")
        elif falhas:
            messagebox.showwarning("Concluído com falhas",
                                   f"{len(sucesso)} relatório(s) gerado(s).\n{len(falhas)} falharam:\n"
                                   + ", ".join(falhas))
        elif sucesso:
            messagebox.showinfo("Concluído", f"{len(sucesso)} relatório(s) exportado(s) com sucesso.")
        else:
            messagebox.showerror("Não executado", "Nenhum relatório gerado. Veja o log de execução.")

    def _append_log(self, text, status):
        ts = datetime.now().strftime("%H:%M:%S")
        self._escrever_log([(f"{ts} | {text}", status)])

    def _escrever_log(self, itens):
        self.log_text.configure(state="normal")
        for texto, tag in itens:
            self.log_text.insert("end", texto + "\n", tag)
        total = int(self.log_text.index("end-1c").split(".")[0])
        if total > self.LIMITE_LINHAS_LOG:
            self.log_text.delete("1.0", f"{total - self.LIMITE_LINHAS_LOG + 1}.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
