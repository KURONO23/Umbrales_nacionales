import json
import pydeck as pdk
import pandas as pd

def obtener_color_probabilidad(prob):
    """
    Rampa de color estilo Google Flood Hub:
    - 0% a 20%: Transparente / Gris tenue
    - 20% a 40%: Amarillo
    - 40% a 70%: Naranja
    - >= 70%: Rojo Carmesí / Alerta Máxima
    """
    if prob < 0.20:
        return [200, 200, 200, 20] # Muy tenue
    elif prob < 0.40:
        return [255, 235, 59, 140] # Amarillo
    elif prob < 0.70:
        return [255, 152, 0, 190] # Naranja
    else:
        return [244, 67, 54, 230] # Rojo intenso

def obtener_color_evento_op(evento):
    """Color binario para el Umbral Operativo: 0=transparente, 1=Rojo neón."""
    if evento == 1:
        return [255, 23, 68, 220] # Alerta Sí
    return [150, 150, 150, 25]     # Normal

def preparar_features_geojson(gdf, modo="prob"):
    """
    Convierte un GeoDataFrame en un GeoJSON con colores RGBA inyectados para PyDeck.
    """
    gdf_copy = gdf.copy()
    
    if modo == "prob":
        gdf_copy["fill_color"] = gdf_copy["prob"].apply(obtener_color_probabilidad)
        gdf_copy["line_color"] = [[0, 0, 0, 40] for _ in range(len(gdf_copy))]
    else:
        gdf_copy["fill_color"] = gdf_copy["evento_op"].apply(obtener_color_evento_op)
        gdf_copy["line_color"] = [[0, 0, 0, 40] for _ in range(len(gdf_copy))]
        
    return json.loads(gdf_copy.to_json())

def preparar_features_puntos(gdf, modo="prob"):
    """
    Genera una lista de diccionarios para la capa de balizas/pines estilo Google Flood Hub.
    Solo incluye puntos con alerta (prob >= 20% o evento_op == 1) para alto rendimiento visual.
    """
    if gdf.empty:
        return []
        
    if modo == "prob":
        gdf_alerta = gdf[gdf["prob"] >= 0.20].copy()
    else:
        gdf_alerta = gdf[gdf["evento_op"] == 1].copy()
        
    if gdf_alerta.empty:
        return []
        
    puntos = []
    for _, row in gdf_alerta.iterrows():
        prob = row["prob"]
        evento = row["evento_op"]
        
        if modo == "prob":
            if prob >= 0.70:
                color_core = [244, 67, 54, 240]
                color_halo = [244, 67, 54, 80]
                radio_core = 4000
                radio_halo = 10000
            elif prob >= 0.40:
                color_core = [255, 152, 0, 230]
                color_halo = [255, 152, 0, 70]
                radio_core = 3500
                radio_halo = 8500
            else:
                color_core = [255, 235, 59, 210]
                color_halo = [255, 235, 59, 60]
                radio_core = 3000
                radio_halo = 7000
        else:
            color_core = [255, 23, 68, 240]
            color_halo = [255, 23, 68, 80]
            radio_core = 4000
            radio_halo = 10000
            
        puntos.append({
            "coordinates": [float(row["lon"]), float(row["lat"])],
            "lon": float(row["lon"]),
            "lat": float(row["lat"]),
            "id": int(row["id"]),
            "DISTRITO": str(row["DISTRITO"]),
            "PROVINCIA": str(row["PROVINCIA"]),
            "DEPARTAMENTO": str(row["DEPARTAMENTO"]),
            "prob_pct": float(row["prob_pct"]),
            "evento_op": int(row["evento_op"]),
            "pp": float(row["pp"]),
            "ant_log": float(row["ant_log"]),
            "color_core": color_core,
            "color_halo": color_halo,
            "radio_core": radio_core,
            "radio_halo": radio_halo
        })
    return puntos

def crear_mapa_pydeck(
    geojson_data,
    puntos_alerta=None,
    punto_foco=None,
    red_hidrica_data=None,
    departamentos_data=None,
    centro_lat=-9.19,
    centro_lon=-75.01,
    zoom=4.8,
    estilo_mapa="Oscuro",
    modo_3d=False
):
    """
    Genera el mapa interactivo WebGL en PyDeck con look & feel Google Flood Hub:
    - GeoJsonLayer para red hídrica ANA (ríos y quebradas brillantes).
    - GeoJsonLayer para límites departamentales (contorno geopolítico tenue).
    - GeoJsonLayer para polígonos de grilla (con soporte para elevación 3D).
    - ScatterplotLayer (Halos + Núcleos) para balizas de alerta visibles a escala nacional.
    - Anillo de enfoque neon para el distrito/zona seleccionada.
    """
    layers = []

    # 1. Capa de Límites Departamentales (Contorno muy tenue para georreferenciación)
    if departamentos_data:
        dept_layer = pdk.Layer(
            "GeoJsonLayer",
            departamentos_data,
            id="limites-departamentales",
            opacity=0.35,
            stroked=True,
            filled=False,
            get_line_color=[160, 175, 195, 80],  # Línea gris azulada muy suave
            get_line_width=1,
            line_width_min_pixels=0.7,
            pickable=False,
            auto_highlight=False
        )
        layers.append(dept_layer)

    # 2. Capa de Red Hídrica Nacional (Ríos y Quebradas ANA) - Estilo suave y tenue
    if red_hidrica_data:
        rios_layer = pdk.Layer(
            "GeoJsonLayer",
            red_hidrica_data,
            id="red-hidrica-ana",
            opacity=0.30,
            stroked=True,
            filled=False,
            get_line_color=[79, 195, 247, 90],  # Azul celeste muy sutil
            get_line_width=1,
            line_width_min_pixels=0.6,           # Trazo fino y suave
            pickable=False,
            auto_highlight=False
        )
        layers.append(rios_layer)

    # 2. Capa base de polígonos de grilla (con o sin extrusión 3D)
    grid_layer = pdk.Layer(
        "GeoJsonLayer",
        geojson_data,
        id="grilla-inundacion",
        opacity=0.75 if not modo_3d else 0.88,
        stroked=True,
        filled=True,
        extruded=modo_3d,
        wireframe=False if modo_3d else True,
        get_elevation="properties.prob * 48000" if modo_3d else 0,
        elevation_scale=1,
        get_fill_color="properties.fill_color",
        get_line_color="properties.line_color",
        get_line_width=1,
        line_width_min_pixels=0.5,
        pickable=True,
        auto_highlight=True,
        highlight_color=[255, 255, 255, 140]
    )
    layers.append(grid_layer)

    # 3. Capa de balizas / pines Google Flood Hub (si hay alertas)
    if puntos_alerta and len(puntos_alerta) > 0:
        # Halo exterior difuso
        halo_layer = pdk.Layer(
            "ScatterplotLayer",
            data=puntos_alerta,
            id="alerta-halo",
            get_position="coordinates",
            get_fill_color="color_halo",
            get_radius="radio_halo",
            radius_min_pixels=6,
            radius_max_pixels=28,
            pickable=False
        )
        # Núcleo interior brillante con borde
        core_layer = pdk.Layer(
            "ScatterplotLayer",
            data=puntos_alerta,
            id="alerta-core",
            get_position="coordinates",
            get_fill_color="color_core",
            get_line_color=[255, 255, 255, 220],
            line_width_min_pixels=1.2,
            stroked=True,
            get_radius="radio_core",
            radius_min_pixels=3.5,
            radius_max_pixels=14,
            pickable=True
        )
        layers.extend([halo_layer, core_layer])

    # 4. Anillo de enfoque / selección activa
    if punto_foco:
        foco_data = [{
            "coordinates": [float(punto_foco["lon"]), float(punto_foco["lat"])]
        }]
        target_layer = pdk.Layer(
            "ScatterplotLayer",
            data=foco_data,
            id="foco-seleccion",
            get_position="coordinates",
            get_fill_color=[0, 229, 255, 60],
            get_line_color=[0, 229, 255, 255],
            line_width_min_pixels=3,
            stroked=True,
            filled=True,
            radius_scale=1,
            get_radius=12000,
            radius_min_pixels=15,
            radius_max_pixels=45,
            pickable=False
        )
        layers.append(target_layer)

    pitch_val = 45 if modo_3d else (20 if zoom > 6 else 0)

    view_state = pdk.ViewState(
        latitude=centro_lat,
        longitude=centro_lon,
        zoom=zoom,
        min_zoom=3.5,
        max_zoom=13,
        pitch=pitch_val,
        bearing=0
    )

    tooltip = {
        "html": """
        <div style="font-family: sans-serif; font-size: 13px; color: #fff; background-color: rgba(22, 27, 34, 0.95); backdrop-filter: blur(8px); padding: 12px 16px; border-radius: 8px; box-shadow: 0 6px 20px rgba(0,0,0,0.7); border: 1px solid #30363d; min-width: 200px;">
            <div style="font-size: 14px; font-weight: 700; margin-bottom: 2px; color: #58a6ff;">
                📍 {DISTRITO}
            </div>
            <div style="font-size: 11px; color: #8b949e; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">
                {PROVINCIA}, {DEPARTAMENTO}
            </div>
            <div style="margin-bottom: 4px;"><b>Probabilidad Inundación:</b> <span style="color: #f2cc60; font-size: 14px; font-weight: 700;">{prob_pct}%</span></div>
            <div style="margin-bottom: 3px;"><b>Umbral Operativo:</b> {evento_op}</div>
            <div style="margin-bottom: 3px;"><b>Lluvia Hoy (pp):</b> {pp} mm</div>
            <div style="margin-bottom: 3px;"><b>Antecedente (15d):</b> {ant_log} mm</div>
            <div style="color: #6e7681; font-size: 10px; margin-top: 6px; border-top: 1px solid #30363d; padding-top: 4px;">
                Celda #{id} · Coord: {lat}, {lon}
            </div>
        </div>
        """,
        "style": {
            "backgroundColor": "transparent",
            "border": "none"
        }
    }

    # Selección de mapa base
    map_styles = {
        "Oscuro": "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
        "Topográfico / Terreno": "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",
        "Claro": "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
    }
    estilo_url = map_styles.get(estilo_mapa, map_styles["Oscuro"])

    mapa = pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_style=estilo_url,
        tooltip=tooltip
    )
    return mapa
