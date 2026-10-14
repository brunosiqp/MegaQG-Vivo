import calendar
import sys

from core import config
from core.logging_utils import setup_logging
from modulos.exportador_relatorio.runner import MODO_DIARIO, MODO_PERIODO, rodar_exportacao
from core.ui_helpers import escolher_pasta


def pedir_ano() -> int:
    while True:
        entrada = input("Ano a exportar (ex: 2026): ").strip()
        if entrada.isdigit() and 2000 <= int(entrada) <= 2100:
            return int(entrada)
        print("Ano inválido. Digite um ano com 4 dígitos, ex: 2026.")


def pedir_mes() -> int:
    while True:
        entrada = input("Mês a exportar (1-12): ").strip()
        if entrada.isdigit() and 1 <= int(entrada) <= 12:
            return int(entrada)
        print("Mês inválido. Digite um número entre 1 e 12.")


def pedir_baixar_xml() -> bool:
    while True:
        entrada = input("Baixar XML das notas (coluna extra)? [S/n]: ").strip().lower()
        if entrada in ("", "s", "sim"):
            return True
        if entrada in ("n", "nao", "não"):
            return False
        print("Resposta inválida. Digite S ou N.")


def pedir_modo() -> str:
    while True:
        entrada = input("Tipo de relatório: [D] 1 por dia / [M] 1 para o mês inteiro [D]: ").strip().lower()
        if entrada in ("", "d", "dia"):
            return MODO_DIARIO
        if entrada in ("m", "mes", "mês"):
            return MODO_PERIODO
        print("Resposta inválida. Digite D ou M.")


def pedir_filtro_status() -> str:
    while True:
        entrada = input("Notas: [T] todas (6, 9, 10) / [C] somente canceladas (9) [T]: ").strip().lower()
        if entrada in ("", "t", "todas"):
            return "todas"
        if entrada in ("c", "canceladas"):
            return "canceladas"
        print("Resposta inválida. Digite T ou C.")


def pedir_pasta_saida() -> str:
    print("Selecione a pasta de saída dos relatórios (abrindo janela)...")
    pasta = escolher_pasta("Selecione a pasta de saída dos relatórios", config.pasta_saida_padrao())
    if not pasta:
        print(f"Nenhuma pasta selecionada - usando padrão: {config.pasta_saida_padrao()}")
        return config.pasta_saida_padrao()
    return pasta


def main():
    log_file = setup_logging(config.log_dir(), nome_execucao="megaqg-exportador-relatorio-log")

    print("=== MegaQG Vivo - Exportador de Relatório ===")

    pasta_saida = pedir_pasta_saida()
    ano = pedir_ano()
    mes = pedir_mes()
    modo = pedir_modo()
    filtro_status = pedir_filtro_status()
    baixar_xml = pedir_baixar_xml()
    ultimo_dia_mes = calendar.monthrange(ano, mes)[1]

    resultado = rodar_exportacao(
        ano, mes, 1, ultimo_dia_mes,
        output_base_path=pasta_saida,
        baixar_xml=baixar_xml,
        modo=modo,
        filtro_status=filtro_status,
    )

    print(f"\nLog completo salvo em: {log_file}")
    input("\nPressione ENTER para sair...")

    if resultado["falhas"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
