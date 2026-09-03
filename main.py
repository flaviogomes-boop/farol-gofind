import streamlit as st
import pandas as pd
import boto3
import io
import calendar
from datetime import datetime, date

# Configuração da Página
st.set_page_config(
    page_title="Gofind - Farol de Saúde de Dados",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ESTILIZAÇÃO CSS (MANUAL DE MARCA GOFIND + PORTAL GOFIND) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Kumbh+Sans:wght@400;600;700&family=Raleway:wght@400;500;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'Raleway', sans-serif;
        color: #444444;
    }
    
    /* Fundo da Área Principal */
    .stApp {
        background-color: #F8F9FA;
    }

    /* Sidebar Estilo Portal Gofind (#0E3940) */
    [data-testid="stSidebar"] {
        background-color: #0E3940 !important;
        color: #FFFFFF !important;
    }
    [data-testid="stSidebar"] * {
        color: #FFFFFF !important;
    }
    
    /* Títulos Kumbh Sans */
    h1, h2, h3, h4, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
        font-family: 'Kumbh Sans', sans-serif !important;
        color: #0E3940 !important;
        font-weight: 700;
    }

    /* Estilo do Logo Header */
    .gofind-header {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 10px 0px 20px 0px;
        border-bottom: 1px solid rgba(255,255,255,0.1);
        margin-bottom: 20px;
    }
    .gofind-logo-text {
        font-family: 'Kumbh Sans', sans-serif;
        font-size: 26px;
        font-weight: 700;
        color: #93C400 !important;
        letter-spacing: -0.5px;
    }
    .gofind-logo-dot {
        color: #93C400;
    }

    /* Abas Customizadas */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        height: 45px;
        background-color: #FFFFFF;
        border-radius: 6px;
        color: #0E3940;
        font-weight: 600;
        font-family: 'Kumbh Sans', sans-serif;
        border: 1px solid #E2E8F0;
    }
    .stTabs [aria-selected="true"] {
        background-color: #93C400 !important;
        color: #FFFFFF !important;
        border-color: #93C400 !important;
    }

    /* Cards e Métricas */
    [data-testid="stMetric"] {
        background-color: #FFFFFF;
        padding: 15px;
        border-radius: 8px;
        border-left: 5px solid #93C400;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    [data-testid="stMetricLabel"] {
        font-family: 'Kumbh Sans', sans-serif;
        color: #0E3940 !important;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR FIXA (ESTILO PORTAL) ---
with st.sidebar:
    st.markdown("""
        <div class="gofind-header">
            <svg width="36" height="24" viewBox="0 0 120 80" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M30 40C30 23.4315 43.4315 10 60 10C76.5685 10 90 23.4315 90 40C90 56.5685 76.5685 70 60 70C43.4315 70 30 56.5685 30 40Z" fill="#93C400"/>
                <circle cx="35" cy="40" r="12" fill="#0E3940"/>
            </svg>
            <span class="gofind-logo-text">go<span style="color:#93C400;">find</span></span>
        </div>
    """, unsafe_allow_html=True)
    st.write("👤 **Olá, vetoquinol@gofind.online**")
    st.write("🏢 **Cliente:** Vetoquinol")
    st.divider()

# Credenciais S3
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

with st.spinner("Carregando bases do S3..."):
    df_sellout, df_stock = carregar_e_compilar_tudo(AWS_KEY, AWS_SECRET, BUCKET, PREFIX)

cnpjs_so = [str(x) for x in df_sellout['distribuidor_clean'].dropna().unique() if str(x).strip() != ''] if not df_sellout.empty else []
cnpjs_st = [str(x) for x in df_stock['cnpj_clean'].dropna().unique() if str(x).strip() != ''] if not df_stock.empty else []
cnpjs_todos = sorted(list(set(cnpjs_so + cnpjs_st)))

mapa_nomes = {}
if not df_sellout.empty:
    mapa_nomes.update(df_sellout.set_index('distribuidor_clean')['nome_distribuidor'].dropna().to_dict())
if not df_stock.empty:
    mapa_nomes.update(df_stock.set_index('cnpj_clean')['nome_loja'].dropna().to_dict())

# Cálculo da Média Diária Histórica por Distribuidor (para o Alerta Amarelo)
medias_diarias_dist = {}
if not df_sellout.empty:
    daily_dist = df_sellout.groupby(['distribuidor_clean', 'dt_venda'])['quantidade_produtos'].sum().reset_index()
    medias_diarias_dist = daily_dist.groupby('distribuidor_clean')['quantidade_produtos'].mean().to_dict()

# Abas
aba1, aba2, aba3, aba4 = st.tabs([
    "📅 Calendário Farol - Sellout", 
    "📦 Calendário Farol - Estoque", 
    "🚨 Auditoria Sellout (Duplicidades)", 
    "📊 Tabela Completa de Estoque"
])

def render_controles_data(key_prefix):
    col_tipo, col_m, col_a, col_custom = st.columns([2, 2, 2, 4])
    tipo_busca = col_tipo.radio("Modo de Visão:", ["Mês Recorrente", "Período Personalizado"], key=f"{key_prefix}_tipo", horizontal=True)
    today = date.today()
    if tipo_busca == "Mês Recorrente":
        mes = col_m.selectbox("Mês:", list(range(1, 13)), index=today.month - 1, key=f"{key_prefix}_m")
        ano = col_a.selectbox("Ano:", list(range(2025, today.year + 2)), index=list(range(2025, today.year + 2)).index(today.year), key=f"{key_prefix}_a")
        dt_inicio = date(ano, mes, 1)
        _, ult_dia = calendar.monthrange(ano, mes)
        dt_fim = date(ano, mes, ult_dia)
    else:
        datas = col_custom.date_input("Selecione o Período:", [date(2025, 1, 1), today], key=f"{key_prefix}_custom")
        dt_inicio = datas[0] if len(datas) > 0 else date(2025, 1, 1)
        dt_fim = datas[1] if len(datas) > 1 else today
    return pd.date_range(dt_inicio, dt_fim).strftime('%Y-%m-%d').tolist()

# ----------------------------------------------------
# ABA 1: CALENDÁRIO SELLOUT
# ----------------------------------------------------
with aba1:
    st.subheader("Calendário de Acompanhamento Diário - Sellout")
    datas_periodo_so = render_controles_data("so")
    
    base_grade_so = [{'dt_venda': d, 'distribuidor_clean': c} for d in datas_periodo_so for c in cnpjs_todos]
    df_grid_so = pd.DataFrame(base_grade_so)
    
    if not df_sellout.empty:
        agg_so = df_sellout.groupby(['dt_venda', 'distribuidor_clean']).agg(
            Qtd_Notas=('nNF', 'nunique'),
            Itens_Vendidos=('quantidade_produtos', 'sum'),
            Faturamento=('preco_venda_total', 'sum')
        ).reset_index()
        df_cross_so = pd.merge(df_grid_so, agg_so, on=['dt_venda', 'distribuidor_clean'], how='left').fillna(0)
    else:
        df_cross_so = df_grid_so
        df_cross_so['Qtd_Notas'] = 0
        df_cross_so['Itens_Vendidos'] = 0
        df_cross_so['Faturamento'] = 0.0

    # Lógica do Farol Amarelo (Média Histórica)
    def def_status_so(r):
        med = medias_diarias_dist.get(r['distribuidor_clean'], 0)
        if r['Qtd_Notas'] == 0 or r['Itens_Vendidos'] == 0:
            return "🔴 Vermelho (Não Enviou)"
        elif r['Itens_Vendidos'] < med:
            return "🟡 Amarelo (Abaixo da Média)"
        else:
            return "🟢 Verde (OK)"

    df_cross_so['Media_Historica_Diaria'] = df_cross_so['distribuidor_clean'].map(lambda x: round(medias_diarias_dist.get(x, 0), 1))
    df_cross_so['Status'] = df_cross_so.apply(def_status_so, axis=1)
    df_cross_so['Nome_Distribuidor'] = df_cross_so['distribuidor_clean'].map(lambda x: mapa_nomes.get(x, f"CNPJ {x}"))

    res_diario_so = df_cross_so.groupby('dt_venda').agg(
        Verdes=('Status', lambda x: (x == "🟢 Verde (OK)").sum()),
        Amarelos=('Status', lambda x: (x == "🟡 Amarelo (Abaixo da Média)").sum()),
        Vermelhos=('Status', lambda x: (x == "🔴 Vermelho (Não Enviou)").sum()),
        Faturamento_Dia=('Faturamento', 'sum')
    ).reset_index()

    st.markdown("##### Resumo do Mês / Período Selecionado")
    st.dataframe(res_diario_so.assign(Faturamento_Dia=res_diario_so['Faturamento_Dia'].apply(formatar_real)), use_container_width=True)
    
    st.divider()
    col_d_sel, col_s_sel = st.columns(2)
    dia_escolhido_so = col_d_sel.selectbox("Escolha o Dia para Inspecionar:", options=datas_periodo_so, key="dia_so")
    status_escolhido_so = col_s_sel.radio("Filtrar por Sinal:", ["🔴 Vermelho (Não Enviou)", "🟡 Amarelo (Abaixo da Média)", "🟢 Verde (OK)"], key="stat_so", horizontal=True)

    detalhe_so = df_cross_so[(df_cross_so['dt_venda'] == dia_escolhido_so) & (df_cross_so['Status'] == status_escolhido_so)]
    st.write(f"**Distribuidores ({len(detalhe_so)}) no dia `{dia_escolhido_so}` com status `{status_escolhido_so}`:**")
    
    exib_so = detalhe_so.copy()
    exib_so['Faturamento'] = exib_so['Faturamento'].apply(formatar_real)
    st.dataframe(exib_so[['distribuidor_clean', 'Nome_Distribuidor', 'Qtd_Notas', 'Itens_Vendidos', 'Media_Historica_Diaria', 'Faturamento']], use_container_width=True)

# ----------------------------------------------------
# ABA 2: CALENDÁRIO ESTOQUE
# ----------------------------------------------------
with aba2:
    st.subheader("Calendário de Acompanhamento Diário - Estoque (Stock)")
    datas_periodo_st = render_controles_data("st")
    
    base_grade_st = [{'dt_estoque': d, 'cnpj_clean': c} for d in datas_periodo_st for c in cnpjs_todos]
    df_grid_st = pd.DataFrame(base_grade_st)
    
    if not df_stock.empty:
        agg_st = df_stock.groupby(['dt_estoque', 'cnpj_clean']).agg(
            Registros=('quantidade', 'count'),
            Saldo_Itens=('quantidade', 'sum'),
            Produtos_Distintos=('ean', 'nunique')
        ).reset_index()
        df_cross_st = pd.merge(df_grid_st, agg_st, on=['dt_estoque', 'cnpj_clean'], how='left').fillna(0)
    else:
        df_cross_st = df_grid_st
        df_cross_st['Registros'] = 0
        df_cross_st['Saldo_Itens'] = 0
        df_cross_st['Produtos_Distintos'] = 0

    df_cross_st['Status'] = df_cross_st['Registros'].apply(lambda x: "🟢 Verde (Estoque Recebido)" if x > 0 else "🔴 Vermelho (Estoque Ausente)")
    df_cross_st['Nome_Distribuidor'] = df_cross_st['cnpj_clean'].map(lambda x: mapa_nomes.get(x, f"CNPJ {x}"))

    res_diario_st = df_cross_st.groupby('dt_estoque').agg(
        Verdes=('Status', lambda x: (x == "🟢 Verde (Estoque Recebido)").sum()),
        Vermelhos=('Status', lambda x: (x == "🔴 Vermelho (Estoque Ausente)").sum())
    ).reset_index()

    st.markdown("##### Resumo de Envios de Estoque")
    st.dataframe(res_diario_st, use_container_width=True)
    
    st.divider()
    col_d_st, col_s_st = st.columns(2)
    dia_escolhido_st = col_d_st.selectbox("Escolha o Dia de Estoque:", options=datas_periodo_st, key="dia_st")
    status_escolhido_st = col_s_st.radio("Filtrar por Sinal:", ["🔴 Vermelho (Estoque Ausente)", "🟢 Verde (Estoque Recebido)"], key="stat_st", horizontal=True)

    detalhe_st = df_cross_st[(df_cross_st['dt_estoque'] == dia_escolhido_st) & (df_cross_st['Status'] == status_escolhido_st)]
    st.dataframe(detalhe_st[['cnpj_clean', 'Nome_Distribuidor', 'Registros', 'Produtos_Distintos', 'Saldo_Itens']], use_container_width=True)

# ----------------------------------------------------
# ABA 3: AUDITORIA SELLOUT
# ----------------------------------------------------
with aba3:
    st.subheader("Auditoria de Notas e Linhas Duplicadas em Sellout")
    if not df_sellout.empty:
        cols_p = [c for c in ['nfeId', 'nNF', 'distribuidor', 'loja', 'gtin', 'dt_proc'] if c in df_sellout.columns]
        dup_so = df_sellout[df_sellout.duplicated(subset=cols_p, keep=False)].sort_values(by=cols_p)
        st.metric("Total Linhas Duplicadas em Sellout", len(dup_so), delta_color="inverse")
        st.dataframe(dup_so, use_container_width=True)

# ----------------------------------------------------
# ABA 4: TABELA COMPLETA DE ESTOQUE
# ----------------------------------------------------
with aba4:
    st.subheader("Base de Dados Completa de Estoque Diário")
    if not df_stock.empty:
        cols_st = ['cnpj_clean', 'ean', 'quantidade', 'dt_estoque']
        df_stock_analise = df_stock.copy()
        df_stock_analise['Duplicado_no_Dia'] = df_stock_analise.duplicated(subset=cols_st, keep=False)
        df_stock_analise['Status_Linha'] = df_stock_analise['Duplicado_no_Dia'].apply(lambda x: "⚠️ Repetido no Dia" if x else "✅ Ok")
        st.dataframe(df_stock_analise[['arquivo_origem', 'data', 'cnpj_clean', 'nome_loja', 'ean', 'nome_produto', 'quantidade', 'Status_Linha']].sort_values(by=['data', 'cnpj_clean'], ascending=[False, True]), use_container_width=True)