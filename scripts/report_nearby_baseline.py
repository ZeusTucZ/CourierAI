"""Document the baseline change; report missing evidence instead of invented runs."""
import json
from pathlib import Path

OUT=Path('artifacts/nearby_baseline')


def main():
    configured=Path('config/first_nearby_baseline.json')
    cfg=json.loads((configured if configured.exists() else OUT/'PROPOSED_threshold.json').read_text())
    lines=['# FirstNearbyOrderBaseline — reemplazo del baseline principal','',
        'FirstNearbyOrderBaseline represents a novice courier who accepts the first feasible order offered as long as its total trip distance is within a historically-derived "nearby" threshold.', '',
        '**Limitación de evidencia de esta entrega:** no hay distancias históricas repartidor→pickup. Por tanto, la descripción ideal anterior no se puede acreditar para distance_total. El P75 propuesto procede de una aproximación del perfil, no de pares históricos completos. No se inventaron pickups ni se utilizó held-out para calcularlo.', '',
        '## Política', '',
        'Reutiliza evaluate_constraints y build_work_plan para flagged_zone_night, mandatory_break, heat_rule, shift_end_infeasible y vehicle_capacity. Si es factible, ACCEPT cuando distance_pickup_km + distance_delivery_km <= max_distance_km; SKIP en otro caso. Cada oferta se decide al llegar, sin esperar alternativas.',
        'No utiliza pago, tips, surge, MXN/h, salario de reserva, zone value ni predicción para decidir. Economics no se calcula en su fast path; el simulator sigue contabilizando ingresos y costos reales de la simulación. La precedencia de seguridad se conserva. SKIP por distancia usa binding_constraint=null porque no existe un enum oficial de distancia; su motivo textual es explícito.',
        'El simulador conserva su gate FIFO de SLA/capacidad/tiempo y puede permitir pedidos con trabajo pendiente. No se modifica el simulador. En el runner, solo para este baseline, se desactivan acciones estratégicas (incluida cancelación económica); Smart recibe su política congelada original. El baseline espera cuando está idle. Los shocks y las restricciones físicas existentes siguen aplicándose.', '',
        '## Umbral y provenance', '',
        f"P75 {'configurado' if configured.exists() else 'PROPUESTO, pendiente de autorización'}: **{cfg['max_distance_km']:.9f} km**.",
        f"Fuente: {cfg['source']}. Perfil: {cfg['profile_version']}. sample_size={cfg['sample_size']} observaciones de delivery; observed_total_sample_size={cfg['observed_total_sample_size']}.",
        f"Transformación: {cfg['transformation']}.",
        'La aproximación combina la distribución empírica delivery con pickup Uniform(0.3,3) km, independientes. Se obtiene el cuantil de la CDF de esa mezcla por bisección, sin seeds ni muestras Monte Carlo. No se modificó el calibrated profile. La distancia delivery es haversine; el recargo espacial de posición del simulador no entra al cálculo del cuantil y sí entra al total cotizado usado al decidir.', '',
        '## Ejecución y reproducción', '',
        'No ejecutar run_tuning para este cambio: ese comando busca parámetros Smart. Esta comparación carga exclusivamente final_strategy_config.json y no lo reescribe.', '',
        '```bash', '# Solo si se autoriza explícitamente la aproximación:',
        'python -m scripts.prepare_nearby_baseline --allow-profile-proxy',
        'python -m scripts.compare_nearby_baseline --mode tuning',
        'python -m scripts.run_heldout_evaluation',
        'python -m scripts.report_nearby_baseline', '```', '',
        'El runner exige verificación de tuning con el mismo baseline y freeze antes de held-out. Usa las mismas seeds, fechas, vehículo, duración y streams anteriores. Verifica igualdad completa de estados/decisiones/metrics Smart, excluyendo latencia. Los resultados antiguos no se sobrescriben: las nuevas salidas son evaluation/tuning_nearby_results y evaluation/heldout_nearby_results.',
        'GreedyRateBaseline permanece como implementación y referencia secundaria histórica, no como baseline principal del nuevo comando held-out. Los helpers legacy y comandos de MVP 2 preservan compatibilidad; run_ablations ahora admite FirstNearby como referencia sin modificar las features Smart.', '',
        '## Validación', '',
        'Tests: umbral inferior/igual/superior, las cinco restricciones con prioridad, invariancia ante pago/tip/surge/historia/zone value/salario, determinismo, pares históricos incompletos, CDF exacta del proxy, integración sin acciones estratégicas, streams comunes y replay. Resultado total: ver artifacts/nearby_baseline/regression.log.', '',
        '## Resultados']
    for mode in ('tuning','heldout'):
        path=OUT/f'{mode}_summary.json'
        if not path.exists():
            lines+=['',f'**{mode}: pendiente.** No se ejecutó una comparación sin definir legítimamente el umbral. Falta autorizar el proxy o aportar registros de training con ambas distancias.']
            continue
        r=json.loads(path.read_text())
        lines+=['',f'### {mode}', '',
            f"{r['shifts']} shifts. Baseline neto medio {r['mean_baseline_net']:.2f} MXN; Smart {r['mean_smart_net']:.2f}. Mejora media {r['mean_improvement_pct']:.3f}%; mediana {r['median_improvement_pct']:.3f}%; win rate {r['smart_win_rate_pct']:.1f}%.",
            f"Baseline acepta {r['accepted_pct']:.2f}% de ofertas; SKIP por distancia {r['distance_skip_pct']:.2f}%; restricciones obligatorias {r['hard_constraint_skip_pct']:.2f}%; gate de factibilidad del simulador {r['simulator_gate_skip_pct']:.2f}%. Denominador: todas las ofertas.",
            f"Distancia aceptada: {r['accepted_distance']}.", '',
            '| Métrica total | FirstNearby | Smart |','|---|---:|---:|']
        for key in ('orders_completed','late_deliveries','distance_traveled_km','safety_violations','orders_cancelled','reposition_count'):
            lines.append(f"| {key} | {r['totals']['baseline'][key]:.3f} | {r['totals']['smart'][key]:.3f} |")
        lines+=['',f"Comparación secundaria de neto medio: {r['secondary_means']}.",
            f"Smart idéntico al anterior: {r['smart_identical_to_previous']}; streams idénticos: {r['source_streams_identical_to_previous']}; validación logs: {r['log_validation_status']}; replay: {r['replay_status']}.",
            f"Tabla por seed: artifacts/nearby_baseline/{mode}_comparison.csv. Tres agentes: {mode}_secondary_comparison.csv. Decisiones/razones: {mode}_decisions.csv. Resumen completo: {mode}_summary.json."]
    lines+=['', '## Alcance e integridad', '',
        'Archivos de implementación: app/agents/nearby.py, app/evaluation/runner.py; scripts/prepare_nearby_baseline.py, compare_nearby_baseline.py, run_heldout_evaluation.py, run_ablations.py, report_nearby_baseline.py; tests/agents/test_nearby.py; esta documentación. Configuración independiente en config/first_nearby_baseline.json únicamente cuando el umbral se autorice.',
        'SmartAgent, HistoricalDemandModel, StrategySnapshot, perfil calibrado, política/tuning Smart, simulador, shocks, datos y archivos oficiales no se modifican. Sus hashes de partida están en artifacts/nearby_baseline/protected_before.json; el runner valida su integridad. Esta es una comparación con un baseline distinto sobre held-out previamente utilizado, no nueva evidencia de generalización ni un retuning del Smart.']
    Path('FIRST_NEARBY_BASELINE.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':main()
