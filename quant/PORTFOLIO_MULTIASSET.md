# Portfolio cuant multi-asset (hedge-fund style) — diseño y veredicto honesto

> Encargo: portfolio diversificado multi-asset, ≥3 tipos de estrategia, risk budgeting,
> objetivo 12–20% CAGR con DD 10–15% (stress ≤18–22%), ruina ~0%, ≥700 trades, robusto
> multi-régimen. **Regla aceptada explícitamente: si el máximo robusto es <12%, decirlo
> sin forzar.**
>
> **Datos:** 25 mercados OANDA diarios reales **2005–2020** (cubre GFC 2008 y COVID 2020).
> ⚠️ **2022 (subida de tipos/inflación) y 2021–2024 (bull) NO están en mis datos** — no
> obtenibles en este entorno. Es una limitación material señalada en cada conclusión.

---

## 0. Veredicto (léase primero)

**El objetivo 12–20% CAGR con DD 10–15% NO es alcanzable de forma robusta con estos
activos y datos.** Lo digo explícitamente, como pediste.

- El **único sleeve con edge real** es **mean-reversion en índices** (Calmar ≈ 0.33–0.43).
- **Trend following perdió dinero 2005–2020** (−1% CAGR, −57% DD a 1% riesgo): fue un
  periodo históricamente malo para trend ("trend winter" 2011–2020) y su mejor año
  reciente (2022) no está en mis datos. **Añadirlo empeora el portfolio.**
- **Breakout/vol-expansion: edge ≈ 0.** No aporta.
- Por tanto la "diversificación multi-asset" **no mejora el retorno** aquí: los sleeves
  no-índice no tienen edge en este periodo.
- **Máximo robusto realista: ~4–6% CAGR a 10–15% DD** (Calmar ~0.33–0.43). Para 12% CAGR
  harían falta ~30–36% DD. Forzar 12–20% sería curve-fitting que reventaría en real.

> Estimación honesta de lo que un **CTA diversificado profesional** logra incluyendo los
> booms de trend de 2008 *y* 2022 (que no puedo testear aquí): ~8–12% CAGR / 15–20% DD
> (Sharpe ~0.5–0.8). Incluso eso queda **por debajo de 12% con DD 10–15%**. No invento
> esos números: los marco como referencia de industria, no como resultado medido.

---

## 1. Selección de activos y por qué

25 mercados, 4 clases (diversificación estructural por régimen):

| Clase | Instrumentos | Gana cuando… |
|---|---|---|
| **Equity** | SPX500, NAS100, FR40, JP225, UK100, US2000, AU200, NL25 | bull/rango (MR compra dips); cae en crisis |
| **Commodity** | XAU(oro), WTICO(petróleo), CORN, WHEAT, SOYBN, SUGAR, NATGAS | shocks de oferta/inflación; oro en crisis (refugio) |
| **Bond** | USB10Y, USB02Y, DE10YB, UK10YB | recesión/risk-off (rallian cuando cae la bolsa) |
| **FX** | EUR_USD, EUR_JPY, AUD_USD, GBP_USD, USD_CAD, AUD_JPY | tendencias macro; JPY como refugio risk-off |

Lógica de régimen: en crisis, **bonos+oro+cortos de equity** (vía TF) compensan; en bull,
**MR de índices** cosecha; en shocks, **commodities/FX** tienden. La intención de diseño
es correcta; el problema (sección 5) es que **2 de 3 motores no pagaron 2005–2020**.

---

## 2. Sleeves (3 estrategias distintas)

| Sleeve | Regla | Horizonte | Universo |
|---|---|---|---|
| **MR** (mean reversion) | RSI(2)<10 sobre SMA200, salida RSI(2)>65 / time-stop, stop 3·ATR, **long-only** | swing (2–8 días) | 8 índices |
| **TF** (trend following) | Donchian(50/20) ruptura, stop 3·ATR, **long+short** | semanas-meses | 25 mercados |
| **BO** (breakout/vol-exp) | ruptura Donchian(20) filtrada por expansión de ATR, long+short | días-semanas | 25 mercados |

Cada trade arriesga 1% (ATR-sizing). Sin martingala/grid/promediar pérdidas.

---

## 3. Combinación, correlación y risk budgeting

**Correlación entre sleeves (R mensual): MR–TF ≈ +0.1, MR–BO ≈ −0.35, TF–BO ≈ +0.5.**
Estructura de diversificación **buena** (MR y BO se compensan). Construcción de cartera:
vol-parity por activo (1/vol), peso igual por clase, presupuesto de riesgo entre sleeves,
y **vol-targeting** del portfolio (~11%). Cap de posiciones simultáneas para acotar heat.

**Pero la diversificación solo ayuda si los componentes tienen retorno esperado positivo.**
Medido (motor event-driven, neto de costes, 1% riesgo):

| Sleeve | CAGR | maxDD | Calmar | Veredicto |
|---|---|---|---|---|
| **MR (índices)** | **+3.94%** | −11.9% | **0.33** | único con edge |
| TF (25 mkts) | −1.03% | −57.0% | −0.02 | **perdedor neto** este periodo |
| BO (25 mkts) | ~0 | grande | ~0 | sin edge |
| **Combinado MR+TF (cap 6)** | +1.3% (a −13% DD) | −13% | **0.10** | TF arrastra al MR |

→ El portfolio combinado rinde **menos** que el MR solo, porque suma sleeves sin edge.

---

## 4. Estimación realista de CAGR y DD (≥700 trades)

Total trades del sistema: **2.499** (✓ ≥700). Frontier medido (combinado, cap 6):

| Riesgo/trade | CAGR | maxDD | Calmar | Ruina ≥25% |
|---|---|---|---|---|
| 0.50% | 1.3% | −13.1% | 0.10 | 1.3% |
| 1.00% | 2.4% | −24.9% | 0.09 | 36% |
| 2.00% | 3.8% | −44.9% | 0.09 | 96% |

**Mejor componente robusto (MR-índices) aislado:** ~4% CAGR / −12% DD / Calmar 0.33.
Escalado: **a DD 10–15%, el CAGR realista es ~4–6%**. Para 12% CAGR → ~30–36% DD.

**Análisis por régimen (punto operativo, neto):**

| Régimen | Retorno | maxDD |
|---|---|---|
| GFC 2008–09 | **+13.7%** | −3.7% |
| Crisis euro 2011 | +1.4% | −3.1% |
| Bull 2013–2017 | −6.8% | −9.5% |
| Q4-2018 | ~0% | −0.3% |
| COVID 2020 | −0.3% | −0.5% |

Defensivo y positivo en crisis (2008), plano en COVID — **sobrevive**, pero el bull
2013–17 lo erosiona (MR decae, TF whipsaw).

**Walk-forward:** IS 2005–2012 +3.5% CAGR → **OOS 2013–2020 −0.8%** (decae fuera de
muestra). **Monte Carlo (block bootstrap):** DD mediana −11.7%, p95 −21.2%, ruina ≥25% ≈ 1.5%.

---

## 5. Riesgos estructurales del sistema

1. **Dependencia de un solo edge:** todo el retorno viene del MR de índices, que está
   **decayendo** (OOS negativo). No es realmente multi-motor; es mono-motor + adornos.
2. **Trend following muerto en la muestra:** el principal diversificador de los CTAs no
   pagó 2005–2020. Si vuelve (como en 2022), el sistema mejoraría; si no, no hay segundo
   motor.
3. **Concentración equity:** 8 de los activos con edge son índices muy correlacionados
   (~0.9); el "diversificador" real (bonos/commodities/FX) no aportó retorno.
4. **Sin sleeve de carry/vol real:** no tengo datos de tipos (carry FX/bonos) ni de
   estructura temporal del VIX → no pude construir esos motores, que son los que dan
   estabilidad a los fondos macro.

---

## 6. Qué haría fallar este sistema en el mundo real

- **Continuación de la decadencia del MR** (anomalía arbitrada) → el único motor se apaga.
- **Otro "trend winter"** → el diversificador sigue sin pagar; el sistema depende del MR.
- **Crash más rápido que los filtros** (gap overnight, halt) → el stop no protege al precio
  esperado; el sizing 1% asume ejecución limpia.
- **Costes reales > modelados** en mercados menos líquidos (NATGAS, SUGAR, NL25) o spreads
  que se ensanchan en estrés.
- **Cambio de régimen de correlación:** en 2022 bonos y equities cayeron juntos (correlación
  positiva) → el "hedge" de bonos falla justo cuando se necesita. (No testeable aquí: 2022
  fuera de datos.)
- **Sobreajuste implícito** si se "rescata" el 12% subiendo riesgo → ruina (a 2% riesgo,
  ruina ≥25% = 96%).

---

## Conclusión

Construí el portfolio multi-asset/multi-estrategia con risk budgeting y validación completa
(2.499 trades, regímenes, Monte Carlo, walk-forward). **El máximo retorno robusto bajo DD
10–15% es ~4–6% CAGR — por debajo del objetivo 12%, y lo declaro explícitamente.** La causa
no es la construcción (correcta) sino que **dos de los tres motores no tienen edge en los
datos disponibles** y el tercero (MR) decae. Un 12–20% solo sale aceptando ~30%+ DD
(ruina alta) o curve-fitting — ambos prohibidos por tu propio criterio.

**Camino honesto para acercarse a 12%+:** (a) datos 2021–2026 + 2022 para revivir el motor
de trend; (b) sleeve de carry real (necesita datos de tipos); (c) universo CTA completo
(40+ mercados con term structure). Sin eso, el sistema desplegable real es un **overlay
defensivo ~5% CAGR / 12% DD / ruina ~0**, no un fondo de 15%.

*Reproducir:* `python3 src/build_universe.py && python3 src/run_portfolio_event.py`
(y `run_portfolio.py` para la versión vectorizada con vol-targeting). Artefactos en
`results/portfolio_event_*` y `results/portfolio_*`.
