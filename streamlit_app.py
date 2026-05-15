import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import re

# ==========================================
# 1. CONFIGURACIÓN DE LA PÁGINA
# ==========================================
st.set_page_config(page_title="Panel Gerencial - Wiidem", layout="wide", page_icon="🏭")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border-left: 5px solid #1A5276; }
    </style>
    """, unsafe_allow_html=True)

def limpiar_codigo(t):
    if pd.isna(t): return ""
    return re.sub(r'[^A-Z0-9]', '', str(t).upper())

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
        except Exception as e:
            st.warning(f"No se pudo conectar a {conn_name}: {e}")
            return pd.DataFrame(), pd.DataFrame()

    df_m_fa, df_d_fa = fetch_db("famma_db")
    df_m_fu, df_d_fu = fetch_db("fumi_db")
    
    df_mes = pd.concat([df_m_fa, df_m_fu], ignore_index=True)
    df_dia = pd.concat([df_d_fa, df_d_fu], ignore_index=True)
    
    for df in [df_mes, df_dia]:
        if not df.empty:
            df['Perfo_SQL'] = np.where(df['Perfo_SQL'] > 1.5, df['Perfo_SQL']/100, df['Perfo_SQL']) * 100
            df['Operador_Full'] = df['Nombre'].astype(str) + " (" + df['Legajo'].astype(str) + ")"
            
    return df_mes.drop_duplicates(subset=['Operador_Full']), df_dia

# ==========================================
# 3. BARRA LATERAL (FILTROS Y ARCHIVOS)
# ==========================================
st.sidebar.header("📅 Periodo a Auditar")
mes_sel = st.sidebar.slider("Mes", 1, 12, 4)
anio_sel = st.sidebar.number_input("Año", 2024, 2030, 2026)

st.sidebar.divider()
st.sidebar.header("📁 Carga de Archivos")
archivos_prod = st.sidebar.file_uploader("1. Producción (Excel/CSV)", type=["xlsx", "csv"], accept_multiple_files=True)
archivo_rel = st.sidebar.file_uploader("2. Relación Máquina-Producto", type=["xlsx", "csv"])

# ==========================================
# 4. PROCESAMIENTO HÍBRIDO (EXCEL + SQL)
# ==========================================
if archivos_prod and archivo_rel:
    with st.spinner("Procesando datos y sincronizando con base de datos Wiidem..."):
        # 1. SQL
        df_sql_mes, df_sql_dia = extraer_sql_data(mes_sel, anio_sel)
        
        # 2. Excel Relaciones
        df_rel_raw = pd.read_excel(archivo_rel) if archivo_rel.name.endswith('xlsx') else pd.read_csv(archivo_rel)
        df_rel = df_rel_raw[['Código Producto', 'Tiempo Ciclo']].copy()
        df_rel.columns = ['Cod_Orig', 'TC_Master']
        df_rel['TC_Master'] = pd.to_numeric(df_rel['TC_Master'].astype(str).str.replace(',','.'), errors='coerce')
        df_rel['Cod_Match'] = df_rel['Cod_Orig'].apply(limpiar_codigo)
        df_rel = df_rel.dropna(subset=['TC_Master']).drop_duplicates('Cod_Match', keep='last')

        # 3. Excel Producción
        df_p_list = []
        for file in archivos_prod:
            df_temp = pd.read_excel(file) if file.name.endswith('xlsx') else pd.read_csv(file)
            df_p_list.append(df_temp)
            
        df_p = pd.concat(df_p_list, ignore_index=True)
        df_p.columns = [str(c).strip() for c in df_p.columns]
        df_p.rename(columns={'Fábrica': 'Planta', 'Máquina':'Maquina', 'Código Producto/Semielaborado':'Codigo_Prod', 'Tiempo Producción (Min)':'Min_Prod'}, inplace=True, errors='ignore')
        
        # Filtro de Planta
        if 'Planta' in df_p.columns:
            df_p = df_p[df_p['Planta'].astype(str).str.contains('SOLDADURA|ESTAMPADO', case=False, na=False)].copy()
        
        df_p['Pzas_Real'] = df_p.get('Buenas', 0) + df_p.get('Retrabajo', 0) + df_p.get('Observadas', 0)
        df_p['Min_Prod'] = pd.to_numeric(df_p['Min_Prod'].astype(str).str.replace(',','.'), errors='coerce').fillna(0)
        df_p['Cod_Match'] = df_p['Codigo_Prod'].apply(limpiar_codigo)
        
        # --- SOLUCIÓN DEL ERROR DE CELDAS VACÍAS AQUÍ ---
        c_ciclo = next((c for c in df_p.columns if 'conteo' in c.lower() or 'ciclo orden' in c.lower()), None)
        if c_ciclo:
            df_p['Pzas_Por_Ciclo'] = np.where(df_p[c_ciclo].astype(str).str.contains('2', na=False), 2.0, 1.0)
        else:
            df_p['Pzas_Por_Ciclo'] = 1.0
        # ------------------------------------------------

        # Unpivot
        col_usuarios = [c for c in df_p.columns if 'Usuario' in c]
        df_melted = df_p.melt(id_vars=['Planta', 'Fecha', 'Min_Prod', 'Pzas_Real', 'Pzas_Por_Ciclo', 'Cod_Match'], 
                              value_vars=col_usuarios, value_name='Nombre_Excel').dropna(subset=['Nombre_Excel'])
        df_melted = df_melted[~df_melted['Nombre_Excel'].astype(str).str.lower().str.contains('nan|usuario|admin|-|^$')]

        # Cruce Nombres -> Legajos
        if not df_sql_mes.empty:
            map_nombres = dict(zip(df_sql_mes['Nombre'].str.strip().str.upper(), df_sql_mes['Operador_Full']))
            df_melted['Nombre_Upper'] = df_melted['Nombre_Excel'].astype(str).str.strip().str.upper()
            df_melted['Operador_Full'] = df_melted['Nombre_Upper'].map(map_nombres)
            df_melted['Operador_Full'] = df_melted['Operador_Full'].fillna(df_melted['Nombre_Excel'] + " (S/L)")
        else:
            df_melted['Operador_Full'] = df_melted['Nombre_Excel'] + " (S/L)"

        # Cálculos de Producción
        df_excel = pd.merge(df_melted, df_rel[['Cod_Match', 'TC_Master']], on='Cod_Match', how='left')
        df_excel['TC_Master'] = df_excel['TC_Master'].fillna(1.0)
        df_excel['Pzas_Esp'] = (df_excel['Min_Prod'] / df_excel['TC_Master'].replace(0, 1)) * df_excel['Pzas_Por_Ciclo']
        df_excel['Dia'] = pd.to_datetime(df_excel['Fecha'], errors='coerce').dt.day
        
        df_daily_excel = df_excel.groupby(['Operador_Full', 'Fecha', 'Dia']).agg({'Pzas_Real':'sum', 'Pzas_Esp':'sum', 'Min_Prod':'sum'}).reset_index()

        # Cruce con SQL Diario
        if not df_sql_dia.empty:
            df_sql_dia_grp = df_sql_dia.groupby(['Operador_Full', 'Dia']).agg({'Perfo_SQL':'mean'}).reset_index()
            df_final_diario = pd.merge(df_daily_excel, df_sql_dia_grp, on=['Operador_Full', 'Dia'], how='left').fillna(0)
        else:
            df_final_diario = df_daily_excel.copy()
            df_final_diario['Perfo_SQL'] = 0.0
            
        df_final_diario['Fecha_Label'] = df_final_diario['Dia'].astype(str) + f"/{mes_sel}"

    # ==========================================
    # 5. DASHBOARD GERENCIAL
    # ==========================================
    st.title("🏭 Auditoría Gerencial de Performance")
    
    operadores_disponibles = sorted(df_final_diario['Operador_Full'].unique())
    op_sel = st.selectbox("👤 Seleccionar Operador:", operadores_disponibles)
    
    df_op = df_final_diario[df_final_diario['Operador_Full'] == op_sel].sort_values('Dia').copy()
    
    st.divider()
    
    # --- CONTROLES DE AJUSTE ---
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🛠️ 1. Exclusión de Días")
        st.write("Selecciona los días que NO deben promediarse:")
        dias_excluidos = st.multiselect("Días a eliminar:", df_op['Fecha_Label'].tolist())
    with c2:
        st.subheader("⚖️ 2. Multiplicador de Performance")
        st.write("Ajusta el porcentaje (100% = Sin cambios, 110% = Suma 10% extra al promedio)")
        multiplicador = st.number_input("Multiplicador (%)", min_value=10.0, max_value=200.0, value=100.0, step=5.0)

    # --- CÁLCULOS AUDITADOS ---
    # 1. Filtramos los días
    df_valido = df_op[~df_op['Fecha_Label'].isin(dias_excluidos)]
    
    # 2. Promedios
    perfo_original_mensual = df_op['Perfo_SQL'].mean() if not df_op.empty else 0
    perfo_base_dias_validos = df_valido['Perfo_SQL'].mean() if not df_valido.empty else 0
    
    # 3. Aplicamos el multiplicador
    perfo_final_auditada = perfo_base_dias_validos * (multiplicador / 100.0)

    # --- MÉTRICAS VISUALES ---
    st.write("")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("OEE Promedio Original", f"{perfo_original_mensual:.1f}%")
    m2.metric(f"OEE Base ({len(df_valido)} días válidos)", f"{perfo_base_dias_validos:.1f}%", f"{(perfo_base_dias_validos - perfo_original_mensual):+.1f}% vs Orig.")
    m3.metric("🎯 OEE FINAL AUDITADA", f"{perfo_final_auditada:.1f}%", f"x {multiplicador/100:.2f} (Multiplicador)")
    m4.metric("Total Piezas Validadas", f"{df_valido['Pzas_Real'].sum():,.0f}")

    st.divider()
    
    col_grafico, col_tabla = st.columns([1.2, 1])
    
    with col_grafico:
        st.subheader("📊 Gráfico de Evolución Diaria")
        df_op['Estado'] = df_op['Fecha_Label'].apply(lambda x: 'Excluido' if x in dias_excluidos else 'Válido')
        
        fig = px.bar(df_op, x='Fecha_Label', y='Perfo_SQL', color='Estado',
                     color_discrete_map={'Válido':'#1A5276', 'Excluido':'#D5D8DC'},
                     text=df_op['Perfo_SQL'].apply(lambda x: f"{x:.1f}%"))
        
        # Línea de la meta ajustada
        fig.add_hline(y=perfo_final_auditada, line_dash="dash", line_color="red", 
                      annotation_text=f"Meta Final: {perfo_final_auditada:.1f}%", 
                      annotation_position="top left")
        
        fig.update_traces(textposition='outside')
        fig.update_layout(yaxis_title="Performance OEE (%)", xaxis_title="Día", plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)

    with col_tabla:
        st.subheader("📝 Tabla de Producción (Días Válidos)")
        df_valido['Cadencia (P/H)'] = np.where(df_valido['Min_Prod'] > 0, df_valido['Pzas_Real'] / (df_valido['Min_Prod']/60.0), 0)
        df_valido['Diferencia'] = df_valido['Pzas_Real'] - df_valido['Pzas_Esp']
        
        df_mostrar = df_valido[['Fecha_Label', 'Perfo_SQL', 'Pzas_Real', 'Pzas_Esp', 'Diferencia', 'Cadencia (P/H)']].copy()
        df_mostrar.columns = ['Día', 'OEE SQL (%)', 'Pz Reales', 'Pz Esperadas', 'Diferencia', 'Cadencia P/H']
        
        st.dataframe(df_mostrar.style.format({
            'OEE SQL (%)': '{:.1f}%',
            'Pz Reales': '{:,.0f}',
            'Pz Esperadas': '{:,.0f}',
            'Diferencia': '{:+,.0f}',
            'Cadencia P/H': '{:.1f}'
        }), hide_index=True, use_container_width=True)

else:
    st.info("👋 Por favor, sube los archivos de Producción (pueden ser varios) y el maestro de Relaciones en la barra lateral.")
