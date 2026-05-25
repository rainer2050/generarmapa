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

# =========================================================
# CONFIG
# =========================================================

LOGIN_URL = "http://sigof.distriluz.com.pe/plus/usuario/login"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": LOGIN_URL,
}

# =========================================================
# FUNCIONES
# =========================================================

def haversine(lat1, lon1, lat2, lon2):

    R = 6371000

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = (
        sin(dlat / 2) ** 2
        +
        cos(radians(lat1))
        *
        cos(radians(lat2))
        *
        sin(dlon / 2) ** 2
    )

    return 2 * R * atan2(
        sqrt(a),
        sqrt(1 - a)
    )

# =========================================================
# LOGIN
# =========================================================

usuario = st.text_input(
    "Usuario SIGOF"
)

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

        match = re.search(
            r"var DEFECTO_IDUUNN\s*=\s*'(\d+)';",
            r.text
        )

        defecto_iduunn = (
            match.group(1)
            if match
            else "0"
        )

        st.session_state["session"] = session
        st.session_state["logueado"] = True
        st.session_state["defecto_iduunn"] = defecto_iduunn

        st.success(
            f"✅ Sesión iniciada "
            f"Unidad {defecto_iduunn}"
        )

    except Exception as e:

        st.error(str(e))

# =========================================================
# APP
# =========================================================

if st.session_state.get("logueado"):

    st.subheader("⚙️ CONFIGURACIÓN")

    # =====================================================
    # RUTA
    # =====================================================

    ruta = st.text_input(
        "Ingrese ruta",
        placeholder="Ejemplo: 46516"
    )

    # =====================================================
    # TIPO MAPA
    # =====================================================

    tipo_mapa = st.radio(
        "Tipo de mapa",
        [
            "SOLO PENDIENTES",
            "TODA LA RUTA"
        ]
    )

    # =====================================================
    # PERIODOS
    # =====================================================

    actual = datetime.now()

    mes_1 = (
        actual
        - relativedelta(months=1)
    ).strftime("%Y%m")

    mes_2 = (
        actual
        - relativedelta(months=2)
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

    while (
        anio > 2024
        or (
            anio == 2024
            and mes >= 9
        )
    ):

        periodos.append(
            f"{anio}{mes:02d}"
        )

        mes -= 1

        if mes == 0:

            mes = 12
            anio -= 1

    periodos_seleccionados = st.multiselect(
        "Períodos históricos",
        periodos,
        default=default_periodos
    )

    # =====================================================
    # BOTÓN
    # =====================================================

    procesar = st.button(
        "🛰️ PROCESAR GIS"
    )

    # =====================================================
    # PROCESAR
    # =====================================================

    if procesar:

        try:

            session = st.session_state[
                "session"
            ]

            hoy = datetime.now().strftime(
                "%Y-%m-%d"
            )

            # =================================================
            # URL BASE
            # =================================================

            if tipo_mapa == "SOLO PENDIENTES":

                url_base = (
                    f"http://sigof.distriluz.com.pe/"
                    f"plus/Reportes/"
                    f"ajax_ordenes_historico_xls/"
                    f"U/{hoy}/{hoy}/0/0/0/"
                    f"{ruta}/0/0/0/0/"
                    f"LSC/0/9/0"
                )

            else:

                url_base = (
                    f"http://sigof.distriluz.com.pe/"
                    f"plus/Reportes/"
                    f"ajax_ordenes_historico_xls/"
                    f"U/{hoy}/{hoy}/0/0/0/"
                    f"{ruta}/0/0/0/0/"
                    f"0/0/9/0"
                )

            r = session.get(
                url_base,
                headers=HEADERS,
                timeout=180
            )

            if (
                r.status_code != 200
                or r.content[:2] != b"PK"
            ):

                st.error(
                    "❌ Error descargando"
                )

                st.stop()

            df_base = pd.read_excel(
                BytesIO(r.content)
            )

            st.success(
                f"✅ Registros base: "
                f"{len(df_base):,}"
            )

            # =================================================
            # DETECTAR SUMINISTRO
            # =================================================

            col_suministro = None

            for c in df_base.columns:

                if "suministro" in str(c).lower():

                    col_suministro = c
                    break

            if not col_suministro:

                st.error(
                    "❌ No existe suministro"
                )

                st.stop()

            suministros = df_base[
                col_suministro
            ].astype(str).unique()

            # =================================================
            # DESCARGAR HISTÓRICOS
            # =================================================

            dfs_hist = []

            total = len(
                periodos_seleccionados
            )

            progress = st.progress(0)

            estado = st.empty()

            for i, periodo in enumerate(
                periodos_seleccionados
            ):

                estado.text(
                    f"Procesando "
                    f"{i+1}/{total}"
                )

                url_hist = (
                    f"http://sigof.distriluz.com.pe/"
                    f"plus/Reportes/"
                    f"ajax_ordenes_historico_xls/"
                    f"U/{hoy}/{hoy}/0/0/0/"
                    f"{ruta}/0/0/0/0/"
                    f"0/0/9/{periodo}"
                )

                rh = session.get(
                    url_hist,
                    headers=HEADERS,
                    timeout=180
                )

                if (
                    rh.status_code == 200
                    and rh.content[:2] == b"PK"
                ):

                    df_temp = pd.read_excel(
                        BytesIO(rh.content)
                    )

                    df_temp = df_temp[
                        df_temp[
                            col_suministro
                        ].astype(str).isin(
                            suministros
                        )
                    ]

                    df_temp[
                        "periodo_historico"
                    ] = periodo

                    dfs_hist.append(df_temp)

                progress.progress(
                    (i + 1) / total
                )

            estado.empty()
            progress.empty()

            if not dfs_hist:

                st.error(
                    "❌ Sin históricos"
                )

                st.stop()

            # =================================================
            # FUSIÓN
            # =================================================

            fusionado = pd.concat(
                dfs_hist,
                ignore_index=True
            )

            # =================================================
            # COLUMNAS GPS
            # =================================================

            lat_col = None
            lon_col = None

            for c in fusionado.columns:

                cl = str(c).lower()

                if "lat" in cl:
                    lat_col = c

                if "lon" in cl:
                    lon_col = c

            if not lat_col or not lon_col:

                st.error(
                    "❌ Sin columnas GPS"
                )

                st.stop()

            fusionado[lat_col] = pd.to_numeric(
                fusionado[lat_col],
                errors="coerce"
            )

            fusionado[lon_col] = pd.to_numeric(
                fusionado[lon_col],
                errors="coerce"
            )

            fusionado = fusionado[
                (
                    fusionado[lat_col] != 0
                )
                &
                (
                    fusionado[lon_col] != 0
                )
            ]

            # =================================================
            # CENTRO
            # =================================================

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

                puntos = grupo[
                    [lat_col, lon_col]
                ].values

                meses = len(
                    grupo[
                        "periodo_historico"
                    ].unique()
                )

                if len(puntos) == 1:

                    lat_final = puntos[0][0]
                    lon_final = puntos[0][1]

                    estado_gps = "UNICO"

                    dispersion = 0

                else:

                    n = len(puntos)

                    matriz = np.zeros(
                        (n, n)
                    )

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

                        distancias = []

                        for pt in puntos:

                            distancias.append(
                                haversine(
                                    pt[0],
                                    pt[1],
                                    centro_lat,
                                    centro_lon
                                )
                            )

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
                            np.argmin(
                                suma
                            )
                        )

                        estado_gps = "VALIDADO"

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
                    (
                        "https://www.google.com/maps?q="
                        f"{lat_final},{lon_final}"
                    )
                })

                progress_gis.progress(
                    (i + 1)
                    / total_grupos
                )

            progress_gis.empty()

            # =================================================
            # RESULTADO FINAL
            # =================================================

            df_gps = pd.DataFrame(
                resultados
            )

            df_final = df_base.merge(
                df_gps,
                on=col_suministro,
                how="left"
            )

            # =================================================
            # EXPORTAR
            # =================================================

            salida = (
                f"GIS_{ruta}.xlsx"
            )

            with pd.ExcelWriter(
                salida,
                engine="xlsxwriter"
            ) as writer:

                df_final.to_excel(
                    writer,
                    index=False,
                    sheet_name="GIS"
                )

            # =================================================
            # GUARDAR EN SESSION
            # =================================================

            st.session_state[
                "df_final"
            ] = df_final

            st.session_state[
                "salida"
            ] = salida

            st.success(
                "✅ GIS generado correctamente"
            )

        except Exception as e:

            st.error(str(e))

# =========================================================
# MOSTRAR RESULTADOS
# =========================================================

if "df_final" in st.session_state:

    df_final = st.session_state[
        "df_final"
    ]

    salida = st.session_state[
        "salida"
    ]

    # =====================================================
    # DESCARGA
    # =====================================================

    with open(
        salida,
        "rb"
    ) as f:

        st.download_button(
            "📥 DESCARGAR EXCEL FINAL",
            f,
            file_name=salida,
            mime=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            )
        )

    # =====================================================
    # MAPA
    # =====================================================

    st.subheader("🗺️ MAPA GIS")

    df_mapa = df_final.dropna(
        subset=[
            "latitud_validada",
            "longitud_validada"
        ]
    )

    if len(df_mapa) > 0:

        centro_lat = df_mapa[
            "latitud_validada"
        ].median()

        centro_lon = df_mapa[
            "longitud_validada"
        ].median()

        mapa = folium.Map(
            location=[
                centro_lat,
                centro_lon
            ],
            zoom_start=15
        )

        for _, row in df_mapa.iterrows():

            color = "green"

            if row["estado_gps"] == "REBOTADO":
                color = "red"

            elif row["estado_gps"] == "UNICO":
                color = "blue"

            popup = (
                f"<b>Suministro:</b> "
                f"{row.iloc[3]}<br>"
                f"<b>Estado:</b> "
                f"{row['estado_gps']}<br>"
                f"<b>Dispersión:</b> "
                f"{row['dispersion_m']} m"
            )

            folium.CircleMarker(
                location=[
                    row["latitud_validada"],
                    row["longitud_validada"]
                ],
                radius=5,
                popup=popup,
                color=color,
                fill=True,
                fill_opacity=0.8
            ).add_to(mapa)

        st_folium(
            mapa,
            width=None,
            height=700,
            returned_objects=[]
        )

    st.dataframe(
        df_final,
        use_container_width=True
    )