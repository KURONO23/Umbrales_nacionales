import os
import glob
import pandas as pd
import geopandas as gpd
import streamlit as st

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

@st.cache_data(show_spinner=False)
def obtener_fechas_disponibles():
    """Busca todas las fechas disponibles en la carpeta data."""
    patron = os.path.join(DATA_DIR, "grillaPISCO_prob_*.gpkg")
    archivos = glob.glob(patron)
    fechas = []
    for arc in archivos:
        nombre = os.path.basename(arc)
        # grillaPISCO_prob_YYYY-MM-DD.gpkg -> YYYY-MM-DD
        fecha = nombre.replace("grillaPISCO_prob_", "").replace(".gpkg", "")
        fechas.append(fecha)
    fechas.sort(reverse=True)
    return fechas

@st.cache_data(show_spinner=False)
def cargar_datos_fecha(fecha: str):
    """
    Carga el GeoPackage y el CSV de la fecha dada optimizando campos y memoria.
    """
    gpkg_path = os.path.join(DATA_DIR, f"grillaPISCO_prob_{fecha}.gpkg")
    csv_path = os.path.join(DATA_DIR, f"resumen_prob_grillaPISCO_{fecha}.csv")
    
    if not os.path.exists(gpkg_path):
        raise FileNotFoundError(f"No se encontró el GeoPackage para la fecha {fecha}")
        
    # Cargar GeoPackage
    gdf = gpd.read_file(gpkg_path, engine="pyogrio")
    
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
    ubigeo_path = os.path.join(DATA_DIR, "celdas_ubigeo.csv")
    if os.path.exists(ubigeo_path):
        df_ubi = pd.read_csv(ubigeo_path)
        # Deduplicar por id para asegurar exactamente 1 fila por celda
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
    if os.path.exists(csv_path):
        df_resumen = pd.read_csv(csv_path)
        
    return gdf, df_resumen

@st.cache_data(show_spinner=False)
def cargar_limite_peru():
    """Carga el contorno nacional de Perú."""
    shp_path = os.path.join(DATA_DIR, "Peru.shp")
    if os.path.exists(shp_path):
        gdf_peru = gpd.read_file(shp_path, engine="pyogrio")
        if gdf_peru.crs is None or gdf_peru.crs.to_epsg() != 4326:
            gdf_peru = gdf_peru.to_crs(epsg=4326)
        return gdf_peru
    return None

@st.cache_data(show_spinner=False)
def cargar_red_hidrica():
    """Carga la red hídrica optimizada de ríos y quebradas ANA."""
    geojson_path = os.path.join(DATA_DIR, "red_hidrica.geojson")
    if os.path.exists(geojson_path):
        with open(geojson_path, "r", encoding="utf-8") as f:
            import json
            return json.load(f)
    return None
