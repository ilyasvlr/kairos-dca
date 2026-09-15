"""
Dashboard Page
Vue d'ensemble du marché et indicateurs
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# Import depuis core
import sys
sys.path.append('..')
from core.data_fetcher import (
    fetch_crypto_data,
    fetch_stock_data,
    fetch_fear_greed_crypto,
    fetch_fear_greed_history
)

st.set_page_config(page_title="Dashboard - Kairos DCA", page_icon="📊", layout="wide")

from core.ui import render_disclaimer
render_disclaimer()

st.title("📊 Dashboard")

# Récupérer la configuration depuis session_state
if 'ticker' not in st.session_state:
    st.warning("⚠️ Configure d'abord un actif dans la page principale")
    st.stop()

ticker = st.session_state['ticker']
asset_name = st.session_state['asset_name']
start_date = st.session_state['start_date']
end_date = st.session_state['end_date']

# Charger les données
with st.spinner(f"Chargement des données pour {asset_name}..."):
    if '-USD' in ticker:
        prices = fetch_crypto_data(ticker, str(start_date), str(end_date))
    else:
        prices = fetch_stock_data(ticker, str(start_date), str(end_date))

if prices.empty:
    st.error("Impossible de charger les données")
    st.stop()

# Fear & Greed
fear_greed = fetch_fear_greed_crypto()

# === SECTION 1 : KPIs ===
st.subheader(f"{asset_name} ({ticker})")

col1, col2, col3, col4 = st.columns(4)

with col1:
    current_price = prices['Close'].iloc[-1]
    st.metric(
        "Prix actuel",
        f"${current_price:,.2f}",
        delta=f"{((current_price / prices['Close'].iloc[-2]) - 1) * 100:.2f}%"
    )

with col2:
    ath = prices['High'].max()
    distance_from_ath = ((current_price / ath) - 1) * 100
    st.metric(
        "ATH",
        f"${ath:,.2f}",
        delta=f"{distance_from_ath:.1f}%"
    )

with col3:
    atl = prices['Low'].min()
    distance_from_atl = ((current_price / atl) - 1) * 100
    st.metric(
        "ATL",
        f"${atl:,.2f}",
        delta=f"+{distance_from_atl:.1f}%"
    )

with col4:
    fg_value = fear_greed['value']
    fg_class = fear_greed['classification']

    # Couleur selon la valeur
    if fg_value < 25:
        delta_color = "normal"
        delta = "Extreme Fear"
    elif fg_value < 45:
        delta_color = "normal"
        delta = "Fear"
    elif fg_value < 55:
        delta_color = "off"
        delta = "Neutral"
    elif fg_value < 75:
        delta_color = "inverse"
        delta = "Greed"
    else:
        delta_color = "inverse"
        delta = "Extreme Greed"

    st.metric(
        "Fear & Greed",
        f"{fg_value}/100",
        delta=delta
    )

# === SECTION 2 : GRAPHIQUE PRINCIPAL ===
st.subheader("📈 Évolution du prix")

# Créer le graphique
fig = go.Figure()

fig.add_trace(go.Scatter(
    x=prices.index,
    y=prices['Close'],
    mode='lines',
    name='Prix',
    line=dict(color='#00D4AA', width=2)
))

# Ajouter les moyennes mobiles
if len(prices) > 50:
    ma50 = prices['Close'].rolling(window=50).mean()
    fig.add_trace(go.Scatter(
        x=prices.index,
        y=ma50,
        mode='lines',
        name='MA50',
        line=dict(color='#FFA500', width=1, dash='dash')
    ))

if len(prices) > 200:
    ma200 = prices['Close'].rolling(window=200).mean()
    fig.add_trace(go.Scatter(
        x=prices.index,
        y=ma200,
        mode='lines',
        name='MA200',
        line=dict(color='#FF6347', width=1, dash='dash')
    ))

fig.update_layout(
    height=500,
    xaxis_title="Date",
    yaxis_title="Prix ($)",
    hovermode='x unified',
    showlegend=True,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)

st.plotly_chart(fig, width='stretch')

# === SECTION 3 : VOLUME ===
st.subheader("📊 Volume")

fig_volume = go.Figure()

fig_volume.add_trace(go.Bar(
    x=prices.index,
    y=prices['Volume'],
    name='Volume',
    marker_color='#00D4AA'
))

fig_volume.update_layout(
    height=300,
    xaxis_title="Date",
    yaxis_title="Volume",
    hovermode='x unified'
)

st.plotly_chart(fig_volume, width='stretch')

# === SECTION 4 : FEAR & GREED HISTORY ===
if '-USD' in ticker:  # Seulement pour crypto
    st.subheader("😱 Fear & Greed Index (Historique)")

    fg_history = fetch_fear_greed_history(days=365)

    if not fg_history.empty:
        fig_fg = go.Figure()

        # Colorer selon la valeur
        colors = []
        for val in fg_history['value']:
            if val < 25:
                colors.append('#FF0000')  # Rouge
            elif val < 45:
                colors.append('#FFA500')  # Orange
            elif val < 55:
                colors.append('#FFFF00')  # Jaune
            elif val < 75:
                colors.append('#90EE90')  # Vert clair
            else:
                colors.append('#00FF00')  # Vert

        fig_fg.add_trace(go.Scatter(
            x=fg_history['timestamp'],
            y=fg_history['value'],
            mode='lines+markers',
            name='Fear & Greed',
            line=dict(color='#00D4AA', width=2),
            marker=dict(color=colors, size=4)
        ))

        # Ajouter les zones de couleur
        fig_fg.add_hrect(y0=0, y1=25, fillcolor="red", opacity=0.1, line_width=0)
        fig_fg.add_hrect(y0=25, y1=45, fillcolor="orange", opacity=0.1, line_width=0)
        fig_fg.add_hrect(y0=45, y1=55, fillcolor="yellow", opacity=0.1, line_width=0)
        fig_fg.add_hrect(y0=55, y1=75, fillcolor="lightgreen", opacity=0.1, line_width=0)
        fig_fg.add_hrect(y0=75, y1=100, fillcolor="green", opacity=0.1, line_width=0)

        fig_fg.update_layout(
            height=300,
            xaxis_title="Date",
            yaxis_title="Fear & Greed Index",
            yaxis_range=[0, 100],
            hovermode='x unified'
        )

        st.plotly_chart(fig_fg, width='stretch')
    else:
        st.warning("Impossible de charger l'historique Fear & Greed")

# === SECTION 5 : STATISTIQUES ===
st.subheader("📊 Statistiques")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("#### Performance")
    perf_1w = ((prices['Close'].iloc[-1] / prices['Close'].iloc[-7]) - 1) * 100 if len(prices) > 7 else 0
    perf_1m = ((prices['Close'].iloc[-1] / prices['Close'].iloc[-30]) - 1) * 100 if len(prices) > 30 else 0
    perf_3m = ((prices['Close'].iloc[-1] / prices['Close'].iloc[-90]) - 1) * 100 if len(prices) > 90 else 0

    st.write(f"**1 semaine :** {perf_1w:+.2f}%")
    st.write(f"**1 mois :** {perf_1m:+.2f}%")
    st.write(f"**3 mois :** {perf_3m:+.2f}%")

with col2:
    st.markdown("#### Volatilité")
    daily_returns = prices['Close'].pct_change().dropna()
    volatility = daily_returns.std() * (252 ** 0.5) * 100  # Annualisée

    st.write(f"**Volatilité annualisée :** {volatility:.2f}%")
    st.write(f"**Plus haut (période) :** ${prices['High'].max():,.2f}")
    st.write(f"**Plus bas (période) :** ${prices['Low'].min():,.2f}")

with col3:
    st.markdown("#### Données")
    st.write(f"**Début :** {prices.index[0].strftime('%Y-%m-%d')}")
    st.write(f"**Fin :** {prices.index[-1].strftime('%Y-%m-%d')}")
    st.write(f"**Jours de trading :** {len(prices)}")
