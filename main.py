import streamlit as st
import pandas as pd
import boto3
import io
import plotly.express as px
from datetime import datetime

st.set_page_config(
    page_title="Farol de Auditoria Gofind - Vetoquinol",
    page_icon="🚦",
    layout="wide"
)

st.title("🚦 Farol de Auditoria e Saúde de Dados (Gofind)")
st.caption("Análise diária por CNPJ (desde Jan/2025), checagem de duplicidades e controle de estoque.")

# --- CREDENCIAIS E PARÂMETROS ---
AWS_KEY = str(st.secrets.get("AWS_ACCESS_KEY_ID", "AKIARSGQ7ED4FB3WIUF5")).strip()
AWS_SECRET = str(st.secrets.get("AWS_SECRET_ACCESS_KEY", "I/6iuAaECI9ukPUjQRU2AHIXHdvo2qOpEUaSR3S")).strip()
BUCKET = "gofind-integration-file"
PREFIX = "client-vetoquinol/"

def formatar_real(valor):
    if pd.isna(valor):
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

@st.cache_data(ttl=300)
def compilar_dados_completos(key, secret, bucket, prefix):
    """Lê todos os CSVs de reports/ (incluindo Vetoquinol-dados-faltando.csv) e stock-reports/"""
    s3 = boto3.client('s3', aws_access_key_id=key, aws_secret_access_key=secret, region_name='us-east-1')
    
    # 1. Compilação Sellout (reports/)
    res_so = s3.list_objects_v2(Bucket=bucket, Prefix=f"{prefix}reports/")
    arq_so = [obj['Key'] for obj in res_so.get('Contents', []) if obj['Key'].endswith('.csv')]
    
    dfs_so = []
    for k in arq_so:
        try:
            obj = s3.get_object(Bucket=bucket, Key=k)
            df_t = pd.read_csv(io.BytesIO(obj['Body'].read()), encoding='utf-8', dtype=str)
            df_t['arquivo_origem'] = k.split('/')[-1]
            dfs_so.append(df_t)
        except Exception:
            pass
            
    df_sellout = pd.concat(dfs_so, ignore_index=True) if dfs_so else pd.DataFrame()

    # 2. Compilação Estoque (stock-reports/)
    res_st = s3.list_objects_v2(Bucket=bucket, Prefix=f"{prefix}stock-reports/")
    arq_st = [obj['Key'] for obj in res_st.get('Contents', []) if obj['Key'].endswith('.csv')]
    
    dfs_st = []
    for k in arq_st:
        try:
            obj = s3.get_object(Bucket=bucket, Key=k)
            df_t = pd.read_csv(io.BytesIO(obj['Body'].read()), encoding='utf-8', dtype=str)
            df_t['arquivo_origem'] = k.split('/')[-1]
            dfs_st.append(df_t)
        except Exception:
            pass
            
    df_stock = pd.concat(dfs_st, ignore_index=True) if dfs_st else pd.DataFrame()

    # Tratamento de Tipos - Sellout
    if not df_sellout.empty:
        df_sellout['quantidade_produtos'] = pd.to_numeric(df_sellout['quantidade_produtos'], errors='coerce').fillna(0)
        df_sellout['preco_venda_total'] = pd.to_numeric(df_sellout['preco_venda_total'], errors='coerce').fillna(0)
        df_sellout['dt_venda'] = pd.to_datetime(df_sellout['data'], errors='coerce').dt.strftime('%Y-%m-%d')
        df_sellout['dt_proc'] = pd.to_datetime(df_sellout['data_processamento'], errors='coerce').dt.strftime('%Y-%m-%d')

    # Tratamento de Tipos - Estoque
    if not df_stock.empty:
        df_stock['quantidade'] = pd.to_numeric(df_stock['quantidade'], errors='coerce').fillna(0)
        df_stock['dt_estoque'] = pd.to_datetime(df_stock['data'], errors='coerce').dt.strftime('%Y-%m-%d')

    return df_sellout, df_stock

# Carregamento dos dados
with st.spinner("Compilando base histórica completa (incluindo dados-faltando.csv)..."):
    df_sellout, df_stock = compilar_dados_completos(AWS_KEY, AWS_SECRET, BUCKET, PREFIX)

aba1, aba2, aba3 = st.tabs(["📅 Matriz Diária por CNPJ (Jan/2025+)", "🚨 Auditoria de Duplicidades (Sellout)", "📦 Anomalias de Estoque (Stock)"])

# ----------------------------------------------------
# ABA 1: MATRIZ CALENDÁRIO DIÁRIA POR CNPJ (JAN/2025 EM DIANTE)
# ----------------------------------------------------
with aba1:
    st.subheader("Acompanhamento Diário de Envios por CNPJ do Distribuidor")
    
    if not df_sellout.empty and 'distribuidor' in df_sellout.columns:
        # Filtra datas a partir de 01/01/2025
        df_so_filtered = df_sellout[df_sellout['dt_venda'] >= '2025-01-01'].copy()
        
        # Filtro de Seleção de Distribuidor
        cnpjs_disponiveis = sorted(df_so_filtered['distribuidor'].dropna().unique())
        cnpj_selecionado = st.selectbox("Selecione o CNPJ do Distribuidor para auditar a esteira diária:", options=["TODOS"] + cnpjs_disponiveis)
        
        if cnpj_selecionado != "TODOS":
            df_so_filtered = df_so_filtered[df_so_filtered['distribuidor'] == cnpj_selecionado]

        # Agrupamento Diário por CNPJ e Data
        resumo_diario = df_so_filtered.groupby(['dt_venda', 'distribuidor', 'nome_distribuidor']).agg(
            Notas_Faturadas=('nNF', 'nunique'),
            Itens_Vendidos=('quantidade_produtos', 'sum'),
            Faturamento=('preco_venda_total', 'sum'),
            Notas_Canceladas=('status', lambda x: (x == 'CANCELADA').sum())
        ).reset_index()

        # Definição do Farol
        def classificar_dia(row):
            if row['Notas_Faturadas'] > 0 and row['Itens_Vendidos'] > 0:
                return "🟢 Recebido c/ Vendas"
            elif row['Notas_Faturadas'] > 0:
                return "🟡 Apenas Notas s/ Volume"
            else:
                return "🔴 Sem Recebimento"

        resumo_diario['Status_Farol'] = resumo_diario.apply(classificar_dia, axis=1)

        st.markdown("##### Resumo Executivo da Seleção")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Dias Analisados c/ Movimento", resumo_diario['dt_venda'].nunique())
        m2.metric("Total de Notas Processadas", int(resumo_diario['Notas_Faturadas'].sum()))
        m3.metric("Total de Itens Vetoquinol", int(resumo_diario['Itens_Vendidos'].sum()))
        m4.metric("Faturamento Total", formatar_real(resumo_diario['Faturamento'].sum()))

        st.divider()
        st.markdown("##### Tabela Diária Detalhada")
        
        resumo_exibicao = resumo_diario.copy()
        resumo_exibicao['Faturamento'] = resumo_exibicao['Faturamento'].apply(formatar_real)
        st.dataframe(resumo_exibicao.sort_values(by=['dt_venda', 'distribuidor'], ascending=[False, True]), use_container_width=True)

# ----------------------------------------------------
# ABA 2: AUDITORIA RIGOROSA DE DUPLICIDADE (SELLOUT)
# ----------------------------------------------------
with aba2:
    st.subheader("Detecção de Linhas e Notas Duplicadas")
    st.markdown("Verificação do cruzamento: `[nfeId + número nota (nNF) + CNPJ distribuidor + CNPJ cliente (loja) + Produto (gtin) + Data Processamento]`")
    
    if not df_sellout.empty:
        cols_chave_so = ['nfeId', 'nNF', 'distribuidor', 'loja', 'gtin', 'dt_proc']
        cols_presentes = [c for c in cols_chave_so if c in df_sellout.columns]
        
        # Identificação de registros duplicados
        duplicados_mask = df_sellout.duplicated(subset=cols_presentes, keep=False)
        df_duplicados_so = df_sellout[duplicados_mask].sort_values(by=cols_presentes)
        
        q1, q2 = st.columns(2)
        q1.metric("Total de Linhas na Base Consolidada", len(df_sellout))
        q2.metric("Linhas Identificadas como DUPLICADAS", len(df_duplicados_so), delta_color="inverse")
        
        if not df_duplicados_so.empty:
            st.error(f"🚨 Atenção: Foram encontradas {len(df_duplicados_so)} linhas com combinação idêntica de NfeId, Nota, CNPJ Distribuidor, Cliente, Produto e Data de Processamento!")
            st.dataframe(df_duplicados_so[['nfeId', 'nNF', 'distribuidor', 'nome_distribuidor', 'loja', 'gtin', 'nome_produto', 'dt_proc', 'arquivo_origem']], use_container_width=True)
        else:
            st.success("✅ Nenhuma duplicidade encontrada com a chave exata informada!")

# ----------------------------------------------------
# ABA 3: ANOMALIAS DE ESTOQUE (MULTI-ENVIO)
# ----------------------------------------------------
with aba3:
    st.subheader("Validação de Multi-Envios e Duplicidades no Estoque")
    st.markdown("Verificação de envio repetido: `[Mesmo Distribuidor (cnpj_loja) + Mesmo Produto (ean) + Mesma Quantidade na Mesma Data]`")
    
    if not df_stock.empty:
        cols_chave_st = ['cnpj_loja', 'ean', 'quantidade', 'dt_estoque']
        cols_st_presentes = [c for c in cols_chave_st if c in df_stock.columns]
        
        duplicados_st_mask = df_stock.duplicated(subset=cols_st_presentes, keep=False)
        df_duplicados_st = df_stock[duplicados_st_mask].sort_values(by=cols_st_presentes)
        
        e1, e2 = st.columns(2)
        e1.metric("Total de Registros de Estoque", len(df_stock))
        e2.metric("Registros de Estoque Duplicados no Mesmo Dia", len(df_duplicados_st), delta_color="inverse")
        
        if not df_duplicados_st.empty:
            st.warning(f"⚠️ Identificados {len(df_duplicados_st)} registros de estoque com o mesmo produto, distribuidor e saldo no mesmo dia!")
            st.dataframe(df_duplicados_st[['dt_estoque', 'cnpj_loja', 'nome_loja', 'ean', 'nome_produto', 'quantidade', 'arquivo_origem']], use_container_width=True)
        else:
            st.success("✅ Nenhum multi-envio de estoque duplicado detectado!")