"""
killzones.py
------------
Numerical "killzone" intraday test (ICT-style time windows), 2005-2020, M5 OANDA data
for SPX500 and NAS100 (the only intraday data available; the 2026 uploads are daily).

A killzone = a fixed time-of-day window in US/Eastern (DST-aware). For each day/killzone:
  opening range (OR) = high/low of the first `or_min` minutes of the window.
  BREAKOUT : price closes beyond OR -> trade in that direction.
  REVERSION: price breaks OR then closes back inside (liquidity sweep) -> fade it.
  Stop = opposite OR side; target = rr*stop; force-flat at the window end (no overnight).

Reports GROSS (zero cost) and NET edge -> shows whether killzones carry a real edge.
"""
import os, sys
import numpy as np
import pandas as pd
from engine import backtest, trade_metrics, Costs, Signals, atr

D = os.path.join(os.path.dirname(__file__), "..", "data")
# killzones in ET (start_hour, start_min, end_hour, end_min)
KZ = {
    "London":  (2, 0, 5, 0),
    "NY_AM":   (7, 0, 11, 0),
    "NY_PM":   (12, 0, 15, 0),
    "LDN_close": (10, 0, 12, 0),
}
COSTS = {"SPX": Costs(0.25, 0.20, 0.40), "NQ": Costs(1.00, 0.75, 1.50)}


def load_m5(tag):
    df = pd.read_csv(f"{D}/{tag}_M5.csv", parse_dates=[0], index_col=0)
    return df


def build_kz(df, kz, or_min=30, rr=2.0, mode="breakout", min_stop_atr=0.05, atr_n=14):
    et = df.index.tz_convert("America/New_York")
    mins = pd.Series(et.hour * 60 + et.minute, index=df.index)
    sh, sm, eh, em = KZ[kz]
    win_start, win_end = sh * 60 + sm, eh * 60 + em
    in_win = (mins >= win_start) & (mins < win_end)
    from_start = mins - win_start
    sess = pd.Series(et.date, index=df.index)
    a = atr(df, atr_n)

    in_or = in_win & (from_start < or_min)
    or_hi = df["high"].where(in_or).groupby(sess.values).transform("max")
    or_lo = df["low"].where(in_or).groupby(sess.values).transform("min")
    ready = in_win & (from_start >= or_min)
    c = df["close"]

    if mode == "breakout":
        long_e = ready & (c > or_hi)
        short_e = ready & (c < or_lo)
        sl = (c - or_lo); ss = (or_hi - c)
    else:  # reversion: broke out then closed back inside the OR
        broke_hi = (df["high"] > or_hi)
        broke_lo = (df["low"] < or_lo)
        long_e = ready & broke_lo & (c > or_lo)      # swept lows, reclaimed -> long
        short_e = ready & broke_hi & (c < or_hi)     # swept highs, rejected -> short
        sl = (c - or_lo) + 0.5 * (or_hi - or_lo)
        ss = (or_hi - c) + 0.5 * (or_hi - or_lo)

    long_e = long_e & (sl > min_stop_atr * a)
    short_e = short_e & (ss > min_stop_atr * a)
    stop = pd.Series(np.where(long_e, sl, np.where(short_e, ss, np.nan)), index=df.index)
    tgt = rr * stop
    last = in_win & (~in_win.shift(-1, fill_value=False))
    f = pd.Series(False, index=df.index)
    return Signals(long_e.fillna(False), short_e.fillna(False), stop, tgt, f, f, max_hold=0,
                   force_flat=last.fillna(False))


def main():
    ZERO = Costs(0, 0, 0)
    print(f"{'instr':5s} {'killzone':9s} {'mode':9s} {'N':>6} {'grossE[R]':>10} {'grossPF':>8} {'netE[R]':>9} {'netPF':>7} {'netWin%':>8}")
    rows = []
    for tag in ["SPX", "NQ"]:
        df = load_m5(tag)
        for kz in KZ:
            for mode in ["breakout", "reversion"]:
                sig = build_kz(df, kz, or_min=30, rr=2.0, mode=mode)
                g = trade_metrics(backtest(df, sig, ZERO))
                n = trade_metrics(backtest(df, sig, COSTS[tag]))
                if g.get("trades", 0) < 30:
                    continue
                print(f"{tag:5s} {kz:9s} {mode:9s} {g['trades']:6d} {g['expectancy_R']:+10.4f} {g['profit_factor']:8.2f} "
                      f"{n['expectancy_R']:+9.4f} {n['profit_factor']:7.2f} {n['winrate']*100:7.1f}%")
                rows.append({"instr": tag, "killzone": kz, "mode": mode, "trades": g["trades"],
                             "gross_E_R": round(g["expectancy_R"], 4), "gross_PF": round(g["profit_factor"], 3),
                             "net_E_R": round(n["expectancy_R"], 4), "net_PF": round(n["profit_factor"], 3),
                             "net_win_%": round(n["winrate"] * 100, 1)})
    out = pd.DataFrame(rows)
    res = os.path.join(os.path.dirname(__file__), "..", "results")
    out.to_csv(f"{res}/killzones_results.csv", index=False)
    print(f"\nsaved results/killzones_results.csv  | total trades tested: {out['trades'].sum():,}")
    return out


if __name__ == "__main__":
    main()
