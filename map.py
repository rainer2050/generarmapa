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

ocultar_elementos_st = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stAppDeployButton {display: none !important;}
    </style>
    """
st.markdown(ocultar_elementos_st, unsafe_allow_html=True)

LOGIN_URL = "http://sigof.distriluz.com.pe/plus/usuario/login"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": LOGIN_URL,
}

st.title("🛰️ SIGOF GIS AVANZADO")

# =========================================================
# FUNCIÓN CONTROLADA DE LOGIN
# =========================================================

def ejecutar_login_sigof(usr, psw):
    """Ejecuta el inicio de sesión único y devuelve el objeto session."""
    try:
        session = requests.Session()
        login_page = session.get(LOGIN_URL, headers=HEADERS, timeout=60)
        soup = BeautifulSoup(login_page.text, "html.parser")
        csrf = soup.find("input", {"name": "_csrf_token"})
        credentials = {
            "data[Usuario][usuario]": usr,
            "data[Usuario][pass]": psw
        }
        if csrf:
            credentials["_csrf_token"] = csrf["value"]

        r = session.post(LOGIN_URL, data=credentials, headers=HEADERS, timeout=60)
        if "Salir" in r.text:
            return session
        return None
    except:
        return None

# =========================================================
# FUNCIÓN OPTIMIZADA DE DESCARGA (EVITA RE-LOGINS INNECESARIOS)
# =========================================================

def descargar_excel_seguro(url):
    """Descarga el Excel de forma segura. Si la sesión expiró, re-loguea UNA sola vez."""
    session = st.session_state["session"]
    try:
        r = session.get(url, headers=HEADERS, timeout=180)
        if r.content[:2] == b"PK": # Es un formato Excel válido (.xlsx comprimido)
            return r.content
    except:
        pass
    
    # Si llegó aquí, la sesión expiró o falló. Intentamos reconexión express UNA sola vez.
    nueva_sesion = ejecutar_login_sigof(st.session_state["usr_backdoor"], st.session_state["psw_backdoor"])
    if nueva_sesion:
        st.session_state["session"] = nueva_sesion  # Actualizamos la sesión global de la app
        try:
            r = nueva_sesion.get(url, headers=HEADERS, timeout=180)
            if r.content[:2] == b"PK":
                return r.content
        except:
            pass
    return None

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
# CONTROL DE SESIÓN GENERAL
# =========================================================

if "logueado" not in st.session_state:
    st.session_state["logueado"] = False

# =========================================================
# INTERFAZ DE LOGIN
# =========================================================

if not st.session_state["logueado"]:
    st.subheader("🔐 ACCESO SISTEMA SIGOF")
    
    # 💡 Consejo: Puedes escribir tus credenciales directamente en value="" para no teclearlas siempre
    usuario = st.text_input("Usuario SIGOF", value="", key="storage_user")
    password = st.text_input("Contraseña", type="password", value="", key="storage_pass")

    if st.button("INICIAR SESIÓN"):
        if usuario and password:
            with st.spinner("Conectando de forma segura con SIGOF..."):
                sesion_valida = ejecutar_login_sigof(usuario, password)
                
                if sesion_valida:
                    st.success("✅ Sesión iniciada correctamente")
                    st.session_state["session"] = sesion_valida
                    st.session_state["logueado"] = True
                    st.session_state["usr_backdoor"] = usuario
                    st.session_state["psw_backdoor"] = password
                    st.rerun()
                else:
                    st.error("❌ Usuario o contraseña incorrectos o error del servidor SIGOF.")
        else:
            st.warning("⚠️ Por favor rellene ambos campos para continuar.")

# =========================================================
# PANEL DE CONTROL PRINCIPAL
# =========================================================

if st.session_state["logueado"]:
    session = st.session_state["session"]
    st.subheader("⚙️ CONFIGURACIÓN GIS")

    modo = st.radio(
        "Modo trabajo",
        ["POR RUTA", "POR LECTURISTA", "POR SUMINISTROS"]
    )

    tipo_filtro = "TODOS"
    if modo in ["POR RUTA", "POR LECTURISTA"]:
        tipo_filtro = st.radio(
            "Filtro de Estado",
            ["TODOS", "PENDIENTES", "PENDIENTES + RELECTURAS"]
        )

    if modo == "POR RUTA":
        codigo = st.text_input("Código ruta", placeholder="Ejemplo: 68724")

    elif modo == "POR LECTURISTA":
        try:
            url_lect = "http://sigof.distriluz.com.pe/plus/ValidaImei/listarusuario"
            r_lect = session.get(url_lect, headers=HEADERS, timeout=120)
            
            if r_lect.status_code != 200 or not isinstance(r_lect.json(), list):
                nueva_s = ejecutar_login_sigof(st.session_state["usr_backdoor"], st.session_state["psw_backdoor"])
                if nueva_s:
                    st.session_state["session"] = nueva_s
                    session = nueva_s
                    r_lect = session.get(url_lect, headers=HEADERS, timeout=120)

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

            dict_lect = {x["nombre"]: x["id"] for x in lecturistas}
            nombre_lect = st.selectbox("Seleccione Lecturista", sorted(dict_lect.keys()))
            codigo = dict_lect[nombre_lect]

        except Exception as e:
            st.error(f"Error al traer lecturistas: {e}. Reintente presionando la pantalla.")
            st.stop()

    else:
        suministros_manual = st.text_area("Ingrese suministros separados por coma", height=120)
        archivo_excel = st.file_uploader("O cargar Excel", type=["xlsx"])

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
    # PROCESAR ACCIÓN GIS
    # =====================================================
    if st.button("🛰️ PROCESAR GIS"):
        try:
            hoy = datetime.now().strftime("%Y-%m-%d")

            if modo == "POR RUTA":
                if tipo_filtro == "PENDIENTES":
                    url_actual = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{codigo}/0/0/0/0/LSC/0/9/0"
                elif tipo_filtro == "PENDIENTES + RELECTURAS":
                    url_pend = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{codigo}/0/0/0/0/LSC/0/9/0"
                    url_rel = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{codigo}/0/0/0/0/REL/0/9/0"
                else:
                    url_actual = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{codigo}/0/0/0/0/0/0/9/0"

            elif modo == "POR LECTURISTA":
                if tipo_filtro == "PENDIENTES":
                    url_actual = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U,L/{hoy}/{hoy}/0/0/0/0/0/{codigo}/0/0/LSC/0/9/0"
                elif tipo_filtro == "PENDIENTES + RELECTURAS":
                    url_pend = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U,L/{hoy}/{hoy}/0/0/0/0/0/{codigo}/0/0/LSC/0/9/0"
                    url_rel = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U,L/{hoy}/{hoy}/0/0/0/0/0/{codigo}/0/0/REL/0/9/0"
                else:
                    url_actual = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U,L/{hoy}/{hoy}/0/0/0/0/0/{codigo}/0/0/0/0/9/0"
            else:
                lista_sum = []
                if suministros_manual.strip():
                    lista_sum.extend([x.strip() for x in suministros_manual.split(",") if x.strip()])
                if archivo_excel:
                    df_excel = pd.read_excel(archivo_excel)
                    lista_sum.extend(df_excel.iloc[:, 0].astype(str).tolist())
                
                lista_sum = list(set(lista_sum))
                if not lista_sum:
                    st.error("❌ No hay suministros válidos")
                    st.stop()

                texto_sum = ",".join(lista_sum)
                url_actual = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U,S/{hoy}/{hoy}/0/0/0/0/{texto_sum}/0/0/0/0/0/9/0"

            # =================================================
            # EJECUCIÓN DE DESCARGAS USANDO LA FUNCIÓN OPTIMIZADA
            # =================================================
            with st.spinner("📥 Descargando base..."):
                if modo in ["POR RUTA", "POR LECTURISTA"] and tipo_filtro == "PENDIENTES + RELECTURAS":
                    bin_pend = descargar_excel_seguro(url_pend)
                    bin_rel = descargar_excel_seguro(url_rel)

                    dfs_union = []
                    if bin_pend: dfs_union.append(pd.read_excel(BytesIO(bin_pend)))
                    if bin_rel: dfs_union.append(pd.read_excel(BytesIO(bin_rel)))

                    if not dfs_union:
                        st.warning("⚠️ Sin datos descargados. Verifique que existan órdenes asignadas.")
                        st.stop()

                    df_actual = pd.concat(dfs_union, ignore_index=True)

                    # FILTRO EXACTO SOLICITADO: COLUMNA U ('Resultado') EN BLANCO
                    col_resultado = None
                    for col in df_actual.columns:
                        if str(col).lower() == "resultado":
                            col_resultado = col
                            break

                    if col_resultado:
                        df_actual = df_actual[
                            df_actual[col_resultado].isna() | 
                            (df_actual[col_resultado].astype(str).str.strip() == "")
                        ]
                else:
                    bin_actual = descargar_excel_seguro(url_actual)
                    if not bin_actual:
                        st.error("❌ No se pudo descargar el archivo actual. Sesión inaccesible.")
                        st.stop()
                    df_actual = pd.read_excel(BytesIO(bin_actual))

            if df_actual.empty:
                st.warning("⚠️ No quedan registros tras limpiar la columna 'Resultado'.")
                st.stop()

            st.success(f"✅ Registros base cargados: {len(df_actual):,}")

            col_suministro = None
            for c in df_actual.columns:
                if "suministro" in str(c).lower():
                    col_suministro = c
                    break

            if not col_suministro:
                st.error("❌ No existe columna de suministro")
                st.stop()

            suministros = df_actual[col_suministro].astype(str).unique()

            # =================================================
            # DESCARGAS HISTÓRICAS OPTIMIZADAS (CON AUTO-RECONEXIÓN INTERNA)
            # =================================================
            dfs_hist = []
            usar_por_suministro = (len(suministros) <= 100)
            progress = st.progress(0)

            if usar_por_suministro:
                st.info(f"🔍 Método de descarga: **HISTÓRICO POR SUMINISTRO** ({len(suministros)} elementos)")
                texto_sum = ",".join(suministros)
                total = len(periodos_seleccionados)

                for i, periodo in enumerate(periodos_seleccionados):
                    url_hist = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U,S/{hoy}/{hoy}/0/0/0/0/{texto_sum}/0/0/0/0/0/9/{periodo}"
                    bin_h = descargar_excel_seguro(url_hist)
                    if bin_h:
                        df_temp = pd.read_excel(BytesIO(bin_h))
                        if not df_temp.empty:
                            df_temp["periodo_historico"] = periodo
                            dfs_hist.append(df_temp)
                    progress.progress((i + 1) / total)
            else:
                rutas_detectadas = []
                if modo == "POR LECTURISTA":
                    for c in df_actual.columns:
                        if "ruta" in str(c).lower():
                            rutas = df_actual[c].dropna().astype(str).unique()
                            for rt in rutas:
                                if "-" in rt:
                                    cod = rt.split("-")[0].strip()
                                    if cod.isdigit():
                                        rutas_detectadas.append(cod)
                            break
                elif modo == "POR RUTA":
                    rutas_detectadas = [codigo]

                st.info(f"🔍 Método de descarga: **HISTÓRICO POR RUTA** ({len(rutas_detectadas)} rutas mapeadas)")
                total = len(rutas_detectadas) * len(periodos_seleccionados)
                contador = 0

                for ruta_hist in rutas_detectadas:
                    for periodo in periodos_seleccionados:
                        url_hist = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{ruta_hist}/0/0/0/0/0/0/9/{periodo}"
                        bin_h = descargar_excel_seguro(url_hist)
                        if bin_h:
                            df_temp = pd.read_excel(BytesIO(bin_h))
                            df_temp = df_temp[df_temp[col_suministro].astype(str).isin(suministros)]
                            if not df_temp.empty:
                                df_temp["periodo_historico"] = periodo
                                dfs_hist.append(df_temp)
                        contador += 1
                        progress.progress(contador / total)

            if not dfs_hist:
                st.warning("⚠️ No se encontraron registros históricos válidos.")
                st.stop()

            fusionado = pd.concat(dfs_hist, ignore_index=True)

            # Procesar Coordenadas
            lat_col, lon_col = None, None
            for c in fusionado.columns:
                cl = str(c).lower()
                if "lat" in cl: lat_col = c
                if "lon" in cl: lon_col = c

            fusionado[lat_col] = pd.to_numeric(fusionado[lat_col], errors="coerce")
            fusionado[lon_col] = pd.to_numeric(fusionado[lon_col], errors="coerce")
            fusionado = fusionado.dropna(subset=[lat_col, lon_col])
            fusionado = fusionado[(fusionado[lat_col] != 0) & (fusionado[lon_col] != 0)]

            # Algoritmo Mínima Dispersión
            resultados = []
            grupos = fusionado.groupby(col_suministro)
            progress_gis = st.progress(0)
            total_grupos = len(grupos)

            for i, (suministro, grupo) in enumerate(grupos):
                grupo = grupo.sort_values("periodo_historico", ascending=False)
                puntos = grupo[[lat_col, lon_col]].values

                if len(puntos) == 1:
                    lat_final, lon_final = puntos[0][0], puntos[0][1]
                    estado_gps = "ULTIMO_PERIODO"
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
                    suma = matriz.sum(axis=1)
                    idx = int(np.argmin(suma))
                    lat_final, lon_final = puntos[idx][0], puntos[idx][1]
                    estado_gps = "VALIDADO"

                resultados.append({
                    col_suministro: suministro,
                    "latitud_validada": lat_final,
                    "longitud_validada": lon_final,
                    "estado_gps": estado_gps,
                    "dispersion_m": round(dispersion, 2),
                    "google_maps": f"http://maps.google.com/?q={lat_final},{lon_final}"
                })
                progress_gis.progress((i + 1) / total_grupos)

            df_gps = pd.DataFrame(resultados)
            df_final = df_actual.merge(df_gps, on=col_suministro, how="left")

            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df_final.to_excel(writer, index=False, sheet_name="GIS")

            st.download_button(
                "📥 DESCARGAR EXCEL",
                data=output.getvalue(),
                file_name=f"GIS_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # Mapa
            st.subheader("🗺️ MAPA GIS")
            df_mapa = df_final.dropna(subset=["latitud_validada", "longitud_validada"])

            if df_mapa.empty:
                st.warning("⚠️ No quedan coordenadas válidas para mostrar.")
                st.stop()

            centro_lat = df_mapa["latitud_validada"].median()
            centro_lon = df_mapa["longitud_validada"].median()

            mapa = folium.Map(location=[centro_lat, centro_lon], zoom_start=13, tiles=None)
            plugins.Fullscreen().add_to(mapa)

            folium.TileLayer("OpenStreetMap", name="Mapa").add_to(mapa)
            folium.TileLayer(
                tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                attr="Google",
                name="Satélite"
            ).add_to(mapa)

            cluster = MarkerCluster(disableClusteringAtZoom=12, showCoverageOnHover=False).add_to(mapa)

            for _, row in df_mapa.iterrows():
                popup_html = (
                    f"<b>Suministro:</b> {row[col_suministro]}<br>"
                    f"<b>Estado:</b> {row['estado_gps']}<br>"
                    f"<b>Dispersión:</b> {row['dispersion_m']} m<br>"
                    f"<a href='{row['google_maps']}' target='_blank'>🌍 Maps</a>"
                )
                folium.Marker(
                    location=[row["latitud_validada"], row["longitud_validada"]],
                    popup=popup_html
                ).add_to(cluster)

            folium.LayerControl().add_to(mapa)
            components.html(mapa._repr_html_(), height=850, scrolling=True)

        except Exception as e:
            st.error(f"Error general en el proceso: {e}")