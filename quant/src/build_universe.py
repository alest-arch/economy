"""
build_universe.py
-----------------
Resample the full OANDA minute universe (25 cross-asset instruments, 2005-2020)
to DAILY OHLC for a diversified trend-following portfolio. Saves data/universe/*.csv.
"""
import glob, os
import pandas as pd

RAW = "/tmp/fsdata/pyfinancialdata/data/currencies/oanda"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "universe")
AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}

# asset-class tagging (for diversification / correlation reporting)
CLASS = {
    "AU200_AUD": "equity", "FR40_EUR": "equity", "JP225_USD": "equity", "NAS100_USD": "equity",
    "NL25_EUR": "equity", "SPX500_USD": "equity", "UK100_GBP": "equity", "US2000_USD": "equity",
    "DE10YB_EUR": "bond", "UK10YB_GBP": "bond", "USB02Y_USD": "bond", "USB10Y_USD": "bond",
    "CORN_USD": "commodity", "NATGAS_USD": "commodity", "SOYBN_USD": "commodity",
    "SUGAR_USD": "commodity", "WHEAT_USD": "commodity", "WTICO_USD": "commodity", "XAU_USD": "commodity",
    "AUD_JPY": "fx", "AUD_USD": "fx", "EUR_JPY": "fx", "EUR_USD": "fx", "GBP_USD": "fx", "USD_CAD": "fx",
}


def main():
    os.makedirs(OUT, exist_ok=True)
    insts = sorted([d for d in os.listdir(RAW) if os.path.isdir(f"{RAW}/{d}")])
    for inst in insts:
        files = sorted(glob.glob(f"{RAW}/{inst}/*/*.csv"))
        fr = [pd.read_csv(f, usecols=["time", "open", "high", "low", "close", "volume"]) for f in files]
        df = pd.concat(fr, ignore_index=True)
        df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
        df = df.dropna(subset=["time"]).set_index("time").sort_index()
        df = df[~df.index.duplicated(keep="last")]
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["open", "high", "low", "close"])
        df = df[~((df.high < df.low) | (df.low <= 0))]
        d = df.resample("1D").agg(AGG).dropna(subset=["open"])
        d = d[d.volume > 0]
        d.to_csv(f"{OUT}/{inst}.csv", float_format="%.5f")
        print(f"{inst:14s} {CLASS.get(inst,'?'):9s} daily={len(d):5d}  {d.index.min().date()}..{d.index.max().date()}")


if __name__ == "__main__":
    main()
