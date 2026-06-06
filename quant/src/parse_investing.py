"""
parse_investing.py
------------------
Convert Investing.com CSV exports (European number format) into clean OHLC CSVs
ready for the backtests in this repo.

Investing.com format quirks handled:
  - decimal comma + thousands dot:   "24.759,05" -> 24759.05 ;  "4,536" -> 4.536
  - dates DD.MM.YYYY, newest-first
  - volume "572,67M" / "1,2K" / "3,4B"
  - bond files are YIELDS (no volume); a synthetic constant-duration bond PRICE index
    is built (price return ~= -duration * d(yield)) so trend/MR can trade "the bond".

Usage:
  python3 parse_investing.py  <out_tag>=<path.csv> [--bond] ...
  e.g.  python3 parse_investing.py SPX=US500.csv NQ=Nasdaq.csv DAX=DAX.csv \
                                   US10Y=us10y.csv --bond  DE10Y=de10y.csv --bond

Output: data/recent/<TAG>.csv with columns date,open,high,low,close (+volume if present).

IMPORTANT: export the FULL history from Investing.com first — set the date range
(the calendar picker on the "Historical Data" tab) to e.g. 01/01/2008..today BEFORE
downloading, otherwise the file only contains ~1 month (the visible page).
"""
import os, sys
import numpy as np
import pandas as pd

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "recent")
DURATION = 8.0  # approx modified duration for a 10y note (for synthetic bond price)


def _num(x):
    if pd.isna(x) or str(x).strip() in ("", "-"):
        return np.nan
    s = str(x).strip().replace(".", "").replace(",", ".")
    return float(s)


def _vol(x):
    if pd.isna(x) or str(x).strip() == "":
        return np.nan
    s = str(x).strip().upper().replace(".", "").replace(",", ".")
    mult = 1.0
    if s.endswith("K"): mult, s = 1e3, s[:-1]
    elif s.endswith("M"): mult, s = 1e6, s[:-1]
    elif s.endswith("B"): mult, s = 1e9, s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return np.nan


def parse(path, tag, is_bond=False):
    df = pd.read_csv(path)
    df.columns = [c.strip().strip('"') for c in df.columns]
    cmap = {"Fecha": "date", "Último": "close", "Apertura": "open",
            "Máximo": "high", "Mínimo": "low", "Vol.": "volume"}
    df = df.rename(columns=cmap)
    df["date"] = pd.to_datetime(df["date"], format="%d.%m.%Y")
    for c in ["open", "high", "low", "close"]:
        df[c] = df[c].map(_num)
    if "volume" in df.columns:
        df["volume"] = df["volume"].map(_vol)
    df = df.sort_values("date").set_index("date").dropna(subset=["close"])

    if is_bond:
        # yields -> synthetic constant-duration bond total-return price index
        y = df["close"] / 100.0
        dprice = (-DURATION * y.diff()).fillna(0.0)
        px = 100.0 * (1.0 + dprice).cumprod()
        out = pd.DataFrame(index=df.index)
        out["close"] = px
        # build OHLC from intraday yield range (high yield -> low price)
        out["open"] = px / (1.0 + (-DURATION * (df["open"]/100.0 - y)))
        out["high"] = px / (1.0 + (-DURATION * (df["low"]/100.0 - y)))   # low yield -> high price
        out["low"] = px / (1.0 + (-DURATION * (df["high"]/100.0 - y)))
        out = out[["open", "high", "low", "close"]].replace([np.inf, -np.inf], np.nan).dropna()
    else:
        out = df[["open", "high", "low", "close"] + (["volume"] if "volume" in df.columns else [])]
    os.makedirs(OUT, exist_ok=True)
    out.to_csv(f"{OUT}/{tag}.csv")
    span = (out.index.max() - out.index.min()).days / 365.25
    print(f"{tag:6s} rows={len(out):5d}  {out.index.min().date()} -> {out.index.max().date()}  ({span:.1f}y){'  [bond synth price]' if is_bond else ''}")
    if len(out) < 250:
        print(f"  ⚠️  {tag}: solo {len(out)} filas (~{len(out)/21:.0f} meses). Exporta el HISTÓRICO COMPLETO de Investing.com.")
    return out


def main(args):
    is_bond = False
    specs = []
    for a in args:
        if a == "--bond":
            is_bond = True; continue
        if "=" in a:
            tag, path = a.split("=", 1)
            specs.append((tag, path, is_bond)); is_bond = False
    for tag, path, b in specs:
        parse(path, tag, b)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
    else:
        main(sys.argv[1:])
