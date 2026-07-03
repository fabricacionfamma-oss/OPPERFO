import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, Reference

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
# GENERADOR DE EXCEL (NUEVA FUNCIÓN)
# ==========================================
def generar_excel_descargable(df_resumen, df_dia, mes, anio):
    output = io.BytesIO()
    wb = openpyxl.Workbook()
    
    # Estilos
    font_title = Font(name="Calibri", size=16, bold=True, color="1A5276")
    font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    font_body = Font(name="Calibri", size=11)
    
    fill_header = PatternFill(start_color="1A5276", end_color="1A5276", fill_type="solid")
    fill_alert_red = PatternFill(start_color="FADBD8", end_color="FADBD8", fill_type="solid")
    font_alert_red = Font(name="Calibri", size=11, bold=True, color="922B21")
    fill_alert_green = PatternFill(start_color="D4EFDF", end_color="D4EFDF", fill_type="solid")
    font_alert_green = Font(name="Calibri", size=11, color="196F3D")
    
    thin_border = Border(left=Side(style='thin', color='D5D8DC'), right=Side(style='thin', color='D5D8DC'),
                         top=Side(style='thin', color='D5D8DC'), bottom=Side(style='thin', color='D5D8DC'))
    align_center = Alignment(horizontal="center", vertical="center")
    
    # --- PESTAÑA 1: RESUMEN GENERAL ---
    ws1 = wb.active
    ws1.title = "Resumen General"
    ws1.views.sheetView[0].showGridLines = False
    
    ws1.cell(row=2, column=2, value="REPORTE DE AUDITORÍA GERENCIAL").font = font_title
    ws1.cell(row=3, column=2, value=f"Periodo: Mes {mes} / Año {anio}").font = font_body
    
    headers_resumen = ["Operador", "Empresa", "Performance Mensual (%)"]
    for col_idx, header in enumerate(headers_resumen, start=2):
        c = ws1.cell(row=5, column=col_idx, value=header)
        c.font = font_header; c.fill = fill_header; c.alignment = align_center
        
    for row_idx, row_data in df_resumen.iterrows():
        r = row_idx + 6
        ws1.cell(row=r, column=2, value=row_data["Operador_Full"]).border = thin_border
        ws1.cell(row=r, column=3, value=row_data["Empresa"]).border = thin_border
        
        c_perf = ws1.cell(row=r, column=4, value=row_data["Perfo_Mensual (%)"]/100)
        c_perf.number_format = '0.0%'
        c_perf.border = thin_border
        
        val = row_data["Perfo_Mensual (%)"]
        if val < 80 or val > 100:
            c_perf.fill = fill_alert_red; c_perf.font = font_alert_red
        else:
            c_perf.fill = fill_alert_green; c_perf.font = font_alert_green

    for col in range(2, 5):
        ws1.column_dimensions[get_column_letter(col)].width = 25

    # --- PESTAÑA 2: DETALLE DIARIO Y GRÁFICOS ---
    ws2 = wb.create_sheet(title="Detalle Diario")
    ws2.views.sheetView[0].showGridLines = False
    
    ws2.cell(row=2, column=2, value="DESGLOSE DIARIO POR OPERADOR").font = font_title
    
    headers_diario = ["Operador", "Empresa", "Día", "Performance Diaria"]
    for col_idx, header in enumerate(headers_diario, start=2):
        c = ws2.cell(row=4, column=col_idx, value=header)
        c.font = font_header; c.fill = fill_header; c.alignment = align_center

    df_diario_sorted = df_dia.sort_values(["Operador_Full", "Dia"]).reset_index(drop=True)
    
    current_row = 5
    start_row_op = 5
    operador_actual = None
    
    for _, row_data in df_diario_sorted.iterrows():
        # Detectar cambio de operador para graficar
        if operador_actual != row_data["Operador_Full"] and operador_actual is not None:
            # Insertar Gráfico del operador anterior
            chart = BarChart()
            chart.type = "col"
            chart.style = 10
            chart.title = f"Rendimiento - {operador_actual}"
            chart.y_axis.title = "Performance"
            chart.x_axis.title = "Día"
            
            data_ref = Reference(ws2, min_col=5, min_row=start_row_op-1, max_row=current_row-1)
            cats_ref = Reference(ws2, min_col=4, min_row=start_row_op, max_row=current_row-1)
            chart.add_data(data_ref, titles_from_data=True)
            chart.set_categories(cats_ref)
            chart.legend = None
            chart.height = 10; chart.width = 15
            
            ws2.add_chart(chart, f"G{start_row_op}")
            start_row_op = current_row

        operador_actual = row_data["Operador_Full"]
        
        ws2.cell(row=current_row, column=2, value=row_data["Operador_Full"]).border = thin_border
        ws2.cell(row=current_row, column=3, value=row_data["Empresa"]).border = thin_border
        ws2.cell(row=current_row, column=4, value=row_data["Dia"]).border = thin_border
        
        c_perf = ws2.cell(row=current_row, column=5, value=row_data["Perfo_SQL"]/100)
        c_perf.number_format = '0.0%'
        c_perf.border = thin_border
        
        val = row_data["Perfo_SQL"]
        if val < 80 or val > 100:
            c_perf.fill = fill_alert_red; c_perf.font = font_alert_red
        else:
            c_perf.fill = fill_alert_green; c_perf.font = font_alert_green
            
        current_row += 1

    for col in range(2, 6):
        ws2.column_dimensions[get_column_letter(col)].width = 20

    wb.save(output)
    output.seek(0)
    return output

# ==========================================
# 2. MOTOR SQL (AUTOMÁTICO) -> Mantén tu código original aquí
# ==========================================
@st.cache_data(ttl=600)
def extraer_sql_data(mes, anio):
    # Simulación para que el código no rompa (aquí debes mantener tu función real de base de datos)
    df_m = pd.DataFrame([{"Nombre": "JUAN P", "Legajo": "10", "Perfo_SQL": 95, "Empresa": "FAMMA"}])
    df_m['Operador_Full'] = df_m['Nombre'] + " (" + df_m['Legajo'] + ")"
    df_d = pd.DataFrame([{"Nombre": "JUAN P", "Legajo": "10", "Dia": 1, "Perfo_SQL": 90, "Empresa": "FAMMA", "Operador_Full": "JUAN P (10)"}])
    return df_m, df_d

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
    df_sql_mes, df_sql_dia = extraer_sql_data(mes_sel, anio_sel) # <- Usa tu función real aquí

st.title("🏭 Auditoría Gerencial Wiidem")

if not df_sql_mes.empty:
    
    st.header("🏆 Resumen General de Operarios")
    
    # Preparamos los datos del resumen
    df_resumen = df_sql_mes[['Operador_Full', 'Empresa', 'Perfo_SQL']].copy()
    df_resumen = df_resumen.rename(columns={'Perfo_SQL': 'Perfo_Mensual (%)'})
    df_resumen = df_resumen.sort_values('Perfo_Mensual (%)', ascending=False).reset_index(drop=True)

    # --- BOTÓN DE EXPORTAR A EXCEL (AQUÍ VA LA INTEGRACIÓN) ---
    col_export, col_vacio = st.columns([1, 4])
    with col_export:
        archivo_excel = generar_excel_descargable(df_resumen, df_sql_dia, mes_sel, anio_sel)
        st.download_button(
            label="📥 Descargar Reporte Excel",
            data=archivo_excel,
            file_name=f"Auditoria_Gerencial_{mes_sel}_{anio_sel}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
    
    with st.expander("Ver Listado Completo con Alertas (Rojo <80% o >100%)", expanded=True):
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
