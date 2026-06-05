"""
intraday_strategies.py
----------------------
High-frequency intraday archetypes (no overnight risk: every trade is force-flat
at the cash close). Sessions use DST-aware US/Eastern time.

  orb      : Opening Range Breakout. Trade the break of the first `or_min` minutes
             of the US cash session, stop at the opposite side of the range, exit at
             a fixed R multiple or at the close. The best-documented intraday index edge.
  intraday_momentum : the sign of the first hour of the session predicts the rest of
             the day (Gao, Han, Li, Zhou 2018). Enter at the end of hour 1, exit EOD.

These produce thousands of trades -> a statistically large sample. Whether they
carry a *net* edge after costs is exactly what the validation must decide.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from engine import Signals, atr

RTH_OPEN = (9, 30)     # 09:30 ET
RTH_CLOSE = (16, 0)    # 16:00 ET


def _et(df: pd.DataFrame) -> pd.DatetimeIndex:
    return df.index.tz_convert("America/New_York")


def _rth_frame(df: pd.DataFrame):
    """Return ET-local helper columns: minutes-from-open, RTH mask, session date."""
    et = _et(df)
    mins = et.hour * 60 + et.minute
    open_m = RTH_OPEN[0] * 60 + RTH_OPEN[1]
    close_m = RTH_CLOSE[0] * 60 + RTH_CLOSE[1]
    rth = (mins >= open_m) & (mins < close_m)
    from_open = mins - open_m
    sess_date = pd.Series(et.date, index=df.index)
    return pd.Series(rth, index=df.index), pd.Series(from_open, index=df.index), sess_date


def build_signals_orb(df: pd.DataFrame, or_min: int = 30, rr: float | None = 2.0,
                      atr_n: int = 14, min_stop_atr: float = 0.10,
                      last_entry_min: int = 360, shorts: bool = True,
                      trend_filter: bool = False, trend_n: int = 50) -> Signals:
    """
    or_min        : length of the opening range in minutes (e.g. 15/30/60).
    rr            : take-profit at rr * risk; None -> rely on EOD exit only.
    min_stop_atr  : skip trades whose stop (the OR range) is < this * ATR (avoids
                    degenerate tiny-range stops that costs would dominate).
    last_entry_min: no new entries after this many minutes from the open.
    """
    rth, from_open, sess = _rth_frame(df)
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    a = atr(df, atr_n)

    # opening range = high/low of bars within [0, or_min) from the open, per session
    in_or = rth & (from_open < or_min)
    g = df.assign(_s=sess.values)
    or_hi = h.where(in_or).groupby(sess.values).transform("max")
    or_lo = l.where(in_or).groupby(sess.values).transform("min")
    # only known AFTER the OR window closes
    or_ready = rth & (from_open >= or_min) & (from_open < last_entry_min)

    stop_long = (c - or_lo)
    stop_short = (or_hi - c)

    trend = c.rolling(trend_n, min_periods=trend_n).mean() if trend_filter else None
    tl = (c > trend) if trend_filter else pd.Series(True, index=df.index)
    ts = (c < trend) if trend_filter else pd.Series(True, index=df.index)

    long_entry = or_ready & (c > or_hi) & (stop_long > min_stop_atr * a) & tl
    short_entry = (or_ready & (c < or_lo) & (stop_short > min_stop_atr * a) & ts) if shorts \
        else pd.Series(False, index=df.index)

    # stop distance: distance to the opposite side of the opening range
    stop_dist = pd.Series(np.where(long_entry, stop_long, np.where(short_entry, stop_short, np.nan)),
                          index=df.index)
    target_dist = (rr * stop_dist) if rr else pd.Series(np.nan, index=df.index)

    # force flat at the last RTH bar of each day
    last_bar = rth & (~rth.shift(-1, fill_value=False))
    false = pd.Series(False, index=df.index)
    return Signals(long_entry=long_entry.fillna(False), short_entry=short_entry.fillna(False),
                   stop_dist=stop_dist, target_dist=target_dist,
                   exit_long=false, exit_short=false, max_hold=0,
                   force_flat=last_bar.fillna(False))


def build_signals_intraday_mom(df: pd.DataFrame, signal_min: int = 60,
                               stop_atr: float = 1.5, atr_n: int = 14,
                               shorts: bool = True) -> Signals:
    """Enter at the end of the first `signal_min` minutes in the direction of that
    move; exit at the close. Stop is ATR-based (disaster stop)."""
    rth, from_open, sess = _rth_frame(df)
    c = df["close"]
    a = atr(df, atr_n)

    open_px = c.where(rth & (from_open == from_open[rth].min())).groupby(sess.values).transform("first")
    # session open = first RTH close; first-hour return measured at the signal bar
    sess_open = df["open"].where(rth).groupby(sess.values).transform("first")
    sig_bar = rth & (from_open >= signal_min) & (from_open < signal_min + 30)
    # take the FIRST bar at/after signal_min as the entry trigger
    first_sig = sig_bar & (~sig_bar.groupby(sess.values).cumsum().gt(1))
    hour_ret = c - sess_open

    long_entry = first_sig & (hour_ret > 0)
    short_entry = (first_sig & (hour_ret < 0)) if shorts else pd.Series(False, index=df.index)
    stop_dist = stop_atr * a
    target_dist = pd.Series(np.nan, index=df.index)

    last_bar = rth & (~rth.shift(-1, fill_value=False))
    false = pd.Series(False, index=df.index)
    return Signals(long_entry=long_entry.fillna(False), short_entry=short_entry.fillna(False),
                   stop_dist=stop_dist, target_dist=target_dist,
                   exit_long=false, exit_short=false, max_hold=0,
                   force_flat=last_bar.fillna(False))
