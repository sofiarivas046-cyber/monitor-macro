import streamlit as st
import pandas as pd
import requests
from fredapi import Fred
import plotly.express as px
from datetime import datetime, timedelta

# Configuración de la página
st.set_page_config(
    page_title="Monitor Macroeconómico",
    page_icon="📈",
    layout="wide"
)

st.title("📊 Monitor Macroeconómico")
st.caption("Fuentes oficiales: Banco Central de Chile y Reserva Federal de EE.UU. (FRED)")

# ----------------------------------------------------
# 1. Función FRED (Estados Unidos)
# ----------------------------------------------------
@st.cache_data(ttl=1800)
def get_fred_data(api_key):
    fred = Fred(api_key=api_key)
    
    tasa_10y = fred.get_series('DGS10').dropna()
    tasa_fed = fred.get_series('FEDFUNDS').dropna()
    cpi = fred.get_series('CPIAUCSL').dropna()
    unrate = fred.get_series('UNRATE').dropna()
    
    cpi_yoy = ((cpi.iloc[-1] / cpi.iloc[-13]) - 1) * 100
    
    return {
        "us_10y": (tasa_10y.iloc[-1], tasa_10y.iloc[-2]),
        "fed_rate": (tasa_fed.iloc[-1], tasa_fed.iloc[-2]),
        "us_cpi": cpi_yoy,
        "us_unemp": unrate.iloc[-1],
        "df_10y": tasa_10y.tail(90).reset_index().rename(columns={"index": "Fecha", 0: "Tasa (%)"})
    }

# ----------------------------------------------------
# 2. Función Banco Central de Chile
# ----------------------------------------------------
@st.cache_data(ttl=1800)
def get_bcch_series(user, password, series_id, days_back=120):
    first_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
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
        
        # Validar si el BCCh entregó respuesta
        if "Series" in res and res["Series"] and "Obs" in res["Series"]:
            obs = res["Series"]["Obs"]
            if isinstance(obs, dict):
                obs = [obs]
            df = pd.DataFrame(obs)
            col_val = next((c for c in df.columns if c.lower() == 'value'), None)
            if col_val:
                df['value'] = pd.to_numeric(df[col_val].astype(str).str.replace(',', '.'), errors='coerce')
                return df.dropna(subset=['value']).reset_index(drop=True)
                
        elif "SeriesInfos" in res and res["SeriesInfos"]:
            obs = res["SeriesInfos"][0].get("Obs", [])
            df = pd.DataFrame(obs)
            if 'value' in df.columns:
                df['value'] = pd.to_numeric(df['value'].astype(str).str.replace(',', '.'), errors='coerce')
                return df.dropna(subset=['value']).reset_index(drop=True)

        return None
    except Exception:
        return None

# ----------------------------------------------------
# 3. Lectura de Credenciales y Carga
# ----------------------------------------------------
fred_key = st.secrets.get("FRED_API_KEY", "")
bcch_user = st.secrets.get("BCCH_USER", "")
bcch_pass = st.secrets.get("BCCH_PASS", "")

if not fred_key or not bcch_user or not bcch_pass:
    st.error("⚠️ Faltan configurar las credenciales en Streamlit Secrets.")
    st.stop()

with st.spinner("Actualizando variables macroeconómicas..."):
    # Carga FRED
    data_us = get_fred_data(fred_key)
    
    # Códigos de series oficiales del Banco Central de Chile
    df_dolar = get_bcch_series(bcch_user, bcch_pass, "F073.TCO.PRE.Z.D", days_back=60)
    df_tpm = get_bcch_series(bcch_user, bcch_pass, "F022.TPM.TIN.D001.NO.Z.D", days_back=60)
    df_cobre = get_bcch_series(bcch_user, bcch_pass, "F019.PPB.PRE.40.M", days_back=180)
    df_ipc = get_bcch_series(bcch_user, bcch_pass, "F074.IPC.VAR.Z.Z.C.M", days_back=180)

# ----------------------------------------------------
# 4. Sección Chile
# ----------------------------------------------------
st.subheader("🇨🇱 Indicadores Chile")
c1, c2, c3, c4 = st.columns(4)

with c1:
    if df_dolar is not None and len(df_dolar) >= 2:
        val_act = df_dolar['value'].iloc[-1]
        val_ant = df_dolar['value'].iloc[-2]
        st.metric("Dólar Observado (USD/CLP)", f"${val_act:,.2f}", delta=f"{val_act - val_ant:+.2f}")
    elif df_dolar is not None and len(df_dolar) == 1:
        st.metric("Dólar Observado (USD/CLP)", f"${df_dolar['value'].iloc[-1]:,.2f}")
    else:
        st.metric("Dólar Observado", "No disp.")

with c2:
    if df_cobre is not None and not df_cobre.empty:
        val_act = df_cobre['value'].iloc[-1]
        st.metric("Cobre BML (USD/lb)", f"${val_act:.2f}")
    else:
        st.metric("Cobre BML", "No disp.")

with c3:
    if df_tpm is not None and not df_tpm.empty:
        st.metric("TPM (Tasa Política Monetaria)", f"{df_tpm['value'].iloc[-1]:.2f}%")
    else:
        st.metric("TPM", "No disp.")

with c4:
    if df_ipc is not None and not df_ipc.empty:
        st.metric("IPC Mensual (Var. %)", f"{df_ipc['value'].iloc[-1]:.2f}%")
    else:
        st.metric("IPC", "No disp.")

st.divider()

# ----------------------------------------------------
# 5. Sección Estados Unidos
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
