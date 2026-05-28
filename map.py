
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

if "excel_nombre" not in st.session_state:
    st.session_state["excel_nombre"] = None

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
    password = st.text_input("Contraseña", type="password")

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

    modo = st.radio(
        "Modo trabajo",
        [
            "POR RUTA",
            "POR LECTURISTA",
            "POR SUMINISTROS"
        ]
    )

    # =====================================================
    # TIPO
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
            placeholder="Ejemplo: 46516"
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
            "Ingrese suministros separados por coma",
            height=120
        )

        archivo_excel = st.file_uploader(
            "O subir Excel",
            type=["xlsx"]
        )

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
            # URL ACTUAL
            # =================================================

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

            elif modo == "POR LECTURISTA":

                if tipo_mapa == "PENDIENTES":

                    url_actual = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/ajax_ordenes_historico_xls/"
                        f"U,L/{hoy}/{hoy}/0/0/0/0/0/"
                        f"{codigo}/0/0/LSC/0/9/0"
                    )

                elif tipo_mapa == "PENDIENTES + RELECTURAS":

                    url_lsc = (
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

                else:

                    url_actual = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/ajax_ordenes_historico_xls/"
                        f"U,L/{hoy}/{hoy}/0/0/0/0/0/"
                        f"{codigo}/0/0/0/0/9/0"
                    )

            else:

                lista_suministros = ""

                if suministros_manual.strip():

                    lista_suministros = ",".join([
                        x.strip()
                        for x in suministros_manual.split(",")
                        if x.strip()
                    ])

                elif archivo_excel:

                    df_excel = pd.read_excel(archivo_excel)

                    lista_suministros = ",".join(
                        df_excel.iloc[:, 0]
                        .astype(str)
                        .tolist()
                    )

                else:

                    st.error("❌ Ingrese suministros")
                    st.stop()

                url_actual = (
                    f"http://sigof.distriluz.com.pe/"
                    f"plus/Reportes/ajax_ordenes_historico_xls/"
                    f"U,S/{hoy}/{hoy}/0/0/0/0/"
                    f"{lista_suministros}"
                    f"/0/0/0/0/0/9/0"
                )

            # =================================================
            # DESCARGA ACTUAL
            # =================================================

            with st.spinner("📥 Descargando actual..."):

                if (
                    modo == "POR LECTURISTA"
                    and
                    tipo_mapa == "PENDIENTES + RELECTURAS"
                ):

                    r1 = session.get(
                        url_lsc,
                        headers=HEADERS,
                        timeout=180
                    )

                    r2 = session.get(
                        url_rel,
                        headers=HEADERS,
                        timeout=180
                    )

                    dfs_union = []

                    if r1.status_code == 200 and r1.content[:2] == b"PK":

                        dfs_union.append(
                            pd.read_excel(BytesIO(r1.content))
                        )

                    if r2.status_code == 200 and r2.content[:2] == b"PK":

                        dfs_union.append(
                            pd.read_excel(BytesIO(r2.content))
                        )

                    if not dfs_union:

                        st.warning(
                            "⚠️ No existen pendientes ni relecturas."
                        )

                        st.stop()

                    df_actual = pd.concat(
                        dfs_union,
                        ignore_index=True
                    )

                    # FILTRO RESULTADO VACÍO

                    if "Resultado" in df_actual.columns:

                        df_actual = df_actual[
                            df_actual["Resultado"]
                            .isna()
                        ]

                else:

                    r = session.get(
                        url_actual,
                        headers=HEADERS,
                        timeout=180
                    )

                    if r.status_code != 200:
                        st.error("❌ Error servidor")
                        st.stop()

                    if r.content[:2] != b"PK":
                        st.warning("⚠️ No existen registros.")
                        st.stop()

                    df_actual = pd.read_excel(
                        BytesIO(r.content)
                    )

            if df_actual.empty:

                st.warning("⚠️ Sin registros.")
                st.stop()

            st.success(
                f"✅ Registros encontrados: {len(df_actual):,}"
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

                st.error("❌ No existe columna suministro")
                st.stop()

            suministros = (
                df_actual[col_suministro]
                .astype(str)
                .unique()
            )

            # =================================================
            # RUTAS
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

            cantidad_suministros = len(suministros)

            usar_filtro_suministro = (
                cantidad_suministros < 100
            )

            if usar_filtro_suministro:

                st.info(
                    f"⚡ Solo se detectaron "
                    f"{cantidad_suministros} suministros. "
                    f"Se usará búsqueda histórica "
                    f"directa por suministro."
                )

            else:

                st.info(
                    f"🛣️ Se usarán históricos "
                    f"por rutas "
                    f"({cantidad_suministros} suministros)."
                )

            # =================================================
            # CONTADOR
            # =================================================

            if usar_filtro_suministro:

                total_descargas = len(
                    periodos_seleccionados
                )

            else:

                total_descargas = (
                    len(rutas_detectadas)
                    * len(periodos_seleccionados)
                )

            contador = 0

            progress = st.progress(0)

            estado = st.empty()

            # =================================================
            # HISTÓRICO POR SUMINISTRO
            # =================================================

            if usar_filtro_suministro:

                lista_suministros = ",".join(
                    map(str, suministros[:100])
                )

                for periodo in periodos_seleccionados:

                    estado.write(
                        f"📥 Histórico suministro "
                        f"| Periodo {periodo}"
                    )

                    url_hist = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/ajax_ordenes_historico_xls/"
                        f"U,S/{hoy}/{hoy}/0/0/0/0/"
                        f"{lista_suministros}"
                        f"/0/0/0/0/0/9/{periodo}"
                    )

                    try:

                        rh = session.get(
                            url_hist,
                            headers=HEADERS,
                            timeout=180
                        )

                        if (
                            rh.status_code == 200
                            and
                            rh.content[:2] == b"PK"
                        ):

                            df_temp = pd.read_excel(
                                BytesIO(rh.content)
                            )

                            if not df_temp.empty:

                                df_temp["periodo_historico"] = periodo

                                dfs_hist.append(df_temp)

                    except:
                        pass

                    contador += 1

                    progress.progress(
                        min(
                            contador / total_descargas,
                            1.0
                        )
                    )

            # =================================================
            # HISTÓRICO POR RUTA
            # =================================================

            else:

                for ruta_hist in rutas_detectadas:

                    for periodo in periodos_seleccionados:

                        estado.write(
                            f"📥 Ruta {ruta_hist} "
                            f"| {periodo}"
                        )

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

                            if (
                                rh.status_code == 200
                                and
                                rh.content[:2] == b"PK"
                            ):

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
                            min(
                                contador / total_descargas,
                                1.0
                            )
                        )

            if not dfs_hist:

                st.warning("⚠️ Sin históricos.")
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
            # ÚLTIMO PERIODO SI SOLO HAY UNO
            # =================================================

            conteo_periodos = (
                fusionado
                .groupby(col_suministro)
                ["periodo_historico"]
                .nunique()
            )

            fusionado["solo_ultimo"] = (
                fusionado[col_suministro]
                .map(conteo_periodos) == 1
            )

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

                puntos = grupo[
                    [lat_col, lon_col]
                ].values

                meses = len(
                    grupo["periodo_historico"]
                    .unique()
                )

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

                        distancias = [

                            haversine(
                                pt[0],
                                pt[1],
                                centro_lat,
                                centro_lon
                            )

                            for pt in puntos
                        ]

                        idx = int(
                            np.argmin(distancias)
                        )

                        estado_gps = "REBOTADO"

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

            excel_data = output.getvalue()

            st.session_state["excel_data"] = excel_data

            st.session_state["excel_nombre"] = (
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

                if row["estado_gps"] == "REBOTADO":
                    color_icono = "red"

                elif row["estado_gps"] == "ULTIMO PERIODO":
                    color_icono = "blue"

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
            file_name=st.session_state["excel_nombre"],
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

