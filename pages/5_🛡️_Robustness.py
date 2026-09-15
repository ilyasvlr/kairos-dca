"""
Robustness Page
Carte de robustesse des stratégies Dry Powder sur fenêtres glissantes.

Pas d'optimiseur, pas de « meilleur X » : une grille fixée à l'avance, évaluée sur
toutes les fenêtres de l'historique contre le DCA classique.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys

sys.path.append('..')
from core.data_fetcher import fetch_crypto_data, fetch_stock_data
from core.robustness import build_grid, compute_robustness_map, rank_stability

st.set_page_config(page_title="Robustesse - Kairos", page_icon="🛡️", layout="wide")

from core.ui import render_disclaimer
render_disclaimer()

# Paire divergente (bleu = mieux que le classique, rouge = moins bien, gris = égal)
COLOR_POS = "#2a78d6"
COLOR_NEG = "#e34948"
COLOR_MID = "#f0efec"
INK = "#1f1f1e"
WHITE = "#ffffff"


def _hex_to_rgb(color: str) -> tuple:
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def _relative_luminance(rgb: tuple) -> float:
    """Luminance relative WCAG 2.x (sRGB linéarisé)"""
    def linear(c: float) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(rgb_a: tuple, rgb_b: tuple) -> float:
    la, lb = _relative_luminance(rgb_a), _relative_luminance(rgb_b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def cell_background(z: float, zmax: float) -> tuple:
    """Couleur réellement peinte par Plotly : interpolation RGB linéaire sur l'échelle rouge-gris-bleu"""
    t = min(max((z + zmax) / (2 * zmax), 0.0), 1.0)
    (a, b), local = ((COLOR_NEG, COLOR_MID), t / 0.5) if t <= 0.5 else ((COLOR_MID, COLOR_POS), (t - 0.5) / 0.5)
    ra, rb = _hex_to_rgb(a), _hex_to_rgb(b)
    return tuple(ra[k] + (rb[k] - ra[k]) * local for k in range(3))


def text_color_for(background: tuple) -> str:
    """
    Encre ou blanc, selon le meilleur contraste WCAG.
    (Un seuil de luma naïf à 0.5 choisirait du blanc sur le rouge #e34948,
    où l'encre foncée contraste en réalité mieux : 4.17:1 contre 3.95:1.)
    """
    ink_ratio = _contrast_ratio(background, _hex_to_rgb(INK))
    white_ratio = _contrast_ratio(background, _hex_to_rgb(WHITE))
    return INK if ink_ratio >= white_ratio else WHITE

st.title("🛡️ Carte de robustesse Dry Powder")
st.markdown("""
Chaque configuration de la grille est testée sur **toutes les fenêtres glissantes** de l'historique,
contre le DCA classique sur la même fenêtre et avec exactement les mêmes versements.

Aucune configuration ne gagne à tous les coups. Cette carte ne te donne pas un « meilleur réglage » :
elle te montre **la distribution des résultats** de chaque règle, pour que tu choisisses en connaissant le risque.
""")

if 'ticker' not in st.session_state:
    st.warning("⚠️ Configure d'abord un actif dans la page principale")
    st.stop()

ticker = st.session_state['ticker']
asset_name = st.session_state['asset_name']
end_date = st.session_state['end_date']
frequency = st.session_state['frequency']
fees = st.session_state['fees']
asset_type = 'crypto' if '-USD' in ticker else 'stock'
freq_fr = {'daily': 'quotidien', 'weekly': 'hebdomadaire', 'monthly': 'mensuel'}[frequency]

# === PARAMÈTRES ===
col1, col2, col3 = st.columns(3)
with col1:
    window_years = st.selectbox("Durée de chaque fenêtre", options=[2, 3, 5], index=1,
                                format_func=lambda y: f"{y} ans")
with col2:
    step_months = st.selectbox("Décalage entre deux fenêtres", options=[3, 6, 12], index=1,
                               format_func=lambda m: f"{m} mois")
with col3:
    st.markdown(f"**{asset_name}** · DCA {freq_fr} · frais {fees * 100:.2f}%")
    st.caption("Le budget n'a aucun effet sur les écarts relatifs (tout est proportionnel), il n'est donc pas demandé.")


@st.cache_data(show_spinner=False)
def cached_map(ticker: str, asset_type: str, end: str, frequency: str, fees: float,
               window_years: int, step_months: int):
    """Historique COMPLET de l'actif (pas la période du sidebar) : sinon une seule fenêtre."""
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
        'history_start': history.index[0],
        'history_end': history.index[-1],
        'span_years': (history.index[-1] - history.index[0]).days / 365.25,
    }
    return summary, rows, meta


with st.spinner(f"Calcul de la carte sur tout l'historique de {asset_name}..."):
    try:
        summary, rows, meta = cached_map(ticker, asset_type, str(end_date), frequency, fees,
                                         window_years, step_months)
    except ValueError as e:
        st.warning(f"⚠️ {e}. Essaie une durée de fenêtre plus courte.")
        st.stop()

n_windows = rows['window_start'].nunique()
independent = (meta['span_years'] - 1) / window_years
stability = rank_stability(rows)

# === VUE D'ENSEMBLE ===
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
          help=f"Elles se chevauchent : cela représente environ {independent:.1f} périodes de "
               f"{window_years} ans réellement indépendantes.")
k2.metric("Périodes indépendantes", f"≈ {independent:.1f}")
k3.metric("Configs gagnantes > 50% du temps", f"{n_majority} / {len(summary)}")
k4.metric("Meilleur écart médian", f"{best['gap_median']:+.2f}%",
          help="Écart de valeur finale contre le DCA classique, médiane sur toutes les fenêtres.")

if n_positive == 0:
    st.info(
        f"ℹ️ **Sur {asset_name}, aucune configuration de réserve n'a fait mieux que le DCA classique "
        f"en médiane.** Garder du cash de côté a coûté plus qu'il n'a rapporté sur la majorité des fenêtres."
    )
else:
    st.info(
        f"ℹ️ **{n_positive} configuration(s) sur {len(summary)} ont un écart médian positif**, "
        f"dont {n_majority} battent le classique dans plus de la moitié des fenêtres. "
        f"Regarde leur pire fenêtre avant d'en retenir une."
    )

if independent < 4:
    st.warning(
        f"⚠️ **Échantillon mince** : ≈ {independent:.1f} périodes indépendantes seulement. "
        "Un pourcentage de victoires calculé sur si peu de marchés distincts reste très incertain."
    )

# Stabilité du classement : la carte aurait-elle aidé à choisir dans le passé ?
if stability is None:
    st.caption("Stabilité du classement : historique insuffisant pour comparer deux périodes séparées.")
else:
    rho = stability['spearman']
    if rho >= 0.5:
        verdict = "le classement est **stable** dans le temps"
    elif rho >= 0:
        verdict = "le classement n'est **que faiblement** reproductible"
    else:
        verdict = ("le classement s'est **inversé** : les règles les mieux placées avant "
                   "ont fait partie des moins bonnes ensuite")
    msg = (
        f"**Stabilité du classement : {rho:+.2f}** (corrélation de rang). Les {stability['n_early']} fenêtres "
        f"terminées avant {stability['split_date']:%Y-%m} et les {stability['n_late']} commencées après ne "
        f"se chevauchent pas : {verdict}. La meilleure règle de la première période est "
        f"{stability['best_early_rank_late']}e sur {stability['n_configs']} dans la seconde."
    )
    # Pas de vert : un classement stable peut très bien confirmer que toutes les règles perdent
    (st.info if rho >= 0.5 else st.warning)(msg)

# === HEATMAP ===
st.subheader("🗺️ Réserve × seuil de déclenchement")

reserves = sorted(summary['reserve_ratio'].unique())
thresholds = sorted(summary['dip_threshold'].unique(), reverse=True)  # -15% à gauche, -45% à droite
grid_gap = summary.pivot(index='reserve_ratio', columns='dip_threshold', values='gap_median').loc[reserves, thresholds]
grid_win = summary.pivot(index='reserve_ratio', columns='dip_threshold', values='win_rate').loc[reserves, thresholds]
grid_worst = summary.pivot(index='reserve_ratio', columns='dip_threshold', values='gap_worst').loc[reserves, thresholds]

x_labels = [f"{t * 100:.0f}%" for t in thresholds]
y_labels = [f"{r * 100:.0f}%" for r in reserves]
zmax = max(abs(grid_gap.values.min()), abs(grid_gap.values.max()), 0.01)

customdata = [[[grid_win.iloc[i, j], grid_worst.iloc[i, j]] for j in range(len(thresholds))]
              for i in range(len(reserves))]

fig_heat = go.Figure(go.Heatmap(
    z=grid_gap.values,
    x=x_labels,
    y=y_labels,
    zmid=0,
    zmin=-zmax,
    zmax=zmax,
    colorscale=[[0.0, COLOR_NEG], [0.5, COLOR_MID], [1.0, COLOR_POS]],
    customdata=customdata,
    hovertemplate=(
        "Réserve %{y} · seuil %{x}<br>"
        "Écart médian : %{z:+.2f}%<br>"
        "Bat le classique : %{customdata[0]:.0f}% des fenêtres<br>"
        "Pire fenêtre : %{customdata[1]:+.2f}%<extra></extra>"
    ),
    xgap=2,
    ygap=2,
    colorbar=dict(title="Écart médian (%)", ticksuffix="%"),
))
# Plotly n'accepte qu'une couleur de texte par heatmap : une annotation par case,
# chacune avec l'encre la plus lisible sur la couleur réellement peinte.
for i, reserve_label in enumerate(y_labels):
    for j, threshold_label in enumerate(x_labels):
        z = grid_gap.iloc[i, j]
        fig_heat.add_annotation(
            x=threshold_label,
            y=reserve_label,
            text=f"{z:+.2f}%<br>{grid_win.iloc[i, j]:.0f}% vict.",
            showarrow=False,
            font=dict(color=text_color_for(cell_background(z, zmax)), size=12),
        )

fig_heat.update_layout(
    height=380,
    xaxis_title="Seuil de drawdown qui déclenche le déploiement",
    yaxis_title="Part du budget mise en réserve",
    margin=dict(l=10, r=10, t=10, b=10),
)
st.plotly_chart(fig_heat, width='stretch')
st.caption("Bleu : fait mieux que le DCA classique en médiane · rouge : moins bien · gris : équivalent. "
           "Chaque case indique l'écart médian et le % de fenêtres gagnées.")

# === TABLEAU ===
st.subheader("📋 Distribution par configuration")

table = pd.DataFrame({
    'Réserve (%)': summary['reserve_ratio'] * 100,
    'Seuil (%)': summary['dip_threshold'] * 100,
    'Fenêtres gagnées (%)': summary['win_rate'],
    'Écart médian (%)': summary['gap_median'],
    'Pire fenêtre (%)': summary['gap_worst'],
    'Meilleure fenêtre (%)': summary['gap_best'],
    'Dispersion (pts)': summary['gap_std'],
    'Écart XIRR médian (pp)': summary['xirr_excess_median'],
    'Cash dormant moyen (%)': summary['cash_share_avg'],
})
st.dataframe(
    table,
    width='stretch',
    hide_index=True,
    column_config={
        'Réserve (%)': st.column_config.NumberColumn(format="%.0f"),
        'Seuil (%)': st.column_config.NumberColumn(format="%.0f"),
        'Fenêtres gagnées (%)': st.column_config.NumberColumn(format="%.0f"),
        'Écart médian (%)': st.column_config.NumberColumn(format="%.2f"),
        'Pire fenêtre (%)': st.column_config.NumberColumn(format="%.2f"),
        'Meilleure fenêtre (%)': st.column_config.NumberColumn(format="%.2f"),
        'Dispersion (pts)': st.column_config.NumberColumn(format="%.2f"),
        'Écart XIRR médian (pp)': st.column_config.NumberColumn(format="%.2f"),
        'Cash dormant moyen (%)': st.column_config.NumberColumn(format="%.1f"),
    },
)
st.caption(
    "Écart = valeur finale (coins + cash) de la règle ÷ valeur finale du DCA classique − 1, sur la même fenêtre. "
    "Cash dormant moyen = part moyenne du portefeuille restée en cash. Trié par écart médian décroissant."
)

# === DÉTAIL D'UNE CONFIGURATION ===
st.subheader("🔍 Quand une règle fonctionne-t-elle ?")

options = list(summary.index)
choice = st.selectbox(
    "Configuration",
    options=options,
    format_func=lambda i: (f"Réserve {summary.loc[i, 'reserve_ratio'] * 100:.0f}% · "
                           f"seuil {summary.loc[i, 'dip_threshold'] * 100:.0f}% "
                           f"(médiane {summary.loc[i, 'gap_median']:+.2f}%)"),
)
sel = summary.loc[choice]
detail = rows[
    (rows['reserve_ratio'] == sel['reserve_ratio']) & (rows['dip_threshold'] == sel['dip_threshold'])
].sort_values('window_start')

fig_detail = go.Figure(go.Bar(
    x=detail['window_start'],
    y=detail['value_gap_pct'],
    marker_color=[COLOR_POS if v > 0 else COLOR_NEG for v in detail['value_gap_pct']],
    customdata=detail[['window_end', 'xirr', 'classic_xirr']].assign(
        window_end=detail['window_end'].dt.strftime('%Y-%m-%d')
    ).values,
    hovertemplate=(
        "Fenêtre %{x|%Y-%m-%d} → %{customdata[0]}<br>"
        "Écart de valeur : %{y:+.2f}%<br>"
        "XIRR règle %{customdata[1]:.2f}% · classique %{customdata[2]:.2f}%<extra></extra>"
    ),
))
fig_detail.add_hline(y=0, line_color="#b5b4af", line_width=1)
fig_detail.update_layout(
    height=360,
    bargap=0.15,
    xaxis_title="Début de la fenêtre",
    yaxis_title="Écart vs DCA classique (%)",
    yaxis_ticksuffix="%",
    margin=dict(l=10, r=10, t=10, b=10),
    showlegend=False,
)
st.plotly_chart(fig_detail, width='stretch')
st.caption(
    "Chaque barre est une fenêtre. Des barres voisines partagent la plupart de leurs données : "
    "une série de barres bleues consécutives correspond souvent à un seul épisode de marché."
)

st.markdown("---")
st.caption(
    "⚠️ Choisir la meilleure ligne de ce tableau reste une sélection sur le passé : sur 20 règles, "
    "l'une d'elles finira en tête même par hasard. Fie-toi à la stabilité du classement et à la pire "
    "fenêtre, pas seulement à l'écart médian."
)
