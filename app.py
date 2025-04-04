from flask import Flask, render_template, request
import pandas as pd
from sqlalchemy import create_engine, text
import warnings
from datetime import datetime

warnings.filterwarnings("ignore", category=UserWarning)

app = Flask(__name__)
DATABASE_URL = "mssql+pyodbc://BREDT1-CLBDDP10/FATURAMENTO?trusted_connection=yes&driver=ODBC+Driver+17+for+SQL+Server"
engine = create_engine(DATABASE_URL)

@app.route("/", methods=["GET", "POST"])
def index():
    # Initialize filters and processed data
    filtros = {}  # Filters for user input
    dados_processados = []  # Processed data to be displayed

    if request.method == "POST":
        tipos = [
            request.form.get("eventual"),
            request.form.get("regular"),
        ]
        tipos = [t for t in tipos if t]  # Filter out empty types
        data_vencimento = request.form.get("data_vencimento")
        numero_previa = request.form.get("num_op_previa")
        data_inicio = request.form.get("data_inicio")
        data_fim = request.form.get("data_fim")

        # Convert 'numero_previa' to integer if possible
        numero_previa = int(numero_previa) if numero_previa else None

        filtros = {
            "tipos": tipos,
            "data_vencimento": data_vencimento,
            "numero_previa": numero_previa,
            "data_inicio": data_inicio,
            "data_fim": data_fim,
        }

        # Base query for fetching data
        query_base = """ 
        SELECT
            [ID_EMPRESA],
            [NOME],
            [TIPO],
            [PREVIA],
            [CICLO_ASSOCIADO],
            [TIPO_OCORRENCIA],
            [NUMERO DO CICLO],
            [INICIO DE PROCESSAMENTO],
            [FINAL DE PROCESSAMENTO],
            [VENCIMENTO_CICLO]
        FROM [FATURAMENTO].[fat].[Historico_Ciclo]
        WHERE [ID_EMPRESA] = '100001'
        """

        # Append filters to the base query
        if numero_previa:
            query_base += " AND [NUMERO DO CICLO] = :num_previa"
        if tipos:
            tipos_str = ", ".join([f":tipo_{i}" for i, t in enumerate(tipos)])
            query_base += f" AND [TIPO] IN ({tipos_str})"
        if data_vencimento:
            query_base += " AND [VENCIMENTO_CICLO] = :data_vencimento"
        if data_inicio:
            query_base += " AND [INICIO DE PROCESSAMENTO] >= :data_inicio"
        if data_fim:
            query_base += " AND [FINAL DE PROCESSAMENTO] <= :data_fim"

        # Paginate the query results
        query_paginated = query_base + " ORDER BY [DATA DE CORTE] DESC OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY"

        offset = 0
        limit = 50
        params = {
            "num_previa": numero_previa,
            "data_vencimento": data_vencimento,
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            **{f"tipo_{i}": t for i, t in enumerate(tipos)},
            "offset": offset,
            "limit": limit,
        }

        # Fetch paginated results
        while True:
            with engine.connect() as conn:
                try:
                    dados_temp = pd.read_sql_query(query_paginated, conn, params=params)
                except Exception as e:
                    print(f"Error: {e}")
                    break

            if dados_temp.empty:
                break

            dados_processados += dados_temp.to_dict(orient='records')
            offset += limit
    else:
        # Default query to fetch all data
        query = """
        SELECT 
            [NOME],
            [TIPO],
            [CICLO_ASSOCIADO],
            [TIPO_OCORRENCIA],
            [NUMERO DO CICLO],
            [INICIO DE PROCESSAMENTO],
            [FINAL DE PROCESSAMENTO],
            [VENCIMENTO_CICLO]
        FROM [FATURAMENTO].[fat].[Historico_Ciclo]
        ORDER BY [DATA DE CORTE] DESC, [ID_EMPRESA], [NUMERO DO CICLO];
        """
        with engine.connect() as conn:
            dados_temp = pd.read_sql_query(query, conn)
        dados_processados = dados_temp.to_dict(orient="records")

    # Render the index template with processed data and filters
    return render_template("index.html", dados=dados_processados, filtros=filtros)

@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0"
    response.headers["Expires"] = "-1"
    response.headers["Pragma"] = "no-cache"
    return response

@app.route("/analise.html", methods=["GET", "POST"])
def analise():
    # Initialize filters

    filtros = {}  # Filters for analysis

    if request.method == "POST":
        # Receive selected row data via POST
        numciclo = request.form["numciclo"]
        data_vencimento = request.form["data_vencimento"]
        nomeciclo = request.form["nomeciclo"]
        tipociclo = request.form["tipociclo"]

    filtros = {
            "tipociclo": tipociclo,
            "data_vencimento": data_vencimento,
            "numciclo": numciclo,
            "nomeciclo": nomeciclo,
        }

    # RECURRING VALUES

    #DEBITO RECORRENTE
    query_DR = text("""
    DECLARE @DataSelecionada DATETIME = :data_selecionada;
    DECLARE @DataInicio DATETIME = DATEADD(MONTH, -5, EOMONTH(@DataSelecionada, -1));

    SELECT 
        [TIPO],
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM') AS MES_REFERENCIA,
        [VENCIMENTO_CICLO],
        SUM([VALOR]) AS TOTAL_MES
    FROM 
        [FATURAMENTO].[fat].[Historico_Previa_itens]
    WHERE 
        [NATUREZA] = 'Débito'
        AND [DEMONSTRATIVO] = 'Não'
        AND [TIPO_EVENTO] = 'Recorrente'
        AND [TIPO] = 'PREVIA'
        AND DAY([VENCIMENTO_CICLO]) = DAY(@DataSelecionada)
        AND [VENCIMENTO_CICLO] >= @DataInicio
        AND [VENCIMENTO_CICLO] <= @DataSelecionada
    GROUP BY 
        [TIPO],
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [VENCIMENTO_CICLO]
    ORDER BY 
        [VENCIMENTO_CICLO] ASC, 
        [TIPO] ASC;
    """)

    # RECURRING CREDIT
    query_CR = text("""
    DECLARE @DataSelecionada DATETIME = :data_selecionada;
    DECLARE @DataInicio DATETIME = DATEADD(MONTH, -5, EOMONTH(@DataSelecionada, -1));

    SELECT 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM') AS MES_REFERENCIA,
        [TIPO],
        SUM([VALOR]) AS TOTAL_MES
    FROM 
        [FATURAMENTO].[fat].[Historico_Previa_itens]
    WHERE 
        [NATUREZA] = 'Crédito'
        AND [DEMONSTRATIVO] = 'Não'
        AND [TIPO_EVENTO] = 'Recorrente'
        AND [TIPO] = 'PREVIA'
        AND DAY([VENCIMENTO_CICLO]) = DAY(@DataSelecionada)
        AND [VENCIMENTO_CICLO] BETWEEN @DataInicio AND @DataSelecionada
    GROUP BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO]
    ORDER BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO];
    """)

    # NON-RECURRING VALUES

    #DEBITO NÃO RECORRENTE
    query_DNR = text("""
    DECLARE @DataSelecionada DATETIME = :data_selecionada;
    DECLARE @DataInicio DATETIME = DATEADD(MONTH, -5, EOMONTH(@DataSelecionada, -1));

    SELECT 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM') AS MES_REFERENCIA,
        [TIPO],
        SUM([VALOR]) AS TOTAL_MES
    FROM 
        [FATURAMENTO].[fat].[Historico_Previa_itens]
    WHERE 
        [NATUREZA] = 'Crédito'
        AND [DEMONSTRATIVO] = 'Não'
        AND [TIPO_EVENTO] = 'Recorrente'
        AND [TIPO] = 'PREVIA'
        AND DAY([VENCIMENTO_CICLO]) = DAY(@DataSelecionada)
        AND [VENCIMENTO_CICLO] BETWEEN @DataInicio AND @DataSelecionada
    GROUP BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO]
    ORDER BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO];
    """)

    # NON-RECURRING CREDIT
    query_CNR = text("""
    DECLARE @DataSelecionada DATETIME = :data_selecionada;
    DECLARE @DataInicio DATETIME = DATEADD(MONTH, -5, EOMONTH(@DataSelecionada, -1));

    SELECT 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM') AS MES_REFERENCIA,
        [TIPO],
        SUM([VALOR]) AS TOTAL_MES
    FROM 
        [FATURAMENTO].[fat].[Historico_Previa_itens]
    WHERE 
        [NATUREZA] = 'Crédito'
        AND [DEMONSTRATIVO] = 'Não'
        AND [TIPO_EVENTO] = 'Recorrente'
        AND [TIPO] = 'PREVIA'
        AND DAY([VENCIMENTO_CICLO]) = DAY(@DataSelecionada)
        AND [VENCIMENTO_CICLO] BETWEEN @DataInicio AND @DataSelecionada
    GROUP BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO]
    ORDER BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO];
    """)

    # OTHER VALUES

    #DEBITO OUTROS
    query_DO = text("""
    DECLARE @DataSelecionada DATETIME = :data_selecionada;
    DECLARE @DataInicio DATETIME = DATEADD(MONTH, -5, EOMONTH(@DataSelecionada, -1));

    SELECT 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM') AS MES_REFERENCIA,
        [TIPO],
        SUM([VALOR]) AS TOTAL_MES
    FROM 
        [FATURAMENTO].[fat].[Historico_Previa_itens]
    WHERE 
        [NATUREZA] = 'Crédito'
        AND [DEMONSTRATIVO] = 'Não'
        AND [TIPO_EVENTO] = 'Recorrente'
        AND [TIPO] = 'PREVIA'
        AND DAY([VENCIMENTO_CICLO]) = DAY(@DataSelecionada)
        AND [VENCIMENTO_CICLO] BETWEEN @DataInicio AND @DataSelecionada
    GROUP BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO]
    ORDER BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO];
    """)

    # OTHER CREDIT
    query_CO = text("""
    DECLARE @DataSelecionada DATETIME = :data_selecionada;
    DECLARE @DataInicio DATETIME = DATEADD(MONTH, -5, EOMONTH(@DataSelecionada, -1));

    SELECT 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM') AS MES_REFERENCIA,
        [TIPO],
        SUM([VALOR]) AS TOTAL_MES
    FROM 
        [FATURAMENTO].[fat].[Historico_Previa_itens]
    WHERE 
        [NATUREZA] = 'Crédito'
        AND [DEMONSTRATIVO] = 'Não'
        AND [TIPO_EVENTO] = 'Recorrente'
        AND [TIPO] = 'PREVIA'
        AND DAY([VENCIMENTO_CICLO]) = DAY(@DataSelecionada)
        AND [VENCIMENTO_CICLO] BETWEEN @DataInicio AND @DataSelecionada
    GROUP BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO]
    ORDER BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO];
    """)

    # QUANTITIES

    #QUANT. DEB RECORRENTE
    query_QDR = text("""
    DECLARE @DataSelecionada DATETIME = :data_selecionada;
    DECLARE @DataInicio DATETIME = DATEADD(MONTH, -5, EOMONTH(@DataSelecionada, -1));

    SELECT 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM') AS MES_REFERENCIA,
        [TIPO],
        SUM([VALOR]) AS TOTAL_MES
    FROM 
        [FATURAMENTO].[fat].[Historico_Previa_itens]
    WHERE 
        [NATUREZA] = 'Crédito'
        AND [DEMONSTRATIVO] = 'Não'
        AND [TIPO_EVENTO] = 'Recorrente'
        AND [TIPO] = 'PREVIA'
        AND DAY([VENCIMENTO_CICLO]) = DAY(@DataSelecionada)
        AND [VENCIMENTO_CICLO] BETWEEN @DataInicio AND @DataSelecionada
    GROUP BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO]
    ORDER BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO];
    """)

    # QUANTITY OF RECURRING CREDIT
    query_QCR = text("""
    DECLARE @DataSelecionada DATETIME = :data_selecionada;
    DECLARE @DataInicio DATETIME = DATEADD(MONTH, -5, EOMONTH(@DataSelecionada, -1));

    SELECT 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM') AS MES_REFERENCIA,
        [TIPO],
        SUM([VALOR]) AS TOTAL_MES
    FROM 
        [FATURAMENTO].[fat].[Historico_Previa_itens]
    WHERE 
        [NATUREZA] = 'Crédito'
        AND [DEMONSTRATIVO] = 'Não'
        AND [TIPO_EVENTO] = 'Recorrente'
        AND [TIPO] = 'PREVIA'
        AND DAY([VENCIMENTO_CICLO]) = DAY(@DataSelecionada)
        AND [VENCIMENTO_CICLO] BETWEEN @DataInicio AND @DataSelecionada
    GROUP BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO]
    ORDER BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO];
    """)

    # QUANTITY OF NON-RECURRING DEBIT
    query_QDNR = text("""
    DECLARE @DataSelecionada DATETIME = :data_selecionada;
    DECLARE @DataInicio DATETIME = DATEADD(MONTH, -5, EOMONTH(@DataSelecionada, -1));

    SELECT 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM') AS MES_REFERENCIA,
        [TIPO],
        SUM([VALOR]) AS TOTAL_MES
    FROM 
        [FATURAMENTO].[fat].[Historico_Previa_itens]
    WHERE 
        [NATUREZA] = 'Crédito'
        AND [DEMONSTRATIVO] = 'Não'
        AND [TIPO_EVENTO] = 'Recorrente'
        AND [TIPO] = 'PREVIA'
        AND DAY([VENCIMENTO_CICLO]) = DAY(@DataSelecionada)
        AND [VENCIMENTO_CICLO] BETWEEN @DataInicio AND @DataSelecionada
    GROUP BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO]
    ORDER BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO];
    """)

    # QUANTITY OF NON-RECURRING CREDIT
    query_QCNR = text("""
    DECLARE @DataSelecionada DATETIME = :data_selecionada;
    DECLARE @DataInicio DATETIME = DATEADD(MONTH, -5, EOMONTH(@DataSelecionada, -1));

    SELECT 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM') AS MES_REFERENCIA,
        [TIPO],
        SUM([VALOR]) AS TOTAL_MES
    FROM 
        [FATURAMENTO].[fat].[Historico_Previa_itens]
    WHERE 
        [NATUREZA] = 'Crédito'
        AND [DEMONSTRATIVO] = 'Não'
        AND [TIPO_EVENTO] = 'Recorrente'
        AND [TIPO] = 'PREVIA'
        AND DAY([VENCIMENTO_CICLO]) = DAY(@DataSelecionada)
        AND [VENCIMENTO_CICLO] BETWEEN @DataInicio AND @DataSelecionada
    GROUP BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO]
    ORDER BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO];
    """)

    # QUANTITY OF OTHER DEBIT
    query_QDO = text("""
    DECLARE @DataSelecionada DATETIME = :data_selecionada;
    DECLARE @DataInicio DATETIME = DATEADD(MONTH, -5, EOMONTH(@DataSelecionada, -1));

    SELECT 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM') AS MES_REFERENCIA,
        [TIPO],
        SUM([VALOR]) AS TOTAL_MES
    FROM 
        [FATURAMENTO].[fat].[Historico_Previa_itens]
    WHERE 
        [NATUREZA] = 'Crédito'
        AND [DEMONSTRATIVO] = 'Não'
        AND [TIPO_EVENTO] = 'Recorrente'
        AND [TIPO] = 'PREVIA'
        AND DAY([VENCIMENTO_CICLO]) = DAY(@DataSelecionada)
        AND [VENCIMENTO_CICLO] BETWEEN @DataInicio AND @DataSelecionada
    GROUP BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO]
    ORDER BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO];
    """)

    # QUANTITY OF OTHER CREDIT
    query_QCO = text("""
    DECLARE @DataSelecionada DATETIME = :data_selecionada;
    DECLARE @DataInicio DATETIME = DATEADD(MONTH, -5, EOMONTH(@DataSelecionada, -1));

    SELECT 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM') AS MES_REFERENCIA,
        [TIPO],
        SUM([VALOR]) AS TOTAL_MES
    FROM 
        [FATURAMENTO].[fat].[Historico_Previa_itens]
    WHERE 
        [NATUREZA] = 'Crédito'
        AND [DEMONSTRATIVO] = 'Não'
        AND [TIPO_EVENTO] = 'Recorrente'
        AND [TIPO] = 'PREVIA'
        AND DAY([VENCIMENTO_CICLO]) = DAY(@DataSelecionada)
        AND [VENCIMENTO_CICLO] BETWEEN @DataInicio AND @DataSelecionada
    GROUP BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO]
    ORDER BY 
        FORMAT([VENCIMENTO_CICLO], 'yyyy-MM'),
        [TIPO];
    """)

    # Execute queries and store results
    try:
        with engine.connect() as conn:
            dados_tempDR = pd.read_sql_query(query_DR, conn, params={"data_selecionada": filtros.get("data_vencimento", pd.Timestamp.now())})
            dados_tempCR = pd.read_sql_query(query_CR, conn, params={"data_selecionada": filtros.get("data_vencimento", pd.Timestamp.now())})
            # Handle other queries similarly

            dados_tempDNR = pd.read_sql_query(query_DNR, conn, params={"data_selecionada": filtros.get("data_vencimento", pd.Timestamp.now())})
            dados_tempCNR = pd.read_sql_query(query_CNR, conn, params={"data_selecionada": filtros.get("data_vencimento", pd.Timestamp.now())})

            dados_tempDO = pd.read_sql_query(query_DO, conn, params={"data_selecionada": filtros.get("data_vencimento", pd.Timestamp.now())})
            dados_tempCO = pd.read_sql_query(query_CO, conn, params={"data_selecionada": filtros.get("data_vencimento", pd.Timestamp.now())})

            dados_tempQDR = pd.read_sql_query(query_QDR, conn, params={"data_selecionada": filtros.get("data_vencimento", pd.Timestamp.now())})
            dados_tempQCR = pd.read_sql_query(query_QCR, conn, params={"data_selecionada": filtros.get("data_vencimento", pd.Timestamp.now())})
            dados_tempQDNR = pd.read_sql_query(query_QDNR, conn, params={"data_selecionada": filtros.get("data_vencimento", pd.Timestamp.now())})
            dados_tempQCNR = pd.read_sql_query(query_QCNR, conn, params={"data_selecionada": filtros.get("data_vencimento", pd.Timestamp.now())})
            dados_tempQDO = pd.read_sql_query(query_QDO, conn, params={"data_selecionada": filtros.get("data_vencimento", pd.Timestamp.now())})
            dados_tempQCO = pd.read_sql_query(query_QCO, conn, params={"data_selecionada": filtros.get("data_vencimento", pd.Timestamp.now())})

    except Exception as e:
        print(f"Error executing query: {e}")
        # Initialize empty DataFrames for all results
        dados_tempDR = dados_tempCR = dados_tempDNR = dados_tempCNR = dados_tempDO = dados_tempCO = \
            dados_tempQDR = dados_tempQCR = dados_tempQDNR = dados_tempQCNR = dados_tempQDO = dados_tempQCO = pd.DataFrame()

    # A

    if not dados_tempDR.empty:
        dados_DR = dados_tempDR.pivot_table(
            index=["TIPO"],
            columns="MES_REFERENCIA",
            values="TOTAL_MES",
            fill_value=0,
            aggfunc="sum"
        ).sort_index(axis=1)  # Ordena por meses

        # Calcula a variação percentual mês a mês
        colunas_DR = list(dados_DR.columns)
        variacoes_DR = dados_DR.pct_change(axis=1) * 100  # Calcula % de variação

        # Transforma em lista de dicionários para renderização
        dados_processados_DR = dados_DR.reset_index().to_dict(orient="records")
        variacoes_processadas_DR = variacoes_DR.reset_index().to_dict(orient="records")

        # Formata os valores
        for row, variacao_row in zip(dados_processados_DR, variacoes_processadas_DR):
            for mes in colunas_DR:
                if mes in row and isinstance(row[mes], (int, float)):
                    row[mes] = '{:,.2f}'.format(row[mes]).replace(",", ".")
                if mes in variacao_row and isinstance(variacao_row[mes], (int, float)):
                    variacao_row[mes] = '{:,.2f}%'.format(variacao_row[mes]).replace(",", ".")

            # Insere as variações diretamente nos dados formatados
            row["VARIACOES"] = variacao_row
    else:
        colunas_DR = []
        dados_processados_DR = []# Initialize empty list for DR data


    # B

    if not dados_tempCR.empty:
        dados_CR = dados_tempCR.pivot_table(
            index=["TIPO"],
            columns="MES_REFERENCIA",
            values="TOTAL_MES",
            fill_value=0,
            aggfunc="sum"
        )
        colunas_CR = list(dados_CR.columns)
        dados_processados_CR = dados_CR.reset_index().to_dict(orient="records")

        for row in dados_processados_CR:
            for mes in colunas_CR:
                if mes in row and isinstance(row[mes], (int, float)):
                    row[mes] = '{:,.2f}'.format(row[mes]).replace(",", ".")

            row["TIPO"] = "CREDITO RECORRENTE" if row.get("TIPO") == "PREVIA" else row.get("TIPO")
    else:
        colunas_CR = []
        dados_processados_CR = []
        dados_CR = pd.DataFrame()

    # C

    if not dados_tempDNR.empty:
        dados_DNR = dados_tempDNR.pivot_table(
            index=["TIPO"],
            columns="MES_REFERENCIA",
            values="TOTAL_MES",
            fill_value=0,
            aggfunc="sum"
        )
        colunas_DNR = list(dados_DNR.columns)
        dados_processados_DNR = dados_DNR.reset_index().to_dict(orient="records")

        for row in dados_processados_DNR:
            for mes in colunas_DNR:
                if mes in row and isinstance(row[mes], (int, float)):
                    row[mes] = '{:,.2f}'.format(row[mes]).replace(",", ".")
        
        for row in dados_processados_DNR:
            row["TIPO"] = "CREDITO RECORRENTE" if row.get("TIPO") == "PREVIA" else row.get("TIPO")
    else:
        colunas_DNR = []
        dados_processados_DNR = []
        dados_DNR = pd.DataFrame()

    # D

    if not dados_tempCNR.empty:
        dados_CNR = dados_tempCNR.pivot_table(
            index=["TIPO"],
            columns="MES_REFERENCIA",
            values="TOTAL_MES",
            fill_value=0,
            aggfunc="sum"
        )
        colunas_CNR = list(dados_CNR.columns)
        dados_processados_CNR = dados_CNR.reset_index().to_dict(orient="records")

        for row in dados_processados_CNR:
            for mes in colunas_CNR:
                if mes in row and isinstance(row[mes], (int, float)):
                    row[mes] = '{:,.2f}'.format(row[mes]).replace(",", ".")
        
        for row in dados_processados_CNR:
            row["TIPO"] = "CREDITO RECORRENTE" if row.get("TIPO") == "PREVIA" else row.get("TIPO")
    else:
        colunas_CNR = []
        dados_processados_CNR = []
        dados_CNR = pd.DataFrame()

    # E

    if not dados_tempDO.empty:
        dados_DO = dados_tempDO.pivot_table(
            index=["TIPO"],
            columns="MES_REFERENCIA",
            values="TOTAL_MES",
            fill_value=0,
            aggfunc="sum"
        )
        colunas_DO = list(dados_DO.columns)
        dados_processados_DO = dados_DO.reset_index().to_dict(orient="records")

        for row in dados_processados_DO:
            for mes in colunas_DO:
                if mes in row and isinstance(row[mes], (int, float)):
                    row[mes] = '{:,.2f}'.format(row[mes]).replace(",", ".")
        
        for row in dados_processados_DO:
            row["TIPO"] = "CREDITO RECORRENTE" if row.get("TIPO") == "PREVIA" else row.get("TIPO")
    else:
        colunas_DO = []
        dados_processados_DO = []
        dados_DO = pd.DataFrame()

    # F

    if not dados_tempCO.empty:
        dados_CO = dados_tempCO.pivot_table(
            index=["TIPO"],
            columns="MES_REFERENCIA",
            values="TOTAL_MES",
            fill_value=0,
            aggfunc="sum"
        )
        colunas_CO = list(dados_CO.columns)
        dados_processados_CO = dados_CO.reset_index().to_dict(orient="records")

        for row in dados_processados_CO:
            for mes in colunas_CO:
                if mes in row and isinstance(row[mes], (int, float)):
                    row[mes] = '{:,.2f}'.format(row[mes]).replace(",", ".")
        
        for row in dados_processados_CO:
            row["TIPO"] = "CREDITO RECORRENTE" if row.get("TIPO") == "PREVIA" else row.get("TIPO")
    else:
        colunas_CO = []
        dados_processados_CO = []
        dados_CO = pd.DataFrame()

    # G

    if not dados_tempQDR.empty:
        dados_QDR = dados_tempQDR.pivot_table(
            index=["TIPO"],
            columns="MES_REFERENCIA",
            values="TOTAL_MES",
            fill_value=0,
            aggfunc="sum"
        )
        colunas_QDR = list(dados_QDR.columns)
        dados_processados_QDR = dados_QDR.reset_index().to_dict(orient="records")

        for row in dados_processados_QDR:
            for mes in colunas_QDR:
                if mes in row and isinstance(row[mes], (int, float)):
                    row[mes] = '{:,.2f}'.format(row[mes]).replace(",", ".")
        
        for row in dados_processados_QDR:
            row["TIPO"] = "CREDITO RECORRENTE" if row.get("TIPO") == "PREVIA" else row.get("TIPO")
    else:
        colunas_QDR = []
        dados_processados_QDR = []
        dados_QDR = pd.DataFrame()

    # H

    if not dados_tempQCR.empty:
        dados_QCR = dados_tempQCR.pivot_table(
            index=["TIPO"],
            columns="MES_REFERENCIA",
            values="TOTAL_MES",
            fill_value=0,
            aggfunc="sum"
        )
        colunas_QCR = list(dados_QCR.columns)
        dados_processados_QCR = dados_QCR.reset_index().to_dict(orient="records")

        for row in dados_processados_QCR:
            for mes in colunas_QCR:
                if mes in row and isinstance(row[mes], (int, float)):
                    row[mes] = '{:,.2f}'.format(row[mes]).replace(",", ".")
        
        for row in dados_processados_QCR:
            row["TIPO"] = "CREDITO RECORRENTE" if row.get("TIPO") == "PREVIA" else row.get("TIPO")
    else:
        colunas_QCR = []
        dados_processados_QCR = []
        dados_QCR = pd.DataFrame()

    # I

    if not dados_tempQDNR.empty:
        dados_QDNR = dados_tempQDNR.pivot_table(
            index=["TIPO"],
            columns="MES_REFERENCIA",
            values="TOTAL_MES",
            fill_value=0,
            aggfunc="sum"
        )
        colunas_QDNR = list(dados_QDNR.columns)
        dados_processados_QDNR = dados_QDNR.reset_index().to_dict(orient="records")

        for row in dados_processados_QDNR:
            for mes in colunas_QDNR:
                if mes in row and isinstance(row[mes], (int, float)):
                    row[mes] = '{:,.2f}'.format(row[mes]).replace(",", ".")
        
        for row in dados_processados_QDNR:
            row["TIPO"] = "CREDITO RECORRENTE" if row.get("TIPO") == "PREVIA" else row.get("TIPO")
    else:
        colunas_QDNR = []
        dados_processados_QDNR = []
        dados_QDNR = pd.DataFrame()

    # J

    if not dados_tempQCNR.empty:
        dados_QCNR = dados_tempQCNR.pivot_table(
            index=["TIPO"],
            columns="MES_REFERENCIA",
            values="TOTAL_MES",
            fill_value=0,
            aggfunc="sum"
        )
        colunas_QCNR = list(dados_QCNR.columns)
        dados_processados_QCNR = dados_QCNR.reset_index().to_dict(orient="records")

        for row in dados_processados_QCNR:
            for mes in colunas_QCNR:
                if mes in row and isinstance(row[mes], (int, float)):
                    row[mes] = '{:,.2f}'.format(row[mes]).replace(",", ".")
        
        for row in dados_processados_QCNR:
            row["TIPO"] = "CREDITO RECORRENTE" if row.get("TIPO") == "PREVIA" else row.get("TIPO")
    else:
        colunas_QCNR = []
        dados_processados_QCNR = []
        dados_QCNR = pd.DataFrame()

    # K

    if not dados_tempQDO.empty:
        dados_QDO = dados_tempQDO.pivot_table(
            index=["TIPO"],
            columns="MES_REFERENCIA",
            values="TOTAL_MES",
            fill_value=0,
            aggfunc="sum"
        )
        colunas_QDO = list(dados_QDO.columns)
        dados_processados_QDO = dados_QDO.reset_index().to_dict(orient="records")

        for row in dados_processados_QDO:
            for mes in colunas_QDO:
                if mes in row and isinstance(row[mes], (int, float)):
                    row[mes] = '{:,.2f}'.format(row[mes]).replace(",", ".")
        
        for row in dados_processados_QDO:
            row["TIPO"] = "CREDITO RECORRENTE" if row.get("TIPO") == "PREVIA" else row.get("TIPO")
    else:
        colunas_QDO = []
        dados_processados_QDO = []
        dados_QDO = pd.DataFrame()

    # L

    if not dados_tempQCO.empty:
        dados_QCO = dados_tempQCO.pivot_table(
            index=["TIPO"],
            columns="MES_REFERENCIA",
            values="TOTAL_MES",
            fill_value=0,
            aggfunc="sum"
        )
        colunas_QCO = list(dados_QCO.columns)
        dados_processados_QCO = dados_QCO.reset_index().to_dict(orient="records")

        for row in dados_processados_QCO:
            for mes in colunas_QCO:
                if mes in row and isinstance(row[mes], (int, float)):
                    row[mes] = '{:,.2f}'.format(row[mes]).replace(",", ".")
        
        for row in dados_processados_QCO:
            row["TIPO"] = "CREDITO RECORRENTE" if row.get("TIPO") == "PREVIA" else row.get("TIPO")
    else:
        colunas_QCO = []
        dados_processados_QCO = []
        dados_QCO = pd.DataFrame()

#tabela1
    dados_combinados_um = pd.concat([dados_DR, dados_CR])
    dados_combinados_um = dados_combinados_um.reset_index(drop=True).fillna(0)
    dados_combinados_um = dados_combinados_um.applymap(
        lambda x: '{:,.2f}'.format(x).replace(",", ".") if isinstance(x, (int, float)) else x
    )
    dados_combinados_list1 = dados_combinados_um.to_dict(orient='records')

#tabela2
    dados_combinados_dois = pd.concat([dados_DNR, dados_CNR])
    dados_combinados_dois = dados_combinados_dois.reset_index(drop=True).fillna(0)
    dados_combinados_dois = dados_combinados_dois.applymap(
        lambda x: '{:,.2f}'.format(x).replace(",", ".") if isinstance(x, (int, float)) else x
    )
    dados_combinados_list2 = dados_combinados_dois.to_dict(orient='records')


    dados_combinados_tres = pd.concat([dados_DO, dados_CO])
    dados_combinados_tres = dados_combinados_tres.reset_index(drop=True).fillna(0)
    dados_combinados_tres = dados_combinados_tres.applymap(
        lambda x: '{:,.2f}'.format(x).replace(",", ".") if isinstance(x, (int, float)) else x
    )
    dados_combinados_list3 = dados_combinados_tres.to_dict(orient='records')


    dados_combinados_quatro = pd.concat([dados_QDR, dados_QCR, dados_QDNR, dados_QCNR, dados_QDO, dados_QCO])
    dados_combinados_quatro = dados_combinados_quatro.reset_index(drop=True).fillna(0)
    dados_combinados_quatro = dados_combinados_quatro.applymap(
        lambda x: '{:,.2f}'.format(x).replace(",", ".") if isinstance(x, (int, float)) else x
    )
    dados_combinados_list4 = dados_combinados_quatro.to_dict(orient='records')



    # Render the analysis template with combined data
    return render_template(
        "analise.html",
        dados1=dados_combinados_list1,
        colunas1=sorted(set(colunas_DR + colunas_CR)),
        dados2=dados_combinados_list2,
        colunas2=sorted(set(colunas_DNR + colunas_CNR)),
        dados3=dados_combinados_list3,
        colunas3=sorted(set(colunas_DO + colunas_CO)),
        dados4=dados_combinados_list4,
        colunas4=sorted(set(colunas_QDR + colunas_QCR + colunas_QDNR + colunas_QCNR + colunas_QDO + colunas_QCO )),
        filtros=filtros,
        numero=numciclo, 
        data_vencimento=data_vencimento, 
        nome=nomeciclo, 
        tipos=tipociclo
    )
    

@app.route("/enviar", methods=["POST"])
def enviar():
    try:
        textinput = request.form.get("testeinput")

        mensagem = f"Data observations sent successfully!"

        return f"<script>alert('{mensagem}'); window.location.href = '/';</script>"

    except Exception as e:
        print(f"Error processing data: {e}")
        return f"<script>alert('Error processing data: {str(e)}'); window.location.href = '/';</script>", 500




if __name__ == "__main__":
    app.run(debug=True)
