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

# =========================================================
# HAVERSINE
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

                st.error(
                    "❌ Usuario o contraseña incorrectos"
                )

                st.stop()

            st.success(
                "✅ Sesión iniciada correctamente"
            )

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
            "Filtro lecturista",
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

        tipo_ingreso = st.radio(
            "Ingreso suministros",
            [
                "MANUAL",
                "EXCEL"
            ]
        )

        lista_suministros = []

        if tipo_ingreso == "MANUAL":

            suministros_texto = st.text_area(
                "Ingrese suministros separados por coma"
            )

            lista_suministros = [
                x.strip()
                for x in suministros_texto.split(",")
                if x.strip()
            ]

        else:

            archivo_excel = st.file_uploader(
                "Subir Excel",
                type=["xlsx"]
            )

            if archivo_excel:

                df_excel = pd.read_excel(
                    archivo_excel
                )

                primera_columna = (
                    df_excel.columns[0]
                )

                lista_suministros = (
                    df_excel[primera_columna]
                    .dropna()
                    .astype(str)
                    .tolist()
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

    while anio > 2024 or (
        anio == 2024 and mes >= 9
    ):

        periodos.append(
            f"{anio}{mes:02d}"
        )

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

            hoy = datetime.now().strftime(
                "%Y-%m-%d"
            )

            # =================================================
            # URL ACTUAL
            # =================================================

            if modo == "POR RUTA":

                if tipo_mapa == "PENDIENTES":

                    url_actual = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/"
                        f"ajax_ordenes_historico_xls/"
                        f"U/{hoy}/{hoy}/0/0/0/"
                        f"{codigo}/0/0/0/0/"
                        f"LSC/0/9/0"
                    )

                else:

                    url_actual = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/"
                        f"ajax_ordenes_historico_xls/"
                        f"U/{hoy}/{hoy}/0/0/0/"
                        f"{codigo}/0/0/0/0/"
                        f"0/0/9/0"
                    )

                r = session.get(
                    url_actual,
                    headers=HEADERS,
                    timeout=180
                )

            # =================================================
            # LECTURISTA
            # =================================================

            elif modo == "POR LECTURISTA":

                dfs_union = []

                if tipo_mapa == "TODOS":

                    urls = [

                        (
                            f"http://sigof.distriluz.com.pe/"
                            f"plus/Reportes/"
                            f"ajax_ordenes_historico_xls/"
                            f"U,L/{hoy}/{hoy}/0/0/0/0/0/"
                            f"{codigo}/0/0/0/0/9/0"
                        )

                    ]

                elif tipo_mapa == "PENDIENTES":

                    urls = [

                        (
                            f"http://sigof.distriluz.com.pe/"
                            f"plus/Reportes/"
                            f"ajax_ordenes_historico_xls/"
                            f"U,L/{hoy}/{hoy}/0/0/0/0/0/"
                            f"{codigo}/0/0/LSC/0/9/0"
                        )

                    ]

                else:

                    urls = [

                        (
                            f"http://sigof.distriluz.com.pe/"
                            f"plus/Reportes/"
                            f"ajax_ordenes_historico_xls/"
                            f"U,L/{hoy}/{hoy}/0/0/0/0/0/"
                            f"{codigo}/0/0/LSC/0/9/0"
                        ),

                        (
                            f"http://sigof.distriluz.com.pe/"
                            f"plus/Reportes/"
                            f"ajax_ordenes_historico_xls/"
                            f"U,L/{hoy}/{hoy}/0/0/0/0/0/"
                            f"{codigo}/0/0/REL/0/9/0"
                        )

                    ]

                for url_extra in urls:

                    try:

                        r_extra = session.get(
                            url_extra,
                            headers=HEADERS,
                            timeout=180
                        )

                        if (
                            r_extra.status_code == 200
                            and
                            r_extra.content[:2] == b"PK"
                        ):

                            df_extra = pd.read_excel(
                                BytesIO(r_extra.content)
                            )

                            dfs_union.append(df_extra)

                    except:
                        pass

                if not dfs_union:

                    st.warning(
                        "⚠️ No existen registros."
                    )

                    st.stop()

                df_actual = pd.concat(
                    dfs_union,
                    ignore_index=True
                )

                df_actual = df_actual.drop_duplicates()

            # =================================================
            # SUMINISTROS
            # =================================================

            else:

                if not lista_suministros:

                    st.warning(
                        "⚠️ No existen suministros."
                    )

                    st.stop()

                suministros_join = ",".join(
                    lista_suministros
                )

                url_actual = (

                    f"http://sigof.distriluz.com.pe/"
                    f"plus/Reportes/"
                    f"ajax_ordenes_historico_xls/"
                    f"U,S/{hoy}/{hoy}/0/0/0/0/"
                    f"{suministros_join}"
                    f"/0/0/0/0/0/9/0"

                )

                r = session.get(
                    url_actual,
                    headers=HEADERS,
                    timeout=180
                )

            # =================================================
            # DESCARGA
            # =================================================

            if modo != "POR LECTURISTA":

                if r.status_code != 200:

                    st.error(
                        "❌ Error servidor"
                    )

                    st.stop()

                if r.content[:2] != b"PK":

                    st.warning(
                        "⚠️ No existen registros."
                    )

                    st.stop()

                df_actual = pd.read_excel(
                    BytesIO(r.content)
                )

            if df_actual.empty:

                st.warning(
                    "⚠️ No existen datos."
                )

                st.stop()

            st.success(
                f"✅ Registros encontrados: "
                f"{len(df_actual):,}"
            )

            # =================================================
            # COLUMNAS
            # =================================================

            col_suministro = None

            for c in df_actual.columns:

                if "suministro" in str(c).lower():

                    col_suministro = c
                    break

            if not col_suministro:

                st.error(
                    "❌ No existe columna suministro"
                )

                st.stop()

            suministros = (
                df_actual[col_suministro]
                .astype(str)
                .unique()
            )

            # =================================================
            # DETECTAR RUTAS
            # =================================================

            if modo == "POR RUTA":

                rutas_detectadas = [codigo]

            else:

                rutas_detectadas = []

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

                rutas_detectadas = sorted(
                    list(set(rutas_detectadas))
                )

            # =================================================
            # HISTÓRICOS
            # =================================================

            dfs_hist = []

            total_descargas = (
                len(rutas_detectadas)
                * len(periodos_seleccionados)
            )

            contador = 0

            progress = st.progress(0)

            estado = st.empty()

            for ruta_hist in rutas_detectadas:

                for periodo in periodos_seleccionados:

                    estado.write(
                        f"📥 Ruta {ruta_hist} "
                        f"| {periodo}"
                    )

                    if modo == "POR SUMINISTROS":

                        url_hist = (

                            f"http://sigof.distriluz.com.pe/"
                            f"plus/Reportes/"
                            f"ajax_ordenes_historico_xls/"
                            f"U,S/{hoy}/{hoy}/0/0/0/0/"
                            f"{suministros_join}"
                            f"/0/0/0/0/0/9/{periodo}"

                        )

                    else:

                        url_hist = (

                            f"http://sigof.distriluz.com.pe/"
                            f"plus/Reportes/"
                            f"ajax_ordenes_historico_xls/"
                            f"U/{hoy}/{hoy}/0/0/0/"
                            f"{ruta_hist}"
                            f"/0/0/0/0/0/0/9/{periodo}"

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

                                df_temp[
                                    "periodo_historico"
                                ] = periodo

                                dfs_hist.append(
                                    df_temp
                                )

                    except:
                        pass

                    contador += 1

                    porcentaje = (
                        contador
                        / total_descargas
                    )

                    progress.progress(
                        min(porcentaje, 1.0)
                    )

            if not dfs_hist:

                st.error(
                    "❌ No existen históricos"
                )

                st.stop()

            fusionado = pd.concat(
                dfs_hist,
                ignore_index=True
            )

            # =================================================
            # GPS
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

            centro_lat = fusionado[
                lat_col
            ].median()

            centro_lon = fusionado[
                lon_col
            ].median()

            # =================================================
            # VALIDACIÓN GIS
            # =================================================

            resultados = []

            grupos = fusionado.groupby(
                col_suministro
            )

            total_grupos = len(grupos)

            progress_gis = st.progress(0)

            for i, (
                suministro,
                grupo
            ) in enumerate(grupos):

                grupo = grupo.sort_values(
                    "periodo_historico"
                )

                puntos = grupo[
                    [lat_col, lon_col]
                ].values

                meses = len(
                    grupo[
                        "periodo_historico"
                    ].unique()
                )

                if meses == 1:

                    ultimo = grupo.iloc[-1]

                    lat_final = ultimo[
                        lat_col
                    ]

                    lon_final = ultimo[
                        lon_col
                    ]

                    estado_gps = (
                        "ULTIMO PERIODO"
                    )

                    dispersion = 0

                elif len(puntos) == 1:

                    lat_final = puntos[0][0]
                    lon_final = puntos[0][1]

                    estado_gps = "UNICO"

                    dispersion = 0

                else:

                    n = len(puntos)

                    matriz = np.zeros((n, n))

                    for x in range(n):

                        for y in range(
                            x + 1,
                            n
                        ):

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
                            np.argmin(
                                distancias
                            )
                        )

                        estado_gps = (
                            "REBOTADO"
                        )

                    else:

                        suma = matriz.sum(
                            axis=1
                        )

                        idx = int(
                            np.argmin(suma)
                        )

                        estado_gps = (
                            "VALIDADO"
                        )

                    lat_final = puntos[idx][0]
                    lon_final = puntos[idx][1]

                resultados.append({

                    col_suministro:
                    suministro,

                    "latitud_validada":
                    lat_final,

                    "longitud_validada":
                    lon_final,

                    "estado_gps":
                    estado_gps,

                    "dispersion_m":
                    round(
                        dispersion,
                        2
                    ),

                    "meses_historicos":
                    meses,

                    "google_maps":

                    f"https://www.google.com/maps?q="
                    f"{lat_final},{lon_final}"

                })

                progress_gis.progress(
                    (i + 1)
                    / total_grupos
                )

            # =================================================
            # FINAL
            # =================================================

            df_gps = pd.DataFrame(
                resultados
            )

            df_final = df_actual.merge(
                df_gps,
                on=col_suministro,
                how="left"
            )

            # =================================================
            # SESSION STATE
            # =================================================

            st.session_state[
                "df_final"
            ] = df_final

            st.session_state[
                "centro_lat"
            ] = centro_lat

            st.session_state[
                "centro_lon"
            ] = centro_lon

            st.session_state[
                "col_suministro"
            ] = col_suministro

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

            st.download_button(
                "📥 DESCARGAR EXCEL",
                data=excel_data,
                file_name=f"GIS_{modo}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        except Exception as e:

            st.error(
                f"Error general: {e}"
            )

# =========================================================
# MAPA PERSISTENTE
# =========================================================

if "df_final" in st.session_state:

    df_final = st.session_state["df_final"]

    centro_lat = st.session_state[
        "centro_lat"
    ]

    centro_lon = st.session_state[
        "centro_lon"
    ]

    col_suministro = st.session_state[
        "col_suministro"
    ]

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

        elif row["estado_gps"] in [
            "UNICO",
            "ULTIMO PERIODO"
        ]:
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

    mapa_html = mapa._repr_html_()

    components.html(
        mapa_html,
        height=850,
        scrolling=True
    )