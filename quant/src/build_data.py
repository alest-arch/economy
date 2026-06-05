"""
build_data.py
-------------
Consolidate raw OANDA 1-minute index data (SPX500_USD, NAS100_USD) into clean,
resampled OHLC bars (H1 and H4) in UTC, and persist compact CSVs for a fully
reproducible backtest.

Raw source: FutureSharks/financial-data (OANDA broker feed, 2005-2020).
Each raw file: time,close,high,low,open,volume  (volume = tick count).
Timestamps are UTC (verified: daily maintenance gap at ~21:00-22:00 UTC = 17:00 ET).

Why OANDA CFD prices and not the cash index (^GSPC/^NDX)?
  - They are the prices a *retail* trader could actually transact on, nearly 24h.
  - They already embed the broker's quoted mid -> spreads/slippage modelled on top
    are realistic rather than fantasy "fill at the official index print".

Resampling convention: closed='left', label='left'
  -> the H1 bar stamped 14:00 aggregates [14:00, 15:00). Signals are evaluated on
     a *closed* bar and acted on at the next bar's open (handled in the backtester),
     so there is no look-ahead.
"""
import glob
import os
import sys
import pandas as pd

RAW = "/tmp/fsdata/pyfinancialdata/data/currencies/oanda"
OUT = os.path.join(os.path.dirname(__file__), "..", "data")
INSTRUMENTS = {"SPX500_USD": "SPX", "NAS100_USD": "NQ"}
TIMEFRAMES = {"M5": "5min", "M15": "15min", "H1": "1h", "H4": "4h"}


def load_minute(instrument: str) -> pd.DataFrame:
    files = sorted(glob.glob(os.path.join(RAW, instrument, "*", "*.csv")))
    if not files:
        raise FileNotFoundError(f"No raw files for {instrument} under {RAW}")
    frames = []
    for f in files:
        d = pd.read_csv(f, usecols=["time", "open", "high", "low", "close", "volume"])
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.dropna(subset=["time"]).set_index("time").sort_index()
    # de-duplicate identical timestamps (keep last) and enforce numeric
    df = df[~df.index.duplicated(keep="last")]
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    # sanity: high>=max(open,close)>=...>=low ; drop pathological bars
    bad = (df["high"] < df["low"]) | (df["high"] <= 0) | (df["low"] <= 0)
    df = df[~bad]
    return df


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    out = df.resample(rule, closed="left", label="left").agg(agg)
    # drop empty periods (weekends, maintenance break) -> no trades possible there
    out = out.dropna(subset=["open", "high", "low", "close"])
    out = out[out["volume"] > 0]
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    summary = []
    for inst, tag in INSTRUMENTS.items():
        print(f"[{tag}] loading minute data ...", flush=True)
        m = load_minute(inst)
        print(f"[{tag}] minute rows={len(m):,}  {m.index.min()} -> {m.index.max()}", flush=True)
        for tf, rule in TIMEFRAMES.items():
            r = resample(m, rule)
            path = os.path.join(OUT, f"{tag}_{tf}.csv")
            r.to_csv(path, float_format="%.3f")
            summary.append((tag, tf, len(r), str(r.index.min()), str(r.index.max())))
            print(f"[{tag}] {tf}: {len(r):,} bars -> {os.path.relpath(path)}", flush=True)
        del m
    print("\n=== SUMMARY ===")
    for tag, tf, n, a, b in summary:
        print(f"{tag:4s} {tf:3s} bars={n:>7,}  {a}  ->  {b}")


if __name__ == "__main__":
    sys.exit(main())
