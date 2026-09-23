import os
import sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import streamlit as st
import pandas as pd
import altair as alt
from src.data_loader import obtener_fechas_disponibles, cargar_datos_fecha, cargar_red_hidrica, cargar_departamentos
from src.map_utils import preparar_features_geojson, preparar_features_puntos, crear_mapa_pydeck

st.set_page_config(
    page_title="UrbanNuna - SENAMHI | Monitoreo Nacional de Inundaciones",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inyección de CSS para look & feel ejecutivo estilo Google Flood Hub
st.markdown("""
<style>
    .block-container {
        padding-top: 2.2rem !important;
        padding-bottom: 1.5rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }
    header[data-testid="stHeader"] {
        background: rgba(14, 17, 23, 0.85);
        backdrop-filter: blur(8px);
    }
    h1, h2, h3 {
        margin-top: 0.1rem !important;
        padding-top: 0rem !important;
        line-height: 1.2 !important;
    }
    .metric-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 10px 14px;
        margin-bottom: 8px;
    }
    .metric-title {
        color: #8b949e;
        font-size: 0.74rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .metric-value {
        font-size: 1.55rem;
        font-weight: 700;
        margin-top: 2px;
    }
    .detail-card {
        background: #161b22;
        border: 1px solid #388bfd;
        border-radius: 8px;
        padding: 14px 16px;
        margin-top: 8px;
        margin-bottom: 12px;
        box-shadow: 0 4px 16px rgba(56, 139, 253, 0.15);
    }
    .detail-title {
        font-size: 1.05rem;
        font-weight: 700;
        color: #58a6ff;
        margin-bottom: 2px;
    }
    .detail-sub {
        font-size: 0.78rem;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 10px;
    }
    .badge-critical {
        background: rgba(244, 67, 54, 0.2);
        color: #f85149;
        border: 1px solid #f85149;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 700;
    }
    .badge-high {
        background: rgba(255, 152, 0, 0.2);
        color: #ff9800;
        border: 1px solid #ff9800;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 700;
    }
    .badge-mod {
        background: rgba(255, 235, 59, 0.2);
        color: #f2cc60;
        border: 1px solid #f2cc60;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 700;
    }
    .badge-normal {
        background: rgba(139, 148, 158, 0.2);
        color: #8b949e;
        border: 1px solid #484f58;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .top-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 6px;
        padding: 8px 12px;
        margin-bottom: 8px;
    }
    .top-title {
        font-size: 0.85rem;
        font-weight: 600;
        color: #f0f6fc;
    }
    .top-sub {
        font-size: 0.75rem;
        color: #8b949e;
    }
</style>
""", unsafe_allow_html=True)

# ----------------- SIDEBAR: CONTROLES ESTILO GOOGLE FLOOD HUB -----------------
with st.sidebar:
    st.markdown("### 🌊 **UrbanNuna**")
    st.caption("Dirección de Hidrología — SENAMHI Perú")
    st.markdown("---")
    
    fechas = obtener_fechas_disponibles()
    if not fechas:
        st.error("No se encontraron salidas en la carpeta data.")
        st.stop()
        
    fecha_sel = st.selectbox("📅 Fecha de Evaluación", options=fechas, index=0)

# Cargar datos de la fecha seleccionada
with st.spinner("Cargando matriz nacional..."):
    try:
        gdf, df_resumen = cargar_datos_fecha(fecha_sel)
    except Exception as err:
        st.error(f"❌ Error al cargar datos para la fecha {fecha_sel}: {err}")
        st.info("Verifique que los archivos de datos en `data/` se encuentren disponibles.")
        st.stop()

# Departamentos disponibles
depts_disponibles = sorted([d for d in gdf["DEPARTAMENTO"].unique() if d not in ["Sin Datos", "N/D"]])
opciones_dept = ["Todos los Departamentos"] + depts_disponibles

with st.sidebar:
    st.markdown("#### 🔍 **Navegación Territorial**")
    dept_sel = st.selectbox("Departamento:", options=opciones_dept, index=0)
    
    # Filtrar distritos según departamento
    if dept_sel != "Todos los Departamentos":
        gdf_dept = gdf[gdf["DEPARTAMENTO"] == dept_sel]
        distritos_disponibles = sorted([d for d in gdf_dept["DISTRITO"].unique() if d not in ["Sin Datos", "N/D"]])
    else:
        gdf_dept = gdf
        # Distritos con mayor probabilidad para sugerencia rápida
        distritos_disponibles = sorted(gdf[gdf["prob"] >= 0.20]["DISTRITO"].unique().tolist())
        
    opciones_dist = ["(Nacional / Sin selección)"] + distritos_disponibles
    dist_sel = st.selectbox("Distrito / Zona:", options=opciones_dist, index=0)
    
    st.markdown("---")
    st.markdown("#### 🎚️ **Filtro de Severidad**")
    
    severidad_sel = st.radio(
        "Nivel de Alerta:",
        options=[
            "Todas las Celdas",
            "🔴 Crítico (Prob ≥ 70%)",
            "🟠 Alto (Prob 40-70%)",
            "🟡 Moderado (Prob 20-40%)",
            "🚨 Alertas Operativas (Umbral = 1)"
        ],
        index=0
    )
    
    st.markdown("---")
    st.markdown("#### 🌊 **Capas Territoriales e Hidrológicas**")
    mostrar_rios = st.checkbox("Mostrar Red de Ríos y Quebradas (ANA)", value=True)
    mostrar_dept = st.checkbox("Mostrar Límites Departamentales", value=True)
    modo_3d = st.toggle("🏢 Modo 3D (Extrusión por Riesgo)", value=False)
    
    st.markdown("---")
    st.markdown("#### 🗺️ **Estilo del Mapa Base**")
    estilo_mapa_sel = st.selectbox(
        "Mapa:",
        options=["Oscuro", "Topográfico / Terreno", "Claro"],
        index=0
    )

# ----------------- GESTIÓN DE BOTONES REGIONALES (SESSION STATE) -----------------
if "reg_foco" not in st.session_state:
    st.session_state["reg_foco"] = "nacional"

# ----------------- FILTRADO DINÁMICO DE DATOS -----------------
gdf_filtrado = gdf.copy()

# Filtro por departamento
if dept_sel != "Todos los Departamentos":
    gdf_filtrado = gdf_filtrado[gdf_filtrado["DEPARTAMENTO"] == dept_sel]

# Filtro por severidad
if severidad_sel == "🔴 Crítico (Prob ≥ 70%)":
    gdf_filtrado = gdf_filtrado[gdf_filtrado["prob"] >= 0.70]
elif severidad_sel == "🟠 Alto (Prob 40-70%)":
    gdf_filtrado = gdf_filtrado[(gdf_filtrado["prob"] >= 0.40) & (gdf_filtrado["prob"] < 0.70)]
elif severidad_sel == "🟡 Moderado (Prob 20-40%)":
    gdf_filtrado = gdf_filtrado[(gdf_filtrado["prob"] >= 0.20) & (gdf_filtrado["prob"] < 0.40)]
elif severidad_sel == "🚨 Alertas Operativas (Umbral = 1)":
    gdf_filtrado = gdf_filtrado[gdf_filtrado["evento_op"] == 1]

# Modo de visualización para capas de mapa
modo_clave = "op" if "Operativas" in severidad_sel else "prob"

# Determinar centro y zoom dinámico del mapa (Fly-To)
centro_lat = -9.19
centro_lon = -75.01
zoom_mapa = 4.8
punto_foco = None

if dist_sel != "(Nacional / Sin selección)":
    fila_dist = gdf[gdf["DISTRITO"] == dist_sel].sort_values(by="prob", ascending=False).iloc[0]
    centro_lat = float(fila_dist["lat"])
    centro_lon = float(fila_dist["lon"])
    zoom_mapa = 9.8
    punto_foco = {
        "lat": centro_lat,
        "lon": centro_lon,
        "distrito": dist_sel,
        "prob_pct": fila_dist["prob_pct"]
    }
elif dept_sel != "Todos los Departamentos" and not gdf_dept.empty:
    centro_lat = float(gdf_dept["lat"].mean())
    centro_lon = float(gdf_dept["lon"].mean())
    zoom_mapa = 7.0
else:
    # Si no hay selección manual, revisar si se activó una píldora regional
    reg = st.session_state.get("reg_foco", "nacional")
    if reg == "norte":
        centro_lat, centro_lon, zoom_mapa = -5.20, -80.30, 7.2
    elif reg == "selva":
        centro_lat, centro_lon, zoom_mapa = -5.10, -74.50, 6.4
    elif reg == "sur":
        centro_lat, centro_lon, zoom_mapa = -15.80, -71.20, 7.0

# ----------------- FICHA TÉCNICA DE ZONA EN SIDEBAR (GOOGLE FLOOD HUB CARD) -----------------
with st.sidebar:
    st.markdown("---")
    if punto_foco:
        fila_f = gdf[gdf["DISTRITO"] == dist_sel].sort_values(by="prob", ascending=False).iloc[0]
        prob_pct = fila_f["prob_pct"]
        if prob_pct >= 70:
            badge_html = '<span class="badge-critical">🔴 CRÍTICO</span>'
        elif prob_pct >= 40:
            badge_html = '<span class="badge-high">🟠 ALTO</span>'
        elif prob_pct >= 20:
            badge_html = '<span class="badge-mod">🟡 MODERADO</span>'
        else:
            badge_html = '<span class="badge-normal">⚪ NORMAL</span>'
            
        st.markdown(f"""
        <div class="detail-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <div class="detail-title">📍 {fila_f['DISTRITO']}</div>
                {badge_html}
            </div>
            <div class="detail-sub">{fila_f['PROVINCIA']}, {fila_f['DEPARTAMENTO']}</div>
            <div style="margin-bottom: 8px;">
                <div style="display: flex; justify-content: space-between; font-size: 0.8rem; margin-bottom: 3px;">
                    <span>Probabilidad Inundación:</span>
                    <b style="color: #f2cc60;">{prob_pct:.1f}%</b>
                </div>
                <div style="width: 100%; background: #30363d; height: 8px; border-radius: 4px; overflow: hidden;">
                    <div style="width: {min(prob_pct, 100)}%; background: {'#f85149' if prob_pct>=70 else ('#ff9800' if prob_pct>=40 else '#f2cc60')}; height: 100%;"></div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Mini gráfico de diagnóstico hídrico (Precipitación Hoy vs Antecedente)
        df_diag = pd.DataFrame({
            "Componente": ["Lluvia Hoy (pp)", "Antecedente (15d)"],
            "Milimetros": [float(fila_f["pp"]), float(fila_f["ant_log"])]
        })
        chart_diag = alt.Chart(df_diag).mark_bar(cornerRadius=4).encode(
            x=alt.X("Milimetros:Q", title="Milímetros (mm)"),
            y=alt.Y("Componente:N", title=None, sort=None),
            color=alt.Color("Componente:N", scale=alt.Scale(domain=["Lluvia Hoy (pp)", "Antecedente (15d)"], range=["#58a6ff", "#3fb950"]), legend=None),
            tooltip=["Componente", "Milimetros"]
        ).properties(height=95)
        st.caption("💧 **Diagnóstico Hídrico de Saturación:**")
        st.altair_chart(chart_diag, use_container_width=True)
        
    with st.expander("🚨 **Top 5 Zonas Críticas Nacionales**", expanded=(punto_foco is None)):
        top_5 = gdf.sort_values(by="prob", ascending=False).head(5)
        for _, fila in top_5.iterrows():
            prob_val = fila['prob'] * 100.0
            color_badge = "#f85149" if prob_val >= 70 else ("#ff9800" if prob_val >= 40 else "#f2cc60")
            alerta_txt = "🔴 Alerta Activa" if fila['evento_op'] == 1 else "🟡 Precaución"
            st.markdown(f"""
            <div class="top-card">
                <div class="top-title">📍 {fila['DISTRITO']}</div>
                <div style="font-size: 0.72rem; color: #58a6ff; margin-bottom: 3px;">{fila['PROVINCIA']}, {fila['DEPARTAMENTO']}</div>
                <div class="top-sub">
                    Prob: <b style="color: {color_badge};">{prob_val:.1f}%</b> · Lluvia: <b>{fila['pp']:.1f} mm</b>
                    <br>{alerta_txt} · Ant: {fila['ant_log']:.1f} mm
                </div>
            </div>
            """, unsafe_allow_html=True)

# ----------------- ENCABEZADO Y KPIS EJECUTIVOS -----------------
col_tit, col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns([2.5, 1, 1, 1, 1])

celdas_en_alerta_op = int((gdf["evento_op"] == 1).sum())
celdas_criticas = int((gdf["prob"] >= 0.70).sum())
celdas_altas = int(((gdf["prob"] >= 0.40) & (gdf["prob"] < 0.70)).sum())
max_pp = gdf["pp"].max() if not gdf.empty else 0.0

with col_tit:
    st.markdown(f"### **UrbanNuna | Monitoreo Nacional de Inundaciones**")
    st.caption(f"Evaluación operativa al **{fecha_sel}** en grilla PISCO (0.1°) · Enfoque Groundsource AI + Firth Logistic")

with col_kpi1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Alerta Operativa</div>
        <div class="metric-value" style="color: #f85149;">{celdas_en_alerta_op}</div>
    </div>
    """, unsafe_allow_html=True)

with col_kpi2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">🔴 Crítico (≥70%)</div>
        <div class="metric-value" style="color: #f85149;">{celdas_criticas}</div>
    </div>
    """, unsafe_allow_html=True)

with col_kpi3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">🟠 Alto (40-70%)</div>
        <div class="metric-value" style="color: #ff9800;">{celdas_altas}</div>
    </div>
    """, unsafe_allow_html=True)

with col_kpi4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Lluvia Máx (24h)</div>
        <div class="metric-value" style="color: #58a6ff;">{max_pp:.1f} <span style="font-size: 0.9rem;">mm</span></div>
    </div>
    """, unsafe_allow_html=True)

# ----------------- PÍLDORAS DE SALTO RÁPIDO A REGIONES VULNERABLES -----------------
col_b1, col_b2, col_b3, col_b4 = st.columns(4)
with col_b1:
    if st.button("🇵🇪 Nacional", use_container_width=True):
        st.session_state["reg_foco"] = "nacional"
        st.rerun()
with col_b2:
    if st.button("🌊 Costa Norte (Piura/Tumbes)", use_container_width=True):
        st.session_state["reg_foco"] = "norte"
        st.rerun()
with col_b3:
    if st.button("🌳 Selva / Amazonía", use_container_width=True):
        st.session_state["reg_foco"] = "selva"
        st.rerun()
with col_b4:
    if st.button("🏔️ Sierra Sur", use_container_width=True):
        st.session_state["reg_foco"] = "sur"
        st.rerun()

# ----------------- RENDERIZADO DEL MAPA WEBGL PYDECK -----------------
geojson_data = preparar_features_geojson(gdf_filtrado, modo=modo_clave)
puntos_alerta = preparar_features_puntos(gdf_filtrado, modo=modo_clave)
red_hidrica_data = cargar_red_hidrica() if mostrar_rios else None
departamentos_data = cargar_departamentos() if mostrar_dept else None

mapa_deck = crear_mapa_pydeck(
    geojson_data=geojson_data,
    puntos_alerta=puntos_alerta,
    punto_foco=punto_foco,
    red_hidrica_data=red_hidrica_data,
    departamentos_data=departamentos_data,
    centro_lat=centro_lat,
    centro_lon=centro_lon,
    zoom=zoom_mapa,
    estilo_mapa=estilo_mapa_sel,
    modo_3d=modo_3d
)

st.pydeck_chart(mapa_deck, use_container_width=True)

# ----------------- LEYENDA FLOTANTE GOOGLE FLOOD HUB -----------------
rios_leyenda = '<div style="display: flex; align-items: center; gap: 6px; border-left: 1px solid #30363d; padding-left: 10px;"><span style="width: 14px; height: 3px; background: #00e5ff; display: inline-block;"></span> <span style="color: #00e5ff; font-weight: 600;">Ríos y Quebradas ANA</span></div>' if mostrar_rios else ''

leyenda_html = f"""
<div style="display: flex; justify-content: flex-end; margin-top: -55px; margin-bottom: 20px; padding-right: 20px; position: relative; z-index: 10;">
    <div style="background: rgba(22, 27, 34, 0.95); backdrop-filter: blur(8px); border: 1px solid #30363d; border-radius: 8px; padding: 10px 16px; box-shadow: 0 4px 14px rgba(0,0,0,0.5); font-family: sans-serif; font-size: 12px;">
        <div style="color: #8b949e; font-size: 10px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">Niveles de Alerta Nacional (Google Flood Hub Perú)</div>
        <div style="display: flex; gap: 14px; align-items: center;">
            <div style="display: flex; align-items: center; gap: 6px;"><span style="width: 12px; height: 12px; background: rgba(200, 200, 200, 0.2); border: 1px solid #555; border-radius: 3px; display: inline-block;"></span> <span style="color: #8b949e;">&lt; 20% Normal</span></div>
            <div style="display: flex; align-items: center; gap: 6px;"><span style="width: 12px; height: 12px; background: rgb(255, 235, 59); border-radius: 3px; display: inline-block;"></span> <span style="color: #f2cc60;">20 - 40% Moderado</span></div>
            <div style="display: flex; align-items: center; gap: 6px;"><span style="width: 12px; height: 12px; background: rgb(255, 152, 0); border-radius: 3px; display: inline-block;"></span> <span style="color: #ff9800;">40 - 70% Alto</span></div>
            <div style="display: flex; align-items: center; gap: 6px;"><span style="width: 12px; height: 12px; background: rgb(244, 67, 54); border-radius: 3px; display: inline-block;"></span> <span style="color: #f85149; font-weight: bold;">≥ 70% Crítico</span></div>
            {rios_leyenda}
            <div style="display: flex; align-items: center; gap: 6px; border-left: 1px solid #30363d; padding-left: 10px;"><span style="width: 10px; height: 10px; border-radius: 50%; background: #00e5ff; display: inline-block; box-shadow: 0 0 8px #00e5ff;"></span> <span style="color: #00e5ff; font-weight: bold;">Zona Seleccionada</span></div>
        </div>
    </div>
</div>
"""
st.markdown(leyenda_html, unsafe_allow_html=True)

# ----------------- TABLA DE DETALLE Y EXPORTACIÓN INDECI / COEN -----------------
with st.expander("📋 **Boletín Ejecutivo: Tabla de Zonas Bajo Alerta & Exportación INDECI / COEN**", expanded=False):
    df_export = gdf[gdf["prob"] >= 0.20][
        ["id", "DEPARTAMENTO", "PROVINCIA", "DISTRITO", "prob_pct", "evento_op", "pp", "ant_log", "lat", "lon"]
    ].sort_values(by="prob_pct", ascending=False)
    
    st.dataframe(
        df_export.rename(columns={
            "prob_pct": "Probabilidad (%)",
            "evento_op": "Alerta Operativa (1/0)",
            "pp": "Lluvia Hoy (mm)",
            "ant_log": "Antecedente 15d (mm)",
            "lat": "Latitud",
            "lon": "Longitud"
        }),
        use_container_width=True,
        hide_index=True
    )
    
    col_exp1, col_exp2 = st.columns([1, 4])
    with col_exp1:
        csv_data = df_export.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Descargar Boletín CSV",
            data=csv_data,
            file_name=f"boletin_inundaciones_SENAMHI_{fecha_sel}.csv",
            mime="text/csv"
        )
