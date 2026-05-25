import streamlit as st
import requests
import pandas as pd
import numpy as np
import folium
import streamlit.components.v1 as components
import re

from folium.plugins import MarkerCluster
from bs4 import BeautifulSoup
from io import BytesIO
from datetime import datetime
from dateutil.relativedelta import relativedelta
from math import radians, sin, cos, sqrt, atan2

# =========================================================
# CONFIGURACIÓN DE STREAMLIT
# =========================================================
st.set_page_config(
    page_title="SIGOF GIS",
    layout="wide",
    initial_sidebar_state="expanded"
)

LOGIN_URL = "http://sigof.distriluz.com.pe/plus/usuario/login"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": LOGIN_URL,
}

st.title("🛰️ SIGOF GIS INTELIGENTE")

# Inicialización segura del estado de la sesión
if "logueado" not in st.session_state:
    st.session_state["logueado"] = False
if "session" not in st.session_state:
    st.session_state["session"] = None

# =========================================================
# FUNCIONES MATEMÁTICAS
# =========================================================
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # Radio de la Tierra en metros
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1))
        * cos(radians(lat2))
        * sin(dlon / 2) ** 2
    )
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))

# =========================================================
# MÓDULO DE AUTENTICACIÓN (LOGIN)
# =========================================================
if not st.session_state["logueado"]:
    st.subheader("🔑 Autenticación de Sistema")
    col1, col2 = st.columns(2)
    with col1:
        usuario = st.text_input("Usuario SIGOF")
    with col2:
        password = st.text_input("Contraseña", type="password")

    if st.button("INICIAR SESIÓN", use_container_width=True):
        try:
            session = requests.Session()
            login_page = session.get(LOGIN_URL, headers=HEADERS, timeout=60)
            soup = BeautifulSoup(login_page.text, "html.parser")

            csrf = soup.find("input", {"name": "_csrf_token"})
            credentials = {
                "data[Usuario][usuario]": usuario,
                "data[Usuario][pass]": password
            }

            if csrf:
                credentials["_csrf_token"] = csrf["value"]

            r = session.post(LOGIN_URL, data=credentials, headers=HEADERS, timeout=60)

            if "Salir" not in r.text:
                st.error("❌ Usuario o contraseña incorrectos")
                st.stop()

            st.success("✅ Sesión iniciada correctamente")
            st.session_state["session"] = session
            st.session_state["logueado"] = True
            st.rerun()

        except Exception as e:
            st.error(f"Error de conexión con el servidor: {str(e)}")
else:
    st.sidebar.success("👤 Conectado al sistema SIGOF")
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state["logueado"] = False
        st.session_state["session"] = None
        st.rerun()

# =========================================================
# PANEL PRINCIPAL (SÓLO ACCESIBLE SI ESTÁ LOGUEADO)
# =========================================================
if st.session_state.get("logueado"):
    st.subheader("⚙️ Configuración de Procesamiento GIS")

    col_r, col_m = st.columns([1, 2])
    with col_r:
        ruta = st.text_input("Ruta de Inspección", placeholder="Ejemplo: 46516")
    with col_m:
        tipo_mapa = st.radio("Tipo de consulta base", ["TOTAL RUTA", "SOLO PENDIENTES"], horizontal=True)

    # Configuración dinámica de períodos históricos basados en el mes actual
    actual = datetime.now()
    mes_1 = (actual - relativedelta(months=1)).strftime("%Y%m")
    mes_2 = (actual - relativedelta(months=2)).strftime("%Y%m")

    default_periodos = list(dict.fromkeys(["202409", "202410", "202508", "202509", mes_1, mes_2]))
    periodos = []

    anio = actual.year
    mes = actual.month

    # Retroceder en el tiempo construyendo los períodos hasta septiembre de 2024
    while anio > 2024 or (anio == 2024 and mes >= 9):
        periodos.append(f"{anio}{mes:02d}")
        mes -= 1
        if mes == 0:
            mes = 12
            anio -= 1

    periodos_seleccionados = st.multiselect("Seleccionar períodos históricos para cruce GPS", periodos, default=default_periodos)

    # =====================================================
    # BOTÓN DE PROCESAMIENTO CORE
    # =====================================================
    if st.button("🛰️ PROCESAR ANÁLISIS GIS", use_container_width=True):
        try:
            # Limpiar caché de estados previos
            if "df_final" in st.session_state:
                del st.session_state["df_final"]
                del st.session_state["excel_bytes"]

            session = st.session_state["session"]
            hoy = datetime.now().strftime("%Y-%m-%d")

            # 1. Definición de URL Base de descarga según el criterio seleccionado
            if tipo_mapa == "SOLO PENDIENTES":
                url_actual = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{ruta}/0/0/0/0/LSC/0/9/0"
            else:
                url_actual = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{ruta}/0/0/0/0/0/0/9/0"

            # 2. Descarga del archivo Excel base actual
            r = session.get(url_actual, headers=HEADERS, timeout=180)
            if r.status_code != 200 or r.content[:2] != b"PK":
                st.error("❌ Error al descargar datos base del servidor Distriluz. Verifica los parámetros.")
                st.stop()

            df_actual = pd.read_excel(BytesIO(r.content))

            # --- PARADA DE SEGURIDAD OPTIMIZADA: DETENER SI ES 0 ---
            if len(df_actual) == 0:
                st.warning(f"⚠️ La ruta {ruta} tiene 0 registros en '{tipo_mapa}'. No se consumirá histórico ni se cargará mapa.")
                st.stop()
            # -------------------------------------------------------

            st.success(f"✅ Datos base obtenidos con éxito. Registros actuales a evaluar: {len(df_actual):,}")

            # Identificación inteligente de la columna 'Suministro'
            col_suministro = next((c for c in df_actual.columns if "suministro" in str(c).lower()), None)
            if not col_suministro:
                st.error("❌ No se encontró una columna que contenga el nombre 'suministro' en el archivo maestro.")
                st.stop()

            suministros_actuales = df_actual[col_suministro].astype(str).unique()

            # 3. Ciclo de extracción y filtrado en caliente de históricos
            dfs_hist = []
            total = len(periodos_seleccionados)
            progress = st.progress(0)
            estado_descarga = st.empty()

            for i, periodo in enumerate(periodos_seleccionados):
                estado_descarga.text(f"Descargando e interpolando período histórico: {i+1}/{total} ({periodo})")
                url_hist = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{ruta}/0/0/0/0/0/0/9/{periodo}"
                
                rh = session.get(url_hist, headers=HEADERS, timeout=180)
                if rh.status_code == 200 and rh.content[:2] == b"PK":
                    df_temp = pd.read_excel(BytesIO(rh.content))
                    # Filtrar de inmediato para mantener en memoria sólo lo que cruza con nuestra muestra base actual
                    df_temp = df_temp[df_temp[col_suministro].astype(str).isin(suministros_actuales)].copy()
                    df_temp["periodo_historico"] = periodo
                    dfs_hist.append(df_temp)

                progress.progress((i + 1) / total)

            estado_descarga.empty()
            progress.empty()

            if not dfs_hist:
                st.error("❌ Se descargaron históricos pero ningún suministro base coincide con el pasado histórico.")
                st.stop()

            # Consolidar registros históricos filtrados
            fusionado = pd.concat(dfs_hist, ignore_index=True)

            # Identificación de columnas GPS
            lat_col = next((c for c in fusionado.columns if "lat" in str(c).lower()), None)
            lon_col = next((c for c in fusionado.columns if "lon" in str(c).lower()), None)

            if not lat_col or not lon_col:
                st.error("❌ No se ubicaron las columnas de Latitud/Longitud en la estructura de datos descargada.")
                st.stop()

            # Sanitización y limpieza estricta de coordenadas vacías o en cero (0.0)
            fusionado[lat_col] = pd.to_numeric(fusionado[lat_col], errors="coerce")
            fusionado[lon_col] = pd.to_numeric(fusionado[lon_col], errors="coerce")
            fusionado = fusionado[(fusionado[lat_col] != 0) & (fusionado[lon_col] != 0)].dropna(subset=[lat_col, lon_col])

            if len(fusionado) == 0:
                st.error("❌ Los archivos históricos existen pero no cuentan con ninguna coordenada GPS válida.")
                st.stop()

            # Cálculo del baricentro de la nube de puntos general
            centro_lat = fusionado[lat_col].median()
            centro_lon = fusionado[lon_col].median()

            # 4. Motor Algorítmico GIS para la validación espacial de puntos por Suministro
            resultados = []
            grupos = fusionado.groupby(col_suministro)
            total_grupos = len(grupos)
            progress_gis = st.progress(0)

            for i, (suministro, grupo) in enumerate(grupos):
                puntos = grupo[[lat_col, lon_col]].values
                meses = len(grupo["periodo_historico"].unique())

                if len(puntos) == 1:
                    lat_final = puntos[0][0]
                    lon_final = puntos[0][1]
                    dispersion = 0.0
                    estado = "UNICO"
                else:
                    n = len(puntos)
                    matriz = np.zeros((n, n))
                    for x in range(n):
                        for y in range(x + 1, n):
                            d = haversine(puntos[x][0], puntos[x][1], puntos[y][0], puntos[y][1])
                            matriz[x, y] = d
                            matriz[y, x] = d

                    dispersion = matriz.max()

                    if dispersion > 500:
                        # Si supera el umbral de dispersión se extrae el punto más cercano a la mediana general (Evita rebotes a bases operativas lejanas)
                        distancias = [haversine(pt[0], pt[1], centro_lat, centro_lon) for pt in puntos]
                        idx = int(np.argmin(distancias))
                        estado = "REBOTADO"
                    else:
                        # Selecciona el punto con menor distancia acumulada respecto a su propio grupo histórico
                        suma = matriz.sum(axis=1)
                        idx = int(np.argmin(suma))
                        estado = "VALIDADO"

                    lat_final = puntos[idx][0]
                    lon_final = puntos[idx][1]

                resultados.append({
                    col_suministro: suministro,
                    "latitud_validada": lat_final,
                    "longitud_validada": lon_final,
                    "estado_gps": estado,
                    "dispersion_m": round(dispersion, 2),
                    "meses_historicos": meses,
                    "google_maps": f"https://www.google.com/maps/?q={lat_final},{lon_final}"
                })
                progress_gis.progress((i + 1) / total_grupos)

            progress_gis.empty()

            # Combinar la información espacial recalculada con el dataframe original
            df_gps = pd.DataFrame(resultados)
            df_final = df_actual.merge(df_gps, on=col_suministro, how="left")

            # 5. Guardado persistente en memoria para evitar colisiones I/O de disco local
            salida = f"GIS_{ruta}.xlsx"
            output_excel = BytesIO()
            with pd.ExcelWriter(output_excel, engine="xlsxwriter") as writer:
                df_final.to_excel(writer, index=False, sheet_name="GIS")
            excel_bytes = output_excel.getvalue()

            st.success("✅ Procesamiento espacial completado con éxito.")

            # Botón de Descarga Seguro
            st.download_button(
                "📥 DESCARGAR EXCEL DE ENRUTAMIENTO FINAL",
                excel_bytes,
                file_name=salida,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # =================================================
            # MAPA AVANZADO INTEGRADO CON PINES Y TEXTO INFERIOR
            # =================================================
            st.subheader("🗺️ MAPA CORREGIDO DE GEOLOCALIZACIÓN")
            df_mapa = df_final.dropna(subset=["latitud_validada", "longitud_validada"])

            if len(df_mapa) > 0:
                mapa = folium.Map(location=[centro_lat, centro_lon], zoom_start=15, tiles=None)

                # Definición de capas base (Estilos de visualización intercambiables)
                folium.TileLayer("OpenStreetMap", name="Mapa Normal").add_to(mapa)
                folium.TileLayer(
                    tiles="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
                    attr="OpenTopoMap",
                    name="Mapa Topográfico"
                ).add_to(mapa)
                folium.TileLayer(
                    tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                    attr="Google",
                    name="Vista Satélite",
                    overlay=False,
                    control=True
                ).add_to(mapa)

                # Configuración de Clústeres para mejorar rendimiento visual
                cluster = MarkerCluster(
                    name="Suministros Distribuidos",
                    overlay=True,
                    control=False,
                    disableClusteringAtZoom=18
                ).add_to(mapa)

                for _, row in df_mapa.iterrows():
                    # Definición de paleta de color por estado analizado
                    color = "green"
                    if row["estado_gps"] == "REBOTADO":
                        color = "red"
                    elif row["estado_gps"] == "UNICO":
                        color = "blue"

                    sum_str = str(row[col_suministro])
                    est_str = str(row["estado_gps"])
                    disp_str = str(row["dispersion_m"])
                    g_maps_url = str(row["google_maps"])

                    popup_html = (
                        f"<b>Suministro:</b> {sum_str}<br>"
                        f"<b>Estado de Validación:</b> {est_str}<br>"
                        f"<b>Máxima Dispersión:</b> {disp_str} metros<br>"
                        f"<a href='{g_maps_url}' target='_blank'>🌍 Abrir en Google Maps</a>"
                    )

                    # 1. GENERACIÓN DEL MARCADOR PIN DE LOCALIZACIÓN
                    folium.Marker(
                        location=[row["latitud_validada"], row["longitud_validada"]],
                        popup=folium.Popup(popup_html, max_width=300),
                        tooltip=f"Suministro: {sum_str}",
                        icon=folium.Icon(
                            color=color, 
                            icon="map-marker",  # Ícono clásico de marcador de mapa
                            prefix="fa"         # Biblioteca FontAwesome
                        )
                    ).add_to(cluster)

                    # 2. GENERACIÓN DEL TEXTO SITUADO EXACTAMENTE ABAJO DEL PIN
                    # icon_anchor=(75, -12) centra horizontalmente el texto y lo mueve hacia abajo
                    folium.Marker(
                        location=[row["latitud_validada"], row["longitud_validada"]],
                        icon=folium.DivIcon(
                            icon_size=(150, 36),
                            icon_anchor=(75, -12),
                            html=f"""
                            <div style="
                                font-size: 9px;
                                color: black;
                                font-weight: bold;
                                background-color: rgba(255, 255, 255, 0.85);
                                padding: 1px 4px;
                                border-radius: 3px;
                                border: 1px solid #555555;
                                text-align: center;
                                width: fit-content;
                                margin: 0 auto;
                                box-shadow: 1px 1px 3px rgba(0,0,0,0.3);
                            ">
                                {sum_str}
                            </div>
                            """
                        )
                    ).add_to(cluster)

                # Agregar controles de mapas interactivos al lienzo
                folium.LayerControl().add_to(mapa)
                mapa_html = mapa._repr_html_()

                # Renderizar HTML mediante el componente nativo de Streamlit
                components.html(mapa_html, height=800, scrolling=True)
            else:
                st.warning("⚠️ El proceso concluyó pero los registros base carecen de coordenadas mapeables.")

        except Exception as e:
            st.error(f"Se capturó un fallo crítico en ejecución: {str(e)}")