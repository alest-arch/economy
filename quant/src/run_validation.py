"""
run_validation.py
-----------------
Full, reproducible validation of the recommended strategy:
  "Swing Mean-Reversion, Daily-signal / H4-execution" on SPX and NQ.

Produces (under ../results/):
  - metrics_fullsample.csv      headline in-sample-ish metrics (fixed params)
  - walkforward_folds.csv       per-fold IS choice + OOS outcome
  - montecarlo.json             reshuffle/bootstrap + risk-of-ruin
  - cost_stress.csv             sensitivity to 1x/2x/3x trading costs
  - equity_curves.png           OOS-stitched + combined portfolio equity
  - summary.json                everything, machine-readable

Run:  python3 run_validation.py
"""
from __future__ import annotations
import json
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from engine import (backtest, trade_metrics, monte_carlo, walk_forward,
                    Signals, DEFAULT_COSTS, Costs)
from strategies import build_signals_swing_mtf, make_daily

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
RES = os.path.join(os.path.dirname(__file__), "..", "results")
os.makedirs(RES, exist_ok=True)

INSTR = ["SPX", "NQ"]

# ---- a-priori "robust" configuration (chosen from the event study + economics,
#      NOT optimised on the equity curve) -----------------------------------
BASE = dict(rsi_n=2, os_th=10.0, trend_n=200, exit_th=65.0, stop_atr=3.0,
            atr_n=14, max_hold_bars=30, session="us")

# small, economically-motivated grid for the walk-forward param selection
GRID = [dict(rsi_n=2, trend_n=200, atr_n=14, max_hold_bars=30, session="us",
             os_th=o, stop_atr=s, exit_th=e)
        for o in (5.0, 10.0, 15.0) for s in (2.0, 3.0, 4.5) for e in (55.0, 65.0)]


def load(tag, tf):
    return pd.read_csv(os.path.join(DATA, f"{tag}_{tf}.csv"), parse_dates=[0], index_col=0)


def builder_factory(exec_full, daily_full):
    """Return a build_signals(df_slice, **p) that computes signals on FULL history
    (so SMA200/ATR have lookback) then reindexes to the slice -> no look-ahead,
    no boundary truncation inside walk-forward folds."""
    def bs(df_slice, **p):
        s = build_signals_swing_mtf(exec_full, daily_full, **p)
        ix = df_slice.index
        return Signals(
            long_entry=s.long_entry.reindex(ix).fillna(False),
            short_entry=s.short_entry.reindex(ix).fillna(False),
            stop_dist=s.stop_dist.reindex(ix),
            target_dist=s.target_dist.reindex(ix),
            exit_long=s.exit_long.reindex(ix).fillna(False),
            exit_short=s.exit_short.reindex(ix).fillna(False),
            max_hold=s.max_hold,
        )
    return bs


def combine_portfolio(trade_lists: dict, start_equity=100_000.0, risk_frac=0.01):
    """Time-accurate combiner: every trade risks 1% of *current shared* equity,
    realised at its exit; up to 2 positions can overlap (<=2% heat)."""
    timeline = []
    eid = 0
    for inst, trades in trade_lists.items():
        for t in trades:
            timeline.append((t.entry_time, 0, eid, None))
            timeline.append((t.exit_time, 1, eid, t.r))
            eid += 1
    # exits (1) before entries (0) at equal timestamps -> -typ
    timeline.sort(key=lambda x: (x[0], -x[1]))
    equity = start_equity
    risk_at_entry = {}
    times, vals = [timeline[0][0]], [equity]
    for time, typ, eid_, r in timeline:
        if typ == 0:
            risk_at_entry[eid_] = risk_frac * equity
        else:
            equity += r * risk_at_entry.get(eid_, risk_frac * equity)
            times.append(time); vals.append(equity)
    return pd.Series(vals, index=pd.DatetimeIndex(times)).sort_index()


def fmt(m):
    return {
        "trades": m.get("trades"),
        "winrate_%": round(100 * m.get("winrate", np.nan), 1),
        "avg_win_R": round(m.get("avg_win_R", np.nan), 3),
        "avg_loss_R": round(m.get("avg_loss_R", np.nan), 3),
        "expectancy_R": round(m.get("expectancy_R", np.nan), 4),
        "profit_factor": round(m.get("profit_factor", np.nan), 3),
        "max_drawdown_%": round(100 * m.get("max_drawdown", np.nan), 1),
        "cagr_%": round(100 * m.get("cagr", np.nan), 2),
        "sharpe_annual": round(m.get("sharpe_annual", np.nan), 2),
        "trades_per_year": round(m.get("trades_per_year", np.nan), 1),
        "max_consec_losses": m.get("max_consec_losses"),
    }


def main():
    summary = {"base_params": BASE, "instruments": {}, "cost_model": {}}
    full_metrics, fold_rows, cost_rows = {}, [], []
    oos_streams, full_equities, oos_trade_lists, full_trade_lists = {}, {}, {}, {}

    for tag in INSTR:
        h4 = load(tag, "H4")
        daily = make_daily(load(tag, "H1"))
        costs = DEFAULT_COSTS[tag]
        summary["cost_model"][tag] = vars(costs)
        bs = builder_factory(h4, daily)

        # ---------- (1) full-sample headline (fixed BASE params) ----------
        sig = build_signals_swing_mtf(h4, daily, **BASE)
        res = backtest(h4, sig, costs, allow_short=False)
        m = trade_metrics(res)
        full_metrics[tag] = m
        full_equities[tag] = res["equity"]
        full_trade_lists[tag] = res["trades"]
        print(f"\n[{tag}] FULL-SAMPLE (fixed params): {fmt(m)}")

        # ---------- (2) walk-forward (4y IS / 1y OOS) ----------
        wf = walk_forward(h4, bs, GRID, costs, is_years=4.0, oos_years=1.0,
                          score_key="profit_factor", min_trades=10, allow_short=False)
        oos_streams[tag] = wf["oos_r"]
        oos_trade_lists[tag] = wf["oos_trades"]
        # OOS-stitched metrics (rebuild an equity curve from OOS trades)
        oos_res = {"trades": wf["oos_trades"], "r": wf["oos_r"],
                   "equity": _equity_from_trades(wf["oos_trades"]),
                   "start_equity": 100_000.0}
        oos_m = trade_metrics(oos_res)
        print(f"[{tag}] WALK-FORWARD OOS (stitched): {fmt(oos_m)}")
        for f in wf["folds"]:
            f2 = dict(f); f2["instrument"] = tag
            fold_rows.append(f2)

        # ---------- (3) cost stress on the full-sample config ----------
        for mult in (1.0, 2.0, 3.0):
            c2 = Costs(costs.half_spread_pts * mult, costs.slip_pts * mult,
                       costs.stop_extra_slip_pts * mult)
            mm = trade_metrics(backtest(h4, sig, c2, allow_short=False))
            cost_rows.append({"instrument": tag, "cost_x": mult,
                              "expectancy_R": round(mm["expectancy_R"], 4),
                              "profit_factor": round(mm["profit_factor"], 3),
                              "cagr_%": round(100 * mm["cagr"], 2),
                              "max_dd_%": round(100 * mm["max_drawdown"], 1)})

        summary["instruments"][tag] = {
            "full_sample": fmt(m),
            "walk_forward_oos": fmt(oos_m),
            "n_folds": len(wf["folds"]),
        }

    # ---------- (4) combined portfolio (time-accurate) ----------
    port_full = combine_portfolio(full_trade_lists)
    port_oos = combine_portfolio(oos_trade_lists)
    summary["portfolio"] = {
        "full_sample": _equity_stats(port_full),
        "walk_forward_oos": _equity_stats(port_oos),
    }
    print(f"\n[PORTFOLIO] full-sample: {summary['portfolio']['full_sample']}")
    print(f"[PORTFOLIO] OOS stitched: {summary['portfolio']['walk_forward_oos']}")

    # ---------- (5) Monte Carlo + risk of ruin (pooled OOS bet stream) ----------
    pooled = np.concatenate([oos_streams[t] for t in INSTR]) if all(len(oos_streams[t]) for t in INSTR) else np.array([])
    mc = {}
    if len(pooled) > 10:
        mc["reshuffle"] = monte_carlo(pooled, n_sims=10000, risk_frac=0.01, ruin_dd=0.20, block=1)
        mc["block_bootstrap"] = monte_carlo(pooled, n_sims=10000, risk_frac=0.01, ruin_dd=0.20, block=5)
        mc["ruin_at_30dd_reshuffle"] = monte_carlo(pooled, n_sims=10000, risk_frac=0.01, ruin_dd=0.30, block=1)["risk_of_ruin"]
        print(f"\n[MC] pooled OOS trades={len(pooled)} "
              f"ruin(>=20%DD) reshuffle={mc['reshuffle']['risk_of_ruin']:.3%} "
              f"bootstrap={mc['block_bootstrap']['risk_of_ruin']:.3%} "
              f"medianDD={mc['reshuffle']['maxdd_p50']:.1%} p95DD={mc['reshuffle']['maxdd_p95']:.1%}")
    summary["monte_carlo"] = mc

    # ---------- persist ----------
    pd.DataFrame({t: fmt(full_metrics[t]) for t in INSTR}).T.to_csv(os.path.join(RES, "metrics_fullsample.csv"))
    pd.DataFrame(fold_rows).to_csv(os.path.join(RES, "walkforward_folds.csv"), index=False)
    pd.DataFrame(cost_rows).to_csv(os.path.join(RES, "cost_stress.csv"), index=False)
    with open(os.path.join(RES, "montecarlo.json"), "w") as f:
        json.dump(mc, f, indent=2, default=float)
    with open(os.path.join(RES, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=float)

    _plot(full_equities, port_full, port_oos, oos_trade_lists)
    print(f"\nArtifacts written to {os.path.relpath(RES)}/")


def _equity_from_trades(trades, start=100_000.0):
    eq = start
    times, vals = [], []
    for t in trades:
        eq *= (1.0 + 0.01 * t.r)
        times.append(t.exit_time); vals.append(eq)
    if not times:
        return pd.Series([start])
    return pd.Series(vals, index=pd.DatetimeIndex(times))


def _equity_stats(eq):
    if len(eq) < 2:
        return {}
    start, final = eq.iloc[0], eq.iloc[-1]
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    dd = (eq / eq.cummax() - 1.0).min()
    rets = eq.pct_change().dropna()
    sharpe = rets.mean() / rets.std() * np.sqrt(len(rets) / yrs) if rets.std() > 0 and yrs > 0 else np.nan
    return {"final_mult": round(final / start, 3),
            "cagr_%": round(100 * ((final / start) ** (1 / yrs) - 1), 2) if yrs > 0 else None,
            "max_dd_%": round(100 * dd, 1),
            "sharpe_annual": round(sharpe, 2)}


def _plot(full_equities, port_full, port_oos, oos_trade_lists):
    fig, ax = plt.subplots(2, 1, figsize=(11, 9))
    for tag in INSTR:
        e = full_equities[tag]
        ax[0].plot(e.index, e.values / e.iloc[0], label=f"{tag} (fixed params, full)")
    ax[0].plot(port_full.index, port_full.values / port_full.iloc[0], "k", lw=2, label="Portfolio SPX+NQ")
    ax[0].set_title("Full-sample equity (fixed a-priori params, 1% risk/trade, net of costs)")
    ax[0].set_ylabel("Equity (x start)"); ax[0].legend(); ax[0].grid(alpha=0.3)

    for tag in INSTR:
        e = _equity_from_trades(oos_trade_lists[tag])
        ax[1].plot(e.index, e.values / e.iloc[0], label=f"{tag} OOS (walk-forward)")
    ax[1].plot(port_oos.index, port_oos.values / port_oos.iloc[0], "k", lw=2, label="Portfolio OOS")
    ax[1].set_title("Out-of-sample (walk-forward) stitched equity — the honest result")
    ax[1].set_ylabel("Equity (x start)"); ax[1].legend(); ax[1].grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(RES, "equity_curves.png"), dpi=110)
    print("saved equity_curves.png")


if __name__ == "__main__":
    main()
