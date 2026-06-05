"""
oos_regime.py
-------------
Characterise the 2021-2026 out-of-sample regime from the only recent data
obtainable inside the sandbox network policy (GitHub-hosted): CBOE VIX daily and
Shiller S&P 500 monthly. Produces results/oos_2021_2026_regime.png and
results/oos_2021_2026_regime.csv.

NOTE: this is a REGIME characterisation, not a daily backtest -- daily SPX/NQ OHLC
for 2021-2026 was not reachable (Yahoo/Stooq/FRED/histdata/CDNs are blocked).
See OOS_2021_2026.md for the honest interpretation.
"""
import os
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
RES = os.path.join(os.path.dirname(__file__), "..", "results")


def main():
    sp = pd.read_csv(os.path.join(DATA, "SP500_monthly.csv"), parse_dates=["Date"])[["Date", "SP500"]].dropna().set_index("Date")
    sp = sp[sp.index >= "2019-01-01"].copy()
    sp["ma10"] = sp["SP500"].rolling(10).mean()
    vix = pd.read_csv(os.path.join(DATA, "VIX.csv"), parse_dates=["DATE"]).set_index("DATE")["CLOSE"]
    vix = vix[vix.index >= "2021-01-01"]
    spw = sp[sp.index >= "2021-01-01"]

    # regime table
    rows = []
    spm = spw["SP500"]
    for y, g in spm.groupby(spm.index.year):
        gv = vix[vix.index.year == y]
        rows.append({"year": y, "sp_return_%": round((g.iloc[-1] / g.iloc[0] - 1) * 100, 1),
                     "sp_maxDD_monthly_%": round((g / g.cummax() - 1).min() * 100, 1),
                     "vix_avg": round(gv.mean(), 1) if len(gv) else None,
                     "vix_max": round(gv.max(), 1) if len(gv) else None,
                     "pct_days_vix_gt25": round((gv > 25).mean() * 100, 0) if len(gv) else None})
    pd.DataFrame(rows).to_csv(os.path.join(RES, "oos_2021_2026_regime.csv"), index=False)

    fig, ax = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    ax[0].plot(spw.index, spw["SP500"], color="black", lw=1.8, label="S&P 500 (mensual)")
    ax[0].plot(spw.index, spw["ma10"], color="tab:blue", lw=1.2, ls="--", label="SMA 10m (~filtro SMA200)")
    shades = [("2021-01-01", "2021-12-31", "tab:green", 0.08), ("2022-01-01", "2022-12-31", "tab:red", 0.12),
              ("2023-01-01", "2024-12-31", "tab:green", 0.08), ("2025-01-01", "2026-06-01", "tab:olive", 0.08)]
    for a, b, c, al in shades:
        for axi in ax:
            axi.axvspan(pd.Timestamp(a), pd.Timestamp(b), color=c, alpha=al)
    ax[0].set_title("S&P 500 y régimen 2021-2026 (OOS posterior a los datos del backtest)")
    ax[0].legend(loc="upper left"); ax[0].grid(alpha=.3); ax[0].set_ylabel("Índice")
    ax[1].plot(vix.index, vix.values, color="tab:purple", lw=0.9, label="VIX (diario)")
    ax[1].axhline(25, color="red", ls=":", lw=1, label="VIX=25 (umbral alta-vol)")
    ax[1].set_ylabel("VIX"); ax[1].legend(loc="upper right"); ax[1].grid(alpha=.3)
    plt.tight_layout(); plt.savefig(os.path.join(RES, "oos_2021_2026_regime.png"), dpi=110)
    print("saved oos_2021_2026_regime.png and .csv")


if __name__ == "__main__":
    main()
