"""
Data Fetcher Module
Récupère les données de marché depuis différentes sources gratuites
"""

import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta
import streamlit as st


# Règle de cache : une fonction @st.cache_data LÈVE en cas d'échec au lieu de renvoyer
# un résultat vide. Streamlit ne met jamais une exception en cache ; un DataFrame vide,
# si. Sans ça, une seule limitation de débit Yahoo casse l'actif pour TOUS les
# utilisateurs pendant toute la durée du TTL. Les fonctions publiques attrapent
# l'erreur et affichent un message.

RETRY_HINT = "Yahoo Finance limite parfois les requêtes : réessaie dans quelques minutes."


@st.cache_data(ttl=3600, show_spinner=False)  # Cache 1h, succès uniquement
def _download_history(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    df = yf.Ticker(symbol).history(start=start_date, end=end_date)
    if df.empty:
        raise ValueError(f"aucune donnée reçue pour {symbol}")
    return df[['Open', 'High', 'Low', 'Close', 'Volume']]


def fetch_crypto_data(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Récupère les données crypto via yfinance
    symbol: 'BTC-USD', 'ETH-USD', etc.
    """
    try:
        return _download_history(symbol, start_date, end_date)
    except Exception as e:
        st.error(f"Erreur lors du chargement de {symbol} : {e}. {RETRY_HINT}")
        return pd.DataFrame()


def fetch_stock_data(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Récupère les données actions/ETF via yfinance
    symbol: 'AAPL', 'SPY', 'QQQ', etc.
    """
    try:
        return _download_history(symbol, start_date, end_date)
    except Exception as e:
        st.error(f"Erreur lors du chargement de {symbol} : {e}. {RETRY_HINT}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)  # Cache 5min, succès uniquement
def _download_fear_greed(limit: int) -> list:
    response = requests.get(f"https://api.alternative.me/fng/?limit={limit}", timeout=10)
    response.raise_for_status()
    data = response.json().get('data') or []
    if not data:
        raise ValueError("réponse vide de alternative.me")
    return data


def fetch_fear_greed_crypto() -> dict:
    """
    Récupère le Fear & Greed Index crypto depuis alternative.me
    """
    try:
        latest = _download_fear_greed(1)[0]
        return {
            'value': int(latest['value']),
            'classification': latest['value_classification'],
            'timestamp': latest['timestamp']
        }
    except Exception as e:
        st.warning(f"Impossible de récupérer le Fear & Greed: {str(e)}")

    return {'value': 50, 'classification': 'Neutral', 'timestamp': None}


def fetch_fear_greed_history(days: int = 365) -> pd.DataFrame:
    """
    Récupère l'historique du Fear & Greed
    """
    try:
        df = pd.DataFrame(_download_fear_greed(days))
        df['value'] = df['value'].astype(int)
        # l'API renvoie le timestamp en string -> cast numérique avant conversion
        df['timestamp'] = pd.to_datetime(df['timestamp'].astype('int64'), unit='s')
        df = df.sort_values('timestamp')
        return df[['timestamp', 'value', 'value_classification']]
    except Exception as e:
        st.warning(f"Impossible de récupérer l'historique Fear & Greed: {str(e)}")

    return pd.DataFrame()


def get_available_assets() -> dict:
    """
    Retourne la liste des actifs disponibles par catégorie
    """
    return {
        'Crypto': {
            'Bitcoin': 'BTC-USD',
            'Ethereum': 'ETH-USD',
            'Solana': 'SOL-USD',
            'BNB': 'BNB-USD',
            'XRP': 'XRP-USD',
            'Cardano': 'ADA-USD',
            'Dogecoin': 'DOGE-USD',
            'Avalanche': 'AVAX-USD',
            'Polkadot': 'DOT-USD',
            'Chainlink': 'LINK-USD',
        },
        'Actions': {
            'Apple': 'AAPL',
            'Microsoft': 'MSFT',
            'Google': 'GOOGL',
            'Amazon': 'AMZN',
            'Tesla': 'TSLA',
            'Nvidia': 'NVDA',
            'Meta': 'META',
        },
        'ETF': {
            'S&P 500': 'SPY',
            'Nasdaq 100': 'QQQ',
            'Total Market (US)': 'VTI',
            'Bitcoin ETF': 'IBIT',
            'ARK Innovation': 'ARKK',
        },
        'Indices mondiaux': {
            'MSCI World': 'URTH',
            'MSCI All Country World': 'ACWI',
            'Total World Stock': 'VT',
        },
    }


def get_flat_asset_list() -> list:
    """
    Version aplatie de get_available_assets(), triée par catégorie puis par nom :
    une liste de dicts {category, name, ticker}, pour un unique sélecteur
    recherchable (au lieu de deux menus déroulants dépendants).
    """
    flat = []
    for category, names in get_available_assets().items():
        for name, ticker in names.items():
            flat.append({'category': category, 'name': name, 'ticker': ticker})
    return flat
