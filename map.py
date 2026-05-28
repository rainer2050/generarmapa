# =========================================================
# IMPORTS
# =========================================================

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
# CONFIG
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
                st.error("❌ Usuario o contraseña incorrectos")
                st.stop()

            st.success("✅ Sesión iniciada correctamente")

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

    tipo_ruta = "TODOS"
    tipo_lecturista = "TODOS"

    # =====================================================
    # POR RUTA
    # =====================================================

    if modo == "POR RUTA":

        tipo_ruta = st.radio(
            "Filtro Ruta",
            [
                "TODOS",
                "PENDIENTES",
                "PENDIENTES + RELECTURAS"
            ]
        )

        codigo = st.text_input(
            "Código ruta",
            placeholder="Ejemplo: 68724"
        )

    # =====================================================
    # POR LECTURISTA
    # =====================================================

    elif modo == "POR LECTURISTA":

        tipo_lecturista = st.radio(
            "Filtro Lecturista",
            [
                "TODOS",
                "PENDIENTES",
                "PENDIENTES + RELECTURAS"
            ]
        )

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
            "O cargar Excel",
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
    # PROCESAR
    # =====================================================

    if st.button("🛰️ PROCESAR GIS"):

        try:

            hoy = datetime.now().strftime("%Y-%m-%d")

            # =================================================
            # URL ACTUAL
            # =================================================

            if modo == "POR RUTA":

                if tipo_ruta == "PENDIENTES":

                    url_actual = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/ajax_ordenes_historico_xls/"
                        f"U/{hoy}/{hoy}/0/0/0/"
                        f"{codigo}/0/0/0/0/LSC/0/9/0"
                    )

                elif tipo_ruta == "PENDIENTES + RELECTURAS":

                    url_pend = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/ajax_ordenes_historico_xls/"
                        f"U/{hoy}/{hoy}/0/0/0/"
                        f"{codigo}/0/0/0/0/LSC/0/9/0"
                    )

                    url_rel = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/ajax_ordenes_historico_xls/"
                        f"U/{hoy}/{hoy}/0/0/0/"
                        f"{codigo}/0/0/0/0/REL/0/9/0"
                    )

                else:

                    url_actual = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/ajax_ordenes_historico_xls/"
                        f"U/{hoy}/{hoy}/0/0/0/"
                        f"{codigo}/0/0/0/0/0/0/9/0"
                    )

            elif modo == "POR LECTURISTA":

                if tipo_lecturista == "PENDIENTES":

                    url_actual = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/ajax_ordenes_historico_xls/"
                        f"U,L/{hoy}/{hoy}/0/0/0/0/0/"
                        f"{codigo}/0/0/LSC/0/9/0"
                    )

                elif tipo_lecturista == "PENDIENTES + RELECTURAS":

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

                else:

                    url_actual = (
                        f"http://sigof.distriluz.com.pe/"
                        f"plus/Reportes/ajax_ordenes_historico_xls/"
                        f"U,L/{hoy}/{hoy}/0/0/0/0/0/"
                        f"{codigo}/0/0/0/0/9/0"
                    )

            else:

                lista_sum = []

                if suministros_manual.strip():

                    lista_sum.extend([
                        x.strip()
                        for x in suministros_manual.split(",")
                        if x.strip()
                    ])

                if archivo_excel:

                    df_excel = pd.read_excel(archivo_excel)

                    lista_sum.extend(
                        df_excel.iloc[:, 0]
                        .astype(str)
                        .tolist()
                    )

                lista_sum = list(set(lista_sum))

                if not lista_sum:
                    st.error("❌ No hay suministros")
                    st.stop()

                texto_sum = ",".join(lista_sum)

                url_actual = (
                    f"http://sigof.distriluz.com.pe/"
                    f"plus/Reportes/ajax_ordenes_historico_xls/"
                    f"U,S/{hoy}/{hoy}/0/0/0/0/"
                    f"{texto_sum}/0/0/0/0/0/9/0"
                )

            # =================================================
            # DESCARGA BASE
            # =================================================

            with st.spinner("📥 Descargando base..."):

                if (
                    (
                        modo == "POR LECTURISTA"
                        and
                        tipo_lecturista == "PENDIENTES + RELECTURAS"
                    )
                    or
                    (
                        modo == "POR RUTA"
                        and
                        tipo_ruta == "PENDIENTES + RELECTURAS"
                    )
                ):

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

                    dfs_union = []

                    if r1.content[:2] == b"PK":
                        dfs_union.append(
                            pd.read_excel(BytesIO(r1.content))
                        )

                    if r2.content[:2] == b"PK":
                        dfs_union.append(
                            pd.read_excel(BytesIO(r2.content))
                        )

                    if not dfs_union:
                        st.warning("⚠️ Sin pendientes")
                        st.stop()

                    df_actual = pd.concat(
                        dfs_union,
                        ignore_index=True
                    )

                    # =================================================
                    # FILTRO RESULTADO VACÍO
                    # =================================================

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

                    if r.content[:2] != b"PK":
                        st.warning("⚠️ Sin registros")
                        st.stop()

                    df_actual = pd.read_excel(
                        BytesIO(r.content)
                    )

            if df_actual.empty:
                st.warning("⚠️ No existen registros")
                st.stop()

            st.success(
                f"✅ Registros encontrados: {len(df_actual):,}"
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
                st.error("❌ No existe suministro")
                st.stop()

            suministros = (
                df_actual[col_suministro]
                .astype(str)
                .unique()
            )

            # =================================================
            # HISTÓRICO
            # =================================================

            dfs_hist = []

            usar_por_suministro = (
                len(suministros) <= 100
            )

            if usar_por_suministro:

                st.info(
                    "🔎 Histórico usando filtro POR SUMINISTRO"
                )

            else:

                st.info(
                    "🔎 Histórico usando filtro POR RUTA"
                )

            progress = st.progress(0)