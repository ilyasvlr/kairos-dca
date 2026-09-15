"""
Backtester Module
Moteur de backtesting pour stratégies DCA classiques et dynamiques (Zero Look-Ahead Bias)

Comptabilité des flux
---------------------
Chaque jour, le Backtester mesure deux choses :
  - l'argent DÉPLOYÉ  : montant réellement acheté dans l'actif
  - l'argent VERSÉ    : ce qui sort de la poche de l'investisseur
                        = déployé + variation de la réserve de cash de la stratégie

Pour une stratégie sans réserve (Classique, Drawdown, RSI, Kairos), les deux sont
égaux. Pour une stratégie Dry Powder, le versement est le budget complet de la
période, qu'il soit acheté ou mis de côté. Le XIRR et la valeur finale intègrent
donc le cash dormant : une stratégie qui thésaurise n'est pas récompensée.
"""

import calendar
import datetime as dt
from typing import Any, Dict, List, Mapping, Optional, Tuple

import numpy as np
import pandas as pd

from .metrics import (
    calculate_xirr,
    calculate_cagr,
    calculate_max_drawdown,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
)


# ==============================================================================
# 1. STRATÉGIES DCA
# ==============================================================================

class BaseDCAStrategy:
    """
    Classe de base pour toutes les stratégies DCA.

    Contrat avec le Backtester :
      - reset()       : appelé au début de chaque run. Toute stratégie qui garde un
                        état interne DOIT le remettre à zéro ici (et appeler super()).
      - cash_reserve  : cash mis de côté et non encore déployé (0 par défaut).
      - should_buy()  : appelé une fois par jour, dans l'ordre chronologique.
    """

    label = "Base"

    def __init__(
        self,
        base_amount: float,
        frequency: str = 'weekly',
        day_of_week: int = 1,  # 0=Lundi, 6=Dimanche
        day_of_month: int = 1,
    ):
        if frequency not in ('daily', 'weekly', 'monthly'):
            raise ValueError(f"Fréquence inconnue: {frequency}")
        self.base_amount = base_amount
        self.frequency = frequency
        self.day_of_week = day_of_week
        self.day_of_month = day_of_month
        self.reset()

    def reset(self) -> None:
        """Remet l'état interne à zéro (appelé au début de chaque run)"""
        self._first_day: Optional[dt.date] = None
        self._last_scheduled: Optional[dt.date] = None
        self._last_buy_day: Optional[dt.date] = None

    @property
    def cash_reserve(self) -> float:
        """Cash mis de côté et non déployé. Les stratégies sans réserve renvoient 0."""
        return 0.0

    def _scheduled_day(self, day: dt.date) -> dt.date:
        """Date d'achat théorique la plus récente (<= day) pour la fréquence choisie"""
        if self.frequency == 'daily':
            return day
        if self.frequency == 'weekly':
            return day - dt.timedelta(days=(day.weekday() - self.day_of_week) % 7)
        # monthly : le jour cible est borné à la longueur du mois (ex: 31 -> 30 en avril)
        target = min(self.day_of_month, calendar.monthrange(day.year, day.month)[1])
        if day.day >= target:
            return day.replace(day=target)
        prev = day.replace(day=1) - dt.timedelta(days=1)
        return prev.replace(day=min(self.day_of_month, calendar.monthrange(prev.year, prev.month)[1]))

    def _check_frequency(self, date: pd.Timestamp) -> bool:
        """
        Vérifie si la date est un jour d'achat.

        Si le jour cible n'est pas coté (week-end, jour férié), l'achat est reporté
        au premier jour coté suivant de la même période — sinon un DCA mensuel au 1er
        du mois sur actions saute ~40% des mois. Une période entamée avant le début
        des données n'est pas rattrapée.
        """
        day = date.date()
        if self._first_day is None:
            self._first_day = day
        if day == self._last_buy_day:
            return True  # idempotent si appelé deux fois le même jour

        scheduled = self._scheduled_day(day)
        if scheduled < self._first_day:
            return False
        if self._last_scheduled is not None and scheduled <= self._last_scheduled:
            return False

        self._last_scheduled = scheduled
        self._last_buy_day = day
        return True

    def get_multiplier(self, market_state: Mapping[str, Any]) -> float:
        """Retourne le multiplicateur de mise (1.0 par défaut)"""
        return 1.0

    def should_buy(self, date: pd.Timestamp, market_state: Mapping[str, Any]) -> Tuple[bool, float]:
        """
        Détermine si on achète et combien.
        market_state contient les indicateurs CAUSAUX au jour J (pas de look-ahead).
        """
        if not self._check_frequency(date):
            return False, 0.0

        multiplier = self.get_multiplier(market_state)
        return True, self.base_amount * multiplier


class ClassicDCAStrategy(BaseDCAStrategy):
    """DCA classique : montant fixe, fréquence fixe"""
    label = "Classique"


class DrawdownDCAStrategy(BaseDCAStrategy):
    """DCA agressif en fonction du Drawdown par rapport à l'ATH causal"""
    label = "Drawdown"

    def get_multiplier(self, state: Mapping[str, Any]) -> float:
        dd = state.get('drawdown', 0.0)
        if pd.isna(dd):
            return 1.0
        if dd <= -0.60:
            return 5.0  # Fire sale
        elif dd <= -0.40:
            return 3.0  # Gros crash
        elif dd <= -0.20:
            return 2.0  # Correction
        return 1.0      # Normal


class RSIDCAStrategy(BaseDCAStrategy):
    """DCA basé sur le RSI (Mean Reversion)"""
    label = "RSI"

    def get_multiplier(self, state: Mapping[str, Any]) -> float:
        rsi = state.get('rsi', 50.0)
        if pd.isna(rsi):
            return 1.0
        if rsi < 30:
            return 2.5  # Survente forte
        elif rsi < 45:
            return 1.5  # Survente modérée
        elif rsi > 60:
            return 0.5  # Surachat, on ralentit
        return 1.0


class KairosScoreDCAStrategy(BaseDCAStrategy):
    """DCA Multi-Facteur : Score combiné (F&G + 200WMA + RSI)"""
    label = "Kairos Score"

    def get_multiplier(self, state: Mapping[str, Any]) -> float:
        score = 0

        # 1. Fear & Greed < 30 (+40 pts)
        fg = state.get('fear_greed', 50)
        if not pd.isna(fg) and fg < 30:
            score += 40

        # 2. Prix sous la 200WMA (+30 pts)
        price = state.get('price', 0)
        ma_200w = state.get('ma_200w', 0)
        if not pd.isna(ma_200w) and ma_200w > 0 and price < ma_200w:
            score += 30

        # 3. RSI < 40 (+30 pts)
        rsi = state.get('rsi', 50)
        if not pd.isna(rsi) and rsi < 40:
            score += 30

        # Application du score
        if score >= 70:
            return 3.0  # Kairos Moment (alignement parfait)
        elif score >= 40:
            return 1.5  # Opportunité modérée
        return 0.5      # Marché cher/euphorique, on accumule au ralenti


class DryPowderDCAStrategy(BaseDCAStrategy):
    """
    DCA avec réserve de cash (Dry Powder).

    À chaque période, le budget est coupé en deux :
      - (1 - reserve_ratio) est acheté immédiatement (DCA de base)
      - reserve_ratio est mis de côté dans la réserve

    Quand le drawdown passe sous dip_threshold, on injecte
    deployment_multiplier × réserve en plus du DCA de base.

    rearm=False : (défaut) injection à chaque période tant que le drawdown reste
                  sous le seuil (la réserve fraîchement accumulée est redéployée).
    rearm=True  : une seule injection par creux ; la stratégie se réarme quand le
                  drawdown repasse au-dessus du seuil. Tire au DÉBUT d'une baisse
                  puis rate le point bas sur les baisses longues : 0/40 configs
                  battent le DCA classique sur BTC 2021-10 -> 2024-04.

    Le capital total versé est exactement base_budget × nombre de périodes,
    quels que soient les paramètres.
    """
    label = "Dry Powder"

    def __init__(
        self,
        base_budget: float,
        reserve_ratio: float,
        dip_threshold: float,
        deployment_multiplier: float = 1.0,
        frequency: str = 'weekly',
        day_of_week: int = 1,
        day_of_month: int = 1,
        rearm: bool = False,
    ):
        if base_budget <= 0:
            raise ValueError(f"base_budget doit être > 0 (reçu {base_budget})")
        if not 0.0 <= reserve_ratio <= 1.0:
            raise ValueError(f"reserve_ratio doit être dans [0, 1] (reçu {reserve_ratio})")
        if not -1.0 < dip_threshold < 0.0:
            raise ValueError(f"dip_threshold doit être dans ]-1, 0[ (reçu {dip_threshold})")
        if not 0.0 < deployment_multiplier <= 1.0:
            # > 1 injecterait plus que la réserve : le capital versé dépasserait le budget
            raise ValueError(f"deployment_multiplier doit être dans ]0, 1] (reçu {deployment_multiplier})")

        self.base_budget = base_budget
        self.reserve_ratio = reserve_ratio
        self.dip_threshold = dip_threshold
        self.deployment_multiplier = deployment_multiplier
        self.rearm = rearm
        self.dca_amount = base_budget * (1 - reserve_ratio)
        self.reserve_amount = base_budget * reserve_ratio

        # super().__init__ appelle reset(), qui a besoin des attributs ci-dessus
        super().__init__(
            base_amount=base_budget,
            frequency=frequency,
            day_of_week=day_of_week,
            day_of_month=day_of_month,
        )

    def reset(self) -> None:
        super().reset()
        self._reserve = 0.0
        self._armed = True

    @property
    def cash_reserve(self) -> float:
        return self._reserve

    def should_buy(self, date: pd.Timestamp, state: Mapping[str, Any]) -> Tuple[bool, float]:
        dd = state.get('drawdown', np.nan)
        below = not pd.isna(dd) and dd <= self.dip_threshold

        # Réarmement évalué CHAQUE jour, pas seulement les jours d'achat : un passage
        # au-dessus du seuil entre deux achats hebdo doit être vu.
        if not below:
            self._armed = True

        if not self._check_frequency(date):
            return False, 0.0

        # La réserve se remplit une fois par PÉRIODE (après le filtre de fréquence)
        self._reserve += self.reserve_amount
        amount = self.dca_amount

        if below and self._armed and self._reserve > 0:
            injection = self._reserve * self.deployment_multiplier  # <= réserve (mult <= 1)
            amount += injection
            self._reserve -= injection
            self._armed = not self.rearm

        return True, amount


# ==============================================================================
# 2. MOTEUR DE BACKTEST
# ==============================================================================

class Backtester:
    """
    Moteur de backtesting avec garantie de causalité stricte (Zero Look-Ahead Bias).
    """

    def __init__(
        self,
        prices: pd.DataFrame,
        strategy: BaseDCAStrategy,
        fees: float = 0.001,
        fear_greed_history: Optional[pd.DataFrame] = None,
        long_prices: Optional[pd.DataFrame] = None,
    ):
        self.prices = prices.copy()
        self.strategy = strategy
        self.fees = fees
        self.fear_greed_history = fear_greed_history
        # Historique antérieur à la fenêtre testée, pour amorcer l'ATH (drawdown) et
        # la 200WMA. Peut s'étendre au-delà de la fenêtre : tous les indicateurs sont
        # causaux, les données futures ne sont jamais lues.
        self.long_prices = long_prices

    def build_market_state(self) -> pd.DataFrame:
        """
        Précalcule tous les indicateurs de marché de manière STRICTEMENT CAUSALE.
        Aucune donnée future n'est utilisée pour calculer l'état au jour J.

        Ne dépend pas de la stratégie : un optimiseur peut le calculer une fois
        et le passer à run(market_state=...) pour chaque essai.
        """
        df = self.prices.copy()
        close = df['Close']

        # 1. RSI (Causal par construction : rolling)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # 2. Drawdown (Causal STRICT : expanding().max() ne regarde que le passé/présent)
        # L'ATH est amorcé sur l'historique long : sans ça, un backtest démarrant
        # après un krach voit un drawdown de 0 au jour 1.
        if self.long_prices is not None and not self.long_prices.empty:
            combined = pd.concat([self.long_prices['Close'], close])
            combined = combined[~combined.index.duplicated(keep='last')].sort_index()
        else:
            combined = close
        running_max = combined.expanding().max().reindex(close.index)
        df['drawdown'] = (close - running_max) / running_max

        # 3. 200-Week MA (Causal)
        # min_periods=200 : sans 200 semaines réelles ce n'est PAS une 200WMA.
        if self.long_prices is not None and not self.long_prices.empty:
            source_close = self.long_prices['Close']
        else:
            source_close = close
        weekly_close = source_close.resample('W').last()
        ma_200w = weekly_close.rolling(window=200).mean()
        df['ma_200w'] = ma_200w.reindex(df.index, method='ffill')

        # 4. Fear & Greed (Match par date)
        if self.fear_greed_history is not None and not self.fear_greed_history.empty:
            fg_df = self.fear_greed_history.copy()
            ts = fg_df['timestamp']
            if not pd.api.types.is_datetime64_any_dtype(ts):
                ts = pd.to_datetime(ts, unit='s')
            if getattr(ts.dt, 'tz', None) is not None:
                ts = ts.dt.tz_localize(None)
            fg_df['date'] = ts.dt.date
            fg_df = fg_df.set_index('date')
            # df.index.date est un ndarray : il faut un pd.Index pour .map()
            df['fear_greed'] = pd.Index(df.index.date).map(fg_df['value']).to_numpy()
        else:
            df['fear_greed'] = 50.0

        df['price'] = close

        return df

    # Compatibilité avec l'ancien nom
    _build_market_state = build_market_state

    def run(self, market_state: Optional[pd.DataFrame] = None) -> Dict:
        """
        Lance le backtest et retourne les résultats.

        market_state : état de marché précalculé (optionnel). Doit avoir été construit
        sur la même fenêtre de prix — utile pour un optimiseur qui enchaîne les essais.
        """
        if market_state is None:
            market_state = self.build_market_state()
        elif not market_state.index.equals(self.prices.index):
            raise ValueError("market_state ne correspond pas à la fenêtre de prix du Backtester")

        strategy = self.strategy
        strategy.reset()

        coins = 0.0
        total_deployed = 0.0     # acheté dans l'actif
        total_contributed = 0.0  # sorti de la poche de l'investisseur

        dates = market_state.index
        n = len(dates)
        portfolio_values = np.zeros(n)
        contributed_series = np.zeros(n)
        contributions = np.zeros(n)
        reserve_series = np.zeros(n)

        trades: List[Dict] = []
        cashflows: List[float] = []   # Pour le calcul XIRR
        cf_dates: List[pd.Timestamp] = []

        # Un dict par jour : même interface que la Series (.get, []) pour les
        # stratégies, mais bien plus rapide qu'iterrows()
        records = market_state.to_dict('records')

        for i, (date, state) in enumerate(zip(dates, records)):
            price = state['price']

            reserve_before = strategy.cash_reserve
            should_buy, amount = strategy.should_buy(date, state)
            reserve_after = strategy.cash_reserve

            spent = float(amount) if (should_buy and amount > 0) else 0.0
            # Conservation : ce qui est versé = ce qui est acheté + ce qui est mis de côté
            contribution = spent + (reserve_after - reserve_before)

            if spent > 0:
                fees_amount = spent * self.fees
                coins_bought = (spent - fees_amount) / price
                coins += coins_bought
                total_deployed += spent

                trades.append({
                    'date': date,
                    'price': price,
                    'amount': spent,
                    'coins': coins_bought,
                    'fees': fees_amount,
                    'multiplier': spent / strategy.base_amount if strategy.base_amount > 0 else 1.0,
                    'drawdown': state['drawdown'],
                    'rsi': state['rsi'],
                    'cash_reserve': reserve_after,
                })

            if abs(contribution) > 1e-9:
                total_contributed += contribution
                contributions[i] = contribution
                cashflows.append(-contribution)
                cf_dates.append(date)

            portfolio_values[i] = coins * price + reserve_after
            contributed_series[i] = total_contributed
            reserve_series[i] = reserve_after

        final_price = market_state['price'].iloc[-1]
        final_value = coins * final_price           # valeur des coins seuls
        cash_reserve = strategy.cash_reserve
        total_portfolio_value = final_value + cash_reserve

        # Flux final (positif = valeur de liquidation, cash dormant inclus)
        if total_portfolio_value > 0:
            cashflows.append(total_portfolio_value)
            cf_dates.append(dates[-1])

        portfolio_values = pd.Series(portfolio_values, index=dates)
        total_invested_series = pd.Series(contributed_series, index=dates)
        contributions = pd.Series(contributions, index=dates)
        trades_df = pd.DataFrame(trades)

        # Rendements journaliers HORS versements : un dépôt n'est pas un gain.
        # Sans cet ajustement, chaque jour d'achat compte comme un rendement positif
        # et le Sharpe grimpe mécaniquement avec la fréquence des versements.
        previous = portfolio_values.shift(1)
        daily_returns = (
            ((portfolio_values - previous - contributions) / previous)
            .replace([np.inf, -np.inf], np.nan)
            .dropna()
        )

        years = (dates[-1] - dates[0]).days / 365.25

        metrics = {
            'total_invested': total_contributed,           # versé (= déployé sans réserve)
            'total_deployed': total_deployed,              # réellement acheté
            'cash_reserve': cash_reserve,                  # cash dormant en fin de période
            'final_value': final_value,                    # coins seuls
            'total_portfolio_value': total_portfolio_value,  # coins + cash
            'roi': ((total_portfolio_value - total_contributed) / total_contributed * 100)
                   if total_contributed > 0 else 0.0,
            'xirr': calculate_xirr(cashflows, cf_dates),   # déjà en %
            'cagr': calculate_cagr(total_contributed, total_portfolio_value, years),
            'max_drawdown': calculate_max_drawdown(portfolio_values),
            'sharpe_ratio': calculate_sharpe_ratio(daily_returns),
            'sortino_ratio': calculate_sortino_ratio(daily_returns),
            'num_trades': len(trades_df),
        }

        if not trades_df.empty:
            # PnL net de chaque achat : valeur actuelle des coins - montant déboursé
            trades_df['pnl'] = trades_df['coins'] * final_price - trades_df['amount']
            metrics['win_rate'] = (trades_df['pnl'] > 0).sum() / len(trades_df) * 100
            metrics['avg_buy_price'] = trades_df['price'].mean()
            metrics['avg_multiplier'] = trades_df['multiplier'].mean()
        else:
            metrics['win_rate'] = 0.0
            metrics['avg_buy_price'] = 0.0
            metrics['avg_multiplier'] = 0.0

        return {
            'metrics': metrics,
            'portfolio_values': portfolio_values,            # coins + cash
            'total_invested_series': total_invested_series,  # cumul versé
            'cash_reserve_series': pd.Series(reserve_series, index=dates),  # cash dormant jour par jour
            'trades': trades_df,
            'market_state': market_state,
        }


def compare_strategies(
    prices: pd.DataFrame,
    strategies: List[BaseDCAStrategy],
    fees: float = 0.001,
    fear_greed_history: Optional[pd.DataFrame] = None,
    long_prices: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Compare plusieurs stratégies et retourne un tableau comparatif"""
    results = []

    freq_fr = {'daily': 'quotidien', 'weekly': 'hebdo', 'monthly': 'mensuel'}

    # L'état de marché ne dépend pas de la stratégie : calculé une seule fois
    market_state = None

    for strategy in strategies:
        backtester = Backtester(prices, strategy, fees, fear_greed_history, long_prices)
        if market_state is None:
            market_state = backtester.build_market_state()
        result = backtester.run(market_state=market_state)
        m = result['metrics']

        label = getattr(strategy, 'label', strategy.__class__.__name__)
        freq = freq_fr.get(strategy.frequency, strategy.frequency)
        if isinstance(strategy, ClassicDCAStrategy):
            strategy_name = f"Classique ({freq}, ${strategy.base_amount:g})"
        else:
            strategy_name = f"Dynamique: {label} ({freq}, ${strategy.base_amount:g})"

        # Coût de revient = prix moyen payé par pièce, sur l'argent réellement acheté
        trades = result['trades']
        total_coins = trades['coins'].sum() if not trades.empty else 0.0
        cost_basis = (m['total_deployed'] / total_coins) if total_coins > 0 else 0.0

        # Pas de Sharpe ici : une fois les versements retirés des rendements, toute
        # stratégie 100% investie a le Sharpe de l'actif — la colonne ne départage rien.
        results.append({
            'Stratégie': strategy_name,
            'Investi': m['total_invested'],
            'Valeur Finale': m['total_portfolio_value'],
            'ROI %': m['roi'],
            'XIRR %': m['xirr'],
            'Max DD %': m['max_drawdown'],
            'Achats': m['num_trades'],
            'Coût de revient': cost_basis,
        })

    return pd.DataFrame(results)
