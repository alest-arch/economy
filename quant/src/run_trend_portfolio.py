"""
run_trend_portfolio.py
----------------------
Diversified cross-asset trend-following portfolio (managed-futures style) on the
25-instrument OANDA universe (2005-2020). This is the ONLY robust route to a higher
return/drawdown ratio: diversification raises the Calmar that leverage cannot.

Trend rule per instrument: dual-Donchian(50/20) breakout, long+short, ATR(14) stop
(3*ATR), let winners run. 1% risk per trade. Costs modelled in bps of price.

Reports: total trades, CAGR, maxDD, Calmar, Sharpe, per-period, max concurrent
positions, asset-class correlation, risk-scaling frontier, Monte-Carlo ruin.
"""
import os, json
import numpy as np
import pandas as pd

from engine import backtest, trade_metrics, monte_carlo, Costs
from strategies import build_signals_trend_daily
from build_universe import CLASS

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "universe")
RES = os.path.join(os.path.dirname(__file__), "..", "results")
PERIODS = [("2005", "2009"), ("2010", "2014"), ("2015", "2020")]
TR = dict(entry_n=50, exit_n=20, trend_n=None, stop_atr=3.0, atr_n=14, shorts=True, longs=True)
COST_BPS = dict(half=1.0, slip=1.0, stop_extra=1.5)   # per side, bps of price


def load(inst):
    return pd.read_csv(f"{DATA}/{inst}.csv", parse_dates=[0], index_col=0)


def costs_for(df):
    p = float(df["close"].median())
    b = p / 1e4
    return Costs(COST_BPS["half"] * b, COST_BPS["slip"] * b, COST_BPS["stop_extra"] * b)


def combine(trade_lists, cap=None, start=100_000.0, risk=0.01):
    ev, meta, tid = [], {}, 0
    for trades in trade_lists.values():
        for t in trades:
            ev.append((t.entry_time, 0, tid)); ev.append((t.exit_time, 1, tid)); meta[tid] = t.r; tid += 1
    ev.sort(key=lambda x: (x[0], -x[1]))
    eq, openct, maxc = start, 0, 0
    risk_at, acc = {}, []
    times, vals = [ev[0][0]], [eq]
    for time, typ, i in ev:
        if typ == 0:
            if cap is None or openct < cap:
                risk_at[i] = risk * eq; openct += 1; maxc = max(maxc, openct); acc.append(i)
        else:
            if i in risk_at:
                eq += meta[i] * risk_at[i]; openct -= 1
                times.append(time); vals.append(eq)
    return pd.Series(vals, index=pd.DatetimeIndex(times)).sort_index(), np.array([meta[i] for i in acc]), maxc


def stats(eq):
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1
    dd = (eq / eq.cummax() - 1).min()
    rets = eq.pct_change().dropna()
    # daily-ish sharpe from the irregular equity steps (approx)
    sh = rets.mean() / rets.std() * np.sqrt(len(rets) / yrs) if rets.std() > 0 else np.nan
    return cagr, dd, sh, yrs


def main():
    insts = sorted([f[:-4] for f in os.listdir(DATA) if f.endswith(".csv")])
    trades_by, monthly = {}, {}
    total = 0
    for inst in insts:
        df = load(inst)
        res = backtest(df, build_signals_trend_daily(df, **TR), costs_for(df), allow_short=True)
        trades_by[inst] = res["trades"]
        total += len(res["trades"])
        s = pd.Series([t.r for t in res["trades"]],
                      index=pd.DatetimeIndex([t.exit_time for t in res["trades"]]).tz_localize(None))
        monthly[inst] = s.resample("ME").sum() if len(s) else pd.Series(dtype=float)
    print(f"TOTAL TRADES across {len(insts)} instruments: {total}")

    eq, r_all, maxc = combine(trades_by, cap=None)
    cagr, dd, sh, yrs = stats(eq)
    print(f"\n[PORTFOLIO uncapped] trades={len(r_all)} maxConcurrent={maxc}")
    print(f"  CAGR={cagr*100:.2f}%  maxDD={dd*100:.1f}%  Calmar={cagr/abs(dd):.2f}  Sharpe={sh:.2f}  ({yrs:.1f}y)")
    eqc, r_c, _ = combine(trades_by, cap=3)
    cg, ddc, shc, _ = stats(eqc)
    print(f"[PORTFOLIO cap=3]   CAGR={cg*100:.2f}%  maxDD={ddc*100:.1f}%  Calmar={cg/abs(ddc):.2f}  (constraint 1-3 concurrent)")

    print("\n[Per-period, uncapped]")
    for lo, hi in PERIODS:
        e = eq.loc[lo:hi]
        if len(e) > 2:
            c, d, _, _ = stats(e)
            print(f"  {lo}-{hi}: CAGR {c*100:+6.1f}%  maxDD {d*100:5.1f}%")

    # asset-class monthly aggregation + correlation
    classes = {}
    for inst, m in monthly.items():
        cl = CLASS.get(inst, "?")
        classes[cl] = classes.get(cl, pd.Series(dtype=float)).add(m, fill_value=0.0)
    cdf = pd.DataFrame(classes).fillna(0.0)
    print("\n[Asset-class monthly-R correlation]")
    print(cdf.corr().round(2).to_string())

    # risk scaling -> where is 14% CAGR and what DD?
    print("\n[Risk scaling, uncapped]  risk% -> CAGR / maxDD / ruin>=20%")
    rows = []
    for rf in [0.005, 0.01, 0.015, 0.02, 0.03]:
        e, rr, _ = combine(trades_by, cap=None, risk=rf)
        c, d, _, _ = stats(e)
        mc = monte_carlo(r_all, n_sims=4000, risk_frac=rf, ruin_dd=0.20, block=5)
        print(f"  {rf*100:4.1f}% -> CAGR {c*100:5.1f}%  maxDD {d*100:5.1f}%  ruin {mc['risk_of_ruin']*100:4.1f}%")
        rows.append({"risk_%": rf * 100, "cagr_%": round(c * 100, 2), "maxDD_%": round(d * 100, 1),
                     "ruin20_%": round(mc["risk_of_ruin"] * 100, 2)})

    mc = monte_carlo(r_all, n_sims=8000, risk_frac=0.01, ruin_dd=0.20, block=5)
    summary = {"instruments": len(insts), "total_trades": total, "max_concurrent": maxc,
               "uncapped_1pct": {"cagr_%": round(cagr * 100, 2), "maxDD_%": round(dd * 100, 1),
                                 "calmar": round(cagr / abs(dd), 2), "sharpe": round(sh, 2)},
               "cap3_1pct": {"cagr_%": round(cg * 100, 2), "maxDD_%": round(ddc * 100, 1)},
               "risk_scaling": rows, "mc_ruin20_1pct_%": round(mc["risk_of_ruin"] * 100, 2)}
    with open(f"{RES}/trend_portfolio_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=float)

    _plot(eq, eqc, trades_by)
    print(f"\nArtifacts -> results/trend_portfolio_*  (summary + equity png)")


def _plot(eq, eqc, trades_by):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(eq.index, eq.values / eq.iloc[0], "k", lw=1.8, label="Trend portfolio (25 mkts, 1% risk, uncapped)")
    ax.plot(eqc.index, eqc.values / eqc.iloc[0], "tab:red", lw=1.2, label="Same, capped at 3 concurrent")
    ax.set_yscale("log"); ax.set_title("Diversified cross-asset trend portfolio (2005-2020)")
    ax.set_ylabel("Equity (x start, log)"); ax.legend(); ax.grid(alpha=.3, which="both")
    plt.tight_layout(); plt.savefig(f"{RES}/trend_portfolio_equity.png", dpi=110)
    print("saved trend_portfolio_equity.png")


if __name__ == "__main__":
    main()
