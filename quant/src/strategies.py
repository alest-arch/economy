"""
strategies.py
-------------
Signal generators. Each returns an engine.Signals object aligned to df.

Two principled archetypes for equity indices:

  meanrev  : "buy the dip in an uptrend" (Connors-style short-term mean reversion).
             Indices mean-revert intraday/short-term while drifting up long-term, so
             we only fade pullbacks *with* the higher-timeframe trend. High winrate,
             RR < 1, edge from p(win). The classic, widely-replicated index anomaly.

  breakout : volatility/Donchian breakout in the direction of the trend (trend
             following). Low winrate, RR > 1, edge from the size of the winners.

Both use:
  - an ATR-scaled stop so risk is volatility-normalised (1% sizing handles the rest),
  - a session filter (index edges concentrate in the US cash session),
  - no pyramiding / averaging.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import Signals, sma, ema, rsi, atr, donchian


def _session_mask(idx: pd.DatetimeIndex, session: str) -> pd.Series:
    """Timeframe-aware US-cash-session filter (timestamps are UTC).

    The US RTH window is ~14:00-21:00 UTC. On H1 bars that is the {14..19} stamps;
    on H4 bars (stamped 00/04/08/12/16/20) the RTH-overlapping bars are {12,16}.
    """
    h = idx.hour.to_numpy()
    is_h4 = bool(np.all((h % 4) == 0))  # H4 stamps are multiples of 4
    if session == "all":
        m = np.ones(len(idx), dtype=bool)
    elif session == "us":
        m = np.isin(h, [12, 16]) if is_h4 else ((h >= 14) & (h <= 19))
    elif session == "us_open":
        m = np.isin(h, [12]) if is_h4 else ((h >= 14) & (h <= 17))
    else:
        raise ValueError(session)
    return pd.Series(m, index=idx)


# --------------------------------------------------------------------------- #
#  Mean reversion (buy-the-dip / fade-the-rip, trend filtered)
# --------------------------------------------------------------------------- #
def build_signals_meanrev(df: pd.DataFrame, rsi_n: int = 2, os_th: float = 10.0,
                          ob_th: float = 90.0, trend_n: int = 200, exit_th: float = 55.0,
                          stop_atr: float = 3.0, atr_n: int = 14, rr: float | None = None,
                          max_hold: int = 24, session: str = "us",
                          shorts: bool = False) -> Signals:
    c = df["close"]
    r = rsi(c, rsi_n)
    a = atr(df, atr_n)
    trend = sma(c, trend_n)
    sess = _session_mask(df.index, session)

    bull = c > trend
    bear = c < trend

    long_entry = bull & (r < os_th) & sess & a.notna() & trend.notna()
    short_entry = (bear & (r > ob_th) & sess & a.notna() & trend.notna()) if shorts else pd.Series(False, index=df.index)

    # discretionary exits: momentum reverted back through the mid-line
    exit_long = r > exit_th
    exit_short = r < (100.0 - exit_th)

    stop_dist = (stop_atr * a)
    target_dist = (rr * stop_dist) if rr else pd.Series(np.nan, index=df.index)

    return Signals(long_entry=long_entry.fillna(False), short_entry=short_entry.fillna(False),
                   stop_dist=stop_dist, target_dist=target_dist,
                   exit_long=exit_long.fillna(False), exit_short=exit_short.fillna(False),
                   max_hold=max_hold)


# --------------------------------------------------------------------------- #
#  Trend / breakout (Donchian channel, trend filtered)
# --------------------------------------------------------------------------- #
def build_signals_breakout(df: pd.DataFrame, don_n: int = 20, trend_fast: int = 50,
                           trend_slow: int = 200, stop_atr: float = 2.5, atr_n: int = 14,
                           rr: float = 2.0, max_hold: int = 0, session: str = "us",
                           shorts: bool = True) -> Signals:
    c = df["close"]
    a = atr(df, atr_n)
    hi, lo = donchian(df, don_n)
    f = sma(c, trend_fast)
    s = sma(c, trend_slow)
    sess = _session_mask(df.index, session)

    up = f > s
    dn = f < s

    # breakout = close pushes through the prior N-bar extreme (shifted -> no look-ahead)
    brk_up = c > hi.shift(1)
    brk_dn = c < lo.shift(1)

    long_entry = up & brk_up & sess & a.notna() & s.notna()
    short_entry = (dn & brk_dn & sess & a.notna() & s.notna()) if shorts else pd.Series(False, index=df.index)

    stop_dist = stop_atr * a
    target_dist = rr * stop_dist

    # breakout uses stop/target only (trend exit handled by hard stop + RR target + time)
    no_exit = pd.Series(False, index=df.index)
    return Signals(long_entry=long_entry.fillna(False), short_entry=short_entry.fillna(False),
                   stop_dist=stop_dist, target_dist=target_dist,
                   exit_long=no_exit, exit_short=no_exit, max_hold=max_hold)


# --------------------------------------------------------------------------- #
#  THE STRATEGY: multi-timeframe swing mean-reversion
#  (signal on the DAILY bar -> executed/managed on the H4 bar)
# --------------------------------------------------------------------------- #
def make_daily(h1_or_h4: pd.DataFrame) -> pd.DataFrame:
    """Build a daily OHLC frame (UTC calendar day) from a finer frame."""
    d = h1_or_h4.resample("1D").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(subset=["open", "high", "low", "close"])
    return d


def build_signals_swing_mtf(df_exec: pd.DataFrame, df_daily: pd.DataFrame,
                            rsi_n: int = 2, os_th: float = 10.0, trend_n: int = 200,
                            exit_th: float = 65.0, stop_atr: float = 2.5, atr_n: int = 14,
                            max_hold_bars: int = 30, session: str = "us",
                            vix: pd.Series | None = None, vix_max: float | None = None,
                            rr: float | None = None, fast_n: int | None = None,
                            max_stretch: float | None = None,
                            max_atr_rank: float | None = None) -> Signals:
    """
    Edge source: a 2-8 day mean reversion that only exists at the swing horizon.
    Signal is computed on the DAILY bar and *lagged by one completed day* (no
    look-ahead), then mapped onto the execution timeframe (H4) where stops, the
    time stop and entries are managed at finer granularity.

    Long-only by construction: the reversion edge is reliable only on the long
    side above the 200-day trend (buying fear in a bull regime). Shorting index
    rips above-trend has no comparable statistical support (see report).
    """
    c = df_daily["close"]
    r = rsi(c, rsi_n)
    trend = sma(c, trend_n)
    a = atr(df_daily, atr_n)

    bull = c > trend
    d_entry = (bull & (r < os_th)).astype(float)
    d_exit = (r > exit_th).astype(float)

    # --- regime corrections (diagnosis-driven, NOT return-optimised) ---
    if fast_n is not None:
        # require a bull regime (fast MA > slow MA) -> drop the ~breakeven bear-regime dips
        d_entry = d_entry * (sma(c, fast_n) > trend).astype(float)
    if max_stretch is not None:
        # cede very-stretched/frothy markets to the trend sleeve (MR edge is thin there)
        a_d = atr(df_daily, atr_n)
        d_entry = d_entry * (((c - trend) / a_d) < max_stretch).astype(float)
    if max_atr_rank is not None:
        # volatility circuit-breaker: do NOT buy dips while volatility is exploding
        # (fast crashes -> dips keep dipping; this is what wrecked MR in 2020/2008)
        atr_rank = (atr(df_daily, atr_n) / c).rolling(252, min_periods=60).rank(pct=True)
        d_entry = d_entry * (atr_rank < max_atr_rank).astype(float)

    if vix is not None and vix_max is not None:
        # optional regime guard: skip dips while VIX (fear) is in a blow-off above vix_max
        vix_d = vix.reindex(c.index).ffill()
        d_entry = d_entry * (vix_d < vix_max).astype(float)

    feat = pd.DataFrame({"d_entry": d_entry, "d_exit": d_exit, "d_atr": a}, index=df_daily.index)
    feat_lag = feat.shift(1)                      # only use the prior *completed* day
    feat_lag.index = feat_lag.index.normalize()

    key = df_exec.index.normalize()
    mapped = feat_lag.reindex(key)
    mapped.index = df_exec.index

    sess = _session_mask(df_exec.index, session)
    long_entry = (mapped["d_entry"] > 0.5) & sess & mapped["d_atr"].notna()
    exit_long = (mapped["d_exit"] > 0.5)
    stop_dist = stop_atr * mapped["d_atr"]
    target_dist = (rr * stop_dist) if rr else pd.Series(np.nan, index=df_exec.index)

    false = pd.Series(False, index=df_exec.index)
    return Signals(long_entry=long_entry.fillna(False), short_entry=false,
                   stop_dist=stop_dist, target_dist=target_dist,
                   exit_long=exit_long.fillna(False), exit_short=false,
                   max_hold=max_hold_bars)


# --------------------------------------------------------------------------- #
#  TREND-FOLLOWING sleeve (Donchian breakout, long+short) — the regime diversifier
# --------------------------------------------------------------------------- #
def build_signals_trend_daily(df: pd.DataFrame, entry_n: int = 50, exit_n: int = 20,
                              trend_n: int | None = 200, stop_atr: float = 3.0, atr_n: int = 14,
                              shorts: bool = True, longs: bool = True) -> Signals:
    """
    Classic dual-Donchian trend following on the DAILY bar.
    trend_n=None disables the SMA filter (pure breakout, both directions) -> used for
    the diversified cross-asset portfolio. trend_n=200 -> only trade with the long MA.
    """
    c = df["close"]
    a = atr(df, atr_n)
    hi_e = df["high"].rolling(entry_n, min_periods=entry_n).max().shift(1)
    lo_e = df["low"].rolling(entry_n, min_periods=entry_n).min().shift(1)
    hi_x = df["high"].rolling(exit_n, min_periods=exit_n).max().shift(1)
    lo_x = df["low"].rolling(exit_n, min_periods=exit_n).min().shift(1)
    if trend_n is None:
        up_ok = pd.Series(True, index=df.index)
        dn_ok = pd.Series(True, index=df.index)
    else:
        trend = sma(c, trend_n)
        up_ok = c > trend
        dn_ok = c < trend

    long_entry = ((c > hi_e) & up_ok) if longs else pd.Series(False, index=df.index)
    short_entry = ((c < lo_e) & dn_ok) if shorts else pd.Series(False, index=df.index)

    exit_long = c < lo_x        # trailing breakdown closes the long
    exit_short = c > hi_x        # trailing breakout closes the short

    stop_dist = stop_atr * a
    target_dist = pd.Series(np.nan, index=df.index)

    return Signals(long_entry=long_entry.fillna(False), short_entry=short_entry.fillna(False),
                   stop_dist=stop_dist, target_dist=target_dist,
                   exit_long=exit_long.fillna(False), exit_short=exit_short.fillna(False),
                   max_hold=0)
