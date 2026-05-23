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
# CONFIG STREAMLIT
# =========================================================

st.set_page_config(
    page_title="SIGOF GIS",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.title("🛰️ SIGOF GIS PENDIENTES")

# =========================================================
# CONFIG GENERAL
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
        placeholder="Ejemplo: 65453"
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

    if st.button("🛰️ PROCESAR PENDIENTES"):

        try:

            if not ruta:

                st.warning(
                    "⚠️ Ingrese una ruta"
                )

                st.stop()

            session = st.session_state[
                "session"
            ]

            hoy = datetime.now().strftime(
                "%Y-%m-%d"
            )

            # =================================================
            # DESCARGAR PENDIENTES
            # =================================================

            st.info(
                "📥 Descargando pendientes..."
            )

            url_pendientes = (
    f"http://sigof.distriluz.com.pe/"
    f"plus/Reportes/"
    f"ajax_ordenes_historico_xls/"
    f"U/{hoy}/{hoy}/0/0/0/"
    f"{ruta}/0/0/0/0/0/0/9/{periodos_seleccionados}"
)
            st.code(url_pendientes)

            r = session.get(
                url_pendientes,
                headers=HEADERS,
                timeout=180
            )

            if (
                r.status_code != 200
                or r.content[:2] != b"PK"
            ):

                st.error(
                    "❌ Error descargando pendientes"
                )

                st.stop()

            df_pend = pd.read_excel(
                BytesIO(r.content)
            )

            st.success(
                f"✅ Pendientes descargados: "
                f"{len(df_pend):,}"
            )

            # =================================================
            # DETECTAR SUMINISTRO
            # =================================================

            col_suministro = None

            for c in df_pend.columns:

                if "suministro" in str(c).lower():

                    col_suministro = c
                    break

            if not col_suministro:

                st.error(
                    "❌ No se encontró columna suministro"
                )

                st.stop()

            pendientes = df_pend[
                col_suministro
            ].astype(str).unique()

            # =================================================
            # HISTÓRICOS
            # =================================================

            st.info(
                "📥 Descargando históricos..."
            )

            dfs_hist = []

            total_periodos = len(
                periodos_seleccionados
            )

            progress_hist = st.progress(0)

            for i, periodo in enumerate(
                periodos_seleccionados
            ):

                url_hist = (
                    f"http://sigof.distriluz.com.pe/"
                    f"plus/Reportes/"
                    f"ajax_ordenes_historico_xls/"
                    f"U/{hoy}/{hoy}/0/0/0/"
                    f"{ruta}/0/0/0/"
                    f"0/0/9/{periodo}"
                )

                st.code(url_hist)

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
                            pendientes
                        )
                    ]

                    df_temp[
                        "periodo_historico"
                    ] = periodo

                    dfs_hist.append(df_temp)

                progress_hist.progress(
                    (i + 1)
                    / total_periodos
                )

            if not dfs_hist:

                st.error(
                    "❌ No se encontraron históricos"
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
            # DETECTAR LAT/LON
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
                    "❌ No se encontraron columnas GPS"
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
            # PROCESAMIENTO GIS
            # =================================================

            st.info(
                "🛰️ Procesando coordenadas..."
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

            df_final = df_pend.merge(
                df_gps,
                on=col_suministro,
                how="left"
            )

            # =================================================
            # EXPORTAR
            # =================================================

            salida = (
                f"pendientes_gis_{ruta}.xlsx"
            )

            with pd.ExcelWriter(
                salida,
                engine="xlsxwriter"
            ) as writer:

                df_final.to_excel(
                    writer,
                    index=False,
                    sheet_name="PENDIENTES_GIS"
                )

            st.success(
                "✅ Excel generado correctamente"
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