import streamlit as st
import requests
import pandas as pd
import numpy as np
import folium
import streamlit.components.v1 as components

from folium.plugins import MarkerCluster
from bs4 import BeautifulSoup
from io import BytesIO
from datetime import datetime
from dateutil.relativedelta import relativedelta
from math import radians, sin, cos, sqrt, atan2

# =========================================================
# CONFIG
# =========================================================

st.set_page_config(
    page_title="SIGOF GIS",
    layout="wide",
    initial_sidebar_state="collapsed"
)

LOGIN_URL = "http://sigof.distriluz.com.pe/plus/usuario/login"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": LOGIN_URL,
}

st.title("🛰️ SIGOF GIS")

# =========================================================
# FUNCIONES
# =========================================================

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
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
# LOGIN
# =========================================================

usuario = st.text_input("Usuario SIGOF")
password = st.text_input("Contraseña", type="password")

if st.button("INICIAR SESIÓN"):
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

    except Exception as e:
        st.error(str(e))

# =========================================================
# DESPUÉS LOGIN
# =========================================================

if st.session_state.get("logueado"):
    st.subheader("⚙️ Configuración GIS")

    ruta = st.text_input("Ruta", placeholder="Ejemplo: 46516")
    tipo_mapa = st.radio("Tipo procesamiento", ["TOTAL RUTA", "SOLO PENDIENTES"])

    actual = datetime.now()
    mes_1 = (actual - relativedelta(months=1)).strftime("%Y%m")
    mes_2 = (actual - relativedelta(months=2)).strftime("%Y%m")

    default_periodos = list(dict.fromkeys(["202409", "202410", "202508", "202509", mes_1, mes_2]))
    periodos = []

    anio = actual.year
    mes = actual.month

    while anio > 2024 or (anio == 2024 and mes >= 9):
        periodos.append(f"{anio}{mes:02d}")
        mes -= 1
        if mes == 0:
            mes = 12
            anio -= 1

    periodos_seleccionados = st.multiselect("Períodos históricos", periodos, default=default_periodos)

    # =====================================================
    # PROCESAR
    # =====================================================
    if st.button("🛰️ PROCESAR GIS"):
        try:
            session = st.session_state["session"]
            hoy = datetime.now().strftime("%Y-%m-%d")

            if tipo_mapa == "SOLO PENDIENTES":
                url_actual = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{ruta}/0/0/0/0/LSC/0/9/0"
            else:
                url_actual = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{ruta}/0/0/0/0/0/0/9/0"

            with st.spinner("📥 Descargando base actual..."):
                r = session.get(url_actual, headers=HEADERS, timeout=180)

            if r.status_code != 200 or r.content[:2] != b"PK":
                st.error("❌ Error descargando información")
                st.stop()

            df_actual = pd.read_excel(BytesIO(r.content))
            st.success(f"✅ Registros encontrados: {len(df_actual):,}")

            col_suministro = None
            for c in df_actual.columns:
                if "suministro" in str(c).lower():
                    col_suministro = c
                    break

            if not col_suministro:
                st.error("❌ No existe columna suministro")
                st.stop()

            suministros_actuales = df_actual[col_suministro].astype(str).unique()

            # Históricos
            dfs_hist = []
            total = len(periodos_seleccionados)

            progress_hist = st.progress(0)
            estado_hist = st.empty()

            for i, periodo in enumerate(periodos_seleccionados):
                url_hist = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{ruta}/0/0/0/0/0/0/9/{periodo}"
                rh = session.get(url_hist, headers=HEADERS, timeout=180)

                if rh.status_code == 200 and rh.content[:2] == b"PK":
                    df_temp = pd.read_excel(BytesIO(rh.content))
                    df_temp = df_temp[df_temp[col_suministro].astype(str).isin(suministros_actuales)]
                    df_temp["periodo_historico"] = periodo
                    dfs_hist.append(df_temp)

                porcentaje = int(((i + 1) / total) * 100)
                progress_hist.progress(porcentaje / 100)
                estado_hist.write(f"📥 Históricos {i+1}/{total} ({porcentaje}%)")

            if not dfs_hist:
                st.error("❌ No existen históricos")
                st.stop()

            fusionado = pd.concat(dfs_hist, ignore_index=True)
            estado_hist.write(f"✅ Históricos fusionados: {len(fusionado):,}")

            # Detectar LAT/LON
            lat_col = None
            lon_col = None

            for c in fusionado.columns:
                cl = str(c).lower()
                if "lat" in cl: lat_col = c
                if "lon" in cl: lon_col = c

            fusionado[lat_col] = pd.to_numeric(fusionado[lat_col], errors="coerce")
            fusionado[lon_col] = pd.to_numeric(fusionado[lon_col], errors="coerce")

            fusionado = fusionado[(fusionado[lat_col] != 0) & (fusionado[lon_col] != 0)]

            centro_lat = fusionado[lat_col].median()
            centro_lon = fusionado[lon_col].median()

            # Análisis GIS
            resultados = []
            grupos = fusionado.groupby(col_suministro)
            total_grupos = len(grupos)

            progress_gis = st.progress(0)
            estado_gis = st.empty()

            for i, (suministro, grupo) in enumerate(grupos):
                puntos = grupo[[lat_col, lon_col]].values
                meses = len(grupo["periodo_historico"].unique())

                if len(puntos) == 1:
                    lat_final = puntos[0][0]
                    lon_final = puntos[0][1]
                    dispersion = 0
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
                        distancias = []
                        for pt in puntos:
                            distancias.append(haversine(pt[0], pt[1], centro_lat, centro_lon))
                        idx = int(np.argmin(distancias))
                        estado = "REBOTADO"
                    else:
                        suma = matriz.sum(axis=1)
                        idx = int(np.argmin(suma))
                        estado = "VALIDADO"

                    lat_final = puntos[idx][0]
                    lon_final = puntos[idx][1]

                # CORRECCIÓN AQUÍ: Cambiado el formato del link para evitar que rompa las celdas en Excel
                resultados.append({
                    col_suministro: suministro,
                    "latitud_validada": float(lat_final),
                    "longitud_validada": float(lon_final),
                    "estado_gps": estado,
                    "dispersion_m": round(dispersion, 2),
                    "meses_historicos": meses,
                    "google_maps": f"https://www.google.com/maps?q={lat_final},{lon_final}"
                })

                porcentaje_gis = int(((i + 1) / total_grupos) * 100)
                progress_gis.progress(porcentaje_gis / 100)

                if i % 50 == 0 or i == total_grupos - 1:
                    estado_gis.write(f"🛰️ GIS {i+1:,}/{total_grupos:,} ({porcentaje_gis}%)")

            df_gps = pd.DataFrame(resultados)
            df_final = df_actual.merge(df_gps, on=col_suministro, how="left")

            # Exportar
            progress_excel = st.progress(0)
            estado_excel = st.empty()
            estado_excel.write("📎 Generando Excel...")

            salida = f"GIS_{ruta}.xlsx"
            
            # Ajuste de exportación usando un Buffer en memoria para evitar bloqueos de archivos en disco
            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df_final.to_excel(writer, index=False, sheet_name="GIS")
            excel_data = output.getvalue()

            progress_excel.progress(1.0)
            estado_excel.write("✅ Excel generado")

            st.download_button(
                "📥 DESCARGAR EXCEL FINAL",
                data=excel_data,
                file_name=salida,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # Mapa
            st.subheader("🗺️ MAPA GIS")
            df_mapa = df_final.dropna(subset=["latitud_validada", "longitud_validada"])

            mapa = folium.Map(location=[centro_lat, centro_lon], zoom_start=15, tiles=None)

            folium.TileLayer("OpenStreetMap", name="Normal").add_to(mapa)
            folium.TileLayer(
                tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                attr="Google",
                name="Satélite"
            ).add_to(mapa)

            mini_cluster = folium.FeatureGroup(name="Mini puntos").add_to(mapa)
            cluster = MarkerCluster(
                name="Suministros",
                overlay=True,
                control=False,
                disableClusteringAtZoom=22,
                spiderfyOnMaxZoom=False,
                showCoverageOnHover=False,
                zoomToBoundsOnClick=False
            ).add_to(mapa)

            for _, row in df_mapa.iterrows():
                color = "green"
                if row["estado_gps"] == "REBOTADO":
                    color = "red"
                elif row["estado_gps"] == "UNICO":
                    color = "blue"

                popup = (
                    f"<b>Suministro:</b> {row[col_suministro]}<br>"
                    f"<b>Estado:</b> {row['estado_gps']}<br>"
                    f"<b>Dispersión:</b> {row['dispersion_m']} m<br>"
                    f"<a href='{row['google_maps']}' target='_blank'>🌍 Ver Mapa</a>"
                )

                folium.CircleMarker(
                    location=[row["latitud_validada"], row["longitud_validada"]],
                    radius=7,
                    popup=popup,
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.9,
                    weight=2
                ).add_to(cluster)

                folium.CircleMarker(
                    location=[row["latitud_validada"], row["longitud_validada"]],
                    radius=2,
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=1,
                    weight=1
                ).add_to(mini_cluster)

                folium.Marker(
                    location=[row["latitud_validada"], row["longitud_validada"]],
                    icon=folium.DivIcon(
                        icon_size=(160, 36),
                        icon_anchor=(80, -18),
                        html=f"""
                        <div style="
                            font-size:8px;
                            color:black;
                            font-weight:bold;
                            text-align:center;
                            white-space: nowrap;
                            margin-top:18px;
                        ">
                            {row[col_suministro]}
                        </div>
                        """
                    )
                ).add_to(cluster)

            folium.LayerControl().add_to(mapa)
            mapa_html = mapa._repr_html_()
            components.html(mapa_html, height=850, scrolling=True)

        except Exception as e:
            st.error(str(e))