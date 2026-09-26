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
    Retorna la lista de rutas candidatas donde residen las salidas operativas del modelo.
    Prioridad: Salidas (actualizada a las 2:50 PM), luego data (respaldo).
    Soporta variaciones de mayúsculas/minúsculas para Linux.
    """
    candidatos = [
        os.path.join(BASE_DIR, "Salidas"),
        os.path.join(BASE_DIR, "SALIDAS"),
        os.path.join(BASE_DIR, "salidas"),
        os.path.join(BASE_DIR, "data"),
        os.path.join(BASE_DIR, "DATA"),
    ]
    directorios = []
    vistos = set()
    for ruta in candidatos:
        ruta_norm = os.path.normpath(ruta)
        if os.path.isdir(ruta) and ruta_norm not in vistos:
            vistos.add(ruta_norm)
            directorios.append(ruta)
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
    
    # Limpiar y formatear métricas
    gdf["prob_pct"] = (gdf["prob"] * 100).round(1)
    gdf["pp"] = gdf["pp"].fillna(0.0).round(1)
    gdf["ant_log"] = gdf["ant_log"].fillna(0.0).round(1)
    gdf["evento_op"] = gdf["evento_op"].fillna(0).astype(int)
    gdf["evento_log"] = gdf["evento_log"].fillna(0).astype(int)
    
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

    # Cargar CSV resumen si existe para métricas tabulares rápidas
    df_resumen = None
    if csv_path and os.path.exists(csv_path):
        df_resumen = pd.read_csv(csv_path)
        
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
