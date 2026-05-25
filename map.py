import streamlit as st
import requests
import pandas as pd
import numpy as np
import re

from bs4 import BeautifulSoup
from io import BytesIO

from datetime import datetime
from dateutil.relativedelta import relativedelta

from math import radians, sin, cos, sqrt, atan2

# =========================================================
# STREAMLIT
# =========================================================

st.set_page_config(
    page_title="SIGOF GIS",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.title("🛰️ SIGOF GIS RUTAS")

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

    return (
        2
        * R
        * atan2(
            sqrt(a),
            sqrt(1 - a)
        )
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

# =========================================================
# LOGIN BUTTON
# =========================================================

if st.button("🔐 INICIAR SESIÓN"):

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

        match = re.search(
            r"var DEFECTO_IDUUNN\s*=\s*'(\d+)';",
            r.text
        )

        if not match:

            st.error(
                "❌ Usuario o contraseña incorrectos"
            )

            st.stop()

        st.success(
            "✅ Sesión iniciada correctamente"
        )

        st.session_state["session"] = session
        st.session_state["logueado"] = True

    except Exception as e:

        st.error(str(e))

# =========================================================
# DESPUÉS LOGIN
# =========================================================

if st.session_state.get("logueado"):

    st.subheader("⚙️ Configuración GIS")

    # =====================================================
    # RUTA
    # =====================================================

    ruta = st.text_input(
        "Ruta",
        placeholder="Ejemplo: 46516"
    )

    # =====================================================
    # TIPO MAPA
    # =====================================================

    tipo_mapa = st.radio(
        "Tipo de mapa",
        [
            "TOTAL RUTA",
            "SOLO PENDIENTES"
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
    # PROCESAR
    # =====================================================

    if st.button("🛰️ PROCESAR GIS"):

        try:

            if not ruta:

                st.warning(
                    "⚠️ Ingrese ruta"
                )

                st.stop()

            if len(periodos_seleccionados) < 6:

                st.warning(
                    "⚠️ Seleccione mínimo 6 meses"
                )

                st.stop()

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

            st.info(
                "📥 Descargando base actual..."
            )

            st.code(url_base)

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
                    "❌ Error descargando base"
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
                    "❌ No existe columna suministro"
                )

                st.stop()

            suministros = df_base[
                col_suministro
            ].astype(str).unique()

            # =================================================
            # HISTÓRICOS
            # =================================================

            st.info(
                "📥 Descargando históricos..."
            )

            dfs_hist = []

            total = len(
                periodos_seleccionados
            )

            progress = st.progress(0)

            for i, periodo in enumerate(
                periodos_seleccionados
            ):

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

            if not dfs_hist:

                st.error(
                    "❌ No existen históricos"
                )

                st.stop()

            # =================================================
            # FUSIONAR
            # =================================================

            fusionado = pd.concat(
                dfs_hist,
                ignore_index=True
            )

            st.success(
                f"✅ Históricos fusionados: "
                f"{len(fusionado):,}"
            )

            # =================================================
            # DETECTAR GPS
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
                    "❌ No existen columnas GPS"
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

            fusionado = fusionado.dropna(
                subset=[lat_col, lon_col]
            )

            if fusionado.empty:

                st.error(
                    "❌ No existen coordenadas válidas"
                )

                st.stop()

            # =================================================
            # CENTRO GEOGRÁFICO
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

            st.info(
                "🛰️ Procesando triangulación..."
            )

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

                    dispersion = 0

                    estado = "UNICO"

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

                        estado = "REBOTADO"

                    else:

                        suma = matriz.sum(
                            axis=1
                        )

                        idx = int(
                            np.argmin(
                                suma
                            )
                        )

                        estado = "VALIDADO"

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
                    estado,

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

            nombre_tipo = (
                "PENDIENTES"
                if tipo_mapa == "SOLO PENDIENTES"
                else "TOTAL"
            )

            salida = (
                f"GIS_{nombre_tipo}_{ruta}.xlsx"
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

            st.success(
                "✅ Excel GIS generado correctamente"
            )

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

        except Exception as e:

            st.error(str(e))