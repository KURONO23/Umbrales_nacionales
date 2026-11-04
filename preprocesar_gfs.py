"""Prepara los pronósticos diarios GFS sobre la grilla PISCO por vecino más cercano."""
from pathlib import Path
import os
import re
import tempfile
import numpy as np
import rasterio
from rasterio.features import geometry_mask
import xarray as xr
import geopandas as gpd


def salidas_de_corrida(netcdf, destino):
    m = re.search(r'(\d{4})-?(\d{2})-?(\d{2})', Path(netcdf).stem)
    corrida = ''.join(m.groups()) if m else Path(netcdf).stem.removeprefix("pp_GFS_")
    return sorted(Path(destino).glob(f"gfs_pisco_{corrida}_*.tif"))


def preparar_si_nuevo(directorio):
    """Prepara la corrida más reciente solo si cambió el NetCDF o la plantilla."""
    base = Path(directorio)
    # 1. Buscar primero corrida GFS nativa (ej. pp_GFS_20261104.nc)
    fuentes = sorted(
        [f for f in base.glob("pp_GFS_*.nc") if f.stem.removeprefix("pp_GFS_").isdigit()],
        reverse=True
    )
    # 2. Si no existe corrida nativa 0.25, usar cubo PISCO GFS de la emisión
    if not fuentes:
        fuentes = sorted(base.glob("pp_GFS_grillaPISCO_emision_*.nc"), reverse=True)

    plantillas = sorted(base.glob("prob_grillaPISCO_*.tif"), reverse=True)
    if not fuentes or not plantillas:
        return []
    fuente, plantilla = fuentes[0], plantillas[0]
    contorno = base.parent / "data" / "departamentos.geojson"
    if not contorno.exists():
        raise FileNotFoundError(f"Falta el contorno nacional: {contorno}")
    existentes = salidas_de_corrida(fuente, base)
    if len(existentes) == 10 and all(
        ruta.stat().st_mtime_ns >= max(fuente.stat().st_mtime_ns, plantilla.stat().st_mtime_ns, contorno.stat().st_mtime_ns)
        and rasterio.open(ruta).tags().get("mask") == "departamentos.geojson:touched"
        for ruta in existentes
    ):
        return existentes
    generar(fuente, plantilla, contorno, base)
    return salidas_de_corrida(fuente, base)


def generar(netcdf, plantilla, contorno, destino):
    with rasterio.open(plantilla) as ref:
        if str(ref.crs) != "EPSG:4326":
            raise ValueError("La plantilla debe estar en EPSG:4326")
        perfil = ref.profile.copy()
        filas, columnas = np.indices((ref.height, ref.width))
        lon = ref.transform.c + (columnas + .5) * ref.transform.a
        lat = ref.transform.f + (filas + .5) * ref.transform.e
        pais = gpd.read_file(contorno).to_crs(ref.crs)
        mascara_peru = geometry_mask(pais.geometry, out_shape=(ref.height, ref.width), transform=ref.transform, invert=True, all_touched=True)
    with xr.open_dataset(netcdf) as ds:
        var_name = "gfspp" if "gfspp" in ds else ("pp" if "pp" in ds else None)
        if not var_name:
            raise ValueError("Falta variable de precipitación en NetCDF (gfspp o pp)")
        
        m = re.search(r'(\d{4})-?(\d{2})-?(\d{2})', Path(netcdf).stem)
        corrida = ''.join(m.groups()) if m else Path(netcdf).stem.removeprefix("pp_GFS_")
        perfil.update(dtype="float32", count=1, nodata=-9999., compress="deflate")

        # Comprobar si ya viene remuestreado a PISCO (210x174) o si es 0.25° nativo
        is_pisco_grid = ds[var_name].shape[-2:] == (ref.height, ref.width)

        for i, tiempo in enumerate(ds.time.values):
            fecha = str(tiempo.astype("datetime64[D]"))
            if is_pisco_grid:
                slice_data = ds[var_name].isel(time=i).values
                salida = np.where(mascara_peru & np.isfinite(slice_data), slice_data, -9999.).astype("float32")
                res_tag = "0.10 degrees (PISCO)"
            else:
                lon_coord = "lon" if "lon" in ds.coords else "longitude"
                lat_coord = "lat" if "lat" in ds.coords else "latitude"
                dentro = (lon >= float(ds[lon_coord].min()) - .125) & (lon <= float(ds[lon_coord].max()) + .125) & (lat >= float(ds[lat_coord].min()) - .125) & (lat <= float(ds[lat_coord].max()) + .125)
                valores = ds[var_name].isel(time=i).sel({lon_coord: xr.DataArray(lon, dims=("fila", "columna")), lat_coord: xr.DataArray(lat, dims=("fila", "columna"))}, method="nearest").values
                salida = np.where(dentro & mascara_peru & np.isfinite(valores), valores, -9999.).astype("float32")
                res_tag = "0.25 degrees"

            ruta = Path(destino) / f"gfs_pisco_{corrida}_{fecha}.tif"
            with tempfile.NamedTemporaryFile(dir=destino, suffix=".tif", delete=False) as temporal:
                ruta_temporal = Path(temporal.name)
            with rasterio.open(ruta_temporal, "w", **perfil) as dst:
                dst.write(salida, 1)
                dst.update_tags(source=Path(netcdf).name, source_resolution=res_tag, resampling="nearest", purpose="visualization only", units="mm/day", mask="departamentos.geojson:touched")
            os.replace(ruta_temporal, ruta)
            print(ruta)


if __name__ == "__main__":
    base = Path(__file__).resolve().parent / "Salidas"
    if not preparar_si_nuevo(base):
        raise SystemExit("Falta GFS o plantilla PISCO en Salidas/")
