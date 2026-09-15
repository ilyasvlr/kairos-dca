"""
Kairos DCA - Main Application
Optimiseur de DCA multi-actifs avec indicateurs avancés
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# Configuration de la page
st.set_page_config(
    page_title="Kairos DCA",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Titre principal
st.title("🎯 Kairos DCA")
st.markdown("### Optimiseur de DCA multi-actifs avec indicateurs avancés")

# Sidebar - Configuration globale
st.sidebar.header("⚙️ Configuration")

# Sélection de l'actif
from core.data_fetcher import get_available_assets
from core.ui import render_disclaimer

assets = get_available_assets()
asset_category = st.sidebar.selectbox(
    "Catégorie",
    options=list(assets.keys()),
    index=0
)

asset_names = list(assets[asset_category].keys())
asset_name = st.sidebar.selectbox(
    "Actif",
    options=asset_names,
    index=0
)

ticker = assets[asset_category][asset_name]

# Période de backtest
st.sidebar.subheader("📅 Période")
default_end = datetime.now()
default_start = default_end - timedelta(days=365*3)

col1, col2 = st.sidebar.columns(2)
with col1:
    start_date = st.date_input(
        "Début",
        value=default_start,
        max_value=default_end
    )
with col2:
    end_date = st.date_input(
        "Fin",
        value=default_end,
        max_value=default_end
    )

# Paramètres DCA
st.sidebar.subheader("💰 Paramètres DCA")
base_amount = st.sidebar.number_input(
    "Montant de base ($)",
    min_value=10,
    max_value=10000,
    value=100,
    step=10
)

frequency = st.sidebar.selectbox(
    "Fréquence",
    options=['daily', 'weekly', 'monthly'],
    format_func=lambda x: {'daily': 'Quotidien', 'weekly': 'Hebdomadaire', 'monthly': 'Mensuel'}[x],
    index=1
)

fees = st.sidebar.slider(
    "Frais (%)",
    min_value=0.0,
    max_value=1.0,
    value=0.1,
    step=0.01
) / 100

# Stocker dans session_state pour accès global
st.session_state['ticker'] = ticker
st.session_state['asset_name'] = asset_name
st.session_state['start_date'] = start_date
st.session_state['end_date'] = end_date
st.session_state['base_amount'] = base_amount
st.session_state['frequency'] = frequency
st.session_state['fees'] = fees

render_disclaimer()

# Message d'accueil
st.markdown("""
### 👋 Bienvenue sur Kairos DCA

Utilise le menu latéral pour configurer ton actif et ta période, puis navigue vers :

- **📊 Dashboard** : prix, volume, Fear & Greed
- **🔬 Backtest** : DCA classique et comparaison de fréquences
- **📈 Indicateurs** : techniques, on-chain (approximations) et macro
- **⚡ Dynamic DCA** : visualiser comment fonctionnent les stratégies dynamiques, sur une seule fenêtre
- **🛡️ Robustesse** : la distribution des résultats sur toutes les fenêtres historiques — la page à consulter avant toute décision

---
""")

# Afficher la configuration actuelle
st.info(f"""
**Configuration actuelle :**
- Actif : {asset_name} ({ticker})
- Période : {start_date} → {end_date}
- Montant : ${base_amount} {frequency}
- Frais : {fees*100:.2f}%
""")
