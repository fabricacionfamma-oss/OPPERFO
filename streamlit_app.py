import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from fpdf import FPDF

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

# Función para aplicar colores a la tabla interactiva
def color_performance(val):
    if val > 100 or val < 80:
        return 'color: #D32F2F; font-weight: bold;' # Rojo para desvíos
    else:
        return 'color: #2E7D32;' # Verde para rango normal (80-100)

# ==========================================
# 2. MOTOR SQL (CON DEBÚGUEO DE ERRORES)
# ==========================================
@st.cache_data(ttl=600)
def extraer_sql_data(mes, anio):
    def fetch_db(conn_name):
        try:
            conn = st.connection(conn_name, type="sql")
            
            # 1. Consulta Mensual
            q_m = f"""SELECT op.Name as Nombre, op.Docket as Legajo, 
                      SUM(p.Performance * p.ProductiveTime) / NULLIF(SUM(p.ProductiveTime), 0) as Perfo_SQL
                      FROM OPER_M_01 p JOIN OPERATOR op ON p.OperatorId = op.OperatorId 
                      WHERE p.Month = {mes} AND p.Year = {anio}
                      GROUP BY op.Name, op.Docket"""
            
            # 2. Consulta Diaria
            q_d = f"""SELECT op.Name as Nombre, op.Docket as Legajo, DAY(p.Date) as Dia, 
                      SUM(p.Performance * p.ProductiveTime) / NULLIF(SUM(p.ProductiveTime), 0) as Perfo_SQL
                      FROM OPER_D_01 p JOIN OPERATOR op ON p.OperatorId = op.OperatorId 
                      WHERE MONTH(p.Date) = {mes} AND YEAR(p.Date) = {anio}
                      GROUP BY op.Name, op.Docket, DAY(p.Date)"""
            
            # 3. Consulta de Máquinas (Revisar si 'p.Machine' se llama así en tu BD)
            q_mac = f"""SELECT op.Name as Nombre, op.Docket as Legajo, p.Machine as Maquina
                        FROM OPER_D_01 p JOIN OPERATOR op ON p.OperatorId = op.OperatorId
                        WHERE MONTH(p.Date) = {mes} AND YEAR(p.Date) = {anio}
                        GROUP BY op.Name, op.Docket, p.Machine"""
                        
            return conn.query(q_m), conn.query(q_d), conn.query(q_mac)
        except Exception as e:
            # Captura y muestra el error real en la interfaz de Streamlit
            st.error(f"❌ Error en la base de datos '{conn_name}': {e}")
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    df_m_fa, df_d_fa, df_mac_fa = fetch_db("famma_db")
    df_m_fu, df_d_fu, df_mac_fu = fetch_db("fumi_db")
    
    # Marcamos la empresa antes de unir
    df_m_fa['Empresa'] = 'FAMMA'
    df_m_fu['Empresa'] = 'FUMISCOR'
    
    df_mes = pd.concat([df_m_fa, df_m_fu], ignore_index=True)
    df_dia = pd.concat([df_d_fa, df_d_fu], ignore_index=True)
    df_mac = pd.concat([df_mac_fa, df_mac_fu], ignore_index=True)
    
    # Filtro: Eliminar operarios con legajo que empiece con FW
    if not df_mes.empty:
        df_mes = df_mes[~df_mes['Legajo'].astype(str).str.upper().str.startswith('FW')]
    if not df_dia.empty:
        df_dia = df_dia[~df_dia['Legajo'].astype(str).str.upper().str.startswith('FW')]
    if not df_mac.empty:
        df_mac = df_mac[~df_mac['Legajo'].astype(str).str.upper().str.startswith('FW')]
    
    # Consolidar máquinas por operario (un string separado por comas)
    if not df_mac.empty:
        df_mac['Operador_Full'] = df_mac['Nombre'].astype(str).str.upper() + " (" + df_mac['Legajo'].astype(str) + ")"
        maquinas_series = df_mac.groupby('Operador_Full')['Maquina'].apply(
            lambda x: ', '.join(sorted(list(set(x.dropna().astype(str)))))
        )
    else:
        maquinas_series = pd.Series(dtype=str)
    
    # Procesar métricas y nombres full
    for df in [df_mes, df_dia]:
        if not df.empty:
            df['Perfo_SQL'] = np.where(df['Perfo_SQL'] > 1.5, df['Perfo_SQL']/100, df['Perfo_SQL']) * 100
            df['Operador_Full'] = df['Nombre'].astype(str).str.upper() + " (" + df['Legajo'].astype(str) + ")"
            
    # Mapear listado de máquinas al dataframe mensual
    if not df_mes.empty:
        df_mes['Máquinas'] = df_mes['Operador_Full'].map(maquinas_series).fillna('Sin registrar')
        
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

if not df_sql_mes.empty:
    
    # --- SECCIÓN: LISTA GENERAL ---
    st.header("🏆 Resumen General de Operarios")
    with st.expander("Ver Listado Completo con Alertas (Rojo <80% o >100%)", expanded=True):
        
        df_resumen = df_sql_mes[['Operador_Full', 'Empresa', 'Perfo_SQL', 'Máquinas']].copy()
        df_resumen = df_resumen.rename(columns={'Perfo_SQL': 'Perfo_Mensual (%)'})
        df_resumen = df_resumen.sort_values('Perfo_Mensual (%)', ascending=False).reset_index(drop=True)
        
        evento = st.dataframe(
            df_resumen.style.map(color_performance, subset=['Perfo_Mensual (%)'])
            .format({'Perfo_Mensual (%)': '{:.1f}%'}),
            use_container_width=True, hide_index=True,
            on_select="rerun",
            selection_mode="single-row"
        )

        if len(evento.selection.rows) > 0:
            fila_seleccionada = evento.selection.rows[0]
            op_click = df_resumen.iloc[fila_seleccionada]['Operador_Full']
            st.session_state['operador_seleccionado'] = op_click

        # --- GENERACIÓN DE REPORTES (CSV Y PDF) ---
        st.write("") 
        col1, col2 = st.columns(2)
        
        # Descarga CSV
        csv_data = df_resumen.to_csv(index=False).encode('utf-8')
        col1.download_button(
            label="📥 Descargar Listado (CSV)",
            data=csv_data,
            file_name=f"reporte_operarios_{mes_sel}_{anio_sel}.csv",
            mime="text/csv",
            use_container_width=True
        )
        
        # Función interna para estructurar PDF horizontal (A4 Landscape)
        def crear_pdf(df, mes, anio):
            pdf = FPDF(orientation='L', unit='mm', format='A4')
            pdf.add_page()
            
            # Título
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(0, 10, f"Auditoría Gerencial Wiidem - Periodo: {mes}/{anio}", ln=True, align='C')
            pdf.ln(5)
            
            # Cabecera de Tabla
            pdf.set_font("Arial", 'B', 10)
            pdf.set_fill_color(26, 82, 118) # Azul corporativo
            pdf.set_text_color(255, 255, 255) # Blanco
            
            col_widths = [75, 25, 25, 145] 
            headers = ['Operador (Legajo)', 'Planta', 'Perfo', 'Máquinas Operadas']
            
            for i in range(len(headers)):
                pdf.cell(col_widths[i], 8, headers[i], border=1, fill=True, align='C')
            pdf.ln()
            
            # Filas de Datos
            pdf.set_font("Arial", '', 9)
            
            for index, row in df.iterrows():
                perfo = row['Perfo_Mensual (%)']
                
                # Formato condicional de color según desvíos
                if perfo < 80 or perfo > 100:
                    pdf.set_text_color(211, 47, 47) # Rojo
                else:
                    pdf.set_text_color(46, 125, 50) # Verde
                
                pdf.cell(col_widths[0], 8, str(row['Operador_Full'])[:45], border=1)
                pdf.cell(col_widths[1], 8, str(row['Empresa']), border=1, align='C')
                pdf.cell(col_widths[2], 8, f"{perfo:.1f}%", border=1, align='C')
                
                # Texto negro estándar para la lista de máquinas
                pdf.set_text_color(0, 0, 0)
                pdf.cell(col_widths[3], 8, str(row['Máquinas'])[:90], border=1)
                pdf.ln()
                
            return pdf.output(dest='S').encode('latin1')

        try:
            pdf_bytes = crear_pdf(df_resumen, mes_sel, anio_sel)
            col2.download_button(
                label="📄 Descargar Listado (PDF)",
                data=pdf_bytes,
                file_name=f"reporte_operarios_{mes_sel}_{anio_sel}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        except NameError:
            col2.error("Falta instalar la librería fpdf (Ejecuta: pip install fpdf)")

    st.divider()
    
    # --- SECCIÓN: AUDITORÍA INDIVIDUAL ---
    st.header("🔍 Auditoría Individual")
    
    lista_operadores = sorted(df_resumen['Operador_Full'].unique())

    if 'operador_seleccionado' in st.session_state and st.session_state['operador_seleccionado'] in lista_operadores:
        indice_default = lista_operadores.index(st.session_state['operador_seleccionado'])
    else:
        indice_default = 0

    op_sel = st.selectbox(
        "Seleccione Operador para analizar detalle diario:", 
        lista_operadores,
        index=indice_default
    )
    
    st.session_state['operador_seleccionado'] = op_sel
    
    sql_op = df_sql_dia[df_sql_dia['Operador_Full'] == op_sel].copy()
    df_dash = sql_op[['Dia', 'Perfo_SQL']].copy().fillna(0)
    df_dash['Fecha_Label'] = df_dash['Dia'].astype(str) + f"/{mes_sel}"

    c1, c2 = st.columns(2)
    with c1:
        excluidos = st.multiselect("Eliminar días atípicos del promedio:", df_dash['Fecha_Label'].tolist())
    with c2:
        multiplicador = st.number_input("Multiplicador de Ajuste (%)", 10.0, 200.0, 100.0, 5.0)

    df_v = df_dash[~df_dash['Fecha_Label'].isin(excluidos)]
    p_orig = df_dash['Perfo_SQL'].mean() if not df_dash.empty else 0
    p_base = df_v['Perfo_SQL'].mean() if not df_v.empty else 0
    p_final = p_base * (multiplicador / 100.0)

    m1, m2, m3 = st.columns(3)
    m1.metric("Perfo Mensual Original", f"{p_orig:.1f}%")
    m2.metric(f"Perfo Días Válidos", f"{p_base:.1f}%", f"{p_base-p_orig:+.1f}%")
    m3.metric("🎯 PERFO FINAL AUDITADA", f"{p_final:.1f}%", f"x {multiplicador/100:.2f}")

    if not df_dash.empty:
        df_dash['Estado'] = df_dash['Fecha_Label'].apply(lambda x: 'Excluido' if x in excluidos else 'Válido')
        st.plotly_chart(px.bar(df_dash, x='Fecha_Label', y='Perfo_SQL', color='Estado', 
                               color_discrete_map={'Válido':'#1A5276', 'Excluido':'#D5D8DC'},
                               text=df_dash['Perfo_SQL'].apply(lambda x: f"{x:.1f}%")), use_container_width=True)
    else:
        st.warning("No hay datos diarios para este operador en el mes seleccionado.")

else:
    st.info("No se encontraron datos en la base de datos para el mes y año seleccionados o las consultas están fallando.")
