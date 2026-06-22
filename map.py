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
# FUNCIÓN OPTIMIZADA DE DESCARGA
# =========================================================

def descargar_excel_seguro(url):
    session = st.session_state["session"]
    try:
        r = session.get(url, headers=HEADERS, timeout=180)
        if r.content[:2] == b"PK": 
            return r.content
    except:
        pass
    
    nueva_sesion = ejecutar_login_sigof(st.session_state["usr_backdoor"], st.session_state["psw_backdoor"])
    if nueva_sesion:
        st.session_state["session"] = nueva_sesion  
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
    usuario = st.text_input("Usuario SIGOF", value="", key="storage_user")
    password = st.text_input("Contraseña", type="password", value="", key="storage_pass")

    if st.button("INICIAR SESION"):
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

    modo = st.radio("Modo trabajo", ["POR RUTA", "POR LECTURISTA", "POR SUMINISTROS"])

    tipo_filtro = "TODOS"
    if modo in ["POR RUTA", "POR LECTURISTA"]:
        tipo_filtro = st.radio("Filtro de Estado", ["TODOS", "PENDIENTES", "PENDIENTES + RELECTURAS"])

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
                if not u.get("Roles"): continue
                for rol in u["Roles"]:
                    if rol.get("nombre") == "Lecturista":
                        lecturistas.append({"nombre": u["NombreUsuario"], "id": str(u["IdProveedorPersonal"])})
                        break

            dict_lect = {x["nombre"]: x["id"] for x in lecturistas}
            nombre_lect = st.selectbox("Seleccione Lecturista", sorted(dict_lect.keys()))
            codigo = dict_lect[nombre_lect]

        except Exception as e:
            st.error(f"Error al traer lecturistas: {e}.")
            st.stop()
    else:
        suministros_manual = st.text_area("Ingrese suministros separados por coma", height=120)
        archivo_excel = st.file_uploader("O cargar Excel", type=["xlsx"])

    # =====================================================
    # GENERACIÓN DE PERIODOS DISPONIBLES
    # =====================================================
    actual = datetime.now()
    mes_actual_str = actual.strftime("%Y%m")
    mes_anterior_str = (actual - relativedelta(months=1)).strftime("%Y%m")
    
    periodos_lista = []
    anio, mes = actual.year, actual.month
    while anio > 2024 or (anio == 2024 and mes >= 9):
        periodos_lista.append(f"{anio}{mes:02d}")
        mes -= 1
        if mes == 0: mes = 12; anio -= 1

    # =====================================================
    # FILTROS DE PERIODOS SEPARADOS (CORRECCIÓN CLAVE)
    # =====================================================
    st.markdown("---")
    col_p1, col_p2 = st.columns(2)
    
    with col_p1:
        # Define qué mes se va a consultar/procesar como base actual de trabajo
        periodo_base = st.selectbox("📅 Periodo Registro Base (Órdenes a trabajar)", periodos_lista, index=0)
    
    with col_p2:
        # Define qué meses se descargarán para cruzar y buscar coordenadas históricas
        periodos_historicos = st.multiselect("📚 Históricos para búsqueda GIS (Coordenadas)", periodos_lista, default=[mes_anterior_str])
    st.markdown("---")

    # =====================================================
    # PROCESAR ACCIÓN GIS
    # =====================================================
    if st.button("🛰️ PROCESAR GIS"):
        try:
            hoy = datetime.now().strftime("%Y-%m-%d")

            if modo == "POR RUTA":
                if tipo_filtro == "PENDIENTES":
                    url_actual = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{codigo}/0/0/0/0/LSC/0/9/{periodo_base}"
                elif tipo_filtro == "PENDIENTES + RELECTURAS":
                    url_pend = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{codigo}/0/0/0/0/LSC/0/9/{periodo_base}"
                    url_rel = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{codigo}/0/0/0/0/REL/0/9/{periodo_base}"
                else:
                    url_actual = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{codigo}/0/0/0/0/0/0/9/{periodo_base}"

            elif modo == "POR LECTURISTA":
                if tipo_filtro == "PENDIENTES":
                    url_actual = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U,L/{hoy}/{hoy}/0/0/0/0/0/{codigo}/0/0/LSC/0/9/{periodo_base}"
                elif tipo_filtro == "PENDIENTES + RELECTURAS":
                    url_pend = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U,L/{hoy}/{hoy}/0/0/0/0/0/{codigo}/0/0/LSC/0/9/{periodo_base}"
                    url_rel = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U,L/{hoy}/{hoy}/0/0/0/0/0/{codigo}/0/0/REL/0/9/{periodo_base}"
                else:
                    url_actual = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U,L/{hoy}/{hoy}/0/0/0/0/0/{codigo}/0/0/0/0/9/{periodo_base}"
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
                url_actual = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U,S/{hoy}/{hoy}/0/0/0/0/{texto_sum}/0/0/0/0/0/9/{periodo_base}"

            # =================================================
            # DESCARGA DE REGISTRO BASE
            # =================================================
            with st.spinner(f"📥 Descargando Registro Base del periodo {periodo_base}..."):
                if modo in ["POR RUTA", "POR LECTURISTA"] and tipo_filtro == "PENDIENTES + RELECTURAS":
                    bin_pend = descargar_excel_seguro(url_pend)
                    bin_rel = descargar_excel_seguro(url_rel)

                    dfs_union = []
                    if bin_pend: dfs_union.append(pd.read_excel(BytesIO(bin_pend)))
                    if bin_rel: dfs_union.append(pd.read_excel(BytesIO(bin_rel)))

                    if not dfs_union:
                        st.error(f"❌ El Registro Base para el periodo {periodo_base} no retornó datos o aún no está cargado.")
                        st.stop()

                    df_actual = pd.concat(dfs_union, ignore_index=True)
                else:
                    bin_actual = descargar_excel_seguro(url_actual)
                    if not bin_actual:
                        st.error(f"❌ El Registro Base para el periodo {periodo_base} no retornó datos o aún no está cargado.")
                        st.stop()
                    df_actual = pd.read_excel(BytesIO(bin_actual))

                # FILTRO FLEXIBLE DE COLUMNA RESULTADO
                col_resultado = next((col for col in df_actual.columns if str(col).lower() == "resultado"), None)
                if col_resultado:
                    df_pendientes = df_actual[df_actual[col_resultado].isna() | (df_actual[col_resultado].astype(str).str.strip() == "")]
                    if df_pendientes.empty:
                        st.warning(f"⚠️ El periodo Base {periodo_base} no contiene órdenes PENDIENTES (Columna 'Resultado' llena).")
                        if not st.checkbox("¿Deseas procesar todas las órdenes de este periodo (incluyendo completadas)?", value=True):
                            st.stop()
                    else:
                        df_actual = df_pendientes

            if df_actual.empty:
                st.warning("⚠️ No quedan registros en el DataFrame Base para ser procesados.")
                st.stop()

            st.success(f"✅ Registro Base cargado: {len(df_actual):,} filas (Periodo: {periodo_base})")

            col_suministro = next((c for c in df_actual.columns if "suministro" in str(c).lower()), None)
            if not col_suministro:
                st.error("❌ No se encontró la columna Suministro en el archivo base.")
                st.stop()

            suministros = df_actual[col_suministro].astype(str).unique()

            # =================================================
            # DESCARGAS HISTÓRICAS INDEPENDIENTES
            # =================================================
            dfs_hist = []
            usar_por_suministro = (len(suministros) <= 100)
            progress = st.progress(0)

            if usar_por_suministro:
                st.info(f"🔍 Buscando histórico por Suministros ({len(suministros)} elementos)")
                texto_sum = ",".join(suministros)
                total = len(periodos_historicos)

                for i, p_hist in enumerate(periodos_historicos):
                    url_hist = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U,S/{hoy}/{hoy}/0/0/0/0/{texto_sum}/0/0/0/0/0/9/{p_hist}"
                    bin_h = descargar_excel_seguro(url_hist)
                    if bin_h:
                        try:
                            df_temp = pd.read_excel(BytesIO(bin_h))
                            if not df_temp.empty and len(df_temp) > 0:
                                df_temp["periodo_historico"] = p_hist
                                dfs_hist.append(df_temp)
                        except:
                            pass
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
                                    if cod.isdigit(): rutas_detectadas.append(cod)
                            break
                elif modo == "POR RUTA":
                    rutas_detectadas = [codigo]

                st.info(f"🔍 Buscando histórico por Rutas ({len(rutas_detectadas)} detectadas)")
                total = len(rutas_detectadas) * len(periodos_historicos)
                contador = 0

                for ruta_hist in rutas_detectadas:
                    for p_hist in periodos_historicos:
                        url_hist = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{ruta_hist}/0/0/0/0/0/0/9/{p_hist}"
                        bin_h = descargar_excel_seguro(url_hist)
                        if bin_h:
                            try:
                                df_temp = pd.read_excel(BytesIO(bin_h))
                                df_temp = df_temp[df_temp[col_suministro].astype(str).isin(suministros)]
                                if not df_temp.empty and len(df_temp) > 0:
                                    df_temp["periodo_historico"] = p_hist
                                    dfs_hist.append(df_temp)
                            except:
                                pass
                        contador += 1
                        progress.progress(contador / total)

            if not dfs_hist:
                st.warning("⚠️ No se hallaron datos geográficos en los meses históricos seleccionados. Se procesará solo con la info base.")
                fusionado = df_actual.copy()
                fusionado["periodo_historico"] = periodo_base
            else:
                fusionado = pd.concat(dfs_hist, ignore_index=True)

            # Extraer Columnas Geográficas
            lat_col, lon_col = None, None
            for c in fusionado.columns:
                cl = str(c).lower()
                if "lat" in cl: lat_col = c
                if "lon" in cl: lon_col = c

            if not lat_col or not lon_col:
                st.error("❌ El archivo de SIGOF no contiene las columnas de Latitud/Longitud.")
                st.stop()

            fusionado[lat_col] = pd.to_numeric(fusionado[lat_col], errors="coerce")
            fusionado[lon_col] = pd.to_numeric(fusionado[lon_col], errors="coerce")
            fusionado = fusionado.dropna(subset=[lat_col, lon_col])
            fusionado = fusionado[(fusionado[lat_col] != 0) & (fusionado[lon_col] != 0)]

            # =================================================
            # ALGORITMO GIS MÍNIMA DISPERSIÓN
            # =================================================
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
                    "google_maps": f"https://www.google.com/maps?q={lat_final},{lon_final}"
                })
                progress_gis.progress((i + 1) / total_grupos)

            df_gps = pd.DataFrame(resultados)
            df_final = df_actual.merge(df_gps, on=col_suministro, how="left")

            # Botón Descarga Excel
            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df_final.to_excel(writer, index=False, sheet_name="GIS_PROCESADO")

            st.download_button(
                "📥 DESCARGAR EXCEL PROCESADO",
                data=output.getvalue(),
                file_name=f"RESULTADO_GIS_{periodo_base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # Renderizado de Mapa Folium
            st.subheader("🗺️ MAPA VISUALIZADOR GIS")
            df_mapa = df_final.dropna(subset=["latitud_validada", "longitud_validada"])

            if df_mapa.empty:
                st.warning("⚠️ No se encontraron coordenadas válidas asociadas a los suministros bases.")
                st.stop()

            centro_lat = df_mapa["latitud_validada"].median()
            centro_lon = df_mapa["longitud_validada"].median()

            mapa = folium.Map(location=[centro_lat, centro_lon], zoom_start=14, tiles=None)
            plugins.Fullscreen().add_to(mapa)

            folium.TileLayer("OpenStreetMap", name="Mapa Normal").add_to(mapa)
            folium.TileLayer(
                tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                attr="Google Satellite",
                name="Visión Satelital"
            ).add_to(mapa)

            cluster = MarkerCluster(disableClusteringAtZoom=13, showCoverageOnHover=False).add_to(mapa)

            for _, row in df_mapa.iterrows():
                popup_html = (
                    f"<b>Suministro:</b> {row[col_suministro]}<br>"
                    f"<b>Estado:</b> {row['estado_gps']}<br>"
                    f"<b>Dispersión Máx:</b> {row['dispersion_m']} metros<br>"
                    f"<a href='{row['google_maps']}' target='_blank'>🌍 Abrir en Google Maps</a>"
                )
                folium.Marker(
                    location=[row["latitud_validada"], row["longitud_validada"]],
                    popup=popup_html
                ).add_to(cluster)

            folium.LayerControl().add_to(mapa)
            components.html(mapa._repr_html_(), height=750, scrolling=True)

        except Exception as e:
            st.error(f"Ocurrió un error inesperado al procesar los datos: {e}")