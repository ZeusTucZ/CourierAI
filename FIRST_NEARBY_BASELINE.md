# FirstNearbyOrderBaseline — reemplazo del baseline principal

FirstNearbyOrderBaseline represents a novice courier who accepts the first feasible order offered as long as its total trip distance is within a historically-derived "nearby" threshold.

**Limitación de evidencia de esta entrega:** no hay distancias históricas repartidor→pickup. Por tanto, la descripción ideal anterior no se puede acreditar para distance_total. El P75 propuesto procede de una aproximación del perfil, no de pares históricos completos. No se inventaron pickups ni se utilizó held-out para calcularlo.

## Política

Reutiliza evaluate_constraints y build_work_plan para flagged_zone_night, mandatory_break, heat_rule, shift_end_infeasible y vehicle_capacity. Si es factible, ACCEPT cuando distance_pickup_km + distance_delivery_km <= max_distance_km; SKIP en otro caso. Cada oferta se decide al llegar, sin esperar alternativas.
No utiliza pago, tips, surge, MXN/h, salario de reserva, zone value ni predicción para decidir. Economics no se calcula en su fast path; el simulator sigue contabilizando ingresos y costos reales de la simulación. La precedencia de seguridad se conserva. SKIP por distancia usa binding_constraint=null porque no existe un enum oficial de distancia; su motivo textual es explícito.
El simulador conserva su gate FIFO de SLA/capacidad/tiempo y puede permitir pedidos con trabajo pendiente. No se modifica el simulador. En el runner, solo para este baseline, se desactivan acciones estratégicas (incluida cancelación económica); Smart recibe su política congelada original. El baseline espera cuando está idle. Los shocks y las restricciones físicas existentes siguen aplicándose.

## Umbral y provenance

P75 PROPUESTO, pendiente de autorización: **14.990869288 km**.
Fuente: Frozen calibrated profile: empirical delivery training + uniform synthetic pickup. Perfil: calibrated-b902d8308110. sample_size=31654 observaciones de delivery; observed_total_sample_size=0.
Transformación: P75 of independent empirical delivery + Uniform(pickup.low,pickup.high); analytic mixture CDF, 60 bisections, no RNG/seeds.
La aproximación combina la distribución empírica delivery con pickup Uniform(0.3,3) km, independientes. Se obtiene el cuantil de la CDF de esa mezcla por bisección, sin seeds ni muestras Monte Carlo. No se modificó el calibrated profile. La distancia delivery es haversine; el recargo espacial de posición del simulador no entra al cálculo del cuantil y sí entra al total cotizado usado al decidir.

## Ejecución y reproducción

No ejecutar run_tuning para este cambio: ese comando busca parámetros Smart. Esta comparación carga exclusivamente final_strategy_config.json y no lo reescribe.

```bash
# Solo si se autoriza explícitamente la aproximación:
python -m scripts.prepare_nearby_baseline --allow-profile-proxy
python -m scripts.compare_nearby_baseline --mode tuning
python -m scripts.run_heldout_evaluation
python -m scripts.report_nearby_baseline
```

El runner exige verificación de tuning con el mismo baseline y freeze antes de held-out. Usa las mismas seeds, fechas, vehículo, duración y streams anteriores. Verifica igualdad completa de estados/decisiones/metrics Smart, excluyendo latencia. Los resultados antiguos no se sobrescriben: las nuevas salidas son evaluation/tuning_nearby_results y evaluation/heldout_nearby_results.
GreedyRateBaseline permanece como implementación y referencia secundaria histórica, no como baseline principal del nuevo comando held-out. Los helpers legacy y comandos de MVP 2 preservan compatibilidad; run_ablations ahora admite FirstNearby como referencia sin modificar las features Smart.

## Validación

Tests: umbral inferior/igual/superior, las cinco restricciones con prioridad, invariancia ante pago/tip/surge/historia/zone value/salario, determinismo, pares históricos incompletos, CDF exacta del proxy, integración sin acciones estratégicas, streams comunes y replay. Resultado total: ver artifacts/nearby_baseline/regression.log.

## Resultados

**tuning: pendiente.** No se ejecutó una comparación sin definir legítimamente el umbral. Falta autorizar el proxy o aportar registros de training con ambas distancias.

**heldout: pendiente.** No se ejecutó una comparación sin definir legítimamente el umbral. Falta autorizar el proxy o aportar registros de training con ambas distancias.

## Alcance e integridad

Archivos de implementación: app/agents/nearby.py, app/evaluation/runner.py; scripts/prepare_nearby_baseline.py, compare_nearby_baseline.py, run_heldout_evaluation.py, run_ablations.py, report_nearby_baseline.py; tests/agents/test_nearby.py; esta documentación. Configuración independiente en config/first_nearby_baseline.json únicamente cuando el umbral se autorice.
SmartAgent, HistoricalDemandModel, StrategySnapshot, perfil calibrado, política/tuning Smart, simulador, shocks, datos y archivos oficiales no se modifican. Sus hashes de partida están en artifacts/nearby_baseline/protected_before.json; el runner valida su integridad. Esta es una comparación con un baseline distinto sobre held-out previamente utilizado, no nueva evidencia de generalización ni un retuning del Smart.
