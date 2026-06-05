# Estrategia cuantitativa SPX / NQ — Diseño, validación y veredicto honesto

> **Criterio de selección de este estudio:** *estabilidad fuera de muestra y entre
> periodos*, **no** rentabilidad absoluta ni el mejor backtest. Una estrategia con
> menos operaciones pero comportamiento estable se prefiere a otra más rentable pero
> inestable. Todo el análisis está construido para *intentar romper* las estrategias,
> no para lucirlas.

---

## 0. Veredicto ejecutivo (léase primero)

1. **El único edge estadísticamente real encontrado es la reversión a la media de
   corto plazo a horizonte SWING (señal diaria, ejecución en H4).** En estudio de
   eventos es altamente significativo: tras un RSI(2) bajo en régimen alcista, ambos
   índices rebotan a 8 días con **t = 5.4 (SPX)** y **t = 5.9 (NQ)**.

2. **Ese edge NO es estable en el tiempo: se ha degradado.**
   - 2005–2009: expectancy **+0.045 R**, profit factor 1.30
   - 2010–2014: expectancy **+0.120 R**, profit factor 2.19 (máximo)
   - **2015–2020: expectancy +0.006 R, profit factor 1.02 → prácticamente cero.**

   Es el patrón clásico de una anomalía publicada (Connors) que el mercado arbitra.
   En walk-forward la señal sobrevive en **9/12 ventanas OOS en NQ** y solo **7/12 en
   SPX**, con las ventanas recientes claramente más débiles.

3. **Todo lo intradía probado (Opening Range Breakout, momentum intradía, reversión
   en H1) NO tiene edge ni siquiera bruto, y es ruinoso neto de costes.** Se descarta
   con evidencia (sección 4). *No se fuerza intradía para alcanzar tamaño de muestra.*

4. **Recomendación honesta:** la estrategia swing es **la más estable de las
   evaluadas** y, con riesgo fijo del 1%, su **riesgo de ruina es ≈ 0%**. Pero dado
   el deterioro 2015–2020 **no se recomienda desplegarla con tamaño pleno**: trátese
   como *overlay* de bajo riesgo / cartera en papel hasta reconfirmar edge en vivo, y
   con las mejoras estructurales de la sección 9. **No tiene un edge fiable hoy; tuvo
   uno claro hasta ~2014.**

---

## 1. Datos y metodología

| Aspecto | Detalle |
|---|---|
| Instrumentos | SPX500 (S&P 500) y NAS100 (Nasdaq‑100), CFD/índice OANDA |
| Granularidad fuente | **1 minuto real**, 2005‑01‑02 → 2020‑05‑14 (~4,0 M y 4,3 M velas) |
| Remuestreo | M5, M15, H1, H4 y D1 (UTC, `closed='left'`) — sin huecos rellenados |
| Regímenes cubiertos | GFC 2008, flash crash 2010, 2011, 2015‑16, Q4‑2018, **COVID 2020** |
| Datos auxiliares | VIX diario CBOE 1990‑2026 (filtro de régimen) |
| Precios | Se usan precios **de bróker retail** (transables ~24h), no el print oficial |

**Por qué OANDA y no el índice cash (^GSPC/^NDX):** son los precios que un trader
retail puede *ejecutar* realmente; los spreads/slippage se modelan **encima** de un
precio ya tradeable, en vez de fantasear con rellenos al cierre oficial del índice.

**Antisesgo (look-ahead):**
- La señal se calcula sobre una vela **cerrada** `t` y se ejecuta en la **apertura de
  `t+1`**.
- Señal multi‑timeframe: las features diarias se **retrasan un día completo** antes de
  mapearse a las velas H4 (solo se usa el día ya cerrado). Verificado explícitamente.
- Stops/targets se evalúan *intrabar* con **desempate pesimista**: si una vela toca
  stop y target, se asume **stop primero**. Los huecos de apertura que cruzan el stop
  rellenan al precio (peor) de apertura + slippage.

**Contabilidad en R‑múltiplos:** cada operación arriesga **1% del capital actual**
(`tamaño = 1%·equity / distancia_al_stop`). El resultado se mide en **R** (P&L /
riesgo inicial). Esto normaliza el capital (irrelevante por ser todo %) y hace
limpias la expectancy, el Monte Carlo y la ruina. Sin piramidar, sin promediar
pérdidas, sin martingala/grid.

**Modelo de costes (en puntos de índice, se restan en CADA entrada y salida):**

| Instrumento | ½ spread | slippage | slippage extra en stop | Round‑trip típico |
|---|---|---|---|---|
| SPX | 0.25 pt | 0.20 pt | +0.40 pt | ~0.9–1.3 pt (≈ 0.4–0.6 bps) |
| NQ  | 1.00 pt | 0.75 pt | +1.50 pt | ~3.5–5 pt (≈ 0.5–0.8 bps) |

Conservador para OANDA. Además se hace **stress ×2 y ×3** (sección 8).

---

## 2. El hallazgo que define la temporalidad: *el edge es multi‑día*

Estudio de eventos: retorno **futuro** tras la señal de reversión (RSI(2)<10 sobre la
SMA200), por timeframe. Mide la señal **sin** el ruido del stop/salida.

| Instr. | TF | Horizonte | Señales | Ret. fwd | Win% | **t‑stat** | Incond. |
|---|---|---|---|---|---|---|---|
| SPX | **H1** | +8 barras | 1170 | **−4.0 bps** | 50.3% | **−2.25** | +1.0 |
| SPX | H4 | +8 barras | 274 | +10.1 bps | 60.9% | +1.84 | +3.7 |
| SPX | **D1** | +8 días | 270 | **+73.4 bps** | 67.0% | **+5.42** | +18.7 |
| NQ | **H1** | +8 barras | 1123 | −2.6 bps | 52.0% | −1.29 | +1.8 |
| NQ | H4 | +8 barras | 275 | +3.1 bps | 57.1% | +0.48 | +6.7 |
| NQ | **D1** | +8 días | 306 | **+89.3 bps** | 64.7% | **+5.92** | +34.4 |

**Lectura:**
- En **H1 no hay edge** (incluso negativo: a 1 hora los descensos *continúan*; domina
  ruido/microestructura + costes).
- En **D1 el edge es fuerte y muy significativo** (t > 5). Es un efecto de **2–8 días**.
- **H4 es marginal** por sí solo, pero es **la única de M5/M15/H1/H4 con signo
  correcto** y sirve como timeframe de *ejecución* para una señal de origen diario.

→ **Temporalidad elegida: H4 (ejecución) gobernada por señal diaria.** No M5/M15/H1:
no tienen edge (lo confirma además el rechazo intradía de la sección 4).

---

## 3. La estrategia retenida — "Swing Mean‑Reversion SPX/NQ"

**Tipo:** reversión a la media de corto plazo, **filtrada por tendencia**, **solo
largos** (comprar miedo dentro de un régimen alcista). Híbrida en el sentido de que
la *dirección* la fija un filtro de tendencia (componente trend) y el *timing* lo fija
la sobreventa (componente mean‑reversion).

**Por qué solo largos:** el edge de reversión es fiable solo al alza sobre la SMA200.
Vender los "rips" por encima de tendencia **no tiene soporte estadístico** (se probó;
sección 4). Los índices tienen deriva alcista estructural: shortear reversión pierde.

### Reglas exactas (if / then)

Indicadores sobre la **vela diaria** (señal), ejecución sobre **H4**:

```
trend       = SMA(close_diario, 200)
rsi2        = RSI(close_diario, 2)            # Wilder
atrD        = ATR(diario, 14)
sesion_US   = velas H4 de 12:00 y 16:00 UTC   # solape con la sesión cash US
```

**ENTRADA (largo):**
```
SI   close_diario(ayer) > trend(ayer)            # régimen alcista
 Y   rsi2(ayer) < 10                             # sobreventa de corto plazo
 Y   vela H4 actual ∈ sesion_US
ENTONCES comprar en la apertura de la siguiente vela H4
         tamaño = 1% equity / (3.0 · atrD)
```

**STOP LOSS:**
```
stop = entrada − 3.0 · atrD          # stop volatilidad-escalado, amplio
```

**SALIDA (lo que ocurra primero):**
```
1) rsi2(día cerrado) > 65            -> salir en la apertura H4 siguiente  (reversión completada)
2) stop tocado intrabar             -> salir al stop (con slippage)
3) time stop: 30 velas H4 (~5 días) -> salir en apertura H4 siguiente
```
*(No hay take‑profit fijo: la "diana" es la reversión a la media, capturada por la
condición 1. Variante con TP = R·stop disponible en el código.)*

### Justificación matemática del RR

La reversión a la media es **alto winrate / RR < 1**. Resultados OOS (NQ):

```
winrate p           = 75.4%
avg_win  (W)        = +0.28 R
avg_loss (L)        = −0.468 R     (ratio de pago W/L ≈ 0.60, <1)
expectancy          = p·W − (1−p)·L = 0.754·0.28 − 0.246·0.468 = +0.096 R
winrate de equilibrio = L / (W+L) = 0.468 / 0.748 = 62.6%
```
El edge existe **porque 75.4% > 62.6%** (margen de 12.8 pp). Un RR<1 es *coherente* y
deseable aquí: stops amplios (3·ATR) dan espacio a la reversión y, al dimensionar por
el stop, **cada pérdida sigue acotada a ~1R** independientemente de su amplitud.

**Filtros de mercado:** (a) tendencia SMA200 diaria — solo operar a favor de la deriva;
(b) sesión US — concentra el edge donde hay liquidez/spreads buenos; (c) sobreventa
RSI(2)<10 — exige un *desplazamiento* real, no cualquier pullback. Filtro VIX probado y
**descartado** (sección 8).

**Concurrencia:** máx. 2 posiciones simultáneas (SPX + NQ) → *heat* ≤ 2%. Cumple "1–3
operaciones simultáneas".

---

## 4. Estrategias DESCARTADAS y por qué fallan

> Esta sección es parte central del entregable: documentar lo que **no** funciona es
> tan importante como lo que sí. Todo está medido con los mismos costes realistas.

### 4.1 Opening Range Breakout (ORB) intradía — **DESCARTADA**

| Instr. | Config | Trades | E[R] **bruto** | PF bruto | E[R] **neto** | PF neto | maxDD neto |
|---|---|---|---|---|---|---|---|
| SPX | ORB or60 rr2 L+S | 4358 | +0.010 | 1.03 | **−0.117** | 0.70 | −99.5% |
| SPX | ORB or60 largo+trend | 2235 | +0.025 | 1.09 | −0.106 | 0.71 | −91.3% |
| NQ | ORB or60 rr2 L+S | 4123 | **−0.008** | 0.97 | −0.231 | 0.48 | −100% |
| NQ | ORB or30 rr1 L+S | 6269 | −0.000 | 1.00 | −0.273 | 0.46 | −100% |

**Por qué falla:** el edge **bruto es ≈ 0** (ruido; t≈1 en el mejor caso). Como los
stops intradía son pequeños, **el coste en R es grande** (coste/distancia‑stop), y el
sistema pasa de "moneda al aire" a **ruina** (−100% DD). El famoso resultado ORB de la
literatura depende de comisiones ínfimas, un único instrumento y un periodo reciente
concreto; **no es robusto** en 15 años con spreads de CFD realistas.

### 4.2 Momentum intradía (primera hora → resto del día) — **DESCARTADA**
SPX bruto +0.11 R pero **neto −0.27 R** (PF 0.69, −100% DD); NQ neto −0.61 R. El
pequeño edge bruto **no sobrevive a los costes** a esa frecuencia (~255 trades/año).

### 4.3 Reversión a la media en H1 — **DESCARTADA**
Estudio de eventos **negativo** (SPX t = −2.25 a 8 barras). A 1 hora los descensos
*continúan*; no hay reversión que capturar. Backtest neto: PF 0.46–0.59.

### 4.4 Breakout/trend Donchian en H1–H4 (largo+corto) — **DESCARTADA**
PF 0.84–0.85 neto, DD −67% a −83%. Demasiados *whipsaws*; los costes y los falsos
breakouts dominan la deriva.

### 4.5 Reversión a la media **largo+corto** (añadir cortos) — **DESCARTADA**
Añadir cortos *empeora* todo (NQ H1: E[R] −0.177, DD −90%). Confirma que **el lado
corto de reversión no tiene edge** en índices con deriva alcista.

**Conclusión de la sección:** de todo el espacio explorado, **solo sobrevive la
reversión swing solo‑largos**. Lo demás falla por (i) ausencia de edge bruto y/o (ii)
costes que convierten un edge marginal en pérdidas a alta frecuencia.

---

## 5. Resultados de la estrategia retenida (neto de costes, riesgo 1%)

### 5.1 Métricas — muestra completa (parámetros fijos *a priori*) vs **walk‑forward OOS**

| Métrica | SPX full | **SPX OOS** | NQ full | **NQ OOS** |
|---|---|---|---|---|
| Nº operaciones | 153 | 114 | 163 | 122 |
| Winrate | 69.3% | 65.8% | 73.6% | **75.4%** |
| Avg win / Avg loss (R) | 0.32 / −0.51 | 0.24 / −0.37 | 0.31 / −0.68 | 0.28 / −0.47 |
| **Expectancy (R)** | +0.064 | **+0.034** | +0.052 | **+0.096** |
| **Profit factor** | 1.41 | **1.27** | 1.29 | **1.83** |
| Max drawdown | −3.2% | −2.1% | −3.1% | −2.4% |
| CAGR | 0.63% | 0.35% | 0.54% | 1.06% |
| **Sharpe (aprox.)** | 0.41 | **0.27** | 0.32 | **0.74** |
| Trades / año | 10.1 | 10.6 | 10.6 | 11.1 |
| Máx. pérdidas seguidas | 3 | 4 | 4 | 4 |

**Cartera SPX+NQ (OOS, combinada en el tiempo):** crecimiento ×1.16, **CAGR 1.39%,
maxDD −3.1%, Sharpe 0.72**.

> Lectura honesta: **NQ mantiene edge OOS sólido (PF 1.83); SPX queda marginal (PF
> 1.27).** Retornos absolutos **bajos** porque el sistema está **muy poco tiempo en
> mercado** (≈11 trades/año, pocos días cada uno) — es un *overlay* de baja exposición
> y alta calidad por unidad de riesgo, no un sistema de retorno alto.

### 5.2 Walk‑forward (IS 4 años / OOS 1 año, re‑selección de parámetros en cada IS)

- **SPX: 7/12 ventanas OOS con expectancy positiva.**
- **NQ: 9/12 ventanas OOS con expectancy positiva.**

Las ventanas que terminan en **2016–2020** son sistemáticamente las más débiles
(SPX 2015‑2020: E[R] −0.54; NQ 2012‑2016: E[R] −0.22). → **inestabilidad reciente.**

---

## 6. Monte Carlo y riesgo de ruina

Sobre el flujo combinado de operaciones OOS (236 trades), 10.000 simulaciones:

| Test | Qué mide | Resultado |
|---|---|---|
| **Reordenación** (reshuffle) | dependencia de la secuencia / DD de camino | ruina(≥20%DD) **0.0%**; DD mediana −3.7%, p95 −5.9%, p99 −7.2% |
| **Bootstrap por bloques** | ¿fue suerte la muestra? varía el resultado final | final p05 ×1.055, p50 ×1.165, p95 ×1.285; **P(pérdida neta) 0.47%** |
| Ruina ≥30% DD | catástrofe | **0.0%** |

*(En reshuffle el resultado final es invariante por construcción —multiplicar es
conmutativo— por eso ese test mide DD/secuencia; el bootstrap es el que dispersa el
resultado final.)*

### Escalado de riesgo (por qué 1% es correcto)

| Riesgo/trade | Final p50 | DD mediana | DD p95 | **Ruina ≥20%** | Ruina ≥40% |
|---|---|---|---|---|---|
| 0.5% | ×1.10 | −2.8% | −4.4% | 0.0% | 0.0% |
| **1.0%** | **×1.20** | **−5.6%** | **−8.7%** | **0.0%** | 0.0% |
| 2.0% | ×1.43 | −11.0% | −16.8% | 1.0% | 0.0% |
| 3.0% | ×1.68 | −16.2% | −24.3% | **21.1%** | 0.0% |
| 5.0% | ×2.28 | −26.1% | −37.9% | 89.1% | 2.8% |

→ **1% es ruina‑resistente; a partir de 3% la probabilidad de ruina se dispara.** El
riesgo fijo del 1% del enunciado queda **validado cuantitativamente**.

---

## 7. Estabilidad entre periodos — *el criterio decisivo* (y donde la estrategia falla)

| Época | Trades | Expectancy (R) | Winrate | Profit factor |
|---|---|---|---|---|
| 2005–2009 | 87 | +0.045 | 74.7% | 1.30 |
| 2010–2014 | 114 | **+0.120** | 72.8% | **2.19** |
| **2015–2020** | 115 | **+0.006** | 67.8% | **1.02** |

**Este es el resultado más importante del estudio.** Aplicando *tu* criterio
(estabilidad > rentabilidad), la estrategia **suspende el test en el último régimen**:
su edge se ha erosionado hasta ~cero en 2015–2020. Es coherente con una anomalía
ampliamente publicada (Connors RSI2) que el mercado ha arbitrado. La señal sigue
teniendo el *signo* correcto (winrate 67.8% > equilibrio), pero el margen neto sobre
costes ya no es fiable.

---

## 8. Robustez adicional

**Stress de costes (muestra completa, config fija):**

| Instr. | ×1 | ×2 | ×3 |
|---|---|---|---|
| SPX | PF 1.41 | PF 1.27 | PF **1.10** (sobrevive) |
| NQ | PF 1.29 | PF 1.11 | PF **0.93** (rompe) |

SPX aguanta hasta 3× costes; **NQ rompe a 3×** (spreads más anchos). El edge de NQ es
más rentable pero **más sensible a costes**.

**Filtro VIX (intento de "rescatar" 2015–2020) — NO funciona:** condicionar las
entradas por nivel/régimen de VIX **no revive** el edge reciente (2015‑2020 con
VIX<18 → PF 1.12; con VIX≥18 → PF 0.87; sin relación monótona en toda la muestra). Se
reporta como **mejora fallida**, no se incorpora (sería *overfitting*).

**Benchmark (comprar y mantener, 2005–2020):**

| | Estrategia (1%) | SPX B&H | NQ B&H |
|---|---|---|---|
| CAGR | ~1.2–1.4% | +5.6% | +11.8% |
| Sharpe | ~0.5–0.7 | 0.34 | 0.56 |
| Max DD | **−3 a −6%** | −56.9% | −53.2% |

Risk‑adjusted (Sharpe) la estrategia fue **competitiva** con ~**10× menos drawdown**,
pero con retorno absoluto muy inferior (baja exposición). Históricamente.

---

## 9. Conclusión honesta y mejoras estructurales

**¿Tiene edge real?**
- **Sí, históricamente y de forma robusta hasta ~2014** (t>5 en estudio de eventos,
  sobrevive walk‑forward, ruina ≈0 al 1%).
- **No de forma fiable hoy:** 2015–2020 ≈ break‑even (PF 1.02). El edge se ha
  degradado, que es precisamente el fallo de *estabilidad entre periodos* a vigilar.
- **Todo lo intradía: sin edge, descartado con evidencia.**

**Por tanto, no se recomienda desplegar a tamaño pleno.** Es el sistema **más estable
de los evaluados**, ruina‑resistente, y un buen *framework* — pero el edge concreto
está arbitrado. Acción recomendada: **papel / tamaño mínimo + reconfirmación de edge
en vivo (p.ej. 12–24 meses) antes de escalar.**

**Mejoras estructurales (no cosméticas de parámetros):**
1. **Diversificar el suelo de edge:** la reversión en índices está arbitrada;
   reaplicar el *mismo marco* a activos menos eficientes (futuros de materias primas,
   índices de menor capitalización, FX cruzados) donde la anomalía aún pague.
2. **Sleeve ortogonal de tendencia** (trend‑following en H4/D1 sobre los mismos
   índices) para equilibrar regímenes: la reversión sufre en mercados en tendencia
   fuerte/bajista; un sleeve trend cubre justo ese estado. Combinar por presupuesto de
   riesgo, no por optimización conjunta.
3. **Aumentar exposición sin aumentar riesgo de cola:** más instrumentos
   *descorrelacionados* (no más riesgo por trade), para subir CAGR manteniendo DD.
4. **Sleeve de *overnight drift*** (efecto nocturno, especialmente fuerte en NQ:
   Sharpe ~0.86 en el estudio) como *timing* de beta separado y aún presente, con
   stop de catástrofe.
5. **Aceptar el diagnóstico:** en índices muy líquidos, el edge ya no está en la señal
   de precio cruda, sino en **ejecución, costes y construcción de cartera**. Buscar
   ahí, no en más *tuning* de RSI/ATR.

---

## 10. Reproducibilidad

```bash
cd quant/src
python3 build_data.py        # M1 -> H1/H4 (M5/M15 vía script en run_diagnostics path)
python3 run_validation.py    # full-sample, walk-forward OOS, Monte Carlo, cartera, gráficos
python3 run_diagnostics.py   # event study, decadencia, escalado de riesgo, rechazo intradía, benchmark
```

Artefactos en `quant/results/`: `metrics_fullsample.csv`, `walkforward_folds.csv`,
`montecarlo.json`, `cost_stress.csv`, `event_study.csv`, `edge_decay.csv`,
`risk_scaling.csv`, `intraday_rejection.csv`, `benchmark.csv`, `equity_curves.png`,
`summary.json`.

**Limitaciones declaradas:** (1) datos 2005‑2020 (sin 2021‑2025, que probablemente
acentuaría la decadencia); (2) precios OANDA CFD, no futuros ES/NQ reales (spreads
parecidos, pero sin libro de órdenes ni roll de futuros); (3) un solo proveedor de
datos; (4) Sharpe anualizado por frecuencia de trades (aproximado, como pedía el
enunciado); (5) el remuestreo a día de calendario UTC no es idéntico a la sesión cash
RTH (efecto menor, validado por el estudio de eventos).
