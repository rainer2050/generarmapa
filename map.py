import streamlit as st
import requests
import pandas as pd
import numpy as np
import folium
import streamlit.components.v1 as components

from folium import plugins
from folium.plugins import MarkerCluster

from bs4 import BeautifulSoup
from io import BytesIO
from datetime import datetime
from dateutil.relativedelta import relativedelta
from math import radians, sin, cos, sqrt, atan2

# =========================================================
# CONFIGURACIÓN
# =========================================================

st.set_page_config(
    page_title="SIGOF GIS AVANZADO",
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
# SESSION STATE
# =========================================================

if "logueado" not in st.session_state:
    st.session_state["logueado"] = False

if "mapa_html" not in st.session_state:
    st.session_state["mapa_html"] = None

if "excel_data" not in st.session_state:
    st.session_state["excel_data"] = None

if "nombre_excel" not in st.session_state:
    st.session_state["nombre_excel"] = None

# =========================================================
# FUNCIÓN HAVERSINE
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

    password = st.text_input(
        "Contraseña",
        type="password"
    )

    if st.button("INICIAR SESIÓN"):

        try:

            session = requests.Session()

            login_page = session.get(
                LOGIN_URL,
                headers=HEADERS,
                timeout=60
            )

            soup = BeautifulSoup(
                login_page.text,
                "html.parser"
            )

            csrf = soup.find(
                "input",
                {"name": "_csrf_token"}
            )

            credentials = {
                "data[Usuario][usuario]": usuario,
                "data[Usuario][pass]": password
            }

            if csrf:
                credentials["_csrf_token"] = csrf["value"]

            r = session.post(
                LOGIN_URL,
                data=credentials,
                headers=HEADERS,
                timeout=60
            )

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
# PANEL PRINCIPAL
# =========================================================

if st.session_state["logueado"]:

    session = st.session_state["session"]

    st.subheader("⚙️ CONFIGURACIÓN GIS")

    # =====================================================
    # MODOS
    # =====================================================

    modo = st.radio(
        "Modo trabajo",
        [
            "POR RUTA",
            "POR LECTURISTA",
            "POR SUMINISTROS"
        ]
    )

    # =====================================================
    # TIPO MAPA
    # =====================================================

    if modo == "POR LECTURISTA":

        tipo_mapa = st.radio(
            "Tipo",
            [
                "TODOS",
                "PENDIENTES",
                "PENDIENTES + RELECTURAS"
            ]
        )

    else:

        tipo_mapa = st.radio(
            "Tipo",
            [
                "TOTAL",
                "PENDIENTES"
            ]
        )

    # =====================================================
    # POR RUTA
    # =====================================================

    if modo == "POR RUTA":

        codigo = st.text_input(
            "Código ruta",
            placeholder="Ejemplo: 68724"
        )

    # =====================================================
    # POR LECTURISTA
    # =====================================================

    elif modo == "POR LECTURISTA":

        try:

            url_lect = (
                "http://sigof.distriluz.com.pe/"
                "plus/ValidaImei/listarusuario"
            )

            r_lect = session.get(
                url_lect,
                headers=HEADERS,
                timeout=120
            )

            usuarios = r_lect.json()

            lecturistas = []

            for u in usuarios:

                if not u.get("Roles"):
                    continue

                for rol in u["Roles"]:

                    if rol.get("nombre") == "Lecturista":

                        lecturistas.append({
                            "nombre": u["NombreUsuario"],
                            "id": str(u["IdProveedorPersonal"])
                        })

                        break

            dict_lect = {
                x["nombre"]: x["id"]
                for x in lecturistas
            }

            nombre_lect = st.selectbox(
                "Seleccione Lecturista",
                sorted(dict_lect.keys())
            )

            codigo = dict_lect[nombre_lect]

        except Exception as e:

            st.error(f"Error lecturistas: {e}")
            st.stop()

    # =====================================================
    # POR SUMINISTROS
    # =====================================================

    else:

        suministros_manual = st.text_area(
            "Ingresar suministros separados por coma",
            height=120
        )

        archivo_excel = st.file_uploader(
            "O cargar Excel",
            type=["xlsx"]
        )

        lista_suministros = []

        if suministros_manual.strip():

            lista_suministros.extend([
                x.strip()
                for x in suministros_manual.split(",")
                if x.strip()
            ])

        if archivo_excel is not None:

            try:

                df_excel = pd.read_excel(
                    archivo_excel
                )

                primera_col = df_excel.columns[0]

                lista_excel = (
                    df_excel[primera_col]
                    .dropna()
                    .astype(str)
                    .tolist()
                )

                lista_suministros.extend(lista_excel)

            except Exception as e:

                st.error(
                    f"Error leyendo Excel: {e}"
                )

        lista_suministros = list(
            set(lista_suministros)
        )

        codigo = ",".join(lista_suministros)

    # =====================================================
    # PERIODOS
    # =====================================================

    actual = datetime.now()

    mes_1 = (
        actual - relativedelta(months=1)
    ).strftime("%Y%m")

    mes_2 = (
        actual - relativedelta(months=2)
    ).strftime("%Y%m")

    default_periodos = list(dict.fromkeys([
        "202409",
        "202410",
        "202508",
        "202509",
        mes_1,
        mes_2
    ]))

    periodos = []

    anio = actual.year
    mes = actual.month

    while anio > 2024 or (anio == 2024 and mes >= 9):

        periodos.append(f"{anio}{mes:02d}")

        mes -= 1

        if mes == 0:
            mes = 12
            anio -= 1

    periodos_seleccionados = st.multiselect(
        "Históricos",
        periodos,
        default=default_periodos
    )

    # =====================================================
    # PROCESAR GIS
    # =====================================================

    if st.button("🛰️ PROCESAR GIS"):

        try:

            hoy = datetime.now().strftime("%Y-%m-%d")

            # =================================================
            # OBTENER BASE ACTUAL
            # =================================================

            df_actual = None

            # =============================================
            # POR RUTA
            # =============================================

            if modo == "POR RUTA":

                if tipo_mapa == "PENDIENTES":

                    url_actual = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/ajax_ordenes_historico_xls/"
                        f"U/{hoy}/{hoy}/0/0/0/"
                        f"{codigo}/0/0/0/0/LSC/0/9/0"
                    )

                else:

                    url_actual = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/ajax_ordenes_historico_xls/"
                        f"U/{hoy}/{hoy}/0/0/0/"
                        f"{codigo}/0/0/0/0/0/0/9/0"
                    )

                r = session.get(
                    url_actual,
                    headers=HEADERS,
                    timeout=180
                )

                if r.status_code != 200:
                    st.error("❌ Error servidor")
                    st.stop()

                if r.content[:2] != b"PK":
                    st.warning("⚠️ 0 registros encontrados")
                    st.stop()

                df_actual = pd.read_excel(
                    BytesIO(r.content)
                )

            # =============================================
            # POR LECTURISTA
            # =============================================

            elif modo == "POR LECTURISTA":

                if tipo_mapa == "TODOS":

                    url_actual = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/ajax_ordenes_historico_xls/"
                        f"U,L/{hoy}/{hoy}/0/0/0/0/0/"
                        f"{codigo}/0/0/0/0/9/0"
                    )

                    r = session.get(
                        url_actual,
                        headers=HEADERS,
                        timeout=180
                    )

                    if r.content[:2] != b"PK":
                        st.warning("⚠️ 0 registros")
                        st.stop()

                    df_actual = pd.read_excel(
                        BytesIO(r.content)
                    )

                elif tipo_mapa == "PENDIENTES":

                    url_actual = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/ajax_ordenes_historico_xls/"
                        f"U,L/{hoy}/{hoy}/0/0/0/0/0/"
                        f"{codigo}/0/0/LSC/0/9/0"
                    )

                    r = session.get(
                        url_actual,
                        headers=HEADERS,
                        timeout=180
                    )

                    if r.content[:2] != b"PK":
                        st.warning("⚠️ 0 pendientes")
                        st.stop()

                    df_actual = pd.read_excel(
                        BytesIO(r.content)
                    )

                elif tipo_mapa == "PENDIENTES + RELECTURAS":

                    url_pend = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/ajax_ordenes_historico_xls/"
                        f"U,L/{hoy}/{hoy}/0/0/0/0/0/"
                        f"{codigo}/0/0/LSC/0/9/0"
                    )

                    url_rel = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/ajax_ordenes_historico_xls/"
                        f"U,L/{hoy}/{hoy}/0/0/0/0/0/"
                        f"{codigo}/0/0/REL/0/9/0"
                    )

                    r1 = session.get(
                        url_pend,
                        headers=HEADERS,
                        timeout=180
                    )

                    r2 = session.get(
                        url_rel,
                        headers=HEADERS,
                        timeout=180
                    )

                    dfs_concat = []

                    if r1.content[:2] == b"PK":

                        df_p = pd.read_excel(
                            BytesIO(r1.content)
                        )

                        dfs_concat.append(df_p)

                    if r2.content[:2] == b"PK":

                        df_r = pd.read_excel(
                            BytesIO(r2.content)
                        )

                        dfs_concat.append(df_r)

                    if not dfs_concat:

                        st.warning(
                            "⚠️ No existen pendientes ni relecturas."
                        )

                        st.stop()

                    df_actual = pd.concat(
                        dfs_concat,
                        ignore_index=True
                    )

                    # =========================================
                    # FILTRO RESULTADO VACÍO
                    # =========================================

                    col_resultado = None

                    for c in df_actual.columns:

                        if str(c).strip().lower() == "resultado":
                            col_resultado = c
                            break

                    if col_resultado:

                        df_actual = df_actual[
                            df_actual[col_resultado]
                            .fillna("")
                            .astype(str)
                            .str.strip()
                            == ""
                        ]

                        st.info(
                            f"📋 Resultado vacío: "
                            f"{len(df_actual):,}"
                        )

            # =============================================
            # POR SUMINISTROS
            # =============================================

            else:

                if not codigo:
                    st.warning(
                        "⚠️ Debe ingresar suministros"
                    )
                    st.stop()

                url_actual = (
                    f"http://sigof.distriluz.com.pe/"
                    f"plus/Reportes/ajax_ordenes_historico_xls/"
                    f"U,S/{hoy}/{hoy}/0/0/0/0/"
                    f"{codigo}/0/0/0/0/0/9/0"
                )

                r = session.get(
                    url_actual,
                    headers=HEADERS,
                    timeout=180
                )

                if r.content[:2] != b"PK":
                    st.warning("⚠️ 0 registros")
                    st.stop()

                df_actual = pd.read_excel(
                    BytesIO(r.content)
                )

            # =================================================
            # VALIDACIÓN BASE
            # =================================================

            if df_actual is None or df_actual.empty:

                st.warning("⚠️ No hay registros.")
                st.stop()

            st.success(
                f"✅ Registros encontrados: "
                f"{len(df_actual):,}"
            )

            # =================================================
            # SUMINISTRO
            # =================================================

            col_suministro = None

            for c in df_actual.columns:

                if "suministro" in str(c).lower():

                    col_suministro = c
                    break

            if not col_suministro:

                st.error("❌ No existe suministro")
                st.stop()

            suministros = (
                df_actual[col_suministro]
                .astype(str)
                .unique()
            )

            # =================================================
            # DETECTAR RUTAS
            # =================================================

            rutas_detectadas = []

            if modo == "POR LECTURISTA":

                col_ruta = None

                for c in df_actual.columns:

                    if "ruta" in str(c).lower():

                        col_ruta = c
                        break

                if col_ruta:

                    rutas_texto = (
                        df_actual[col_ruta]
                        .dropna()
                        .astype(str)
                        .unique()
                        .tolist()
                    )

                    for rt in rutas_texto:

                        if "-" in rt:

                            codigo_ruta = (
                                rt.split("-")[0]
                                .strip()
                            )

                            if codigo_ruta.isdigit():

                                rutas_detectadas.append(
                                    codigo_ruta
                                )

                rutas_detectadas = list(
                    set(rutas_detectadas)
                )

            elif modo == "POR RUTA":

                rutas_detectadas = [codigo]

            # =================================================
            # HISTÓRICOS
            # =================================================

            dfs_hist = []

            progress = st.progress(0)

            if modo in ["POR RUTA", "POR LECTURISTA"]:

                total_descargas = (
                    len(rutas_detectadas)
                    * len(periodos_seleccionados)
                )

                contador = 0

                for ruta_hist in rutas_detectadas:

                    for periodo in periodos_seleccionados:

                        url_hist = (
                            f"http://sigof.distriluz.com.pe/"
                            f"plus/Reportes/ajax_ordenes_historico_xls/"
                            f"U/{hoy}/{hoy}/0/0/0/"
                            f"{ruta_hist}/0/0/0/0/0/0/9/{periodo}"
                        )

                        try:

                            rh = session.get(
                                url_hist,
                                headers=HEADERS,
                                timeout=180
                            )

                            if rh.content[:2] == b"PK":

                                df_temp = pd.read_excel(
                                    BytesIO(rh.content)
                                )

                                df_temp = df_temp[
                                    df_temp[col_suministro]
                                    .astype(str)
                                    .isin(suministros)
                                ]

                                if not df_temp.empty:

                                    df_temp["periodo_historico"] = periodo

                                    dfs_hist.append(df_temp)

                        except:
                            pass

                        contador += 1

                        progress.progress(
                            contador / total_descargas
                        )

            else:

                total_descargas = len(
                    periodos_seleccionados
                )

                contador = 0

                for periodo in periodos_seleccionados:

                    url_hist = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/ajax_ordenes_historico_xls/"
                        f"U,S/{hoy}/{hoy}/0/0/0/0/"
                        f"{codigo}/0/0/0/0/0/9/{periodo}"
                    )

                    try:

                        rh = session.get(
                            url_hist,
                            headers=HEADERS,
                            timeout=180
                        )

                        if rh.content[:2] == b"PK":

                            df_temp = pd.read_excel(
                                BytesIO(rh.content)
                            )

                            df_temp = df_temp[
                                df_temp[col_suministro]
                                .astype(str)
                                .isin(suministros)
                            ]

                            if not df_temp.empty:

                                df_temp["periodo_historico"] = periodo

                                dfs_hist.append(df_temp)

                    except:
                        pass

                    contador += 1

                    progress.progress(
                        contador / total_descargas
                    )

            # =================================================
            # VALIDACIÓN HISTÓRICOS
            # =================================================

            if not dfs_hist:

                st.warning(
                    "⚠️ No existen históricos."
                )

                st.stop()

            fusionado = pd.concat(
                dfs_hist,
                ignore_index=True
            )

            # =================================================
            # COORDENADAS
            # =================================================

            lat_col = None
            lon_col = None

            for c in fusionado.columns:

                cl = str(c).lower()

                if "lat" in cl:
                    lat_col = c

                if "lon" in cl:
                    lon_col = c

            fusionado[lat_col] = pd.to_numeric(
                fusionado[lat_col],
                errors="coerce"
            )

            fusionado[lon_col] = pd.to_numeric(
                fusionado[lon_col],
                errors="coerce"
            )

            fusionado = fusionado[
                (fusionado[lat_col] != 0)
                &
                (fusionado[lon_col] != 0)
            ]

            # =================================================
            # ÚLTIMO PERIODO VÁLIDO
            # =================================================

            fusionado = fusionado.sort_values(
                "periodo_historico",
                ascending=False
            )

            # =================================================
            # CENTRO
            # =================================================

            centro_lat = fusionado[lat_col].median()
            centro_lon = fusionado[lon_col].median()

            # =================================================
            # GIS
            # =================================================

            resultados = []

            grupos = fusionado.groupby(
                col_suministro
            )

            total_grupos = len(grupos)

            progress_gis = st.progress(0)

            for i, (suministro, grupo) in enumerate(grupos):

                grupo = grupo.sort_values(
                    "periodo_historico",
                    ascending=False
                )

                puntos = grupo[
                    [lat_col, lon_col]
                ].values

                meses = len(
                    grupo["periodo_historico"]
                    .unique()
                )

                # =============================================
                # SOLO 1 REGISTRO
                # =============================================

                if len(puntos) == 1:

                    lat_final = puntos[0][0]
                    lon_final = puntos[0][1]

                    estado_gps = "ULTIMO PERIODO"

                    dispersion = 0

                else:

                    n = len(puntos)

                    matriz = np.zeros((n, n))

                    for x in range(n):

                        for y in range(x + 1, n):

                            d = haversine(
                                puntos[x][0],
                                puntos[x][1],
                                puntos[y][0],
                                puntos[y][1]
                            )

                            matriz[x, y] = d
                            matriz[y, x] = d

                    dispersion = matriz.max()

                    if dispersion > 500:

                        idx = 0

                        estado_gps = "ULTIMO PERIODO"

                    else:

                        suma = matriz.sum(axis=1)

                        idx = int(
                            np.argmin(suma)
                        )

                        estado_gps = "VALIDADO"

                    lat_final = puntos[idx][0]
                    lon_final = puntos[idx][1]

                resultados.append({

                    col_suministro: suministro,

                    "latitud_validada": lat_final,

                    "longitud_validada": lon_final,

                    "estado_gps": estado_gps,

                    "dispersion_m": round(
                        dispersion,
                        2
                    ),

                    "meses_historicos": meses,

                    "google_maps":
                    f"https://www.google.com/maps?q="
                    f"{lat_final},{lon_final}"
                })

                progress_gis.progress(
                    (i + 1) / total_grupos
                )

            # =================================================
            # FINAL
            # =================================================

            df_gps = pd.DataFrame(resultados)

            df_final = df_actual.merge(
                df_gps,
                on=col_suministro,
                how="left"
            )

            # =================================================
            # EXCEL
            # =================================================

            output = BytesIO()

            with pd.ExcelWriter(
                output,
                engine="xlsxwriter"
            ) as writer:

                df_final.to_excel(
                    writer,
                    index=False,
                    sheet_name="GIS"
                )

            st.session_state["excel_data"] = output.getvalue()

            st.session_state["nombre_excel"] = (
                f"GIS_{modo}_{hoy}.xlsx"
            )

            # =================================================
            # MAPA
            # =================================================

            st.subheader("🗺️ MAPA GIS")

            df_mapa = df_final.dropna(
                subset=[
                    "latitud_validada",
                    "longitud_validada"
                ]
            )

            mapa = folium.Map(
                location=[
                    centro_lat,
                    centro_lon
                ],
                zoom_start=13,
                tiles=None
            )

            plugins.Fullscreen().add_to(mapa)

            folium.TileLayer(
                "OpenStreetMap",
                name="Mapa"
            ).add_to(mapa)

            folium.TileLayer(
                tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                attr="Google",
                name="Satélite"
            ).add_to(mapa)

            cluster = MarkerCluster(
                disableClusteringAtZoom=12,
                showCoverageOnHover=False
            ).add_to(mapa)

            for _, row in df_mapa.iterrows():

                color_icono = "green"

                if row["estado_gps"] == "ULTIMO PERIODO":
                    color_icono = "blue"

                elif row["estado_gps"] == "REBOTADO":
                    color_icono = "red"

                popup_html = (
                    f"<b>Suministro:</b> "
                    f"{row[col_suministro]}<br>"
                    f"<b>Estado:</b> "
                    f"{row['estado_gps']}<br>"
                    f"<b>Dispersión:</b> "
                    f"{row['dispersion_m']} m<br>"
                    f"<a href='{row['google_maps']}' "
                    f"target='_blank'>"
                    f"🌍 Abrir Google Maps</a>"
                )

                folium.Marker(
                    location=[
                        row["latitud_validada"],
                        row["longitud_validada"]
                    ],
                    popup=popup_html,
                    icon=folium.Icon(
                        color=color_icono,
                        icon="info-sign"
                    )
                ).add_to(cluster)

            folium.LayerControl().add_to(mapa)

            st.session_state["mapa_html"] = (
                mapa._repr_html_()
            )

        except Exception as e:

            st.error(
                f"Error general: {e}"
            )

    # =====================================================
    # MOSTRAR EXCEL
    # =====================================================

    if st.session_state["excel_data"]:

        st.download_button(
            "📥 DESCARGAR EXCEL",
            data=st.session_state["excel_data"],
            file_name=st.session_state["nombre_excel"],
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # =====================================================
    # MOSTRAR MAPA
    # =====================================================

    if st.session_state["mapa_html"]:

        components.html(
            st.session_state["mapa_html"],
            height=850,
            scrolling=True
        )