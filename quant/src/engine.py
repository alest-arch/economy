"""
engine.py
---------
Reusable quant research library:
  - indicators (RSI/ATR/SMA/EMA/Donchian/Bollinger/realized-vol)
  - an event-driven, no-look-ahead backtester with realistic costs (R-multiple accounting)
  - performance metrics (winrate, expectancy, profit factor, max DD, Sharpe, ...)
  - Monte Carlo (trade reshuffle + bootstrap) with risk-of-ruin
  - walk-forward (rolling in-sample/out-of-sample) harness

Design choices that matter for *honesty*:
  * Signals are computed on a CLOSED bar t and executed at the OPEN of bar t+1.
  * Stops/targets are evaluated intrabar with a PESSIMISTIC tie-break: if a bar's
    range touches both the stop and the target, we assume the STOP filled first.
  * Opening gaps through the stop fill at the (worse) open price, plus slippage.
  * Costs (half-spread + slippage) are applied to every entry and exit fill; stop
    exits get extra slippage. Costs are charged in price points so they scale with
    the position size implied by the stop distance (tight stop -> more cost in R).
  * Position size = (risk_fraction * equity) / stop_distance  ->  every trade risks
    a fixed % of *current* equity (no martingale, no averaging down, no pyramiding).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field


# --------------------------------------------------------------------------- #
#  Indicators
# --------------------------------------------------------------------------- #
def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int) -> pd.Series:
    """Wilder's RSI."""
    delta = close.diff()
    up = delta.clip(lower=0.0)
    down = (-delta).clip(lower=0.0)
    roll_up = up.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    roll_down = down.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    rs = roll_up / roll_down.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.fillna(50.0)


def atr(df: pd.DataFrame, n: int) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def donchian(df: pd.DataFrame, n: int):
    hi = df["high"].rolling(n, min_periods=n).max()
    lo = df["low"].rolling(n, min_periods=n).min()
    return hi, lo


def realized_vol(close: pd.Series, n: int) -> pd.Series:
    """Annualised-ish rolling std of log returns (used only for regime ranking)."""
    r = np.log(close / close.shift(1))
    return r.rolling(n, min_periods=n).std()


# --------------------------------------------------------------------------- #
#  Cost model (per instrument), expressed in PRICE POINTS
# --------------------------------------------------------------------------- #
@dataclass
class Costs:
    half_spread_pts: float       # half the bid/ask spread, charged each side
    slip_pts: float              # generic slippage each side (limit/market)
    stop_extra_slip_pts: float   # additional slippage when a protective stop fires

    def entry_cost(self) -> float:
        return self.half_spread_pts + self.slip_pts

    def exit_cost(self, is_stop: bool) -> float:
        return self.half_spread_pts + self.slip_pts + (self.stop_extra_slip_pts if is_stop else 0.0)


# Realistic OANDA-style index CFD costs (conservative).  See report for justification.
DEFAULT_COSTS = {
    "SPX": Costs(half_spread_pts=0.25, slip_pts=0.20, stop_extra_slip_pts=0.40),
    "NQ":  Costs(half_spread_pts=1.00, slip_pts=0.75, stop_extra_slip_pts=1.50),
}


# --------------------------------------------------------------------------- #
#  Signal container produced by a strategy
# --------------------------------------------------------------------------- #
@dataclass
class Signals:
    """All series are aligned to the bar index. Decisions use bar t, fill at t+1 open."""
    long_entry: pd.Series          # bool: open a long
    short_entry: pd.Series         # bool: open a short
    stop_dist: pd.Series           # float: stop distance in points at entry (>0)
    target_dist: pd.Series         # float: target distance in points (>0) or NaN -> no fixed TP
    exit_long: pd.Series           # bool: discretionary exit for an open long (signal-based, next open)
    exit_short: pd.Series          # bool: discretionary exit for an open short
    max_hold: int = 0              # time stop in bars (0 = disabled)
    force_flat: pd.Series = None   # bool: hard EOD exit at THIS bar's close (intraday systems)


@dataclass
class Trade:
    side: int                      # +1 long, -1 short
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry: float
    exit: float
    stop: float
    qty: float
    pnl: float                     # currency
    r: float                       # R-multiple (pnl / intended risk)
    bars_held: int
    reason: str                    # 'stop' | 'target' | 'signal' | 'time' | 'eod'
    equity_after: float


# --------------------------------------------------------------------------- #
#  Event-driven backtester
# --------------------------------------------------------------------------- #
def backtest(df: pd.DataFrame, sig: Signals, costs: Costs,
             start_equity: float = 100_000.0, risk_frac: float = 0.01,
             allow_short: bool = True) -> dict:
    """
    Single-instrument, single-position-at-a-time backtest.
    Returns dict with trades (list[Trade]), equity curve (Series) and the R-stream.
    """
    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    idx = df.index

    le = sig.long_entry.to_numpy()
    se = sig.short_entry.to_numpy()
    sd = sig.stop_dist.to_numpy()
    td = sig.target_dist.to_numpy()
    xl = sig.exit_long.to_numpy()
    xs = sig.exit_short.to_numpy()
    ff = (sig.force_flat.to_numpy() if sig.force_flat is not None
          else np.zeros(len(df), dtype=bool))
    max_hold = sig.max_hold

    n = len(df)
    equity = start_equity
    trades: list[Trade] = []
    eq_times = [idx[0]]
    eq_vals = [equity]

    pos = 0            # 0 flat, +1 long, -1 short
    entry_px = stop_px = target_px = np.nan
    qty = 0.0
    entry_i = -1
    intended_risk = 0.0

    i = 1
    while i < n:
        if pos == 0:
            # ---- look for an entry decided on bar i-1, executed at open of bar i ----
            take_long = le[i - 1] and (sd[i - 1] > 0)
            take_short = allow_short and se[i - 1] and (sd[i - 1] > 0)
            if take_long or take_short:
                side = 1 if take_long else -1
                raw_open = o[i]
                ec = costs.entry_cost()
                entry_px = raw_open + side * ec          # pay the spread/slippage
                stop_dist = sd[i - 1]
                stop_px = entry_px - side * stop_dist
                tdist = td[i - 1]
                target_px = entry_px + side * tdist if np.isfinite(tdist) and tdist > 0 else np.nan
                intended_risk = risk_frac * equity
                qty = intended_risk / stop_dist           # 1 pt = 1 currency unit per qty
                pos = side
                entry_i = i
                # NOTE: management of bar i happens below (same bar can stop out)
            else:
                i += 1
                continue

        # ---- manage an open position on bar i ----
        side = pos
        first_bar = (i == entry_i)
        ec_exit = None
        exit_px = np.nan
        reason = None

        # 1) opening-gap check (skip on the very first bar -> we entered at its open)
        if not first_bar:
            if side == 1:
                if o[i] <= stop_px:
                    exit_px, reason = o[i] - costs.exit_cost(True), "stop"      # gap fill at open
                elif np.isfinite(target_px) and o[i] >= target_px:
                    exit_px, reason = o[i] - costs.exit_cost(False), "target"
            else:
                if o[i] >= stop_px:
                    exit_px, reason = o[i] + costs.exit_cost(True), "stop"
                elif np.isfinite(target_px) and o[i] <= target_px:
                    exit_px, reason = o[i] + costs.exit_cost(False), "target"

        # 2) intrabar stop/target (pessimistic: stop checked before target)
        if reason is None:
            if side == 1:
                hit_stop = l[i] <= stop_px
                hit_tgt = np.isfinite(target_px) and h[i] >= target_px
                if hit_stop:
                    exit_px, reason = stop_px - costs.exit_cost(True), "stop"
                elif hit_tgt:
                    exit_px, reason = target_px - costs.exit_cost(False), "target"
            else:
                hit_stop = h[i] >= stop_px
                hit_tgt = np.isfinite(target_px) and l[i] <= target_px
                if hit_stop:
                    exit_px, reason = stop_px + costs.exit_cost(True), "stop"
                elif hit_tgt:
                    exit_px, reason = target_px + costs.exit_cost(False), "target"

        # 2.5) hard end-of-day flat -> exit at THIS bar's close (no overnight risk)
        if reason is None and ff[i]:
            exit_px = c[i] - side * costs.exit_cost(False)
            reason = "eod"

        # 3) signal / time stop -> evaluated on bar i's close, executed next open (i+1)
        if reason is None:
            want_exit = (xl[i] if side == 1 else xs[i])
            timed_out = (max_hold > 0 and (i - entry_i) >= max_hold)
            if want_exit or timed_out:
                if i + 1 < n:
                    nxt = o[i + 1]
                    exit_px = nxt - side * costs.exit_cost(False)
                    reason = "signal" if want_exit else "time"
                    # advance close happens at i+1; account below then jump
                    pnl = side * (exit_px - entry_px) * qty
                    equity += pnl
                    r = pnl / intended_risk if intended_risk else 0.0
                    trades.append(Trade(side, idx[entry_i], idx[i + 1], entry_px, exit_px,
                                        stop_px, qty, pnl, r, i + 1 - entry_i, reason, equity))
                    eq_times.append(idx[i + 1]); eq_vals.append(equity)
                    pos = 0
                    i += 2
                    continue
                else:
                    # no next bar -> close at last close (end of data)
                    exit_px = c[i] - side * costs.exit_cost(False)
                    reason = "eod"

        # finalize stop/target/eod exits that happened on bar i
        if reason is not None:
            pnl = side * (exit_px - entry_px) * qty
            equity += pnl
            r = pnl / intended_risk if intended_risk else 0.0
            trades.append(Trade(side, idx[entry_i], idx[i], entry_px, exit_px,
                                stop_px, qty, pnl, r, i - entry_i, reason, equity))
            eq_times.append(idx[i]); eq_vals.append(equity)
            pos = 0
            i += 1
            continue

        i += 1

    equity_curve = pd.Series(eq_vals, index=pd.DatetimeIndex(eq_times))
    r_stream = np.array([t.r for t in trades], dtype=float)
    return {"trades": trades, "equity": equity_curve, "r": r_stream,
            "start_equity": start_equity}


# --------------------------------------------------------------------------- #
#  Performance metrics
# --------------------------------------------------------------------------- #
def trade_metrics(res: dict, bars_per_year: float = 0.0) -> dict:
    trades = res["trades"]
    r = res["r"]
    eq = res["equity"]
    n = len(trades)
    if n == 0:
        return {"trades": 0}
    wins = r[r > 0]
    losses = r[r <= 0]
    winrate = len(wins) / n
    avg_win = wins.mean() if len(wins) else 0.0
    avg_loss = losses.mean() if len(losses) else 0.0           # negative
    expectancy_R = r.mean()
    gross_win = wins.sum()
    gross_loss = -losses.sum()
    profit_factor = gross_win / gross_loss if gross_loss > 0 else np.inf

    # equity-based stats
    start = res["start_equity"]
    final = eq.iloc[-1]
    total_ret = final / start - 1.0
    roll_max = eq.cummax()
    dd = eq / roll_max - 1.0
    max_dd = dd.min()

    # per-trade Sharpe (on R stream) and annualised approximation
    r_std = r.std(ddof=1) if n > 1 else np.nan
    sharpe_per_trade = expectancy_R / r_std if r_std and r_std > 0 else np.nan
    # annualise by trade frequency
    span_years = (eq.index[-1] - eq.index[0]).days / 365.25 if len(eq) > 1 else np.nan
    trades_per_year = n / span_years if span_years and span_years > 0 else np.nan
    sharpe_ann = sharpe_per_trade * np.sqrt(trades_per_year) if np.isfinite(sharpe_per_trade) and np.isfinite(trades_per_year) else np.nan

    # CAGR
    cagr = (final / start) ** (1.0 / span_years) - 1.0 if span_years and span_years > 0 and final > 0 else np.nan

    # max consecutive losses
    mcl = cur = 0
    for x in r:
        if x <= 0:
            cur += 1; mcl = max(mcl, cur)
        else:
            cur = 0

    return {
        "trades": n,
        "winrate": winrate,
        "avg_win_R": avg_win,
        "avg_loss_R": avg_loss,
        "expectancy_R": expectancy_R,
        "profit_factor": profit_factor,
        "total_return": total_ret,
        "cagr": cagr,
        "max_drawdown": max_dd,
        "sharpe_per_trade": sharpe_per_trade,
        "sharpe_annual": sharpe_ann,
        "trades_per_year": trades_per_year,
        "max_consec_losses": mcl,
        "final_equity": final,
        "span_years": span_years,
        "exposure_long": np.mean([t.side == 1 for t in trades]),
    }


# --------------------------------------------------------------------------- #
#  Monte Carlo: trade reshuffle + bootstrap, with risk-of-ruin
# --------------------------------------------------------------------------- #
def monte_carlo(r_stream: np.ndarray, n_sims: int = 5000, risk_frac: float = 0.01,
                ruin_dd: float = 0.30, block: int = 1, seed: int = 7) -> dict:
    """
    Compound an equity curve from per-trade R-multiples under random orderings.

    - reshuffle: permute the realised trades (tests path/sequence dependence).
    - bootstrap (block>1): resample blocks with replacement (tests if the *sample*
      of trades was lucky; injects unseen sequences / streaks).
    - 'ruin' = the equity ever falls >= ruin_dd below its running peak.
    Each R is converted to a return of (risk_frac * R) applied multiplicatively.
    """
    rng = np.random.default_rng(seed)
    n = len(r_stream)
    if n == 0:
        return {}
    finals, dd_mag, ruined = np.empty(n_sims), np.empty(n_sims), 0  # dd_mag stored as POSITIVE magnitude

    for s in range(n_sims):
        if block <= 1:
            seq = rng.permutation(r_stream)
        else:
            nb = int(np.ceil(n / block))
            starts = rng.integers(0, n, size=nb)
            seq = np.concatenate([np.take(r_stream, range(st, st + block), mode="wrap") for st in starts])[:n]
        rets = risk_frac * seq
        equity = np.cumprod(1.0 + rets)
        peak = np.maximum.accumulate(equity)
        dd = equity / peak - 1.0
        finals[s] = equity[-1]
        mdd = dd.min()
        dd_mag[s] = -mdd
        if mdd <= -ruin_dd:
            ruined += 1

    return {
        "n_sims": n_sims,
        "risk_of_ruin": ruined / n_sims,         # P(peak-to-trough drawdown >= ruin_dd)
        "ruin_dd": ruin_dd,
        "final_mult_p05": float(np.percentile(finals, 5)),
        "final_mult_p50": float(np.percentile(finals, 50)),
        "final_mult_p95": float(np.percentile(finals, 95)),
        # drawdown magnitudes (positive): p50 typical, p95/p99 the adverse tail
        "maxdd_p50": float(-np.percentile(dd_mag, 50)),
        "maxdd_p95": float(-np.percentile(dd_mag, 95)),
        "maxdd_p99": float(-np.percentile(dd_mag, 99)),
        "prob_loss": float(np.mean(finals < 1.0)),
    }


# --------------------------------------------------------------------------- #
#  Walk-forward harness
# --------------------------------------------------------------------------- #
def walk_forward(df: pd.DataFrame, build_signals, param_grid: list[dict], costs: Costs,
                 is_years: float = 3.0, oos_years: float = 1.0,
                 score_key: str = "expectancy_R", min_trades: int = 20,
                 allow_short: bool = True, risk_frac: float = 0.01) -> dict:
    """
    Rolling walk-forward:
      - split the sample into [IS window][OOS window], step forward by oos_years.
      - on each IS window, pick the param set that maximises `score_key` (with a
        minimum-trade guard) -> NO peeking at OOS.
      - run that param set on the following OOS window; stitch the OOS trades.
    Returns the concatenated OOS trade stream + per-fold record.
    """
    idx = df.index
    t0, t1 = idx[0], idx[-1]
    is_td = pd.Timedelta(days=int(is_years * 365.25))
    oos_td = pd.Timedelta(days=int(oos_years * 365.25))

    folds = []
    oos_r = []
    oos_trades = []
    is_start = t0
    while True:
        is_end = is_start + is_td
        oos_end = is_end + oos_td
        if is_end >= t1:
            break
        oos_end = min(oos_end, t1)
        is_df = df.loc[is_start:is_end]
        oos_df = df.loc[is_end:oos_end]
        if len(oos_df) < 50:
            break

        # ---- choose best params on IS ----
        best = None
        for p in param_grid:
            sig = build_signals(is_df, **p)
            res = backtest(is_df, sig, costs, risk_frac=risk_frac, allow_short=allow_short)
            m = trade_metrics(res)
            if m.get("trades", 0) < min_trades:
                continue
            score = m.get(score_key, -np.inf)
            # tie-break toward higher profit factor then more trades
            key = (score, m.get("profit_factor", 0), m.get("trades", 0))
            if best is None or key > best[0]:
                best = (key, p, m)

        if best is None:
            is_start = is_start + oos_td
            continue

        _, best_p, is_m = best
        # ---- evaluate on OOS with chosen params ----
        sig = build_signals(oos_df, **best_p)
        res = backtest(oos_df, sig, costs, risk_frac=risk_frac, allow_short=allow_short)
        m = trade_metrics(res)
        folds.append({
            "is_start": str(is_start.date()), "is_end": str(is_end.date()),
            "oos_end": str(oos_end.date()), "params": best_p,
            "is_expectancy_R": is_m.get("expectancy_R"), "is_trades": is_m.get("trades"),
            "oos_expectancy_R": m.get("expectancy_R"), "oos_trades": m.get("trades"),
            "oos_winrate": m.get("winrate"), "oos_pf": m.get("profit_factor"),
        })
        oos_r.append(res["r"])
        oos_trades.extend(res["trades"])
        is_start = is_start + oos_td

    oos_r = np.concatenate(oos_r) if oos_r else np.array([])
    return {"folds": folds, "oos_r": oos_r, "oos_trades": oos_trades}
