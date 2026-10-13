import os
import glob
import re
import pandas as pd
import geopandas as gpd
import streamlit as st

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

def obtener_directorios_salida():
    """
    Retorna la lista de rutas donde residen las salidas operativas del modelo.
    Prioridad exclusiva: Salidas/ (actualizada automáticamente a las 2:50 PM).
    Soporta variaciones de mayúsculas/minúsculas para Linux.
    """
    candidatos = [
        os.path.join(BASE_DIR, "Salidas"),
        os.path.join(BASE_DIR, "SALIDAS"),
        os.path.join(BASE_DIR, "salidas"),
    ]
    directorios = []
    vistos = set()
    for ruta in candidatos:
        ruta_norm = os.path.normpath(ruta)
        if os.path.isdir(ruta) and ruta_norm not in vistos:
            vistos.add(ruta_norm)
            directorios.append(ruta)
            
    # Solo si la carpeta Salidas no existiera, fallback defensivo a data/
    if not directorios:
        fallback_data = os.path.join(BASE_DIR, "data")
        if os.path.isdir(fallback_data):
            directorios.append(fallback_data)
            
    return directorios

def buscar_archivo_salida(nombre_archivo: str):
    """
    Busca un archivo operativo en las carpetas de salida disponibles (Salidas, data).
    """
    for d in obtener_directorios_salida():
        path = os.path.join(d, nombre_archivo)
        if os.path.exists(path):
            return path
    return None

def buscar_archivo_estatico(nombre_archivo: str):
    """
    Busca capas base estáticas (celdas_ubigeo.csv, departamentos.geojson, etc.).
    """
    path_data = os.path.join(DATA_DIR, nombre_archivo)
    if os.path.exists(path_data):
        return path_data
    for d in obtener_directorios_salida():
        path = os.path.join(d, nombre_archivo)
        if os.path.exists(path):
            return path
    return None

@st.cache_data(ttl=120, show_spinner=False)
def obtener_fechas_disponibles():
    """
    Escanea las carpetas de salida (Salidas y data) buscando todos los archivos grillaPISCO_prob_*.gpkg.
    Extrae las fechas YYYY-MM-DD y las devuelve ordenadas descendentemente (más reciente primero).
    Tiene TTL de 120s para detectar automáticamente la actualización diaria de las 2:50 PM.
    """
    fechas = set()
    for d in obtener_directorios_salida():
        patron = os.path.join(d, "grillaPISCO_prob_*.gpkg")
        archivos = glob.glob(patron)
        for arc in archivos:
            nombre = os.path.basename(arc)
            match = re.search(r"grillaPISCO_prob_(\d{4}-\d{2}-\d{2})\.gpkg", nombre, re.IGNORECASE)
            if match:
                fechas.add(match.group(1))
                
    lista_fechas = sorted(list(fechas), reverse=True)
    return lista_fechas

@st.cache_data(ttl=300, show_spinner=False)
def cargar_datos_fecha(fecha: str):
    """
    Carga el GeoPackage y el CSV de la fecha dada desde la carpeta Salidas (o data).
    """
    gpkg_path = buscar_archivo_salida(f"grillaPISCO_prob_{fecha}.gpkg")
    csv_path = buscar_archivo_salida(f"resumen_prob_grillaPISCO_{fecha}.csv")
    
    if not gpkg_path or not os.path.exists(gpkg_path):
        raise FileNotFoundError(f"No se encontró el archivo vectorial 'grillaPISCO_prob_{fecha}.gpkg' en Salidas ni en data.")
        
    # Cargar GeoPackage con fallback seguro (pyogrio primero, luego fiona/default)
    try:
        gdf = gpd.read_file(gpkg_path, engine="pyogrio")
    except Exception:
        gdf = gpd.read_file(gpkg_path)
    
    # Filtrar solo celdas con probabilidad definida (las 3,993 de interés)
    gdf = gdf[gdf["prob"].notnull()].copy()
    
    # Asegurar tipos y CRS WGS84
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
        
    # Calcular centroides para Tooltip y capas puntuales rápidas
    gdf["lon"] = gdf.geometry.centroid.x.round(4)
    gdf["lat"] = gdf.geometry.centroid.y.round(4)
    gdf["id_num"] = gdf["id"].astype(float).astype(int)

    # Cargar CSV resumen si existe para métricas tabulares completas del estudio
    df_resumen = None
    if csv_path and os.path.exists(csv_path):
        try:
            df_resumen = pd.read_csv(csv_path)
            df_resumen["id_num"] = df_resumen["ciudad"].astype(float).astype(int)
            cols_resumen = [c for c in ["id_num", "prob_corte", "umbral_op", "Iop", "ant_op", "evento_log"] if c in df_resumen.columns]
            gdf = gdf.merge(df_resumen[cols_resumen], on="id_num", how="left", suffixes=("", "_csv"))
            for c_dup in ["Iop", "ant_op", "evento_log"]:
                if f"{c_dup}_csv" in gdf.columns:
                    gdf[c_dup] = gdf[c_dup].combine_first(gdf[f"{c_dup}_csv"])
                    gdf.drop(columns=[f"{c_dup}_csv"], inplace=True)
        except Exception:
            pass

    # Integrar metadatos de calibración por celda (cuadro_ciudad.csv)
    calib_path = buscar_archivo_estatico("cuadro_ciudad.csv")
    if calib_path and os.path.exists(calib_path):
        try:
            df_calib = pd.read_csv(calib_path)
            df_calib["id_num"] = df_calib["ciudad"].astype(float).astype(int)
            cols_calib = [c for c in ["id_num", "mejor_ventana_op", "mejor_ventana_log", "auc_log", "mcc_op", "prob_corte", "umbral_op", "modelo_origen", "dist_modelo_vecino_km"] if c in df_calib.columns]
            gdf = gdf.merge(df_calib[cols_calib], on="id_num", how="left", suffixes=("", "_calib"))
            if "prob_corte_calib" in gdf.columns:
                if "prob_corte" not in gdf.columns or gdf["prob_corte"].isnull().all():
                    gdf["prob_corte"] = gdf["prob_corte_calib"]
                else:
                    gdf["prob_corte"] = gdf["prob_corte"].combine_first(gdf["prob_corte_calib"])
                gdf.drop(columns=["prob_corte_calib"], inplace=True)
            if "umbral_op_calib" in gdf.columns:
                if "umbral_op" not in gdf.columns or gdf["umbral_op"].isnull().all():
                    gdf["umbral_op"] = gdf["umbral_op_calib"]
                else:
                    gdf["umbral_op"] = gdf["umbral_op"].combine_first(gdf["umbral_op_calib"])
                gdf.drop(columns=["umbral_op_calib"], inplace=True)
        except Exception:
            pass

    # Limpiar y formatear métricas del modelo
    gdf["prob_pct"] = (gdf["prob"] * 100).round(1)
    if "prob_corte" in gdf.columns:
        gdf["prob_corte"] = gdf["prob_corte"].fillna(0.20)
        gdf["prob_corte_pct"] = (gdf["prob_corte"] * 100).round(1)
    else:
        gdf["prob_corte"] = 0.20
        gdf["prob_corte_pct"] = 20.0

    gdf["pp"] = gdf["pp"].fillna(0.0).round(1)
    gdf["ant_log"] = gdf["ant_log"].fillna(0.0).round(1)
    if "ant_op" in gdf.columns:
        gdf["ant_op"] = gdf["ant_op"].fillna(0.0).round(1)
    else:
        gdf["ant_op"] = gdf["ant_log"]

    if "Iop" in gdf.columns:
        gdf["Iop"] = gdf["Iop"].fillna(gdf["pp"] + gdf["ant_op"]).round(1)
    else:
        gdf["Iop"] = (gdf["pp"] + gdf["ant_op"]).round(1)

    if "umbral_op" in gdf.columns:
        gdf["umbral_op"] = gdf["umbral_op"].fillna(50.0).round(1)
    else:
        gdf["umbral_op"] = 50.0

    gdf["evento_op"] = gdf["evento_op"].fillna(0).astype(int)
    gdf["evento_log"] = gdf["evento_log"].fillna(0).astype(int)

    # Indicador de superación de corte probabilístico calibrado (Youden)
    gdf["supera_corte_log"] = (gdf["prob"] >= gdf["prob_corte"]).astype(int)
    # Doble Alerta: activa cuando AMBOS modelos superan su condición crítica
    gdf["doble_alerta"] = ((gdf["supera_corte_log"] == 1) & (gdf["evento_op"] == 1)).astype(int)

    # Metadatos descriptivos de calibración
    if "modelo_origen" not in gdf.columns:
        gdf["modelo_origen"] = "propio"
    else:
        gdf["modelo_origen"] = gdf["modelo_origen"].fillna("propio")

    if "mejor_ventana_log" not in gdf.columns:
        gdf["mejor_ventana_log"] = 15
    else:
        gdf["mejor_ventana_log"] = gdf["mejor_ventana_log"].fillna(15).astype(int)

    if "mejor_ventana_op" not in gdf.columns:
        gdf["mejor_ventana_op"] = 15
    else:
        gdf["mejor_ventana_op"] = gdf["mejor_ventana_op"].fillna(15).astype(int)

    if "auc_log" in gdf.columns:
        gdf["auc_log"] = gdf["auc_log"].round(3)
    else:
        gdf["auc_log"] = 0.890

    if "dist_modelo_vecino_km" in gdf.columns:
        gdf["dist_modelo_vecino_km"] = gdf["dist_modelo_vecino_km"].fillna(0.0).round(1)
    else:
        gdf["dist_modelo_vecino_km"] = 0.0

    # Integrar información de Ubigeo (Departamento, Provincia, Distrito)
    ubigeo_path = buscar_archivo_estatico("celdas_ubigeo.csv")
    if ubigeo_path and os.path.exists(ubigeo_path):
        df_ubi = pd.read_csv(ubigeo_path)
        df_ubi_clean = df_ubi.drop_duplicates(subset=["id"], keep="first")
        gdf = gdf.merge(df_ubi_clean[["id", "DEPARTAMENTO", "PROVINCIA", "DISTRITO"]], on="id", how="left")
        gdf["DEPARTAMENTO"] = gdf["DEPARTAMENTO"].fillna("Sin Datos")
        gdf["PROVINCIA"] = gdf["PROVINCIA"].fillna("Sin Datos")
        gdf["DISTRITO"] = gdf["DISTRITO"].fillna("Sin Datos")
    else:
        gdf["DEPARTAMENTO"] = "N/D"
        gdf["PROVINCIA"] = "N/D"
        gdf["DISTRITO"] = "N/D"

    return gdf, df_resumen

@st.cache_data(show_spinner=False)
def cargar_limite_peru():
    """Carga el contorno nacional de Perú."""
    shp_path = buscar_archivo_estatico("Peru.shp")
    if shp_path and os.path.exists(shp_path):
        gdf_peru = gpd.read_file(shp_path, engine="pyogrio")
        if gdf_peru.crs is None or gdf_peru.crs.to_epsg() != 4326:
            gdf_peru = gdf_peru.to_crs(epsg=4326)
        return gdf_peru
    return None

@st.cache_data(show_spinner=False)
def cargar_red_hidrica():
    """Carga la red hídrica optimizada de ríos y quebradas ANA."""
    geojson_path = buscar_archivo_estatico("red_hidrica.geojson")
    if geojson_path and os.path.exists(geojson_path):
        with open(geojson_path, "r", encoding="utf-8") as f:
            import json
            return json.load(f)
    return None

@st.cache_data(show_spinner=False)
def cargar_departamentos():
    """Carga los límites departamentales del Perú en formato GeoJSON."""
    geojson_path = buscar_archivo_estatico("departamentos.geojson")
    if geojson_path and os.path.exists(geojson_path):
        with open(geojson_path, "r", encoding="utf-8") as f:
            import json
            return json.load(f)
    return None
