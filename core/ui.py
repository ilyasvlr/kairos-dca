"""
UI Module
Éléments d'interface partagés par toutes les pages
"""

import streamlit as st

APP_VERSION = "1.0"

DISCLAIMER = (
    "⚠️ Kairos DCA est un outil éducatif de backtesting. "
    "Les performances passées ne préjugent pas des performances futures. "
    "Ceci ne constitue pas un conseil en investissement."
)


def render_disclaimer() -> None:
    """
    Avertissement en bas de la sidebar.

    À appeler sur CHAQUE page : en multipage, la sidebar de app.py n'apparaît que
    sur la page d'accueil, et un visiteur peut arriver directement sur une page.
    """
    st.sidebar.markdown("---")
    st.sidebar.caption(DISCLAIMER)
    st.sidebar.caption(f"Kairos DCA v{APP_VERSION}")
