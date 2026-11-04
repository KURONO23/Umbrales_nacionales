"""Prepara los pronósticos diarios GFS sobre la grilla PISCO por vecino más cercano."""
from pathlib import Path
import os
import tempfile
import numpy as np
import rasterio
from rasterio.features import geometry_mask
import xarray as xr
import geopandas as gpd


def salidas_de_corrida(netcdf, destino):
    corrida = Path(netcdf).stem.removeprefix("pp_GFS_")
    return sorted(Path(destino).glob(f"gfs_pisco_{corrida}_*.tif"))


def preparar_si_nuevo(directorio):
    """Prepara la corrida más reciente solo si cambió el NetCDF o la plantilla."""
    base = Path(directorio)
    # Filtrar solo archivos de la corrida GFS con fecha numérica (ej. pp_GFS_20261104.nc), ignorando otros cubos
    fuentes = sorted(
        [f for f in base.glob("pp_GFS_*.nc") if f.stem.removeprefix("pp_GFS_").isdigit()],
        reverse=True
    )
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
        dentro = (lon >= float(ds.lon.min()) - .125) & (lon <= float(ds.lon.max()) + .125) & (lat >= float(ds.lat.min()) - .125) & (lat <= float(ds.lat.max()) + .125)
        perfil.update(dtype="float32", count=1, nodata=-9999., compress="deflate")
        for i, tiempo in enumerate(ds.time.values):
            fecha = str(tiempo.astype("datetime64[D]"))
            valores = ds[var_name].isel(time=i).sel(lon=xr.DataArray(lon, dims=("fila", "columna")), lat=xr.DataArray(lat, dims=("fila", "columna")), method="nearest").values
            salida = np.where(dentro & mascara_peru & np.isfinite(valores), valores, -9999.).astype("float32")
            corrida = Path(netcdf).stem.removeprefix("pp_GFS_")
            ruta = Path(destino) / f"gfs_pisco_{corrida}_{fecha}.tif"
            with tempfile.NamedTemporaryFile(dir=destino, suffix=".tif", delete=False) as temporal:
                ruta_temporal = Path(temporal.name)
            with rasterio.open(ruta_temporal, "w", **perfil) as dst:
                dst.write(salida, 1)
                dst.update_tags(source=Path(netcdf).name, source_resolution="0.25 degrees", resampling="nearest", purpose="visualization only", units="mm/day", mask="departamentos.geojson:touched")
            os.replace(ruta_temporal, ruta)
            print(ruta)


if __name__ == "__main__":
    base = Path(__file__).resolve().parent / "Salidas"
    if not preparar_si_nuevo(base):
        raise SystemExit("Falta GFS o plantilla PISCO en Salidas/")
