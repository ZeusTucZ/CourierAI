# MVP 3 — Verificación local

Fecha: 2026-09-12. macOS, Python 3.14.7. Datos exclusivamente sintéticos.

## Regresión y tests

Antes de modificar código: **223 passed, 2 warnings in 1.60s**.
Al finalizar: **272 passed, 2 warnings in 1.73s**; 223 existentes + 49 nuevos.
Los warnings son deprecaciones ya presentes de Starlette/httpx y AnyIO BlockingPortal.
No se modificaron tests de MVP 1/2. Los nuevos están en `tests/test_mvp3.py`.

Cobertura: perfil inmutable/load-save, CSV/JSON/JSONL y Solomon con unidades explícitas,
missingness, generación calibrada determinista, predicciones zona/hora, fallback disperso,
cutoff histórico, dos futuros distintos con el mismo observable, snapshots/clipping,
límites de reservation wage, failure/recovery, opportunity cost, reposición y costos,
inserción sobre FIFO, precedencia pickup/dropoff, capacidad/SLA, límites de candidatos,
SLA fijo, atribución de shock directa y propagada, cancelación excepcional/penalizaciones,
splits sin overlap, configuración congelada, 10 shifts, fallo por seguridad, ablations
de un solo flag, replay con updates/fallos, detección de manipulación y compatibilidad MVP 2.
También se verifica seguridad con moto/car/bike y ausencia de lecturas de histórico/archivos
dentro del fast path con snapshot V2 activo.

## Calibración y procedencia

No se usó un dataset externo. `prepare_mvp3_data` generó 1,217 registros históricos
sintéticos con seeds 1–10, en diez turnos de febrero de 2026, 80 horas de exposición.
El perfil usa 15.2125 órdenes/hora y distribuciones empíricas ajustadas a esos registros.
No se presenta esta calibración como evidencia de condiciones reales de reparto.

- Perfil: `artifacts/calibrated_profile.json`.
- Manifest: `artifacts/calibration_manifest.json`.
- Reporte: `artifacts/calibration_report.json`.
- Modelo: `artifacts/historical_model.json`.
- Fuente: `artifacts/synthetic_tuning_history.json`.
- SHA-256 fuente: `ff0716c7e38a029ba51a8694e22f86d3266e67ac6865093205b69440c1650d81`.

El CLI `calibrate_dataset` también se ejecutó sobre esa fuente, con `--synthetic`,
80 horas y un directorio separado `artifacts/calibration_cli_check`.

## Fórmulas y políticas usadas

- Zone value: `clip(predicted_zone_net_rate - mean_zone_net_rate, -50, 50)` MXN/h.
- Opportunity cost: `max(0, predicted_net_rate) * committed_minutes / 60 * 0.25`.
- Reservation wage: `clip(165 + 0.1*reference - 20*max(0,1-remaining_min/60),80,250)`.
- Reposición: ganancia esperada sobre WAIT > MXN 5, horizonte 30 min, dwell 30 min,
  grid sintético de 0.5 km; cobra tiempo, distancia y costo; valida hard constraints.
- Batching: inserción pickup/preparación y delivery separados, sin preemptar fase activa;
  hasta 32 candidatos y 4 órdenes activas; minimiza suma de completions factibles.
- SLA: `offer_time + 1.5*max(1,pickup+prep+delivery) + 10 min`, fijo al aceptar.
- Cancellation: solo tras closure/rain/delay registrada que vuelve trabajo tardío o
  inviable; compara continue/cancel values; multa MXN 20 y margen MXN 5.
- Skip penalty: MXN 0, independiente de cancellation. Lateness value: MXN 1/min.
- No OR-Tools: la inserción acotada queda holgadamente bajo el presupuesto medido.

Costos, velocidades, capacidades, geografía sintética, SLA, valores y penalizaciones
siguen siendo supuestos configurados. Las cinco restricciones oficiales no se ajustan.
El README documenta fórmulas completas, transformaciones y limitaciones.

## Rendimiento

1,000 mediciones por operación, después de 20 warmups; resultados locales.

| Operación | Mediana ms | p95 ms | Máximo ms | >50 ms |
|---|---:|---:|---:|---:|
| /decide HTTP TestClient | 0.5296 | 0.6532 | 1.3179 | 0 |
| StrategyUpdater | 0.2419 | 0.2732 | 0.3190 | 0 |
| Insertion, 3 active orders | 0.5102 | 0.5570 | 0.6814 | 0 |

Seis turnos de agente de 8 horas, sin exportación: **225.11 ms**.
TestClient mide la pila HTTP en proceso; no es latencia de red. El validador del
endpoint servido por Uvicorn midió 20 ms round trip y dio PASS. Benchmark completo:
`artifacts/benchmark_mvp3.json`.

## Tuning y held-out

Tuning: 1–10. Held-out final: 10001–10010. Sets disjuntos; no se entrenó con held-out.
No se optimizaron parámetros a partir de estos resultados ni de las ablations.
Las exportaciones se repitieron después de corregir serialización de compatibilidad;
los parámetros, decisiones y resultados económicos permanecieron iguales.

Fingerprint de profile/model/policy en ambos sets: `73f1b66c92c7ecf4f4d68e0468b6b6604b6d7853a85c81d095a36f6d311d50a5`.

### Tuning

| Seed | Baseline net MXN | Smart net MXN | Mejora % | Safety B/S |
|---:|---:|---:|---:|---|
| 1 | 2146.33 | 2563.37 | +19.43 | 0/0 |
| 2 | 2506.31 | 2731.88 | +9.00 | 0/0 |
| 3 | 2184.55 | 2434.11 | +11.42 | 0/0 |
| 4 | 2011.46 | 2549.21 | +26.73 | 0/0 |
| 5 | 2151.56 | 2740.28 | +27.36 | 0/0 |
| 6 | 2107.75 | 2374.13 | +12.64 | 0/0 |
| 7 | 2091.70 | 2422.45 | +15.81 | 0/0 |
| 8 | 1943.87 | 2498.53 | +28.53 | 0/0 |
| 9 | 2336.89 | 2582.88 | +10.53 | 0/0 |
| 10 | 2231.98 | 2758.62 | +23.60 | 0/0 |

Media baseline: **2171.24**; media Smart: **2565.54**.
Mejora media: **18.51%**; mediana: **17.62%**.
Win rate: **100%**. Safety violations: **0**.

### Held-out

| Seed | Baseline net MXN | Smart net MXN | Mejora % | Safety B/S |
|---:|---:|---:|---:|---|
| 10001 | 1993.98 | 2567.65 | +28.77 | 0/0 |
| 10002 | 2306.22 | 2513.21 | +8.98 | 0/0 |
| 10003 | 2047.35 | 2580.20 | +26.03 | 0/0 |
| 10004 | 2068.81 | 2819.60 | +36.29 | 0/0 |
| 10005 | 2005.49 | 2613.34 | +30.31 | 0/0 |
| 10006 | 2135.16 | 2795.18 | +30.91 | 0/0 |
| 10007 | 2009.25 | 2611.10 | +29.95 | 0/0 |
| 10008 | 2149.45 | 2740.20 | +27.48 | 0/0 |
| 10009 | 2088.43 | 2548.92 | +22.05 | 0/0 |
| 10010 | 2090.54 | 2220.66 | +6.22 | 0/0 |

Media baseline: **2089.47**; media Smart: **2601.01**.
Mejora media: **24.70%**; mediana: **28.13%**.
Win rate: **100%**. Safety violations: **0**.

Held-out: Baseline completó 238 órdenes y omitió 1,042; Smart completó 263 y
omitió 1,017. Tardanzas: 11 vs 2, atribuibles a disrupciones. Cero cancelaciones y
cero órdenes pendientes en estos diez turnos. Smart realizó 27 reposiciones,
18.5967 km y MXN 22.3161 de costo. La cancelación se demuestra en tests controlados,
no se finge que ocurrió en held-out. Métricas completas por seed, incluyendo bruto,
costos, MXN/h y MXN/km: `evaluation/heldout_results/results.json`.

CSV compatible con las columnas oficiales: `artifacts/results_mvp3.csv`.
Solo se incluyen GreedyRate y OurAgent; no se inventó una fila Oracle.

## Ablations sobre tuning

| Variante | Media neta | Delta vs Full | Delta vs baseline |
|---|---:|---:|---:|
| SmartFull | 2565.54 | +0.00 | +394.31 |
| SmartNoZoneValue | 2604.32 | +38.77 | +433.08 |
| SmartNoReposition | 2651.30 | +85.75 | +480.06 |
| SmartNoImprovedBatching | 2530.08 | -35.46 | +358.84 |
| SmartNoHistoricalPrediction | 2632.78 | +67.23 | +461.54 |

La inserción mejora sobre FIFO en este conjunto. El reposicionamiento, el valor
de zona y la capa histórica no muestran beneficio neto en estas ablations. Full se
conserva sin ajustes para no ocultar el resultado. No se afirma que todo componente
implementado aporte mejora; es justamente lo que esta evaluación permite detectar.

## Replay, failure y validador

- 20/20 logs held-out (10 seeds × 2 agentes): replay completo y formato oficial PASS.
- 20/20 logs preexistentes de MVP 2: replay completo PASS con esta implementación.
- Dos futuros distintos con oferta/estado inicial iguales: primera predicción,
  snapshot y decisión idénticos; test de no-leakage PASS.
- Update inicial, fallo simulado a minuto 30, recuperación a minuto 60:
  decisiones `degraded=false,true,false`; mismo último snapshot durante fallo.
- Replay reproduce ese flujo de updates y el trace; alterar un snapshot registrado falla.
- `/decide` con snapshot V2 activo y validador oficial: PASS.
- `validate_format.py` sobre el log de Smart de seed 10001: PASS; 128 decisiones,
  27 earnings updates, 269 position updates, 1 shock y 16 strategy updates.
- Los tipos adicionales del trace no se mezclan en el JSONL público.

## Correcciones durante la implementación

1. El adapter CSV necesitaba convertir números de texto antes de la validación estricta.
2. Rutas/agenda exportadas debían usar arrays JSON para igualdad de replay.
3. Nuevos campos económicos opcionales rompían replay de logs antiguos: se preservó
   la serialización MVP 1/2 para snapshots legacy y se normalizan solo defaults de
   metadata antes de comparar. No se descartan decisiones ni contabilidad.
4. Se añadió atribución del shock a órdenes atrasadas por propagación en la cola.
Las correcciones tienen pruebas; no se alteró la estrategia para mejorar las ganancias.

## Archivos nuevos y modificados

```text
app/
  calibration/           NEW: profiles.py, loaders.py, fitting.py, __init__.py
  strategy/              NEW: models.py, historical.py, updater.py, opportunity_cost.py,
                             reposition.py, routing.py, sla.py, cancellation.py, __init__.py
  evaluation/            NEW: runner.py, __init__.py
  simulation/strategic.py NEW: extension of the existing simulator
  simulation/            MOD: config.py, generator.py, simulator.py, state.py, replay.py
  models/                MOD: strategy.py, responses.py
  decision/              MOD: economics.py, explanations.py, engine.py
  metrics/               MOD: collector.py, results.py
scripts/                 NEW: calibrate_dataset.py, prepare_mvp3_data.py, mvp3_common.py,
                             run_tuning.py, run_heldout_evaluation.py, run_ablations.py,
                             benchmark_mvp3.py, serve_mvp3.py
evaluation/              NEW: tuning_seeds.txt, heldout_seeds.txt
tests/test_mvp3.py        NEW: 49 cases
MVP3_README.md            NEW
MVP3_VERIFICATION.md      NEW
.gitignore               MOD: generated evaluation result directories
```

## Integridad de archivos oficiales

Comparación byte por byte contra HEAD: los siete archivos oficiales están intactos.

| Archivo | SHA-256 |
|---|---|
| README.md | `e7cfd76e3f58f251ab543c523d6c0172d4c932716007019c75f6e4820a97c9e4` |
| evaluation_protocol.md | `5bad2101c1369c80cd679eb067804f7f4b32ffcf67be1f973332a5d41d456cbc` |
| event_log_schema.json | `21a7dcf17d80660ba0dd840d1fe87c1dcde581443cd565c8f1f90d4421f1faad` |
| decision_response_schema.json | `5aa80414e24a30748cdec057df2d2a1141032dadd3f02f95394e1217f9f4d2f4` |
| event_log_example.jsonl | `aa09af2594dd66929d7a0e83190ea627131bd89a93b02ae83f2396223cddabaa` |
| validate_format.py | `7f01af0c76d8bfa1ce84a77aaaf51be483786c4ced33b24431dac1349cba9473` |
| results_table_template.csv | `efdfc9c7f942fb25280072a0780e2bc113506a3619aa9faae872a0885985405a` |

## Límites de la conclusión

Se implementó y verificó la infraestructura MVP 3. Los datos y la geografía siguen
siendo sintéticos, el baseline es una política greedy específica, la mejora se mide
sobre streams nuevos de la misma familia calibrada y no prueba generalización real.
El resultado defendible es reproducibilidad, trazabilidad y comparación controlada;
la validación empírica requiere datos externos, exposición verificable y nuevos
held-out conjuntos después de futuras decisiones de tuning.
