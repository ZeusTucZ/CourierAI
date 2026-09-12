# Verificación local del MVP 2

Fecha: 2026-09-12. Entorno: Windows, Python 3.13.14, dependencias de
`requirements-lock.txt`. No se añadieron dependencias ni se cambiaron los archivos
Python preexistentes del MVP 1.

**Datos sintéticos sin calibración. Todos estos runs son de desarrollo, no reporting
held-out ni estimaciones de ingresos reales.**

## Regresión y suite completa

Antes de escribir código se ejecutó la suite original:

```text
python -m pytest -q --tb=short
95 passed, 2 warnings in 0.47s
```

Al finalizar:

```text
python -m pytest -q --tb=short
184 passed, 2 warnings in 3.63s
```

Resultado: **95 tests originales + 89 tests nuevos, todos aprobados**.
Las advertencias son las deprecaciones ya presentes de Starlette/httpx y del alias
BlockingPortal de AnyIO. No se modificaron tests existentes para obtener el resultado.

Los tests nuevos cubren generación en memoria y entre procesos, configuración,
transiciones de ejecución, stacking, overrides reales, cinco restricciones para
ambos agentes, umbral del baseline, efecto de zona, los cuatro shocks, expiraciones,
contabilidad, comparación, igualdad de condiciones, replay y detección de alteraciones.
Se prueban turnos completos con moto, car y bike, y controles sin shocks que exigen
cero tardanzas, cero trabajos bloqueados y cero pendientes al terminar.

## Endpoint oficial y event logs

Con el servidor del MVP 1 activo:

```text
python validate_format.py --endpoint http://localhost:8000/decide --event-log artifacts/mvp2/moto-seed-1234/SmartAgent.jsonl
```

Salida, exit code 0:

```text
events: decision=118, earnings_update=32, order_offered=118,
        position_update=280, shift_end=1, shift_start=1, shock=1
endpoint: http://localhost:8000/decide
round trip: 50ms
PASS output conforms to the required formats
```

También se ejecutó `/decide` individualmente: PASS. El round trip incluye conexión,
transporte y procesamiento HTTP; el validator aplica el presupuesto a `latency_ms`
informado por la decisión. La medición aislada del motor y servicio está más abajo.

```text
python validate_format.py --event-log artifacts/mvp2/moto-seed-1234/GreedyRateBaseline.jsonl
PASS output conforms to the required formats

python validate_format.py --event-log artifacts/mvp2-shocks/moto-seed-1234/SmartAgent.jsonl
PASS output conforms to the required formats
```

El baseline produjo 118 ofertas/decisiones, 26 earnings updates, 252 position updates
y una lluvia. La demo con cuatro shocks produjo 118 ofertas/decisiones, 33 earnings
updates, 293 position updates y cuatro shocks. Todos los logs son JSONL cronológicos
y usan únicamente tipos de evento oficiales. El validator verifica formato; la
corrección se prueba por separado con pytest.

## Determinismo por seed

```text
python -m scripts.run_shift --seed 1234 --shift-hours 8 --vehicle moto --start-zone 7
```

Ambos agentes usaron 118 ofertas del mismo stream, con SHA-256:

```text
5ac1733affebe3ad7062d3364f76420dcbc49e1b576314ae53282cfb6f39eaf1
```

Archivo: `artifacts/mvp2/moto-seed-1234/source.jsonl`.
El test `test_same_config_byte_identical` exige igualdad de bytes en los tres vehículos.
`test_generation_across_fresh_processes_and_hash_seeds` compara stdout binario de dos
procesos con `PYTHONHASHSEED=1` y `999`. También se comprueba que cambiar la seed cambia
el stream y que baseline/Smart reciben ofertas efectivas idénticas durante el turno.

## Replay de decisiones y ejecución

```text
python -m scripts.replay_shift artifacts/mvp2/moto-seed-1234/SmartAgent.jsonl
PASS SmartAgent: 118 decisions; full execution matches

python -m scripts.replay_shift artifacts/mvp2/moto-seed-1234/GreedyRateBaseline.jsonl
PASS GreedyRateBaseline: 118 decisions; full execution matches

python -m scripts.replay_shift artifacts/mvp2-shocks/moto-seed-1234/SmartAgent.jsonl
PASS SmartAgent: 118 decisions; full execution matches
```

SHA-256 de la fuente de la demo con cuatro shocks:

```text
c93c73c2f602a9435e1180db97f9f6901d183cd49476a7e0bdb91e922f851aab
```

Se verifican inputs exactos, snapshot, decisión, binding_constraint, reason, economics,
eventos de ejecución, estado y contabilidad. Solo se ignoran diferencias de latencia.
Los tests negativos comprueban rechazo al modificar reason, input, ingresos, fuente,
eliminar una decisión o truncar el turno.

## Ejemplo de turno completo

Seed 1234, 8 horas, moto, zona inicial 7; configuración sintética por defecto
(15:00–23:00, lluvia a mitad del turno). Archivo de evidencia:
`artifacts/mvp2/moto-seed-1234/comparison.json`.

| Métrica | GreedyRateBaseline | SmartAgent |
|---|---:|---:|
| Ofertas | 118 | 118 |
| Aceptadas / completadas | 25 / 25 | 31 / 31 |
| Rechazadas | 93 | 87 |
| Gross earnings MXN | 2337.92 | 3450.40 |
| Operating costs MXN | 152.17 | 164.36 |
| Net earnings MXN | 2185.75 | 3286.04 |
| Distancia km | 126.81 | 136.96 |
| Entregas tardías | 5 | 2 |
| Violaciones de seguridad | 0 | 0 |
| Episodios post-accept infeasible | 1 | 0 |
| Pendientes al cierre | 0 | 0 |

Diferencia neta: **MXN 1100.29**; diferencia de completadas: **+6**;
diferencia de distancia: **+10.16 km**; diferencia de tardanzas: **−3**.
Mejora porcentual según la fórmula solicitada: **50.34%**.
El episodio del baseline se contuvo y el trabajo pudo reanudarse; no se ocultó
como una ejecución normal sin disrupciones.

Demo adicional:

```text
python -m scripts.run_shift --seed 1234 --simulation-config config/synthetic_shocks_example.json --output-dir artifacts/mvp2-shocks
```

GreedyRateBaseline: MXN 2469.11 netos, 28 completadas, 7 tardías, 0 pendientes y
0 violaciones. SmartAgent: MXN 3319.23 netos, 32 completadas, 3 tardías, 0 pendientes
y 0 violaciones. Diferencia MXN 850.11; mejora 34.43%.

## Comparación de diez seeds de desarrollo

```text
python -m scripts.compare_agents --seeds 1 2 3 4 5 6 7 8 9 10
```

| Seed | GreedyRateBaseline net MXN | SmartAgent net MXN | Mejora % |
|---|---:|---:|---:|
| 1 | 2260.24 | 3064.56 | 35.59 |
| 2 | 2301.52 | 3061.83 | 33.04 |
| 3 | 2508.62 | 3366.98 | 34.22 |
| 4 | 2450.05 | 3079.32 | 25.68 |
| 5 | 2456.56 | 3172.12 | 29.13 |
| 6 | 2505.24 | 3455.26 | 37.92 |
| 7 | 2753.27 | 3536.32 | 28.44 |
| 8 | 2467.51 | 3265.10 | 32.32 |
| 9 | 2299.90 | 3148.12 | 36.88 |
| 10 | 2636.47 | 3534.12 | 34.05 |

- Media neta GreedyRateBaseline: MXN **2463.94**.
- Media neta SmartAgent: MXN **3268.37**.
- Media de mejoras porcentuales por seed: **32.73%**.
- Smart win rate: **100%** en estos diez casos; empates no cuentan como victoria.
- Violaciones acumuladas: **0 para cada agente**.
- Porcentajes indefinidos por baseline cero: **0** en esta muestra.

Evidencia: `artifacts/mvp2/multi_seed_comparison.json`, junto a los logs individuales.
Se mantuvo la configuración inicial; no se calibraron sus números después de observar
los resultados. La comparación mide políticas completas, incluyendo distinta valoración
del tiempo comprometido; no permite atribuir la mejora exclusivamente a zone values.

## Rendimiento

```text
python -m scripts.benchmark --iterations 5000
```

| Ruta | Mediana ms | p95 ms | Máximo ms | Casos >50 ms |
|---|---:|---:|---:|---:|
| Motor MVP 1 | 0.0238 | 0.0399 | 0.2633 | 0 / 5000 |
| Servicio incluyendo registro de decisión | 0.1520 | 0.3172 | 4.6084 | 0 / 5000 |

```text
python -m scripts.benchmark_shifts --seeds 1 2 3
pairs: 3
agent_shifts: 6
elapsed_seconds: 0.5407944
seconds_per_pair: 0.1802648
max_p95_decision_latency_ms: 0.6105
total_safety_violations: 0
```

El benchmark de turnos excluye exportación a disco; ejecuta turnos de 8 horas en tiempo
acelerado. Son mediciones locales reproducibles con variación de scheduling, no SLA
de red ni garantía para carga arbitraria.

## Integridad y alcance

Se compararon hashes SHA-256 de todos los archivos Python preexistentes en `app/`,
`tests/` y `scripts/`: **ninguno cambió**. La única modificación a un archivo previo
fue añadir `artifacts/` a `.gitignore`; el resto son archivos nuevos.

Los siete archivos oficiales mantienen los mismos hashes iniciales, también listados
en `VERIFICATION.md`:

| Archivo | SHA-256 |
|---|---|
| README.md | E7CFD76E3F58F251AB543C523D6C0172D4C932716007019C75F6E4820A97C9E4 |
| evaluation_protocol.md | 5BAD2101C1369C80CD679EB067804F7F4B32FFCF67BE1F973332A5D41D456CBC |
| event_log_schema.json | 21A7DCF17D80660BA0DD840D1FE87C1DCDE581443CD565C8F1F90D4421F1FAAD |
| decision_response_schema.json | 5AA80414E24A30748CDEC057DF2D2A1141032DADD3F02F95394E1217F9F4D2F4 |
| event_log_example.jsonl | AA09AF2594DD66929D7A0E83190EA627131BD89A93B02AE83F2396223CDDABAA |
| validate_format.py | 7F01AF0C76D8BFA1CE84A77AAAF51BE483786C4CED33B24431DAC1349CBA9473 |
| results_table_template.csv | EFDFC9C7F942FB25280072A0780E2BC113506A3619AA9FAAE872A0885985405A |

Los requisitos de implementación del MVP 2 están cubiertos. La evaluación completa
del hackathon sigue pendiente de validación real/calibración, resultados held-out y
una conexión a modelos cuya recuperación pueda ensayarse; esos elementos fueron
excluidos de esta fase. Las seeds reporting 10001–10010 no se ejecutaron automáticamente
y no se llenó la tabla oficial de resultados.

El modelo espacial no es geográfico; los SLA son promesas sintéticas; los parámetros
económicos/zonas son los provisionales del MVP 1. Una disrupción irreconciliable deja
trabajo pendiente explícito, sin inventar cancelación ni acreditar ingresos no ganados.
Las justificaciones y limitaciones se detallan en `MVP2_README.md`.
