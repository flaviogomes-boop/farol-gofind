import streamlit as st
import pandas as pd
import boto3
import io
from datetime import datetime, date

st.set_page_config(
    page_title="Farol Completo Gofind - Sellout & Estoque",
    page_icon="🚦",
    layout="wide"
)

st.title("🚦 Farol Diário de Saúde de Dados (Sellout + Estoque)")
st.caption("Cruzamento por CNPJ do Distribuidor de 01/01/2025 até hoje. Auditoria de integridade e faltas.")

# --- CREDENCIAIS AWS S3 ---
AWS_KEY = str(st.secrets.get("AWS_ACCESS_KEY_ID", "AKIARSGQ7ED4FB3WIUF5")).strip()
AWS_SECRET = str(st.secrets.get("AWS_SECRET_ACCESS_KEY", "I/6iuAaECI9ukPUjQRU2AHIXHdvo2qOpEUaSR3S")).strip()
BUCKET = "gofind-integration-file"
PREFIX = "client-vetoquinol/"

def formatar_real(valor):
    if pd.isna(valor):
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

@st.cache_data(ttl=300)
def carregar_e_compilar_tudo(key, secret, bucket, prefix):
    s3 = boto3.client('s3', aws_access_key_id=key, aws_secret_access_key=secret, region_name='us-east-1')
    
    # 1. SELLOUT
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

    # 2. ESTOQUE
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

    # Tratamento Sellout
    if not df_sellout.empty:
        df_sellout['quantidade_produtos'] = pd.to_numeric(df_sellout['quantidade_produtos'], errors='coerce').fillna(0)
        df_sellout['preco_venda_total'] = pd.to_numeric(df_sellout['preco_venda_total'], errors='coerce').fillna(0)
        df_sellout['dt_venda'] = pd.to_datetime(df_sellout['data'], errors='coerce').dt.strftime('%Y-%m-%d')
        df_sellout['dt_proc'] = pd.to_datetime(df_sellout['data_processamento'], errors='coerce').dt.strftime('%Y-%m-%d')
        df_sellout['distribuidor_clean'] = df_sellout['distribuidor'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(14)

    # Tratamento Estoque
    if not df_stock.empty:
        df_stock['quantidade'] = pd.to_numeric(df_stock['quantidade'], errors='coerce').fillna(0)
        df_stock['dt_estoque'] = pd.to_datetime(df_stock['data'], errors='coerce').dt.strftime('%Y-%m-%d')
        df_stock['cnpj_clean'] = df_stock['cnpj_loja'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(14)

    return df_sellout, df_stock

with st.spinner("Compilando base completa do S3..."):
    df_sellout, df_stock = carregar_e_compilar_tudo(AWS_KEY, AWS_SECRET, BUCKET, PREFIX)

# --- TRATAMENTO SEGURO DA LISTA DE CNPJS (CORREÇÃO DO BUG) ---
cnpjs_so = [str(x) for x in df_sellout['distribuidor_clean'].dropna().unique() if str(x).strip() != ''] if not df_sellout.empty else []
cnpjs_st = [str(x) for x in df_stock['cnpj_clean'].dropna().unique() if str(x).strip() != ''] if not df_stock.empty else []
cnpjs_todos = sorted(list(set(cnpjs_so + cnpjs_st)))

# Mapeamento de Nomes
mapa_nomes = {}
if not df_sellout.empty:
    mapa_nomes.update(df_sellout.set_index('distribuidor_clean')['nome_distribuidor'].dropna().to_dict())
if not df_stock.empty:
    mapa_nomes.update(df_stock.set_index('cnpj_clean')['nome_loja'].dropna().to_dict())

# --- NAVEGAÇÃO ---
aba1, aba2, aba3, aba4 = st.tabs([
    "🚦 Farol Diário de Sellout", 
    "📦 Farol Diário de Estoque", 
    "🚨 Auditoria Sellout (Duplicidades)", 
    "📊 Tabela Completa de Estoque"
])

# ----------------------------------------------------
# ABA 1: FAROL DIÁRIO DE SELLOUT
# ----------------------------------------------------
with aba1:
    st.subheader("Esteira Diária de Sellout por CNPJ")
    
    cnpj_sel_so = st.selectbox(
        "Selecione o Distribuidor (CNPJ):", 
        options=cnpjs_todos, 
        format_func=lambda x: f"{x} - {mapa_nomes.get(x, 'Distribuidor ' + x)}"
    )
    
    if cnpj_sel_so:
        datas_cal = pd.date_range(start="2025-01-01", end=date.today().strftime('%Y-%m-%d')).strftime('%Y-%m-%d').tolist()
        df_cal_so = pd.DataFrame({'dt_venda': datas_cal})
        df_cal_so['distribuidor_clean'] = cnpj_sel_so
        
        df_so_cnpj = df_sellout[df_sellout['distribuidor_clean'] == cnpj_sel_so] if not df_sellout.empty else pd.DataFrame()
        
        if not df_so_cnpj.empty:
            agg_so = df_so_cnpj.groupby('dt_venda').agg(
                Qtd_Notas=('nNF', 'nunique'),
                Itens_Vendidos=('quantidade_produtos', 'sum'),
                Faturamento=('preco_venda_total', 'sum')
            ).reset_index()
            df_farol_so = pd.merge(df_cal_so, agg_so, on='dt_venda', how='left').fillna(0)
        else:
            df_farol_so = df_cal_so
            df_farol_so['Qtd_Notas'] = 0
            df_farol_so['Itens_Vendidos'] = 0
            df_farol_so['Faturamento'] = 0.0

        def status_so(row):
            if row['Qtd_Notas'] > 0 and row['Itens_Vendidos'] > 0:
                return "🟢 Recebido c/ Vendas"
            elif row['Qtd_Notas'] > 0:
                return "🟡 Apenas Nota (s/ Volume)"
            else:
                return "🔴 Não Enviou Nota"

        df_farol_so['Farol_Sellout'] = df_farol_so.apply(status_so, axis=1)
        df_farol_so['Nome_Distribuidor'] = mapa_nomes.get(cnpj_sel_so, cnpj_sel_so)
        
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Dias sem Envio de Nota (🔴)", len(df_farol_so[df_farol_so['Farol_Sellout'].str.contains("🔴")]))
        d2.metric("Dias com Vendas (🟢)", len(df_farol_so[df_farol_so['Farol_Sellout'].str.contains("🟢")]))
        d3.metric("Total Notas no Período", int(df_farol_so['Qtd_Notas'].sum()))
        d4.metric("Faturamento Acumulado", formatar_real(df_farol_so['Faturamento'].sum()))

        st.divider()
        exib_so = df_farol_so.copy()
        exib_so['Faturamento'] = exib_so['Faturamento'].apply(formatar_real)
        st.dataframe(exib_so[['dt_venda', 'distribuidor_clean', 'Nome_Distribuidor', 'Farol_Sellout', 'Qtd_Notas', 'Itens_Vendidos', 'Faturamento']].sort_values(by='dt_venda', ascending=False), use_container_width=True)

# ----------------------------------------------------
# ABA 2: FAROL DIÁRIO DE ESTOQUE
# ----------------------------------------------------
with aba2:
    st.subheader("Esteira Diária de Envio de Estoque (Stock Reports)")
    
    cnpj_sel_st = st.selectbox(
        "Selecione o Distribuidor para Estoque:", 
        options=cnpjs_todos, 
        key="st_sel", 
        format_func=lambda x: f"{x} - {mapa_nomes.get(x, 'Distribuidor ' + x)}"
    )
    
    if cnpj_sel_st:
        datas_cal = pd.date_range(start="2025-01-01", end=date.today().strftime('%Y-%m-%d')).strftime('%Y-%m-%d').tolist()
        df_cal_st = pd.DataFrame({'dt_estoque': datas_cal})
        df_cal_st['cnpj_clean'] = cnpj_sel_st
        
        df_st_cnpj = df_stock[df_stock['cnpj_clean'] == cnpj_sel_st] if not df_stock.empty else pd.DataFrame()
        
        if not df_st_cnpj.empty:
            agg_st = df_st_cnpj.groupby('dt_estoque').agg(
                Registros_Estoque=('quantidade', 'count'),
                Saldo_Total_Itens=('quantidade', 'sum'),
                Produtos_Distintos=('ean', 'nunique')
            ).reset_index()
            df_farol_st = pd.merge(df_cal_st, agg_st, on='dt_estoque', how='left').fillna(0)
        else:
            df_farol_st = df_cal_st
            df_farol_st['Registros_Estoque'] = 0
            df_farol_st['Saldo_Total_Itens'] = 0
            df_farol_st['Produtos_Distintos'] = 0

        def status_st(row):
            if row['Registros_Estoque'] > 0:
                return "🟢 Estoque Recebido"
            else:
                return "🔴 Estoque Ausente"

        df_farol_st['Farol_Estoque'] = df_farol_st.apply(status_st, axis=1)
        df_farol_st['Nome_Distribuidor'] = mapa_nomes.get(cnpj_sel_st, cnpj_sel_st)
        
        s1, s2, s3 = st.columns(3)
        s1.metric("Dias c/ Estoque Recebido (🟢)", len(df_farol_st[df_farol_st['Farol_Estoque'].str.contains("🟢")]))
        s2.metric("Dias SEM Envio de Estoque (🔴)", len(df_farol_st[df_farol_st['Farol_Estoque'].str.contains("🔴")]))
        s3.metric("Média de Produtos Diferentes por Envio", round(df_farol_st[df_farol_st['Registros_Estoque'] > 0]['Produtos_Distintos'].mean() or 0, 1))

        st.divider()
        st.dataframe(df_farol_st[['dt_estoque', 'cnpj_clean', 'Nome_Distribuidor', 'Farol_Estoque', 'Registros_Estoque', 'Produtos_Distintos', 'Saldo_Total_Itens']].sort_values(by='dt_estoque', ascending=False), use_container_width=True)

# ----------------------------------------------------
# ABA 3: AUDITORIA SELLOUT
# ----------------------------------------------------
with aba3:
    st.subheader("Auditoria de Notas e Linhas Duplicadas em Sellout")
    if not df_sellout.empty:
        cols_chave_so = ['nfeId', 'nNF', 'distribuidor', 'loja', 'gtin', 'dt_proc']
        cols_p = [c for c in cols_chave_so if c in df_sellout.columns]
        
        dup_so = df_sellout[df_sellout.duplicated(subset=cols_p, keep=False)].sort_values(by=cols_p)
        st.metric("Total Linhas Duplicadas em Sellout", len(dup_so), delta_color="inverse")
        st.dataframe(dup_so, use_container_width=True)

# ----------------------------------------------------
# ABA 4: TABELA COMPLETA DE ESTOQUE + DUPLICADOS
# ----------------------------------------------------
with aba4:
    st.subheader("Base de Dados Completa de Estoque Diário")
    if not df_stock.empty:
        cols_chave_st = ['cnpj_clean', 'ean', 'quantidade', 'dt_estoque']
        
        df_stock_analise = df_stock.copy()
        df_stock_analise['Duplicado_no_Dia'] = df_stock_analise.duplicated(subset=cols_chave_st, keep=False)
        df_stock_analise['Status_Linha'] = df_stock_analise['Duplicado_no_Dia'].apply(lambda x: "⚠️ Repetido no Dia" if x else "✅ Ok")
        
        a1, a2 = st.columns(2)
        a1.metric("Total de Linhas na Base de Estoque", len(df_stock_analise))
        a2.metric("Linhas Repetidas no Mesmo Dia", len(df_stock_analise[df_stock_analise['Duplicado_no_Dia']]), delta_color="inverse")
        
        st.divider()
        st.dataframe(
            df_stock_analise[['arquivo_origem', 'data', 'cnpj_clean', 'nome_loja', 'ean', 'nome_produto', 'quantidade', 'Status_Linha']].sort_values(by=['data', 'cnpj_clean'], ascending=[False, True]),
            use_container_width=True
        )