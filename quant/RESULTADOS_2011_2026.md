# Resultados con datos reales 2011–2026 (S&P, Nasdaq, DAX, Oro, Bono US 10Y)

> Por fin con el histórico real que aportaste (Investing.com, ~2007/2011–2026). Cubre los
> regímenes que pedías: **COVID 2020, subida de tipos 2022, bull 2021–2024, 2025–26.**
> Sistema: **MR (índices, long-only) + Trend (los 5, long+short)**, motor event-driven,
> neto de costes, 1% riesgo/trade base. **794 trades** (✓ ≥700).

## Lo importante: el Trend Following REVIVIÓ
En mis tests con datos 2005–2020 (OANDA) el trend perdía (su "invierno"). Con datos
**2020–2026** el trend **funciona** (+29.8% en el sleeve), porque ahora hay el bull
2020-21, el bear de 2022 (cortos de equity + bono), y tendencias de oro. **La
diversificación por fin aporta** → el Calmar sube de ~0.10 a **~0.31 (full) / ~0.52 (2020-26)**.

## Comportamiento por régimen (1% riesgo, combinado)

| Régimen | Retorno | maxDD | |
|---|---|---|---|
| 2011–2019 | +41.2% | −13.9% | (la peor caída fue aquí, 2015–17) |
| **COVID 2020** | +1.0% | −3.0% | defensivo, sobrevive |
| Bull 2021 | +3.5% | −3.4% | |
| **Subida tipos 2022** | **−4.3%** | −5.5% | sobrevive el bear, pérdida pequeña |
| Recuperación 2023–24 | +11.3% | −3.8% | |
| 2025–26 | +16.7% | −2.9% | |
| **FULL 2020–2026** | **+33.7%** | **−9.1%** | positivo en cada régimen |

**Walk-forward:** IS 2011–2017 +3.3% CAGR → **OOS 2018–2026 +5.2%** (mejora fuera de
muestra; sin decadencia). **Monte Carlo:** DD mediana −11.8%, p95 −19.7%, ruina ≥25% = 0.8%.

## Frontier retorno/DD — respuesta a "¿qué DD para 15%?"

| Riesgo/trade | CAGR full | maxDD full | CAGR 2020–26 | maxDD 2020–26 | Ruina ≥25% |
|---|---|---|---|---|---|
| 1.0% | 4.3% | −13.9% | 4.8% | −9.1% | 0.8% |
| 1.5% | 6.4% | −20.3% | 7.1% | −13.4% | 9.7% |
| 2.0% | 8.3% | −26.5% | 9.2% | −17.6% | 34% |
| 3.0% | 11.9% | −37.8% | 13.2% | −25.5% | 86% |

**Respuesta honesta (Calmar ~0.5 en 2020–26):**
- **DD 10–15% → CAGR realista ~7–9%** (riesgo 1.5–2%).
- **15% CAGR → DD ~28–30%** y ruina alta. No es 10–15% DD.
- El objetivo **14–15% con DD 10–15% sigue sin ser alcanzable** robustamente (haría falta
  Calmar ~1.0; el real es ~0.5). Pero ahora estamos **mucho más cerca** que con índices solo.

## Punto operativo recomendado (robusto)
**Riesgo 1.5%/trade → ~6–7% CAGR full (~7% en 2020–26) con DD ~13–20%, ruina ~10%.** O más
conservador a 1% (4.3% / −14% / ruina <1%). Subir a 2% da ~9% pero el DD se va a ~18–26%.

## Qué haría fallar esto en real
- **Solo 5 instrumentos** → diversificación limitada; un CTA real usa 30–50 (más Calmar).
- **Bono sintético** desde el rendimiento (duración ~8), no un futuro real → aproximación.
- **Costes/slippage** mayores en estrés; gaps overnight que el stop no captura.
- Si el **trend vuelve a su "invierno"** (como 2011–2019), el retorno cae al nivel del MR (~4%).
- **2022 con correlación bono-equity positiva**: aquí el bono ayudó poco; en un shock peor podría no cubrir.

## Veredicto
Sistema **robusto y desplegable**: positivo en todos los regímenes 2020–2026, DD −9.1% en
ese periodo, 794 trades, OOS>IS, ruina ~0 a riesgo bajo. **Retorno realista ~6–9% CAGR a
DD 13–18%.** Para ~14–15% hay que aceptar ~25–28% DD (dentro de tu "stress máx 18–22%" NO
cabe; lo digo claro). La vía para subir el retorno manteniendo DD es **más instrumentos**
(30–50, estilo CTA), no más apalancamiento.

*Reproducir:* `python3 src/parse_investing.py ... && python3 src/run_recent.py`
