"""
Indicators Page
Affiche tous les indicateurs techniques et on-chain
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys

sys.path.append('..')
from core.data_fetcher import fetch_crypto_data, fetch_stock_data, fetch_fear_greed_crypto
from core.indicators import calculate_all_indicators, get_signal_strength
from core.macro_data import fetch_macro_indicators, get_macro_sentiment

st.set_page_config(page_title="Indicators - Kairos DCA", page_icon="📈", layout="wide")

from core.ui import render_disclaimer
render_disclaimer()

st.title("📈 Indicateurs")

signal_colors = {
    'strong_buy': '🟢',
    'buy': '🟢',
    'neutral': '🟡',
    'sell': '🔴',
    'strong_sell': '🔴'
}

# Récupérer la configuration
if 'ticker' not in st.session_state:
    st.warning("⚠️ Configure d'abord un actif dans la page principale")
    st.stop()

ticker = st.session_state['ticker']
asset_name = st.session_state['asset_name']
start_date = st.session_state['start_date']
end_date = st.session_state['end_date']

# Déterminer le type d'actif
asset_type = 'crypto' if '-USD' in ticker else 'stock'

# Charger les données
with st.spinner(f"Chargement des données pour {asset_name}..."):
    if asset_type == 'crypto':
        prices = fetch_crypto_data(ticker, str(start_date), str(end_date))
    else:
        prices = fetch_stock_data(ticker, str(start_date), str(end_date))

if prices.empty:
    st.error("Impossible de charger les données")
    st.stop()

# Historique étendu : la 200WMA a besoin de 200 semaines de recul AVANT
# le premier point affiché, sinon la ligne est vide sur toute la période.
long_close = None
if asset_type == 'crypto':
    long_start = (pd.Timestamp(start_date) - pd.DateOffset(years=5)).date()
    with st.spinner("Chargement de l'historique long (200WMA)..."):
        long_prices = fetch_crypto_data(ticker, str(long_start), str(end_date))
    if not long_prices.empty:
        long_close = long_prices['Close']

# Calculer tous les indicateurs
with st.spinner("Calcul des indicateurs..."):
    indicators = calculate_all_indicators(prices, asset_type, symbol=ticker, long_close=long_close)

# Récupérer Fear & Greed (crypto uniquement)
fear_greed = fetch_fear_greed_crypto() if asset_type == 'crypto' else None

# Récupérer indicateurs macro
with st.spinner("Chargement des données macro..."):
    macro_indicators = fetch_macro_indicators()

# === SECTION 1 : SIGNAUX GLOBAUX ===
st.subheader("🎯 Signaux globaux")

col1, col2, col3, col4 = st.columns(4)

with col1:
    rsi_val = indicators['rsi'].iloc[-1]
    rsi_signal = get_signal_strength(rsi_val, 'rsi')

    st.metric(
        "RSI (14)",
        f"{rsi_val:.1f}",
        delta=f"{signal_colors[rsi_signal]} {rsi_signal.replace('_', ' ').title()}"
    )

with col2:
    if fear_greed:
        fg_val = fear_greed['value']
        fg_signal = get_signal_strength(fg_val, 'fear_greed')

        st.metric(
            "Fear & Greed",
            f"{fg_val}/100",
            delta=f"{signal_colors[fg_signal]} {fg_signal.replace('_', ' ').title()}"
        )

with col3:
    if asset_type == 'crypto' and 'mvrv_zscore' in indicators:
        mvrv_val = indicators['mvrv_zscore'].iloc[-1]
        if not pd.isna(mvrv_val):
            mvrv_signal = get_signal_strength(mvrv_val, 'mvrv_zscore')

            st.metric(
                "MVRV Z-Score",
                f"{mvrv_val:.2f}",
                delta=f"{signal_colors[mvrv_signal]} {mvrv_signal.replace('_', ' ').title()}"
            )

with col4:
    macro_sentiment = get_macro_sentiment(macro_indicators)
    macro_colors = {
        'bullish': '🟢',
        'neutral': '🟡',
        'bearish': '🔴'
    }

    st.metric(
        "Sentiment Macro",
        macro_sentiment.title(),
        delta=f"{macro_colors[macro_sentiment]} {macro_sentiment}"
    )

# === SECTION 2 : SÉLECTEUR D'INDICATEURS ===
st.subheader("📊 Indicateurs disponibles")

indicator_options = {
    'RSI': 'rsi',
    'MACD': 'macd',
    'Bandes de Bollinger': 'bollinger',
    'Moyennes Mobiles': 'moving_averages',
    'ATR': 'atr',
    'Stochastic RSI': 'stoch_rsi',
}

if asset_type == 'crypto':
    indicator_options.update({
        '200-Week MA': 'ma_200w',
        'Régression Log': 'log_regression',
        'MVRV Z-Score': 'mvrv_zscore',
    })
    if 'BTC' in ticker:
        indicator_options['Rainbow Chart'] = 'rainbow'

selected_indicators = st.multiselect(
    "Sélectionne les indicateurs à afficher",
    options=list(indicator_options.keys()),
    default=['RSI', 'Bandes de Bollinger', 'Moyennes Mobiles']
)

# === SECTION 3 : GRAPHIQUE PRINCIPAL ===
if selected_indicators:
    st.subheader(f"📈 {asset_name} avec indicateurs")

    # Créer le graphique principal
    fig = make_subplots(
        rows=1, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[1.0]
    )

    # Prix
    fig.add_trace(
        go.Scatter(
            x=prices.index,
            y=prices['Close'],
            mode='lines',
            name='Prix',
            line=dict(color='#00D4AA', width=2)
        ),
        row=1, col=1
    )

    # Ajouter les indicateurs sélectionnés
    colors = ['#FF6347', '#FFD700', '#9370DB', '#FF69B4', '#20B2AA', '#FFA07A']
    color_idx = 0

    for indicator_name in selected_indicators:
        indicator_key = indicator_options[indicator_name]

        if indicator_key in ('rsi', 'macd', 'atr', 'stoch_rsi', 'mvrv_zscore'):
            # Affichés dans leurs propres graphiques, plus bas
            pass

        elif indicator_key == 'bollinger':
            fig.add_trace(
                go.Scatter(
                    x=prices.index,
                    y=indicators['bb_upper'],
                    mode='lines',
                    name='BB Upper',
                    line=dict(color=colors[color_idx % len(colors)], width=1, dash='dash')
                ),
                row=1, col=1
            )
            fig.add_trace(
                go.Scatter(
                    x=prices.index,
                    y=indicators['bb_lower'],
                    mode='lines',
                    name='BB Lower',
                    line=dict(color=colors[color_idx % len(colors)], width=1, dash='dash'),
                    fill='tonexty',
                    fillcolor='rgba(255, 99, 71, 0.1)'
                ),
                row=1, col=1
            )
            color_idx += 1

        elif indicator_key == 'moving_averages':
            for ma_name, ma_values in indicators['moving_averages'].items():
                fig.add_trace(
                    go.Scatter(
                        x=prices.index,
                        y=ma_values,
                        mode='lines',
                        name=ma_name,
                        line=dict(color=colors[color_idx % len(colors)], width=1)
                    ),
                    row=1, col=1
                )
                color_idx += 1

        elif indicator_key == 'ma_200w' and 'ma_200w' in indicators:
            ma_200w = indicators['ma_200w']
            if not ma_200w.empty:
                fig.add_trace(
                    go.Scatter(
                        x=prices.index,
                        y=ma_200w,
                        mode='lines',
                        name='200-Week MA',
                        line=dict(color='#00FF00', width=3)
                    ),
                    row=1, col=1
                )
            else:
                st.info(
                    "200-Week MA indisponible : moins de 200 semaines d'historique "
                    f"pour {asset_name} (l'actif est trop jeune)."
                )

        elif indicator_key == 'log_regression' and 'log_reg_middle' in indicators:
            fig.add_trace(
                go.Scatter(
                    x=indicators['log_reg_upper'].index,
                    y=indicators['log_reg_upper'],
                    mode='lines',
                    name='Log Reg Upper',
                    line=dict(color='#FF0000', width=1, dash='dot')
                ),
                row=1, col=1
            )
            fig.add_trace(
                go.Scatter(
                    x=indicators['log_reg_middle'].index,
                    y=indicators['log_reg_middle'],
                    mode='lines',
                    name='Log Reg Middle',
                    line=dict(color='#FFD700', width=2)
                ),
                row=1, col=1
            )
            fig.add_trace(
                go.Scatter(
                    x=indicators['log_reg_lower'].index,
                    y=indicators['log_reg_lower'],
                    mode='lines',
                    name='Log Reg Lower',
                    line=dict(color='#00FF00', width=1, dash='dot'),
                    fill='tonexty',
                    fillcolor='rgba(0, 255, 0, 0.05)'
                ),
                row=1, col=1
            )

        elif indicator_key == 'rainbow' and 'rainbow' in indicators:
            for band in indicators['rainbow'].values():
                fig.add_trace(
                    go.Scatter(
                        x=band['values'].index,
                        y=band['values'],
                        mode='lines',
                        name=band['label'],
                        line=dict(color=band['color'], width=1)
                    ),
                    row=1, col=1
                )

    fig.update_layout(
        height=600,
        xaxis_title="Date",
        yaxis_title="Prix ($)",
        hovermode='x unified',
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    st.plotly_chart(fig, width='stretch')

    # === RSI en graphique séparé ===
    if 'RSI' in selected_indicators:
        st.subheader("📊 RSI (Relative Strength Index)")

        fig_rsi = go.Figure()

        fig_rsi.add_trace(
            go.Scatter(
                x=indicators['rsi'].index,
                y=indicators['rsi'],
                mode='lines',
                name='RSI',
                line=dict(color='#00D4AA', width=2)
            )
        )

        # Zones de survente/sureachat
        fig_rsi.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.5)
        fig_rsi.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.5)

        fig_rsi.add_hrect(y0=70, y1=100, fillcolor="red", opacity=0.1, line_width=0)
        fig_rsi.add_hrect(y0=0, y1=30, fillcolor="green", opacity=0.1, line_width=0)

        fig_rsi.update_layout(
            height=300,
            xaxis_title="Date",
            yaxis_title="RSI",
            yaxis_range=[0, 100],
            hovermode='x unified'
        )

        st.plotly_chart(fig_rsi, width='stretch')

    # === MACD en graphique séparé ===
    if 'MACD' in selected_indicators:
        st.subheader("📊 MACD (12, 26, 9)")

        fig_macd = go.Figure()

        hist = indicators['macd_hist']
        fig_macd.add_trace(
            go.Bar(
                x=hist.index,
                y=hist,
                name='Histogramme',
                marker_color=['#00D4AA' if v >= 0 else '#FF6347' for v in hist.fillna(0)]
            )
        )
        fig_macd.add_trace(
            go.Scatter(
                x=indicators['macd_line'].index,
                y=indicators['macd_line'],
                mode='lines',
                name='MACD',
                line=dict(color='#FFD700', width=2)
            )
        )
        fig_macd.add_trace(
            go.Scatter(
                x=indicators['macd_signal'].index,
                y=indicators['macd_signal'],
                mode='lines',
                name='Signal',
                line=dict(color='#9370DB', width=2)
            )
        )
        fig_macd.add_hline(y=0, line_color="gray", opacity=0.5)

        fig_macd.update_layout(
            height=300,
            xaxis_title="Date",
            yaxis_title="MACD",
            hovermode='x unified'
        )

        st.plotly_chart(fig_macd, width='stretch')

    # === Stochastic RSI en graphique séparé ===
    if 'Stochastic RSI' in selected_indicators:
        st.subheader("📊 Stochastic RSI")

        fig_stoch = go.Figure()

        fig_stoch.add_trace(
            go.Scatter(
                x=indicators['stoch_rsi_k'].index,
                y=indicators['stoch_rsi_k'],
                mode='lines',
                name='%K',
                line=dict(color='#00D4AA', width=2)
            )
        )
        fig_stoch.add_trace(
            go.Scatter(
                x=indicators['stoch_rsi_d'].index,
                y=indicators['stoch_rsi_d'],
                mode='lines',
                name='%D',
                line=dict(color='#FFD700', width=2)
            )
        )

        fig_stoch.add_hrect(y0=80, y1=100, fillcolor="red", opacity=0.1, line_width=0)
        fig_stoch.add_hrect(y0=0, y1=20, fillcolor="green", opacity=0.1, line_width=0)

        fig_stoch.update_layout(
            height=300,
            xaxis_title="Date",
            yaxis_title="Stoch RSI",
            yaxis_range=[0, 100],
            hovermode='x unified'
        )

        st.plotly_chart(fig_stoch, width='stretch')

    # === ATR en graphique séparé ===
    if 'ATR' in selected_indicators:
        st.subheader("📊 ATR (Average True Range)")

        fig_atr = go.Figure()

        fig_atr.add_trace(
            go.Scatter(
                x=indicators['atr'].index,
                y=indicators['atr'],
                mode='lines',
                name='ATR (14)',
                line=dict(color='#FFA07A', width=2)
            )
        )

        fig_atr.update_layout(
            height=300,
            xaxis_title="Date",
            yaxis_title="ATR ($)",
            hovermode='x unified'
        )

        st.plotly_chart(fig_atr, width='stretch')

    # === MVRV Z-Score en graphique séparé ===
    if 'MVRV Z-Score' in selected_indicators and 'mvrv_zscore' in indicators:
        st.subheader("📊 MVRV Z-Score (approximation)")

        mvrv = indicators['mvrv_zscore']

        if mvrv.notna().any():
            fig_mvrv = go.Figure()

            fig_mvrv.add_trace(
                go.Scatter(
                    x=mvrv.index,
                    y=mvrv,
                    mode='lines',
                    name='MVRV Z-Score',
                    line=dict(color='#9370DB', width=2)
                )
            )

            # Seuils Z-Score statistiques (et non ceux du MVRV on-chain)
            fig_mvrv.add_hline(y=-1.5, line_dash="dash", line_color="green", opacity=0.5)
            fig_mvrv.add_hline(y=2.0, line_dash="dash", line_color="red", opacity=0.5)
            fig_mvrv.add_hline(y=0, line_color="gray", opacity=0.3)

            fig_mvrv.add_hrect(y0=2.0, y1=max(4.0, float(mvrv.max())),
                               fillcolor="red", opacity=0.08, line_width=0)
            fig_mvrv.add_hrect(y0=min(-4.0, float(mvrv.min())), y1=-1.5,
                               fillcolor="green", opacity=0.08, line_width=0)

            fig_mvrv.update_layout(
                height=300,
                xaxis_title="Date",
                yaxis_title="Z-Score",
                hovermode='x unified'
            )

            st.plotly_chart(fig_mvrv, width='stretch')

            st.caption(
                "⚠️ Approximation : le vrai MVRV utilise la realized cap on-chain. "
                "Ici c'est un proxy basé sur la moyenne mobile 365j du prix. "
                "Les seuils sont ceux d'un Z-Score statistique (-1.5 / +2.0), "
                "pas ceux du MVRV on-chain (0 / 7)."
            )
        else:
            st.info(
                "MVRV Z-Score indisponible : il faut ~730 jours de données "
                "(2 fenêtres de 365j). Élargis la période dans la page principale."
            )

# === SECTION 4 : INDICATEURS MACRO ===
st.subheader("🌍 Indicateurs Macro")

# (clé, couleur, préfixe, suffixe, décimales, années d'historique à tracer)
MACRO_LAYOUT = [
    ('fed_funds', '#FF6347', '', '%', 2, 15),
    ('yield_10y', '#FFD700', '', '%', 2, 15),
    ('cpi', '#9370DB', '', '', 1, 15),
    ('m2', '#20B2AA', '$', ' Md', 0, 15),
    ('dxy', '#00D4AA', '', '', 2, 5),
    ('vix', '#FF69B4', '', '', 2, 5),
]

available = [m for m in MACRO_LAYOUT if m[0] in macro_indicators]

if not available:
    st.warning("Aucune donnée macro disponible (FRED et yfinance injoignables)")

for row_start in range(0, len(available), 3):
    cols = st.columns(3)
    for col, (key, color, prefix, suffix, decimals, years) in zip(
        cols, available[row_start:row_start + 3]
    ):
        with col:
            ind = macro_indicators[key]

            st.metric(
                ind['name'],
                f"{prefix}{ind['value']:,.{decimals}f}{suffix}",
                delta=f"{ind['yoy_change']:+.2f}% sur 1 an"
            )

            data = ind['data']
            cutoff = data.index[-1] - pd.DateOffset(years=years)
            data = data.loc[data.index >= cutoff]

            fig_macro = go.Figure()
            fig_macro.add_trace(
                go.Scatter(
                    x=data.index,
                    y=data['value'],
                    mode='lines',
                    name=ind['name'],
                    line=dict(color=color, width=2)
                )
            )
            fig_macro.update_layout(
                height=250,
                margin=dict(l=10, r=10, t=10, b=10),
                xaxis_title=None,
                yaxis_title=None,
                hovermode='x unified'
            )
            st.plotly_chart(fig_macro, width='stretch')

            st.caption(f"Dernière obs. : {ind['last_date']:%Y-%m-%d}")

# === SECTION 5 : TABLEAU RÉCAPITULATIF ===
st.subheader("📋 Résumé des signaux")

signals_data = []

# RSI
rsi_val = indicators['rsi'].iloc[-1]
signals_data.append({
    'Indicateur': 'RSI (14)',
    'Valeur': f"{rsi_val:.1f}",
    'Signal': get_signal_strength(rsi_val, 'rsi').replace('_', ' ').title()
})

# Fear & Greed
if fear_greed:
    fg_val = fear_greed['value']
    signals_data.append({
        'Indicateur': 'Fear & Greed',
        'Valeur': f"{fg_val}/100",
        'Signal': get_signal_strength(fg_val, 'fear_greed').replace('_', ' ').title()
    })

# MVRV Z-Score
if asset_type == 'crypto' and 'mvrv_zscore' in indicators:
    mvrv_val = indicators['mvrv_zscore'].iloc[-1]
    if not pd.isna(mvrv_val):
        signals_data.append({
            'Indicateur': 'MVRV Z-Score',
            'Valeur': f"{mvrv_val:.2f}",
            'Signal': get_signal_strength(mvrv_val, 'mvrv_zscore').replace('_', ' ').title()
        })

# 200-Week MA
if asset_type == 'crypto' and not indicators.get('ma_200w', pd.Series(dtype=float)).empty:
    ma_200w_val = indicators['ma_200w'].iloc[-1]
    if not pd.isna(ma_200w_val):
        current_price = prices['Close'].iloc[-1]
        if current_price < ma_200w_val:
            signal = 'Buy (sous la 200WMA)'
        else:
            signal = 'Neutral (au-dessus)'

        signals_data.append({
            'Indicateur': '200-Week MA',
            'Valeur': f"${ma_200w_val:,.2f}",
            'Signal': signal
        })

# Macro
macro_sentiment = get_macro_sentiment(macro_indicators)
signals_data.append({
    'Indicateur': 'Sentiment Macro',
    'Valeur': '-',
    'Signal': macro_sentiment.title()
})

signals_df = pd.DataFrame(signals_data)
st.dataframe(signals_df, width='stretch', hide_index=True)
