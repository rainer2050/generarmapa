import streamlit as st
import requests
import pandas as pd
import numpy as np
import folium
import streamlit.components.v1 as components
from folium.plugins import MarkerCluster
from bs4 import BeautifulSoup
from io import BytesIO
from datetime import datetime
from dateutil.relativedelta import relativedelta
from math import radians, sin, cos, sqrt, atan2

# Configuración inicial
st.set_page_config(page_title="SIGOF GIS Avanzado", layout="wide")
LOGIN_URL = "http://sigof.distriluz.com.pe/plus/usuario/login"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": LOGIN_URL}

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1-a))

if "logueado" not in st.session_state: st.session_state["logueado"] = False

# --- LOGIN ---
if not st.session_state["logueado"]:
    usuario, password = st.text_input("Usuario"), st.text_input("Contraseña", type="password")
    if st.button("INICIAR SESIÓN"):
        session = requests.Session()
        r = session.post(LOGIN_URL, data={"data[Usuario][usuario]": usuario, "data[Usuario][pass]": password}, headers=HEADERS)
        if "Salir" in r.text:
            st.session_state["session"], st.session_state["logueado"] = session, True
            st.rerun()
        else: st.error("❌ Fallo de login")
    st.stop()

# --- PROCESAMIENTO ---
session = st.session_state["session"]
modo = st.radio("Modo", ["POR RUTA", "POR LECTURISTA"])
tipo = st.radio("Tipo", ["TOTAL", "PENDIENTES"])

codigo = st.text_input("Código") if modo == "POR RUTA" else None
if modo == "POR LECTURISTA":
    u_json = session.get("http://sigof.distriluz.com.pe/plus/ValidaImei/listarusuario", headers=HEADERS).json()
    lects = {u["NombreUsuario"]: str(u["IdProveedorPersonal"]) for u in u_json if u.get("Roles") and any(r["nombre"]=="Lecturista" for r in u["Roles"])}
    codigo = lects[st.selectbox("Lecturista", sorted(lects.keys()))]

periodos = [f"{datetime.now().year}{m:02d}" for m in range(datetime.now().month, 0, -1)]
p_sel = st.multiselect("Periodos", periodos, default=periodos[:2])

if st.button("🛰️ PROCESAR"):
    hoy = datetime.now().strftime("%Y-%m-%d")
    url_base = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/{'U' if modo=='POR RUTA' else 'U,L'}/{hoy}/{hoy}/0/0/0/{'0/0' if modo=='POR LECTURISTA' else ''}{codigo}/0/0/{'LSC' if tipo=='PENDIENTES' else '0'}/0/9/0"
    
    df = pd.read_excel(BytesIO(session.get(url_base, headers=HEADERS).content))
    col_sum = [c for c in df.columns if "suministro" in str(c).lower()][0]
    
    # Detección columna J (índice 9) con limpieza
    rutas = df.iloc[:, 9].dropna().astype(str).apply(lambda x: x.split(' - ')[0].strip()).unique()
    
    dfs = []
    for r in rutas:
        for p in p_sel:
            url_h = f"http://sigof.distriluz.com.pe/plus/Reportes/ajax_ordenes_historico_xls/U/{hoy}/{hoy}/0/0/0/{r}/0/0/0/0/0/0/9/{p}"
            rh = session.get(url_h, headers=HEADERS)
            if rh.status_code == 200:
                df_h = pd.read_excel(BytesIO(rh.content))
                df_h = df_h[df_h[col_sum].astype(str).isin(df[col_sum].astype(str))]
                if not df_h.empty: dfs.append(df_h)
    
    fusion = pd.concat(dfs, ignore_index=True)
    lat_c = [c for c in fusion.columns if "lat" in str(c).lower()][0]
    lon_c = [c for c in fusion.columns if "lon" in str(c).lower()][0]
    
    # Análisis
    res = []
    for s, g in fusion.groupby(col_sum):
        pts = g[[lat_c, lon_c]].values
        if len(pts) > 1:
            disp = max([haversine(pts[i,0], pts[i,1], pts[j,0], pts[j,1]) for i in range(len(pts)) for j in range(len(pts))])
            idx = int(np.argmin([haversine(p[0], p[1], pts[:,0].mean(), pts[:,1].mean()) for p in pts]))
            res.append({col_sum: s, "lat": pts[idx,0], "lon": pts[idx,1], "est": "REBOTADO" if disp > 500 else "VALIDADO"})
    
    # Mapa
    m = folium.Map(location=[fusion[lat_c].median(), fusion[lon_c].median()], zoom_start=14)
    for row in pd.DataFrame(res).itertuples():
        folium.Marker([row.lat, row.lon], icon=folium.Icon(color="red" if row.est=="REBOTADO" else "green")).add_to(m)
    
    components.html(m._repr_html_(), height=600)
    st.success("Análisis completado.")