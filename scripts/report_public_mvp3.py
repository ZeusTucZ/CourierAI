"""Assemble reviewable MVP3 evidence from generated artifacts, without evaluation."""
import json
import re
import subprocess
from hashlib import sha256
from pathlib import Path

OUT=Path('artifacts')


def read(name): return json.loads((OUT/name).read_text())


def main():
    audit=read('data_audit_report.json'); split=read('data_split_manifest.json')
    manifest=read('calibration_manifest.json'); tuning=read('tuning_report.json')
    held=json.loads(Path('evaluation/heldout_results/results.json').read_text())
    ablations=json.loads(Path('evaluation/ablation_results/ablations.json').read_text())
    latency=read('benchmark_mvp3.json'); freeze=read('final_strategy_config.json')
    routing=read('solomon_routing_profile.json'); validation=read('public_data_validation.json')
    official=['decision_response_schema.json','event_log_schema.json','event_log_example.jsonl',
              'evaluation_protocol.md','results_table_template.csv','validate_format.py']
    protected={p:sha256(Path(p).read_bytes()).hexdigest() for p in official}
    for p,digest in protected.items():
        assert sha256(subprocess.check_output(['git','show','HEAD:'+p])).hexdigest()==digest, p
    (OUT/'official_file_integrity.json').write_text(json.dumps(protected,indent=2)+'\n')
    from app.evaluation.freeze import load_frozen
    from app.evaluation.runner import fingerprint
    models=load_frozen(OUT/'final_strategy_config.json')
    assert held['frozen_config_sha256']==fingerprint(*models)
    assert validation['frozen_sha256_unchanged']==sha256((OUT/'final_strategy_config.json').read_bytes()).hexdigest()
    totals={a:{k:sum(r[a][k] for r in held['rows']) for k in ('orders_completed','late_deliveries','orders_cancelled','distance_traveled_km','safety_violations')} for a in ('baseline','smart')}
    text=['# MVP 3 — datos públicos y calibración','',
          'Trabajo completado dentro de MVP 3. No se modificaron los contratos, schemas, validator ni otros archivos oficiales de Infosys. No se implementó MVP 4.', '',
          '## Datos, archivos y filas', '',
          'Los dos ZIP de Kaggle ya existían al iniciar la tarea. Se reutilizaron sin sobrescribir y se verificó CRC e igualdad de cada CSV con su miembro del ZIP. No fue necesaria autenticación. La fecha original de descarga y la correspondencia remota exacta de esos bytes no están certificadas; las fuentes declaradas y SHA256 están en `artifacts/data_sources.json`.', '',
          '- Zomato: `data/raw/zomato/Zomato Dataset.csv`, `dataset.zip`; fuente: https://www.kaggle.com/datasets/saurabhbadole/zomato-delivery-operations-analytics-dataset',
          '- Order History: `data/raw/order_history/order_history_kaggle_data.csv`, `dataset.zip`; fuente: https://www.kaggle.com/datasets/sujalsuthar/food-delivery-order-history-data',
          '- Solomon: clon nuevo de https://github.com/ML4VRP/ML4VRP2026 en `data/raw/solomon/ML4VRP2026`; commit en `data_sources.json`; inventario completo en `data_audit_report.json`.', '',
          '| Dataset | Filas raw | Entrenamiento | Holdout temporal | Timestamp desconocido |',
          '|---|---:|---:|---:|---:|']
    for name in ('zomato','order_history'):
        s=split[name];text.append(f"| {name} | {audit['datasets'][name]['rows']} | {s['training_rows']} | {s['heldout_rows']} | {s['unknown_timestamp_excluded']} |")
    text+=['', 'Los tamaños utilizables son por campo: distancia/transiciones Zomato 31,654; duración Zomato 34,747; preparación Order History 16,993. No todas las filas tienen todos los atributos.',
           'Solomon: '+', '.join(r['instance'] for r in routing)+'. Cada instancia aporta 100 clientes (600 total), además del depot auditado. C101, C201, RC101 y RC201 no están en el subconjunto clonado; se eligió el primer representante disponible de cada familia, del mismo repositorio.', '',
           '## Calidad, mappings y limpieza', '',
           '- Cero duplicados exactos en ambos CSV. Zomato: 4,071 filas fuera del envelope geográfico plausible de India; coordenadas sin reparar y distancias/zonas nulas en esas filas. No se convirtieron coordenadas a Monterrey.',
           '- Zomato: 1,731 timestamps ausentes excluidos del fit temporal. Se recuperaron 4,068 horas con formato de fracción de día de Excel; el valor 1 corresponde a la medianoche siguiente.',
           '- Zomato: faltan 616 valores de clima, 601 de tráfico y 993 de múltiples entregas. No se imputan categorías.',
           '- Order History: faltan 295 KPT y 168 esperas de rider; 190 filas no Delivered no se usan para ajustar servicio completado. Subtotal, Total, descuentos y compensaciones al restaurante nunca se usan como pago del repartidor.',
           '- Auditoría previa a limpieza: `artifacts/data_audit_report.json`; columnas, tipos, nulos, duplicados, rangos, negativos, IQR outliers y anomalías. Resumen: `artifacts/DATA_AUDIT.md`.',
           '- Mappings direct/derived/missing/not applicable: `artifacts/field_mapping.csv`, incluyendo sidecars logísticos. Limpieza reproducible, razones, cantidades y before/after: `artifacts/data_cleaning_report.json`.',
           '- Normalizados de entrenamiento y holdout: `data/processed/*_train.jsonl`, `*_heldout.jsonl`. Contexto separado: clima, tráfico, vehículo, múltiples, estado y rider wait. No se exportaron identificadores de clientes ni montos de facturas a estos sidecars.', '',
           '## Perfil y manifest', '',
           '`artifacts/calibrated_profile.json` usa el adapter/fitter de MVP 3 y el mismo generador que SyntheticProfile. `artifacts/calibration_manifest.json` contiene status, fuente, sample_size, transformación, distribución y limitaciones por parámetro.', '',
           '| Parámetro | Estado | n |', '|---|---|---:|']
    for p in manifest['parameters']:text.append(f"| {p['parameter']} | {p['status']} | {p['sample_size']} |")
    text+=['', 'La tasa fallback es 15 ofertas/h; el n del manifest de esa tasa cuenta registros de entrada al fitter, no exposición ni una muestra válida para estimar la tasa. Demanda por hora permanece plana; `demand_structure.json` conserva frecuencias por hora observadas sin llamarlas tasas.',
           'Distancia calibrada = haversine, no km de ruta real. La preparación viene de KPT de Order History; Zomato order-to-pickup combina espera/viaje/preparación y solo se conserva como contexto. Duración histórica, vehículo y múltiples entregas son descriptivos: ejecución deriva el tiempo de distancias/velocidad; vehículo fijo por turno y batching depende de decisiones. No se fuerzan eventos concurrentes a partir de multiple_deliveries.',
           'Pagos, tips, pickup distance, peso/volumen, costos, salario de reserva y penalizaciones siguen siendo synthetic_fallback/assumed. Frecuencia de cancelaciones no es penalización monetaria. Solomon genera `solomon_routing_profile.json` con demanda/capacidad, ventanas y estructura espacial en unidades propias; nunca se mezcla con duraciones, kg, ingresos ni horas reales.', '',
           '## HistoricalDemandModel, zonas y no leakage', '',
           '`artifacts/historical_model.json`: agregados inmutables zone × hour, solo entrenamiento Zomato. Predice distancia y duración esperadas con sample_count; expected_orders_per_hour es null por exposición desconocida. expected_gross_pay, expected_net_pay y expected_net_mxn_per_hour son null, economics_available=false. Los consumidores aplican ajuste económico neutro, sin inventar ingresos históricos.',
           'Zonas `zone_1`…`zone_12`: grid de cuantiles 3×4 ajustado exclusivamente con pickups de entrenamiento. `abstract_zones.json` conserva límites; `demand_structure.json` contiene densidad pickup/dropoff, probabilidades de transición, frecuencias por hora y atractivo relativo por conteo. El grid métrico del simulador sigue siendo supuesto; no conserva distancias viales entre estas zonas.',
           f"Cutoffs: Zomato {split['zomato']['cutoff']}; Order History {split['order_history']['cutoff']}. Particiones posteriores se guardan aparte y no participan en fit ni tuning.",
           'Pruebas: dos simulaciones idénticas hasta t con pedidos/shocks futuros diferentes producen igual prediction/decision en t; interfaz sin stream/shocks/RNG; invariancia al RNG global; modificar holdout posterior al cutoff no cambia el fit; seeds disjuntas; hash congelado detecta adulteraciones; SyntheticProfile y CalibratedProfile repiten el mismo stream con la misma seed.', '',
           '## SLA', '',
           '`sla_calibration.json`: P90 nearest-rank por distancia, mínimo 30 muestras/bin, entrenado antes de evaluación. Fórmula integrada: max(pickup estimado + preparación + delivery estimado, P90 histórico del bin). Fuera de soporte se conserva SLA sintético.',
           'Bins ≤3, ≤6, ≤10 y ≤100 km: P90 de 30, 33, 34 y 43 minutos. Clima/tráfico/vehículo se conservan y tráfico/vehículo tienen diagnósticos por subgrupo (`sla_subgroup_diagnostics.json`); el P90 los marginaliza porque el contrato no lleva categoría observada de tráfico. Velocidad por vehículo y shocks visibles afectan el tiempo físico estimado. No se afirma calibración causal de tráfico ni de vehículo.',
           'Cobertura temporal reservada: '+', '.join(f"{x['heldout_coverage']*100:.2f}% (n={x['n']})" for x in validation['sla_heldout_coverage'])+'. No se reajustó con estos resultados.', '',
           '## Tuning y freeze', '',
           'Seeds 1–10 únicamente; búsqueda predeclarada del salario de reserva base {125,165,205}. Objetivo: máximo neto medio Smart; empate favorece menor salario. Restricciones oficiales y SLA no se optimizan.', '',
           '| Salario supuesto | Baseline neto medio | Smart neto medio |','|---:|---:|---:|']
    for r in tuning['outcomes']:text.append(f"| {r['base_reservation_wage']:.0f} | {r['mean_baseline_net']:.2f} | {r['mean_smart_net']:.2f} |")
    text+=['', 'Elegido: 125 MXN/h. Es selección de un supuesto económico dentro de la simulación, no salario observado.',
           f"`artifacts/final_strategy_config.json`: {freeze['strategy_version']}, perfil {freeze['profile_version']}, timestamp {freeze['timestamp']}, hash {freeze['hash']}. Contiene perfil, modelo y parámetros completos. Heldout verifica el hash y carga ese payload sin actualizarlo.", '',
           '## Held-out: baseline vs Smart', '',
           '10 shifts de 8 horas, moto; seeds 10001–10010. Mismas ofertas/shocks por pareja; sin tuning sobre estas seeds.', '',
           '| Métrica | GreedyRateBaseline | SmartAgent |', '|---|---:|---:|',
           f"| Neto medio, MXN/shift | {held['mean_baseline_net']:.2f} | {held['mean_smart_net']:.2f} |"]
    for k,label in [('orders_completed','Pedidos completados (total)'),('late_deliveries','Entregas tardías (total)'),('orders_cancelled','Cancelaciones (total)'),('distance_traveled_km','Distancia km (total)'),('safety_violations','Violaciones de seguridad')]:
        text.append(f"| {label} | {totals['baseline'][k]:.2f} | {totals['smart'][k]:.2f} |")
    text += ['',f"Mejora media por shift: {held['mean_improvement_pct']:.4f}%; mediana: {held['median_improvement_pct']:.2f}%; Smart win rate: {held['smart_win_rate_pct']:.0f}% (2 victorias, 7 empates, 1 derrota). Estado de seguridad: {held['status']}. Cualquier violación no cero hace fallar el runner.",
             'Resultados por seed: `evaluation/heldout_results/results.json`; tabla oficial: `artifacts/results_mvp3.csv`. Estos ingresos son simulados con economics asumidos; no validan rentabilidad real.', '',
             '## Ablations (tuning seeds)', '', '| Variante | mean_net | delta_vs_full | delta_vs_baseline |','|---|---:|---:|---:|']
    for r in ablations:text.append(f"| {r['variant']} | {r['mean_net']:.2f} | {r['delta_vs_full']:.2f} | {r['delta_vs_baseline']:.2f} |")
    text+=['', 'No se ocultó el resultado negativo frente al baseline en tuning. No hay ventaja medida de estos componentes en este escenario. ZoneValue/Reposition/HistoricalPrediction no tienen señal económica observada para actuar; ImprovedBatching no altera el neto en estas seeds. No implica que esos componentes sean universalmente equivalentes.', '',
           '## Validación y latencia', '',
           '- Tests MVP 1/2/3 y nuevos tests públicos: 281 passed (2 deprecation warnings de dependencias), `artifacts/tests.log`.',
           '- `/decide` validado contra el validator oficial mediante servidor HTTP local: `artifacts/endpoint_validation.log`.',
           '- Los 20 logs heldout pasan formato y replay determinista completo: `artifacts/replay_validation.json`.',
           '- Raw SHA256 sin cambios; integridad oficial: `artifacts/official_file_integrity.json`; freeze sin cambios: `public_data_validation.json`.', '',
           '| Benchmark (1000 iteraciones) | Mediana ms | P95 ms | Máximo ms | >50 ms |', '|---|---:|---:|---:|---:|']
    for name in ('decide_http_in_process','strategy_update','batch_insertion_3_active'):
        r=latency[name];text.append(f"| {name} | {r['median_ms']:.3f} | {r['p95_ms']:.3f} | {r['max_ms']:.3f} | {r['over_50ms']} |")
    text+=['', 'El benchmark HTTP usa TestClient, no latencia de red. La prueba HTTP local en frío registró round trip de 56 ms; el validator aprobó el formato y la latencia interna declarada, no garantiza un RTT inferior a 50 ms. Se preserva una primera ejecución concurrente con ablations en `evaluation/heldout_concurrent_results`: tuvo un pico de decisión de 56.46 ms y falló formato por latencia. La repetición secuencial usa exactamente la misma configuración congelada, conserva resultados económicos idénticos y pasa los 20 validators. No se borró ni se presenta como PASS la medición concurrente.', '',
           '## Limitaciones y pasos no calibrables automáticamente', '',
           'No faltó autenticación y no se sustituyeron datasets. No hay evidencia suficiente para tasa absoluta/exposición, hourly demand rates, pickup distance, courier payout/costos/salario/penalizaciones, peso o volumen. Permanecen explícitamente supuestos o null; requieren fuentes adicionales para calibrarse. No se mezclaron unidades de Solomon ni facturas de clientes con esa evidencia.',
           'Los CSV Kaggle preexistían; solo su consistencia local ZIP/CSV está verificada. India no se extrapola geográficamente a Monterrey. Las marginales mezclan fuentes para prep y distancia y pierden correlaciones; zonas abstractas no equivalen a una red vial. Heldout seeds prueban nuevas realizaciones del mismo simulador, no transferencia comercial. Tráfico/vehículo no tienen efectos condicionales calibrados en SLA; sus diagnósticos se reportan.', '',
           '## Reproducción', '', 'Python 3.12 usado en esta ejecución; dependencias: `requirements-calibration.txt` y versiones efectivas en `artifacts/calibration_environment.txt`.', '', '```bash',
           'python -m pip install -r requirements-calibration.txt',
           'python -m scripts.prepare_public_data',
           'python -m scripts.run_tuning',
           'python -m scripts.run_heldout_evaluation',
           'python -m scripts.run_ablations',
           'python -m scripts.validate_public_data',
           'python -m scripts.validate_heldout_logs',
           'python -m scripts.benchmark_mvp3 --iterations 1000',
           'python -m pytest -q',
           'python -m scripts.validate_mvp3_endpoint',
           'python -m scripts.report_public_mvp3', '```', '',
           'Ejecutar evaluaciones y benchmark secuencialmente para evitar contaminación por carga. No ejecutar `prepare_mvp3_data`: ese script anterior genera historia sintética y sobrescribe los nombres de artifacts. Artifacts/processed y nuevos raw están ignorados por Git y disponibles localmente. Los dos ZIP/CSV y el gitlink Solomon ya estaban versionados antes de esta tarea: .gitignore no los desindexa y no se alteró el índice. Se regeneran los derivados con los comandos anteriores. No hay deployment ni componentes de MVP 4.']
    report='\n'.join(text)+'\n'
    Path('PUBLIC_DATA_MVP3.md').write_text(report)
    (OUT/'MVP3_PUBLIC_DATA_REPORT.md').write_text(report)
    print('Wrote PUBLIC_DATA_MVP3.md and artifacts/MVP3_PUBLIC_DATA_REPORT.md')


if __name__=='__main__': main()
