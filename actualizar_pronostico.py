r"""
Módulo Integrador y Extractor de Pronósticos ARES y GFS a 10 Días
=================================================================
Extrae y sincroniza automáticamente todas las salidas del pronóstico GFS y del modelo
hidrológico ARES desde el repositorio de red (\\DHI-FVJ2HGR\SalidasGFS) o local hacia Salidas/.

Extrae día a día (1 a 10 días):
1. grillaPISCO_prob_{fecha}.gpkg (Capa vectorial para PyDeck y mapa de calor)
2. resumen_prob_grillaPISCO_{fecha}.csv (Resumen tabular de celdas y umbrales)
3. diagnostico_operativo_{fecha}.csv (Métricas de diagnóstico del día)
4. nivel_alerta_grillaPISCO_{fecha}.tif (Raster de niveles de alerta 0, 1, 2)
5. prob_grillaPISCO_{fecha}.tif (Raster continuo de probabilidades)
6. evento_op_grillaPISCO_{fecha}.tif (Raster de evento operativo 0, 1)
7. evento_log_grillaPISCO_{fecha}.tif (Raster de evento logarítmico 0, 1)
8. pp_puntual_grillaPISCO_{fecha}.tif (Raster de lluvia puntual PISCO)
9. ant_log_grillaPISCO_{fecha}.tif (Raster de antecedente logarítmico)
10. gfs_pisco_20261104_{fecha}.tif (Raster de lluvia GFS remuestreada)

Además mantiene todos los archivos consolidados y cubos 3D de la emisión.
"""

import os
import sys
import shutil
from pathlib import Path
from ftplib import FTP
import io
import pandas as pd
import geopandas as gpd
import numpy as np
import xarray as xr
import rasterio
from rasterio.transform import Affine

BASE_DIR = Path(__file__).resolve().parent
SALIDAS_DIR = BASE_DIR / "Salidas"
RED_DIR = Path(r"\\DHI-FVJ2HGR\SalidasGFS")
FTP_HOST_DEFAULT = "ftp.senamhi.gob.pe"
FTP_BASE_DEFAULT = "HIDROLOGIA/GFS"

# Geotransform estándar de grilla PISCO (0.1 deg, origen -81.4, 2.0)
PISCO_TRANSFORM = Affine(0.1, 0.0, -81.4, 0.0, -0.1, 2.0)
PISCO_CRS = "EPSG:4326"
PISCO_HEIGHT = 210
PISCO_WIDTH = 174


def descargar_gfs_ftp(destino=SALIDAS_DIR, host=FTP_HOST_DEFAULT, user="senamhi", password="", ruta_base=FTP_BASE_DEFAULT):
    """Descarga opcionalmente la corrida más reciente de GFS desde el FTP de SENAMHI."""
    if not password:
        print("[INFO GFS] Sin contraseña FTP configurada. Se usarán los archivos locales/red existentes.")
        return None
    try:
        print(f"[FTP GFS] Conectando a {host} ({ruta_base})...")
        with FTP(host, timeout=30) as ftp:
            ftp.login(user=user, passwd=password)
            ftp.cwd(ruta_base.strip("/"))
            carpetas = sorted([n for n in ftp.nlst() if n.isdigit() and len(n) == 8], reverse=True)
            if not carpetas:
                print("[FTP GFS] No se encontraron carpetas con formato YYYYMMDD.")
                return None
            ultima_fecha = carpetas[0]
            archivo_nc = f"pp_GFS_{ultima_fecha}.nc"
            ruta_local = Path(destino) / archivo_nc
            if ruta_local.exists():
                print(f"[FTP GFS] La corrida {ultima_fecha} ya existe localmente ({archivo_nc}).")
                return ruta_local
            print(f"[FTP GFS] Descargando nueva corrida {ultima_fecha}: {archivo_nc}...")
            ftp.cwd(f"{ruta_base.strip('/')}/{ultima_fecha}")
            with open(ruta_local, "wb") as f:
                ftp.retrbinary(f"RETR {archivo_nc}", f.write)
            print(f"[FTP GFS] Descarga exitosa: {ruta_local}")
            return ruta_local
    except Exception as exc:
        print(f"[FTP GFS] Error al consultar FTP: {exc}")
        return None


def exportar_rasters_desde_netcdf(origen, destino):
    """Extrae cada rebanada temporal de los cubos NetCDF a GeoTIFFs diarios."""
    cubos = [
        ("nivel_alerta_GFS_grillaPISCO_emision_*.nc", "nivel_alerta", "nivel_alerta_grillaPISCO", "int32", -2147483648),
        ("prob_GFS_grillaPISCO_emision_*.nc", "prob", "prob_grillaPISCO", "float32", np.nan),
        ("evento_op_GFS_grillaPISCO_emision_*.nc", "evento_op", "evento_op_grillaPISCO", "int32", -2147483648),
        ("evento_log_GFS_grillaPISCO_emision_*.nc", "evento_log", "evento_log_grillaPISCO", "int32", -2147483648),
        ("pp_GFS_grillaPISCO_emision_*.nc", "pp", "pp_puntual_grillaPISCO", "float32", np.nan),
    ]

    for patron, var_name, prefijo, dtype_str, nodata_val in cubos:
        archivos = sorted(origen.glob(patron), reverse=True)
        if not archivos:
            continue
        nc_path = archivos[0]
        try:
            with xr.open_dataset(nc_path) as ds:
                if var_name not in ds:
                    continue
                da = ds[var_name]
                fechas = pd.to_datetime(ds.time.values).strftime("%Y-%m-%d").tolist()
                for i, fecha in enumerate(fechas):
                    out_tif = destino / f"{prefijo}_{fecha}.tif"
                    slice_2d = da.values[i]
                    if dtype_str == "int32":
                        arr = np.where(np.isnan(slice_2d), nodata_val, slice_2d).astype(np.int32)
                    else:
                        arr = slice_2d.astype(np.float32)

                    with rasterio.open(
                        out_tif,
                        "w",
                        driver="GTiff",
                        height=slice_2d.shape[0],
                        width=slice_2d.shape[1],
                        count=1,
                        dtype=dtype_str,
                        crs=PISCO_CRS,
                        transform=PISCO_TRANSFORM,
                        nodata=nodata_val,
                        compress="lzw"
                    ) as dst:
                        dst.write(arr, 1)
            print(f" -> GeoTIFFs generados para '{prefijo}' ({len(fechas)} dias)")
        except Exception as e:
            print(f" [AVISO] Error al exportar GeoTIFFs de {nc_path.name}: {e}")


def exportar_ant_log_rasters(gdf_base, df_prob, destino):
    """Genera ant_log_grillaPISCO_{fecha}.tif a partir de la malla y tabla diaria."""
    try:
        inv_trans = ~PISCO_TRANSFORM
        cell_coords = {}
        for idx, row in gdf_base.iterrows():
            c_id = row.get("ID_CIUDAD")
            if pd.isna(c_id):
                continue
            geom = row.geometry
            cx, cy = geom.centroid.x, geom.centroid.y
            col, r = inv_trans * (cx, cy)
            r_idx, c_idx = int(round(r - 0.5)), int(round(col - 0.5))
            if 0 <= r_idx < PISCO_HEIGHT and 0 <= c_idx < PISCO_WIDTH:
                cell_coords[int(c_id)] = (r_idx, c_idx)

        fechas = sorted(df_prob["fecha"].unique())
        for fecha in fechas:
            sub = df_prob[df_prob["fecha"] == fecha]
            grid = np.full((PISCO_HEIGHT, PISCO_WIDTH), np.nan, dtype=np.float32)
            for _, r in sub.iterrows():
                try:
                    c_id = int(r["ciudad"])
                    if c_id in cell_coords:
                        grid[cell_coords[c_id]] = r.get("ant_log", np.nan)
                except Exception:
                    continue

            out_tif = destino / f"ant_log_grillaPISCO_{fecha}.tif"
            with rasterio.open(
                out_tif,
                "w",
                driver="GTiff",
                height=PISCO_HEIGHT,
                width=PISCO_WIDTH,
                count=1,
                dtype="float32",
                crs=PISCO_CRS,
                transform=PISCO_TRANSFORM,
                nodata=np.nan,
                compress="lzw"
            ) as dst:
                dst.write(grid, 1)
        print(f" -> GeoTIFFs generados para 'ant_log_grillaPISCO' ({len(fechas)} dias)")
    except Exception as e:
        print(f" [AVISO] Error al rasterizar ant_log: {e}")


def sincronizar_pronosticos(origen=RED_DIR, destino=SALIDAS_DIR):
    origen = Path(origen)
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)

    print("=== Iniciando sincronizacion completa de pronosticos ARES / GFS ===")
    print(f"Origen de datos: {origen}")
    print(f"Destino:         {destino}\n")

    if not origen.exists():
        print(f"[AVISO] No se pudo acceder a la ruta de red {origen}. Buscando archivos locales en {destino}...")
        origen = destino

    # 1. Sincronizar archivos consolidados y de emision
    if origen != destino:
        print("Sincronizando archivos consolidados desde el origen...")
        for item in origen.iterdir():
            if item.is_file():
                target = destino / item.name
                if not target.exists() or target.stat().st_size != item.stat().st_size:
                    shutil.copy2(item, target)
                    print(f" -> Copiado: {item.name}")

    # 2. Buscar archivo consolidado de pronostico de ARES
    gpkg_candidatos = sorted(origen.glob("grillaPISCO_pronostico_emision_*.gpkg"), reverse=True)
    csv_candidatos = sorted(origen.glob("pronostico_prob_grillaPISCO_emision_*.csv"), reverse=True)
    diag_candidatos = sorted(origen.glob("diagnostico_pronostico_emision_*.csv"), reverse=True)

    if not gpkg_candidatos or not csv_candidatos:
        print("[ERROR] No se encontraron archivos de emision de pronostico ARES (*_emision_*.gpkg/csv).")
        return False

    gpkg_base_path = gpkg_candidatos[0]
    csv_prob_path = csv_candidatos[0]
    print(f"\nCargando malla base:        {gpkg_base_path.name}")
    print(f"Cargando pronostico diario: {csv_prob_path.name}")

    gdf_base = gpd.read_file(gpkg_base_path)
    df_prob = pd.read_csv(csv_prob_path)

    fechas_pronostico = sorted(df_prob["fecha"].unique())
    print(f"Fechas detectadas en el horizonte ({len(fechas_pronostico)} dias):")
    print(", ".join(fechas_pronostico))

    # Claves numericas para merge exacto
    gdf_base["_join_key"] = pd.to_numeric(gdf_base["ID_CIUDAD"], errors="coerce")
    df_prob["_join_key"] = pd.to_numeric(df_prob["ciudad"], errors="coerce")

    cols_prob_target = [
        "prob", "evento_log", "evento_op", "pp", "ant_log", "ant_op",
        "Iop", "calidad_log", "calidad_op", "nivel_alerta", "nivel_alerta_cod"
    ]
    cols_resumen_csv = [
        "ciudad", "fecha", "pp", "ant_log", "ant_op", "prob", "prob_corte",
        "evento_log", "Iop", "umbral_op", "evento_op", "prob_corte_orig",
        "calidad_log", "calidad_op", "nivel_alerta_cod", "nivel_alerta"
    ]

    df_diag_all = pd.read_csv(diag_candidatos[0]) if diag_candidatos else None

    # 3. Generar vectoriales GPKG y CSVs diarios
    print("\nGenerando salidas vectoriales y CSVs diarios...")
    for fecha in fechas_pronostico:
        df_dia = df_prob[df_prob["fecha"] == fecha].copy()

        # CSV Resumen diario
        csv_dia_path = destino / f"resumen_prob_grillaPISCO_{fecha}.csv"
        cols_presentes = [c for c in cols_resumen_csv if c in df_dia.columns]
        df_dia[cols_presentes].to_csv(csv_dia_path, index=False)

        # Diagnostico diario
        if df_diag_all is not None and "fecha" in df_diag_all.columns:
            row_diag = df_diag_all[df_diag_all["fecha"] == fecha]
            if not row_diag.empty:
                diag_dia_path = destino / f"diagnostico_operativo_{fecha}.csv"
                row_diag.to_csv(diag_dia_path, index=False)

        # GeoPackage diario
        gpkg_dia_path = destino / f"grillaPISCO_prob_{fecha}.gpkg"
        gdf_dia = gdf_base[["id", "Area", "ID_CIUDAD", "geometry", "_join_key"]].merge(
            df_dia[["_join_key"] + [c for c in cols_prob_target if c in df_dia.columns]],
            on="_join_key",
            how="left"
        ).drop(columns=["_join_key"])

        gdf_dia.to_file(gpkg_dia_path, driver="GPKG")

    # 4. Extraer GeoTIFFs de todos los cubos NetCDF (nivel_alerta, prob, evento_op, evento_log, pp)
    print("\nExtrayendo capas raster diarias de cubos NetCDF...")
    exportar_rasters_desde_netcdf(origen, destino)

    # 5. Generar rasters de ant_log
    print("\nGenerando capas raster de ant_log...")
    exportar_ant_log_rasters(gdf_base, df_prob, destino)

    # 6. Capas de lluvia GFS remuestreadas
    print("\nVerificando capas raster de precipitacion GFS (gfs_pisco_*.tif)...")
    try:
        from preprocesar_gfs import preparar_si_nuevo
        tifs = preparar_si_nuevo(destino)
        print(f"Capas GFS listas: {len(tifs)} GeoTIFFs disponibles en Salidas/")
    except Exception as exc:
        print(f"[AVISO] Preprocesador GFS: {exc}")

    print("\n[OK] Sincronizacion completa finalizada con exito!")
    print("Todos los productos (GPKG, CSV, GeoTIFFs diarios y cubos NetCDF) estan disponibles en Salidas/.")
    return True


if __name__ == "__main__":
    sincronizar_pronosticos()
