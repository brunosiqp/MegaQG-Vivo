from datetime import datetime

from clientes.vivo.config import STATUS_FILTRO


def query(data_ini: datetime, data_fim_exclusiva: datetime, status=STATUS_FILTRO) -> str:
    """
    =====================================================================
    Descrição:
    Gera a consulta SQL do relatório NFCom (Vivo) para um período (um dia
    ou o mês inteiro), trazendo todas as UFs. Equivalente ao SELECT
    manual usado hoje, mas com a janela de datas parametrizada e sem o
    filtro fixo de CUF = 41.
    =====================================================================
    Parâmetros:
    - data_ini: início do período (inclusive), ex: 01/09/2026 00:00.
    - data_fim_exclusiva: fim do período (exclusivo), ex: 02/09/2026 00:00
      para um dia, ou 01/10/2026 00:00 para o mês de setembro inteiro.
    - status: tupla de IND_STATUS aceitos. Padrão STATUS_FILTRO (6, 9, 10);
      use STATUS_CANCELADAS (9,) para só as canceladas.
    =====================================================================
    Retorno:
    - query_str: string com a consulta SQL pronta para execução.
    =====================================================================
    Observações:
    - A tabela `documento_fiscal` é filtrada por DEMI (data de emissão),
      com o mesmo ajuste de fuso (+3h) usado no SELECT manual.
    - O fim é exclusivo (DEMI < fim) para não perder notas emitidas em
      23:59:59.xxx (frações de segundo).
    =====================================================================
    """

    inicio = data_ini.strftime("%Y-%m-%d %H:%M:%S")
    fim = data_fim_exclusiva.strftime("%Y-%m-%d %H:%M:%S")
    status_str = ", ".join(str(int(s)) for s in status)

    query_str = f"""
SELECT
    JSON_VALUE(INF_ADIC_INT, '$.idNfcomNoSirius')  AS [ID NFCom No Sirius],
    ID                                              AS [ID Mensageria],
    DATEADD(HOUR, +3, CAST(DEMI AS DATETIME2))      AS [Data Emissao],
    FORMAT(DATEADD(HOUR, +3, DEMI), 'dd/MM/yyyy HH:mm:ss') AS [Data Emissao + Hora],
    CUF                                             AS [Codigo UF],

    CASE CUF
        WHEN 11 THEN 'RO'
        WHEN 12 THEN 'AC'
        WHEN 13 THEN 'AM'
        WHEN 14 THEN 'RR'
        WHEN 15 THEN 'PA'
        WHEN 16 THEN 'AP'
        WHEN 17 THEN 'TO'
        WHEN 21 THEN 'MA'
        WHEN 22 THEN 'PI'
        WHEN 23 THEN 'CE'
        WHEN 24 THEN 'RN'
        WHEN 25 THEN 'PB'
        WHEN 26 THEN 'PE'
        WHEN 27 THEN 'AL'
        WHEN 28 THEN 'SE'
        WHEN 29 THEN 'BA'
        WHEN 31 THEN 'MG'
        WHEN 32 THEN 'ES'
        WHEN 33 THEN 'RJ'
        WHEN 35 THEN 'SP'
        WHEN 41 THEN 'PR'
        WHEN 42 THEN 'SC'
        WHEN 43 THEN 'RS'
        WHEN 50 THEN 'MS'
        WHEN 51 THEN 'MT'
        WHEN 52 THEN 'GO'
        WHEN 53 THEN 'DF'
        ELSE 'UF nao identificada'
    END                                             AS [Descricao UF],

    EMPRESA_CNPJ                                    AS [CNPJ Emissor],
    IND_STATUS                                      AS [Status NFCom],
    PROT_X_MOTIVO                                   AS [Descricao Status NFCom],
    nnf                                              AS [Numero NFCom],
    SERIE                                            AS [Serie]

FROM documento_fiscal
WHERE DEMI >= '{inicio}'
  AND DEMI < '{fim}'
  AND IND_STATUS IN ({status_str})
ORDER BY ID ASC;
"""
    return query_str
