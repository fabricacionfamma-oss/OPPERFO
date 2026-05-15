import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

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

# ==========================================
# 4. PROCESAMIENTO Y DASHBOARD
# ==========================================
with st.spinner("Sincronizando con base de datos SQL..."):
    df_sql_mes, df_sql_dia = extraer_sql_data(mes_sel, anio_sel)

st.title("🏭 Auditoría Gerencial Wiidem")

# Solo renderizamos si hay datos en SQL para ese mes/año
if not df_sql_mes.empty:
    
    # --- SECCIÓN NUEVA: LISTA GENERAL ---
    st.header("🏆 Resumen General de Operarios")
    with st.expander("Ver Listado Completo con Alertas (Rojo <80% o >100%)", expanded=True):
        
        # Nos quedamos con los datos directo de SQL
        df_resumen = df_sql_mes[['Operador_Full', 'Empresa', 'Perfo_SQL']].copy()
        df_resumen = df_resumen.rename(columns={'Perfo_SQL': 'Perfo_Mensual (%)'})
        df_resumen = df_resumen.sort_values('Perfo_Mensual (%)', ascending=False).reset_index(drop=True)
        
        # Aplicamos el estilo y HABILITAMOS LA SELECCIÓN
        evento = st.dataframe(
            df_resumen.style.map(color_performance, subset=['Perfo_Mensual (%)'])
            .format({'Perfo_Mensual (%)': '{:.1f}%'}),
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
    
    # Filtrado datos operador directo de SQL
    sql_op = df_sql_dia[df_sql_dia['Operador_Full'] == op_sel].copy()
    df_dash = sql_op[['Dia', 'Perfo_SQL']].copy().fillna(0)
    df_dash['Fecha_Label'] = df_dash['Dia'].astype(str) + f"/{mes_sel}"

    # Controles de Ajuste
    c1, c2 = st.columns(2)
    with c1:
        excluidos = st.multiselect("Eliminar días atípicos del promedio:", df_dash['Fecha_Label'].tolist())
    with c2:
        multiplicador = st.number_input("Multiplicador de Ajuste (%)", 10.0, 200.0, 100.0, 5.0)

    # Métricas
    df_v = df_dash[~df_dash['Fecha_Label'].isin(excluidos)]
    p_orig = df_dash['Perfo_SQL'].mean() if not df_dash.empty else 0
    p_base = df_v['Perfo_SQL'].mean() if not df_v.empty else 0
    p_final = p_base * (multiplicador / 100.0)

    m1, m2, m3 = st.columns(3)
    m1.metric("Perfo Mensual Original", f"{p_orig:.1f}%")
    m2.metric(f"Perfo Días Válidos", f"{p_base:.1f}%", f"{p_base-p_orig:+.1f}%")
    m3.metric("🎯 PERFO FINAL AUDITADA", f"{p_final:.1f}%", f"x {multiplicador/100:.2f}")

    # Gráfico 
    if not df_dash.empty:
        df_dash['Estado'] = df_dash['Fecha_Label'].apply(lambda x: 'Excluido' if x in excluidos else 'Válido')
        st.plotly_chart(px.bar(df_dash, x='Fecha_Label', y='Perfo_SQL', color='Estado', 
                               color_discrete_map={'Válido':'#1A5276', 'Excluido':'#D5D8DC'},
                               text=df_dash['Perfo_SQL'].apply(lambda x: f"{x:.1f}%")), use_container_width=True)
    else:
        st.warning("No hay datos diarios para este operador en el mes seleccionado.")

else:
    st.info("No se encontraron datos en la base de datos para el mes y año seleccionados.")
