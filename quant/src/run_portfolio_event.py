"""
run_portfolio_event.py
----------------------
Multi-asset, multi-strategy portfolio measured with the TRUSTED event-driven engine
(no look-ahead, real trades, intrabar stops). Cleaner/robust vs the vectorised version.

Sleeves:
  MR : daily RSI(2)<10 above SMA200 + vol circuit-breaker, long-only, on the 8 EQUITY
       INDICES (the validated reversion edge, generalised across global indices).
  TF : daily Donchian(50/20) breakout, long+short, ATR stop, on ALL 25 markets.

Combination: every trade risks `risk%` of shared equity; max `cap` concurrent
positions; risk scaled to hit the drawdown budget. Costs in bps of price.
"""
import os, json
import numpy as np
import pandas as pd
from engine import backtest, Costs, monte_carlo
from strategies import build_signals_meanrev, build_signals_trend_daily

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "universe")
RES = os.path.join(os.path.dirname(__file__), "..", "results")
GROUPS = {
    "equity": ["SPX500_USD", "NAS100_USD", "FR40_EUR", "JP225_USD", "UK100_GBP", "US2000_USD", "AU200_AUD", "NL25_EUR"],
    "commodity": ["XAU_USD", "WTICO_USD", "CORN_USD", "WHEAT_USD", "SOYBN_USD", "SUGAR_USD", "NATGAS_USD"],
    "bond": ["USB10Y_USD", "USB02Y_USD", "DE10YB_EUR", "UK10YB_GBP"],
    "fx": ["EUR_USD", "EUR_JPY", "AUD_USD", "GBP_USD", "USD_CAD", "AUD_JPY"],
}
ALL = [i for l in GROUPS.values() for i in l]
INDICES = GROUPS["equity"]


def load(i):
    df = pd.read_csv(f"{DATA}/{i}.csv", parse_dates=[0], index_col=0)
    df.index = df.index.tz_localize(None)
    return df


def costs(df):
    b = float(df["close"].median()) / 1e4
    return Costs(1.5 * b, 1.0 * b, 1.5 * b)


def combine(trade_lists, cap, risk, start=1e5):
    ev, meta, tid = [], {}, 0
    for trs in trade_lists.values():
        for t in trs:
            ev.append((t.entry_time, 0, tid)); ev.append((t.exit_time, 1, tid)); meta[tid] = t.r; tid += 1
    ev.sort(key=lambda x: (x[0], -x[1]))
    eq, oc, ra, maxc = start, 0, {}, 0
    T, V, acc = [ev[0][0]], [eq], []
    for tm, ty, k in ev:
        if ty == 0:
            if oc < cap:
                ra[k] = risk * eq; oc += 1; maxc = max(maxc, oc); acc.append(k)
        else:
            if k in ra:
                eq += meta[k] * ra[k]; oc -= 1; T.append(tm); V.append(eq)
    return pd.Series(V, index=pd.DatetimeIndex(T)).sort_index(), np.array([meta[k] for k in acc]), maxc


def st(eq):
    y = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / y) - 1
    dd = (eq / eq.cummax() - 1).min()
    return cagr, dd, y


def main():
    MR = dict(rsi_n=2, os_th=10.0, trend_n=200, exit_th=65.0, stop_atr=3.0, atr_n=14,
              max_hold=8, session="all", shorts=False)
    TR = dict(entry_n=50, exit_n=20, trend_n=200, stop_atr=3.0, atr_n=14, shorts=True, longs=True)

    tl, mr_tr, tf_tr = {}, [], []
    per_inst = []
    for i in ALL:
        df = load(i); c = costs(df)
        rtf = backtest(df, build_signals_trend_daily(df, **TR), c, allow_short=True)
        tl[("TF", i)] = rtf["trades"]; tf_tr += rtf["trades"]
        line = f"  {i:12s} TF n={len(rtf['trades']):3d}"
        if i in INDICES:
            rmr = backtest(df, build_signals_meanrev(df, **MR), c, allow_short=False)
            tl[("MR", i)] = rmr["trades"]; mr_tr += rmr["trades"]
            line += f"  MR n={len(rmr['trades']):3d}"
        per_inst.append(line)
    print("Per-instrument trade counts:"); print("\n".join(per_inst))
    total = len(mr_tr) + len(tf_tr)
    print(f"\nTotal trades: MR={len(mr_tr)} + TF={len(tf_tr)} = {total}")

    # sleeve standalone (1% risk, cap big) for sharpe/corr context
    for nm, sub in [("MR", {k: v for k, v in tl.items() if k[0] == "MR"}),
                    ("TF", {k: v for k, v in tl.items() if k[0] == "TF"})]:
        eq, r, mc = combine(sub, cap=10, risk=0.01)
        c, d, y = st(eq)
        print(f"sleeve {nm}: CAGR {c*100:5.2f}% maxDD {d*100:6.1f}% Calmar {c/abs(d):.2f} trades {len(r)} maxConc {mc}")

    # ---- combined: scan risk to hit ~12-15% DD (cap concurrent = 6) ----
    print("\n[Combined MR+TF, cap=6] risk -> CAGR / maxDD / Calmar / ruin>=25%")
    rows = []
    for rf in [0.005, 0.0075, 0.01, 0.015, 0.02]:
        eq, r, mc = combine(tl, cap=6, risk=rf)
        c, d, y = st(eq)
        mcr = monte_carlo(r, n_sims=4000, risk_frac=rf, ruin_dd=0.25, block=10)
        print(f"  {rf*100:4.2f}% -> CAGR {c*100:5.1f}%  maxDD {d*100:6.1f}%  Calmar {c/abs(d):.2f}  ruin {mcr['risk_of_ruin']*100:4.1f}%  (maxConc {mc})")
        rows.append({"risk_%": rf*100, "cagr_%": round(c*100, 2), "maxDD_%": round(d*100, 1),
                     "calmar": round(c/abs(d), 2), "ruin25_%": round(mcr["risk_of_ruin"]*100, 1)})

    # pick operating point with maxDD closest to -13%
    best = min(rows, key=lambda x: abs(x["maxDD_%"] + 13))
    rf = best["risk_%"] / 100
    eq, r, mc = combine(tl, cap=6, risk=rf)
    cagr, dd, y = st(eq)
    print(f"\n==== OPERATING POINT: risk {rf*100:.2f}%  CAGR {cagr*100:.2f}%  maxDD {dd*100:.1f}%  Calmar {cagr/abs(dd):.2f}  trades {len(r)} ====")

    regimes = {"GFC 2008-09": ("2007-10", "2009-03"), "EuroCrisis 2011": ("2011-05", "2011-12"),
               "Bull 2013-2017": ("2013-01", "2017-12"), "Q4-2018": ("2018-10", "2018-12"),
               "COVID 2020": ("2020-02", "2020-05")}
    print("[Per-regime, operating point]")
    reg = {}
    for nm, (a, b) in regimes.items():
        e = eq.loc[a:b]
        if len(e) > 2:
            rr = e.iloc[-1]/e.iloc[0]-1; d2 = (e/e.cummax()-1).min()
            reg[nm] = {"ret_%": round(rr*100, 1), "maxDD_%": round(d2*100, 1)}
            print(f"  {nm:16s}: ret {rr*100:+6.1f}%  maxDD {d2*100:5.1f}%")
    # IS/OOS
    print("[Walk-forward IS/OOS]")
    for lab, a, b in [("IS 2005-2012", "2005", "2012"), ("OOS 2013-2020", "2013", "2020")]:
        e = eq.loc[a:b]
        c2, d2, _ = st(e); print(f"  {lab}: CAGR {c2*100:+5.1f}%  maxDD {d2*100:5.1f}%")
    mcf = monte_carlo(r, n_sims=8000, risk_frac=rf, ruin_dd=0.25, block=10)
    print(f"[Monte Carlo] medDD {mcf['maxdd_p50']*100:.1f}%  p95DD {mcf['maxdd_p95']*100:.1f}%  ruin>=25% {mcf['risk_of_ruin']*100:.1f}%")

    summary = {"operating_point": {"risk_%": rf*100, "cagr_%": round(cagr*100, 2), "maxDD_%": round(dd*100, 1),
               "calmar": round(cagr/abs(dd), 2), "trades": len(r), "max_concurrent": mc},
               "frontier": rows, "per_regime": reg,
               "mc": {"medDD_%": round(mcf['maxdd_p50']*100, 1), "p95DD_%": round(mcf['maxdd_p95']*100, 1),
                      "ruin25_%": round(mcf['risk_of_ruin']*100, 2)},
               "total_trades": total}
    with open(f"{RES}/portfolio_event_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=float)

    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 1, figsize=(11, 8))
    ax[0].plot(eq.index, eq.values/eq.iloc[0], "k", lw=1.6)
    ax[0].set_yscale("log"); ax[0].set_title(f"Multi-asset MR+TF portfolio (risk {rf*100:.2f}%, CAGR {cagr*100:.1f}%, maxDD {dd*100:.1f}%)")
    ax[0].grid(alpha=.3, which="both"); ax[0].set_ylabel("Equity (log)")
    d = eq/eq.cummax()-1
    ax[1].fill_between(d.index, d.values*100, 0, color="tab:red", alpha=.5); ax[1].set_ylabel("DD %"); ax[1].grid(alpha=.3)
    plt.tight_layout(); plt.savefig(f"{RES}/portfolio_event_equity.png", dpi=110)
    print(f"\nsaved portfolio_event_equity.png | total trades {total}")


if __name__ == "__main__":
    main()
