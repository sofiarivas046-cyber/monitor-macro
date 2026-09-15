import streamlit as st
import pandas as pd
import requests
from fredapi import Fred
import plotly.express as px
from datetime import datetime, timedelta

# Configuración visual de la página
st.set_page_config(
    page_title="Monitor Macroeconómico",
    page_icon="📈",
    layout="wide"
)

st.title("📊 Monitor Macroeconómico")
st.caption("Fuentes oficiales: Banco Central de Chile y Reserva Federal de EE.UU. (FRED)")

# ----------------------------------------------------__
# 1. Conexión con FRED (EE.UU.)
# ----------------------------------------------------
@st.cache_data(ttl=3600)  # Guarda en caché por 1 hora para no saturar la API
def get_fred_data(api_key):
    fred = Fred(api_key=api_key)
    
    # Series oficiales de FRED
    # DGS10: Bono US 10A, FEDFUNDS: Tasa Fed, CPIAUCSL: IPC US, UNRATE: Desempleo US
    tasa_10y = fred.get_series('DGS10')
    tasa_fed = fred.get_series('FEDFUNDS')
    cpi = fred.get_series('CPIAUCSL')
    unrate = fred.get_series('UNRATE')
    
    # Calcular variación anual de inflación US (últimos 12 meses)
    cpi_yoy = ((cpi.iloc[-1] / cpi.iloc[-13]) - 1) * 100
    
    return {
        "us_10y": (tasa_10y.dropna().iloc[-1], tasa_10y.dropna().iloc[-2]),
        "fed_rate": (tasa_fed.dropna().iloc[-1], tasa_fed.dropna().iloc[-2]),
        "us_cpi": cpi_yoy,
        "us_unemp": unrate.dropna().iloc[-1],
        "df_10y": tasa_10y.dropna().tail(90).reset_index().rename(columns={"index": "Fecha", 0: "Tasa (%)"})
    }


# ----------------------------------------------------
# 2. Conexión con Banco Central de Chile (Con Diagnóstico)
# ----------------------------------------------------
@st.cache_data(ttl=600)
def get_bcch_series(user, password, series_id):
    # Formato de fechas requerido por el BCCh (YYYY-MM-DD)
    first_date = (datetime.now() - timedelta(days=45)).strftime('%Y-%m-%d')
    last_date = datetime.now().strftime('%Y-%m-%d')
    
    url = (
        f"https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx"
        f"?user={user}&pass={password}"
        f"&firstdate={first_date}&lastdate={last_date}"
        f"&timeseries={series_id}&function=GetSeries"
    )
    
    try:
        response = requests.get(url, timeout=15)
        res = response.json()
        
        # Si el Banco Central devuelve un error (ej. credenciales inválidas)
        if res.get("Codigo") != 0 and "Series" not in res:
            st.sidebar.error(f"Error BCCh ({series_id}): {res.get('Descripcion', 'Error desconocido')}")
            return None
            
        if 'Series' in res and 'Obs' in res['Series']:
            obs = res['Series']['Obs']
            # Si solo hay una observación o varias
            if isinstance(obs, dict):
                obs = [obs]
            df = pd.DataFrame(obs)
            df['value'] = pd.to_numeric(df['value'].str.replace(',', '.'), errors='coerce')
            return df.dropna().reset_index(drop=True)
            
        return None
    except Exception as e:
        st.sidebar.error(f"Excepción al conectar con BCCh: {e}")
        return None
# ----------------------------------------------------
# 3. Carga y despliegue de datos
# ----------------------------------------------------
fred_key = st.secrets.get("FRED_API_KEY", "")
bcch_user = st.secrets.get("BCCH_USER", "")
bcch_pass = st.secrets.get("BCCH_PASS", "")

if not fred_key or not bcch_user or not bcch_pass:
    st.error("⚠️ Faltan configurar las credenciales en Streamlit Secrets (FRED_API_KEY, BCCH_USER, BCCH_PASS).")
    st.stop()

# Descarga de datos
with st.spinner("Actualizando variables macroeconómicas..."):
    # FRED
    data_us = get_fred_data(fred_key)
    
    # Banco Central:
    # F073.TCO.PRE.Z.D = Dólar Observado (USD/CLP)
    # F072.CLP.TPM.N.O.D = TPM Chile
    # F073.BML.PRE.Z.D = Cobre spot Londres (USD/lb)
    # F073.IPC.VAR.Z.Z.C = Variación IPC 12 meses
    df_dolar = get_bcch_series(bcch_user, bcch_pass, "F073.TCO.PRE.Z.D")
    df_tpm = get_bcch_series(bcch_user, bcch_pass, "F072.CLP.TPM.N.O.D")
    df_cobre = get_bcch_series(bcch_user, bcch_pass, "F073.BML.PRE.Z.D")
    df_ipc = get_bcch_series(bcch_user, bcch_pass, "F073.IPC.VAR.Z.Z.C")

# ----------------------------------------------------
# 4. Sección Chile
# ----------------------------------------------------
st.subheader("🇨🇱 Indicadores Chile")
c1, c2, c3, c4 = st.columns(4)

with c1:
    if df_dolar is not None and not df_dolar.empty:
        val_act = df_dolar['value'].iloc[-1]
        val_ant = df_dolar['value'].iloc[-2]
        st.metric("Dólar Observado (USD/CLP)", f"${val_act:,.2f}", delta=f"{val_act - val_ant:+.2f}")
    else:
        st.metric("Dólar Observado", "No disp.")

with c2:
    if df_cobre is not None and not df_cobre.empty:
        val_act = df_cobre['value'].iloc[-1]
        val_ant = df_cobre['value'].iloc[-2]
        st.metric("Cobre (USD/lb)", f"${val_act:.2f}", delta=f"{val_act - val_ant:+.2f}")
    else:
        st.metric("Cobre", "No disp.")

with c3:
    if df_tpm is not None and not df_tpm.empty:
        st.metric("TPM (Tasa Política Monetaria)", f"{df_tpm['value'].iloc[-1]:.2f}%")
    else:
        st.metric("TPM", "No disp.")

with c4:
    if df_ipc is not None and not df_ipc.empty:
        st.metric("Inflación IPC (12M)", f"{df_ipc['value'].iloc[-1]:.1f}%")
    else:
        st.metric("Inflación IPC", "No disp.")

st.divider()

# ----------------------------------------------------
# 5. Sección Estados Unidos y Global
# ----------------------------------------------------
st.subheader("🇺🇸 Indicadores Estados Unidos")
u1, u2, u3, u4 = st.columns(4)

with u1:
    val_act, val_ant = data_us["us_10y"]
    st.metric("Bono US Treasury 10A", f"{val_act:.2f}%", delta=f"{(val_act - val_ant):+.2f}%")

with u2:
    val_act, val_ant = data_us["fed_rate"]
    st.metric("Tasa Fed Funds", f"{val_act:.2f}%")

with u3:
    st.metric("Inflación CPI EE.UU. (12M)", f"{data_us['us_cpi']:.1f}%")

with u4:
    st.metric("Desempleo EE.UU.", f"{data_us['us_unemp']:.1f}%")

# ----------------------------------------------------
# 6. Gráfico de Tendencia
# ----------------------------------------------------
st.divider()
st.subheader("📉 Evolución Reciente: Bono Tesoro EE.UU. 10 Años")
fig = px.line(data_us["df_10y"], x="Fecha", y="Tasa (%)", markers=True)
fig.update_layout(height=350, margin=dict(l=20, r=20, t=20, b=20))
st.plotly_chart(fig, use_container_width=True)
