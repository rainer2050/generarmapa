import streamlit as st
import requests
import pandas as pd
import numpy as np
import folium
import re

from streamlit_folium import st_folium
from bs4 import BeautifulSoup
from io import BytesIO
from datetime import datetime
from dateutil.relativedelta import relativedelta
from math import radians, sin, cos, sqrt, atan2

# =========================================================
# CONFIG STREAMLIT
# =========================================================
st.set_page_config(
    page_title="SIGOF GIS",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.title("🛰️ SIGOF GIS INTELIGENTE")

# Inicializar estados de sesión si no existen
if "logueado" not in st.session_state:
    st.session_state["logueado"] = False
if "session" not in st.session_state:
    st.session_state["session"] = None

# =========================================================
# CONFIG ENVIROMENT & HEADERS
# =========================================================
LOGIN_URL = "http://sigof.distriluz.com.pe/plus/usuario/login"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": LOGIN_URL,
}

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
# LOGIN DE USUARIO
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
            login_page = session.get(LOGIN_URL, headers=HEADERS, timeout=30)
            soup = BeautifulSoup(login_page.text, "html.parser")
            
            csrf = soup.find("input", {"name": "_csrf_token"})
            credentials = {
                "data[Usuario][usuario]": usuario,
                "data[Usuario][pass]": password
            }
            if csrf:
                credentials["_csrf_token"] = csrf["value"]

            r = session.post(LOGIN_URL, data=credentials, headers=HEADERS, timeout=30)

            if "Salir" not in r.text:
                st.error("❌ Usuario o contraseña incorrectos")
                st.stop()

            match = re.search(r"var DEFECTO_IDUUNN\s*=\s*'(\d+)';", r.text)
            defecto_iduunn = match.group(1) if match else "0"

            st.session_state["session"] = session
            st.session_state["logueado"] = True
            st.session_state["defecto_iduunn"] = defecto_iduunn
            st.rerun()

        except Exception as e:
            st.error(f"Error de conexión: {str(e)}")
else:
    st.sidebar.success(f"👤 Conectado - Unidad {st.session_state.get('defecto_iduunn')}")
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state["logueado"] = False
        st.session_state["session"] = None
        st.rerun()

# =========================================================
# APLICACIÓN PRINCIPAL (PROCESAMIENTO GIS)
# =========================================================
if st.session_state["logueado"]:
    st.subheader("⚙️ CONFIGURACIÓN DE PARÁMETROS")

    col_r, col_m = st.columns([1, 2])
    with col_r:
        ruta = st.text_input("Ingrese número de ruta", placeholder="Ejemplo: 46516")
    with col_m:
        tipo_mapa = st.radio("Filtro de mapa:", ["SOLO PENDIENTES", "TODA LA RUTA"], horizontal=True)

    # Cálculo dinámico de periodos históricos disponibles
    actual = datetime.now()
    mes_1 = (actual - relativedelta(months=1)).strftime("%Y%m")
    mes_2 = (actual - relativedelta(months=2)).strftime("%Y%m")
    default_periodos = list(dict.fromkeys(["202409", "202410", "202508", "202509", mes_1, mes_2]))

    periodos = []
    anio, mes = actual.year, actual.month
    while anio > 2024 or (anio == 2024 and mes >= 9):
        periodos.append(f"{anio}{mes:02d}")
        mes -= 1
        if mes == 0:
            mes = 12
            anio -= 1

    periodos_seleccionados = st.multiselect("Seleccione Períodos Históricos a evaluar:", periodos, default=default_periodos)

    if st.button("🛰️ PROCESAR ALGORITMO GIS", use_container_width=True):
        try:
            session = st.session_state["session"]
            hoy = datetime.now().strftime("%Y-%m-%d")

            # Construcción de URL Base dinámica
            suffix = "LSC/0/9/0" if tipo_mapa == "SOLO PENDIENTES" else "0/0/9/0"
            url_base = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{ruta}/0/0/0/0/{suffix}"

            with st.spinner("Descargando data maestra base..."):
                r = session.get(url_base, headers=HEADERS, timeout=180)
                if r.status_code != 200 or r.content[:2] != b"PK":
                    st.error("❌ El servidor SIGOF no retornó un archivo Excel válido para la ruta especificada.")
                    st.stop()
                
                df_base = pd.read_excel(BytesIO(r.content))

            # Identificación automática de columna Suministro
            col_suministro = next((c for c in df_base.columns if "suministro" in str(c).lower()), None)
            if not col_suministro:
                st.error("❌ No se encontró la columna de suministros obligatoria en el reporte.")
                st.stop()

            suministros = df_base[col_suministro].astype(str).unique()
            dfs_hist = []

            # Loop de descarga por periodos históricos con barra de progreso
            total = len(periodos_seleccionados)
            progress = st.progress(0)
            estado = st.empty()

            for i, periodo in enumerate(periodos_seleccionados):
                estado.text(f"📥 Descargando e indexando historial técnico: {i+1}/{total} (Periodo {periodo})")
                url_hist = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{ruta}/0/0/0/0/0/0/9/{periodo}"
                
                rh = session.get(url_hist, headers=HEADERS, timeout=180)
                if rh.status_code == 200 and rh.content[:2] == b"PK":
                    df_temp = pd.read_excel(BytesIO(rh.content))
                    df_temp = df_temp[df_temp[col_suministro].astype(str).isin(suministros)].copy()
                    df_temp["periodo_historico"] = periodo
                    dfs_hist.append(df_temp)
                
                progress.progress((i + 1) / total)

            estado.empty()
            progress.empty()

            if not dfs_hist:
                st.error("❌ No se hallaron registros históricos para los periodos seleccionados.")
                st.stop()

            fusionado = pd.concat(dfs_hist, ignore_index=True)

            # Identificación de coordenadas GPS
            lat_col = next((c for c in fusionado.columns if "lat" in str(c).lower()), None)
            lon_col = next((c for c in fusionado.columns if "lon" in str(c).lower()), None)

            if not lat_col or not lon_col:
                st.error("❌ Columnas de coordenadas geográficas (Lat/Lon) ausentes en el set de datos.")
                st.stop()

            # Sanitización de datos espaciales
            fusionado[lat_col] = pd.to_numeric(fusionado[lat_col], errors="coerce")
            fusionado[lon_col] = pd.to_numeric(fusionado[lon_col], errors="coerce")
            fusionado = fusionado[(fusionado[lat_col] != 0) & (fusionado[lon_col] != 0)].dropna(subset=[lat_col, lon_col])

            centro_lat = fusionado[lat_col].median()
            centro_lon = fusionado[lon_col].median()

            # Procesamiento de Clústeres por Suministro (Algoritmo Haversine)
            resultados = []
            grupos = fusionado.groupby(col_suministro)
            total_grupos = len(grupos)
            progress_gis = st.progress(0)

            for i, (suministro, grupo) in enumerate(grupos):
                puntos = grupo[[lat_col, lon_col]].values
                meses = len(grupo["periodo_historico"].unique())

                if len(puntos) == 1:
                    lat_final, lon_final = puntos[0][0], puntos[0][1]
                    estado_gps, dispersion = "UNICO", 0.0
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
                        distancias = [haversine(pt[0], pt[1], centro_lat, centro_lon) for pt in puntos]
                        idx = int(np.argmin(distancias))
                        estado_gps = "REBOTADO"
                    else:
                        suma = matriz.sum(axis=1)
                        idx = int(np.argmin(suma))
                        estado_gps = "VALIDADO"

                    lat_final, lon_final = puntos[idx][0], puntos[idx][1]

                resultados.append({
                    col_suministro: suministro,
                    "latitud_validada": lat_final,
                    "longitud_validada": lon_final,
                    "estado_gps": estado_gps,
                    "dispersion_m": round(dispersion, 2),
                    "meses_historicos": meses,
                    "google_maps": f"https://www.google.com/maps/search/?api=1&query={lat_final},{lon_final}"
                })
                progress_gis.progress((i + 1) / total_grupos)

            progress_gis.empty()

            # Ensamble final de la estructura de datos
            df_gps = pd.DataFrame(resultados)
            df_final = df_base.merge(df_gps, on=col_suministro, how="left")
            
            # Guardado en buffer de memoria (Evita lecturas en disco local del servidor)
            output_excel = BytesIO()
            with pd.ExcelWriter(output_excel, engine="xlsxwriter") as writer:
                df_final.to_excel(writer, index=False, sheet_name="GIS_VALIDADO")
            
            st.session_state["df_final"] = df_final
            st.session_state["excel_bytes"] = output_excel.getvalue()
            st.session_state["col_suministro"] = col_suministro
            st.session_state["ruta_activa"] = ruta

            st.success(f"✅ Análisis completado. {len(df_base):,} registros procesados.")

        except Exception as e:
            st.error(f"Fallo crítico en el procesamiento: {str(e)}")

# =========================================================
# VISTA DE RESULTADOS ANALÍTICOS
# =========================================================
if "df_final" in st.session_state:
    df_final = st.session_state["df_final"]
    excel_bytes = st.session_state["excel_bytes"]
    col_suministro = st.session_state["col_suministro"]
    ruta_activa = st.session_state["ruta_activa"]

    st.write("---")
    st.download_button(
        label="📥 DESCARGAR INFORME EXCEL PROCESADO",
        data=excel_bytes,
        file_name=f"GIS_VALIDADO_RUTA_{ruta_activa}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

    # Modularización por pestañas para optimizar espacio en pantalla
    tab_mapa, tab_datos = st.tabs(["🗺️ Visualización de Georreferenciación", "📊 Matriz de Datos General"])

    with tab_mapa:
        df_mapa = df_final.dropna(subset=["latitud_validada", "longitud_validada"])

        if len(df_mapa) > 0:
            c_lat = df_mapa["latitud_validada"].median()
            c_lon = df_mapa["longitud_validada"].median()

            mapa = folium.Map(location=[c_lat, c_lon], zoom_start=14)

            for _, row in df_mapa.iterrows():
                if row["estado_gps"] == "REBOTADO":
                    color = "red"
                elif row["estado_gps"] == "UNICO":
                    color = "blue"
                else:
                    color = "green"

                popup_html = f"""
                <div style='font-family: Arial, sans-serif; font-size: 12px;'>
                    <b>Suministro:</b> {row[col_suministro]}<br>
                    <b>Estado GPS:</b> <span style='color:{color}; font-weight:bold;'>{row['estado_gps']}</span><br>
                    <b>Dispersión:</b> {row['dispersion_m']} m<br>
                    <a href='{row['google_maps']}' target='_blank'>🧭 Ver en Google Maps</a>
                </div>
                """

                folium.CircleMarker(
                    location=[row["latitud_validada"], row["longitud_validada"]],
                    radius=5,
                    popup=folium.Popup(popup_html, max_width=250),
                    tooltip=f"Suministro: {row[col_suministro]}",
                    color=color,
                    fill=True,
                    fill_opacity=0.75
                ).add_to(mapa)

            st_folium(mapa, width="100%", height=600, returned_objects=[])
        else:
            st.warning("⚠️ No existen coordenadas válidas procesadas para mapear en esta ruta.")

    with tab_datos:
        st.dataframe(df_final, use_container_width=True)