import streamlit as st
import pandas as pd
import boto3
import io
import plotly.express as px

st.set_page_config(page_title="Farol Consolidado - Gofind", layout="wide")

st.title("🚦 Farol Consolidado de Saúde de Dados (Sellout + Estoque)")
st.caption("Leitura e compilação automática em lote de todos os arquivos do S3")

# Credenciais
AWS_KEY = st.secrets.get("AWS_ACCESS_KEY_ID", "AKIARSGQ7ED4FB3WIUF5")
AWS_SECRET = st.secrets.get("AWS_SECRET_ACCESS_KEY", "I/6iuAaECI9ukPUjQRU2AHIXHdvo2qOpEUaSR3S")
BUCKET = "gofind-integration-file"
PREFIX = "client-vetoquinol/"

@st.cache_data(ttl=600)
def compilar_dados_s3(key, secret, bucket, prefix, subpasta):
    """Lê TODOS os arquivos CSV da subpasta no S3 e junta em um único DataFrame consolidado"""
    try:
        s3 = boto3.client('s3', aws_access_key_id=key, aws_secret_access_key=secret)
        path_prefix = f"{prefix}{subpasta}/"
        response = s3.list_objects_v2(Bucket=bucket, Prefix=path_prefix)
        
        arquivos = [obj['Key'] for obj in response.get('Contents', []) if obj['Key'].endswith('.csv')]
        
        lista_dfs = []
        for file_key in arquivos:
            obj = s3.get_object(Bucket=bucket, Key=file_key)
            df_temp = pd.read_csv(io.BytesIO(obj['Body'].read()))
            df_temp['arquivo_origem'] = file_key.split('/')[-1]
            lista_dfs.append(df_temp)
            
        if lista_dfs:
            return pd.concat(lista_dfs, ignore_index=True)
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro ao compilar dados do S3 ({subpasta}): {e}")
        return pd.DataFrame()

# Processamento dos Dados
with st.spinner("Compilando todos os arquivos de Sellout e Estoque do S3..."):
    df_sellout_all = compilar_dados_s3(AWS_KEY, AWS_SECRET, BUCKET, PREFIX, "reports")
    df_stock_all = compilar_dados_s3(AWS_KEY, AWS_SECRET, BUCKET, PREFIX, "stock-reports")

st.success("Compilação concluída com sucesso!")

# Interface de Abas do Farol
aba1, aba2, aba3 = st.tabs(["📊 Farol Geral de Saúde", "🧾 Sellout Consolidado", "📦 Estoque Consolidado"])

with aba1:
    st.subheader("Matriz de Controle de Envios por Distribuidor")
    if not df_sellout_all.empty and 'nome_distribuidor' in df_sellout_all.columns:
        st.markdown("##### Resumo Geral de Sellout Processado")
        resumo_so = df_sellout_all.groupby('nome_distribuidor').agg(
            Total_Linhas=('arquivo_origem', 'count'),
            Total_Valor=('preco_venda_total', 'sum') if 'preco_venda_total' in df_sellout_all.columns else ('arquivo_origem', 'count'),
            Notas_Canceladas=('status', lambda x: (x == 'CANCELADA').sum()) if 'status' in df_sellout_all.columns else ('arquivo_origem', 'count')
        ).reset_index()
        st.dataframe(resumo_so, use_container_width=True)

with aba2:
    st.subheader("Base Unificada de Sellout")
    if not df_sellout_all.empty:
        duplicadas = df_sellout_all.duplicated(subset=['nfeId']).sum() if 'nfeId' in df_sellout_all.columns else 0
        st.warning(f"Linhas com nfeId duplicado na base consolidada: {duplicadas}")
        st.dataframe(df_sellout_all.head(500), use_container_width=True)

with aba3:
    st.subheader("Base Unificada de Estoque")
    if not df_stock_all.empty:
        duplicados_stock = df_stock_all.duplicated(subset=['cnpj_loja', 'ean', 'data']).sum() if all(c in df_stock_all.columns for c in ['cnpj_loja', 'ean', 'data']) else 0
        st.warning(f"Anomalias de multi-envio no mesmo dia/produto: {duplicados_stock}")
        st.dataframe(df_stock_all.head(500), use_container_width=True)