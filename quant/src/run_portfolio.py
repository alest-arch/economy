"""
run_portfolio.py
----------------
Diversified multi-asset, multi-strategy systematic portfolio (hedge-fund style),
vectorised daily-close conceptual backtest with proper risk budgeting.

Universe (25 OANDA markets, 2005-2020), 4 asset groups + a VIX risk overlay:
  equity   : SPX500 NAS100 FR40 JP225 UK100 US2000 AU200 NL25
  commodity: XAU(gold) WTICO(oil) CORN WHEAT SOYBN SUGAR NATGAS
  bond     : USB10Y USB02Y DE10YB UK10YB
  fx       : EUR_USD EUR_JPY AUD_USD GBP_USD USD_CAD AUD_JPY

Sleeves (3 economically distinct, low-correlated):
  TF  trend following   : 12m time-series momentum + 50/200 EMA, long/short, ALL assets
                          -> wins in sustained trends & crises (short equities/oil, long bonds/gold)
  MR  mean reversion    : RSI(2)<10 above SMA200 + vol circuit-breaker, long-only, INDICES only
                          -> wins in range-bound bull markets (buy the dip)
  BO  breakout/vol-exp  : 20d Donchian breakout gated by ATR expansion, long/short, ALL assets
                          -> wins at regime shifts / volatility expansion

Risk budgeting: per-instrument vol-parity (1/vol), equal weight across asset classes,
risk budget across sleeves, then portfolio-level volatility targeting. Optional VIX
de-risk overlay (cut gross when VIX spikes). Costs in bps of price on turnover.
"""
import os, json
import numpy as np
import pandas as pd
from engine import rsi, sma, ema, atr

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "universe")
RES = os.path.join(os.path.dirname(__file__), "..", "results")
VIXP = os.path.join(os.path.dirname(__file__), "..", "data", "VIX.csv")

GROUPS = {
    "equity": ["SPX500_USD", "NAS100_USD", "FR40_EUR", "JP225_USD", "UK100_GBP", "US2000_USD", "AU200_AUD", "NL25_EUR"],
    "commodity": ["XAU_USD", "WTICO_USD", "CORN_USD", "WHEAT_USD", "SOYBN_USD", "SUGAR_USD", "NATGAS_USD"],
    "bond": ["USB10Y_USD", "USB02Y_USD", "DE10YB_EUR", "UK10YB_GBP"],
    "fx": ["EUR_USD", "EUR_JPY", "AUD_USD", "GBP_USD", "USD_CAD", "AUD_JPY"],
}
INST2CLASS = {i: g for g, lst in GROUPS.items() for i in lst}
ALL = [i for lst in GROUPS.values() for i in lst]
INDICES = GROUPS["equity"]

COST_BPS_SIDE = 2.0          # round-trip ~4 bps of price (conservative for liquid)
TARGET_ANN_VOL = 0.11        # portfolio volatility target
SLEEVE_BUDGET = {"TF": 0.50, "MR": 0.25, "BO": 0.25}
ANN = 252


def load():
    px = {}
    for i in ALL:
        df = pd.read_csv(f"{DATA}/{i}.csv", parse_dates=[0], index_col=0)
        df.index = df.index.tz_localize(None)
        px[i] = df
    idx = sorted(set().union(*[set(df.index) for df in px.values()]))
    idx = pd.DatetimeIndex(idx)
    return px, idx


# ---------------- sleeve position generators (per instrument, daily) -----------
def pos_TF(df):
    """Multi-horizon time-series momentum (1/3/6/12m) — the robust TSMOM standard."""
    c = df["close"]
    sig = sum(np.sign(c - c.shift(k)) for k in (21, 63, 126, 252)) / 4.0
    return sig.fillna(0.0)


def pos_MR(df, inst):
    if inst not in INDICES:
        return pd.Series(0.0, index=df.index)
    c = df["close"]
    r = rsi(c, 2); trend = sma(c, 200)
    arank = (atr(df, 14) / c).rolling(252, min_periods=60).rank(pct=True)
    entry = (c > trend) & (r < 10) & (arank < 0.90)
    exit_ = r > 65
    raw = pd.Series(np.where(entry, 1.0, np.where(exit_, 0.0, np.nan)), index=df.index)
    return raw.ffill().fillna(0.0)


def pos_BO(df):
    c = df["close"]
    hi = df["high"].rolling(20).max().shift(1)
    lo = df["low"].rolling(20).min().shift(1)
    exp = atr(df, 10) > atr(df, 50)
    mid = sma(c, 10)
    long_raw = pd.Series(np.where((c > hi) & exp, 1.0, np.where(c < mid, 0.0, np.nan)), index=df.index).ffill().fillna(0.0)
    short_raw = pd.Series(np.where((c < lo) & exp, -1.0, np.where(c > mid, 0.0, np.nan)), index=df.index).ffill().fillna(0.0)
    return (long_raw + short_raw).clip(-1, 1)


SLEEVES = {"TF": pos_TF, "MR": None, "BO": pos_BO}


def sleeve_returns(px, idx, sleeve):
    """Vol-parity, class-balanced daily return series for one sleeve (unit-vol scale)."""
    per_class = {g: [] for g in GROUPS}
    n_trades = 0
    for inst, df in px.items():
        c = df["close"].reindex(idx).ffill()
        ret = c.pct_change().fillna(0.0)
        if sleeve == "MR":
            pos = pos_MR(df, inst).reindex(idx).ffill().fillna(0.0)
        else:
            pos = SLEEVES[sleeve](df).reindex(idx).ffill().fillna(0.0)
        pos = pos.where(c.notna(), 0.0)
        # execution lag + turnover cost (in return units)
        held = pos.shift(1).fillna(0.0)
        turn = (pos.shift(1) - pos.shift(2)).abs().fillna(0.0)
        n_trades += int((turn > 1e-9).sum())
        cost = turn * (COST_BPS_SIDE / 1e4)
        pnl = held * ret - cost
        vol = ret.rolling(60, min_periods=20).std().shift(1).replace(0, np.nan)
        per_class[INST2CLASS[inst]].append((pnl / vol).fillna(0.0))
    # average within class, then equal-weight across classes that have signal
    class_streams = []
    for g, lst in per_class.items():
        if lst:
            s = pd.concat(lst, axis=1).mean(axis=1)
            if s.abs().sum() > 0:
                class_streams.append(s)
    if not class_streams:
        return pd.Series(0.0, index=idx), 0
    return pd.concat(class_streams, axis=1).mean(axis=1), n_trades


def vix_overlay(idx):
    v = pd.read_csv(VIXP, parse_dates=["DATE"]).set_index("DATE")["CLOSE"]
    v.index = v.index.tz_localize(None)
    v = v.reindex(idx).ffill()
    # de-risk to 60% gross when VIX (lagged) is in a blow-off (>32)
    return np.where(v.shift(1) > 32, 0.6, 1.0)


def vol_target(ret, target=TARGET_ANN_VOL):
    rv = ret.rolling(60, min_periods=20).std().shift(1)
    scale = ((target / np.sqrt(ANN)) / rv.replace(0, np.nan)).clip(upper=5).fillna(0.0)
    return (ret * scale).fillna(0.0)


def metrics(ret, name=""):
    eq = (1 + ret).cumprod()
    yrs = len(ret) / ANN
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    vol = ret.std() * np.sqrt(ANN)
    sh = ret.mean() / ret.std() * np.sqrt(ANN) if ret.std() > 0 else np.nan
    dd = (eq / eq.cummax() - 1).min()
    return {"name": name, "CAGR_%": round(cagr * 100, 2), "vol_%": round(vol * 100, 1),
            "Sharpe": round(sh, 2), "maxDD_%": round(dd * 100, 1),
            "Calmar": round(cagr / abs(dd), 2) if dd < 0 else None}


def main():
    px, idx = load()
    sleeves, trades = {}, 0
    for s in ["TF", "MR", "BO"]:
        sr, nt = sleeve_returns(px, idx, s)
        sleeves[s] = sr; trades += nt
        print(f"sleeve {s}: {metrics(vol_target(sr).loc['2005':], s)}  trades~{nt}")

    sdf = pd.DataFrame(sleeves).fillna(0.0)
    print("\n[Sleeve correlation]\n", sdf.loc["2005":].corr().round(2).to_string())

    raw = sum(SLEEVE_BUDGET[s] * sleeves[s] for s in sleeves)
    raw = raw * vix_overlay(idx)
    # portfolio volatility targeting (rolling, lagged -> no look-ahead)
    rv = raw.rolling(60, min_periods=20).std().shift(1)
    scale = (TARGET_ANN_VOL / np.sqrt(ANN)) / rv.replace(0, np.nan)
    scale = scale.clip(upper=5).fillna(0.0)
    port = (raw * scale).fillna(0.0)
    port = port.loc["2005":]

    print("\n==== PORTFOLIO (vol-targeted) ====")
    m = metrics(port, "PORTFOLIO"); print(m, f"| total trades ~{trades}")

    # per-regime
    regimes = {"GFC 2008-09": ("2007-10", "2009-03"), "EuroCrisis 2011": ("2011-05", "2011-12"),
               "Bull 2013-2017": ("2013-01", "2017-12"), "Q4-2018": ("2018-10", "2018-12"),
               "COVID 2020": ("2020-02", "2020-05")}
    print("\n[Per-regime]")
    reg_out = {}
    for nm, (a, b) in regimes.items():
        seg = port.loc[a:b]
        if len(seg) > 5:
            eq = (1 + seg).cumprod()
            r = eq.iloc[-1] - 1; dd = (eq / eq.cummax() - 1).min()
            reg_out[nm] = {"ret_%": round(r * 100, 1), "maxDD_%": round(dd * 100, 1)}
            print(f"  {nm:16s}: ret {r*100:+6.1f}%  maxDD {dd*100:5.1f}%")

    # walk-forward reasoning: IS 2005-2013 vs OOS 2014-2020 (no params optimised)
    print("\n[Walk-forward: IS vs OOS, no params optimised]")
    is_m = metrics(port.loc["2005":"2013"], "IS 2005-2013"); print("  ", is_m)
    oos_m = metrics(port.loc["2014":"2020"], "OOS 2014-2020"); print("  ", oos_m)

    # Monte Carlo (block bootstrap of daily returns)
    rng = np.random.default_rng(7); arr = port.values; n = len(arr); blk = 20
    dds, finals, ruin = [], [], 0
    for _ in range(5000):
        nb = n // blk + 1
        starts = rng.integers(0, n - blk, nb)
        seq = np.concatenate([arr[s:s + blk] for s in starts])[:n]
        eq = np.cumprod(1 + seq); peak = np.maximum.accumulate(eq)
        d = (eq / peak - 1).min(); dds.append(d); finals.append(eq[-1])
        if d <= -0.30: ruin += 1
    mc = {"maxDD_p50_%": round(np.percentile(dds, 50) * 100, 1),
          "maxDD_p95_%": round(np.percentile(dds, 5) * 100, 1),
          "maxDD_p99_%": round(np.percentile(dds, 1) * 100, 1),
          "ruin_ge30dd_%": round(ruin / 5000 * 100, 2),
          "final_p5": round(np.percentile(finals, 5), 2), "final_p50": round(np.percentile(finals, 50), 2)}
    print("\n[Monte Carlo, block bootstrap]", mc)

    summary = {"portfolio": m, "sleeves": {s: metrics(vol_target(sleeves[s]).loc["2005":], s) for s in sleeves},
               "sleeve_corr": sdf.loc["2005":].corr().round(3).to_dict(),
               "per_regime": reg_out, "is": is_m, "oos": oos_m, "monte_carlo": mc,
               "total_trades": trades, "config": {"target_vol": TARGET_ANN_VOL, "budgets": SLEEVE_BUDGET,
                                                   "cost_bps_side": COST_BPS_SIDE}}
    with open(f"{RES}/portfolio_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=float)

    _plot(port, sleeves)
    print(f"\nArtifacts -> results/portfolio_*  | trades={trades}")
    return port


def _plot(port, sleeves):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 1, figsize=(11, 9))
    eq = (1 + port).cumprod()
    ax[0].plot(eq.index, eq.values, "k", lw=1.8, label="Portfolio (vol-targeted 11%)")
    ax[0].set_yscale("log"); ax[0].set_title("Multi-asset multi-strategy portfolio (2005-2020, daily, net of costs)")
    ax[0].set_ylabel("Equity (log)"); ax[0].grid(alpha=.3, which="both"); ax[0].legend()
    dd = eq / eq.cummax() - 1
    ax[1].fill_between(dd.index, dd.values * 100, 0, color="tab:red", alpha=.5)
    ax[1].set_title("Drawdown (%)"); ax[1].grid(alpha=.3); ax[1].set_ylabel("%")
    plt.tight_layout(); plt.savefig(f"{RES}/portfolio_equity.png", dpi=110)
    print("saved portfolio_equity.png")


if __name__ == "__main__":
    main()
