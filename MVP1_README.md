# Courier — MVP 1

Backend local con Python 3.11+, FastAPI y Pydantic. Recibe ofertas, aplica
restricciones deterministas, compara rentabilidad contra una estrategia y guarda
la explicación en memoria. Los siete archivos oficiales permanecen intactos.

## MVP 1 Scope

- `POST /decide`: ofertas oficiales, con o sin `event`, y `courier_state_overrides`.
- `GET /decisions/{order_id}`: contrato oficial de explicación desde el registro.
- Cinco restricciones en código; perfiles separados para `moto`, `car`, `bike`.
- Economics V0, reservation wage, valor configurable del dropoff y factibilidad
  conservadora con órdenes pendientes.
- Snapshot inmutable reemplazable, señal `degraded`, pruebas y benchmark local.

## Instalación y ejecución

Desde la raíz del repositorio, en PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host localhost --port 8000
```

Para reproducir exactamente las dependencias verificadas, instalar
`requirements-lock.txt` en lugar de `requirements-dev.txt`.
En Linux/macOS utilizar `.venv/bin/python` en lugar de `.venv\Scripts\python.exe`.
Para ejecución sin herramientas de desarrollo basta `requirements.txt`.
Usar **un worker**: estrategia y registro pertenecen al proceso. No hay persistencia
al reiniciar. El historial crece con las decisiones de esta sesión del MVP.

API interactiva: <http://localhost:8000/docs>.
`--host localhost` permite resolver el nombre local en IPv4 e IPv6; evita la
demora de fallback observada en Windows al escuchar solo en `127.0.0.1`.

## Pruebas y validador

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.benchmark --iterations 5000
.\.venv\Scripts\python.exe validate_format.py --endpoint http://localhost:8000/decide
.\.venv\Scripts\python.exe -m scripts.capture_responses
.\.venv\Scripts\python.exe validate_format.py --responses examples/responses.json
```

Los tres últimos comandos requieren el servidor activo para capturar respuestas;
validar un archivo ya capturado no requiere servidor. La captura genera siete
ofertas pequeñas: aceptación, rechazo económico y las cinco restricciones.
Para mostrar dos restricciones en vivo, consultar `DEMO-NIGHT` y `DEMO-CAPACITY`
en `/decisions/{order_id}` después de ejecutar la captura.

El validator oficial verifica **formato**, no corrección ni ganancias. Las pruebas
de corrección verifican límites, prioridad, overrides, stacking, aritmética,
determinismo, snapshots, registro y funcionamiento sin red ni archivos. El test
de latencia usa una mediana menor de 10 ms para tolerar pausas del planificador;
el benchmark independiente reporta mediana, p95, máximo y casos sobre 50 ms.

## Arquitectura y archivos

```text
app/
  main.py                      # aplicación, reloj de entrada, errores 422
  api/routes.py                # decidir y consultar explicación
  models/
    common.py                  # números finitos, tipos comunes
    requests.py                # oferta oficial
    responses.py               # respuesta, economics y explicación
    state.py                   # estado y aplicación de overrides
    strategy.py                # StrategySnapshot inmutable
  config/
    policy.py                  # límites oficiales y supuestos MVP
    vehicles.py                # perfiles de moto, car, bike
  decision/
    timing.py                  # trabajo pendiente y tiempos estimados
    constraints.py             # cinco restricciones, primera que falla
    economics.py               # fórmulas V0
    engine.py                  # evaluación y servicio con registro
    explanations.py            # texto económico sin LLM
  logging/decision_log.py       # historial en memoria y acceso por order_id
  services/strategy_store.py    # lectura/reemplazo atómico del snapshot
tests/
  conftest.py
  test_contract.py
  test_constraints.py
  test_economics.py
  test_state_overrides.py
  test_determinism.py
  test_latency.py
scripts/
  benchmark.py
  capture_responses.py
examples/responses.json
requirements.txt
requirements-dev.txt
requirements-lock.txt
pytest.ini
MVP1_README.md
VERIFICATION.md
```

Flujo: validar → resolver estado → estimar compromisos temporales → restricciones
→ economics → umbral de aceptación → explicación → registro → respuesta.
La estimación temporal es necesaria para las restricciones; no calcula pagos.
La primera restricción incumplida determina `binding_constraint` y `reason`.
Una negativa de seguridad nunca ejecuta economics. `tier` siempre es `tier1`.
`binding_constraint` está presente y vale `null` al aceptar; `economics` se omite
en respuestas de seguridad y queda como `null` en su registro.

`perf_counter_ns` mide duración; ninguna regla usa la hora del sistema.
En HTTP, `latency_ms` comienza al entrar al middleware e incluye validación,
estado, motor, explicación y copia/inserción del registro. Excluye la serialización
final y transporte de la respuesta. El benchmark mide también externamente la
llamada completa al servicio. No se recorta ni falsifica una latencia alta.

## Contrato, estado y ambigüedades oficiales

Los JSON oficiales son especificaciones descriptivas, no documentos JSON Schema
estándar completos. Los tests leen sus propiedades, ejemplos y campos requeridos,
y ejecutan las comprobaciones del validator sin modificarlo.

Se admiten todos los campos declarados de `order_offered`, incluyendo nombres de
zona, deadline, plataforma y estimaciones. `event` se puede omitir según el ejemplo
de `/decide`. Tip, preparación y estimaciones son opcionales; estimaciones ausentes
se derivan de distancia/velocidad. Tip y preparación ausentes valen cero.
Los campos desconocidos, valores negativos, no finitos y tipos inválidos producen
422. Los desbordamientos de cálculos también producen 422, no una aceptación.
`decision_deadline` se conserva en el registro: no es un límite de entrega ni
sustituye el presupuesto de latencia.

Peso y volumen no aparecen en la lista oficial `required`, aunque su descripción
los necesita para capacidad. Se acepta el request sin ellos, pero se devuelve
`SKIP / vehicle_capacity` por capacidad no verificable; no se presupone carga cero.

Cada request crea su propio estado. Una aceptación no demuestra entrega ni paso
del tiempo y no muta el estado de siguientes requests. El futuro simulador/proveedor
de estado será responsable de suministrar el estado efectivo en los overrides.
Esto evita que un replay idéntico cambie por solicitudes anteriores.

- `shift_end_time` explícito siempre prevalece; jamás se fija una hora del día.
- Sin fin explícito: `sim_time + (default_shift_hours - shift_elapsed_hours)`.
  El turno por defecto dura 8 horas **como supuesto MVP configurable**; elapsed
  ausente vale cero. En una secuencia real deben suministrarse fin o elapsed.
- `continuous_riding_min` explícito prevalece, incluso si existe un descanso previo.
  Sin él, se usa tiempo desde `last_break_end_time`; sin descanso se usa elapsed
  como cota conservadora de conducción. Con ningún override empieza en cero.
- El contrato no incluye inicio/duración/status de descanso. El proveedor de estado
  debe informar `last_break_end_time` como fin de un descanso válido de 20 minutos.
  Un fin futuro representa descanso activo y bloquea ofertas hasta ese instante.
  No se deducen descansos de esperas en restaurantes ni del tiempo entre requests.
  No se puede verificar la duración histórica de un descanso con este contrato.
- Las horas de seguridad usan el reloj local expresado por `sim_time`. Timestamps
  con y sin offset no se mezclan en un mismo request. Los offsets distintos se
  comparan por instante para fin de turno. No hay conversión mediante zona del SO.

### Restricciones y límites

Orden estable en `app/decision/constraints.py`:

| Prioridad | ID | Regla aplicada |
|---|---|---|
| 1 | `flagged_zone_night` | Dropoff restringido desde las 22:00 inclusive; comprueba hora de oferta y llegada estimada, también pendientes con zona conocida. |
| 2 | `mandatory_break` | Si ya hay 240 minutos continuos, exige descanso de 20 minutos. Rechaza si el trabajo acumulado proyecta más de 240. Llegar exactamente a 240 permite terminar y obliga a descansar antes de otra oferta. |
| 3 | `heat_rule` | Durante [12:00,16:00), conducción continua como máximo 90 minutos. Verifica segmentos que cruzan la ventana; no reinicia el contador al mediodía. Llegar exactamente a 90 es válido. |
| 4 | `shift_end_infeasible` | Finalización estimada posterior al fin de turno o compromiso pendiente sin tiempos suficientes. Igualdad con fin de turno es válida. |
| 5 | `vehicle_capacity` | Peso y volumen de toda la carga más el pedido nuevo no exceden el perfil. Igualdad es válida; carga desconocida impide verificar capacidad. |

La interpretación nocturna mínima es [22:00,24:00) de cada día: el protocolo no
especifica una hora de reapertura al día siguiente. Ampliarla a la madrugada requiere
definir esa política en una fase posterior. Los límites oficiales 22, 240, 20 y 90
se centralizan como literales; el snapshot no puede relajarlos accidentalmente.

### In-flight orders

La estructura interna de `courier_state_overrides.in_flight_orders` no está definida
en los archivos oficiales. El adaptador mínimo documentado es:

```json
{
  "in_flight_orders": [
    {
      "order_id": "ACTIVE-1",
      "weight_kg": 2,
      "volume_liters": 6,
      "estimated_pickup_min": 0,
      "estimated_delivery_min": 15,
      "restaurant_prep_min": 0,
      "zone_dropoff": 7
    }
  ]
}
```

Los tiempos y distancias de estos elementos representan **trabajo restante**.
Puede darse `distance_pickup_km`/`distance_delivery_km` en lugar de la estimación
correspondiente. Para un pedido ya recogido, indicar pickup 0 explícitamente.
Solo `order_id` es obligatorio en el adaptador; los datos faltantes no se convierten
en carga/trabajo cero: producen rechazo conservador de tiempo o capacidad.
`zone_dropoff` es opcional; sin ella no es posible revalidar la zona del trabajo
previamente aceptado, pero la zona del pedido nuevo siempre se verifica.

Se termina el trabajo existente en el orden recibido y luego el pedido nuevo.
Se suman sus pesos, volúmenes, tiempos y conducción. No hay descuento por compartir
ruta. Esta aproximación puede rechazar stacks que una optimización futura haría
viables. No se inventan deadlines de entrega que el contrato no proporciona.

## Economics V0

```text
gross_pay_mxn = base_pay_mxn * surge_multiplier + est_tip_mxn
total_distance_km = distance_pickup_km + distance_delivery_km
operating_cost_mxn = total_distance_km * operating_cost_mxn_per_km
net_pay_mxn = gross_pay_mxn - operating_cost_mxn

pickup_min = estimated_pickup_min o distance_pickup_km / speed_kmh * 60
delivery_min = estimated_delivery_min o distance_delivery_km / speed_kmh * 60
service_min = max(pickup_min + restaurant_prep_min + delivery_min,
                  minimum_service_time_min)
total_time_min = suma de service_min pendientes + service_min del pedido nuevo

raw_rate_mxn_hr = net_pay_mxn / total_time_min * 60
adjusted_rate_mxn_hr = raw_rate_mxn_hr + zone_values.get(zone_dropoff, 0)
deadhead_km = distance_pickup_km
ACCEPT si adjusted_rate_mxn_hr >= reservation_wage_mxn_hr; SKIP si es menor
```

El cero explícito en una estimación se respeta. El piso temporal configurable de
1 minuto evita división entre cero y también cuenta en factibilidad. La preparación
se suma conservadoramente; no se solapa con el trayecto hacia restaurante.

Pago y costo son **incrementales del pedido nuevo**. El denominador incluye tiempo
pendiente como penalización conservadora de oportunidad; no se vuelve a acreditar
el ingreso de pedidos aceptados. No pretende estimar toda la ganancia del turno.
Se comparan floats sin redondeo previo ni epsilon: empate exacto acepta. La razón
económica usa dos decimales, conservando precisión completa cuando redondear ocultaría
una diferencia en el umbral. Todas las razones tienen 1–39 palabras.

## Estrategia y configuraciones por calibrar

`app/models/strategy.py` contiene reservation wage, zone values, flagged zones,
perfiles y política. Sus mappings son copias inmutables; `StrategyStore` entrega
un único snapshot coherente por decisión. Se reemplaza fuera del fast path:

```python
from app.main import create_app
from app.models.strategy import StrategySnapshot

app = create_app(StrategySnapshot(reservation_wage_mxn_hr=180))
app.state.decisions.strategies.replace(StrategySnapshot(
    version="mvp1-v2", reservation_wage_mxn_hr=180,
    zone_values={7: 20, 11: -10}, flagged_zones={11}, is_stale=True,
))
```

`is_stale=True` conserva decisiones autónomas y marca `degraded=True` en respuesta
y registro. Un nuevo snapshot con `False` representa recuperación. No hay conexión
a modelo, actualización dinámica ni endpoint público para mutar estrategia.

**Todos los valores siguientes son supuestos demostrativos, no datos reales:**

| Configuración | Valor inicial | Ubicación |
|---|---|---|
| Reservation wage | MXN 165/h | `models/strategy.py` |
| Valor de zonas | 7: +15 MXN/h, 11: −15 MXN/h; resto: 0 | `models/strategy.py` |
| Zonas marcadas | `{11}`, solo ejemplo, no clasificación real de seguridad | `models/strategy.py` |
| Moto | 25 km/h; 15 kg; 50 L; MXN 1.2/km | `config/vehicles.py` |
| Car | 20 km/h; 100 kg; 300 L; MXN 3/km | `config/vehicles.py` |
| Bike | 15 km/h; 8 kg; 25 L; MXN 0.2/km | `config/vehicles.py` |
| Duración de turno fallback | 8 h | `config/policy.py` |
| Piso de servicio | 1 min | `config/policy.py` |

También requieren validación posterior la suma de preparación, ejecución serial
de stacks y penalización de tiempo pendiente. Los límites oficiales de seguridad
no son parámetros a calibrar.

## Registro y explicación

Se guarda cada decisión inmediatamente en memoria con respuesta, binding,
economics, request, estado resuelto, tiempos, snapshot completo/version, sim_time y
alternativa descartada. `position` queda `null`: el request no informa ubicación
actual y `zone_pickup` no demuestra dónde está el courier.

`GET /decisions/{order_id}` devuelve la última ocurrencia de ese ID, sin recalcular.
El historial completo se conserva internamente con `DecisionLog.history(order_id)`.
Las lecturas devuelven copias, por lo que no pueden alterar el registro.
IDs inexistentes devuelven 404.

## Out of Scope

Simulador/generación de turnos y streams por seed, frontend, mapas, routing real,
OSM/OSRM/OSMnx, OR-Tools, datasets, ML, predicción, LLM, voz, Snowflake, bases de
datos externas, cloud, clima/tráfico real, APIs externas, optimización de batching,
reposicionamiento y cancelación compleja.

El protocolo completo además exige shocks en turnos, replay de streams, recuperación
real de una conexión a modelo, comparación contra baselines y al menos 10 turnos
held-out. Esas evaluaciones requieren fases expresamente excluidas por esta solicitud.
Este MVP prueba replay de decisiones y stale snapshots; no afirma cumplir todavía
la evaluación de turnos ni publica ganancias o modifica la tabla oficial de resultados.

Los resultados medidos de esta implementación están en [VERIFICATION.md](VERIFICATION.md).
