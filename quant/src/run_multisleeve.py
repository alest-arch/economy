"""
run_multisleeve.py
------------------
Multi-sleeve framework: corrected mean-reversion + long trend-following, on SPX & NQ.
Goal = survival across regimes, NOT return maximisation.

Sleeves (each trade risks 1% of shared equity; max 3 concurrent positions):
  MR    : daily RSI(2) mean-reversion above SMA200, H4 execution, long-only,
          + volatility circuit-breaker (skip dips when ATR-percentile > 0.90).
  TREND : daily Donchian(50/20) breakout, long-only (short side has no edge on
          indices -> discarded), ATR stop. Pays exactly where MR is flat.

Outputs (../results/):
  msleeve_period.csv     per-period expectancy/PF/maxDD for each sleeve & combined
  msleeve_correlation.csv monthly-return correlation between sleeves
  msleeve_walkforward.csv OOS walk-forward per sleeve
  msleeve_montecarlo.json combined risk-of-ruin
  msleeve_equity.png      sleeve & combined equity (+ buy&hold)
  msleeve_summary.json
"""
from __future__ import annotations
import json, os
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

from engine import (backtest, trade_metrics, monte_carlo, walk_forward, Signals,
                    DEFAULT_COSTS)
from strategies import build_signals_swing_mtf, build_signals_trend_daily, make_daily

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
RES = os.path.join(os.path.dirname(__file__), "..", "results")
INSTR = ["SPX", "NQ"]
PERIODS = [("2005", "2009"), ("2010", "2014"), ("2015", "2019"), ("2020", "2020")]

MR_BASE = dict(rsi_n=2, os_th=10.0, trend_n=200, exit_th=65.0, stop_atr=3.0,
               atr_n=14, max_hold_bars=30, session="us", max_atr_rank=0.90)
TR_BASE = dict(entry_n=50, exit_n=20, trend_n=200, stop_atr=3.0, atr_n=14,
               shorts=False, longs=True)

MR_GRID = [dict(rsi_n=2, trend_n=200, atr_n=14, max_hold_bars=30, session="us",
                max_atr_rank=0.90, os_th=o, stop_atr=s, exit_th=e)
           for o in (5.0, 10.0, 15.0) for s in (2.0, 3.0, 4.5) for e in (55.0, 65.0)]
TR_GRID = [dict(trend_n=200, atr_n=14, shorts=False, longs=True,
                entry_n=n, exit_n=max(10, n // 2), stop_atr=s)
           for n in (30, 50, 100) for s in (2.0, 3.0, 4.5)]


def load(tag, tf):
    return pd.read_csv(os.path.join(DATA, f"{tag}_{tf}.csv"), parse_dates=[0], index_col=0)


def daily(tag):
    return make_daily(load(tag, "H1"))


# ---- signal builders for the two sleeves (full-history then reindex for WFA) ----
def mr_signals(tag):
    return build_signals_swing_mtf(load(tag, "H4"), daily(tag), **MR_BASE)


def tr_signals(tag):
    return build_signals_trend_daily(daily(tag), **TR_BASE)


def _reindex(sig, ix):
    return Signals(sig.long_entry.reindex(ix).fillna(False), sig.short_entry.reindex(ix).fillna(False),
                   sig.stop_dist.reindex(ix), sig.target_dist.reindex(ix),
                   sig.exit_long.reindex(ix).fillna(False), sig.exit_short.reindex(ix).fillna(False),
                   max_hold=sig.max_hold,
                   force_flat=(sig.force_flat.reindex(ix).fillna(False) if sig.force_flat is not None else None))


def run_sleeve(tag, which):
    """Return the backtest result for one sleeve on one instrument."""
    if which == "MR":
        df, sig = load(tag, "H4"), mr_signals(tag)
        return backtest(df, sig, DEFAULT_COSTS[tag], allow_short=False)
    else:
        df, sig = daily(tag), tr_signals(tag)
        return backtest(df, sig, DEFAULT_COSTS[tag], allow_short=True)


# --------------------------------------------------------------------------- #
def per_period(trades):
    T = pd.DataFrame([(t.entry_time, t.r) for t in trades], columns=["t", "r"]).set_index("t").sort_index()
    out = {}
    for lo, hi in PERIODS:
        s = T.loc[lo:hi]["r"] if len(T) else pd.Series([], dtype=float)
        if len(s) >= 3:
            pf = s[s > 0].sum() / (-s[s <= 0].sum()) if (s <= 0).any() else np.inf
            out[f"{lo}-{hi}"] = {"n": int(len(s)), "E_R": round(s.mean(), 4),
                                 "PF": round(min(pf, 99), 2), "sum_R": round(s.sum(), 2)}
        else:
            out[f"{lo}-{hi}"] = {"n": int(len(s)), "E_R": None, "PF": None, "sum_R": round(s.sum(), 2) if len(s) else 0.0}
    return out


def combine_capped(trade_lists: dict, cap=3, start=100_000.0, risk=0.01):
    """Combine all sleeve/instrument trade streams onto shared equity, capping
    simultaneous open positions at `cap` (respects '1-3 trades at once')."""
    ev = []
    tid = 0
    meta = {}
    for key, trades in trade_lists.items():
        for t in trades:
            ev.append((t.entry_time, 0, tid)); ev.append((t.exit_time, 1, tid))
            meta[tid] = t.r; tid += 1
    ev.sort(key=lambda x: (x[0], -x[1]))   # exits before entries at same ts
    equity = start
    open_ct = 0
    accepted, risk_at = set(), {}
    max_conc = 0
    times, vals = [ev[0][0]], [equity]
    acc_r = []
    for time, typ, i in ev:
        if typ == 0:                       # entry
            if open_ct < cap:
                accepted.add(i); risk_at[i] = risk * equity; open_ct += 1
                max_conc = max(max_conc, open_ct)
        else:                              # exit
            if i in accepted:
                pnl = meta[i] * risk_at[i]; equity += pnl; open_ct -= 1
                acc_r.append(meta[i]); times.append(time); vals.append(equity)
    eq = pd.Series(vals, index=pd.DatetimeIndex(times)).sort_index()
    return eq, np.array(acc_r), max_conc


def monthly_returns(trades, idx_start, idx_end):
    """Equity-agnostic monthly sum of R (for correlation), tz-naive month-end index."""
    if not trades:
        return pd.Series(dtype=float)
    ix = pd.DatetimeIndex([t.exit_time for t in trades]).tz_localize(None)
    s = pd.Series([t.r for t in trades], index=ix).sort_index()
    return s.resample("ME").sum()


def eq_period_stats(eq):
    out = {}
    for lo, hi in PERIODS:
        e = eq.loc[lo:hi]
        if len(e) < 2:
            out[f"{lo}-{hi}"] = {"ret_%": None, "maxDD_%": None}; continue
        ret = e.iloc[-1] / e.iloc[0] - 1
        dd = (e / e.cummax() - 1).min()
        out[f"{lo}-{hi}"] = {"ret_%": round(ret * 100, 2), "maxDD_%": round(dd * 100, 1)}
    return out


# --------------------------------------------------------------------------- #
def main():
    os.makedirs(RES, exist_ok=True)
    sleeve_trades = {}     # (which,tag) -> trades
    sleeve_pool = {"MR": [], "TREND": []}
    for which in ["MR", "TREND"]:
        for tag in INSTR:
            res = run_sleeve(tag, which)
            sleeve_trades[(which, tag)] = res["trades"]
            sleeve_pool[which].extend(res["trades"])

    # ---------- per-period per sleeve ----------
    period_rows = {}
    for which in ["MR", "TREND"]:
        period_rows[which] = per_period(sleeve_pool[which])
        print(f"\n[{which}] per-period (both instruments pooled):")
        for k, v in period_rows[which].items():
            print(f"   {k}: {v}")

    # ---------- combined (capped at 3) ----------
    eq_comb, r_comb, max_conc = combine_capped(sleeve_trades, cap=3)
    bh = {tag: daily(tag)["close"] for tag in INSTR}
    print(f"\n[COMBINED] trades={len(r_comb)} max_concurrent={max_conc}")
    comb_period = eq_period_stats(eq_comb)
    period_rows["COMBINED_equity"] = comb_period
    full_m = {
        "final_mult": round(eq_comb.iloc[-1] / eq_comb.iloc[0], 3),
        "maxDD_%": round((eq_comb / eq_comb.cummax() - 1).min() * 100, 1),
        "trades": len(r_comb), "expectancy_R": round(float(np.mean(r_comb)), 4),
        "PF": round(r_comb[r_comb > 0].sum() / -r_comb[r_comb <= 0].sum(), 3),
        "max_concurrent": max_conc,
    }
    for k, v in comb_period.items():
        print(f"   {k}: {v}")
    print(f"   FULL: {full_m}")

    # ---------- correlation between sleeves (monthly R) ----------
    a, b = eq_comb.index[0], eq_comb.index[-1]
    mr_m = monthly_returns(sleeve_pool["MR"], a, b)
    tr_m = monthly_returns(sleeve_pool["TREND"], a, b)
    # align on the union of active months (a month absent in one sleeve -> 0 R that month)
    aligned = pd.concat([mr_m.rename("MR"), tr_m.rename("TREND")], axis=1).fillna(0.0)
    corr = float(aligned["MR"].corr(aligned["TREND"]))
    print(f"\n[CORRELATION] monthly-R  MR vs TREND = {corr:+.3f}")
    pd.DataFrame({"MR": mr_m, "TREND": tr_m}).to_csv(os.path.join(RES, "msleeve_correlation.csv"))

    # ---------- walk-forward per sleeve ----------
    wf_rows = []
    for which, grid in [("MR", MR_GRID), ("TREND", TR_GRID)]:
        for tag in INSTR:
            if which == "MR":
                exec_full, daily_full = load(tag, "H4"), daily(tag)
                def bs(slice_df, _ef=exec_full, _df=daily_full, **p):
                    return _reindex(build_signals_swing_mtf(_ef, _df, **p), slice_df.index)
                wf = walk_forward(exec_full, bs, grid, DEFAULT_COSTS[tag], is_years=4, oos_years=1,
                                  score_key="profit_factor", min_trades=8, allow_short=False)
            else:
                d = daily(tag)
                def bs(slice_df, _d=d, **p):
                    return _reindex(build_signals_trend_daily(_d, **p), slice_df.index)
                wf = walk_forward(d, bs, grid, DEFAULT_COSTS[tag], is_years=4, oos_years=1,
                                  score_key="profit_factor", min_trades=5, allow_short=True)
            r = wf["oos_r"]
            if len(r):
                pf = r[r > 0].sum() / -r[r <= 0].sum() if (r <= 0).any() else np.inf
                wf_rows.append({"sleeve": which, "instrument": tag, "oos_trades": len(r),
                                "oos_E_R": round(float(r.mean()), 4), "oos_PF": round(min(pf, 99), 2),
                                "oos_winrate_%": round(float((r > 0).mean() * 100), 1),
                                "pos_folds": sum(1 for f in wf["folds"] if (f["oos_expectancy_R"] or 0) > 0),
                                "n_folds": len(wf["folds"])})
    pd.DataFrame(wf_rows).to_csv(os.path.join(RES, "msleeve_walkforward.csv"), index=False)
    print("\n[WALK-FORWARD OOS per sleeve]")
    for r in wf_rows:
        print(f"   {r['sleeve']:5s} {r['instrument']}: N={r['oos_trades']} E[R]={r['oos_E_R']:+.3f} "
              f"PF={r['oos_PF']} WR={r['oos_winrate_%']}% folds+={r['pos_folds']}/{r['n_folds']}")

    # ---------- Monte Carlo on combined ----------
    mc = monte_carlo(r_comb, n_sims=10000, risk_frac=0.01, ruin_dd=0.20, block=1)
    mcb = monte_carlo(r_comb, n_sims=10000, risk_frac=0.01, ruin_dd=0.20, block=5)
    print(f"\n[MC combined] ruin>=20%DD reshuffle={mc['risk_of_ruin']:.2%} bootstrap={mcb['risk_of_ruin']:.2%} "
          f"medDD={mc['maxdd_p50']:.1%} p95DD={mc['maxdd_p95']:.1%} bootP(loss)={mcb['prob_loss']:.2%}")

    # ---------- persist ----------
    with open(os.path.join(RES, "msleeve_period.csv"), "w") as f:
        f.write("block,period,n,E_R,PF,sum_R_or_ret\n")
        for block in ["MR", "TREND"]:
            for k, v in period_rows[block].items():
                f.write(f"{block},{k},{v['n']},{v['E_R']},{v['PF']},{v['sum_R']}\n")
        for k, v in period_rows["COMBINED_equity"].items():
            f.write(f"COMBINED,{k},,,{v['ret_%']},{v['maxDD_%']}\n")
    with open(os.path.join(RES, "msleeve_montecarlo.json"), "w") as f:
        json.dump({"reshuffle": mc, "bootstrap": mcb}, f, indent=2, default=float)
    with open(os.path.join(RES, "msleeve_summary.json"), "w") as f:
        json.dump({"mr_base": MR_BASE, "tr_base": TR_BASE, "combined": full_m,
                   "sleeve_correlation_monthlyR": corr, "per_period": period_rows,
                   "walk_forward": wf_rows}, f, indent=2, default=float)

    _plot(sleeve_trades, eq_comb, bh)
    print(f"\nArtifacts -> {os.path.relpath(RES)}/  (msleeve_*)")


def _eq_from_trades(trades, start=100_000.0, risk=0.01):
    trades = sorted(trades, key=lambda t: t.exit_time)
    eq = start; times, vals = [], []
    for t in trades:
        eq *= (1 + risk * t.r); times.append(t.exit_time); vals.append(eq)
    return pd.Series(vals, index=pd.DatetimeIndex(times)) if times else pd.Series([start])


def _plot(sleeve_trades, eq_comb, bh):
    fig, ax = plt.subplots(2, 1, figsize=(11, 9))
    mr = _eq_from_trades(sleeve_trades[("MR", "SPX")] + sleeve_trades[("MR", "NQ")])
    tr = _eq_from_trades(sleeve_trades[("TREND", "SPX")] + sleeve_trades[("TREND", "NQ")])
    ax[0].plot(mr.index, mr.values / mr.iloc[0], label="MR sleeve (SPX+NQ)")
    ax[0].plot(tr.index, tr.values / tr.iloc[0], label="TREND sleeve (SPX+NQ)")
    ax[0].plot(eq_comb.index, eq_comb.values / eq_comb.iloc[0], "k", lw=2, label="COMBINED (cap 3)")
    ax[0].set_title("Multi-sleeve equity — 1% risk/trade, net of costs"); ax[0].legend(); ax[0].grid(alpha=.3)
    ax[0].set_ylabel("Equity (x start)")
    for tag in INSTR:
        b = bh[tag]; ax[1].plot(b.index, b.values / b.iloc[0], alpha=.7, label=f"{tag} buy&hold")
    ax[1].plot(eq_comb.index, eq_comb.values / eq_comb.iloc[0], "k", lw=2, label="COMBINED system")
    ax[1].set_title("Combined system vs buy & hold (note the drawdown difference)")
    ax[1].legend(); ax[1].grid(alpha=.3); ax[1].set_ylabel("Equity (x start)")
    plt.tight_layout(); plt.savefig(os.path.join(RES, "msleeve_equity.png"), dpi=110)
    print("saved msleeve_equity.png")


if __name__ == "__main__":
    main()
