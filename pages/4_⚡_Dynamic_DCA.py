"""
Dynamic DCA Page
Compare les stratégies DCA classiques et dynamiques (Zero Look-Ahead Bias)
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys

sys.path.append('..')
from core.data_fetcher import fetch_crypto_data, fetch_stock_data, fetch_fear_greed_history
from core.macro_data import fetch_vix_history
from core.backtester import (
    ClassicDCAStrategy,
    DrawdownDCAStrategy,
    RSIDCAStrategy,
    KairosScoreDCAStrategy,
    VaultDCAStrategy,
    Backtester,
    compare_strategies
)

st.set_page_config(page_title="Dynamic DCA - Kairos", page_icon="⚡", layout="wide")

from core.ui import render_disclaimer
render_disclaimer()

st.title("⚡ Optimiseur de DCA Dynamique")
st.markdown("Compare le DCA classique aux stratégies conditionnelles intelligentes. **Zero Look-Ahead Bias garanti** (Drawdown calculé via `expanding().max()`).")

st.warning(
    "⚠️ **Attention : ces résultats sont calculés sur une seule fenêtre temporelle.** "
    "Consultez la page 🛡️ Robustesse pour voir la distribution réelle des résultats "
    "sur plusieurs fenêtres glissantes."
)
st.page_link("pages/5_🛡️_Robustness.py", label="Ouvrir la carte de robustesse", icon="🛡️")

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

asset_type = 'crypto' if '-USD' in ticker else 'stock'

# Charger les données
with st.spinner(f"Chargement des données pour {asset_name}..."):
    if asset_type == 'crypto':
        prices = fetch_crypto_data(ticker, str(start_date), str(end_date))
        fg_history = fetch_fear_greed_history(days=(end_date - start_date).days + 30)
        # Historique antérieur : la 200WMA du Kairos Score doit être disponible
        # DÈS le premier jour simulé, donc 200 semaines de recul en amont.
        long_start = (pd.Timestamp(start_date) - pd.DateOffset(years=5)).date()
        long_prices = fetch_crypto_data(ticker, str(long_start), str(end_date))
    else:
        prices = fetch_stock_data(ticker, str(start_date), str(end_date))
        fg_history = None
        # Même pour les actions : l'ATH doit être amorcé sur l'historique antérieur,
        # sinon un backtest démarré après un krach voit un drawdown de 0 au jour 1.
        long_start = (pd.Timestamp(start_date) - pd.DateOffset(years=5)).date()
        long_prices = fetch_stock_data(ticker, str(long_start), str(end_date))
    # VIX : indicateur de marché global, disponible quel que soit l'actif backtesté
    # (pas besoin d'être crypto). Utilisé par le déclencheur Coffre "VIX".
    vix_history = fetch_vix_history(str(long_start), str(end_date))

if prices.empty:
    st.error("Impossible de charger les données")
    st.stop()

if asset_type != 'crypto':
    st.info(
        "ℹ️ Actif non-crypto : le **Kairos Score** est désactivé (il s'appuie sur le "
        "Fear & Greed et la 200WMA, indisponibles hors crypto). **Drawdown** et "
        "**RSI** restent pleinement opérationnels."
    )

# === SECTION 1 : CONFIGURATION ===
st.subheader("⚙️ Paramètres de la simulation")

col1, col2, col3 = st.columns(3)

with col1:
    sim_amount = st.number_input("Montant de base ($)", min_value=10, value=int(base_amount), step=10)

with col2:
    sim_freq = st.selectbox(
        "Fréquence",
        options=['daily', 'weekly', 'monthly'],
        format_func=lambda x: {'daily': 'Quotidien', 'weekly': 'Hebdomadaire', 'monthly': 'Mensuel'}[x],
        index=['daily', 'weekly', 'monthly'].index(frequency)
    )

with col3:
    sim_fees = st.slider("Frais (%)", min_value=0.0, max_value=1.0, value=float(fees*100), step=0.01) / 100

# Sélection des stratégies à comparer
is_crypto = asset_type == 'crypto'

st.markdown("**Stratégies à comparer :**")
col1, col2, col3, col4 = st.columns(4)

with col1:
    use_classic = st.checkbox("DCA Classique", value=True)
with col2:
    use_drawdown = st.checkbox("Drawdown-Based", value=True, help="x2 à -20%, x3 à -40%, x5 à -60%")
with col3:
    use_rsi = st.checkbox("RSI-Based", value=False, help="x2.5 si RSI<30, x0.5 si RSI>60")
with col4:
    use_kairos = st.checkbox(
        "Kairos Score",
        value=is_crypto,
        disabled=not is_crypto,
        help="Score combiné F&G + 200WMA + RSI (Crypto uniquement)"
    )
    if not is_crypto:
        st.caption("⚠️ Indisponible pour les actions/ETF")

# --- Coffre : budget entier mis de côté jusqu'au déclenchement d'un indicateur ---
col1, col2, col3, col4 = st.columns(4)
with col1:
    use_vault = st.checkbox(
        "🔒 Coffre",
        value=False,
        help="Tout le budget est mis en réserve tant que l'indicateur ne déclenche pas. "
             "Au déclenchement, toute la réserve accumulée est investie d'un coup. "
             "Le capital versé reste budget × nb de périodes, quoi qu'il arrive.",
    )
with col2:
    vault_indicator_options = ['drawdown', 'rsi', 'vix'] + (['fear_greed'] if is_crypto else [])
    vault_indicator = st.selectbox(
        "Déclencheur",
        options=vault_indicator_options,
        format_func=lambda k: VaultDCAStrategy.INDICATORS[k]['label'],
        disabled=not use_vault,
        key='vault_indicator',
    )
with col3:
    _spec = VaultDCAStrategy.INDICATORS[vault_indicator]
    vault_threshold = st.number_input(
        "Seuil",
        min_value=float(_spec['lo']),
        max_value=float(_spec['hi']),
        value=float(_spec['default']),
        step=0.01 if vault_indicator == 'drawdown' else 1.0,
        disabled=not use_vault,
        help=_spec['desc'],
        # Clé dépendante de l'indicateur : les bornes (ex. -0.99..-0.01 pour le
        # drawdown, 1..99 pour le RSI) diffèrent trop pour partager un widget —
        # sinon une ancienne valeur hors bornes fait planter le number_input.
        key=f'vault_threshold_{vault_indicator}',
    )
with col4:
    vault_rearm = st.checkbox(
        "Réarmement",
        value=False,
        disabled=not use_vault,
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
    """Panel fixe pour le test automatique : mêmes stratégies que les cases à cocher
    proposent, plus les 3-4 déclencheurs du Coffre, à seuils par défaut."""
    strategies = [
        ClassicDCAStrategy(base_amount=sim_amount, frequency=sim_freq),
        DrawdownDCAStrategy(base_amount=sim_amount, frequency=sim_freq),
        RSIDCAStrategy(base_amount=sim_amount, frequency=sim_freq),
    ]
    if is_crypto:
        strategies.append(KairosScoreDCAStrategy(base_amount=sim_amount, frequency=sim_freq))
    for indicator in ['drawdown', 'rsi', 'vix'] + (['fear_greed'] if is_crypto else []):
        strategies.append(VaultDCAStrategy(
            base_budget=sim_amount, indicator=indicator, frequency=sim_freq, rearm=False,
        ))
    return strategies


# === SECTION 2 : EXÉCUTION ===
# Les résultats restent affichés tant que les paramètres ne changent pas : sans ça,
# le moindre widget (ex. choix de la stratégie à détailler) les ferait disparaître.
manual_key = (use_classic, use_drawdown, use_rsi, use_kairos,
              use_vault, vault_indicator, vault_threshold, vault_rearm)
params_key = ('manual', ticker, str(start_date), str(end_date), sim_amount, sim_freq, sim_fees, manual_key)
auto_params_key = ('auto', ticker, str(start_date), str(end_date), sim_amount, sim_freq, sim_fees)

col_run1, col_run2 = st.columns(2)
with col_run1:
    if st.button("🚀 Lancer la comparaison", type="primary"):
        st.session_state['dyn_params'] = params_key
with col_run2:
    if st.button("🎲 Test automatique (Top 3)",
                 help="Lance un panel fixe (Classique, Drawdown, RSI, Kairos si crypto, "
                      "et le Coffre sur ses 3-4 déclencheurs) et classe le résultat."):
        st.session_state['dyn_params'] = auto_params_key

active_key = st.session_state.get('dyn_params')
auto_mode = active_key == auto_params_key

if active_key in (params_key, auto_params_key):
    strategies_to_test = _build_auto_strategies() if auto_mode else _build_manual_strategies()

    if not strategies_to_test:
        st.warning("⚠️ Coche au moins une stratégie à comparer.")
        st.stop()

    with st.spinner("Calcul des stratégies en cours (Zero Look-Ahead Bias)..."):
        comparison_df = compare_strategies(
            prices, strategies_to_test, sim_fees, fg_history, long_prices, vix_history
        )

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

        # === AFFICHAGE DES RÉSULTATS ===
        st.markdown("### 📋 Tableau comparatif (une seule fenêtre)")

        # Formater le dataframe pour l'affichage
        display_df = comparison_df.copy()
        display_df['Investi'] = display_df['Investi'].apply(lambda x: f"${x:,.0f}")
        display_df['Valeur Finale'] = display_df['Valeur Finale'].apply(lambda x: f"${x:,.0f}")
        display_df['ROI %'] = display_df['ROI %'].apply(lambda x: f"{x:.2f}%")
        display_df['XIRR %'] = display_df['XIRR %'].apply(lambda x: f"{x:.2f}%")
        display_df['Max DD %'] = display_df['Max DD %'].apply(lambda x: f"{x:.2f}%")
        # Précision adaptative : sur un actif à $575 l'écart entre stratégies se
        # joue aux centimes, un arrondi à l'unité le masquerait entièrement.
        display_df['Coût de revient'] = display_df['Coût de revient'].apply(
            lambda x: f"${x:,.0f}" if x >= 1000 else f"${x:,.2f}"
        )

        st.dataframe(display_df, width='stretch', hide_index=True)

        # Pas de « meilleure stratégie » : sur une seule fenêtre, le classement ne
        # prédit rien (voir la stabilité du classement en page Robustesse).

        # === GRAPHIQUE 1 : COMPARAISON XIRR ===
        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            x=comparison_df['Stratégie'],
            y=comparison_df['XIRR %'],
            text=comparison_df['XIRR %'].apply(lambda x: f"{x:.1f}%"),
            textposition='auto',
            marker_color='#2a78d6'  # couleur unique : aucune barre n'est mise en avant
        ))
        fig_bar.update_layout(
            height=400,
            title="Rendement Annualisé (XIRR) par Stratégie",
            xaxis_title="Stratégie",
            yaxis_title="XIRR (%)",
            showlegend=False
        )
        st.plotly_chart(fig_bar, width='stretch')

        # === GRAPHIQUE 2 : DÉTAIL D'UNE STRATÉGIE (choix libre) ===
        st.markdown("---")
        labels = comparison_df['Stratégie'].tolist()
        detail_idx = st.selectbox(
            "Stratégie à détailler",
            options=list(range(len(labels))),
            format_func=lambda i: labels[i],
            index=1 if (isinstance(strategies_to_test[0], ClassicDCAStrategy) and len(labels) > 1) else 0,
            # ^ 1re stratégie dynamique par défaut, si la 1re de la liste est le classique
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

        # Graphique Prix + Achats (taille des marqueurs = montant)
        fig_price = go.Figure()

        fig_price.add_trace(go.Scatter(
            x=market_state.index,
            y=market_state['Close'],
            mode='lines',
            name='Prix',
            line=dict(color='#00D4AA', width=2)
        ))

        if not trades.empty:
            # Normaliser la taille des marqueurs pour la visibilité (entre 5 et 15)
            min_amt, max_amt = trades['amount'].min(), trades['amount'].max()
            if max_amt > min_amt:
                sizes = 5 + 10 * ((trades['amount'] - min_amt) / (max_amt - min_amt))
            else:
                sizes = 10

            # Couleur basée sur le multiplicateur (plus c'est vert, plus on a acheté gros)
            colors = []
            for mult in trades['multiplier']:
                if mult >= 3.0:
                    colors.append('#00FF00')  # Fire sale
                elif mult >= 1.5:
                    colors.append('#FFD700')  # Opportunité
                else:
                    colors.append('#FF6347')  # Normal/Ralenti

            fig_price.add_trace(go.Scatter(
                x=trades['date'],
                y=trades['price'],
                mode='markers',
                name='Achats (taille = montant)',
                marker=dict(
                    color=colors,
                    size=sizes,
                    line=dict(width=1, color='white')
                ),
                hovertemplate="<b>Date:</b> %{x}<br><b>Prix:</b> $%{y:.2f}<br><b>Montant:</b> $%{customdata[0]:.0f}<br><b>Multiplicateur:</b> x%{customdata[1]:.1f}<extra></extra>",
                customdata=trades[['amount', 'multiplier']].values
            ))

        fig_price.update_layout(
            height=500,
            title="Prix d'achat et points d'entrée dynamiques",
            xaxis_title="Date",
            yaxis_title="Prix ($)",
            hovermode='closest'
        )
        st.plotly_chart(fig_price, width='stretch')

        # === GRAPHIQUE 3 : ÉVOLUTION DU PORTFOLIO ===
        fig_port = go.Figure()
        fig_port.add_trace(go.Scatter(
            x=portfolio_values.index,
            y=portfolio_values,
            mode='lines',
            name='Valeur Portfolio',
            line=dict(color='#00D4AA', width=2)
        ))
        fig_port.add_trace(go.Scatter(
            x=total_invested_series.index,
            y=total_invested_series,
            mode='lines',
            name='Total Investi',
            line=dict(color='#FF6347', width=2, dash='dash')
        ))
        fig_port.update_layout(
            height=400,
            title="Évolution de la valeur vs capital investi",
            xaxis_title="Date",
            yaxis_title="Valeur ($)",
            hovermode='x unified'
        )
        st.plotly_chart(fig_port, width='stretch')

        # === RÉPARTITION DES MULTIPLICATEURS ===
        if not trades.empty:
            st.markdown("### 🎚️ Répartition des mises")
            mult_counts = trades['multiplier'].round(2).value_counts().sort_index()
            recap = pd.DataFrame({
                'Multiplicateur': [f"x{m:g}" for m in mult_counts.index],
                'Nb achats': mult_counts.values,
                '% des achats': (mult_counts.values / len(trades) * 100).round(1),
                'Capital engagé': [
                    f"${trades.loc[trades['multiplier'].round(2) == m, 'amount'].sum():,.0f}"
                    for m in mult_counts.index
                ],
            })
            st.dataframe(recap, width='stretch', hide_index=True)
