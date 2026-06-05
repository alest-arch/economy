# Quant Strategy — SPX / NQ (swing mean-reversion, honest validation)

Sistema cuantitativo para S&P 500 (SPX) y Nasdaq-100 (NQ) con foco en **robustez
fuera de muestra y estabilidad entre periodos**, no en rentabilidad.

👉 **Informe completo y veredicto honesto: [`ESTRATEGIA.md`](ESTRATEGIA.md)**

## TL;DR
- Único edge real: **reversión a la media swing** (señal diaria RSI(2) sobre SMA200,
  ejecución H4, solo largos). Estudio de eventos t = 5.4 (SPX) / 5.9 (NQ).
- **Pero el edge se ha degradado:** 2010-14 PF 2.19 → **2015-20 PF 1.02**. Inestable
  en el régimen reciente.
- **Todo lo intradía (ORB, momentum, MR H1): sin edge, ruinoso neto** → descartado con
  evidencia (no se fuerza intradía para inflar la muestra).
- Riesgo 1%/trade → **ruina ≈ 0%**. Walk-forward OOS: NQ PF 1.83 (9/12 ventanas), SPX
  PF 1.27 (7/12). Cartera OOS Sharpe 0.72, maxDD -3.1%.
- **Recomendación:** no desplegar a tamaño pleno; overlay de bajo riesgo + reconfirmar
  edge en vivo. Mejoras estructurales en §9 del informe.

## Estructura
```
quant/
  src/
    engine.py               # indicadores, backtester sin look-ahead, métricas, Monte Carlo, walk-forward
    strategies.py           # mean-reversion, breakout y la estrategia swing multi-timeframe
    intraday_strategies.py  # ORB y momentum intradía (descartadas, con evidencia)
    build_data.py           # M1 -> H1/H4
    run_validation.py       # backtest + walk-forward + Monte Carlo + cartera + gráficos
    run_diagnostics.py      # event study, decadencia, escalado de riesgo, rechazo intradía, benchmark
  data/                     # OHLC remuestreado (H1/H4/M15) + VIX  (reproducible)
  results/                  # CSV/JSON/PNG generados
  ESTRATEGIA.md             # informe principal
```

## Reproducir
```bash
pip install numpy pandas scipy matplotlib
cd quant/src

# Core (usa data/ H1+H4 ya incluidos en el repo):
python3 run_validation.py

# Diagnósticos intradía: requieren los bares M5/M15 (no versionados por tamaño).
# Regenerarlos desde la fuente cruda:
git clone --depth 1 https://github.com/FutureSharks/financial-data /tmp/fsdata
python3 build_data.py        # crea data/{SPX,NQ}_{M5,M15,H1,H4}.csv
python3 run_diagnostics.py
```

## Datos
OANDA SPX500_USD / NAS100_USD a 1 minuto (2005-2020), remuestreado. Fuente original:
[FutureSharks/financial-data]. VIX diario: [datasets/finance-vix]. Precios de bróker
retail (transables), no el print oficial del índice.

> Aviso: material de investigación cuantitativa. No es asesoramiento financiero. Los
> resultados pasados no garantizan resultados futuros; ver limitaciones en §10.
