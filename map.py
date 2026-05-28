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
# SESSION
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
# PANEL
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
    # LECTURISTA
    # =====================================================

    tipo_lecturista = None

    if modo == "POR LECTURISTA":

        tipo_lecturista = st.radio(
            "Filtro lecturista",
            [
                "TODOS",
                "PENDIENTES",
                "PENDIENTES + RELECTURAS"
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
                            "id": str(
                                u["IdProveedorPersonal"]
                            )
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

            st.error(
                f"Error lecturistas: {e}"
            )

            st.stop()

    # =====================================================
    # SUMINISTROS
    # =====================================================

    else:

        texto_suministros = st.text_area(
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
    # PROCESAR
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

                url_actual = (
                    f"http://sigof.distriluz.com.pe/"
                    f"plus/Reportes/"
                    f"ajax_ordenes_historico_xls/"
                    f"U/{hoy}/{hoy}/0/0/0/"
                    f"{codigo}/0/0/0/0/0/0/9/0"
                )

                r = session.get(
                    url_actual,
                    headers=HEADERS,
                    timeout=180
                )

                df_actual = pd.read_excel(
                    BytesIO(r.content)
                )

            elif modo == "POR LECTURISTA":

                # ============================================
                # TODOS
                # ============================================

                if tipo_lecturista == "TODOS":

                    url_actual = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/"
                        f"ajax_ordenes_historico_xls/"
                        f"U,L/{hoy}/{hoy}/0/0/0/0/0/"
                        f"{codigo}/0/0/0/0/9/0"
                    )

                    r = session.get(
                        url_actual,
                        headers=HEADERS,
                        timeout=180
                    )

                    df_actual = pd.read_excel(
                        BytesIO(r.content)
                    )

                # ============================================
                # PENDIENTES
                # ============================================

                elif tipo_lecturista == "PENDIENTES":

                    url_actual = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/"
                        f"ajax_ordenes_historico_xls/"
                        f"U,L/{hoy}/{hoy}/0/0/0/0/0/"
                        f"{codigo}/0/0/LSC/0/9/0"
                    )

                    r = session.get(
                        url_actual,
                        headers=HEADERS,
                        timeout=180
                    )

                    if r.content[:2] != b"PK":

                        st.warning(
                            "⚠️ No existen pendientes"
                        )

                        st.stop()

                    df_actual = pd.read_excel(
                        BytesIO(r.content)
                    )

                # ============================================
                # PENDIENTES + RELECTURAS
                # ============================================

                else:

                    # ==========================
                    # LSC
                    # ==========================

                    url_lsc = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/"
                        f"ajax_ordenes_historico_xls/"
                        f"U,L/{hoy}/{hoy}/0/0/0/0/0/"
                        f"{codigo}/0/0/LSC/0/9/0"
                    )

                    r_lsc = session.get(
                        url_lsc,
                        headers=HEADERS,
                        timeout=180
                    )

                    if (
                        r_lsc.status_code == 200
                        and
                        r_lsc.content[:2] == b"PK"
                    ):

                        df_lsc = pd.read_excel(
                            BytesIO(r_lsc.content)
                        )

                    else:

                        df_lsc = pd.DataFrame()

                    # ==========================
                    # REL
                    # ==========================

                    url_rel = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/"
                        f"ajax_ordenes_historico_xls/"
                        f"U,L/{hoy}/{hoy}/0/0/0/0/0/"
                        f"{codigo}/0/0/REL/0/9/0"
                    )

                    r_rel = session.get(
                        url_rel,
                        headers=HEADERS,
                        timeout=180
                    )

                    if (
                        r_rel.status_code == 200
                        and
                        r_rel.content[:2] == b"PK"
                    ):

                        df_rel = pd.read_excel(
                            BytesIO(r_rel.content)
                        )

                    else:

                        df_rel = pd.DataFrame()

                    if (
                        df_lsc.empty
                        and
                        df_rel.empty
                    ):

                        st.warning(
                            "⚠️ No existen pendientes "
                            "ni relecturas"
                        )

                        st.stop()

                    df_actual = pd.concat(
                        [df_lsc, df_rel],
                        ignore_index=True
                    )

                    # ============================================
                    # FILTRO RESULTADO VACÍO
                    # ============================================

                    col_resultado = None

                    for c in df_actual.columns:

                        if (
                            str(c)
                            .strip()
                            .lower()
                            == "resultado"
                        ):

                            col_resultado = c
                            break

                    if col_resultado:

                        df_actual = df_actual[

                            (
                                df_actual[col_resultado]
                                .isna()
                            )

                            |

                            (
                                df_actual[col_resultado]
                                .astype(str)
                                .str.strip()
                                == ""
                            )
                        ]

                        st.info(
                            f"📋 Resultado vacío: "
                            f"{len(df_actual):,}"
                        )

                    if df_actual.empty:

                        st.warning(
                            "⚠️ No existen registros "
                            "pendientes reales"
                        )

                        st.stop()

            # =================================================
            # SUMINISTROS
            # =================================================

            else:

                lista_suministros = []

                if texto_suministros.strip():

                    lista_suministros.extend([
                        x.strip()
                        for x in texto_suministros.split(",")
                        if x.strip()
                    ])

                if archivo_excel:

                    df_excel = pd.read_excel(
                        archivo_excel
                    )

                    lista_excel = (
                        df_excel.iloc[:, 0]
                        .dropna()
                        .astype(str)
                        .tolist()
                    )

                    lista_suministros.extend(
                        lista_excel
                    )

                lista_suministros = list(
                    set(lista_suministros)
                )

                if not lista_suministros:

                    st.error(
                        "❌ No existen suministros"
                    )

                    st.stop()

                suministros_url = ", ".join(
                    lista_suministros
                )

                url_actual = (
                    f"http://sigof.distriluz.com.pe/"
                    f"plus/Reportes/"
                    f"ajax_ordenes_historico_xls/"
                    f"U,S/{hoy}/{hoy}/0/0/0/0/"
                    f"{suministros_url}"
                    f"/0/0/0/0/0/9/0"
                )

                r = session.get(
                    url_actual,
                    headers=HEADERS,
                    timeout=180
                )

                df_actual = pd.read_excel(
                    BytesIO(r.content)
                )

            # =================================================
            # VALIDAR
            # =================================================

            if df_actual.empty:

                st.warning(
                    "⚠️ No existen registros"
                )

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
            # RUTAS
            # =================================================

            rutas_detectadas = []

            if modo == "POR RUTA":

                rutas_detectadas = [codigo]

            else:

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

            for ruta_hist in rutas_detectadas:

                for periodo in periodos_seleccionados:

                    url_hist = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/"
                        f"ajax_ordenes_historico_xls/"
                        f"U/{hoy}/{hoy}/0/0/0/"
                        f"{ruta_hist}/0/0/0/0/0/0/9/"
                        f"{periodo}"
                    )

                    try:

                        rh = session.get(
                            url_hist,
                            headers=HEADERS,
                            timeout=180
                        )

                        if (
                            rh.status_code != 200
                            or
                            rh.content[:2] != b"PK"
                        ):

                            contador += 1

                            continue

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

            # =================================================
            # SI NO HAY HISTÓRICOS
            # =================================================

            if not dfs_hist:

                st.warning(
                    "⚠️ No existen históricos"
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

            centro_lat = fusionado[
                lat_col
            ].median()

            centro_lon = fusionado[
                lon_col
            ].median()

            # =================================================
            # GIS
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
                    grupo["periodo_historico"]
                    .unique()
                )

                # ============================================
                # SOLO UN MES
                # ============================================

                if meses == 1:

                    lat_final = puntos[-1][0]
                    lon_final = puntos[-1][1]

                    estado_gps = "ULTIMO_PERIODO"

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

                        estado_gps = "REBOTADO"

                    else:

                        suma = matriz.sum(
                            axis=1
                        )

                        idx = int(
                            np.argmin(suma)
                        )

                        estado_gps = "VALIDADO"

                    lat_final = puntos[idx][0]
                    lon_final = puntos[idx][1]

                resultados.append({

                    col_suministro: suministro,

                    "latitud_validada":
                    lat_final,

                    "longitud_validada":
                    lon_final,

                    "estado_gps":
                    estado_gps,

                    "dispersion_m":
                    round(dispersion, 2),

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

            st.session_state[
                "excel_data"
            ] = excel_data

            st.session_state[
                "nombre_excel"
            ] = f"GIS_{modo}.xlsx"

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

            plugins.Fullscreen().add_to(
                mapa
            )

            folium.TileLayer(
                "OpenStreetMap",
                name="Mapa"
            ).add_to(mapa)

            folium.TileLayer(
                tiles=(
                    "https://mt1.google.com/"
                    "vt/lyrs=s&x={x}&y={y}&z={z}"
                ),
                attr="Google",
                name="Satélite"
            ).add_to(mapa)

            cluster = MarkerCluster(
                disableClusteringAtZoom=12,
                showCoverageOnHover=False
            ).add_to(mapa)

            for _, row in df_mapa.iterrows():

                color_icono = "green"

                if (
                    row["estado_gps"]
                    == "REBOTADO"
                ):

                    color_icono = "red"

                elif (
                    row["estado_gps"]
                    == "ULTIMO_PERIODO"
                ):

                    color_icono = "blue"

                popup_html = (
                    f"<b>Suministro:</b> "
                    f"{row[col_suministro]}<br>"
                    f"<b>Estado:</b> "
                    f"{row['estado_gps']}<br>"
                    f"<b>Dispersión:</b> "
                    f"{row['dispersion_m']} m<br>"
                    f"<a href='"
                    f"{row['google_maps']}' "
                    f"target='_blank'>"
                    f"🌍 Abrir Maps</a>"
                )

                folium.Marker(
                    location=[
                        row["latitud_validada"],
                        row["longitud_validada"]
                    ],
                    popup=popup_html,
                    icon=folium.Icon(
                        color=color_icono
                    )
                ).add_to(cluster)

            folium.LayerControl().add_to(
                mapa
            )

            mapa_html = mapa._repr_html_()

            st.session_state[
                "mapa_html"
            ] = mapa_html

        except Exception as e:

            st.error(
                f"Error general: {e}"
            )

    # =====================================================
    # DESCARGA
    # =====================================================

    if st.session_state["excel_data"]:

        st.download_button(
            "📥 DESCARGAR EXCEL",
            data=st.session_state[
                "excel_data"
            ],
            file_name=st.session_state[
                "nombre_excel"
            ],
            mime=(
                "application/"
                "vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            )
        )

    # =====================================================
    # MAPA PERSISTENTE
    # =====================================================

    if st.session_state["mapa_html"]:

        components.html(
            st.session_state["mapa_html"],
            height=850,
            scrolling=True
        )