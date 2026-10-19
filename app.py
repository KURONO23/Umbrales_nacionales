import os
import sys
import base64

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import altair as alt
from src.data_loader import obtener_fechas_disponibles, cargar_datos_fecha, cargar_red_hidrica, cargar_departamentos
from src.map_utils import preparar_features_geojson, preparar_features_puntos, crear_mapa_pydeck

logo_path_local = os.path.join(BASE_DIR, "img", "ares_logo.png")
icon_page = logo_path_local if os.path.exists(logo_path_local) else "🌊"

st.set_page_config(
    page_title="ARES Nacional - SENAMHI | Monitoreo y Pronóstico de Inundaciones Urbanas",
    page_icon=icon_page,
    layout="wide",
    initial_sidebar_state="expanded"
)

def obtener_logo_base64():
    """Retorna el logo corporativo en base64 para renderizado HTML directo de alto rendimiento."""
    if os.path.exists(logo_path_local):
        try:
            with open(logo_path_local, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception:
            return None
    return None

# Inyección de CSS para look & feel ejecutivo estilo Google Flood Hub
st.markdown("""
<style>
    .block-container {
        padding-top: 4.2rem !important;
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
    .badge-dual {
        background: rgba(255, 0, 85, 0.25);
        color: #ff0055;
        border: 1px solid #ff0055;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 700;
        box-shadow: 0 0 8px rgba(255, 0, 85, 0.4);
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

# ----------------- MODAL DIALOG "ACERCA DE" (ESTILO CAMELS-PE / SENAMHI) -----------------
def render_contenido_acerca_de():
    st.markdown("""
    <h3 style="color: #58a6ff; font-weight: 700; margin-top: 0; margin-bottom: 12px;">Bienvenido a ARES NACIONAL</h3>
    
    <p style="font-size: 0.95rem; line-height: 1.55; margin-bottom: 16px;">
        <b>ARES NACIONAL</b> (<b>SistemA de MonitoReo y Pronóstico FrEnte a InundacioneS Urbanas</b>) es una plataforma operativa de libre acceso desarrollada por el SENAMHI para el monitoreo continuo y emisión de alertas tempranas frente al peligro de inundaciones urbanas a escala de la grilla PISCO (0.1° × 0.1°) en el territorio peruano.
    </p>
    """, unsafe_allow_html=True)
    
    st.markdown("##### 📦 **Contenido y Modelamiento**")
    st.markdown("""
    * **3,993 celdas continentales:** Cobertura nacional sobre las celdas con evidencia de riesgo y población expuesta (3,385 con modelo propio calibrado in-situ y 608 transferidos por vecino más próximo).
    * **Doble enfoque de alerta temprana:**
      * **Modelo de Regresión Logística (Firth):** Estimación de probabilidad continua con reducción de sesgo por eventos raros y punto de corte calibrado individualmente vía **Índice de Youden** (curva ROC).
      * **Modelo Físico-Operativo ($I_{op}$):** Severidad hídrica acumulada ($I_{op} = pp + ant_{op}$) evaluada contra el umbral crítico optimizado vía **MCC (Matthews Correlation Coefficient)**.
    * **Ventana antecedente adaptativa:** De 1 a 15 días según el tiempo de respuesta hidrológica (escorrentía directa en costa/selva baja y dinámica de saturación progresiva en sierra).
    * **Semáforo de Doble Alerta:** Identificación de celdas donde coinciden simultáneamente la superación del corte probabilístico y del umbral físico-operativo.
    """)

    st.markdown("##### 🌐 **Fuentes de datos**")
    st.markdown("""
    * **Eventos históricos de inundación:** Groundsource (Google Research / LLM Gemini), con más de 36,000 registros procesados a escala diaria nacional.
    * **Precipitación histórica de calibración:** PISCOp v3.0 (1981–2025) a 0.1° de resolución (SENAMHI).
    * **Precipitación operativa diaria:** Repositorio institucional PISCO Operativo (SENAMHI, actualización diaria continua a las 14:30 h).
    * **Validación retrospectiva independiente:** Registro histórico de emergencias del Instituto Nacional de Defensa Civil (**INDECI**, episodio récord El Niño 1997–98).
    * **Red hidrográfica y geopolítica:** Ríos y quebradas de la Autoridad Nacional del Agua (**ANA**) y límites territoriales del IGN.
    """)

    st.markdown("##### 👥 **Autores**")
    st.markdown("""
    **Andrés Goyburo Peña, Eder Pineda Yaros, Max Gutiérrez Reynaga, Waldo Sven Lavado Casimiro**  
    *SENAMHI — Servicio Nacional de Meteorología e Hidrología del Perú*
    """)
    st.markdown("---")
    if st.button("Comenzar a Explorar 🚀", use_container_width=True, type="primary"):
        st.rerun()

if hasattr(st, "dialog"):
    @st.dialog("Acerca de ARES NACIONAL", width="large")
    def modal_acerca_de():
        render_contenido_acerca_de()
elif hasattr(st, "experimental_dialog"):
    @st.experimental_dialog("Acerca de ARES NACIONAL", width="large")
    def modal_acerca_de():
        render_contenido_acerca_de()
else:
    def modal_acerca_de():
        with st.expander("ℹ️ **Acerca de ARES NACIONAL**", expanded=True):
            render_contenido_acerca_de()

# Desplegar automáticamente al abrir el visor por primera vez en la sesión
if "acerca_de_mostrado" not in st.session_state:
    st.session_state["acerca_de_mostrado"] = True
    modal_acerca_de()

# ----------------- SIDEBAR: CONTROLES ESTILO GOOGLE FLOOD HUB -----------------
with st.sidebar:
    st.markdown("""
    <div style="text-align: center; margin-top: -15px; margin-bottom: 14px;">
        <div style="font-size: 1.35rem; font-weight: 800; color: #ffffff; letter-spacing: 0.5px; line-height: 1.2;">ARES NACIONAL</div>
        <div style="font-size: 0.68rem; color: #8b949e; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px; margin-top: 4px;">DIRECCIÓN DE HIDROLOGÍA — SENAMHI PERÚ</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("---")
    
    fechas = obtener_fechas_disponibles()
    if not fechas:
        st.error("No se encontraron salidas operativas en `Salidas/` ni en `data/`.")
        st.info("Verifique que existan archivos `grillaPISCO_prob_YYYY-MM-DD.gpkg` en la carpeta `Salidas/`.")
        st.stop()
    if len(fechas) == 1:
        fecha_sel = fechas[0]
        st.markdown(f"""
        <div style="background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 10px 14px; margin-bottom: 12px;">
            <div style="font-size: 0.72rem; color: #8b949e; text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px;">Fecha de Evaluación</div>
            <div style="font-size: 1.25rem; font-weight: 700; color: #58a6ff; margin-top: 2px;">📅 {fecha_sel}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        fecha_sel = st.selectbox("📅 Fecha de Evaluación:", options=fechas, index=0)

# Cargar datos de la fecha seleccionada
with st.spinner(f"Cargando matriz nacional al {fecha_sel}..."):
    try:
        gdf, df_resumen = cargar_datos_fecha(fecha_sel)
    except Exception as err:
        st.error(f"❌ Error al cargar datos para la fecha {fecha_sel}: {err}")
        st.info("Verifique que los archivos de la fecha en `Salidas/` o `data/` se encuentren disponibles.")
        st.stop()

# Garantizar columnas defensivas (blindaje total ante cachés previas en Streamlit Cloud)
if "prob_corte" not in gdf.columns:
    gdf["prob_corte"] = 0.20
if "prob_corte_pct" not in gdf.columns:
    gdf["prob_corte_pct"] = (gdf["prob_corte"] * 100).round(1)
if "supera_corte_log" not in gdf.columns:
    gdf["supera_corte_log"] = (gdf["prob"] >= gdf["prob_corte"]).astype(int)
if "evento_op" not in gdf.columns:
    gdf["evento_op"] = 0
if "doble_alerta" not in gdf.columns:
    gdf["doble_alerta"] = ((gdf["supera_corte_log"] == 1) & (gdf["evento_op"] == 1)).astype(int)
if "Iop" not in gdf.columns:
    gdf["Iop"] = (gdf["pp"] + gdf.get("ant_log", 0.0)).round(1)
if "umbral_op" not in gdf.columns:
    gdf["umbral_op"] = 50.0
if "mejor_ventana_log" not in gdf.columns:
    gdf["mejor_ventana_log"] = 15
if "mejor_ventana_op" not in gdf.columns:
    gdf["mejor_ventana_op"] = 15
if "modelo_origen" not in gdf.columns:
    gdf["modelo_origen"] = "propio"
if "auc_log" not in gdf.columns:
    gdf["auc_log"] = 0.890
if "dist_modelo_vecino_km" not in gdf.columns:
    gdf["dist_modelo_vecino_km"] = 0.0

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
        # Distritos con alerta activa para sugerencia rápida
        filtro_sug = (gdf["prob"] >= 0.20) | (gdf["supera_corte_log"] == 1) | (gdf["evento_op"] == 1)
        distritos_disponibles = sorted(gdf[filtro_sug]["DISTRITO"].unique().tolist())
        
    opciones_dist = ["(Nacional / Sin selección)"] + distritos_disponibles
    dist_sel = st.selectbox("Distrito / Zona:", options=opciones_dist, index=0)
    
    st.markdown("---")
    st.markdown("#### 🎚️ **Filtro de Niveles de Alerta**")
    
    severidad_sel = st.radio(
        "Nivel de Alerta:",
        options=[
            "Todas las Celdas",
            "🔴 Nivel de Alerta: Alta",
            "🟡 Nivel de Alerta: Media",
            "⚪ Nivel de Alerta: Baja",
            "🚨 Operativa",
            "⚡ Doble Alerta"
        ],
        index=0
    )
    
    st.markdown("---")
    if st.button("ℹ️ Acerca de ARES Nacional", key="btn_sb_acerca", use_container_width=True, help="Conoce los fundamentos metodológicos, fuentes de datos y autores"):
        modal_acerca_de()
    
# Parámetros por defecto para el renderizado del mapa
mostrar_rios = True
mostrar_dept = True
modo_3d = False
estilo_mapa_sel = "Oscuro"

# ----------------- GESTIÓN DE BOTONES REGIONALES (SESSION STATE) -----------------
if "reg_foco" not in st.session_state:
    st.session_state["reg_foco"] = "nacional"

# ----------------- FILTRADO DINÁMICO DE DATOS -----------------
gdf_filtrado = gdf.copy()

# Filtro por departamento
if dept_sel != "Todos los Departamentos":
    gdf_filtrado = gdf_filtrado[gdf_filtrado["DEPARTAMENTO"] == dept_sel]

# Filtro por severidad y modo visual para PyDeck
if severidad_sel == "🔴 Nivel de Alerta: Alta (2)":
    gdf_filtrado = gdf_filtrado[gdf_filtrado["nivel_alerta_cod"] == 2]
    modo_clave = "prob"
elif severidad_sel == "🟡 Nivel de Alerta: Media (1)":
    gdf_filtrado = gdf_filtrado[gdf_filtrado["nivel_alerta_cod"] == 1]
    modo_clave = "prob"
elif severidad_sel == "⚪ Nivel de Alerta: Baja (0)":
    gdf_filtrado = gdf_filtrado[gdf_filtrado["nivel_alerta_cod"] == 0]
    modo_clave = "prob"
elif severidad_sel == "🚨 Operativa":
    gdf_filtrado = gdf_filtrado[gdf_filtrado["evento_op"] == 1]
    modo_clave = "op"
elif severidad_sel == "⚡ Doble Alerta":
    gdf_filtrado = gdf_filtrado[gdf_filtrado["doble_alerta"] == 1]
    modo_clave = "dual"
else:
    modo_clave = "prob"

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
    if punto_foco:
        st.markdown("---")
        fila_f = gdf[gdf["DISTRITO"] == dist_sel].sort_values(by="prob", ascending=False).iloc[0]
        prob_pct = float(fila_f["prob_pct"])
        evento_op = int(fila_f["evento_op"])
        doble = int(fila_f["doble_alerta"])
        iop_val = float(fila_f["Iop"])
        umbral_val = float(fila_f["umbral_op"])
        ventana_d = int(fila_f["mejor_ventana_log"])
        mod_origen = str(fila_f.get("modelo_origen", "propio"))
        auc_val = float(fila_f.get("auc_log", 0.890))
        dist_km = float(fila_f.get("dist_modelo_vecino_km", 0.0))

        if doble == 1:
            badge_html = '<span class="badge-dual">⚡ DOBLE ALERTA</span>'
        elif evento_op == 1:
            badge_html = '<span class="badge-critical">🚨 ALERTA OP</span>'
        elif prob_pct >= 70:
            badge_html = '<span class="badge-critical">🔴 CRÍTICO</span>'
        elif prob_pct >= 40:
            badge_html = '<span class="badge-high">🟠 ALTO</span>'
        elif prob_pct >= 20:
            badge_html = '<span class="badge-mod">🟡 MODERADO</span>'
        else:
            badge_html = '<span class="badge-normal">⚪ NORMAL</span>'

        if mod_origen.lower() == "propio":
            origen_badge = f'🔬 Modelo Propio · AUC: {auc_val:.3f}'
        else:
            origen_badge = f'📡 Modelo Vecino ({dist_km:.1f} km) · AUC: {auc_val:.3f}'

        pct_bar_prob = min(prob_pct, 100.0)
        pct_bar_iop = min((iop_val / umbral_val * 100.0) if umbral_val > 0 else 0.0, 100.0)

        st.markdown(f"""
        <div class="detail-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <div class="detail-title">📍 {fila_f['DISTRITO']}</div>
                {badge_html}
            </div>
            <div class="detail-sub">{fila_f['PROVINCIA']}, {fila_f['DEPARTAMENTO']} · Celda #{int(fila_f['id'])}</div>
            
            <div style="margin-bottom: 10px; background: rgba(0,0,0,0.25); padding: 8px 10px; border-radius: 6px; border: 1px solid #30363d;">
                <div style="font-size: 0.73rem; color: #8b949e; text-transform: uppercase; font-weight: 600; margin-bottom: 3px;">
                    📈 Modelo Logístico (Firth)
                </div>
                <div style="display: flex; justify-content: space-between; font-size: 0.82rem; margin-bottom: 2px;">
                    <span>Probabilidad: <b style="color: #f2cc60;">{prob_pct:.1f}%</b></span>
                </div>
                <div style="width: 100%; background: #21262d; height: 6px; border-radius: 3px; overflow: hidden;">
                    <div style="width: {pct_bar_prob}%; background: {'#ff9800' if prob_pct>=40 else '#f2cc60'}; height: 100%;"></div>
                </div>
            </div>

            <div style="margin-bottom: 10px; background: rgba(0,0,0,0.25); padding: 8px 10px; border-radius: 6px; border: 1px solid #30363d;">
                <div style="font-size: 0.73rem; color: #8b949e; text-transform: uppercase; font-weight: 600; margin-bottom: 3px;">
                    🌊 Modelo Físico-Operativo (Iop)
                </div>
                <div style="display: flex; justify-content: space-between; font-size: 0.82rem; margin-bottom: 2px;">
                    <span>Severidad: <b style="color: #58a6ff;">{iop_val:.1f} mm</b></span>
                    <span style="color: #8b949e;">Umbral Crítico: <b>{umbral_val:.1f} mm</b></span>
                </div>
                <div style="width: 100%; background: #21262d; height: 6px; border-radius: 3px; overflow: hidden;">
                    <div style="width: {pct_bar_iop}%; background: {'#f85149' if evento_op==1 else '#58a6ff'}; height: 100%;"></div>
                </div>
            </div>

            <div style="font-size: 0.73rem; color: #8b949e; margin-top: 4px; border-top: 1px solid #21262d; padding-top: 5px;">
                {origen_badge}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Mini gráfico de diagnóstico hídrico (Precipitación Hoy vs Antecedente de la ventana óptima)
        df_diag = pd.DataFrame({
            "Componente": ["Lluvia Hoy (pp)", f"Antecedente ({ventana_d}d)"],
            "Milimetros": [float(fila_f["pp"]), float(fila_f["ant_log"])]
        })
        chart_diag = alt.Chart(df_diag).mark_bar(cornerRadius=4).encode(
            x=alt.X("Milimetros:Q", title="Milímetros (mm)"),
            y=alt.Y("Componente:N", title=None, sort=None),
            color=alt.Color("Componente:N", scale=alt.Scale(domain=["Lluvia Hoy (pp)", f"Antecedente ({ventana_d}d)"], range=["#58a6ff", "#3fb950"]), legend=None),
            tooltip=["Componente", "Milimetros"]
        ).properties(height=95)
        st.caption(f"💧 **Diagnóstico Hídrico (Ventana Crítica: {ventana_d} días):**")
        st.altair_chart(chart_diag, use_container_width=True)

# ----------------- KPIS EJECUTIVOS NACIONALES -----------------
col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)

celdas_doble = int(gdf["doble_alerta"].sum())
celdas_en_alerta_op = int(gdf["evento_op"].sum())
celdas_criticas = int((gdf["prob"] >= 0.70).sum())
max_pp = gdf["pp"].max() if not gdf.empty else 0.0

with col_kpi1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">⚡ DOBLE ALERTA</div>
        <div class="metric-value" style="color: #ff0055;">{celdas_doble}</div>
    </div>
    """, unsafe_allow_html=True)

with col_kpi2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">🌊 ALERTA OP (IOP)</div>
        <div class="metric-value" style="color: #ff5252;">{celdas_en_alerta_op}</div>
    </div>
    """, unsafe_allow_html=True)

with col_kpi3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">🔴 CRÍTICO (≥70%)</div>
        <div class="metric-value" style="color: #f2cc60;">{celdas_criticas}</div>
    </div>
    """, unsafe_allow_html=True)

with col_kpi4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">LLUVIA MÁX 24H</div>
        <div class="metric-value" style="color: #58a6ff;">{max_pp:.1f} <span style="font-size: 0.82rem; font-weight: normal;">mm</span></div>
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
    if st.button("⛰️ Sierra Sur", use_container_width=True):
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

# Renderizar DeckGL dentro de un iframe autocontenido. Así el canvas y el
# elemento tooltip comparten el mismo sistema de coordenadas aun en Cloud.
components.html(mapa_deck.to_html(as_string=True), height=500, scrolling=False)

# ----------------- LEYENDA FLOTANTE GOOGLE FLOOD HUB -----------------
rios_leyenda = '<div style="display: flex; align-items: center; gap: 6px; border-left: 1px solid #30363d; padding-left: 10px;"><span style="width: 14px; height: 3px; background: #00e5ff; display: inline-block;"></span> <span style="color: #00e5ff; font-weight: 600;">Ríos ANA</span></div>' if mostrar_rios else ''

leyenda_html = f"""
<div style="display: flex; justify-content: flex-end; margin-top: -55px; margin-bottom: 20px; padding-right: 20px; position: relative; z-index: 10;">
    <div style="background: rgba(22, 27, 34, 0.95); backdrop-filter: blur(8px); border: 1px solid #30363d; border-radius: 8px; padding: 10px 16px; box-shadow: 0 4px 14px rgba(0,0,0,0.5); font-family: sans-serif; font-size: 12px;">
        <div style="color: #8b949e; font-size: 10px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">Niveles de Alerta Nacional (ARES · Estudio de Umbrales SENAMHI)</div>
        <div style="display: flex; gap: 14px; align-items: center; flex-wrap: wrap;">
            <div style="display: flex; align-items: center; gap: 6px;"><span style="width: 12px; height: 12px; background: rgba(200, 200, 200, 0.2); border: 1px solid #555; border-radius: 3px; display: inline-block;"></span> <span style="color: #8b949e;">0 Baja</span></div>
            <div style="display: flex; align-items: center; gap: 6px;"><span style="width: 12px; height: 12px; background: rgb(255, 235, 59); border-radius: 3px; display: inline-block;"></span> <span style="color: #f2cc60;">1 Media</span></div>
            <div style="display: flex; align-items: center; gap: 6px;"><span style="width: 12px; height: 12px; background: rgb(244, 67, 54); border-radius: 3px; display: inline-block;"></span> <span style="color: #f85149; font-weight: bold;">2 Alta</span></div>
            <div style="display: flex; align-items: center; gap: 6px;"><span style="width: 12px; height: 12px; background: rgb(255, 23, 68); border-radius: 3px; display: inline-block;"></span> <span style="color: #ff1744; font-weight: bold;">🚨 Alerta Op (Iop)</span></div>
            <div style="display: flex; align-items: center; gap: 6px;"><span style="width: 12px; height: 12px; background: rgb(255, 0, 85); border-radius: 3px; display: inline-block; box-shadow: 0 0 6px #ff0055;"></span> <span style="color: #ff0055; font-weight: bold;">⚡ Doble Alerta</span></div>
            {rios_leyenda}
            <div style="display: flex; align-items: center; gap: 6px; border-left: 1px solid #30363d; padding-left: 10px;"><span style="width: 10px; height: 10px; border-radius: 50%; background: #00e5ff; display: inline-block; box-shadow: 0 0 8px #00e5ff;"></span> <span style="color: #00e5ff; font-weight: bold;">Foco</span></div>
        </div>
    </div>
</div>
"""
st.markdown(leyenda_html, unsafe_allow_html=True)

# ----------------- TABLA DE DETALLE Y EXPORTACIÓN SENAMHI -----------------
with st.expander("📋 **Boletín Ejecutivo: Tabla de Zonas Bajo Alerta & Exportación SENAMHI**", expanded=False):
    # Celdas que presentan al menos una señal de alerta operativa o probabilística
    filtro_alerta_tabla = (gdf["prob"] >= 0.20) | (gdf["supera_corte_log"] == 1) | (gdf["evento_op"] == 1)
    df_export = gdf[filtro_alerta_tabla][
        [
            "id", "DEPARTAMENTO", "PROVINCIA", "DISTRITO",
            "prob_pct",
            "Iop", "umbral_op", "evento_op", "doble_alerta",
            "pp", "ant_log", "mejor_ventana_log", "modelo_origen", "auc_log",
            "lat", "lon"
        ]
    ].sort_values(by="prob_pct", ascending=False)
    
    st.dataframe(
        df_export.rename(columns={
            "id": "ID Celda",
            "prob_pct": "Prob (%)",
            "Iop": "Severidad Iop (mm)",
            "umbral_op": "Umbral Crítico (mm)",
            "evento_op": "Alerta Operativa",
            "doble_alerta": "Doble Alerta",
            "pp": "Lluvia 24h (mm)",
            "ant_log": "Antecedente (mm)",
            "mejor_ventana_log": "Ventana (d)",
            "modelo_origen": "Modelo",
            "auc_log": "AUC-ROC",
            "lat": "Lat",
            "lon": "Lon"
        }),
        use_container_width=True,
        hide_index=True
    )
    
    col_exp1, col_exp2 = st.columns([1, 4])
    with col_exp1:
        csv_data = df_export.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Descargar Boletín CSV Completo",
            data=csv_data,
            file_name=f"boletin_inundaciones_SENAMHI_{fecha_sel}.csv",
            mime="text/csv"
        )
