"""
Indicators Module
Calcule tous les indicateurs techniques et on-chain
"""

import pandas as pd
import numpy as np
from typing import Tuple
import streamlit as st


# === INDICATEURS TECHNIQUES CLASSIQUES ===

@st.cache_data(ttl=3600)
def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Calcule le RSI (Relative Strength Index)"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


@st.cache_data(ttl=3600)
def calculate_macd(
    prices: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calcule le MACD (Moving Average Convergence Divergence)"""
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()

    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


@st.cache_data(ttl=3600)
def calculate_bollinger_bands(
    prices: pd.Series,
    period: int = 20,
    std_dev: int = 2
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calcule les Bandes de Bollinger"""
    sma = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()

    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)

    return upper_band, sma, lower_band


@st.cache_data(ttl=3600)
def calculate_moving_averages(
    prices: pd.Series,
    periods: list = [50, 100, 200]
) -> dict:
    """Calcule plusieurs moyennes mobiles"""
    mas = {}
    for period in periods:
        if len(prices) >= period:
            mas[f'MA{period}'] = prices.rolling(window=period).mean()

    return mas


@st.cache_data(ttl=3600)
def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    """Calcule l'ATR (Average True Range)"""
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()

    return atr


@st.cache_data(ttl=3600)
def calculate_stochastic_rsi(
    prices: pd.Series,
    rsi_period: int = 14,
    stoch_period: int = 14,
    k_period: int = 3,
    d_period: int = 3
) -> Tuple[pd.Series, pd.Series]:
    """Calcule le Stochastic RSI"""
    rsi = calculate_rsi(prices, rsi_period)

    rsi_min = rsi.rolling(window=stoch_period).min()
    rsi_max = rsi.rolling(window=stoch_period).max()

    stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min)

    k = stoch_rsi.rolling(window=k_period).mean() * 100
    d = k.rolling(window=d_period).mean()

    return k, d


# === INDICATEURS ON-CHAIN CRYPTO ===

@st.cache_data(ttl=3600)
def calculate_200_week_ma(prices: pd.Series) -> pd.Series:
    """Calcule la 200-Week Moving Average (la fameuse 'ligne verte')"""
    # Convertir en données hebdomadaires
    weekly_prices = prices.resample('W').last()

    if len(weekly_prices) < 200:
        return pd.Series(dtype=float)

    ma_200w = weekly_prices.rolling(window=200).mean()

    # Réindexer pour matcher les données quotidiennes
    ma_200w = ma_200w.reindex(prices.index, method='ffill')

    return ma_200w


@st.cache_data(ttl=3600)
def calculate_log_regression(
    prices: pd.Series,
    num_days: int = None
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calcule la régression linéaire logarithmique + bandes 2σ
    Retourne: (upper_band, middle_line, lower_band)
    """
    if num_days is None:
        num_days = len(prices)

    # Prendre les N derniers jours
    prices_subset = prices.tail(num_days)

    # Convertir en log
    log_prices = np.log(prices_subset)

    # Créer les x (jours)
    x = np.arange(len(log_prices))

    # Régression linéaire
    coeffs = np.polyfit(x, log_prices, 1)
    poly = np.poly1d(coeffs)

    # Calculer la ligne de régression
    log_regression = poly(x)

    # Calculer les résidus
    residuals = log_prices - log_regression
    std_residuals = residuals.std()

    # Bandes 2σ
    upper_band = np.exp(log_regression + 2 * std_residuals)
    middle_line = np.exp(log_regression)
    lower_band = np.exp(log_regression - 2 * std_residuals)

    # Réindexer pour matcher l'index original
    index_subset = prices_subset.index

    upper_band = pd.Series(upper_band, index=index_subset)
    middle_line = pd.Series(middle_line, index=index_subset)
    lower_band = pd.Series(lower_band, index=index_subset)

    return upper_band, middle_line, lower_band


@st.cache_data(ttl=3600)
def calculate_mvrv_zscore(prices: pd.Series, window: int = 365) -> pd.Series:
    """
    Calcule le MVRV Z-Score (simplifié)
    Note: Le vrai MVRV nécessite des données on-chain (realized cap)
    Ici on utilise une approximation basée sur le prix moyen mobile
    """
    # Prix moyen sur la période (proxy du realized price)
    realized_price = prices.rolling(window=window).mean()

    # MVRV ratio
    mvrv = prices / realized_price

    # Z-Score
    mvrv_mean = mvrv.rolling(window=window).mean()
    mvrv_std = mvrv.rolling(window=window).std()

    zscore = (mvrv - mvrv_mean) / mvrv_std

    return zscore


@st.cache_data(ttl=3600)
def calculate_rainbow_bands(prices: pd.Series) -> dict:
    """
    Calcule les bandes du Rainbow Chart (BTC)
    Basé sur des moyennes mobiles logarithmiques
    """
    log_prices = np.log(prices)

    bands = {}
    periods = [50, 100, 200, 300, 400, 500, 600]
    colors = [
        '#FF0000',  # Rouge - Bubble
        '#FFA500',  # Orange - FOMO
        '#FFFF00',  # Jaune - HODL
        '#90EE90',  # Vert clair - Still cheap
        '#00FF00',  # Vert - Accumulation
        '#0000FF',  # Bleu - Fire sale
        '#800080',  # Violet - Buy
    ]
    labels = [
        'Bubble', 'FOMO', 'HODL', 'Still cheap',
        'Accumulation', 'Fire sale', 'Buy',
    ]

    for i, period in enumerate(periods):
        if len(log_prices) >= period:
            ma = log_prices.rolling(window=period).mean()
            bands[f'band_{i}'] = {
                'values': np.exp(ma),
                'color': colors[i],
                'label': f'{labels[i]} (MA{period})'
            }

    return bands


# === FONCTIONS UTILITAIRES ===

def get_signal_strength(indicator_value: float, indicator_type: str) -> str:
    """
    Retourne la force du signal (buy/neutral/sell) basé sur la valeur de l'indicateur
    """
    if indicator_type == 'rsi':
        if indicator_value < 30:
            return 'strong_buy'
        elif indicator_value < 40:
            return 'buy'
        elif indicator_value > 70:
            return 'strong_sell'
        elif indicator_value > 60:
            return 'sell'
        else:
            return 'neutral'

    elif indicator_type == 'fear_greed':
        if indicator_value < 25:
            return 'strong_buy'
        elif indicator_value < 45:
            return 'buy'
        elif indicator_value > 75:
            return 'strong_sell'
        elif indicator_value > 55:
            return 'sell'
        else:
            return 'neutral'

    elif indicator_type == 'mvrv_zscore':
        # Logique Z-Score statistique (Prix vs MA365)
        if indicator_value < -1.5:
            return 'strong_buy'  # Prix significativement sous la moyenne annuelle (zone d'accumulation)
        elif indicator_value < -0.5:
            return 'buy'
        elif indicator_value > 2.0:
            return 'strong_sell'  # Prix en extension majeure au-dessus de la moyenne (euphorie)
        elif indicator_value > 1.0:
            return 'sell'
        else:
            return 'neutral'

    return 'neutral'


def calculate_all_indicators(
    prices: pd.DataFrame,
    asset_type: str = 'crypto',
    symbol: str = '',
    long_close: pd.Series = None,
) -> dict:
    """
    Calcule tous les indicateurs pour un actif
    Retourne un dictionnaire avec tous les indicateurs

    long_close : série de clôtures sur un historique étendu (au-delà de la
    période affichée). Nécessaire pour la 200WMA, qui a besoin de 200 semaines
    de recul AVANT le premier point affiché. Si absent, on retombe sur la
    période affichée et la 200WMA peut être vide.
    """
    indicators = {}

    close = prices['Close']
    high = prices['High']
    low = prices['Low']

    # Indicateurs techniques (toujours)
    indicators['rsi'] = calculate_rsi(close)
    indicators['macd_line'], indicators['macd_signal'], indicators['macd_hist'] = calculate_macd(close)
    indicators['bb_upper'], indicators['bb_middle'], indicators['bb_lower'] = calculate_bollinger_bands(close)
    indicators['moving_averages'] = calculate_moving_averages(close)
    indicators['atr'] = calculate_atr(high, low, close)
    indicators['stoch_rsi_k'], indicators['stoch_rsi_d'] = calculate_stochastic_rsi(close)

    # Indicateurs on-chain (crypto uniquement)
    if asset_type == 'crypto':
        source_200w = long_close if long_close is not None and not long_close.empty else close
        ma_200w = calculate_200_week_ma(source_200w)
        if not ma_200w.empty:
            # ne garder que la fenêtre affichée
            ma_200w = ma_200w.reindex(close.index, method='ffill')
        indicators['ma_200w'] = ma_200w

        indicators['log_reg_upper'], indicators['log_reg_middle'], indicators['log_reg_lower'] = calculate_log_regression(close)
        indicators['mvrv_zscore'] = calculate_mvrv_zscore(close)

        if 'BTC' in symbol.upper():  # Rainbow chart seulement pour BTC
            indicators['rainbow'] = calculate_rainbow_bands(close)

    return indicators
