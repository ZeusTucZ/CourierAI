# Verificación local del MVP 1

Fecha: 2026-09-12. Entorno: Windows, Python 3.13.14.
Dependencias utilizadas: `requirements-lock.txt`.

## Correctness

```text
python -m pytest -q --tb=short
95 passed, 2 warnings in 0.43s
```

Las dos advertencias son deprecaciones de dependencias del TestClient:
Starlette/httpx y el alias BlockingPortal de AnyIO. No hubo errores de tests.

Cobertura funcional: ejemplos oficiales, campos requeridos, tipos y números
inválidos, ACCEPT/SKIP, explicación breve, cinco restricciones y sus límites,
seguridad sobre pago, cruce de ventanas horarias, tres vehículos, economics,
empate/umbral, dropoff value, overrides, descanso activo, stacking, determinismo,
replays concurrentes, snapshot inmutable/reemplazable/degradado y consulta desde
registro sin recalcular. Una prueba bloquea red y lectura de archivos del fast path.

## Latencia

```text
python -m scripts.benchmark --iterations 5000
```

100 llamadas de calentamiento por ruta y 5,000 mediciones por ruta, alternando
aceptación, rechazo económico y las cinco restricciones:

| Ruta medida externamente | Mediana ms | p95 ms | Máximo ms | Casos >50 ms |
|---|---:|---:|---:|---:|
| Motor | 0.0197 | 0.0490 | 6.3025 | 0 / 5,000 |
| Servicio, incluyendo copia e inserción del registro | 0.1200 | 0.2981 | 3.4450 | 0 / 5,000 |

Son mediciones locales, no una garantía de latencia de red o bajo carga arbitraria.
El máximo puede incluir pausas del planificador y recolección de memoria.

## Validador oficial

Servidor ejecutado con:

```text
python -m uvicorn app.main:app --host localhost --port 8000
python -m scripts.capture_responses
python validate_format.py --endpoint http://localhost:8000/decide --responses examples/responses.json
```

Salida final, exit code 0:

```text
responses: 7 from examples/responses.json
endpoint: http://localhost:8000/decide
round trip: 33ms
PASS output conforms to the required formats
```

Ambos modos también se ejecutaron individualmente con resultado PASS.
El archivo contiene respuestas HTTP reales del backend: `DEMO-ACCEPT`, `DEMO-PAY`,
`DEMO-NIGHT`, `DEMO-BREAK`, `DEMO-HEAT`, `DEMO-SHIFT`, `DEMO-CAPACITY`.
No se modificó el validator. Este solo valida formato; la corrección se comprueba
por separado con pytest.

## Integridad de archivos oficiales

Los hashes SHA-256 coinciden antes y después de la implementación:

| Archivo | SHA-256 |
|---|---|
| README.md | E7CFD76E3F58F251AB543C523D6C0172D4C932716007019C75F6E4820A97C9E4 |
| evaluation_protocol.md | 5BAD2101C1369C80CD679EB067804F7F4B32FFCF67BE1F973332A5D41D456CBC |
| event_log_schema.json | 21A7DCF17D80660BA0DD840D1FE87C1DCDE581443CD565C8F1F90D4421F1FAAD |
| decision_response_schema.json | 5AA80414E24A30748CDEC057DF2D2A1141032DADD3F02F95394E1217F9F4D2F4 |
| event_log_example.jsonl | AA09AF2594DD66929D7A0E83190EA627131BD89A93B02AE83F2396223CDDABAA |
| validate_format.py | 7F01AF0C76D8BFA1CE84A77AAAF51BE483786C4CED33B24431DAC1349CBA9473 |
| results_table_template.csv | EFDFC9C7F942FB25280072A0780E2BC113506A3619AA9FAAE872A0885985405A |

## Límites del alcance verificado

No se ejecutó evaluación de ganancias, turnos held-out, baselines, generador de
streams por seed, shocks de simulador ni recuperación real de modelos: pertenecen
a las fases excluidas por la solicitud. No se afirma cumplimiento del reto completo.

Los contratos no definen el contenido de in-flight orders ni ofrecen inicio y
duración histórica del descanso. El adaptador y la responsabilidad del proveedor
de estado están explícitos en `MVP1_README.md`; no puede verificarse una duración
histórica de descanso con datos que el request no incluye.
