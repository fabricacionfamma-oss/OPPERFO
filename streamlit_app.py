import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from sqlalchemy import create_engine

# ==========================================
# 1. CONFIGURACIÓN
# ==========================================
st.set_page_config(page_title="Auditoría Wiidem - Gerencia", layout="wide", page_icon="📊")

st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. FUNCIONES DE CONEXIÓN SQL (AUTOMÁTICO)
# ==========================================
@st.cache_data(ttl=600)
def fetch_sql_data(mes, anio):
    def query_db(conn_name):
        try:
            conn = st.connection(conn_name, type="sql")
            # Query Mensual
            q_m = f"""SELECT op.Name as Nombre, op.Docket as Legajo, 
                      SUM(p.Performance * p.ProductiveTime) / NULLIF(SUM(p.ProductiveTime), 0) as Perfo_Mes
                      FROM OPER_M_01 p JOIN OPERATOR op ON p.OperatorId = op.OperatorId 
                      WHERE p.Month = {mes} AND p.Year = {anio}
                      GROUP BY op.Name, op.Docket"""
            
            # Query Diaria
            q_d = f"""SELECT op.Name as Nombre, op.Docket as Legajo, DAY(p.Date) as Dia, 
                      SUM(p.Performance * p.ProductiveTime) / NULLIF(SUM(p.ProductiveTime), 0) as Perfo_Dia
                      FROM OPER_D_01 p JOIN OPERATOR op ON p.OperatorId = op.OperatorId 
                      WHERE MONTH(p.Date) = {mes} AND YEAR(p.Date) = {anio}
                      GROUP BY op.Name, op.Docket, DAY(p.Date)"""
            
            df_m = conn.query(q_m)
            df_d = conn.query(q_d)
            return df_m, df_d
        except:
            return pd.DataFrame(), pd.DataFrame()

    df_m_fa, df_d_fa = query_db("famma_db")
    df_m_fu, df_d_fu = query_db("fumi_db")
    
    df_mes = pd.concat([df_m_fa, df_m_fu]).drop_duplicates(subset=['Nombre', 'Legajo'])
    df_dia = pd.concat([df_d_fa, df_d_fu])
    
    # Limpieza de escala
    for df in [df_mes, df_dia]:
        if not df.empty:
            col_p = 'Perfo_Mes' if 'Perfo_Mes' in df.columns else 'Perfo_Dia'
            df[col_p] = np.where(df[col_p] > 1.5, df[col_p]/100, df[col_p]) * 100
            df['Operador_Full'] = df['Nombre'].astype(str) + " (" + df['Legajo'].astype(str) + ")"
            
    return df_mes, df_dia

# ==========================================
# 3. BARRA LATERAL: ENTRADAS Y ARCHIVOS
# ==========================================
st.sidebar.header("⚙️ Configuración")
mes_sel = st.sidebar.slider("Mes de Reporte", 1, 12, 4)
anio_sel = st.sidebar.number_input("Año", 2024, 2030, 2026)

st.sidebar.divider()
st.sidebar.header("📁 Carga de Contexto (Excel)")
file_prod = st.sidebar.file_uploader("Subir Archivo de Producción", type=["xlsx", "csv"])
file_rel = st.sidebar.file_uploader("Subir Relación Máquina-Producto", type=["xlsx", "csv"])

# ==========================================
# 4. LÓGICA DE PROCESAMIENTO (CRUCE)
# ==========================================
if file_prod and file_rel:
    # Cargar SQL automáticamente
    df_sql_mes, df_sql_dia = fetch_sql_data(mes_sel, anio_sel)
    
    # Cargar Excels
    try:
        df_p = pd.read_excel(file_prod) if file_prod.name.endswith('xlsx') else pd.read_csv(file_prod)
        df_r = pd.read_excel(file_rel) if file_rel.name.endswith('xlsx') else pd.read_csv(file_rel)
        
        # Limpieza rápida de códigos y conteo/ciclo
        def clean(t): return re.sub(r'[^A-Z0-9]', '', str(t).upper())
        df_r['Cod_Match'] = df_r['Código Producto'].apply(clean)
        df_r = df_r.drop_duplicates('Cod_Match')
        
        # Filtro de fábrica desde el Excel
        df_p = df_p[df_p['Fábrica'].astype(str).str.contains('SOLDADURA|ESTAMPADO', case=False, na=False)].copy()
        df_p['Pzas_Real'] = df_p['Buenas'] + df_p.get('Retrabajo', 0) + df_p.get('Observadas', 0)
        df_p['Cod_Match'] = df_p['Código Producto/Semielaborado'].apply(clean)
        
        # Unpivot y unión con SQL por Nombre
        map_nombres = dict(zip(df_sql_mes['Nombre'].str.upper(), df_sql_mes['Operador_Full']))
        col_users = [c for c in df_p.columns if 'Usuario' in c]
        df_melt = df_p.melt(id_vars=['Fecha', 'Min_Prod', 'Pzas_Real', 'Cod_Match'], value_vars=col_users, value_name='Nombre_Ex').dropna()
        df_melt['Operador_Full'] = df_melt['Nombre_Ex'].str.upper().map(map_nombres)
        df_melt = df_melt.dropna(subset=['Operador_Full'])
        
        # Piezas Esperadas
        df_final = pd.merge(df_melt, df_r[['Cod_Match', 'Tiempo Ciclo']], on='Cod_Match', how='left')
        df_final['Pzas_Esp'] = df_final['Min_Prod'] / df_final['Tiempo Ciclo'].fillna(1).replace(0,1)
        df_final['Dia'] = pd.to_datetime(df_final['Fecha']).dt.day
        
        df_daily_ex = df_final.groupby(['Operador_Full', 'Dia']).agg({'Pzas_Real':'sum', 'Pzas_Esp':'sum', 'Min_Prod':'sum'}).reset_index()
        
    except Exception as e:
        st.error(f"Error procesando archivos: {e}")
        st.stop()

    # ==========================================
    # 5. INTERFAZ GERENCIAL
    # ==========================================
    st.title("🏭 Auditoría de Performance")
    
    op_list = sorted(df_daily_ex['Operador_Full'].unique())
    op_sel = st.selectbox("Seleccione Operador para Auditar:", op_list)
    
    # Datos específicos
    res_op = df_daily_ex[df_daily_ex['Operador_Full'] == op_sel].copy()
    sql_op = df_sql_dia[df_sql_dia['Operador_Full'] == op_sel].copy()
    
    # Unión Final
    df_dashboard = pd.merge(res_op, sql_op[['Dia', 'Perfo_Dia']], on='Dia', how='left').fillna(0)
    df_dashboard['Fecha_Label'] = df_dashboard['Dia'].apply(lambda x: f"{x}/{mes_sel}")

    col_filtros, col_ajuste = st.columns(2)
    with col_filtros:
        excluidos = st.multiselect("Excluir días de la evaluación:", df_dashboard['Fecha_Label'].tolist())
    with col_ajuste:
        ajuste_manual = st.slider("Ajuste de Performance Gerencial (%)", -20.0, 20.0, 0.0, 0.5)

    # Filtrado de días
    df_valido = df_dashboard[~df_dashboard['Fecha_Label'].isin(excluidos)]
    
    # Métricas Finales
    p_orig = df_dashboard['Perfo_Dia'].mean()
    p_valid = df_valido['Perfo_Dia'].mean() if not df_valido.empty else 0
    p_final = p_valid + ajuste_manual
    
    m1, m2, m3 = st.columns(3)
    m1.metric("OEE Mensual Original", f"{p_orig:.1f}%")
    m2.metric("OEE Días Válidos", f"{p_valid:.1f}%", f"{p_valid-p_orig:+.1f}%")
    m3.metric("🎯 OEE FINAL AUDITADA", f"{p_final:.1f}%", f"{ajuste_manual:+.1f}% Ajuste")

    # Gráfico
    df_dashboard['Estado'] = df_dashboard['Fecha_Label'].apply(lambda x: 'Excluido' if x in excluidos else 'Válido')
    fig = px.bar(df_dashboard, x='Fecha_Label', y='Perfo_Dia', color='Estado', 
                 color_discrete_map={'Válido':'#2E86C1', 'Excluido':'#D5D8DC'},
                 title="Performance Diaria (Fuente: SQL Wiidem)")
    fig.add_hline(y=p_final, line_dash="dot", line_color="red")
    st.plotly_chart(fig, use_container_width=True)

    # Tabla
    st.subheader("📝 Detalle Operativo de Días Válidos")
    df_valido['Cadencia'] = df_valido['Pzas_Real'] / (df_valido['Min_Prod']/60).replace(0,1)
    st.dataframe(df_valido[['Fecha_Label', 'Pzas_Real', 'Pzas_Esp', 'Cadencia', 'Perfo_Dia']], 
                 column_config={"Perfo_Dia": "OEE SQL (%)", "Cadencia": "Pzas/Hora"},
                 hide_index=True, use_container_width=True)

else:
    st.info("👋 Por favor, sube los archivos de Producción y Relaciones en la barra lateral para comenzar.")
st.dataframe(df_filtrado[['Fecha_Str', 'Pzas_Real', 'Pzas_Esp', 'Cadencia_PH', 'Perfo_SQL']], hide_index=True)
