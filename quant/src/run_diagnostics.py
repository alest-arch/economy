"""
run_diagnostics.py
------------------
Reproducible evidence behind the honest verdict. Saves to ../results/:
  - event_study.csv        forward-return predictability of the MR signal by timeframe
  - edge_decay.csv         expectancy of the swing system by 5-year era (the key finding)
  - risk_scaling.csv       Monte-Carlo final wealth / drawdown / ruin vs risk-per-trade
  - intraday_rejection.csv ORB & intraday-momentum results (gross & net) -> no edge
  - benchmark.csv          strategy vs buy & hold

Run after run_validation.py:  python3 run_diagnostics.py
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd

from engine import (backtest, trade_metrics, monte_carlo, DEFAULT_COSTS, Costs,
                    rsi, sma, atr)
from strategies import build_signals_swing_mtf, make_daily
from intraday_strategies import build_signals_orb, build_signals_intraday_mom

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
RES = os.path.join(os.path.dirname(__file__), "..", "results")
INSTR = ["SPX", "NQ"]
BASE = dict(rsi_n=2, os_th=10.0, trend_n=200, exit_th=65.0, stop_atr=3.0,
            atr_n=14, max_hold_bars=30, session="us")


def load(tag, tf):
    return pd.read_csv(os.path.join(DATA, f"{tag}_{tf}.csv"), parse_dates=[0], index_col=0)


def daily(tag):
    return make_daily(load(tag, "H1"))


# --------------------------------------------------------------------------- #
def event_study():
    rows = []
    for tag in INSTR:
        for tf in ["H1", "H4", "D1"]:
            df = load(tag, tf) if tf != "D1" else daily(tag)
            c = df["close"]
            r2 = rsi(c, 2); tr = sma(c, 200)
            sig = (c > tr) & (r2 < 10)
            if tf in ("H1", "H4"):
                hh = df.index.hour
                sig = sig & (hh >= 14) & (hh <= 19)
            sig = sig.fillna(False)
            for k in [1, 2, 4, 8, 24]:
                fwd = c.shift(-k) / c - 1.0
                f = fwd[sig].dropna()
                if len(f) < 20:
                    continue
                t = f.mean() / (f.std() / np.sqrt(len(f)))
                rows.append({"instrument": tag, "timeframe": tf, "horizon_bars": k,
                             "n_signals": int(len(f)), "fwd_ret_bps": round(f.mean() * 1e4, 1),
                             "winrate_%": round((f > 0).mean() * 100, 1), "t_stat": round(t, 2),
                             "uncond_bps": round(fwd.dropna().mean() * 1e4, 1)})
    pd.DataFrame(rows).to_csv(os.path.join(RES, "event_study.csv"), index=False)
    print("event_study.csv written")


def edge_decay():
    rows = []
    trades = []
    for tag in INSTR:
        h4 = load(tag, "H4"); d = daily(tag)
        res = backtest(h4, build_signals_swing_mtf(h4, d, **BASE), DEFAULT_COSTS[tag], allow_short=False)
        for t in res["trades"]:
            trades.append((t.entry_time, t.r))
    T = pd.DataFrame(trades, columns=["t", "r"]).set_index("t").sort_index()
    for lo, hi in [("2005", "2009"), ("2010", "2014"), ("2015", "2020")]:
        s = T.loc[lo:hi]["r"]
        if len(s):
            pf = s[s > 0].sum() / (-s[s <= 0].sum()) if (s <= 0).any() else np.inf
            rows.append({"era": f"{lo}-{hi}", "trades": len(s),
                         "expectancy_R": round(s.mean(), 4), "winrate_%": round((s > 0).mean() * 100, 1),
                         "profit_factor": round(pf, 2)})
    pd.DataFrame(rows).to_csv(os.path.join(RES, "edge_decay.csv"), index=False)
    print("edge_decay.csv written")
    return T["r"].values


def risk_scaling(pooled):
    rows = []
    for rf in [0.005, 0.01, 0.02, 0.03, 0.05]:
        m = monte_carlo(pooled, n_sims=10000, risk_frac=rf, ruin_dd=0.20, block=5)  # bootstrap: varies final
        mdd = monte_carlo(pooled, n_sims=10000, risk_frac=rf, ruin_dd=0.20, block=1)  # reshuffle: DD/ruin
        m40 = monte_carlo(pooled, n_sims=10000, risk_frac=rf, ruin_dd=0.40, block=1)
        rows.append({"risk_per_trade_%": rf * 100,
                     "final_mult_p50": round(m["final_mult_p50"], 3),
                     "final_mult_p05": round(m["final_mult_p05"], 3),
                     "maxdd_p50_%": round(mdd["maxdd_p50"] * 100, 1),
                     "maxdd_p95_%": round(mdd["maxdd_p95"] * 100, 1),
                     "ruin_20dd_%": round(mdd["risk_of_ruin"] * 100, 2),
                     "ruin_40dd_%": round(m40["risk_of_ruin"] * 100, 2)})
    pd.DataFrame(rows).to_csv(os.path.join(RES, "risk_scaling.csv"), index=False)
    print("risk_scaling.csv written")


def intraday_rejection():
    ZERO = Costs(0, 0, 0)
    rows = []
    for tag in INSTR:
        df = load(tag, "M15")
        configs = [
            ("ORB or60 rr2 L+S", build_signals_orb(df, or_min=60, rr=2.0, shorts=True)),
            ("ORB or60 rr2 long+trend", build_signals_orb(df, or_min=60, rr=2.0, shorts=False,
                                                          trend_filter=True, trend_n=50)),
            ("ORB or30 rr1 L+S", build_signals_orb(df, or_min=30, rr=1.0, shorts=True)),
            ("IntradayMom 1h", build_signals_intraday_mom(df, signal_min=60, shorts=True)),
        ]
        for name, s in configs:
            g = trade_metrics(backtest(df, s, ZERO))
            net = trade_metrics(backtest(df, s, DEFAULT_COSTS[tag]))
            rows.append({"instrument": tag, "config": name, "trades": g["trades"],
                         "gross_E[R]": round(g["expectancy_R"], 4), "gross_PF": round(g["profit_factor"], 3),
                         "net_E[R]": round(net["expectancy_R"], 4), "net_PF": round(net["profit_factor"], 3),
                         "net_maxDD_%": round(net["max_drawdown"] * 100, 1)})
    pd.DataFrame(rows).to_csv(os.path.join(RES, "intraday_rejection.csv"), index=False)
    print("intraday_rejection.csv written")


def benchmark():
    rows = []
    for tag in INSTR:
        d = daily(tag)
        bh = d["close"].pct_change().dropna()
        yrs = (d.index[-1] - d.index[0]).days / 365.25
        cagr = (d["close"].iloc[-1] / d["close"].iloc[0]) ** (1 / yrs) - 1
        dd = ((1 + bh).cumprod() / (1 + bh).cumprod().cummax() - 1).min()
        rows.append({"instrument": tag, "buyhold_cagr_%": round(cagr * 100, 1),
                     "buyhold_sharpe": round(bh.mean() / bh.std() * np.sqrt(252), 2),
                     "buyhold_maxDD_%": round(dd * 100, 1)})
    pd.DataFrame(rows).to_csv(os.path.join(RES, "benchmark.csv"), index=False)
    print("benchmark.csv written")


if __name__ == "__main__":
    os.makedirs(RES, exist_ok=True)
    event_study()
    pooled = edge_decay()
    risk_scaling(pooled)
    intraday_rejection()
    benchmark()
    print("\nDiagnostics complete.")
