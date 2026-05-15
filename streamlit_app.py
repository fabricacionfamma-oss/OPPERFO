import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import re

# ==========================================
# 1. CONFIGURACIÓN DE LA PÁGINA
# ==========================================
st.set_page_config(page_title="Panel Gerencial - Auditoría", layout="wide", page_icon="📊")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border-left: 5px solid #1A5276; }
    </style>
    """, unsafe_allow_html=True)

def limpiar_codigo(t):
    if pd.isna(t): return ""
    return re.sub(r'[^A-Z0-9]', '', str(t).upper())

# Función para aplicar colores a la tabla
def color_performance(val):
    if val > 100 or val < 80:
        return 'color: #D32F2F; font-weight: bold;' # Rojo para desvíos
    else:
        return 'color: #2E7D32;' # Verde para rango normal (80-100)

# ==========================================
# 2. MOTOR SQL (AUTOMÁTICO)
# ==========================================
@st.cache_data(ttl=600)
def extraer_sql_data(mes, anio):
    def fetch_db(conn_name):
        try:
            conn = st.connection(conn_name, type="sql")
            q_m = f"""SELECT op.Name as Nombre, op.Docket as Legajo, 
                      SUM(p.Performance * p.ProductiveTime) / NULLIF(SUM(p.ProductiveTime), 0) as Perfo_SQL
                      FROM OPER_M_01 p JOIN OPERATOR op ON p.OperatorId = op.OperatorId 
                      WHERE p.Month = {mes} AND p.Year = {anio}
                      GROUP BY op.Name, op.Docket"""
            q_d = f"""SELECT op.Name as Nombre, op.Docket as Legajo, DAY(p.Date) as Dia, 
                      SUM(p.Performance * p.ProductiveTime) / NULLIF(SUM(p.ProductiveTime), 0) as Perfo_SQL
                      FROM OPER_D_01 p JOIN OPERATOR op ON p.OperatorId = op.OperatorId 
                      WHERE MONTH(p.Date) = {mes} AND YEAR(p.Date) = {anio}
                      GROUP BY op.Name, op.Docket, DAY(p.Date)"""
            return conn.query(q_m), conn.query(q_d)
        except Exception:
            return pd.DataFrame(), pd.DataFrame()

    df_m_fa, df_d_fa = fetch_db("famma_db")
    df_m_fu, df_d_fu = fetch_db("fumi_db")
    
    # Marcamos la empresa antes de unir
    df_m_fa['Empresa'] = 'FAMMA'
    df_m_fu['Empresa'] = 'FUMISCOR'
    
    df_mes = pd.concat([df_m_fa, df_m_fu], ignore_index=True)
    df_dia = pd.concat([df_d_fa, df_d_fu], ignore_index=True)
    
    for df in [df_mes, df_dia]:
        if not df.empty:
            df['Perfo_SQL'] = np.where(df['Perfo_SQL'] > 1.5, df['Perfo_SQL']/100, df['Perfo_SQL']) * 100
            df['Operador_Full'] = df['Nombre'].astype(str).str.upper() + " (" + df['Legajo'].astype(str) + ")"
            
    return df_mes.drop_duplicates(subset=['Operador_Full']), df_dia

# ==========================================
# 3. BARRA LATERAL
# ==========================================
st.sidebar.header("📅 Periodo a Auditar")
mes_sel = st.sidebar.slider("Mes", 1, 12, 4)
anio_sel = st.sidebar.number_input("Año", 2024, 2030, 2026)

st.sidebar.divider()
st.sidebar.header("📁 Carga de Archivos")
archivos_prod = st.sidebar.file_uploader("1. Producción (Excel/CSV)", type=["xlsx", "csv"], accept_multiple_files=True)
archivo_rel = st.sidebar.file_uploader("2. Relación Máquina-Producto", type=["xlsx", "csv"])

# ==========================================
# 4. PROCESAMIENTO
# ==========================================
if archivos_prod and archivo_rel:
    with st.spinner("Sincronizando con Wiidem..."):
        df_sql_mes, df_sql_dia = extraer_sql_data(mes_sel, anio_sel)
        
        # Procesar Relaciones
        df_rel_raw = pd.read_excel(archivo_rel) if archivo_rel.name.endswith('xlsx') else pd.read_csv(archivo_rel)
        df_rel = df_rel_raw[['Código Producto', 'Tiempo Ciclo']].copy()
        df_rel.columns = ['Cod_Orig', 'TC_Master']
        df_rel['TC_Master'] = pd.to_numeric(df_rel['TC_Master'].astype(str).str.replace(',','.'), errors='coerce')
        df_rel['Cod_Match'] = df_rel['Cod_Orig'].apply(limpiar_codigo)
        df_rel = df_rel.dropna(subset=['TC_Master']).drop_duplicates('Cod_Match')

        # Procesar Producción
        df_p_list = [pd.read_excel(f) if f.name.endswith('xlsx') else pd.read_csv(f) for f in archivos_prod]
        df_p = pd.concat(df_p_list, ignore_index=True)
        df_p.columns = [str(c).strip() for c in df_p.columns]
        df_p.rename(columns={'Fábrica': 'Planta', 'Máquina':'Maquina', 'Código Producto/Semielaborado':'Codigo_Prod', 'Tiempo Producción (Min)':'Min_Prod'}, inplace=True, errors='ignore')
        
        # Filtro Planta y Limpieza
        df_p = df_p[df_p['Planta'].astype(str).str.contains('SOLDADURA|ESTAMPADO', case=False, na=False)].copy()
        df_p['Pzas_Real'] = df_p['Buenas'] + df_p.get('Retrabajo', 0) + df_p.get('Observadas', 0)
        df_p['Cod_Match'] = df_p['Codigo_Prod'].apply(limpiar_codigo)
        
        c_ciclo = next((c for c in df_p.columns if 'conteo' in c.lower() or 'ciclo orden' in c.lower()), None)
        df_p['Pzas_Por_Ciclo'] = np.where(df_p[c_ciclo].astype(str).str.contains('2', na=False), 2.0, 1.0) if c_ciclo else 1.0

        # Unpivot y unión con SQL
        col_usuarios = [c for c in df_p.columns if 'Usuario' in c]
        df_melt = df_p.melt(id_vars=['Planta', 'Maquina', 'Fecha', 'Min_Prod', 'Pzas_Real', 'Cod_Match', 'Pzas_Por_Ciclo'], 
                            value_vars=col_usuarios, value_name='Nombre_Ex').dropna()
        
        map_nombres = dict(zip(df_sql_mes['Nombre'].str.strip().str.upper(), df_sql_mes['Operador_Full']))
        df_melt['Operador_Full'] = df_melt['Nombre_Ex'].str.strip().str.upper().map(map_nombres)
        df_melt = df_melt.dropna(subset=['Operador_Full'])

        # Cruce para piezas y cadencia
        df_cruce = pd.merge(df_melt, df_rel[['Cod_Match', 'TC_Master']], on='Cod_Match', how='left')
        df_cruce['Pzas_Esp'] = (df_cruce['Min_Prod'] / df_cruce['TC_Master'].fillna(1).replace(0,1)) * df_cruce['Pzas_Por_Ciclo']
        df_cruce['Dia'] = pd.to_datetime(df_cruce['Fecha'], errors='coerce').dt.day

    # ==========================================
    # 5. DASHBOARD - SECCIONES
    # ==========================================
    st.title("🏭 Auditoría Gerencial Wiidem")
    
    # --- SECCIÓN NUEVA: LISTA GENERAL ---
    st.header("🏆 Resumen General de Operarios")
    with st.expander("Ver Listado Completo con Alertas (Rojo <80% o >100%)", expanded=True):
        # Unimos la Planta (del Excel) con la Perfo (de SQL)
        df_resumen = pd.merge(
            df_melt.groupby('Operador_Full').agg({'Planta':'first'}).reset_index(),
            df_sql_mes[['Operador_Full', 'Empresa', 'Perfo_SQL']],
            on='Operador_Full', how='inner'
        )
        
        df_resumen = df_resumen.rename(columns={'Perfo_SQL': 'OEE_Mensual (%)'})
        df_resumen = df_resumen.sort_values('OEE_Mensual (%)', ascending=False).reset_index(drop=True)
        
        # Aplicamos el estilo y HABILITAMOS LA SELECCIÓN
        evento = st.dataframe(
            df_resumen.style.map(color_performance, subset=['OEE_Mensual (%)'])
            .format({'OEE_Mensual (%)': '{:.1f}%'}),
            use_container_width=True, hide_index=True,
            on_select="rerun",
            selection_mode="single-row"
        )

        # Guardar la selección en el estado de la sesión
        if len(evento.selection.rows) > 0:
            fila_seleccionada = evento.selection.rows[0]
            op_click = df_resumen.iloc[fila_seleccionada]['Operador_Full']
            st.session_state['operador_seleccionado'] = op_click

    st.divider()
    
    # --- SECCIÓN: AUDITORÍA INDIVIDUAL ---
    st.header("🔍 Auditoría Individual")
    
    lista_operadores = sorted(df_resumen['Operador_Full'].unique())

    # Determinar el índice a mostrar por defecto basado en la selección
    if 'operador_seleccionado' in st.session_state and st.session_state['operador_seleccionado'] in lista_operadores:
        indice_default = lista_operadores.index(st.session_state['operador_seleccionado'])
    else:
        indice_default = 0

    op_sel = st.selectbox(
        "Seleccione Operador para analizar detalle diario:", 
        lista_operadores,
        index=indice_default
    )
    
    # Actualizamos el estado por si cambia manualmente el desplegable
    st.session_state['operador_seleccionado'] = op_sel
    
    # Filtrado datos operador
    df_op_dia = df_cruce[df_cruce['Operador_Full'] == op_sel].groupby('Dia').agg({'Pzas_Real':'sum', 'Pzas_Esp':'sum', 'Min_Prod':'sum'}).reset_index()
    sql_op = df_sql_dia[df_sql_dia['Operador_Full'] == op_sel].copy()
    df_dash = pd.merge(df_op_dia, sql_op[['Dia', 'Perfo_SQL']], on='Dia', how='left').fillna(0)
    df_dash['Fecha_Label'] = df_dash['Dia'].astype(str) + f"/{mes_sel}"

    # Controles de Ajuste
    c1, c2 = st.columns(2)
    with c1:
        excluidos = st.multiselect("Eliminar días atípicos del promedio:", df_dash['Fecha_Label'].tolist())
    with c2:
        multiplicador = st.number_input("Multiplicador de Ajuste (%)", 10.0, 200.0, 100.0, 5.0)

    # Métricas
    df_v = df_dash[~df_dash['Fecha_Label'].isin(excluidos)]
    p_orig = df_dash['Perfo_SQL'].mean()
    p_base = df_v['Perfo_SQL'].mean() if not df_v.empty else 0
    p_final = p_base * (multiplicador / 100.0)

    m1, m2, m3 = st.columns(3)
    m1.metric("OEE Mensual Original", f"{p_orig:.1f}%")
    m2.metric(f"OEE Días Válidos", f"{p_base:.1f}%", f"{p_base-p_orig:+.1f}%")
    m3.metric("🎯 OEE FINAL AUDITADA", f"{p_final:.1f}%", f"x {multiplicador/100:.2f}")

    # Gráfico y Tabla de Máquinas
    df_dash['Estado'] = df_dash['Fecha_Label'].apply(lambda x: 'Excluido' if x in excluidos else 'Válido')
    st.plotly_chart(px.bar(df_dash, x='Fecha_Label', y='Perfo_SQL', color='Estado', 
                           color_discrete_map={'Válido':'#1A5276', 'Excluido':'#D5D8DC'},
                           text=df_dash['Perfo_SQL'].apply(lambda x: f"{x:.1f}%")), use_container_width=True)

    st.subheader("📋 Desglose por Máquina y Cadencia")
    df_maq = df_cruce[(df_cruce['Operador_Full'] == op_sel) & (~(df_cruce['Dia'].astype(str) + f"/{mes_sel}").isin(excluidos))].copy()
    df_maq['Cadencia P/H'] = df_maq['Pzas_Real'] / (df_maq['Min_Prod']/60).replace(0,1)
    st.dataframe(df_maq[['Fecha', 'Maquina', 'Pzas_Real', 'Cadencia P/H']].sort_values('Fecha'), use_container_width=True, hide_index=True)

else:
    st.info("👋 Sube los archivos en la barra lateral para generar el ranking y la auditoría.")
