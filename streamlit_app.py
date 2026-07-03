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

def color_performance(val):
    if val > 100 or val < 80:
        return 'color: #D32F2F; font-weight: bold;'
    else:
        return 'color: #2E7D32;'

# ==========================================
# 2. MOTOR SQL (ORIGINAL - SIN MÁQUINAS)
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
            st.error(f"Error en la BD '{conn_name}': {e}")
            return pd.DataFrame(), pd.DataFrame()

    df_m_fa, df_d_fa = fetch_db("famma_db")
    df_m_fu, df_d_fu = fetch_db("fumi_db")
    
    df_m_fa['Empresa'] = 'FAMMA'
    df_m_fu['Empresa'] = 'FUMISCOR'
    
    df_mes = pd.concat([df_m_fa, df_m_fu], ignore_index=True)
    df_dia = pd.concat([df_d_fa, df_d_fu], ignore_index=True)
    
    # Filtro: Eliminar operarios con legajo FW
    if not df_mes.empty:
        df_mes = df_mes[~df_mes['Legajo'].astype(str).str.upper().str.startswith('FW')]
    if not df_dia.empty:
        df_dia = df_dia[~df_dia['Legajo'].astype(str).str.upper().str.startswith('FW')]
    
    # Procesar métricas y nombres full
    for df in [df_mes, df_dia]:
        if not df.empty:
            df['Perfo_SQL'] = np.where(df['Perfo_SQL'] > 1.5, df['Perfo_SQL']/100, df['Perfo_SQL']) * 100
            df['Operador_Full'] = df['Nombre'].astype(str).str.upper() + " (" + df['Legajo'].astype(str) + ")"
            
    return df_mes.drop_duplicates(subset=['Operador_Full']), df_dia

# ==========================================
# 3. GENERADOR DEL REPORTE PDF (CLASE FPDF)
# ==========================================
class AuditoriaPDF(FPDF):
    def __init__(self, mes, anio):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.mes = mes
        self.anio = anio
        
    def header(self):
        self.set_fill_color(26, 82, 118)
        self.rect(0, 0, 210, 4, 'F')
        self.set_font("Arial", 'B', 8)
        self.set_text_color(127, 140, 141)
        self.cell(0, 10, "WIIDEM - AUDITORIA GERENCIAL DE RENDIMIENTO", ln=True, align='L')
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", 'I', 8)
        self.set_text_color(127, 140, 141)
        self.cell(0, 10, f"Periodo Auditado: {self.mes}/{self.anio}  |  Confidencial", align='L')
        self.set_x(-30)
        self.cell(0, 10, f"Pagina {self.page_no()}", align='R')

    def draw_bar_chart(self, df_op):
        """Dibuja un gráfico de barras de rendimiento diario de forma nativa en PDF"""
        start_x = 20
        start_y = self.get_y() + 5
        chart_width = 170
        chart_height = 50
        
        # Fondo del gráfico
        self.set_fill_color(248, 249, 250)
        self.rect(start_x, start_y, chart_width, chart_height, 'F')
        self.set_draw_color(220, 224, 230)
        self.set_line_width(0.2)
        
        # Líneas de referencia (50%, 80%, 100%)
        levels = [50, 80, 100]
        for lvl in levels:
            lvl_y = start_y + chart_height - (lvl / 120.0 * chart_height)
            self.line(start_x, lvl_y, start_x + chart_width, lvl_y)
            self.set_font("Arial", '', 7)
            self.set_text_color(150, 150, 150)
            self.text(start_x - 7, lvl_y + 1, f"{lvl}%")
            
        n_days = len(df_op)
        if n_days == 0:
            return
            
        bar_gap = 2
        total_gaps_width = bar_gap * (n_days + 1)
        bar_width = (chart_width - total_gaps_width) / n_days
        
        # Dibujar cada barra
        for i, row in df_op.reset_index(drop=True).iterrows():
            perfo = max(0, min(120, row['Perfo_SQL'])) # Tope visual al 120%
            b_height = (perfo / 120.0) * chart_height
            b_x = start_x + bar_gap + i * (bar_width + bar_gap)
            b_y = start_y + chart_height - b_height
            
            # Colores condicionales
            if row['Perfo_SQL'] < 80 or row['Perfo_SQL'] > 100:
                self.set_fill_color(211, 47, 47)
            else:
                self.set_fill_color(46, 125, 50)
                
            self.rect(b_x, b_y, bar_width, b_height, 'F')
            
            # Etiqueta del eje X (Día)
            self.set_font("Arial", '', 6)
            self.set_text_color(50, 50, 50)
            self.text(b_x + (bar_width/2) - 1, start_y + chart_height + 4, str(int(row['Dia'])))
            
        self.ln(chart_height + 12)

# ==========================================
# 4. BARRA LATERAL
# ==========================================
st.sidebar.header("📅 Periodo a Auditar")
mes_sel = st.sidebar.slider("Mes", 1, 12, 4)
anio_sel = st.sidebar.number_input("Año", 2024, 2030, 2026)

# ==========================================
# 5. DASHBOARD PRINCIPAL Y REPORTES
# ==========================================
with st.spinner("Sincronizando con base de datos SQL..."):
    df_sql_mes, df_sql_dia = extraer_sql_data(mes_sel, anio_sel)

st.title("🏭 Auditoría Gerencial Wiidem")

if not df_sql_mes.empty:
    
    st.header("🏆 Resumen General de Operarios")
    with st.expander("Ver Listado Completo con Alertas (Rojo <80% o >100%)", expanded=True):
        
        df_resumen = df_sql_mes[['Operador_Full', 'Empresa', 'Perfo_SQL']].copy()
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

        # ----------------------------------------------------
        # FUNCIÓN PARA GENERAR EL PDF MULTIPÁGINA
        # ----------------------------------------------------
        def compilar_pdf_completo(df_mes, df_dia, mes, anio):
            pdf = AuditoriaPDF(mes, anio)
            
            # --- PAGINA 1: Resumen General ---
            pdf.add_page()
            pdf.set_font("Arial", 'B', 18)
            pdf.set_text_color(26, 82, 118)
            pdf.cell(0, 12, f"Reporte de Auditoria Gerencial - {mes}/{anio}", ln=True)
            pdf.set_font("Arial", '', 10)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(0, 5, "Listado general de desempeno consolidado por operario.", ln=True)
            pdf.ln(6)
            
            # Cabeceras de tabla
            pdf.set_font("Arial", 'B', 10)
            pdf.set_fill_color(26, 82, 118)
            pdf.set_text_color(255, 255, 255)
            col_widths = [100, 40, 50]
            headers = ['Operador (Legajo)', 'Planta', 'Rendimiento Mensual (%)']
            
            for i in range(len(headers)):
                align = 'R' if i == 2 else 'L'
                pdf.cell(col_widths[i], 9, headers[i], border=1, fill=True, align=align)
            pdf.ln()
            
            # Filas de tabla
            pdf.set_font("Arial", '', 10)
            df_sorted = df_mes.sort_values('Perfo_SQL', ascending=False)
            
            for _, row in df_sorted.iterrows():
                pdf.set_text_color(0, 0, 0)
                pdf.cell(col_widths[0], 8, f"  {row['Operador_Full'][:50]}", border=1)
                pdf.cell(col_widths[1], 8, f"  {row['Empresa']}", border=1)
                
                perfo = row['Perfo_SQL']
                if perfo < 80 or perfo > 100:
                    pdf.set_text_color(211, 47, 47)
                    pdf.set_font("Arial", 'B', 10)
                else:
                    pdf.set_text_color(46, 125, 50)
                    pdf.set_font("Arial", '', 10)
                    
                pdf.cell(col_widths[2], 8, f"{perfo:.1f}%  ", border=1, align='R')
                pdf.ln()
                
            # --- HOJA A HOJA: Fichas individuales ---
            for _, row_mes in df_sorted.iterrows():
                op_full = row_mes['Operador_Full']
                pdf.add_page()
                
                # Encabezado Operario
                pdf.set_font("Arial", 'B', 15)
                pdf.set_text_color(26, 82, 118)
                pdf.cell(0, 10, "Ficha de Auditoria Individual", ln=True)
                
                pdf.set_fill_color(245, 247, 250)
                pdf.rect(10, pdf.get_y(), 190, 22, 'F')
                
                pdf.set_font("Arial", 'B', 11)
                pdf.set_text_color(44, 62, 80)
                pdf.set_xy(14, pdf.get_y() + 3)
                pdf.cell(100, 5, f"Operador: {row_mes['Nombre']}")
                pdf.set_font("Arial", 'B', 10)
                pdf.cell(0, 5, f"Planta: {row_mes['Empresa']}", align='R', ln=True)
                
                pdf.set_font("Arial", '', 10)
                pdf.set_text_color(100, 100, 100)
                pdf.set_x(14)
                pdf.cell(100, 5, f"Legajo: {row_mes['Legajo']}")
                
                pdf.set_font("Arial", 'B', 10)
                pdf.set_text_color(46, 125, 50) if 80 <= row_mes['Perfo_SQL'] <= 100 else pdf.set_text_color(211, 47, 47)
                pdf.cell(0, 5, f"Rendimiento Mensual: {row_mes['Perfo_SQL']:.1f}%", align='R', ln=True)
                pdf.ln(10)
                
                # Gráfico
                pdf.set_font("Arial", 'B', 11)
                pdf.set_text_color(26, 82, 118)
                pdf.cell(0, 6, "Grafico de Rendimiento por Dia Trabajado", ln=True)
                
                df_op_daily = df_dia[df_dia['Operador_Full'] == op_full].sort_values('Dia')
                pdf.draw_bar_chart(df_op_daily)
                
                # Tabla diaria
                pdf.set_font("Arial", 'B', 11)
                pdf.set_text_color(26, 82, 118)
                pdf.cell(0, 6, "Detalle Diario de Rendimiento", ln=True)
                pdf.ln(2)
                
                pdf.set_font("Arial", 'B', 9)
                pdf.set_fill_color(52, 73, 94)
                pdf.set_text_color(255, 255, 255)
                pdf.cell(30, 7, "Dia", border=1, fill=True, align='C')
                pdf.cell(50, 7, "Fecha", border=1, fill=True, align='C')
                pdf.cell(50, 7, "Rendimiento (%)", border=1, fill=True, align='C')
                pdf.cell(60, 7, "Estado de Alerta", border=1, fill=True, align='C')
                pdf.ln()
                
                pdf.set_font("Arial", '', 9)
                for _, row_d in df_op_daily.iterrows():
                    pdf.set_text_color(0, 0, 0)
                    pdf.cell(30, 6, f"{int(row_d['Dia'])}", border=1, align='C')
                    pdf.cell(50, 6, f"{int(row_d['Dia'])}/{mes}/{anio}", border=1, align='C')
                    
                    d_perfo = row_d['Perfo_SQL']
                    if d_perfo < 80 or d_perfo > 100:
                        pdf.set_text_color(211, 47, 47)
                        alert_text = "Desvio Detectado"
                    else:
                        pdf.set_text_color(46, 125, 50)
                        alert_text = "Normal"
                        
                    pdf.cell(50, 6, f"{d_perfo:.1f}%", border=1, align='C')
                    pdf.cell(60, 6, alert_text, border=1, align='C')
                    pdf.ln()

            return pdf.output(dest='S').encode('latin1')

        # Botón de Descarga PDF
        st.write("") 
        try:
            pdf_bytes = compilar_pdf_completo(df_sql_mes, df_sql_dia, mes_sel, anio_sel)
            st.download_button(
                label="📄 Descargar Reporte Completo (PDF con Gráficos Individuales)",
                data=pdf_bytes,
                file_name=f"Reporte_Auditoria_Completo_{mes_sel}_{anio_sel}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        except NameError:
            st.error("Falta instalar la librería fpdf (Ejecuta: pip install fpdf)")

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
    st.info("No se encontraron datos en la base de datos para el mes y año seleccionados.")
