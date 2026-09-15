"""
UI Module
Éléments d'interface partagés de l'application (app.py, page unique à onglets)
"""

import streamlit as st

APP_VERSION = "1.1"

DISCLAIMER = (
    "⚠️ Kairos DCA est un outil éducatif de backtesting. "
    "Les performances passées ne préjugent pas des performances futures. "
    "Ceci ne constitue pas un conseil en investissement."
)


def render_disclaimer() -> None:
    """Avertissement en bas de la sidebar. Appelé une seule fois par app.py."""
    st.sidebar.markdown("---")
    st.sidebar.caption(DISCLAIMER)
    st.sidebar.caption(f"Kairos DCA v{APP_VERSION}")
