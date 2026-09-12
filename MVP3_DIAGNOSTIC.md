# MVP3_DIAGNOSTIC — tuning únicamente

Seeds: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]. Configuración congelada y código de estrategia sin cambios; hashes verificados en `artifacts/mvp3_diagnostic/input_integrity.json`. No se abrió ningún archivo ni lista de seeds held-out.

**Causa principal:** 99.918% de decisiones idénticas, señales económicas avanzadas nulas y una sola diferencia causada por el denominador de tiempo comprometido. Smart no supera al baseline en estas tuning seeds: neto medio 1007.69 vs 1013.21 MXN/shift. La diferencia se concentra en seed 3; las otras nueve empatan. No se extrapola este diagnóstico a held-out.

## Decisiones pareadas

1214 ofertas comunes; 1213 decisiones idénticas (99.9176%). Desacuerdos: 1; baseline ACCEPT / Smart SKIP: 1; baseline SKIP / Smart ACCEPT: 0.
Se empareja por seed + order_id. Las políticas pueden llegar con estados distintos al mismo pedido; esa comparación no equivale a un efecto causal aislado de una feature.

| Seed | Ofertas | Idénticas | Baseline net | Smart net | Delta |
|---|---:|---:|---:|---:|---:|
| 1 | 121 | 121 | 950.71 | 950.71 | 0.00 |
| 2 | 129 | 129 | 977.87 | 977.87 | 0.00 |
| 3 | 110 | 109 | 1164.96 | 1109.67 | -55.29 |
| 4 | 115 | 115 | 1051.15 | 1051.15 | 0.00 |
| 5 | 123 | 123 | 725.34 | 725.34 | 0.00 |
| 6 | 112 | 112 | 1021.65 | 1021.65 | 0.00 |
| 7 | 137 | 137 | 1034.15 | 1034.15 | 0.00 |
| 8 | 120 | 120 | 1135.70 | 1135.70 | 0.00 |
| 9 | 112 | 112 | 964.72 | 964.72 | 0.00 |
| 10 | 135 | 135 | 1105.91 | 1105.91 | 0.00 |

## Impacto de cada desacuerdo

La tabla completa `disagreements.csv` contiene estado comparable, razones, tasas, gross realizado por pedido y neto cotizado. Para no atribuirle falsamente a una decisión todo el delta observado, se ejecutó una rama diagnóstica por desacuerdo: idéntica historia Smart hasta ese evento, una sola acción cambiada a la acción baseline si es factible, y después la política Smart original. Impacto = neto Smart original − neto de esa rama. No se fuerzan ACCEPT inseguros. Los efectos no son aditivos porque interactúan con decisiones posteriores; no se usaron para seleccionar parámetros.

| Seed / pedido | Baseline → Smart | Mismo estado | Neto Smart | Neto rama | Efecto elección Smart | Decisiones posteriores distintas |
|---|---|---|---:|---:|---:|---:|
| 3 / ORD-00107 | ACCEPT → SKIP | True | 1109.67 | 1164.96 | -55.29 | 0 |

El único desacuerdo ocurre el 21 de marzo a las 22:27:19, seed 3 / ORD-00107. Ambos tienen el mismo estado y umbral 125. Hay 4.724542 min pendientes de ORD-00095; el pedido nuevo requiere 26.224759 min. Baseline: 55.289140 / 26.224759 × 60 = 126.496810 MXN/h → ACCEPT. Smart: 55.289140 / 30.949301 × 60 = 107.186537 MXN/h → SKIP. Zone value y opportunity cost son exactamente cero. El ACCEPT del baseline completa el pedido; gross 61.49152 menos costo 6.202380 = 55.289140 MXN. La rama Smart con ese único ACCEPT recupera el mismo importe y no cambia ninguna decisión posterior. En este caso, cargar trabajo pendiente en el denominador excluye un pedido rentable y factible; no es un efecto del modelo histórico.

## Utilización de features

| Métrica | Conteo |
|---|---:|
| batching_plan_changed | 0 |
| batching_decision_changed | 0 |
| batching_changed_executed_plan | 0 |
| zone_value_changes_decision | 0 |
| opportunity_changes_decision | 0 |
| history_changes_decision | 0 |
| final_hour_discount_changes_decision | 0 |
| committed_denominator_changes_decision | 1 |
| offers | 1214 |
| with_active_orders | 875 |
| feasible_insertions | 305 |
| feasible_with_active_orders | 22 |
| economic_records | 1065 |
| nonzero_stacking_time | 828 |
| nonzero_zone_value | 0 |
| nonzero_opportunity_cost | 0 |
| strategy_updates | 160 |
| predictions_generated | 1920 |
| predictions_with_economics | 0 |
| reposition_attempts | 509 |
| reposition_eligible | 380 |
| reposition_count | 0 |
| cancellation_checks | 8 |
| cancellations | 0 |
| candidate_count | 6784 |
| unique_alternative_count | 4356 |
| alternative_sla_rejects | 4356 |
| alternative_safety_rejects | 0 |
| alternative_feasible | 0 |
| alternative_sla_existing_miss | 4356 |
| alternative_sla_new_miss | 4267 |
| fifo_wins_strictly | 0 |
| fifo_wins_tie | 0 |
| fifo_only_feasible | 22 |
| accepted_with_active_orders | 19 |
| discounted_wage_offers | 68 |
| discounted_wage_feasible_offers | 0 |

Conteos decisivos: probes contrafactuales locales sobre el mismo estado Smart, mismo instante, mismo candidato y mismas restricciones. Zone value se elimina del snapshot de prueba; opportunity_fraction se neutraliza solo en el probe; HistoricalPrediction usa el updater sin historia al último tick real. No se escribe ningún snapshot/configuración alternativo. El observador reproduce exactamente los logs originales excluyendo latencia.

## Reservation wage vs adjusted rate

Baseline conserva 125 MXN/h; Smart conserva 125 hasta el tick de 22:30 y luego 115. Hay 68 ofertas bajo el descuento, 0 con inserción factible; cambia cero decisiones. Se distingue código activo de efecto decisivo. Tasas disponibles solo cuando las restricciones permiten calcular economics: no se rellenan con cero las ausentes. Las tasas de cada política usan su propio estado/denominador. CSVs incluyen todas las observaciones y cuantiles por ACCEPT, SKIP y candidato factible.

| Agente | Variable (todas) | n | Min | P25 | Mediana | P75 | P90 | Max | Ausentes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | reservation_wage | 1214 | 125.000 | 125.000 | 125.000 | 125.000 | 125.000 | 125.000 | 0 |
| baseline | adjusted_rate | 1065 | 7.304 | 64.269 | 95.574 | 141.950 | 188.238 | 389.839 | 149 |
| baseline | margin_rate_minus_wage | 1065 | -117.696 | -60.731 | -29.426 | 16.950 | 63.238 | 264.839 | 149 |
| smart | reservation_wage | 1214 | 115.000 | 125.000 | 125.000 | 125.000 | 125.000 | 125.000 | 0 |
| smart | adjusted_rate | 1065 | 6.544 | 49.609 | 74.594 | 105.867 | 150.718 | 329.580 | 149 |
| smart | margin_rate_minus_wage | 1065 | -118.456 | -75.391 | -50.406 | -19.133 | 25.718 | 204.580 | 149 |

## Motivos de SKIP

| Agente | Motivo | n | % de sus SKIP |
|---|---|---:|---:|
| baseline | reservation_wage | 721 | 65.19% |
| baseline | SLA/active-commitment/moving gate | 236 | 21.34% |
| baseline | shift_end_infeasible | 106 | 9.58% |
| baseline | mandatory_break | 30 | 2.71% |
| baseline | flagged_zone_night | 13 | 1.18% |
| smart | reservation_wage | 885 | 79.95% |
| smart | shift_end_infeasible | 106 | 9.58% |
| smart | SLA/active-commitment/moving gate | 73 | 6.59% |
| smart | mandatory_break | 30 | 2.71% |
| smart | flagged_zone_night | 13 | 1.17% |

El gate de SLA/compromisos usa el enum público reservation_wage, pero se separó por su razón textual. La diferencia de 163 rechazos etiquetados gate (236 baseline frente a 73 Smart) no son 163 decisiones distintas: en esos pedidos el baseline supera el umbral pero el gate lo bloquea; Smart ya reporta rechazo por tasa comprometida. Los motivos corresponden a la primera restricción reportada, no a un inventario de todas las restricciones simultáneas.

## Reposition: conteo y valor

0 movimientos. `repositions.csv` tiene encabezado y cero filas: no existe un valor neto por movimiento que estimar. No se interpreta net_gain_after_reposition como retorno causal; ese campo del simulador sería el neto total del turno tras costos.
Se observaron 509 consultas, 380 en estado elegible. Sin tasas económicas históricas, gain = −costo de viaje; ningún destino puede superar el umbral positivo de 5 MXN. Detalle y mejor ganancia de cada oportunidad en `reposition_opportunities.csv`.

## Por qué cada ablation empata

| Variante | Cambios de decisión | Rutas propuestas distintas | Rutas ejecutadas distintas | Estados distintos | Delta neto total |
|---|---:|---:|---:|---:|---:|
| SmartFull | 0 | 0 | 0 | 0 | 0.00 |
| SmartNoZoneValue | 0 | 0 | 0 | 0 | 0.00 |
| SmartNoReposition | 0 | 0 | 0 | 0 | 0.00 |
| SmartNoImprovedBatching | 0 | 0 | 0 | 0 | 0.00 |
| SmartNoHistoricalPrediction | 0 | 0 | 0 | 0 | 0.00 |

- **SmartNoZoneValue:** todos los valores económicos zonales usados son cero. Quitarlos no altera adjusted_rate.
- **SmartNoReposition:** SmartFull tampoco realiza movimientos; desactivarlo no elimina ninguna acción, costo ni cambio de posición.
- **SmartNoHistoricalPrediction:** el modelo sí produce estadísticas logísticas, pero no tasas de ingreso ni exposición. Los consumidores monetarios usan cero como ajuste neutro. Las predicciones desaparecen en el snapshot, pero wage, zone value, opportunity cost y decisiones permanecen iguales. El descuento horario del salario de reserva sigue activo porque no depende de historia.
- **SmartNoImprovedBatching:** 875 ofertas llegan con trabajo activo, pero solo 22 admiten inserción y 19 se aceptan. Se evaluaron 6784 candidatos (incluye duplicados FIFO), 4356 alternativas únicas no FIFO: 4356 fallan SLA, 0 restricciones y 0 son factibles. Con trabajo activo, FIFO es el único factible en 22 ofertas, gana estrictamente en 0 y gana por desempate estable en 0. Los incumplimientos SLA afectan a pedidos existentes en 4356 alternativas y al nuevo en 4267 (conteos superpuestos). Esta ablation desactiva la inserción mejorada, no el batching FIFO básico. Ninguna propuesta elegida difiere de FIFO; por eso no cambia ningún plan ni decisión. Los tiempos y distancias son aditivos: la heurística no crea ahorros de ruta geográfica.
- **SmartFull:** referencia sin remover componentes. La igualdad no es una prueba de utilidad: también se compararon decisiones, rutas y estado físico, además de todos los indicadores no relacionados con latencia.

## Clasificación final y límites

La tabla machine-readable principal es `artifacts/mvp3_diagnostic/feature_utilization.csv`: oportunidades, términos/acciones no nulos, cambios locales, impacto medido, clasificación y datos faltantes por componente.

La clasificación siguiente corresponde exclusivamente a estas tuning seeds; los tests de fixtures pueden demostrar capacidades que aquí no se ejercitan. No se optimizó ningún parámetro.

- **Funcionan y cambian decisiones:** el denominador de tiempo comprometido cambia 1 decisión local frente al inmediato (impacto negativo medido). Los gates de seguridad/SLA también operan y bloquean ofertas, pero son compartidos; no son una ventaja diferencial Smart.
- **Funcionan pero no llegan a ser decisivos:** descuento horario activo en 68 ofertas, cero cambios de decisión; cancelación evaluada 8 veces, cero ejecuciones. Mejor inserción cambia 0 planes candidatos y 0 planes ejecutados; cambia 0 decisiones. El modelo histórico ejecuta 160 updates con estadísticas logísticas, que no alimentan una ventaja económica en este diseño.
- **Efectivamente inactivos como señales/acciones:** zone value monetario, opportunity cost monetario y reposition. Se ejecuta código de evaluación, pero los términos son cero y los movimientos no existen. Cancelación se evalúa ocho veces y nunca se ejecuta: código activo, acción no ejercida. El descuento salarial está activo pero no es decisivo; el batching FIFO básico sí se ejecuta (19 ACCEPT con trabajo activo), incluso en SmartNoImprovedBatching.
- **Requieren datos ausentes:** tasas de demanda necesitan horas de exposición; earnings/zone value/opportunity cost/reposition económico necesitan una fuente válida de courier payout y supuestos de costo defendibles. Las distancias/duraciones disponibles no bastan para convertir demanda en MXN/h. No debe usarse el valor de la factura.
- La calibración de SLA y las restricciones se aplican a ambos agentes: no son una ventaja diferencial exclusiva de Smart. Desactivar una feature no elimina esos mecanismos compartidos.

## Reproducción y archivos

`python -m scripts.diagnose_mvp3`

Salida machine-readable: `artifacts/mvp3_diagnostic/summary.json`, `feature_utilization.csv`, `feature_counts.csv`, `decisions.csv`, `disagreements.csv`, `feature_usage_by_decision.csv`, `rate_distributions.csv`, `rate_distributions_raw.csv`, `skip_reasons.csv`, `reposition_opportunities.csv`, `repositions.csv`, `ablations_by_seed.csv`, `per_seed.csv`, `cancellation_checks.json`, `input_integrity.json`. Sin cambios a app/, perfiles, modelo, política congelada ni parámetros.
