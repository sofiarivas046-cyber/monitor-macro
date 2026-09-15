import streamlit as st
import pandas as pd
import requests
from fredapi import Fred
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Configuración visual de la página
st.set_page_config(
    page_title="Monitor Macroeconómico",
    page_icon="📈",
    layout="wide"
)

st.title("📊 Monitor Macroeconómico")
st.caption("Fuentes oficiales: Banco Central de Chile (BCCh) y Reserva Federal de EE.UU. (FRED)")

# Función auxiliar para formatear fechas limpias
def format_date_str(dt, is_monthly=False):
    if dt is None:
        return ""
    try:
        ts = pd.to_datetime(dt, dayfirst=True)
        if is_monthly:
            meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
            return f"📅 {meses[ts.month - 1]} {ts.year}"
        return f"📅 {ts.strftime('%d-%m-%Y')}"
    except Exception:
        return f"📅 {str(dt)[:10]}"

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
    
    fecha_corte = pd.to_datetime(datetime.now() - timedelta(days=365))
    
    # Serie Bono 10Y EE.UU. (último año)
    df_10y_us = tasa_10y[tasa_10y.index >= fecha_corte].reset_index().rename(columns={"index": "Fecha", 0: "US 10Y (%)"})
    df_10y_us["Fecha"] = pd.to_datetime(df_10y_us["Fecha"])
    
    # Serie Fed Funds (último año)
    df_fed = tasa_fed[tasa_fed.index >= fecha_corte].reset_index().rename(columns={"index": "Fecha", 0: "Fed Funds (%)"})
    df_fed["Fecha"] = pd.to_datetime(df_fed["Fecha"])
    
    return {
        "us_10y": (tasa_10y.iloc[-1], tasa_10y.iloc[-2], tasa_10y.index[-1]),
        "fed_rate": (tasa_fed.iloc[-1], tasa_fed.iloc[-2], tasa_fed.index[-1]),
        "us_cpi": (cpi_yoy, cpi.index[-1]),
        "us_unemp": (unrate.iloc[-1], unrate.index[-1]),
        "df_10y_us": df_10y_us,
        "df_fed": df_fed
    }

# ----------------------------------------------------
# 2. Función Banco Central de Chile
# ----------------------------------------------------
@st.cache_data(ttl=1800)
def get_bcch_series(user, password, series_id, days_back=180):
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
        
        obs = None
        if "Series" in res and res["Series"] and "Obs" in res["Series"]:
            obs = res["Series"]["Obs"]
        elif "SeriesInfos" in res and res["SeriesInfos"]:
            obs = res["SeriesInfos"][0].get("Obs", [])

        if obs:
            if isinstance(obs, dict):
                obs = [obs]
            df = pd.DataFrame(obs)
            col_val = next((c for c in df.columns if c.lower() == 'value'), None)
            if col_val:
                df['value'] = pd.to_numeric(df[col_val].astype(str).str.replace(',', '.'), errors='coerce')
                col_date = next((c for c in df.columns if 'date' in c.lower()), df.columns[0])
                df['date_label'] = df[col_date]
                df['Fecha'] = pd.to_datetime(df['date_label'], dayfirst=True, errors='coerce')
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
    # FRED
    data_us = get_fred_data(fred_key)
    
    # Banco Central de Chile (Aquí van las líneas con days_back=365)
    df_dolar = get_bcch_series(bcch_user, bcch_pass, "F073.TCO.PRE.Z.D", days_back=60)
    df_tpm = get_bcch_series(bcch_user, bcch_pass, "F022.TPM.TIN.D001.NO.Z.D", days_back=365)
    df_bono10_cl = get_bcch_series(bcch_user, bcch_pass, "F022.BCLP.TIS.AN10.NO.Z.D", days_back=365)
    df_cobre = get_bcch_series(bcch_user, bcch_pass, "F019.PPB.PRE.40.M", days_back=365)
    df_ipc_nivel = get_bcch_series(bcch_user, bcch_pass, "F074.IPC.IND.Z.EP09.C.M", days_back=365)
    df_ipc_var = get_bcch_series(bcch_user, bcch_pass, "F074.IPC.VAR.Z.Z.C.M", days_back=365)
    df_desempleo_cl = get_bcch_series(bcch_user, bcch_pass, "F049.DES.TAS.INE9.10.M", days_back=365)

# ----------------------------------------------------
# 4. Sección Chile
# ----------------------------------------------------
st.subheader("🇨🇱 Indicadores Chile")

has_tomorrow_dolar = False
if df_dolar is not None and len(df_dolar) >= 2:
    val_manana = df_dolar['value'].iloc[-1]
    fecha_manana = df_dolar['date_label'].iloc[-1]
    
    val_hoy = df_dolar['value'].iloc[-2]
    fecha_hoy = df_dolar['date_label'].iloc[-2]
    
    delta_manana = val_manana - val_hoy
    has_tomorrow_dolar = True
elif df_dolar is not None and len(df_dolar) == 1:
    val_hoy = df_dolar['value'].iloc[0]
    fecha_hoy = df_dolar['date_label'].iloc[0]

if has_tomorrow_dolar:
    c1, c1_next, c2, c3, c4, c5, c6 = st.columns(7)
else:
    c1, c2, c3, c4, c5, c6 = st.columns(6)

with c1:
    if df_dolar is not None and not df_dolar.empty:
        st.metric("USD/CLP (Rige Hoy)", f"${val_hoy:,.2f}")
        st.caption(format_date_str(fecha_hoy, is_monthly=False))
    else:
        st.metric("USD/CLP (Hoy)", "No disp.")

if has_tomorrow_dolar:
    with c1_next:
        st.metric("USD/CLP (Fijado Mañana)", f"${val_manana:,.2f}", delta=f"{delta_manana:+.2f}")
        st.caption(format_date_str(fecha_manana, is_monthly=False))

with c2:
    if df_cobre is not None and not df_cobre.empty:
        val_act = df_cobre['value'].iloc[-1]
        st.metric("Cobre BML (USD/lb)", f"${val_act:.2f}")
        st.caption(format_date_str(df_cobre['date_label'].iloc[-1], is_monthly=True))
    else:
        st.metric("Cobre BML", "No disp.")

with c3:
    if df_tpm is not None and not df_tpm.empty:
        if len(df_tpm) >= 2:
            val_tpm = df_tpm['value'].iloc[-1]
            fecha_tpm = df_tpm['date_label'].iloc[-2]
        else:
            val_tpm = df_tpm['value'].iloc[-1]
            fecha_tpm = df_tpm['date_label'].iloc[-1]
        st.metric("TPM Chile", f"{val_tpm:.2f}%")
        st.caption(format_date_str(fecha_tpm, is_monthly=False))
    else:
        st.metric("TPM", "No disp.")

with c4:
    if df_bono10_cl is not None and not df_bono10_cl.empty:
        val_act = df_bono10_cl['value'].iloc[-1]
        if len(df_bono10_cl) >= 2:
            val_ant = df_bono10_cl['value'].iloc[-2]
            st.metric("Bono BCCh 10A (BCP)", f"{val_act:.2f}%", delta=f"{(val_act - val_ant):+.2f}%")
        else:
            st.metric("Bono BCCh 10A (BCP)", f"{val_act:.2f}%")
        st.caption(format_date_str(df_bono10_cl['date_label'].iloc[-1], is_monthly=False))
    else:
        st.metric("Bono BCCh 10A", "No disp.")

with c5:
    if df_ipc_nivel is not None and not df_ipc_nivel.empty:
        nivel_act = df_ipc_nivel['value'].iloc[-1]
        if df_ipc_var is not None and not df_ipc_var.empty:
            var_mensual = df_ipc_var['value'].iloc[-1]
            st.metric("IPC (Nivel)", f"{nivel_act:,.2f} pts", delta=f"{var_mensual:+.2f}% m/m")
        else:
            st.metric("IPC (Nivel)", f"{nivel_act:,.2f} pts")
        st.caption(format_date_str(df_ipc_nivel['date_label'].iloc[-1], is_monthly=True))
    else:
        st.metric("IPC", "No disp.")

with c6:
    if df_desempleo_cl is not None and not df_desempleo_cl.empty:
        st.metric("Desempleo Chile", f"{df_desempleo_cl['value'].iloc[-1]:.1f}%")
        st.caption(format_date_str(df_desempleo_cl['date_label'].iloc[-1], is_monthly=True))
    else:
        st.metric("Desempleo Chile", "No disp.")

st.divider()

# ----------------------------------------------------
# 5. Sección Estados Unidos
# ----------------------------------------------------
st.subheader("🇺🇸 Indicadores Estados Unidos")
u1, u2, u3, u4 = st.columns(4)

with u1:
    val_act, val_ant, f_date = data_us["us_10y"]
    st.metric("Bono US Treasury 10A", f"{val_act:.2f}%", delta=f"{(val_act - val_ant):+.2f}%")
    st.caption(format_date_str(f_date, is_monthly=False))

with u2:
    val_act, val_ant, f_date = data_us["fed_rate"]
    st.metric("Tasa Fed Funds", f"{val_act:.2f}%")
    st.caption(format_date_str(f_date, is_monthly=True))

with u3:
    val_act, f_date = data_us["us_cpi"]
    st.metric("Inflación CPI EE.UU. (12M)", f"{val_act:.1f}%")
    st.caption(format_date_str(f_date, is_monthly=True))

with u4:
    val_act, f_date = data_us["us_unemp"]
    st.metric("Desempleo EE.UU.", f"{val_act:.1f}%")
    st.caption(format_date_str(f_date, is_monthly=True))

st.divider()

# ----------------------------------------------------
# 6. Gráficos Comparativos (Chile vs. EE.UU.)
# ----------------------------------------------------
st.subheader("📈 Comparativas Macroeconómicas: Chile vs. EE.UU.")
g1, g2 = st.columns(2)

# Gráfico 1: Bonos Soberanos 10 Años
with g1:
    st.markdown("**Tasas Soberanas a 10 Años (Bono BCCh vs. US Treasury)**")
    fig_bonos = go.Figure()
    
    # Serie US 10Y
    df_us_10 = data_us["df_10y_us"]
    fig_bonos.add_trace(go.Scatter(
        x=df_us_10["Fecha"], 
        y=df_us_10["US 10Y (%)"], 
        mode='lines', 
        name='US Treasury 10Y',
        line=dict(color='#1f77b4', width=2)
    ))
    
    # Serie Chile 10Y
    if df_bono10_cl is not None and not df_bono10_cl.empty:
        fig_bonos.add_trace(go.Scatter(
            x=df_bono10_cl["Fecha"], 
            y=df_bono10_cl["value"], 
            mode='lines', 
            name='Chile BCP 10Y',
            line=dict(color='#d62728', width=2)
        ))
        
    fig_bonos.update_layout(
        height=360, 
        margin=dict(l=20, r=20, t=30, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis=dict(title="Tasa (%)")
    )
    st.plotly_chart(fig_bonos, use_container_width=True)

# Gráfico 2: TPM Chile vs. Fed Funds Rate
with g2:
    st.markdown("**Tasas de Política Monetaria (TPM Chile vs. Fed Funds Rate)**")
    fig_tasas = go.Figure()
    
    # Serie Fed Funds
    df_fed = data_us["df_fed"]
    fig_tasas.add_trace(go.Scatter(
        x=df_fed["Fecha"], 
        y=df_fed["Fed Funds (%)"], 
        mode='lines+markers', 
        name='Fed Funds Rate (EE.UU.)',
        line=dict(color='#2ca02c', width=2)
    ))
    
    # Serie TPM Chile
    if df_tpm is not None and not df_tpm.empty:
        fig_tasas.add_trace(go.Scatter(
            x=df_tpm["Fecha"], 
            y=df_tpm["value"], 
            mode='lines', 
            name='TPM Chile (BCCh)',
            line=dict(color='#ff7f0e', width=2)
        ))
        
    fig_tasas.update_layout(
        height=360, 
        margin=dict(l=20, r=20, t=30, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis=dict(title="Tasa (%)")
    )
    st.plotly_chart(fig_tasas, use_container_width=True)
