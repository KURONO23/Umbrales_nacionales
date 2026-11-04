r"""
Pipeline de Sincronización y Automatización Diaria ARES & GFS
=============================================================
Ejecuta la actualización diaria del pronóstico a 10 días:
1. Detecta la corrida más reciente en \\DHI-FVJ2HGR\SalidasGFS (8:00 - 8:15 AM).
2. Limpia los archivos del horizonte anterior para mantener el repositorio limpio.
3. Copia los archivos consolidados y de emisión a GITHUB_LOCAL/Salidas.
4. Genera los 10 GPKG vectoriales, 10 CSVs de resumen y métricas de diagnóstico.
5. Exporta todos los GeoTIFFs diarios (nivel_alerta, prob, evento_op, evento_log, pp_puntual, ant_log).
6. Preprocesa las 10 capas raster de precipitación GFS sobre grilla PISCO.
7. Sincroniza y publica los cambios en GitHub (origin/main).
8. Replica las salidas en la carpeta raíz para compatibilidad con accesos directos.
"""

import os
import sys
import time
import shutil
import logging
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# Rutas base
BASE_DIR = Path(__file__).resolve().parent
SALIDAS_DIR = BASE_DIR / "Salidas"
ROOT_SALIDAS_DIR = BASE_DIR.parent / "Salidas"
RED_DIR = Path(r"\\DHI-FVJ2HGR\SalidasGFS")
LOGS_DIR = BASE_DIR / "logs"

LOGS_DIR.mkdir(parents=True, exist_ok=True)
SALIDAS_DIR.mkdir(parents=True, exist_ok=True)


def configurar_logger():
    fecha_hoy = datetime.now().strftime("%Y%m%d")
    archivo_log = LOGS_DIR / f"cron_{fecha_hoy}.log"
    
    logger = logging.getLogger("ARES_CRON")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    
    # Formato con timestamp
    formato = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    
    # Consola
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formato)
    logger.addHandler(ch)
    
    # Archivo
    fh = logging.FileHandler(archivo_log, encoding="utf-8")
    fh.setFormatter(formato)
    logger.addHandler(fh)
    
    return logger, archivo_log


def esperar_acceso_red(logger, max_intentos=10, espera_seg=15):
    """Verifica acceso a la carpeta de red con reintentos si aún no está montada."""
    logger.info(f"Verificando acceso a recurso de red: {RED_DIR}")
    for intento in range(1, max_intentos + 1):
        if RED_DIR.exists():
            logger.info(f"Conexión exitosa a {RED_DIR} (intento {intento}/{max_intentos})")
            return True
        logger.warning(f"Intento {intento}/{max_intentos}: no se pudo acceder a {RED_DIR}. Reintentando en {espera_seg}s...")
        time.sleep(espera_seg)
    return False


def detectar_emision_red(logger):
    """Encuentra la corrida más reciente en la carpeta de red."""
    candidatos = sorted(RED_DIR.glob("grillaPISCO_pronostico_emision_*.gpkg"), reverse=True)
    if not candidatos:
        logger.error("No se encontró ningún archivo 'grillaPISCO_pronostico_emision_*.gpkg' en la red.")
        return None, None
    
    archivo_base = candidatos[0]
    nombre = archivo_base.stem
    # Extraer fecha YYYY-MM-DD
    fecha_str = nombre.removeprefix("grillaPISCO_pronostico_emision_")
    logger.info(f"Última corrida detectada en red: {fecha_str} ({archivo_base.name})")
    
    # Comprobar si el archivo está siendo escrito aún
    mtime = archivo_base.stat().st_mtime
    seg_transcurridos = time.time() - mtime
    if seg_transcurridos < 30:
        logger.info(f"El archivo fue modificado hace {seg_transcurridos:.1f}s. Esperando 30s a que termine de escribirse...")
        time.sleep(30)
        
    return fecha_str, archivo_base


def limpiar_horizonte_previo(logger, fecha_emision_nueva):
    """Elimina las salidas diarias del horizonte anterior para evitar mezclas."""
    logger.info("Limpiando salidas del horizonte previo en Salidas/...")
    patrones_limpieza = [
        "grillaPISCO_prob_*.gpkg",
        "resumen_prob_grillaPISCO_*.csv",
        "diagnostico_operativo_*.csv",
        "nivel_alerta_grillaPISCO_*.tif",
        "prob_grillaPISCO_*.tif",
        "evento_op_grillaPISCO_*.tif",
        "evento_log_grillaPISCO_*.tif",
        "pp_puntual_grillaPISCO_*.tif",
        "ant_log_grillaPISCO_*.tif",
        "gfs_pisco_*.tif"
    ]
    eliminados = 0
    for pat in patrones_limpieza:
        for f in SALIDAS_DIR.glob(pat):
            try:
                f.unlink()
                eliminados += 1
            except Exception as e:
                logger.warning(f"No se pudo eliminar {f.name}: {e}")
    
    # Limpiar también archivos de emisión previa diferentes a la nueva
    for f in SALIDAS_DIR.glob("*_emision_*"):
        if fecha_emision_nueva not in f.name:
            try:
                f.unlink()
                eliminados += 1
            except Exception as e:
                logger.warning(f"No se pudo eliminar archivo de emisión anterior {f.name}: {e}")
                
    logger.info(f"Limpieza completada: {eliminados} archivos antiguos eliminados.")


def ejecutar_procesamiento(logger):
    """Ejecuta actualizar_pronostico.py y preprocesar_gfs.py usando el entorno virtual."""
    python_exe = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        python_exe = Path(sys.executable)
        
    logger.info(f"Ejecutando actualizar_pronostico.py con {python_exe}...")
    t0 = time.time()
    res1 = subprocess.run(
        [str(python_exe), str(BASE_DIR / "actualizar_pronostico.py")],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    if res1.returncode != 0:
        logger.error(f"Error al ejecutar actualizar_pronostico.py:\n{res1.stderr}")
        return False
    logger.info(f"actualizar_pronostico.py finalizado en {time.time() - t0:.1f}s")

    logger.info("Ejecutando preprocesar_gfs.py...")
    t0_gfs = time.time()
    res2 = subprocess.run(
        [str(python_exe), str(BASE_DIR / "preprocesar_gfs.py")],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    if res2.returncode != 0:
        logger.warning(f"Aviso en preprocesar_gfs.py:\n{res2.stderr}")
    else:
        logger.info(f"preprocesar_gfs.py finalizado en {time.time() - t0_gfs:.1f}s")
        
    return True


def sincronizar_a_raiz(logger):
    """Copia las salidas procesadas a la carpeta Salidas/ de la raíz para compatibilidad."""
    try:
        ROOT_SALIDAS_DIR.mkdir(parents=True, exist_ok=True)
        # Limpiar salidas previas en raíz
        for f in ROOT_SALIDAS_DIR.glob("*"):
            if f.is_file():
                try:
                    f.unlink()
                except Exception:
                    pass
        # Copiar nuevas
        copiados = 0
        for f in SALIDAS_DIR.glob("*"):
            if f.is_file():
                shutil.copy2(f, ROOT_SALIDAS_DIR / f.name)
                copiados += 1
        logger.info(f"Copia espejo a carpeta raíz Salidas/ exitosa ({copiados} archivos sincronizados).")
    except Exception as exc:
        logger.warning(f"Aviso al replicar en carpeta raíz: {exc}")


def sincronizar_git(logger, fecha_emision):
    """Realiza git add, commit y push hacia origin/main."""
    logger.info("Iniciando sincronización con repositorio GitHub...")
    
    # 1. git pull previo
    logger.info("Ejecutando git pull...")
    subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=str(BASE_DIR), capture_output=True)

    # 2. git add Salidas
    logger.info("Añadiendo cambios en Salidas/ (incluyendo eliminaciones de corridas anteriores)...")
    res_add = subprocess.run(["git", "add", "-A", "Salidas"], cwd=str(BASE_DIR), capture_output=True, text=True)
    if res_add.returncode != 0:
        logger.error(f"Fallo en git add: {res_add.stderr}")
        return False
        
    # 3. Comprobar si hay cambios para commitear
    res_diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(BASE_DIR))
    if res_diff.returncode == 0:
        logger.info("No hay cambios nuevos pendientes en Salidas/. GitHub ya está al día.")
        return True
        
    # 4. Commit
    mensaje = f"Auto: Actualizacion pronostico ARES y GFS {fecha_emision} ({datetime.now().strftime('%H:%M')})"
    logger.info(f"Creando commit: '{mensaje}'...")
    res_com = subprocess.run(["git", "commit", "-m", mensaje], cwd=str(BASE_DIR), capture_output=True, text=True)
    if res_com.returncode != 0:
        logger.error(f"Fallo en git commit: {res_com.stderr}")
        return False
        
    # 5. Push
    logger.info("Subiendo cambios a GitHub (git push origin main)...")
    t0_push = time.time()
    res_push = subprocess.run(["git", "push", "origin", "main"], cwd=str(BASE_DIR), capture_output=True, text=True)
    if res_push.returncode != 0:
        logger.error(f"Fallo en git push:\n{res_push.stderr}")
        return False
        
    logger.info(f"git push exitoso en {time.time() - t0_push:.1f}s.")
    return True


def ejecutar_cron_completo(force=False):
    logger, archivo_log = configurar_logger()
    logger.info("=" * 70)
    logger.info("INICIO DE TAREA AUTOMATIZADA: ACTUALIZACIÓN DIARIA ARES & GFS")
    logger.info(f"Hora de inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)
    
    t_inicio_total = time.time()
    
    # 1. Comprobar red
    if not esperar_acceso_red(logger):
        logger.error("No se pudo conectar a la carpeta de red tras varios intentos. Finalizando con error.")
        return 1
        
    # 2. Detectar última emisión
    fecha_emision, archivo_base = detectar_emision_red(logger)
    if not fecha_emision:
        logger.error("No se detectó ninguna corrida válida. Abortando.")
        return 1
        
    # 3. Verificar si ya fue procesada
    marcador_listo = SALIDAS_DIR / f"grillaPISCO_pronostico_emision_{fecha_emision}.gpkg"
    archivos_gpkg_dias = list(SALIDAS_DIR.glob(f"grillaPISCO_prob_*.gpkg"))
    
    if not force and marcador_listo.exists() and len(archivos_gpkg_dias) == 10:
        logger.info(f"La emisión {fecha_emision} ya está completamente procesada ({len(archivos_gpkg_dias)} días listos).")
        logger.info("Verificando si GitHub requiere sincronización...")
        sincronizar_git(logger, fecha_emision)
        logger.info("Tarea finalizada sin requerir reprocesamiento.")
        return 0
        
    logger.info(f"Procesando nueva emisión del día: {fecha_emision}")
    
    # 4. Limpiar horizonte anterior
    limpiar_horizonte_previo(logger, fecha_emision)
    
    # 5. Ejecutar sincronización de salidas y extracción de rasters/vectoriales
    if not ejecutar_procesamiento(logger):
        logger.error("Error durante el procesamiento de datos.")
        return 1
        
    # 6. Replicar en carpeta raíz
    sincronizar_a_raiz(logger)
    
    # 7. Sincronizar y publicar en GitHub
    if not sincronizar_git(logger, fecha_emision):
        logger.error("Error durante la publicación a GitHub.")
        return 1
        
    duracion = time.time() - t_inicio_total
    logger.info("=" * 70)
    logger.info(f"ACTUALIZACIÓN DIARIA COMPLETADA CON ÉXITO EN {duracion:.1f} SEGUNDOS")
    logger.info(f"Log detallado guardado en: {archivo_log}")
    logger.info("=" * 70)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cron diario de actualización ARES / GFS")
    parser.add_argument("--force", action="store_true", help="Fuerza reprocesamiento incluso si la fecha ya existe")
    args = parser.parse_args()
    
    codigo_salida = ejecutar_cron_completo(force=args.force)
    sys.exit(codigo_salida)
