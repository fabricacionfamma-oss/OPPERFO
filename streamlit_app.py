import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

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
# 2. GENERADOR DE EXCEL (SIN GRÁFICOS)
# ==========================================
def generar_excel_descargable(df_resumen, df_dia, mes, anio):
    output = io.BytesIO()
    wb = openpyxl.Workbook()
    
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
    ws1.views.sheetView[0].showGridLines = True
    
    ws1.cell(row=2, column=2, value="REPORTE DE AUDITORÍA GERENCIAL").font = font_title
    ws1.cell(row=3, column=2, value=f"Periodo: Mes {mes} / Año {anio}").font = font_body
    
    headers_resumen = ["Operador", "Empresa", "Performance Mensual (%)"]
    for col_idx, header in enumerate(headers_resumen, start=2):
        c = ws1.cell(row=5, column=col_idx, value=header)
        c.font = font_header; c.fill = fill
