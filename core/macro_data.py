"""
Macro Data Module
Récupère les vraies données macroéconomiques via FRED CSV (No API Key required)
"""

import pandas as pd
import yfinance as yf
import streamlit as st
from datetime import datetime, timedelta


def _yoy_change(series: pd.Series) -> float:
    """
    Variation sur 1 an glissant, calculée sur les DATES et non sur un nombre
    de lignes : les séries FRED n'ont pas toutes la même fréquence
    (DGS10 = quotidien, FEDFUNDS/CPIAUCSL/M2SL = mensuel).
    """
    if series.empty:
        return 0.0

    last_date = series.index[-1]
    target = last_date - pd.DateOffset(years=1)

    prior = series.loc[:target]
    if prior.empty:
        return 0.0

    previous = prior.iloc[-1]
    if pd.isna(previous) or previous == 0:
        return 0.0

    return ((series.iloc[-1] / previous) - 1) * 100


# Même règle que data_fetcher : les fonctions cachées lèvent en cas d'échec (une
# exception n'est jamais mise en cache), les fonctions publiques l'attrapent.

@st.cache_data(ttl=3600, show_spinner=False)
def _download_fred(series_id: str) -> pd.DataFrame:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    df = pd.read_csv(url)

    # FRED nomme la colonne de dates 'observation_date' (anciennement 'DATE')
    date_col = 'observation_date' if 'observation_date' in df.columns else 'DATE'
    if date_col not in df.columns or series_id not in df.columns:
        raise ValueError(f"Format CSV inattendu: {list(df.columns)}")

    # FRED écrit '.' pour les jours sans cotation -> forcer en numérique
    df['value'] = pd.to_numeric(df[series_id], errors='coerce')
    df['date'] = pd.to_datetime(df[date_col])
    df = df.dropna(subset=['value']).set_index('date')[['value']]
    df.index.name = None

    if df.empty:
        raise ValueError("Série vide après nettoyage")
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def _download_yf_5y(symbol: str) -> pd.DataFrame:
    df = yf.Ticker(symbol).history(period="5y")
    if df.empty:
        raise ValueError(f"aucune donnée reçue pour {symbol}")
    return df[['Close']]


def fetch_fred_series(series_id: str, name: str) -> dict:
    """
    Récupère une série FRED via l'export CSV public
    Ex: 'DGS10' (Yield 10Y), 'FEDFUNDS' (Taux Fed), 'CPIAUCSL' (CPI), 'M2SL' (M2)
    """
    try:
        df = _download_fred(series_id)

        return {
            'name': name,
            'value': df['value'].iloc[-1],
            'yoy_change': _yoy_change(df['value']),
            'last_date': df.index[-1],
            'data': df
        }
    except Exception as e:
        st.warning(f"Impossible de récupérer FRED {series_id}: {str(e)}")
        return None


def fetch_dxy() -> pd.DataFrame:
    """Récupère le Dollar Index (DXY) via yfinance"""
    try:
        return _download_yf_5y("DX-Y.NYB")
    except Exception:
        return pd.DataFrame()


def fetch_vix() -> pd.DataFrame:
    """Récupère le VIX (5 ans) via yfinance, pour l'affichage sur la page Indicateurs"""
    try:
        return _download_yf_5y("^VIX")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def _download_yf_range(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    df = yf.Ticker(symbol).history(start=start_date, end=end_date)
    if df.empty:
        raise ValueError(f"aucune donnée reçue pour {symbol}")
    return df[['Close']]


def fetch_vix_history(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Récupère le VIX sur une plage arbitraire, pour alimenter le déclencheur
    Coffre "VIX" du backtester (qui peut porter sur des fenêtres > 5 ans).
    """
    try:
        return _download_yf_range("^VIX", start_date, end_date)
    except Exception:
        return pd.DataFrame()


def fetch_macro_indicators() -> dict:
    """
    Récupère tous les indicateurs macro (FRED + YF)

    Pas de cache ici : les téléchargements sous-jacents sont cachés 1h. L'ancien
    cache de 24h sur cet agrégat figeait aussi les séries manquantes après un
    échec réseau passager.
    """
    indicators = {}

    # 1. FRED Data
    fed_funds = fetch_fred_series('FEDFUNDS', 'Taux Directeur Fed (%)')
    if fed_funds:
        indicators['fed_funds'] = fed_funds

    yield_10y = fetch_fred_series('DGS10', 'Yield 10Y US (%)')
    if yield_10y:
        indicators['yield_10y'] = yield_10y

    cpi = fetch_fred_series('CPIAUCSL', 'CPI (Inflation US)')
    if cpi:
        indicators['cpi'] = cpi

    m2 = fetch_fred_series('M2SL', 'Masse Monétaire M2 (Milliards $)')
    if m2:
        indicators['m2'] = m2

    # 2. Market Data
    dxy = fetch_dxy()
    if not dxy.empty:
        dxy = dxy.rename(columns={'Close': 'value'})
        indicators['dxy'] = {
            'name': 'DXY (Dollar Index)',
            'value': dxy['value'].iloc[-1],
            'yoy_change': _yoy_change(dxy['value']),
            'last_date': dxy.index[-1],
            'data': dxy
        }

    vix = fetch_vix()
    if not vix.empty:
        vix = vix.rename(columns={'Close': 'value'})
        indicators['vix'] = {
            'name': 'VIX (Volatilité)',
            'value': vix['value'].iloc[-1],
            'yoy_change': _yoy_change(vix['value']),
            'last_date': vix.index[-1],
            'data': vix
        }

    return indicators


def get_macro_sentiment(indicators: dict) -> str:
    """
    Détermine le sentiment macro global (simplifié)
    Score > 0 = Bullish pour les risk assets (Crypto/Actions)
    Score < 0 = Bearish
    """
    score = 0

    # DXY fort = mauvais pour crypto/actions
    # (seuils du plus extrême au moins extrême, sinon les branches < 98
    #  sont inatteignables : tout ce qui est < 98 est aussi < 100)
    if 'dxy' in indicators:
        dxy = indicators['dxy']['value']
        if dxy > 105: score -= 2
        elif dxy > 102: score -= 1
        elif dxy < 98: score += 2
        elif dxy < 100: score += 1

    # VIX élevé = peur = mauvais pour risk assets
    if 'vix' in indicators:
        vix = indicators['vix']['value']
        if vix > 30: score -= 2
        elif vix > 20: score -= 1
        elif vix < 15: score += 1

    # Yield 10Y en hausse = pression sur les valorisations
    if 'yield_10y' in indicators:
        yoy = indicators['yield_10y']['yoy_change']
        if yoy > 15: score -= 1  # Yield qui monte fort
        elif yoy < -15: score += 1 # Yield qui baisse (pivot Fed)

    # M2 en hausse = liquidité = bullish
    if 'm2' in indicators:
        yoy = indicators['m2']['yoy_change']
        if yoy > 5: score += 2
        elif yoy < 0: score -= 1

    if score >= 2:
        return 'bullish'
    elif score <= -2:
        return 'bearish'
    else:
        return 'neutral'
