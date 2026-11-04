"""Capa visual GFS alineada a la malla PISCO con información territorial enriquecida."""

from pathlib import Path
import functools
import numpy as np
import pandas as pd
import rasterio


def capas_gfs(directorio):
    return sorted(Path(directorio).glob("gfs_pisco_*_*.tif"))


@functools.lru_cache(maxsize=1)
def cargar_ubigeo_grid():
    """Carga y mapea en memoria la relación (row, col) a id y datos territoriales."""
    csv_path = Path(__file__).resolve().parent.parent / "data" / "grid_cell_ubigeo.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        lookup = {}
        for _, r in df.iterrows():
            lookup[(int(r["row"]), int(r["col"]))] = (
                r["id"],
                r["DEPARTAMENTO"],
                r["PROVINCIA"],
                r["DISTRITO"]
            )
        return lookup
    return {}


def preparar_capa_gfs(raster):
    with rasterio.open(raster) as src:
        valores = src.read(1, masked=True)
        transform = src.transform
        if str(src.crs) != "EPSG:4326" or abs(transform.a - 0.1) > 1e-8 or abs(transform.e + 0.1) > 1e-8:
            raise ValueError("La capa GFS no coincide con la resolución PISCO en EPSG:4326")
    fecha = Path(raster).stem.rsplit("_", 1)[-1]
    lookup = cargar_ubigeo_grid()
    features = []
    for fila, columna in np.argwhere(~np.ma.getmaskarray(valores) & np.isfinite(valores.data) & (valores.data >= 0)):
        mm = float(valores[fila, columna])
        x0 = float(transform.c + columna * transform.a)
        y0 = float(transform.f + fila * transform.e)
        x1, y1 = x0 + transform.a, y0 + transform.e
        cx = round(x0 + transform.a / 2, 4)
        cy = round(y0 + transform.e / 2, 4)
        color = [34, 197, 226, 105] if mm < 10 else [42, 126, 244, 135] if mm < 30 else [129, 70, 235, 160] if mm < 60 else [219, 52, 184, 180]

        info = lookup.get((fila, columna))
        if info:
            c_id, dep, prov, dist = info
            distrito = dist if pd.notna(dist) and dist != "N/D" else "Zona Rural / Cuenca"
            provincia = prov if pd.notna(prov) and prov != "N/D" else "Área Pluviométrica"
            departamento = dep if pd.notna(dep) and dep != "N/D" else "Perú"
            celda_id = str(int(c_id))
        else:
            distrito = "Malla GFS (Precipitación)"
            provincia = "Cobertura 0.1°"
            departamento = "Perú"
            celda_id = f"GFS-{fila}-{columna}"

        props = {
            "DISTRITO": distrito,
            "PROVINCIA": provincia,
            "DEPARTAMENTO": departamento,
            "nivel_alerta_txt": "Sin Alerta Urbana (Monitoreo GFS)",
            "nivel_alerta_color": "#42c6e2",
            "pp": round(mm, 1),
            "ant_log": "-",
            "mejor_ventana_log": "-",
            "gfs_mm": round(mm, 1),
            "fecha_gfs": fecha,
            "modelo_origen_txt": "Pronóstico Meteorológico GFS (0.25° NOAA / SENAMHI)",
            "id": celda_id,
            "lat": cy,
            "lon": cx,
            "fill_color": color,
        }
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]
            },
            "properties": props
        })
    return {"type": "FeatureCollection", "features": features}
