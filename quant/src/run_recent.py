"""
run_recent.py
-------------
Backtest on the user-provided REAL recent data (Investing.com, ~2011-2026):
SPX, NQ, DAX (equity) + GOLD (commodity) + US10Y (synthetic bond price).
Finally covers the periods asked for: COVID 2020, rate-hikes 2022, bull 2021-2024.

Sleeves: MR (indices, long-only) + TF (all, long+short). Event-driven engine.
"""
import os, json
import numpy as np
import pandas as pd
from engine import backtest, Costs, monte_carlo
from strategies import build_signals_meanrev, build_signals_trend_daily

D = os.path.join(os.path.dirname(__file__), "..", "data", "recent")
RES = os.path.join(os.path.dirname(__file__), "..", "results")
INDICES = ["SPX", "NQ", "DAX"]
ALLI = ["SPX", "NQ", "DAX", "GOLD", "US10Y"]


def load(i):
    df = pd.read_csv(f"{D}/{i}.csv", parse_dates=[0], index_col=0)
    df.index = df.index.tz_localize(None) if df.index.tz else df.index
    return df


def costs(df):
    b = float(df["close"].median()) / 1e4
    return Costs(1.5 * b, 1.0 * b, 1.5 * b)


def combine(tl, cap, risk, start=1e5):
    ev, meta, tid = [], {}, 0
    for trs in tl.values():
        for t in trs:
            ev.append((t.entry_time, 0, tid)); ev.append((t.exit_time, 1, tid)); meta[tid] = t.r; tid += 1
    ev.sort(key=lambda x: (x[0], -x[1]))
    eq, oc, ra, maxc, acc = start, 0, {}, 0, []
    T, V = [ev[0][0]], [eq]
    for tm, ty, k in ev:
        if ty == 0:
            if oc < cap:
                ra[k] = risk * eq; oc += 1; maxc = max(maxc, oc); acc.append(k)
        else:
            if k in ra:
                eq += meta[k] * ra[k]; oc -= 1; T.append(tm); V.append(eq)
    return pd.Series(V, index=pd.DatetimeIndex(T)).sort_index(), np.array([meta[k] for k in acc]), maxc


def st(eq):
    if len(eq) < 3: return np.nan, np.nan
    y = (eq.index[-1] - eq.index[0]).days / 365.25
    return (eq.iloc[-1] / eq.iloc[0]) ** (1 / y) - 1, (eq / eq.cummax() - 1).min()


def seg(eq, a, b):
    e = eq.loc[a:b]
    if len(e) < 3: return None
    return e.iloc[-1] / e.iloc[0] - 1, (e / e.cummax() - 1).min()


def main():
    MR = dict(rsi_n=2, os_th=10.0, trend_n=200, exit_th=65.0, stop_atr=3.0, atr_n=14, max_hold=8, session="all", shorts=False)
    TR = dict(entry_n=50, exit_n=20, trend_n=200, stop_atr=3.0, atr_n=14, shorts=True, longs=True)
    tl, ntot = {}, 0
    print("Per-instrument (range | TF trades | MR trades):")
    for i in ALLI:
        df = load(i); c = costs(df)
        rtf = backtest(df, build_signals_trend_daily(df, **TR), c, allow_short=True)
        tl[("TF", i)] = rtf["trades"]; ntot += len(rtf["trades"])
        line = f"  {i:6s} {df.index.min().date()}..{df.index.max().date()}  TF={len(rtf['trades']):3d}"
        if i in INDICES:
            rmr = backtest(df, build_signals_meanrev(df, **MR), c, allow_short=False)
            tl[("MR", i)] = rmr["trades"]; ntot += len(rmr["trades"]); line += f"  MR={len(rmr['trades']):3d}"
        print(line)
    print(f"TOTAL trades = {ntot}")

    # sleeves standalone (1% risk)
    print("\nSleeve standalone (1% risk, cap 8):")
    for nm in ["MR", "TF"]:
        sub = {k: v for k, v in tl.items() if k[0] == nm}
        eq, r, _ = combine(sub, 8, 0.01)
        c, d = st(eq)
        f2026 = seg(eq, "2020", "2026")
        print(f"  {nm}: full CAGR {c*100:5.2f}% DD {d*100:6.1f}% Calmar {c/abs(d):.2f} | 2020-26 ret {f2026[0]*100:+.1f}% DD {f2026[1]*100:.1f}% | trades {len(r)}")

    # combined frontier
    print("\n[Combined MR+TF, cap 5] risk -> full CAGR / DD / Calmar | 2020-26 CAGR / DD | ruin>=25%")
    rows = []
    for rf in [0.01, 0.015, 0.02, 0.03]:
        eq, r, mc = combine(tl, 5, rf)
        c, d = st(eq); e2 = eq.loc["2020":]; c2, d2 = st(e2)
        mcr = monte_carlo(r, n_sims=4000, risk_frac=rf, ruin_dd=0.25, block=10)
        print(f"  {rf*100:4.1f}% -> {c*100:5.1f}% / {d*100:6.1f}% / {c/abs(d):.2f} | {c2*100:5.1f}% / {d2*100:6.1f}% | {mcr['risk_of_ruin']*100:4.1f}%")
        rows.append({"risk_%": rf*100, "full_cagr_%": round(c*100,2), "full_dd_%": round(d*100,1),
                     "calmar": round(c/abs(d),2), "p2020_cagr_%": round(c2*100,2), "p2020_dd_%": round(d2*100,1),
                     "ruin25_%": round(mcr['risk_of_ruin']*100,1)})

    # operating point: pick risk giving full maxDD nearest -13%
    best = min(rows, key=lambda x: abs(x["full_dd_%"] + 13)); rf = best["risk_%"]/100
    eq, r, mc = combine(tl, 5, rf)
    cagr, dd = st(eq)
    print(f"\n==== OPERATING POINT risk {rf*100:.1f}%: full CAGR {cagr*100:.2f}% DD {dd*100:.1f}% Calmar {cagr/abs(dd):.2f} trades {len(r)} maxConc {mc} ====")
    regimes = {"Pre 2011-2019": ("2011","2019"), "COVID 2020": ("2020-01","2020-06"),
               "Bull 2021": ("2021","2021"), "Rate-hike 2022": ("2022","2022"),
               "Recovery 2023-24": ("2023","2024"), "2025-26": ("2025","2026"),
               "FULL 2020-2026": ("2020","2026")}
    print("[Per-regime]"); reg = {}
    for nm,(a,b) in regimes.items():
        s = seg(eq,a,b)
        if s: reg[nm]={"ret_%":round(s[0]*100,1),"maxDD_%":round(s[1]*100,1)}; print(f"  {nm:16s}: ret {s[0]*100:+6.1f}%  maxDD {s[1]*100:5.1f}%")
    print("[Walk-forward]")
    for lab,a,b in [("IS 2011-2017","2011","2017"),("OOS 2018-2026","2018","2026")]:
        c2,d2=st(eq.loc[a:b]); print(f"  {lab}: CAGR {c2*100:+5.1f}%  maxDD {d2*100:5.1f}%")
    mcf = monte_carlo(r, n_sims=8000, risk_frac=rf, ruin_dd=0.25, block=10)
    print(f"[Monte Carlo] medDD {mcf['maxdd_p50']*100:.1f}%  p95DD {mcf['maxdd_p95']*100:.1f}%  ruin>=25% {mcf['risk_of_ruin']*100:.1f}%")

    json.dump({"operating_risk_%": rf*100, "full": {"cagr_%": round(cagr*100,2),"dd_%": round(dd*100,1),"calmar": round(cagr/abs(dd),2)},
               "frontier": rows, "per_regime": reg, "trades": ntot,
               "mc": {"medDD_%": round(mcf['maxdd_p50']*100,1),"p95DD_%": round(mcf['maxdd_p95']*100,1),"ruin25_%": round(mcf['risk_of_ruin']*100,2)}},
              open(f"{RES}/recent_summary.json","w"), indent=2, default=float)

    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig,ax=plt.subplots(2,1,figsize=(11,8))
    ax[0].plot(eq.index, eq.values/eq.iloc[0],"k",lw=1.5); ax[0].set_yscale("log")
    ax[0].set_title(f"Recent real data 2011-2026 — MR+TF (risk {rf*100:.0f}%, CAGR {cagr*100:.1f}%, DD {dd*100:.1f}%)")
    ax[0].grid(alpha=.3,which="both"); ax[0].set_ylabel("Equity (log)")
    d=eq/eq.cummax()-1; ax[1].fill_between(d.index,d.values*100,0,color="tab:red",alpha=.5); ax[1].grid(alpha=.3); ax[1].set_ylabel("DD %")
    plt.tight_layout(); plt.savefig(f"{RES}/recent_equity.png",dpi=110); print("\nsaved recent_equity.png")


if __name__ == "__main__":
    main()
