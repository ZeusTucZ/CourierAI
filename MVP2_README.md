# Courier — MVP 2: simulador y comparación

El MVP 2 convierte las decisiones del MVP 1 en trabajo ejecutado y contabilizado.
Permite comparar `GreedyRateBaseline` y `SmartAgent` sobre el mismo stream, registrar
el turno y verificar su replay. No modifica el motor ni el endpoint del MVP 1.

**Los datos generados en MVP 2 son sintéticos y todavía no están calibrados con datasets reales.**
Los resultados son experimentos de desarrollo, no real-world performance, tarifas
de mercado, ingresos esperables ni evidencia sobre zonas reales de Monterrey.

## Ejecutar

Se utilizan las dependencias ya instaladas para MVP 1. No se añadieron dependencias.
Desde la raíz del repositorio, en PowerShell:

```powershell
.\.venv\Scripts\python.exe -m scripts.run_shift --seed 1234 --shift-hours 8 --vehicle moto --start-zone 7
.\.venv\Scripts\python.exe -m scripts.compare_agents --seeds 1 2 3 4 5 6 7 8 9 10
.\.venv\Scripts\python.exe -m scripts.replay_shift artifacts/mvp2/moto-seed-1234/SmartAgent.jsonl
.\.venv\Scripts\python.exe -m scripts.benchmark_shifts --seeds 1 2 3
```

En Linux/macOS sustituir `.venv\Scripts\python.exe` por `.venv/bin/python`.
El simulador no requiere levantar el servidor HTTP: llama al motor en memoria.
Para instalar o ejecutar `/decide`, consultar `MVP1_README.md`.

Cada comparación individual produce:

```text
artifacts/mvp2/moto-seed-1234/
  source.jsonl                  # fuente exógena idéntica para ambos agentes
  GreedyRateBaseline.jsonl       # ejecución + inputs + snapshot para replay
  SmartAgent.jsonl
  comparison.json               # métricas y diferencias
```

La comparación de múltiples seeds añade `artifacts/mvp2/multi_seed_comparison.json`.
`artifacts/` está ignorado por Git; los archivos se regeneran con estos comandos.
`--output-dir` permite conservar experimentos diferentes sin sobrescribirlos.

Configuraciones alternativas:

```powershell
# Demostración de los cuatro shocks, con parámetros explícitos
.\.venv\Scripts\python.exe -m scripts.run_shift --seed 1234 --simulation-config config/synthetic_shocks_example.json --output-dir artifacts/mvp2-shocks

# Seeds de desarrollo desde archivo; jamás se carga reporting automáticamente
.\.venv\Scripts\python.exe -m scripts.compare_agents --seed-file config/seeds_tuning.txt
```

Los runners aceptan `--vehicle moto|car|bike`, `--shift-hours`, `--start-zone`,
`--simulation-config archivo.json` (SyntheticConfig), `--strategy archivo.json`
(StrategySnapshot) y `--baseline-threshold`.

## Arquitectura

```text
app/
  simulation/
    config.py       ShiftConfig + supuestos sintéticos separados
    events.py       tipos públicos oficiales y modelo de shocks
    generator.py    RNG local y stream exógeno determinista
    state.py        estado persistente, fases y trabajo restante
    shocks.py       condiciones del mundo y ofertas efectivas
    simulator.py    cola de eventos, ejecución, descansos e invariantes
    replay.py       replay de inputs y de ejecución completa
  agents/
    base.py         interfaz Agent y adaptador de overrides
    baseline.py     GreedyRateBaseline
    smart.py        wrapper de DecisionService del MVP 1
  metrics/
    collector.py    reconstrucción desde decisiones y contabilidad del log
    results.py      ShiftMetrics y ShiftResult
    comparison.py  diferencias y agregados
  logging/
    event_log.py    JSONL cronológico y serialización canónica
scripts/
  shift_common.py
  run_shift.py
  compare_agents.py
  replay_shift.py
  benchmark_shifts.py
config/
  seeds_tuning.txt
  seeds_reporting.txt
  synthetic_shocks_example.json
tests/
  mvp2_support.py
  simulation/{test_generation,test_execution,test_shocks}.py
  agents/test_agents.py
  metrics/test_metrics.py
  integration/test_shifts.py
```

Cada `Simulator` posee un `CourierState`, un `WorldState` y un log nuevos. Cada agente
tiene su propia instancia. `run_pair` genera el stream una vez y cada simulador lo
copia; no se comparte estado mutable. El objeto simulador solo puede ejecutarse una
vez. La comparación rechaza streams, entornos físicos o reglas de seguridad distintos.

## Generación y determinismo

`ShiftConfig` mantiene los cuatro campos oficiales: `seed`, `shift_hours`, `vehicle`
y `start_location_zone`. El campo anidado `simulation` separa las opciones internas.
El fin del turno se deriva de inicio + duración, nunca de una hora fija del motor.

Cada generación crea `random.Random(seed)`. No depende del reloj real, RNG global,
orden de threads, red ni requests anteriores. Con el mismo código y configuración
produce bytes JSONL idénticos; se serializa con claves ordenadas, UTF-8 y saltos LF.
También se prueba en procesos separados con distintos `PYTHONHASHSEED`.

El stream contiene `shift_start`, `order_offered`, `shock`, `shift_end`. El primer
ping ocurre al inicio, incluso en turnos cortos. Los siguientes intervalos se
muestrean del rango configurado. Los IDs son únicos dentro del turno.

Las estimaciones de viaje se derivan de distancia/velocidad antes de preguntar al
agente, usando los mismos perfiles para ambos. Se incorporan las condiciones activas
del mundo y se registra tanto la oferta efectiva como el evento fuente original.
Las ofertas efectivas también son iguales para los dos agentes; únicamente difieren
sus overrides de estado, como consecuencia de sus propias decisiones.

**Limitación espacial deliberada:** las distancias son costos de trayecto sintéticos
muestreados, independientes de la posición alcanzada por cada agente. No se recalculan
desde `current_zone`, pues no hay geografía y se requieren ofertas idénticas. El estado
sí actualiza la zona en pickup/dropoff. No se modela que terminar en cierta zona cambie
la demanda o la distancia de ofertas futuras.

## Baseline y SmartAgent

Ambos usan las mismas funciones de las cinco restricciones del MVP 1, las mismas
capacidades, costos, velocidades, zonas marcadas y reglas temporales.

| Agente | Criterio económico |
|---|---|
| GreedyRateBaseline | `(pago neto del nuevo pedido / tiempo de servicio del nuevo pedido) * 60 >= baseline_threshold` |
| SmartAgent | Política MVP 1 intacta: pago neto / tiempo total comprometido, más valor de dropoff, comparado con reservation wage |

El baseline evalúa rentabilidad **inmediata marginal**. Considera los pendientes para
seguridad, capacidad y fin de turno, pero no penaliza su tasa con tiempo comprometido
ni utiliza zone values. Es una política greedy simple, no un agente AcceptAll ni uno
que ignore seguridad. Acepta el empate exacto. Su threshold por defecto hereda el
reservation wage del Smart (165 MXN/h en el snapshot inicial) para no introducir otro
umbral arbitrario. Puede variarse explícitamente con `--baseline-threshold`.

El Smart llama a `DecisionService`, que utiliza el `DecisionEngine` existente. El
adaptador pasa conducción acumulada, tiempo transcurrido del turno, descanso, fin del
turno y tiempos/distancias/carga restantes de cada orden en vuelo.

Una diferencia de ingresos compara **estas dos políticas completas**. No demuestra
que el ajuste de zona por sí solo cause la mejora: también difieren los denominadores
de su tasa. No se retocó Smart ni se calibraron thresholds para mejorar estos resultados.

## Ejecución por eventos y estado

La cola usa `(sim_time, prioridad, secuencia)` para resolver empates determinísticamente.
En un mismo instante: finalizaciones de fase/descanso, expiraciones, shocks, ofertas,
y finalmente `shift_end`. Así una entrega exactamente al final del turno se contabiliza
antes de cerrarlo y un shock expirado no afecta la oferta de ese instante.
No hay sleeps ni avance segundo por segundo. Los tiempos restantes se almacenan en
microsegundos enteros; los eventos obsoletos tras reprogramar se invalidan por versión.

`ACCEPT` reserva carga y añade una orden a la cola FIFO. Sus fases son viaje a pickup,
preparación, viaje a dropoff y, si corresponde, el piso de servicio heredado del MVP 1.
Solo se ejecuta una fase a la vez. Se permiten varias órdenes activas sin compartir
trayectos ni optimizar la ruta. Se conserva la carga de todos los compromisos aceptados
hasta completarlos, una reserva conservadora incluso antes del pickup físico.

`SKIP` registra la razón e incrementa el contador; no añade carga, ingreso, recorrido
ni penalización monetaria. Un rechazo por descanso/calor con el courier vacío y
conducción acumulada inicia un descanso real de 20 minutos. También se descansa al
alcanzar los límites aplicables al terminar el trabajo. La conducción se reinicia
solo al completar el descanso, nunca por esperar en un restaurante.

## Shocks

`apply_shock(WorldState, Shock)` cambia el mundo; el simulador actualiza las fases
pendientes, sus estimaciones y los eventos programados. No llama a modelos ni a red.

| Tipo oficial | Efecto del modelo sintético |
|---|---|
| `surge` | El último multiplier activo para la zona de **pickup** reemplaza el multiplier de ofertas nuevas. Expira tras `duration_min`. El pago ya aceptado permanece fijo. |
| `rain` | Multiplica estimaciones de viaje de ofertas nuevas y tiempo de viaje restante de pedidos activos. Al expirar, retira el factor del trabajo aún restante. No cambia distancia ni agrega espera de restaurante. Lluvias solapadas no multiplican el factor entre sí; permanece activo mientras haya alguna. |
| `closure` | Agrega `closure_delay_min` a ofertas/pedidos con pickup o dropoff en la zona. Sin zona, un cierre identificado solo por `road` usa una penalización global conservadora, porque no se conocen rutas. La expiración impide aplicar la penalización a ofertas nuevas; no borra la demora ya asignada a trabajos aceptados. |
| `delay` | Agrega `slip_min` a la orden identificada, tras el pickup pendiente o antes de reanudar delivery. Si aún no fue ofrecida, conserva la demora para esa oferta. Si ya se completó o nunca aparece, no afecta otras órdenes. |

Los shocks temporales necesitan duración positiva; surge necesita zona y multiplier,
closure zona o road, delay order_id y slip_min. Un payload insuficiente produce un
error de validación, no un efecto silencioso ni parámetros inventados. La especificación
oficial enumera campos, pero no define la semántica de un shock sin esos datos.

`shock_schedule=null` (default) genera una lluvia a mitad del turno. Una lista vacía
deshabilita shocks para controles. El archivo de ejemplo demuestra los cuatro tipos;
su cierre de la zona 11 y nombre de road son ejemplos sintéticos, no cierres reales.

### Disrupciones que vuelven inviable trabajo aceptado

Después de un shock se revalidan los compromisos pendientes con las restricciones
compartidas y las fases reales. Si el recorrido resulta inviable, se registra un
`position_update` con `action=post_accept_infeasible`, constraint, IDs y tiempos.
El trabajo queda detenido en `waiting`, conservando carga, pago prometido y costos
ya incurridos. Se puede reanudar si, por ejemplo, la lluvia expira y vuelve a ser
factible; en caso contrario queda pendiente al cerrar el turno.

Esto es una contención de seguridad, no una política de cancelación/reasignación.
No se circula ni entrega más allá del turno para ocultar incumplimientos. Se reportan
`post_accept_infeasible` y `uncompleted_orders`, además de seguridad y tardanzas;
cero violaciones de seguridad no significa que todos los pedidos se entregaron.
La solución de compromisos bloqueados queda para MVP 3.

## Contabilidad, SLA y métricas

El ingreso se acredita únicamente al completar: `base_pay * surge + tip` de la oferta
aceptada. Los costos se incurren proporcionalmente al recorrido ejecutado, incluyendo
pickup: `km recorridos * costo/km`. Así un pedido detenido mantiene sus costos ya
incurridos y no recibe ingresos ficticios. Nunca se vuelven a cargar costos al completar.
`net_earnings = gross_earnings - operating_costs`.

El simulador conserva la estimación de finalización calculada al aceptar como
`promised_completion_time`. Una entrega completada después de ella cuenta como
`late_deliveries`. Es un SLA sintético de tolerancia cero; **no** se utiliza
`decision_deadline` como deadline de entrega. Las estimaciones revisadas por shocks
se registran sin modificar la promesa original. Los pendientes no completados se
reportan aparte, sin fingir una entrega tardía ni inventar multas.

`ShiftMetrics` reconstruye gross/costs/net, ofertas/aceptadas/rechazadas/completadas,
distancia, idle time, tardanzas, seguridad y latencias media/p95 desde el event log.
Los `earnings_update` guardan contabilidad acumulada y también se emite uno final
para incluir costos de trabajos incompletos. Idle time solo cuenta tiempo disponible
sin trabajo, excluyendo descanso, preparación y detenciones por inviabilidad.

Se calculan MXN/h sobre la duración completa del turno, incluido descanso/idle, y
MXN/km sobre distancia real simulada; con distancia cero, MXN/km es `null`.

La comparación informa diferencia neta, diferencia de completadas, distancia,
tardanzas y seguridad. Usa la fórmula solicitada:

```text
improvement_pct = (smart_net - baseline_net) / baseline_net * 100
```

Con baseline cero devuelve `null`, nunca infinito. El resumen promedia porcentajes
definidos e informa cuántos quedaron indefinidos; no divide las medias para llamarlo
"media de mejoras". Con baseline negativo conserva la fórmula firmada, cuyo porcentaje
no tiene la interpretación habitual de mejora: revisar la diferencia absoluta.
La tasa de victorias cuenta únicamente diferencias netas estrictamente positivas.

## Logs y replay

Solo se emiten los tipos públicos oficiales: `shift_start`, `order_offered`, `shock`,
`decision`, `position_update`, `earnings_update`, `shift_end`. No se inventan tipos
`completion` o `break_end` para el log; estos son consecuencias internas de la cola.

El formato oficial permite campos adicionales. Se añaden:

- `shift_start`: configuración completa, snapshot exacto, agente, versión y hash del stream.
- Eventos exógenos: `source_event` original.
- `decision`: `decision_request` exacto y estado del courier.
- `position_update`: acción, carga, conducción y compromisos temporales por pedido.
- `earnings_update`/`shift_end`: contabilidad y diagnósticos necesarios para reconstruir métricas.

Replay tiene dos comprobaciones: vuelve a decidir con los inputs/snapshot registrados,
y reconstruye toda la simulación desde los eventos fuente, comparando inputs, eventos,
estado y contabilidad. Verifica order_id, decisión, constraint, reason y economics.
Solo ignora latencias; no re-genera la fuente con el RNG para sustituir lo registrado.
Detecta también manipulación de inputs, ingreso, source_event y logs truncados.

La fuente es byte-idéntica. Los logs de ejecución contienen latencias medidas, por lo
que su igualdad es lógica, excluyendo esos campos, no igualdad byte a byte.

## Parámetros sintéticos y justificación de su uso

Todos se centralizan en `app/simulation/config.py`. Los rangos se muestrean con
uniformes independientes y se redondean a seis decimales. No provienen de observaciones.

| Parámetro | Default | Razón de diseño, no evidencia empírica |
|---|---|---|
| Inicio | 2026-03-21 15:00 | Reutiliza el ejemplo oficial; un turno de 8 h cruza calor y noche. |
| Zonas | 12 IDs, uniforme entre 1 y 12 | Incluye 7 y 11 del MVP 1, sin asumir demanda diferenciada. |
| Plataforma | rappi/didi/uber equiprobables | Ejercita el enum oficial; no modela cuota de mercado. |
| Intervalo entre ofertas | U(2,6) min | Produce ofertas mientras hay trabajo, para probar stacking y rechazos. |
| Pickup | U(0.3,3) km | Varía costo y tiempo de desplazamiento vacío. |
| Delivery | U(0.5,6) km | Varía duración y costo del pedido. |
| Base pay | U(35,120) MXN | Da variación económica con la cual ejercer la política, no tarifas reales. |
| Tip | U(0,20) MXN | Ejercita el sumando de propina. Se trata como pago conocido de la simulación. |
| Prep | U(0,8) min | Distingue espera de conducción y afecta factibilidad. |
| Peso | U(0.5,6) kg | Pedidos simples caben en los perfiles iniciales; acumulados pueden no caber. |
| Volumen | U(1,12) L | Ejercita reserva de volumen con varias órdenes. |
| Surge inicial | 1 | Escenario sin recargo hasta recibir un shock. |
| Deadline de decisión | oferta + 5 segundos | Sigue el intervalo típico indicado en el contrato oficial. |
| Lluvia default | mitad del turno, 30 min | Asegura un shock con fases antes/durante/después. |
| Rain time multiplier | 1.25 | Perturbación temporal explícita y fácil de comprobar; no meteorología real. |
| Closure delay | 5 min | Aproximación temporal sencilla sin routing. |

Los valores exactos de rangos, 1.25 y 5 son **supuestos de laboratorio por calibrar**,
no estimaciones defendibles de la realidad. La justificación es ejercitar la mecánica
del experimento, no afirmar que sean representativos u óptimos.

Se heredan **sin cambios** los perfiles del MVP 1 (moto 25 km/h, 15 kg, 50 L, 1.2 MXN/km;
car 20 km/h, 100 kg, 300 L, 3 MXN/km; bike 15 km/h, 8 kg, 25 L, 0.2 MXN/km), el piso de
servicio de 1 minuto, reservation wage 165, zone values 7:+15 y 11:−15, y flagged `{11}`.
Estos también son supuestos provisionales, no una clasificación real de seguridad
ni objetivos de ingresos calibrados. Las reglas oficiales de 22:00, 240/20 min y
90 min durante 12:00–16:00 sí proceden del protocolo; no fueron ajustadas al experimento.

## Tests y verificación

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.benchmark --iterations 5000
.\.venv\Scripts\python.exe validate_format.py --event-log artifacts/mvp2/moto-seed-1234/SmartAgent.jsonl
.\.venv\Scripts\python.exe validate_format.py --event-log artifacts/mvp2/moto-seed-1234/GreedyRateBaseline.jsonl
.\.venv\Scripts\python.exe validate_format.py --endpoint http://localhost:8000/decide
```

El último comando requiere el servidor MVP 1 activo. El validator comprueba formato;
pytest comprueba comportamiento. La medición de decisión excluye escritura JSONL a
disco, que se hace fuera del fast path al finalizar el turno.
Resultados reproducibles: [MVP2_VERIFICATION.md](MVP2_VERIFICATION.md).

## Seeds y alcance pendiente

`config/seeds_tuning.txt` reserva 1–10 para desarrollo; `config/seeds_reporting.txt`
reserva 10001–10010 para evaluación futura. Se comprueba que sean disjuntas y reporting
no se carga automáticamente. La seed 1234 se utiliza como demo de desarrollo.
No se escribió en `results_table_template.csv` ni se presentan resultados held-out.

Para MVP 3 quedan calibración con datos, validación de costos/velocidades/umbrales,
geografía y distancias desde la posición real, valor de dropoff basado en evidencia,
SLA externo, políticas para pendientes inviables y evaluación held-out formal.
No se implementaron frontend, mapas, OSM/OSRM/OSMnx, OR-Tools, datasets, ML, predicción,
LLMs, ElevenLabs, Snowflake, APIs, clima/tráfico real, reposicionamiento avanzado
ni cancelación sofisticada. Tampoco hay una conexión a modelos cuya recuperación
pueda ensayarse: `is_stale` sigue siendo la arquitectura del MVP 1.
