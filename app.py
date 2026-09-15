"""
Kairos DCA - Application
Une seule page : configure l'actif dans la barre latérale, tout le reste
(Dashboard, Backtest, Indicateurs, Dynamic DCA, Robustesse) s'affiche par onglets.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

st.set_page_config(
    page_title="Kairos DCA",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

from core.data_fetcher import (
    get_flat_asset_list,
    fetch_crypto_data,
    fetch_stock_data,
    fetch_fear_greed_crypto,
    fetch_fear_greed_history,
)
from core.macro_data import fetch_vix_history, fetch_macro_indicators, get_macro_sentiment
from core.indicators import calculate_all_indicators, get_signal_strength
from core.backtester import (
    ClassicDCAStrategy,
    DrawdownDCAStrategy,
    RSIDCAStrategy,
    KairosScoreDCAStrategy,
    VaultDCAStrategy,
    Backtester,
    compare_strategies,
)
from core.robustness import build_grid, compute_robustness_map, rank_stability
from core.ui import render_disclaimer

st.title("🎯 Kairos DCA")
st.markdown("### Optimiseur de DCA multi-actifs avec indicateurs avancés")

# ==============================================================================
# SIDEBAR — configuration globale, une seule fois, partagée par tous les onglets
# ==============================================================================
st.sidebar.header("⚙️ Configuration")

flat_assets = get_flat_asset_list()
default_idx = next((i for i, a in enumerate(flat_assets) if a['ticker'] == 'BTC-USD'), 0)
asset_choice = st.sidebar.selectbox(
    "Actif",
    options=flat_assets,
    index=default_idx,
    format_func=lambda a: f"{a['name']} ({a['ticker']}) — {a['category']}",
    help="Tape pour rechercher : nom, ticker ou catégorie (ex. « MSCI », « BTC », « ETF »).",
    key='global_asset',
)
asset_name = asset_choice['name']
ticker = asset_choice['ticker']
asset_type = 'crypto' if '-USD' in ticker else 'stock'

st.sidebar.subheader("📅 Période")
default_end = datetime.now()
default_start = default_end - timedelta(days=365 * 3)

col1, col2 = st.sidebar.columns(2)
with col1:
    start_date = st.date_input("Début", value=default_start, max_value=default_end, key='global_start')
with col2:
    end_date = st.date_input("Fin", value=default_end, max_value=default_end, key='global_end')

st.sidebar.subheader("💰 Paramètres DCA")
base_amount = st.sidebar.number_input(
    "Montant de base ($)", min_value=10, max_value=10000, value=100, step=10, key='global_amount'
)
frequency = st.sidebar.selectbox(
    "Fréquence",
    options=['daily', 'weekly', 'monthly'],
    format_func=lambda x: {'daily': 'Quotidien', 'weekly': 'Hebdomadaire', 'monthly': 'Mensuel'}[x],
    index=1,
    key='global_freq',
)
fees = st.sidebar.slider("Frais (%)", min_value=0.0, max_value=1.0, value=0.1, step=0.01, key='global_fees') / 100

# Conservé pour compatibilité (rien d'autre ne les lit désormais, les onglets
# reçoivent ces valeurs directement en paramètres) et pour un éventuel usage futur.
st.session_state['ticker'] = ticker
st.session_state['asset_name'] = asset_name
st.session_state['start_date'] = start_date
st.session_state['end_date'] = end_date
st.session_state['base_amount'] = base_amount
st.session_state['frequency'] = frequency
st.session_state['fees'] = fees

render_disclaimer()

st.info(f"""
**Configuration actuelle :**
- Actif : {asset_name} ({ticker})
- Période : {start_date} → {end_date}
- Montant : ${base_amount} {frequency}
- Frais : {fees*100:.2f}%
""")

st.caption(
    "Onglets : 📊 vue d'ensemble · 🔬 backtest classique · 📈 indicateurs · "
    "⚡ stratégies dynamiques (une fenêtre) · 🛡️ robustesse (toutes les fenêtres, "
    "la page à consulter avant toute décision)."
)


# ==============================================================================
# ONGLET 1 — DASHBOARD
# ==============================================================================
def render_dashboard(ticker, asset_name, start_date, end_date):
    st.subheader(f"{asset_name} ({ticker})")

    with st.spinner(f"Chargement des données pour {asset_name}..."):
        if '-USD' in ticker:
            prices = fetch_crypto_data(ticker, str(start_date), str(end_date))
        else:
            prices = fetch_stock_data(ticker, str(start_date), str(end_date))

    if prices.empty:
        st.error("Impossible de charger les données")
        return

    fear_greed = fetch_fear_greed_crypto()

    # --- KPIs ---
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        current_price = prices['Close'].iloc[-1]
        st.metric(
            "Prix actuel", f"${current_price:,.2f}",
            delta=f"{((current_price / prices['Close'].iloc[-2]) - 1) * 100:.2f}%"
        )
    with col2:
        ath = prices['High'].max()
        distance_from_ath = ((current_price / ath) - 1) * 100
        st.metric("ATH", f"${ath:,.2f}", delta=f"{distance_from_ath:.1f}%")
    with col3:
        atl = prices['Low'].min()
        distance_from_atl = ((current_price / atl) - 1) * 100
        st.metric("ATL", f"${atl:,.2f}", delta=f"+{distance_from_atl:.1f}%")
    with col4:
        fg_value = fear_greed['value']
        if fg_value < 25:
            delta = "Extreme Fear"
        elif fg_value < 45:
            delta = "Fear"
        elif fg_value < 55:
            delta = "Neutral"
        elif fg_value < 75:
            delta = "Greed"
        else:
            delta = "Extreme Greed"
        st.metric("Fear & Greed", f"{fg_value}/100", delta=delta)

    # --- Graphique principal ---
    st.subheader("📈 Évolution du prix")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=prices.index, y=prices['Close'], mode='lines', name='Prix',
                             line=dict(color='#00D4AA', width=2)))
    if len(prices) > 50:
        ma50 = prices['Close'].rolling(window=50).mean()
        fig.add_trace(go.Scatter(x=prices.index, y=ma50, mode='lines', name='MA50',
                                 line=dict(color='#FFA500', width=1, dash='dash')))
    if len(prices) > 200:
        ma200 = prices['Close'].rolling(window=200).mean()
        fig.add_trace(go.Scatter(x=prices.index, y=ma200, mode='lines', name='MA200',
                                 line=dict(color='#FF6347', width=1, dash='dash')))
    fig.update_layout(
        height=500, xaxis_title="Date", yaxis_title="Prix ($)", hovermode='x unified',
        showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig, width='stretch')

    # --- Volume ---
    st.subheader("📊 Volume")
    fig_volume = go.Figure()
    fig_volume.add_trace(go.Bar(x=prices.index, y=prices['Volume'], name='Volume', marker_color='#00D4AA'))
    fig_volume.update_layout(height=300, xaxis_title="Date", yaxis_title="Volume", hovermode='x unified')
    st.plotly_chart(fig_volume, width='stretch')

    # --- Fear & Greed history (crypto) ---
    if '-USD' in ticker:
        st.subheader("😱 Fear & Greed Index (Historique)")
        fg_history = fetch_fear_greed_history(days=365)

        if not fg_history.empty:
            fig_fg = go.Figure()
            colors = []
            for val in fg_history['value']:
                if val < 25:
                    colors.append('#FF0000')
                elif val < 45:
                    colors.append('#FFA500')
                elif val < 55:
                    colors.append('#FFFF00')
                elif val < 75:
                    colors.append('#90EE90')
                else:
                    colors.append('#00FF00')

            fig_fg.add_trace(go.Scatter(
                x=fg_history['timestamp'], y=fg_history['value'], mode='lines+markers', name='Fear & Greed',
                line=dict(color='#00D4AA', width=2), marker=dict(color=colors, size=4)
            ))
            fig_fg.add_hrect(y0=0, y1=25, fillcolor="red", opacity=0.1, line_width=0)
            fig_fg.add_hrect(y0=25, y1=45, fillcolor="orange", opacity=0.1, line_width=0)
            fig_fg.add_hrect(y0=45, y1=55, fillcolor="yellow", opacity=0.1, line_width=0)
            fig_fg.add_hrect(y0=55, y1=75, fillcolor="lightgreen", opacity=0.1, line_width=0)
            fig_fg.add_hrect(y0=75, y1=100, fillcolor="green", opacity=0.1, line_width=0)
            fig_fg.update_layout(height=300, xaxis_title="Date", yaxis_title="Fear & Greed Index",
                                 yaxis_range=[0, 100], hovermode='x unified')
            st.plotly_chart(fig_fg, width='stretch')
        else:
            st.warning("Impossible de charger l'historique Fear & Greed")

    # --- Statistiques ---
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
        volatility = daily_returns.std() * (252 ** 0.5) * 100
        st.write(f"**Volatilité annualisée :** {volatility:.2f}%")
        st.write(f"**Plus haut (période) :** ${prices['High'].max():,.2f}")
        st.write(f"**Plus bas (période) :** ${prices['Low'].min():,.2f}")
    with col3:
        st.markdown("#### Données")
        st.write(f"**Début :** {prices.index[0].strftime('%Y-%m-%d')}")
        st.write(f"**Fin :** {prices.index[-1].strftime('%Y-%m-%d')}")
        st.write(f"**Jours de trading :** {len(prices)}")


# ==============================================================================
# ONGLET 2 — BACKTEST
# ==============================================================================
def render_backtest(ticker, asset_name, start_date, end_date, base_amount, frequency, fees):
    with st.spinner(f"Chargement des données pour {asset_name}..."):
        if '-USD' in ticker:
            prices = fetch_crypto_data(ticker, str(start_date), str(end_date))
        else:
            prices = fetch_stock_data(ticker, str(start_date), str(end_date))

    if prices.empty:
        st.error("Impossible de charger les données")
        return

    st.subheader("⚙️ Configuration de la stratégie")
    col1, col2, col3 = st.columns(3)
    with col1:
        strategy_frequency = st.selectbox(
            "Fréquence d'achat", options=['daily', 'weekly', 'monthly'],
            format_func=lambda x: {'daily': 'Quotidien', 'weekly': 'Hebdomadaire', 'monthly': 'Mensuel'}[x],
            index=['daily', 'weekly', 'monthly'].index(frequency), key='bt_freq',
        )
    with col2:
        strategy_amount = st.number_input(
            "Montant par achat ($)", min_value=10, max_value=10000, value=int(base_amount), step=10, key='bt_amount',
        )
    with col3:
        strategy_fees = st.slider(
            "Frais (%)", min_value=0.0, max_value=1.0, value=float(fees * 100), step=0.01, key='bt_fees',
        ) / 100

    st.subheader("🚀 Résultats du backtest")

    # Résultats persistés en session_state (comme les onglets Dynamic DCA / Robustesse) :
    # sans ça, interagir avec N'IMPORTE QUEL AUTRE widget de l'app (même un autre
    # onglet) ferait disparaître ces résultats au prochain rerun.
    bt_key = ('single', ticker, str(start_date), str(end_date), strategy_frequency, strategy_amount, strategy_fees)
    if st.button("Lancer le backtest", type="primary", key='bt_run_btn'):
        st.session_state['bt_single_key'] = bt_key

    if st.session_state.get('bt_single_key') == bt_key:
        with st.spinner("Backtest en cours..."):
            strategy = ClassicDCAStrategy(base_amount=strategy_amount, frequency=strategy_frequency)
            backtester = Backtester(prices, strategy, strategy_fees)
            result = backtester.run()

            metrics = result['metrics']
            portfolio_values = result['portfolio_values']
            total_invested_series = result['total_invested_series']
            trades = result['trades']

            st.markdown("### 📊 Métriques de performance")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("ROI Total", f"{metrics['roi']:.2f}%",
                          delta=f"${metrics['final_value'] - metrics['total_invested']:.2f}")
            with col2:
                st.metric(
                    "XIRR (annualisé)", f"{metrics['xirr']:.2f}%",
                    help="Rendement pondéré par le timing de chaque versement. "
                         f"Le CAGR lump-sum affiche {metrics['cagr']:.2f}% mais suppose "
                         "que tout a été investi au jour 1 — faux en DCA."
                )
            with col3:
                st.metric("Max Drawdown", f"{metrics['max_drawdown']:.2f}%")
            with col4:
                st.metric("Sharpe Ratio", f"{metrics['sharpe_ratio']:.2f}")

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total investi", f"${metrics['total_invested']:,.2f}")
            with col2:
                st.metric("Valeur finale", f"${metrics['final_value']:,.2f}")
            with col3:
                st.metric("Nombre d'achats", f"{metrics['num_trades']}")
            with col4:
                st.metric("Win rate", f"{metrics['win_rate']:.1f}%")

            st.markdown("### 📈 Évolution du portfolio")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=portfolio_values.index, y=portfolio_values, mode='lines',
                                     name='Valeur du portfolio', line=dict(color='#00D4AA', width=2)))
            fig.add_trace(go.Scatter(x=total_invested_series.index, y=total_invested_series, mode='lines',
                                     name='Total investi', line=dict(color='#FF6347', width=2, dash='dash')))
            if not trades.empty:
                fig.add_trace(go.Scatter(x=trades['date'], y=trades['price'] * trades['coins'], mode='markers',
                                         name='Achats', marker=dict(color='#FFD700', size=6, symbol='triangle-up')))
            fig.update_layout(height=500, xaxis_title="Date", yaxis_title="Valeur ($)",
                              hovermode='x unified', showlegend=True)
            st.plotly_chart(fig, width='stretch')

            st.markdown("### 💰 Prix avec points d'achat")
            fig_price = go.Figure()
            fig_price.add_trace(go.Scatter(x=prices.index, y=prices['Close'], mode='lines', name='Prix',
                                           line=dict(color='#00D4AA', width=2)))
            if not trades.empty:
                fig_price.add_trace(go.Scatter(x=trades['date'], y=trades['price'], mode='markers', name='Achats',
                                               marker=dict(color='#FFD700', size=8, symbol='triangle-up')))
            fig_price.update_layout(height=400, xaxis_title="Date", yaxis_title="Prix ($)", hovermode='x unified')
            st.plotly_chart(fig_price, width='stretch')

            if not trades.empty:
                st.markdown("### 📋 Historique des achats")
                trades_display = trades.copy()
                trades_display['date'] = trades_display['date'].dt.strftime('%Y-%m-%d')
                trades_display = trades_display.rename(columns={
                    'date': 'Date', 'price': 'Prix', 'amount': 'Montant', 'coins': 'Quantité', 'fees': 'Frais'
                })
                st.dataframe(trades_display[['Date', 'Prix', 'Montant', 'Quantité', 'Frais']],
                            width='stretch', hide_index=True)

    st.markdown("---")
    st.subheader("🔄 Comparaison de stratégies")
    st.markdown("Compare différentes fréquences et montants")

    cmp_key = ('cmp', ticker, str(start_date), str(end_date), fees)
    if st.button("Comparer les stratégies", key='bt_cmp_btn'):
        st.session_state['bt_cmp_key'] = cmp_key

    if st.session_state.get('bt_cmp_key') == cmp_key:
        with st.spinner("Comparaison en cours..."):
            strategies = [
                ClassicDCAStrategy(base_amount=50, frequency='daily'),
                ClassicDCAStrategy(base_amount=100, frequency='daily'),
                ClassicDCAStrategy(base_amount=350, frequency='weekly'),
                ClassicDCAStrategy(base_amount=700, frequency='weekly'),
                ClassicDCAStrategy(base_amount=1500, frequency='monthly'),
                ClassicDCAStrategy(base_amount=3000, frequency='monthly'),
            ]
            comparison_df = compare_strategies(prices, strategies, fees)
            st.dataframe(comparison_df, width='stretch', hide_index=True)

            fig_comp = go.Figure()
            for idx, row in comparison_df.iterrows():
                fig_comp.add_trace(go.Bar(x=[row['Stratégie']], y=[row['ROI %']],
                                          name=row['Stratégie'], marker_color='#00D4AA'))
            fig_comp.update_layout(height=400, xaxis_title="Stratégie", yaxis_title="ROI (%)", showlegend=False)
            st.plotly_chart(fig_comp, width='stretch')


# ==============================================================================
# ONGLET 3 — INDICATEURS
# ==============================================================================
def render_indicators(ticker, asset_name, start_date, end_date):
    signal_colors = {'strong_buy': '🟢', 'buy': '🟢', 'neutral': '🟡', 'sell': '🔴', 'strong_sell': '🔴'}
    asset_type = 'crypto' if '-USD' in ticker else 'stock'

    with st.spinner(f"Chargement des données pour {asset_name}..."):
        if asset_type == 'crypto':
            prices = fetch_crypto_data(ticker, str(start_date), str(end_date))
        else:
            prices = fetch_stock_data(ticker, str(start_date), str(end_date))

    if prices.empty:
        st.error("Impossible de charger les données")
        return

    long_close = None
    if asset_type == 'crypto':
        long_start = (pd.Timestamp(start_date) - pd.DateOffset(years=5)).date()
        with st.spinner("Chargement de l'historique long (200WMA)..."):
            long_prices = fetch_crypto_data(ticker, str(long_start), str(end_date))
        if not long_prices.empty:
            long_close = long_prices['Close']

    with st.spinner("Calcul des indicateurs..."):
        indicators = calculate_all_indicators(prices, asset_type, symbol=ticker, long_close=long_close)

    fear_greed = fetch_fear_greed_crypto() if asset_type == 'crypto' else None

    with st.spinner("Chargement des données macro..."):
        macro_indicators = fetch_macro_indicators()

    st.subheader("🎯 Signaux globaux")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        rsi_val = indicators['rsi'].iloc[-1]
        rsi_signal = get_signal_strength(rsi_val, 'rsi')
        st.metric("RSI (14)", f"{rsi_val:.1f}", delta=f"{signal_colors[rsi_signal]} {rsi_signal.replace('_', ' ').title()}")
    with col2:
        if fear_greed:
            fg_val = fear_greed['value']
            fg_signal = get_signal_strength(fg_val, 'fear_greed')
            st.metric("Fear & Greed", f"{fg_val}/100", delta=f"{signal_colors[fg_signal]} {fg_signal.replace('_', ' ').title()}")
    with col3:
        if asset_type == 'crypto' and 'mvrv_zscore' in indicators:
            mvrv_val = indicators['mvrv_zscore'].iloc[-1]
            if not pd.isna(mvrv_val):
                mvrv_signal = get_signal_strength(mvrv_val, 'mvrv_zscore')
                st.metric("MVRV Z-Score", f"{mvrv_val:.2f}", delta=f"{signal_colors[mvrv_signal]} {mvrv_signal.replace('_', ' ').title()}")
    with col4:
        macro_sentiment = get_macro_sentiment(macro_indicators)
        macro_colors = {'bullish': '🟢', 'neutral': '🟡', 'bearish': '🔴'}
        st.metric("Sentiment Macro", macro_sentiment.title(), delta=f"{macro_colors[macro_sentiment]} {macro_sentiment}")

    st.subheader("📊 Indicateurs disponibles")
    indicator_options = {
        'RSI': 'rsi', 'MACD': 'macd', 'Bandes de Bollinger': 'bollinger',
        'Moyennes Mobiles': 'moving_averages', 'ATR': 'atr', 'Stochastic RSI': 'stoch_rsi',
    }
    if asset_type == 'crypto':
        indicator_options.update({'200-Week MA': 'ma_200w', 'Régression Log': 'log_regression', 'MVRV Z-Score': 'mvrv_zscore'})
        if 'BTC' in ticker:
            indicator_options['Rainbow Chart'] = 'rainbow'

    selected_indicators = st.multiselect(
        "Sélectionne les indicateurs à afficher", options=list(indicator_options.keys()),
        default=['RSI', 'Bandes de Bollinger', 'Moyennes Mobiles'], key='ind_multiselect',
    )

    if selected_indicators:
        st.subheader(f"📈 {asset_name} avec indicateurs")
        fig = make_subplots(rows=1, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[1.0])
        fig.add_trace(go.Scatter(x=prices.index, y=prices['Close'], mode='lines', name='Prix',
                                 line=dict(color='#00D4AA', width=2)), row=1, col=1)

        colors = ['#FF6347', '#FFD700', '#9370DB', '#FF69B4', '#20B2AA', '#FFA07A']
        color_idx = 0

        for indicator_name in selected_indicators:
            indicator_key = indicator_options[indicator_name]

            if indicator_key in ('rsi', 'macd', 'atr', 'stoch_rsi', 'mvrv_zscore'):
                pass
            elif indicator_key == 'bollinger':
                fig.add_trace(go.Scatter(x=prices.index, y=indicators['bb_upper'], mode='lines', name='BB Upper',
                                         line=dict(color=colors[color_idx % len(colors)], width=1, dash='dash')), row=1, col=1)
                fig.add_trace(go.Scatter(x=prices.index, y=indicators['bb_lower'], mode='lines', name='BB Lower',
                                         line=dict(color=colors[color_idx % len(colors)], width=1, dash='dash'),
                                         fill='tonexty', fillcolor='rgba(255, 99, 71, 0.1)'), row=1, col=1)
                color_idx += 1
            elif indicator_key == 'moving_averages':
                for ma_name, ma_values in indicators['moving_averages'].items():
                    fig.add_trace(go.Scatter(x=prices.index, y=ma_values, mode='lines', name=ma_name,
                                             line=dict(color=colors[color_idx % len(colors)], width=1)), row=1, col=1)
                    color_idx += 1
            elif indicator_key == 'ma_200w' and 'ma_200w' in indicators:
                ma_200w = indicators['ma_200w']
                if not ma_200w.empty:
                    fig.add_trace(go.Scatter(x=prices.index, y=ma_200w, mode='lines', name='200-Week MA',
                                             line=dict(color='#00FF00', width=3)), row=1, col=1)
                else:
                    st.info(f"200-Week MA indisponible : moins de 200 semaines d'historique pour {asset_name} (l'actif est trop jeune).")
            elif indicator_key == 'log_regression' and 'log_reg_middle' in indicators:
                fig.add_trace(go.Scatter(x=indicators['log_reg_upper'].index, y=indicators['log_reg_upper'], mode='lines',
                                         name='Log Reg Upper', line=dict(color='#FF0000', width=1, dash='dot')), row=1, col=1)
                fig.add_trace(go.Scatter(x=indicators['log_reg_middle'].index, y=indicators['log_reg_middle'], mode='lines',
                                         name='Log Reg Middle', line=dict(color='#FFD700', width=2)), row=1, col=1)
                fig.add_trace(go.Scatter(x=indicators['log_reg_lower'].index, y=indicators['log_reg_lower'], mode='lines',
                                         name='Log Reg Lower', line=dict(color='#00FF00', width=1, dash='dot'),
                                         fill='tonexty', fillcolor='rgba(0, 255, 0, 0.05)'), row=1, col=1)
            elif indicator_key == 'rainbow' and 'rainbow' in indicators:
                for band in indicators['rainbow'].values():
                    fig.add_trace(go.Scatter(x=band['values'].index, y=band['values'], mode='lines',
                                             name=band['label'], line=dict(color=band['color'], width=1)), row=1, col=1)

        fig.update_layout(height=600, xaxis_title="Date", yaxis_title="Prix ($)", hovermode='x unified',
                          showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, width='stretch')

        if 'RSI' in selected_indicators:
            st.subheader("📊 RSI (Relative Strength Index)")
            fig_rsi = go.Figure()
            fig_rsi.add_trace(go.Scatter(x=indicators['rsi'].index, y=indicators['rsi'], mode='lines', name='RSI',
                                         line=dict(color='#00D4AA', width=2)))
            fig_rsi.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.5)
            fig_rsi.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.5)
            fig_rsi.add_hrect(y0=70, y1=100, fillcolor="red", opacity=0.1, line_width=0)
            fig_rsi.add_hrect(y0=0, y1=30, fillcolor="green", opacity=0.1, line_width=0)
            fig_rsi.update_layout(height=300, xaxis_title="Date", yaxis_title="RSI", yaxis_range=[0, 100], hovermode='x unified')
            st.plotly_chart(fig_rsi, width='stretch')

        if 'MACD' in selected_indicators:
            st.subheader("📊 MACD (12, 26, 9)")
            fig_macd = go.Figure()
            hist = indicators['macd_hist']
            fig_macd.add_trace(go.Bar(x=hist.index, y=hist, name='Histogramme',
                                      marker_color=['#00D4AA' if v >= 0 else '#FF6347' for v in hist.fillna(0)]))
            fig_macd.add_trace(go.Scatter(x=indicators['macd_line'].index, y=indicators['macd_line'], mode='lines',
                                          name='MACD', line=dict(color='#FFD700', width=2)))
            fig_macd.add_trace(go.Scatter(x=indicators['macd_signal'].index, y=indicators['macd_signal'], mode='lines',
                                          name='Signal', line=dict(color='#9370DB', width=2)))
            fig_macd.add_hline(y=0, line_color="gray", opacity=0.5)
            fig_macd.update_layout(height=300, xaxis_title="Date", yaxis_title="MACD", hovermode='x unified')
            st.plotly_chart(fig_macd, width='stretch')

        if 'Stochastic RSI' in selected_indicators:
            st.subheader("📊 Stochastic RSI")
            fig_stoch = go.Figure()
            fig_stoch.add_trace(go.Scatter(x=indicators['stoch_rsi_k'].index, y=indicators['stoch_rsi_k'], mode='lines',
                                           name='%K', line=dict(color='#00D4AA', width=2)))
            fig_stoch.add_trace(go.Scatter(x=indicators['stoch_rsi_d'].index, y=indicators['stoch_rsi_d'], mode='lines',
                                           name='%D', line=dict(color='#FFD700', width=2)))
            fig_stoch.add_hrect(y0=80, y1=100, fillcolor="red", opacity=0.1, line_width=0)
            fig_stoch.add_hrect(y0=0, y1=20, fillcolor="green", opacity=0.1, line_width=0)
            fig_stoch.update_layout(height=300, xaxis_title="Date", yaxis_title="Stoch RSI", yaxis_range=[0, 100], hovermode='x unified')
            st.plotly_chart(fig_stoch, width='stretch')

        if 'ATR' in selected_indicators:
            st.subheader("📊 ATR (Average True Range)")
            fig_atr = go.Figure()
            fig_atr.add_trace(go.Scatter(x=indicators['atr'].index, y=indicators['atr'], mode='lines', name='ATR (14)',
                                         line=dict(color='#FFA07A', width=2)))
            fig_atr.update_layout(height=300, xaxis_title="Date", yaxis_title="ATR ($)", hovermode='x unified')
            st.plotly_chart(fig_atr, width='stretch')

        if 'MVRV Z-Score' in selected_indicators and 'mvrv_zscore' in indicators:
            st.subheader("📊 MVRV Z-Score (approximation)")
            mvrv = indicators['mvrv_zscore']
            if mvrv.notna().any():
                fig_mvrv = go.Figure()
                fig_mvrv.add_trace(go.Scatter(x=mvrv.index, y=mvrv, mode='lines', name='MVRV Z-Score',
                                              line=dict(color='#9370DB', width=2)))
                fig_mvrv.add_hline(y=-1.5, line_dash="dash", line_color="green", opacity=0.5)
                fig_mvrv.add_hline(y=2.0, line_dash="dash", line_color="red", opacity=0.5)
                fig_mvrv.add_hline(y=0, line_color="gray", opacity=0.3)
                fig_mvrv.add_hrect(y0=2.0, y1=max(4.0, float(mvrv.max())), fillcolor="red", opacity=0.08, line_width=0)
                fig_mvrv.add_hrect(y0=min(-4.0, float(mvrv.min())), y1=-1.5, fillcolor="green", opacity=0.08, line_width=0)
                fig_mvrv.update_layout(height=300, xaxis_title="Date", yaxis_title="Z-Score", hovermode='x unified')
                st.plotly_chart(fig_mvrv, width='stretch')
                st.caption(
                    "⚠️ Approximation : le vrai MVRV utilise la realized cap on-chain. "
                    "Ici c'est un proxy basé sur la moyenne mobile 365j du prix. "
                    "Les seuils sont ceux d'un Z-Score statistique (-1.5 / +2.0), "
                    "pas ceux du MVRV on-chain (0 / 7)."
                )
            else:
                st.info("MVRV Z-Score indisponible : il faut ~730 jours de données (2 fenêtres de 365j). Élargis la période dans la barre latérale.")

    st.subheader("🌍 Indicateurs Macro")
    MACRO_LAYOUT = [
        ('fed_funds', '#FF6347', '', '%', 2, 15), ('yield_10y', '#FFD700', '', '%', 2, 15),
        ('cpi', '#9370DB', '', '', 1, 15), ('m2', '#20B2AA', '$', ' Md', 0, 15),
        ('dxy', '#00D4AA', '', '', 2, 5), ('vix', '#FF69B4', '', '', 2, 5),
    ]
    available = [m for m in MACRO_LAYOUT if m[0] in macro_indicators]
    if not available:
        st.warning("Aucune donnée macro disponible (FRED et yfinance injoignables)")

    for row_start in range(0, len(available), 3):
        cols = st.columns(3)
        for col, (key, color, prefix, suffix, decimals, years) in zip(cols, available[row_start:row_start + 3]):
            with col:
                ind = macro_indicators[key]
                st.metric(ind['name'], f"{prefix}{ind['value']:,.{decimals}f}{suffix}", delta=f"{ind['yoy_change']:+.2f}% sur 1 an")
                data = ind['data']
                cutoff = data.index[-1] - pd.DateOffset(years=years)
                data = data.loc[data.index >= cutoff]
                fig_macro = go.Figure()
                fig_macro.add_trace(go.Scatter(x=data.index, y=data['value'], mode='lines', name=ind['name'],
                                               line=dict(color=color, width=2)))
                fig_macro.update_layout(height=250, margin=dict(l=10, r=10, t=10, b=10),
                                        xaxis_title=None, yaxis_title=None, hovermode='x unified')
                st.plotly_chart(fig_macro, width='stretch')
                st.caption(f"Dernière obs. : {ind['last_date']:%Y-%m-%d}")

    st.subheader("📋 Résumé des signaux")
    signals_data = []
    rsi_val = indicators['rsi'].iloc[-1]
    signals_data.append({'Indicateur': 'RSI (14)', 'Valeur': f"{rsi_val:.1f}",
                         'Signal': get_signal_strength(rsi_val, 'rsi').replace('_', ' ').title()})
    if fear_greed:
        fg_val = fear_greed['value']
        signals_data.append({'Indicateur': 'Fear & Greed', 'Valeur': f"{fg_val}/100",
                             'Signal': get_signal_strength(fg_val, 'fear_greed').replace('_', ' ').title()})
    if asset_type == 'crypto' and 'mvrv_zscore' in indicators:
        mvrv_val = indicators['mvrv_zscore'].iloc[-1]
        if not pd.isna(mvrv_val):
            signals_data.append({'Indicateur': 'MVRV Z-Score', 'Valeur': f"{mvrv_val:.2f}",
                                 'Signal': get_signal_strength(mvrv_val, 'mvrv_zscore').replace('_', ' ').title()})
    if asset_type == 'crypto' and not indicators.get('ma_200w', pd.Series(dtype=float)).empty:
        ma_200w_val = indicators['ma_200w'].iloc[-1]
        if not pd.isna(ma_200w_val):
            current_price = prices['Close'].iloc[-1]
            signal = 'Buy (sous la 200WMA)' if current_price < ma_200w_val else 'Neutral (au-dessus)'
            signals_data.append({'Indicateur': '200-Week MA', 'Valeur': f"${ma_200w_val:,.2f}", 'Signal': signal})
    macro_sentiment = get_macro_sentiment(macro_indicators)
    signals_data.append({'Indicateur': 'Sentiment Macro', 'Valeur': '-', 'Signal': macro_sentiment.title()})

    signals_df = pd.DataFrame(signals_data)
    st.dataframe(signals_df, width='stretch', hide_index=True)


# ==============================================================================
# ONGLET 4 — DYNAMIC DCA
# ==============================================================================
def render_dynamic_dca(ticker, asset_name, start_date, end_date, base_amount, frequency, fees):
    st.markdown("Compare le DCA classique aux stratégies conditionnelles intelligentes. **Zero Look-Ahead Bias garanti** (Drawdown calculé via `expanding().max()`).")

    st.warning(
        "⚠️ **Attention : ces résultats sont calculés sur une seule fenêtre temporelle.** "
        "Va voir l'onglet 🛡️ Robustesse pour la distribution réelle des résultats "
        "sur plusieurs fenêtres glissantes."
    )

    asset_type = 'crypto' if '-USD' in ticker else 'stock'

    with st.spinner(f"Chargement des données pour {asset_name}..."):
        if asset_type == 'crypto':
            prices = fetch_crypto_data(ticker, str(start_date), str(end_date))
            fg_history = fetch_fear_greed_history(days=(end_date - start_date).days + 30)
            long_start = (pd.Timestamp(start_date) - pd.DateOffset(years=5)).date()
            long_prices = fetch_crypto_data(ticker, str(long_start), str(end_date))
        else:
            prices = fetch_stock_data(ticker, str(start_date), str(end_date))
            fg_history = None
            long_start = (pd.Timestamp(start_date) - pd.DateOffset(years=5)).date()
            long_prices = fetch_stock_data(ticker, str(long_start), str(end_date))
        vix_history = fetch_vix_history(str(long_start), str(end_date))

    if prices.empty:
        st.error("Impossible de charger les données")
        return

    if asset_type != 'crypto':
        st.info(
            "ℹ️ Actif non-crypto : le **Kairos Score** est désactivé (il s'appuie sur le "
            "Fear & Greed et la 200WMA, indisponibles hors crypto). **Drawdown** et "
            "**RSI** restent pleinement opérationnels."
        )

    st.subheader("⚙️ Paramètres de la simulation")
    col1, col2, col3 = st.columns(3)
    with col1:
        sim_amount = st.number_input("Montant de base ($)", min_value=10, value=int(base_amount), step=10, key='dyn_amount')
    with col2:
        sim_freq = st.selectbox(
            "Fréquence", options=['daily', 'weekly', 'monthly'],
            format_func=lambda x: {'daily': 'Quotidien', 'weekly': 'Hebdomadaire', 'monthly': 'Mensuel'}[x],
            index=['daily', 'weekly', 'monthly'].index(frequency), key='dyn_freq',
        )
    with col3:
        sim_fees = st.slider("Frais (%)", min_value=0.0, max_value=1.0, value=float(fees * 100), step=0.01, key='dyn_fees') / 100

    is_crypto = asset_type == 'crypto'

    st.markdown("**Stratégies à comparer :**")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        use_classic = st.checkbox("DCA Classique", value=True, key='dyn_use_classic')
    with col2:
        use_drawdown = st.checkbox("Drawdown-Based", value=True, help="x2 à -20%, x3 à -40%, x5 à -60%", key='dyn_use_drawdown')
    with col3:
        use_rsi = st.checkbox("RSI-Based", value=False, help="x2.5 si RSI<30, x0.5 si RSI>60", key='dyn_use_rsi')
    with col4:
        use_kairos = st.checkbox(
            "Kairos Score", value=is_crypto, disabled=not is_crypto,
            help="Score combiné F&G + 200WMA + RSI (Crypto uniquement)", key='dyn_use_kairos',
        )
        if not is_crypto:
            st.caption("⚠️ Indisponible pour les actions/ETF")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        use_vault = st.checkbox(
            "🔒 Coffre", value=False,
            help="Tout le budget est mis en réserve tant que l'indicateur ne déclenche pas. "
                 "Au déclenchement, toute la réserve accumulée est investie d'un coup. "
                 "Le capital versé reste budget × nb de périodes, quoi qu'il arrive.",
            key='dyn_use_vault',
        )
    with col2:
        vault_indicator_options = ['drawdown', 'rsi', 'vix'] + (['fear_greed'] if is_crypto else [])
        vault_indicator = st.selectbox(
            "Déclencheur", options=vault_indicator_options,
            format_func=lambda k: VaultDCAStrategy.INDICATORS[k]['label'],
            disabled=not use_vault, key='vault_indicator',
        )
    with col3:
        _spec = VaultDCAStrategy.INDICATORS[vault_indicator]
        vault_threshold = st.number_input(
            "Seuil", min_value=float(_spec['lo']), max_value=float(_spec['hi']), value=float(_spec['default']),
            step=0.01 if vault_indicator == 'drawdown' else 1.0, disabled=not use_vault, help=_spec['desc'],
            key=f'vault_threshold_{vault_indicator}',
        )
    with col4:
        vault_rearm = st.checkbox(
            "Réarmement", value=False, disabled=not use_vault,
            help="Coché : un seul déploiement par épisode (tire au début, peut rater le creux). "
                 "Décoché (recommandé) : redéploie tant que la condition reste vraie.",
            key='vault_rearm',
        )
    if use_vault and not is_crypto:
        st.caption("ℹ️ Fear & Greed indisponible hors crypto : reste à 50 en continu (option masquée ci-dessus).")

    st.caption(
        "⚠️ Les stratégies dynamiques n'investissent pas le même capital total que le DCA "
        "classique (c'est le principe : on met plus quand c'est bas — sauf le Coffre, qui "
        "verse toujours exactement budget × nb de périodes). Compare le **XIRR**, "
        "pas le ROI ni la valeur finale, entre stratégies à capital différent."
    )

    def _build_manual_strategies():
        strategies = []
        if use_classic:
            strategies.append(ClassicDCAStrategy(base_amount=sim_amount, frequency=sim_freq))
        if use_drawdown:
            strategies.append(DrawdownDCAStrategy(base_amount=sim_amount, frequency=sim_freq))
        if use_rsi:
            strategies.append(RSIDCAStrategy(base_amount=sim_amount, frequency=sim_freq))
        if use_kairos:
            strategies.append(KairosScoreDCAStrategy(base_amount=sim_amount, frequency=sim_freq))
        if use_vault:
            strategies.append(VaultDCAStrategy(
                base_budget=sim_amount, indicator=vault_indicator, threshold=vault_threshold,
                frequency=sim_freq, rearm=vault_rearm,
            ))
        return strategies

    def _build_auto_strategies():
        strategies = [
            ClassicDCAStrategy(base_amount=sim_amount, frequency=sim_freq),
            DrawdownDCAStrategy(base_amount=sim_amount, frequency=sim_freq),
            RSIDCAStrategy(base_amount=sim_amount, frequency=sim_freq),
        ]
        if is_crypto:
            strategies.append(KairosScoreDCAStrategy(base_amount=sim_amount, frequency=sim_freq))
        for indicator in ['drawdown', 'rsi', 'vix'] + (['fear_greed'] if is_crypto else []):
            strategies.append(VaultDCAStrategy(base_budget=sim_amount, indicator=indicator, frequency=sim_freq, rearm=False))
        return strategies

    manual_key = (use_classic, use_drawdown, use_rsi, use_kairos, use_vault, vault_indicator, vault_threshold, vault_rearm)
    params_key = ('manual', ticker, str(start_date), str(end_date), sim_amount, sim_freq, sim_fees, manual_key)
    auto_params_key = ('auto', ticker, str(start_date), str(end_date), sim_amount, sim_freq, sim_fees)

    col_run1, col_run2 = st.columns(2)
    with col_run1:
        if st.button("🚀 Lancer la comparaison", type="primary", key='dyn_run_btn'):
            st.session_state['dyn_params'] = params_key
    with col_run2:
        if st.button(
            "🎲 Test automatique (Top 3)", key='dyn_auto_btn',
            help="Lance un panel fixe (Classique, Drawdown, RSI, Kairos si crypto, "
                 "et le Coffre sur ses 3-4 déclencheurs) et classe le résultat."
        ):
            st.session_state['dyn_params'] = auto_params_key

    active_key = st.session_state.get('dyn_params')
    auto_mode = active_key == auto_params_key

    if active_key in (params_key, auto_params_key):
        strategies_to_test = _build_auto_strategies() if auto_mode else _build_manual_strategies()

        if not strategies_to_test:
            st.warning("⚠️ Coche au moins une stratégie à comparer.")
            return

        with st.spinner("Calcul des stratégies en cours (Zero Look-Ahead Bias)..."):
            comparison_df = compare_strategies(prices, strategies_to_test, sim_fees, fg_history, long_prices, vix_history)

            if auto_mode:
                st.markdown("### 🏅 Top 3 (cette fenêtre)")
                top3 = comparison_df.sort_values('XIRR %', ascending=False).head(3).reset_index(drop=True)
                cols = st.columns(3)
                for i, col in enumerate(cols):
                    if i >= len(top3):
                        continue
                    row = top3.iloc[i]
                    with col:
                        st.metric(f"#{i + 1}", row['Stratégie'], delta=f"{row['XIRR %']:.2f}% XIRR")
                st.caption(
                    "⚠️ Classement calculé sur **cette seule fenêtre** : ce n'est pas une prédiction. "
                    "Une stratégie en tête ici peut être dernière sur une autre période — "
                    "vérifie sur 🛡️ Robustesse avant d'en tirer une conclusion."
                )

            st.markdown("### 📋 Tableau comparatif (une seule fenêtre)")
            display_df = comparison_df.copy()
            display_df['Investi'] = display_df['Investi'].apply(lambda x: f"${x:,.0f}")
            display_df['Valeur Finale'] = display_df['Valeur Finale'].apply(lambda x: f"${x:,.0f}")
            display_df['ROI %'] = display_df['ROI %'].apply(lambda x: f"{x:.2f}%")
            display_df['XIRR %'] = display_df['XIRR %'].apply(lambda x: f"{x:.2f}%")
            display_df['Max DD %'] = display_df['Max DD %'].apply(lambda x: f"{x:.2f}%")
            display_df['Coût de revient'] = display_df['Coût de revient'].apply(
                lambda x: f"${x:,.0f}" if x >= 1000 else f"${x:,.2f}"
            )
            st.dataframe(display_df, width='stretch', hide_index=True)

            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(
                x=comparison_df['Stratégie'], y=comparison_df['XIRR %'],
                text=comparison_df['XIRR %'].apply(lambda x: f"{x:.1f}%"), textposition='auto',
                marker_color='#2a78d6'
            ))
            fig_bar.update_layout(height=400, title="Rendement Annualisé (XIRR) par Stratégie",
                                  xaxis_title="Stratégie", yaxis_title="XIRR (%)", showlegend=False)
            st.plotly_chart(fig_bar, width='stretch')

            st.markdown("### 📈 Toutes les stratégies, une seule courbe chacune")
            _ms_all = Backtester(prices, strategies_to_test[0], sim_fees, fg_history, long_prices, vix_history).build_market_state()
            fig_overlay = go.Figure()
            for strat in strategies_to_test:
                res = Backtester(prices, strat, sim_fees, fg_history, long_prices, vix_history).run(market_state=_ms_all)
                label = getattr(strat, 'label', strat.__class__.__name__)
                if isinstance(strat, VaultDCAStrategy):
                    label = f"Coffre [{VaultDCAStrategy.INDICATORS[strat.indicator]['label']}]"
                pv = res['portfolio_values']
                fig_overlay.add_trace(go.Scatter(
                    x=pv.index, y=pv, mode='lines', name=label,
                    hovertemplate=f"<b>{label}</b><br>%{{x|%Y-%m-%d}} : $%{{y:,.0f}}<extra></extra>",
                ))
            fig_overlay.update_layout(
                height=500, xaxis_title="Date", yaxis_title="Valeur du portefeuille ($)", hovermode='x unified',
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            )
            st.plotly_chart(fig_overlay, width='stretch')
            st.caption(
                "💡 Clique un nom dans la légende pour cacher/montrer sa courbe, double-clique pour "
                "l'isoler. La courbe la plus haute à la fin n'a gagné que sur **cette fenêtre précise** — "
                "voir 🛡️ Robustesse pour savoir si ça se reproduit ailleurs."
            )

            st.markdown("---")
            labels = comparison_df['Stratégie'].tolist()
            detail_idx = st.selectbox(
                "Stratégie à détailler", options=list(range(len(labels))), format_func=lambda i: labels[i],
                index=1 if (isinstance(strategies_to_test[0], ClassicDCAStrategy) and len(labels) > 1) else 0,
                key='dyn_detail',
            )
            st.subheader(f"🔬 Détail : {labels[detail_idx]}")

            backtester = Backtester(prices, strategies_to_test[detail_idx], sim_fees, fg_history, long_prices, vix_history)
            detail_result = backtester.run()

            trades = detail_result['trades']
            portfolio_values = detail_result['portfolio_values']
            total_invested_series = detail_result['total_invested_series']
            market_state = detail_result['market_state']

            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Investi", f"${detail_result['metrics']['total_invested']:,.0f}")
                st.metric("Valeur Finale", f"${detail_result['metrics']['final_value']:,.0f}")
            with col2:
                st.metric("XIRR", f"{detail_result['metrics']['xirr']:.2f}%")
                st.metric("Max Drawdown", f"{detail_result['metrics']['max_drawdown']:.2f}%")

            fig_price = go.Figure()
            fig_price.add_trace(go.Scatter(x=market_state.index, y=market_state['Close'], mode='lines', name='Prix',
                                           line=dict(color='#00D4AA', width=2)))
            if not trades.empty:
                min_amt, max_amt = trades['amount'].min(), trades['amount'].max()
                sizes = 5 + 10 * ((trades['amount'] - min_amt) / (max_amt - min_amt)) if max_amt > min_amt else 10
                colors = []
                for mult in trades['multiplier']:
                    if mult >= 3.0:
                        colors.append('#00FF00')
                    elif mult >= 1.5:
                        colors.append('#FFD700')
                    else:
                        colors.append('#FF6347')
                fig_price.add_trace(go.Scatter(
                    x=trades['date'], y=trades['price'], mode='markers', name='Achats (taille = montant)',
                    marker=dict(color=colors, size=sizes, line=dict(width=1, color='white')),
                    hovertemplate="<b>Date:</b> %{x}<br><b>Prix:</b> $%{y:.2f}<br><b>Montant:</b> $%{customdata[0]:.0f}<br><b>Multiplicateur:</b> x%{customdata[1]:.1f}<extra></extra>",
                    customdata=trades[['amount', 'multiplier']].values,
                ))
            fig_price.update_layout(height=500, title="Prix d'achat et points d'entrée dynamiques",
                                    xaxis_title="Date", yaxis_title="Prix ($)", hovermode='closest')
            st.plotly_chart(fig_price, width='stretch')

            fig_port = go.Figure()
            fig_port.add_trace(go.Scatter(x=portfolio_values.index, y=portfolio_values, mode='lines',
                                          name='Valeur Portfolio', line=dict(color='#00D4AA', width=2)))
            fig_port.add_trace(go.Scatter(x=total_invested_series.index, y=total_invested_series, mode='lines',
                                          name='Total Investi', line=dict(color='#FF6347', width=2, dash='dash')))
            fig_port.update_layout(height=400, title="Évolution de la valeur vs capital investi",
                                   xaxis_title="Date", yaxis_title="Valeur ($)", hovermode='x unified')
            st.plotly_chart(fig_port, width='stretch')

            if not trades.empty:
                st.markdown("### 🎚️ Répartition des mises")
                mult_counts = trades['multiplier'].round(2).value_counts().sort_index()
                recap = pd.DataFrame({
                    'Multiplicateur': [f"x{m:g}" for m in mult_counts.index],
                    'Nb achats': mult_counts.values,
                    '% des achats': (mult_counts.values / len(trades) * 100).round(1),
                    'Capital engagé': [
                        f"${trades.loc[trades['multiplier'].round(2) == m, 'amount'].sum():,.0f}" for m in mult_counts.index
                    ],
                })
                st.dataframe(recap, width='stretch', hide_index=True)


# ==============================================================================
# ONGLET 5 — ROBUSTESSE
# ==============================================================================
COLOR_POS = "#2a78d6"
COLOR_NEG = "#e34948"
COLOR_MID = "#f0efec"
INK = "#1f1f1e"
WHITE = "#ffffff"


def _hex_to_rgb(color: str) -> tuple:
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def _relative_luminance(rgb: tuple) -> float:
    def linear(c: float) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(rgb_a: tuple, rgb_b: tuple) -> float:
    la, lb = _relative_luminance(rgb_a), _relative_luminance(rgb_b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def cell_background(z: float, zmax: float) -> tuple:
    t = min(max((z + zmax) / (2 * zmax), 0.0), 1.0)
    (a, b), local = ((COLOR_NEG, COLOR_MID), t / 0.5) if t <= 0.5 else ((COLOR_MID, COLOR_POS), (t - 0.5) / 0.5)
    ra, rb = _hex_to_rgb(a), _hex_to_rgb(b)
    return tuple(ra[k] + (rb[k] - ra[k]) * local for k in range(3))


def text_color_for(background: tuple) -> str:
    ink_ratio = _contrast_ratio(background, _hex_to_rgb(INK))
    white_ratio = _contrast_ratio(background, _hex_to_rgb(WHITE))
    return INK if ink_ratio >= white_ratio else WHITE


def render_robustness(ticker, asset_name, end_date, frequency, fees):
    st.markdown("""
Chaque configuration de la grille est testée sur **toutes les fenêtres glissantes** de l'historique,
contre le DCA classique sur la même fenêtre et avec exactement les mêmes versements.

Aucune configuration ne gagne à tous les coups. Cette carte ne te donne pas un « meilleur réglage » :
elle te montre **la distribution des résultats** de chaque règle, pour que tu choisisses en connaissant le risque.
""")

    asset_type = 'crypto' if '-USD' in ticker else 'stock'
    freq_fr = {'daily': 'quotidien', 'weekly': 'hebdomadaire', 'monthly': 'mensuel'}[frequency]

    col1, col2, col3 = st.columns(3)
    with col1:
        window_years = st.selectbox("Durée de chaque fenêtre", options=[2, 3, 5], index=1,
                                    format_func=lambda y: f"{y} ans", key='rob_window_years')
    with col2:
        step_months = st.selectbox("Décalage entre deux fenêtres", options=[3, 6, 12], index=1,
                                   format_func=lambda m: f"{m} mois", key='rob_step_months')
    with col3:
        st.markdown(f"**{asset_name}** · DCA {freq_fr} · frais {fees * 100:.2f}%")
        st.caption("Le budget n'a aucun effet sur les écarts relatifs (tout est proportionnel), il n'est donc pas demandé.")

    @st.cache_data(show_spinner=False)
    def cached_map(ticker, asset_type, end, frequency, fees, window_years, step_months):
        if asset_type == 'crypto':
            history = fetch_crypto_data(ticker, "2010-01-01", end)
        else:
            history = fetch_stock_data(ticker, "1990-01-01", end)
        if history.empty:
            raise ValueError("Impossible de charger l'historique")
        summary, rows = compute_robustness_map(
            history, build_grid(), frequency=frequency, fees=fees,
            window_years=window_years, step_months=step_months,
        )
        meta = {
            'history_start': history.index[0], 'history_end': history.index[-1],
            'span_years': (history.index[-1] - history.index[0]).days / 365.25,
        }
        return summary, rows, meta

    with st.spinner(f"Calcul de la carte sur tout l'historique de {asset_name}..."):
        try:
            summary, rows, meta = cached_map(ticker, asset_type, str(end_date), frequency, fees, window_years, step_months)
        except ValueError as e:
            st.warning(f"⚠️ {e}. Essaie une durée de fenêtre plus courte.")
            return

    n_windows = rows['window_start'].nunique()
    independent = (meta['span_years'] - 1) / window_years
    stability = rank_stability(rows)

    st.subheader("🎯 Vue d'ensemble")
    st.caption(
        f"Historique {meta['history_start']:%Y-%m-%d} → {meta['history_end']:%Y-%m-%d} "
        f"({meta['span_years']:.1f} ans, la 1re année sert à amorcer l'ATH). "
        f"Grille : réserve 20-60% × seuil -15% à -45%, déploiement 100% de la réserve, sans réarmement."
    )

    n_majority = int((summary['win_rate'] > 50).sum())
    n_positive = int((summary['gap_median'] > 0).sum())
    best = summary.iloc[0]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Fenêtres testées", n_windows,
             help=f"Elles se chevauchent : cela représente environ {independent:.1f} périodes de {window_years} ans réellement indépendantes.")
    k2.metric("Périodes indépendantes", f"≈ {independent:.1f}")
    k3.metric("Configs gagnantes > 50% du temps", f"{n_majority} / {len(summary)}")
    k4.metric("Meilleur écart médian", f"{best['gap_median']:+.2f}%",
             help="Écart de valeur finale contre le DCA classique, médiane sur toutes les fenêtres.")

    if n_positive == 0:
        st.info(f"ℹ️ **Sur {asset_name}, aucune configuration de réserve n'a fait mieux que le DCA classique en médiane.** Garder du cash de côté a coûté plus qu'il n'a rapporté sur la majorité des fenêtres.")
    else:
        st.info(f"ℹ️ **{n_positive} configuration(s) sur {len(summary)} ont un écart médian positif**, dont {n_majority} battent le classique dans plus de la moitié des fenêtres. Regarde leur pire fenêtre avant d'en retenir une.")

    if independent < 4:
        st.warning(f"⚠️ **Échantillon mince** : ≈ {independent:.1f} périodes indépendantes seulement. Un pourcentage de victoires calculé sur si peu de marchés distincts reste très incertain.")

    if stability is None:
        st.caption("Stabilité du classement : historique insuffisant pour comparer deux périodes séparées.")
    else:
        rho = stability['spearman']
        if rho >= 0.5:
            verdict = "le classement est **stable** dans le temps"
        elif rho >= 0:
            verdict = "le classement n'est **que faiblement** reproductible"
        else:
            verdict = "le classement s'est **inversé** : les règles les mieux placées avant ont fait partie des moins bonnes ensuite"
        msg = (
            f"**Stabilité du classement : {rho:+.2f}** (corrélation de rang). Les {stability['n_early']} fenêtres "
            f"terminées avant {stability['split_date']:%Y-%m} et les {stability['n_late']} commencées après ne "
            f"se chevauchent pas : {verdict}. La meilleure règle de la première période est "
            f"{stability['best_early_rank_late']}e sur {stability['n_configs']} dans la seconde."
        )
        (st.info if rho >= 0.5 else st.warning)(msg)

    st.subheader("🗺️ Réserve × seuil de déclenchement")
    reserves = sorted(summary['reserve_ratio'].unique())
    thresholds = sorted(summary['dip_threshold'].unique(), reverse=True)
    grid_gap = summary.pivot(index='reserve_ratio', columns='dip_threshold', values='gap_median').loc[reserves, thresholds]
    grid_win = summary.pivot(index='reserve_ratio', columns='dip_threshold', values='win_rate').loc[reserves, thresholds]
    grid_worst = summary.pivot(index='reserve_ratio', columns='dip_threshold', values='gap_worst').loc[reserves, thresholds]

    x_labels = [f"{t * 100:.0f}%" for t in thresholds]
    y_labels = [f"{r * 100:.0f}%" for r in reserves]
    zmax = max(abs(grid_gap.values.min()), abs(grid_gap.values.max()), 0.01)
    customdata = [[[grid_win.iloc[i, j], grid_worst.iloc[i, j]] for j in range(len(thresholds))] for i in range(len(reserves))]

    fig_heat = go.Figure(go.Heatmap(
        z=grid_gap.values, x=x_labels, y=y_labels, zmid=0, zmin=-zmax, zmax=zmax,
        colorscale=[[0.0, COLOR_NEG], [0.5, COLOR_MID], [1.0, COLOR_POS]], customdata=customdata,
        hovertemplate=("Réserve %{y} · seuil %{x}<br>Écart médian : %{z:+.2f}%<br>"
                       "Bat le classique : %{customdata[0]:.0f}% des fenêtres<br>Pire fenêtre : %{customdata[1]:+.2f}%<extra></extra>"),
        xgap=2, ygap=2, colorbar=dict(title="Écart médian (%)", ticksuffix="%"),
    ))
    for i, reserve_label in enumerate(y_labels):
        for j, threshold_label in enumerate(x_labels):
            z = grid_gap.iloc[i, j]
            fig_heat.add_annotation(x=threshold_label, y=reserve_label,
                                    text=f"{z:+.2f}%<br>{grid_win.iloc[i, j]:.0f}% vict.", showarrow=False,
                                    font=dict(color=text_color_for(cell_background(z, zmax)), size=12))
    fig_heat.update_layout(height=380, xaxis_title="Seuil de drawdown qui déclenche le déploiement",
                           yaxis_title="Part du budget mise en réserve", margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_heat, width='stretch')
    st.caption("Bleu : fait mieux que le DCA classique en médiane · rouge : moins bien · gris : équivalent. Chaque case indique l'écart médian et le % de fenêtres gagnées.")

    st.subheader("📋 Distribution par configuration")
    table = pd.DataFrame({
        'Réserve (%)': summary['reserve_ratio'] * 100, 'Seuil (%)': summary['dip_threshold'] * 100,
        'Fenêtres gagnées (%)': summary['win_rate'], 'Écart médian (%)': summary['gap_median'],
        'Pire fenêtre (%)': summary['gap_worst'], 'Meilleure fenêtre (%)': summary['gap_best'],
        'Dispersion (pts)': summary['gap_std'], 'Écart XIRR médian (pp)': summary['xirr_excess_median'],
        'Cash dormant moyen (%)': summary['cash_share_avg'],
    })
    st.dataframe(table, width='stretch', hide_index=True, column_config={
        'Réserve (%)': st.column_config.NumberColumn(format="%.0f"), 'Seuil (%)': st.column_config.NumberColumn(format="%.0f"),
        'Fenêtres gagnées (%)': st.column_config.NumberColumn(format="%.0f"), 'Écart médian (%)': st.column_config.NumberColumn(format="%.2f"),
        'Pire fenêtre (%)': st.column_config.NumberColumn(format="%.2f"), 'Meilleure fenêtre (%)': st.column_config.NumberColumn(format="%.2f"),
        'Dispersion (pts)': st.column_config.NumberColumn(format="%.2f"), 'Écart XIRR médian (pp)': st.column_config.NumberColumn(format="%.2f"),
        'Cash dormant moyen (%)': st.column_config.NumberColumn(format="%.1f"),
    })
    st.caption("Écart = valeur finale (coins + cash) de la règle ÷ valeur finale du DCA classique − 1, sur la même fenêtre. Cash dormant moyen = part moyenne du portefeuille restée en cash. Trié par écart médian décroissant.")

    st.subheader("🔍 Quand une règle fonctionne-t-elle ?")
    options = list(summary.index)
    choice = st.selectbox(
        "Configuration", options=options,
        format_func=lambda i: (f"Réserve {summary.loc[i, 'reserve_ratio'] * 100:.0f}% · "
                               f"seuil {summary.loc[i, 'dip_threshold'] * 100:.0f}% "
                               f"(médiane {summary.loc[i, 'gap_median']:+.2f}%)"),
        key='rob_config_choice',
    )
    sel = summary.loc[choice]
    detail = rows[(rows['reserve_ratio'] == sel['reserve_ratio']) & (rows['dip_threshold'] == sel['dip_threshold'])].sort_values('window_start')

    fig_detail = go.Figure(go.Bar(
        x=detail['window_start'], y=detail['value_gap_pct'],
        marker_color=[COLOR_POS if v > 0 else COLOR_NEG for v in detail['value_gap_pct']],
        customdata=detail[['window_end', 'xirr', 'classic_xirr']].assign(
            window_end=detail['window_end'].dt.strftime('%Y-%m-%d')
        ).values,
        hovertemplate=("Fenêtre %{x|%Y-%m-%d} → %{customdata[0]}<br>Écart de valeur : %{y:+.2f}%<br>"
                       "XIRR règle %{customdata[1]:.2f}% · classique %{customdata[2]:.2f}%<extra></extra>"),
    ))
    fig_detail.add_hline(y=0, line_color="#b5b4af", line_width=1)
    fig_detail.update_layout(height=360, bargap=0.15, xaxis_title="Début de la fenêtre", yaxis_title="Écart vs DCA classique (%)",
                             yaxis_ticksuffix="%", margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
    st.plotly_chart(fig_detail, width='stretch')
    st.caption("Chaque barre est une fenêtre. Des barres voisines partagent la plupart de leurs données : une série de barres bleues consécutives correspond souvent à un seul épisode de marché.")

    st.markdown("---")
    st.caption("⚠️ Choisir la meilleure ligne de ce tableau reste une sélection sur le passé : sur 20 règles, l'une d'elles finira en tête même par hasard. Fie-toi à la stabilité du classement et à la pire fenêtre, pas seulement à l'écart médian.")


# ==============================================================================
# ONGLETS
# ==============================================================================
tab_dash, tab_bt, tab_ind, tab_dyn, tab_rob = st.tabs([
    "📊 Dashboard", "🔬 Backtest", "📈 Indicateurs", "⚡ Dynamic DCA", "🛡️ Robustesse"
])

with tab_dash:
    render_dashboard(ticker, asset_name, start_date, end_date)

with tab_bt:
    render_backtest(ticker, asset_name, start_date, end_date, base_amount, frequency, fees)

with tab_ind:
    render_indicators(ticker, asset_name, start_date, end_date)

with tab_dyn:
    render_dynamic_dca(ticker, asset_name, start_date, end_date, base_amount, frequency, fees)

with tab_rob:
    render_robustness(ticker, asset_name, end_date, frequency, fees)
