# 🎯 Kairos DCA

Outil de backtesting du **DCA** (Dollar Cost Averaging, investissement programmé) sur crypto, actions et ETF.
Il compare le DCA classique à des variantes dynamiques et montre, sur tout l'historique disponible,
si ces variantes font réellement mieux.

> ⚠️ **Kairos DCA est un outil éducatif de backtesting.**
> Les performances passées ne préjugent pas des performances futures.
> Ceci ne constitue pas un conseil en investissement.

---

## Ce que fait l'outil

| Page | Rôle |
| --- | --- |
| 📊 **Dashboard** | Prix, moyennes mobiles, volume, Fear & Greed (crypto) |
| 🔬 **Backtest** | DCA classique : rendement, XIRR, drawdown, comparaison de fréquences |
| 📈 **Indicateurs** | RSI, MACD, Bollinger, ATR, Stochastic RSI ; 200WMA, régression log, Rainbow (crypto) ; données macro FRED (taux Fed, 10 ans, CPI, M2) et DXY, VIX |
| ⚡ **Dynamic DCA** | **Pédagogique.** Visualise sur *une seule* période comment se comportent les stratégies Drawdown, RSI, Kairos Score et Coffre. Un bouton « Test automatique » lance un panel fixe et classe les résultats (toujours sur cette seule fenêtre) |
| 🛡️ **Robustesse** | **Décisionnel.** Teste 20 règles « Dry Powder » sur toutes les fenêtres glissantes de l'historique, contre le DCA classique |

La page Robustesse ne donne pas de « réglage optimal ». Elle montre la distribution des résultats de chaque règle :
% de fenêtres gagnées, écart médian, pire fenêtre, cash resté dormant, et stabilité du classement dans le temps.

**Sélection d'actif** : un seul menu recherchable (crypto, actions, ETF, et indices mondiaux — MSCI World,
MSCI ACWI, Total World Stock), plutôt que deux menus dépendants.

**Stratégie Coffre (Vault)** : généralise le Dry Powder. Tout le budget est mis de côté jusqu'à ce qu'un
indicateur choisi (Drawdown, RSI, VIX ou Fear & Greed) déclenche l'achat ; au déclenchement, toute la réserve
accumulée est investie d'un coup. Le capital versé reste toujours exactement budget × nombre de périodes,
qu'il soit acheté ou qu'il dorme en réserve — jamais perdu, jamais dépassé.

## Ce que montrent les données

Résultats de la carte de robustesse au 14/09/2026 (fenêtres de 3 ans décalées de 6 mois, DCA hebdomadaire,
réserve de 20 à 60 %, seuil de déclenchement de −15 % à −45 %) :

| Actif | Fenêtres (périodes indépendantes) | Règles gagnantes > 50 % du temps | Meilleur écart médian | Stabilité du classement |
| --- | --- | --- | --- | --- |
| BTC | 16 (≈ 3.7) | **0 / 20** | −0.23 % | −0.61 (instable) |
| ETH | 10 (≈ 2.6) | 5 / 20 | +2.76 % | +0.22 (faible) |
| SPY | 60 (≈ 10.9) | **0 / 20** | −0.18 % | +0.86 (stable) |

**Garder une réserve de cash pour « acheter les creux » n'a pas battu le DCA classique sur BTC ni sur le S&P 500.**
Sur SPY, le résultat est stable sur 33 ans : plus la réserve est grosse, plus l'écart est défavorable.
ETH est le seul signal positif, mais il repose sur environ 2.6 périodes de marché indépendantes : trop peu pour conclure.

Une première version de l'outil optimisait les paramètres automatiquement (Optuna). Elle a été retirée :
testés sur des fenêtres glissantes, les « meilleurs paramètres » ne battaient le classique hors échantillon
que dans 14 % des fenêtres sur BTC et 0 % sur SPY, soit moins bien qu'un réglage fixe choisi au hasard.

## Méthodologie

- **Aucun biais d'anticipation.** Chaque décision d'achat n'utilise que les données disponibles ce jour-là
  (ATH glissant, RSI, 200WMA). Vérifié par test : en tronquant le futur, les achats passés restent identiques.
- **Comptabilité des flux.** Versé = acheté + mis en réserve. Le cash dormant compte dans la valeur finale :
  une stratégie qui thésaurise n'est pas avantagée.
- **XIRR** (rendement tenant compte de la date de chaque versement) plutôt que le CAGR, qui suppose tout investi au jour 1.
- **Comparaisons à flux identiques.** Sur la page Robustesse, chaque règle verse exactement les mêmes montants
  aux mêmes dates que le DCA classique.
- **Historique amorcé.** Le drawdown et la 200WMA sont calculés à partir de l'historique antérieur à la période testée.

## Limites connues

- Données **Yahoo Finance** (via yfinance) : disponibilité non garantie, en particulier depuis des serveurs cloud.
- Le **MVRV Z-Score** est une approximation fondée sur le prix (pas de données on-chain réelles).
- Le **Fear & Greed** n'existe que pour la crypto, depuis 2018.
- Achats exécutés au **prix de clôture** du jour ; frais proportionnels uniquement ; ni slippage, ni fiscalité.
- La réserve de cash **ne rapporte rien** (pas de rémunération type fonds monétaire).
- Sur la page Dynamic DCA, les stratégies à multiplicateur **n'investissent pas le même capital** que le DCA classique :
  comparer leur XIRR, pas leur valeur finale.
- Un actif à la fois ; pas de portefeuille multi-actifs.

## Installation locale

Python 3.12 ou plus récent.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

L'application s'ouvre sur `http://localhost:8501`.

## Déploiement sur Streamlit Community Cloud

1. Pousser le projet sur un dépôt GitHub.
2. Sur [share.streamlit.io](https://share.streamlit.io) : **New app**, choisir le dépôt, branche `main`, fichier principal `app.py`.
3. **Advanced settings → Python version → 3.12**.
4. Déployer, puis ouvrir chaque page : si Yahoo Finance limite les requêtes du serveur, les pages l'indiquent
   par un message et récupèrent au prochain chargement (les échecs ne sont pas mis en cache).

Aucune clé API n'est nécessaire (FRED est interrogé via son export CSV public). Si une clé est ajoutée un jour,
la saisir dans les *Secrets* de Streamlit Cloud, jamais dans le dépôt.

## Structure

```text
app.py                     Accueil et configuration (actif, période, budget, frais)
core/
  backtester.py            Moteur de backtest et stratégies (Classique, Drawdown, RSI, Kairos Score, Dry Powder, Coffre)
  robustness.py            Carte de robustesse sur fenêtres glissantes
  metrics.py               XIRR, drawdown, Sharpe, Sortino
  data_fetcher.py          Prix (yfinance) et Fear & Greed (alternative.me)
  macro_data.py            Séries FRED, DXY, VIX
  indicators.py            Indicateurs techniques et on-chain (approximations)
  ui.py                    Avertissement partagé par toutes les pages
pages/
  1_📊_Dashboard.py
  2_🔬_Backtest.py
  3_📈_Indicators.py
  4_⚡_Dynamic_DCA.py
  5_🛡️_Robustness.py
```

## Stack

Streamlit · pandas · NumPy · SciPy · Plotly · yfinance · FRED (CSV public) · alternative.me
