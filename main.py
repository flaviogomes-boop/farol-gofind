import streamlit as st
import pandas as pd
import boto3
import io
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(
    page_title="Farol Consolidado Gofind - Vetoquinol",
    page_icon="🚦",
    layout="wide"
)

st.title("🚦 Farol Consolidado de Saúde de Dados (Sellout + Estoque)")
st.caption("Compilação automática UTF-8, formatação em Reais (R$) e matriz diária de acompanhamento.")

# Credenciais e Parâmetros
AWS_KEY = str(st.secrets.get("AWS_ACCESS_KEY_ID", "AKIARSGQ7ED4FB3WIUF5")).strip()
AWS_SECRET = str(st.secrets.get("AWS_SECRET_ACCESS_KEY", "I/6iuAaECI9ukPUjQRU2AHIXHdvo2qOpEUaSR3S")).strip()
BUCKET = "gofind-integration-file"
PREFIX = "client-vetoquinol/"

# Função Helper para Formatar Moeda Brasileira
def formatar_real(valor):
    if pd.isna(valor):
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

@st.cache_data(ttl=300)
def compilar_dados_s3(key, secret, bucket, prefix, subpasta):
    """Lê e compila todos os arquivos CSV em UTF-8 garantindo tipos numéricos e datas"""
    try:
        s3 = boto3.client('s3', aws_access_key_id=key, aws_secret_access_key=secret, region_name='us-east-1')
        path_prefix = f"{prefix}{subpasta}/"
        response = s3.list_objects_v2(Bucket=bucket, Prefix=path_prefix)
        arquivos = [obj['Key'] for obj in response.get('Contents', []) if obj['Key'].endswith('.csv')]
        
        if not arquivos:
            return pd.DataFrame()
            
        lista_dfs = []
        for file_key in arquivos:
            obj = s3.get_object(Bucket=bucket, Key=file_key)
            # Leitura explícita UTF-8 (Padrão Americano/Global)
            df_temp = pd.read_csv(io.BytesIO(obj['Body'].read()), encoding='utf-8')
            df_temp['arquivo_origem'] = file_key.split('/')[-1]
            lista_dfs.append(df_temp)
            
        df_consolidado = pd.concat(lista_dfs, ignore_index=True)
        
        # Trata colunas de datas
        for col_dt in ['data', 'data_processamento']:
            if col_dt in df_consolidado.columns:
                df_consolidado[col_dt] = pd.to_datetime(df_consolidado[col_dt], errors='coerce')
                df_consolidado['data_dt'] = df_consolidado[col_dt].dt.strftime('%Y-%m-%d')
                
        # Converte valores numéricos caso tenham vindo formatados
        for col_num in ['preco_venda_total', 'preco_venda_unitario', 'quantidade_produtos', 'quantidade']:
            if col_num in df_consolidado.columns:
                df_consolidado[col_num] = pd.to_numeric(df_consolidado[col_num], errors='coerce').fillna(0)
                
        return df_consolidado
    except Exception as e:
        st.error(f"Erro ao ler subpasta UTF-8 '{subpasta}': {e}")
        return pd.DataFrame()

# Processamento
with st.spinner("Compilando todos os CSVs UTF-8 do S3..."):
    df_sellout = compilar_dados_s3(AWS_KEY, AWS_SECRET, BUCKET, PREFIX, "reports")
    df_stock = compilar_dados_s3(AWS_KEY, AWS_SECRET, BUCKET, PREFIX, "stock-reports")

# Abas
aba1, aba2, aba3 = st.tabs(["🚦 Farol Diário de Recebimento", "🧾 Sellout Consolidado", "📦 Estoque Consolidado"])

# ----------------------------------------------------
# ABA 1: FAROL DIÁRIO DE RECEBIMENTO (ALERTAS)
# ----------------------------------------------------
with aba1:
    st.subheader("Acompanhamento Diário por Distribuidor")
    
    if not df_sellout.empty and 'nome_distribuidor' in df_sellout.columns:
        # Agrupa os recebimentos diários de notas e produtos Vetoquinol
        farol_diario = df_sellout.groupby(['data_dt', 'nome_distribuidor']).agg(
            Qtd_Notas=('nNF', 'nunique') if 'nNF' in df_sellout.columns else ('arquivo_origem', 'count'),
            Produtos_Vetoquinol_Faturados=('quantidade_produtos', 'sum'),
            Faturamento_Total=('preco_venda_total', 'sum'),
            Notas_Canceladas=('status', lambda x: (x == 'CANCELADA').sum()) if 'status' in df_sellout.columns else ('arquivo_origem', 'count')
        ).reset_index()

        # Aplicação das Regras do Farol (Verde, Amarelo, Vermelho)
        def definir_status(row):
            if row['Qtd_Notas'] > 0 and row['Produtos_Vetoquinol_Faturados'] > 0:
                return "🟢 Tudo OK"
            elif row['Qtd_Notas'] > 0 or row['Faturamento_Total'] > 0:
                return "🟡 Atenção (Verificar)"
            else:
                return "🔴 Não Recebido / Sem Movimento"

        farol_diario['Status_Farol'] = farol_diario.apply(definir_status, axis=1)

        # Métrica em Reais
        faturamento_geral = df_sellout['preco_venda_total'].sum() if 'preco_venda_total' in df_sellout.columns else 0
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Faturamento Compilado Total", formatar_real(faturamento_geral))
        c2.metric("Total Notas Faturadas", int(farol_diario['Qtd_Notas'].sum()))
        c3.metric("Produtos Vetoquinol Faturados", int(farol_diario['Produtos_Vetoquinol_Faturados'].sum()))
        c4.metric("Registros em Alerta (Amarelo)", len(farol_diario[farol_diario['Status_Farol'].str.contains("🟡")]))

        st.divider()
        st.markdown("##### Tabela do Farol Diário de Envios")
        
        # Formata a coluna de faturamento na exibição
        farol_exibicao = farol_diario.copy()
        farol_exibicao['Faturamento_Total'] = farol_exibicao['Faturamento_Total'].apply(formatar_real)
        
        st.dataframe(
            farol_exibicao.sort_values(by='data_dt', ascending=False),
            use_container_width=True
        )
    else:
        st.info("Nenhum dado consolidado para gerar o Farol.")

# ----------------------------------------------------
# ABA 2: SELLOUT CONSOLIDADO
# ----------------------------------------------------
with aba2:
    st.subheader("Base Unificada de Sellout (Formatação em Reais R$)")
    if not df_sellout.empty:
        df_so_view = df_sellout.copy()
        if 'preco_venda_total' in df_so_view.columns:
            df_so_view['preco_venda_total_R$'] = df_so_view['preco_venda_total'].apply(formatar_real)
        if 'preco_venda_unitario' in df_so_view.columns:
            df_so_view['preco_venda_unitario_R$'] = df_so_view['preco_venda_unitario'].apply(formatar_real)
            
        st.dataframe(df_so_view, use_container_width=True)

# ----------------------------------------------------
# ABA 3: ESTOQUE CONSOLIDADO
# ----------------------------------------------------
with aba3:
    st.subheader("Base Unificada de Estoque Diário")
    if not df_stock.empty:
        st.dataframe(df_stock, use_container_width=True)