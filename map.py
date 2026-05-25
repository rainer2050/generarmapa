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

st.title("🛰️ SIGOF GIS AVANZADO")

# =========================================================
# SESSION
# =========================================================

if "logueado" not in st.session_state:
    st.session_state["logueado"] = False

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

if not st.session_state["logueado"]:
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
            st.rerun()

        except Exception as e:
            st.error(str(e))

# =========================================================
# POST LOGIN
# =========================================================

if st.session_state["logueado"]:
    session = st.session_state["session"]
    st.subheader("⚙️ CONFIGURACIÓN GIS")

    # =====================================================
    # MODO DE TRABAJO
    # =====================================================
    modo = st.radio("Modo trabajo", ["POR RUTA", "POR LECTURISTA"])

    # =====================================================
    # TIPO MAPA
    # =====================================================
    tipo_mapa = st.radio("Tipo", ["TOTAL", "PENDIENTES"])

    # =====================================================
    # FILTRADO DINÁMICO (RUTA O LECTURISTA)
    # =====================================================
    if modo == "POR RUTA":
        codigo = st.text_input("Código ruta", placeholder="Ejemplo: 46516")
    else:
        try:
            # Consumir el endpoint para listar los usuarios lecturistas
            url_lect = "http://sigof.distriluz.com.pe/plus/ValidaImei/listarusuario"
            r_lect = session.get(url_lect, headers=HEADERS, timeout=120)
            usuarios = r_lect.json()

            lecturistas = []
            for u in usuarios:
                roles = u.get("Roles", [])
                for rol in roles:
                    if rol.get("nombre") == "Lecturista":
                        lecturistas.append({
                            "nombre": u["NombreUsuario"],
                            "id": str(u["IdUsuario"])
                        })
                        break

            # Mapeo de nombres para el selectbox de Streamlit
            dict_lect = {x["nombre"]: x["id"] for x in lecturistas}
            nombre_lect = st.selectbox("Seleccione el Lecturista", sorted(dict_lect.keys()))
            codigo = dict_lect[nombre_lect]  # 'codigo' ahora almacena el IdUsuario del lecturista

        except Exception as e:
            st.error(f"Error cargando la lista de lecturistas: {e}")
            st.stop()

    # =====================================================
    # PERIODOS HISTÓRICOS
    # =====================================================
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

    periodos_seleccionados = st.multiselect("Históricos", periodos, default=default_periodos)

    # =====================================================
    # PROCESAR
    # =====================================================
    if st.button("🛰️ PROCESAR GIS"):
        try:
            hoy = datetime.now().strftime("%Y-%m-%d")

            # =================================================
            # CONSTRUCCIÓN DE URL BASE ACTUAL
            # =================================================
            if modo == "POR RUTA":
                if tipo_mapa == "PENDIENTES":
                    url_actual = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{codigo}/0/0/0/0/LSC/0/9/0"
                else:
                    url_actual = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{codigo}/0/0/0/0/0/0/9/0"
            else:
                # Filtrado por Lecturista para el mes actual
                if tipo_mapa == "PENDIENTES":
                    url_actual = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U,L/{hoy}/{hoy}/0/0/0/0/0/{codigo}/0/0/LSC/0/9/0"
                else:
                    url_actual = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U,L/{hoy}/{hoy}/0/0/0/0/0/{codigo}/0/0/0/0/9/0"

            with st.spinner("📥 Descargando base actual..."):
                r = session.get(url_actual, headers=HEADERS, timeout=180)

            if r.status_code != 200 or r.content[:2] != b"PK":
                st.error("❌ Error descargando la base actual desde el servidor")
                st.stop()

            df_actual = pd.read_excel(BytesIO(r.content))
            st.success(f"✅ Registros base encontrados: {len(df_actual):,}")

            # Buscar columna Suministro de forma flexible
            col_suministro = None
            for c in df_actual.columns:
                if "suministro" in str(c).lower():
                    col_suministro = c
                    break

            if not col_suministro:
                st.error("❌ No se encontró la columna de suministro en el archivo")
                st.stop()

            suministros = df_actual[col_suministro].astype(str).unique()

            # =================================================
            # DESCARGA FILTRADA DE HISTÓRICOS
            # =================================================
            dfs_hist = []
            progress = st.progress(0)
            total = len(periodos_seleccionados)

            for i, periodo in enumerate(periodos_seleccionados):
                # Aquí corregimos la URL histórica para que use el ID del Lecturista cuando corresponda
                if modo == "POR RUTA":
                    url_hist = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{codigo}/0/0/0/0/0/0/9/{periodo}"
                else:
                    # Se usa la estructura 'U,L' e inyecta el 'codigo' (IdUsuario) en la posición del lecturista
                    url_hist = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U,L/{hoy}/{hoy}/0/0/0/0/0/{codigo}/0/0/0/0/9/{periodo}"

                rh = session.get(url_hist, headers=HEADERS, timeout=180)

                if rh.status_code != 200 or rh.content[:2] != b"PK":
                    continue

                df_temp = pd.read_excel(BytesIO(rh.content))
                # Filtramos inmediatamente para conservar solo los suministros de nuestra base actual
                df_temp = df_temp[df_temp[col_suministro].astype(str).isin(suministros)]

                if not df_temp.empty:
                    df_temp["periodo_historico"] = periodo
                    dfs_hist.append(df_temp)

                porcentaje = int(((i + 1) / total) * 100)
                progress.progress(porcentaje / 100)

            if not dfs_hist:
                st.error("❌ No se encontraron registros históricos para los criterios seleccionados.")
                st.stop()

            fusionado = pd.concat(dfs_hist, ignore_index=True)

            # Buscar columnas de Coordenadas
            lat_col, lon_col = None, None
            for c in fusionado.columns:
                cl = str(c).lower()
                if "lat" in cl: lat_col = c
                if "lon" in cl: lon_col = c

            fusionado[lat_col] = pd.to_numeric(fusionado[lat_col], errors="coerce")
            fusionado[lon_col] = pd.to_numeric(fusionado[lon_col], errors="coerce")
            fusionado = fusionado[(fusionado[lat_col] != 0) & (fusionado[lon_col] != 0)]

            centro_lat = fusionado[lat_col].median()
            centro_lon = fusionado[lon_col].median()

            # =================================================
            # ALGORITMO DE CONSISTENCIA GIS
            # =================================================
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
                    estado = "UNICO"
                    dispersion = 0
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
                        estado = "REBOTADO"
                    else:
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
                    "google_maps": f"https://www.google.com/maps?q={lat_final},{lon_final}"
                })

                porcentaje_gis = int(((i + 1) / total_grupos) * 100)
                progress_gis.progress(porcentaje_gis / 100)

            df_gps = pd.DataFrame(resultados)
            df_final = df_actual.merge(df_gps, on=col_suministro, how="left")

            # Descarga de Reporte Excel
            salida = f"GIS_LECTURISTA_{codigo}.xlsx" if modo == "POR LECTURISTA" else f"GIS_RUTA_{codigo}.xlsx"
            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df_final.to_excel(writer, index=False, sheet_name="GIS")
            excel_data = output.getvalue()

            st.download_button(
                "📥 DESCARGAR EXCEL",
                data=excel_data,
                file_name=salida,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # =====================================================
            # RENDERIZADO DEL MAPA
            # =====================================================
            st.subheader("🗺️ MAPA GIS")
            df_mapa = df_final.dropna(subset=["latitud_validada", "longitud_validada"])

            mapa = folium.Map(location=[centro_lat, centro_lon], zoom_start=15, tiles=None)

            folium.TileLayer("OpenStreetMap", name="Normal").add_to(mapa)
            folium.TileLayer(
                tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                attr="Google",
                name="Satélite"
            ).add_to(mapa)

            cluster = MarkerCluster(
                name="Suministros",
                disableClusteringAtZoom=18,
                showCoverageOnHover=False
            ).add_to(mapa)

            for _, row in df_mapa.iterrows():
                color_icono = "green"
                if row["estado_gps"] == "REBOTADO":
                    color_icono = "red"
                elif row["estado_gps"] == "UNICO":
                    color_icono = "blue"

                popup_html = (
                    f"<b>Suministro:</b> {row[col_suministro]}<br>"
                    f"<b>Estado:</b> {row['estado_gps']}<br>"
                    f"<b>Dispersión:</b> {row['dispersion_m']} m<br>"
                    f"<a href='{row['google_maps']}' target='_blank'>🌍 Google Maps</a>"
                )

                # Marcador Nativo Estable
                folium.Marker(
                    location=[row["latitud_validada"], row["longitud_validada"]],
                    popup=folium.Popup(popup_html, max_width=200),
                    icon=folium.Icon(color=color_icono, icon="info-sign")
                ).add_to(cluster)

                # Etiqueta con el Código de Suministro
                folium.Marker(
                    location=[row["latitud_validada"], row["longitud_validada"]],
                    icon=folium.DivIcon(
                        icon_size=(120, 20),
                        icon_anchor=(60, -18),
                        html=f"""
                        <div style="
                            font-size: 9px;
                            font-weight: bold;
                            color: black;
                            background: rgba(255, 255, 255, 0.9);
                            border-radius: 3px;
                            padding: 1px 3px;
                            border: 1px solid #777;
                            text-align: center;
                            white-space: nowrap;
                            box-shadow: 1px 1px 2px rgba(0,0,0,0.2);
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