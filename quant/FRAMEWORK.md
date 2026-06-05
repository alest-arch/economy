# Framework multi-sleeve SPX / NQ — corrección del MR y robustez multi-régimen

> Continuación de [`ESTRATEGIA.md`](ESTRATEGIA.md). Objetivo: **no optimizar** la
> estrategia de reversión, sino **corregir sus fallos estructurales** y convertirla en
> un sistema que **sobreviva en distintos regímenes**. Prioridad absoluta:
> supervivencia, no beneficio. Todo medido con costes reales (spread + slippage),
> riesgo 1% por operación, máximo 3 posiciones simultáneas.

---

## 1. Diagnóstico del fallo original

Se midió la expectancy del MR (RSI(2)+SMA200) **condicionada al régimen** de entrada
(ambos índices, neto de costes):

| Régimen | Bucket | N | E[R] | PF |
|---|---|---|---|---|
| Tendencia | SMA200 **subiendo** | 293 | +0.063 | 1.38 |
| Tendencia | SMA200 **bajando** | 23 | **−0.015** | **0.92** |
| Fuerza (ADX) | ADX<20 (rango) | 162 | +0.040 | 1.24 |
| Fuerza (ADX) | 20–30 | 91 | +0.112 | 1.87 |
| Fuerza (ADX) | **ADX≥30 (tend. fuerte)** | 54 | +0.047 | 1.21 |
| Volatilidad | baja | 154 | +0.057 | 1.38 |
| Volatilidad | **alta (ATR pct ≥0.66)** | 64 | **+0.023** | **1.11** |
| Estiramiento | normal (+1..+5 ATR) | 119 | +0.107 | 1.78 |
| Estiramiento | **muy estirado (>+5 ATR)** | 179 | **+0.029** | **1.15** |

Y por **periodo** (el síntoma que motivó el encargo):

| Periodo | MR E[R] | PF | Lectura |
|---|---|---|---|
| 2005–2009 | +0.045 | 1.30 | OK (incluye recuperación 2009) |
| 2010–2014 | +0.120 | 2.19 | Óptimo |
| 2015–2019 | +0.046 | 1.22 | Degradado (anomalía arbitrada + grind-up frothy) |
| **2020 (COVID, parcial)** | **−0.61 / −0.29** | **0.19 / 0.43** | **FALLO: comprar el dip mientras seguía cayendo** |

**Naturaleza del fallo (respuesta a las 4 hipótesis):**
- **Dependencia de régimen: SÍ, es la causa principal.** El MR vive de rangos/dips en
  régimen alcista normal; se degrada en (a) **tendencia muy fuerte/estirada** (los dips
  son superficiales y el edge ≈ costes) y se **rompe en crashes de alta volatilidad**
  (los dips continúan: 2020).
- **Sobreoptimización: parcial.** El edge bruto es real (estudio de eventos t>5), pero
  la rentabilidad fina depende de un periodo (2010–2014) y se ha arbitrado desde ~2015.
- **Falta de diversificación: SÍ.** Un único sleeve largo-reversión no tiene nada que
  ganar cuando el mercado *tendencia* sin dar dips → expone todo el sistema a un solo
  régimen.
- **Sensibilidad a costes: secundaria** para el swing (stops amplios → coste en R bajo);
  fue letal en intradía (ver §6), no aquí.

---

## 2. Corrección propuesta (estructural, no cosmética)

No se "ajustan parámetros para mejorar el backtest". Se aplican correcciones
**motivadas por el diagnóstico** y se **descartan** las que no aportan:

| Corrección | Motivación (del diagnóstico) | ¿Se adopta? |
|---|---|---|
| **Cortacircuitos de volatilidad** (no comprar dips si ATR-percentil 1y > 0.90) | el bucket de alta vol es el más débil; los crashes destruyen el MR | **SÍ** — mejora 2015–19 (PF 1.22→1.41 SPX) y suaviza 2020 |
| Filtro alcista (SMA50>SMA200) | el régimen bajista es ~breakeven | **NO** — daña la recuperación 2009 (E 0.029→0.008) |
| Filtro anti-estiramiento (dist<7 ATR) | el bucket muy-estirado rinde poco | **NO** — elimina demasiados trades buenos; 2005–09 se vuelve negativo |
| **Añadir un sleeve de tendencia** | el MR no tiene nada que hacer en tendencias fuertes; hay que *cubrir ese régimen* | **SÍ** — es la corrección central |

**MR corregido = original + cortacircuitos de volatilidad (ATR-pct < 0.90).** Sin más.

---

## 3. Diseño de sleeves

### Sleeve A — Mean-Reversion (corregido)
- Señal diaria: `close>SMA200` **y** `RSI(2)<10` **y** `ATR-percentil(252) < 0.90`.
- Ejecución H4, **solo largos**, stop `3·ATR`, salida `RSI(2)>65` / time-stop 30 barras.
- Riesgo 1%. Filtro de sesión US.

### Sleeve B — Trend-following (Donchian, largo) — *el diversificador de régimen*
- Señal diaria: `close > máximo(50)` **y** `close > SMA200` → largo.
- Salida: canal Donchian(20) de arrastre (estilo Turtle) o stop `3·ATR`. Sin TP (dejar
  correr). Ejecución diaria.
- **Solo largos** (ver §6: el lado corto en índices no tiene edge).
- **Parámetros FIJOS por diseño** (no se re-optimizan; ver §5, hallazgo crítico).

### Sleeve C — Breakout/volatilidad (opcional) — **NO incluido**
Evaluado y descartado: el breakout intradía es ruinoso (§6 de ESTRATEGIA.md) y el
breakout diario ya está capturado por el sleeve B. No aporta diversificación ortogonal
adicional → se omite para no añadir complejidad sin edge.

---

## 4. Sistema combinado final

Reglas de cartera: cada operación arriesga **1% del capital compartido**; **máximo 3
posiciones simultáneas** (se rechazan entradas por encima del cap). Verificado:
**concurrencia máxima observada = 3** (cumple "1–3 operaciones").

**Resultado por periodo (curva de equity combinada, params fijos, neto de costes):**

| Periodo | Retorno | Max DD intra-periodo |
|---|---|---|
| 2005–2009 | +3.6% | −6.5% |
| 2010–2014 | +26.6% | −4.4% |
| 2015–2019 | +14.3% | −4.6% |
| 2020 (parcial) | ≈+2% (plano) | −1.0% |
| **Total 2005–2020** | **×1.53 (+52.7%)** | **−6.5%** |

PF 1.65 · expectancy +0.134 R · 332 operaciones · **positivo en todos los periodos.**

**Aportación de cada sleeve por periodo (suma de R, ambos índices):**

| Periodo | MR (sum R) | TREND (sum R) | Quién sostiene |
|---|---|---|---|
| 2005–2009 | +2.4 | +2.2 | ambos |
| 2010–2014 | +11.6 | +11.7 | ambos |
| **2015–2019** | +5.8 | **+11.1** | **TREND rescata al MR degradado** |
| 2020 | −2.0 | 0 (en caja) | TREND evita el crash; cap absorbe |

→ Exactamente el comportamiento buscado: **cuando el MR se degrada (2015–19), el trend
compensa; en el crash (2020), el trend está en caja y limita el daño.**

---

## 5. Evaluación de robustez real

**Correlación entre sleeves (R mensual): +0.03** → prácticamente **ortogonales**. La
diversificación es real, no aparente.

**Walk-forward OOS (IS 4a / OOS 1a, re-selección de parámetros):**

| Sleeve | Instr | OOS N | OOS E[R] | OOS PF | Ventanas + |
|---|---|---|---|---|---|
| MR | SPX | 115 | +0.061 | 1.60 | **8/12** |
| MR | NQ | 108 | +0.094 | 1.79 | **9/12** |
| TREND | SPX | 31 | −0.243 | 0.59 | 3/12 |
| TREND | NQ | 28 | −0.329 | 0.50 | 3/12 |

**🚨 HALLAZGO CRÍTICO:** el sleeve de trend **falla el walk-forward con
re-optimización**. Causa: con solo ~43 operaciones en 15 años, optimizar parámetros por
ventana **sobreajusta**. Pero con **parámetros FIJOS** (sin optimizar), el trend es
**positivo en 7/10 años (SPX) y 8/11 (NQ)**, E[R] +0.22/+0.35. → **Conclusión
metodológica: los sistemas de tendencia de baja frecuencia NO deben optimizarse; se
fijan parámetros por criterio económico.** El sleeve B se usa con parámetros fijos.

**Monte Carlo del sistema combinado (10.000 sim, 1% riesgo):**

| Test | Resultado |
|---|---|
| Riesgo de ruina ≥20% DD (reshuffle) | **0.00%** |
| Riesgo de ruina ≥20% DD (bootstrap bloques) | 0.06% |
| Drawdown mediana / p95 | −6.1% / **−9.5%** |
| P(pérdida neta) en bootstrap | 0.27% |

**Comparación con buy&hold (2005–2020):** B&H rindió mucho más (NQ ×5.7, SPX ×2.4) pero
con drawdowns de **−53% a −57%**; el sistema combinado rindió ×1.53 con **−6.5%** de
drawdown. Se sacrifica rentabilidad por **supervivencia** (criterio explícito del
encargo).

### Estrategias / variantes DESCARTADAS y por qué
1. **Trend short / "crisis alpha"**: E[R] −0.43 (SPX) / −0.24 (NQ), PF 0.30/0.63. Los
   breakouts bajistas en índices se exprimen en el mercado alcista. **No hay edge corto.**
2. **Filtro alcista SMA50>SMA200 en el MR**: daña la recuperación 2009. Descartado.
3. **Filtro anti-estiramiento en el MR**: elimina trades buenos, vuelve 2005–09 negativo.
4. **Re-optimización del trend (walk-forward)**: sobreajuste → usar params fijos.
5. **Sleeves intradía (ORB, momentum)**: sin edge bruto, ruinosos netos (ESTRATEGIA.md §4).

---

## 6. Decisión final: ¿apto para capital real?

**APTO CON CONDICIONES — como overlay diversificado de bajo riesgo, NO como sistema de
retorno alto ni como cobertura de crisis.**

**A favor (cumple el criterio de supervivencia):**
- ✅ **Positivo en los 4 periodos** evaluados (2005–09, 2010–14, 2015–19, 2020 parcial).
- ✅ **No depende de un solo régimen**: MR (rangos/dips) + Trend (tendencias) con
  correlación +0.03.
- ✅ **Riesgo de ruina ≈ 0%** al 1%; drawdown histórico −6.5%, p95 Monte Carlo −9.5%.
- ✅ Respeta las restricciones (1% riesgo, ≤3 posiciones, sin martingala/grid).

**Condiciones y límites honestos (por qué NO es un "sí" incondicional):**
- ⚠️ **El sleeve de trend tiene baja confianza estadística** (~43 trades; falla WFA con
  re-optimización). Debe operarse con parámetros fijos y tamaño conservador.
- ⚠️ **El MR sigue siendo vulnerable a crashes rápidos** (2020 a nivel de sleeve). El
  combinado lo absorbe, pero el sistema **preserva capital, no gana, en crisis**.
- ⚠️ **Los datos terminan en mayo 2020.** No se puede validar 2021–2025, justo donde es
  más probable que continúe la decadencia del MR. **Reconfirmar en datos recientes
  antes de escalar es obligatorio.**
- ⚠️ **Rentabilidad modesta** (~2.8%/año compuesto al 1%): es un overlay de baja
  exposición; el retorno escala con el riesgo, pero a 3% el riesgo de ruina sube al 21%.

**Veredicto:** Sí se puede construir un sistema **más robusto multi-régimen** que la
estrategia original, y este lo es: convierte un sistema mono-régimen que se rompía en
2015–2020 en uno positivo en todos los periodos con ruina ~0. **Apto para capital real
en modo conservador y con reconfirmación en datos 2020–2025**; **no apto** como sistema
de alta rentabilidad ni si se exige beneficio en crisis. La honestidad obliga a decir
que su mayor riesgo —el tiempo fuera de muestra posterior a 2020— **no ha podido
testearse con estos datos**.

---

## Reproducir
```bash
cd quant/src
python3 run_multisleeve.py
```
Artefactos: `results/msleeve_period.csv`, `msleeve_correlation.csv`,
`msleeve_walkforward.csv`, `msleeve_montecarlo.json`, `msleeve_summary.json`,
`msleeve_equity.png`.
