"""
Backtest Page
Teste et compare des stratégies DCA
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

# Import depuis core
import sys
sys.path.append('..')
from core.data_fetcher import fetch_crypto_data, fetch_stock_data
from core.backtester import ClassicDCAStrategy, Backtester, compare_strategies

st.set_page_config(page_title="Backtest - Kairos DCA", page_icon="🔬", layout="wide")

from core.ui import render_disclaimer
render_disclaimer()

st.title("🔬 Backtest DCA")

# Récupérer la configuration
if 'ticker' not in st.session_state:
    st.warning("⚠️ Configure d'abord un actif dans la page principale")
    st.stop()

ticker = st.session_state['ticker']
asset_name = st.session_state['asset_name']
start_date = st.session_state['start_date']
end_date = st.session_state['end_date']
base_amount = st.session_state['base_amount']
frequency = st.session_state['frequency']
fees = st.session_state['fees']

# Charger les données
with st.spinner(f"Chargement des données pour {asset_name}..."):
    if '-USD' in ticker:
        prices = fetch_crypto_data(ticker, str(start_date), str(end_date))
    else:
        prices = fetch_stock_data(ticker, str(start_date), str(end_date))

if prices.empty:
    st.error("Impossible de charger les données")
    st.stop()

# === SECTION 1 : CONFIGURATION DE LA STRATÉGIE ===
st.subheader("⚙️ Configuration de la stratégie")

col1, col2, col3 = st.columns(3)

with col1:
    strategy_frequency = st.selectbox(
        "Fréquence d'achat",
        options=['daily', 'weekly', 'monthly'],
        format_func=lambda x: {'daily': 'Quotidien', 'weekly': 'Hebdomadaire', 'monthly': 'Mensuel'}[x],
        index=['daily', 'weekly', 'monthly'].index(frequency),
        key='strategy_freq'
    )

with col2:
    strategy_amount = st.number_input(
        "Montant par achat ($)",
        min_value=10,
        max_value=10000,
        value=int(base_amount),
        step=10,
        key='strategy_amount'
    )

with col3:
    strategy_fees = st.slider(
        "Frais (%)",
        min_value=0.0,
        max_value=1.0,
        value=float(fees*100),
        step=0.01,
        key='strategy_fees'
    ) / 100

# === SECTION 2 : LANCER LE BACKTEST ===
st.subheader("🚀 Résultats du backtest")

if st.button("Lancer le backtest", type="primary"):
    with st.spinner("Backtest en cours..."):
        # Créer la stratégie
        strategy = ClassicDCAStrategy(
            base_amount=strategy_amount,
            frequency=strategy_frequency
        )

        # Lancer le backtest
        backtester = Backtester(prices, strategy, strategy_fees)
        result = backtester.run()

        metrics = result['metrics']
        portfolio_values = result['portfolio_values']
        total_invested_series = result['total_invested_series']
        trades = result['trades']

        # === AFFICHER LES MÉTRIQUES ===
        st.markdown("### 📊 Métriques de performance")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "ROI Total",
                f"{metrics['roi']:.2f}%",
                delta=f"${metrics['final_value'] - metrics['total_invested']:.2f}"
            )

        with col2:
            st.metric(
                "XIRR (annualisé)",
                f"{metrics['xirr']:.2f}%",
                help="Rendement pondéré par le timing de chaque versement. "
                     f"Le CAGR lump-sum affiche {metrics['cagr']:.2f}% mais suppose "
                     "que tout a été investi au jour 1 — faux en DCA."
            )

        with col3:
            st.metric(
                "Max Drawdown",
                f"{metrics['max_drawdown']:.2f}%"
            )

        with col4:
            st.metric(
                "Sharpe Ratio",
                f"{metrics['sharpe_ratio']:.2f}"
            )

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Total investi",
                f"${metrics['total_invested']:,.2f}"
            )

        with col2:
            st.metric(
                "Valeur finale",
                f"${metrics['final_value']:,.2f}"
            )

        with col3:
            st.metric(
                "Nombre d'achats",
                f"{metrics['num_trades']}"
            )

        with col4:
            st.metric(
                "Win rate",
                f"{metrics['win_rate']:.1f}%"
            )

        # === GRAPHIQUE : PORTFOLIO VS INVESTI ===
        st.markdown("### 📈 Évolution du portfolio")

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=portfolio_values.index,
            y=portfolio_values,
            mode='lines',
            name='Valeur du portfolio',
            line=dict(color='#00D4AA', width=2)
        ))

        fig.add_trace(go.Scatter(
            x=total_invested_series.index,
            y=total_invested_series,
            mode='lines',
            name='Total investi',
            line=dict(color='#FF6347', width=2, dash='dash')
        ))

        # Ajouter les points d'achat
        if not trades.empty:
            fig.add_trace(go.Scatter(
                x=trades['date'],
                y=trades['price'] * trades['coins'],
                mode='markers',
                name='Achats',
                marker=dict(color='#FFD700', size=6, symbol='triangle-up')
            ))

        fig.update_layout(
            height=500,
            xaxis_title="Date",
            yaxis_title="Valeur ($)",
            hovermode='x unified',
            showlegend=True
        )

        st.plotly_chart(fig, width='stretch')

        # === GRAPHIQUE : PRIX AVEC ACHATS ===
        st.markdown("### 💰 Prix avec points d'achat")

        fig_price = go.Figure()

        fig_price.add_trace(go.Scatter(
            x=prices.index,
            y=prices['Close'],
            mode='lines',
            name='Prix',
            line=dict(color='#00D4AA', width=2)
        ))

        if not trades.empty:
            fig_price.add_trace(go.Scatter(
                x=trades['date'],
                y=trades['price'],
                mode='markers',
                name='Achats',
                marker=dict(color='#FFD700', size=8, symbol='triangle-up')
            ))

        fig_price.update_layout(
            height=400,
            xaxis_title="Date",
            yaxis_title="Prix ($)",
            hovermode='x unified'
        )

        st.plotly_chart(fig_price, width='stretch')

        # === TABLEAU DES ACHATS ===
        if not trades.empty:
            st.markdown("### 📋 Historique des achats")

            trades_display = trades.copy()
            trades_display['date'] = trades_display['date'].dt.strftime('%Y-%m-%d')
            trades_display = trades_display.rename(columns={
                'date': 'Date',
                'price': 'Prix',
                'amount': 'Montant',
                'coins': 'Quantité',
                'fees': 'Frais'
            })

            st.dataframe(
                trades_display[['Date', 'Prix', 'Montant', 'Quantité', 'Frais']],
                width='stretch',
                hide_index=True
            )

# === SECTION 3 : COMPARAISON DE STRATÉGIES ===
st.markdown("---")
st.subheader("🔄 Comparaison de stratégies")

st.markdown("Compare différentes fréquences et montants")

if st.button("Comparer les stratégies"):
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

        st.dataframe(
            comparison_df,
            width='stretch',
            hide_index=True
        )

        # Graphique de comparaison
        fig_comp = go.Figure()

        for idx, row in comparison_df.iterrows():
            fig_comp.add_trace(go.Bar(
                x=[row['Stratégie']],
                y=[row['ROI %']],
                name=row['Stratégie'],
                marker_color='#00D4AA'
            ))

        fig_comp.update_layout(
            height=400,
            xaxis_title="Stratégie",
            yaxis_title="ROI (%)",
            showlegend=False
        )

        st.plotly_chart(fig_comp, width='stretch')
