# Reporte de Evaluación: FirstNearbyOrderBaseline vs SmartAgent

**Fecha de evaluación:** 12 de septiembre de 2026  
**Protocolo:** Evaluación ciega sobre conjunto nuevo de held-out seeds (20 turnos).  
**Condición de ejecución:** Evaluación estricta sin tuning, sin ajuste de hiperparámetros, sin filtrado selectivo y bajo condiciones idénticas de simulación.

---

## 1. Declaración de Integridad y Protocolo de Evaluación

1. **Agentes evaluados:**
   - **`FirstNearbyOrderBaseline`**: Baseline myópico de proximidad. Acepta el primer pedido factible cuya distancia total (pickup + delivery) sea menor o igual al umbral derivado históricamente. No utiliza tarifas, tips, surge, predicción histórica, zone values, opportunity cost, batching avanzado ni reposicionamiento.
   - **`SmartAgent`**: Agente estratégico congelado en producción (`artifacts/final_strategy_config.json`). Utiliza el modelo de optimización económica (salario de reserva 125 MXN/h, compensación por zone values, costo de oportunidad, inserción en ruta con SLAs dinámicos y reposicionamiento).
2. **Inmutabilidad:** Ningún parámetro, peso, umbral, dataset ni lógica de decisión de los agentes fue alterado o retuneado.
3. **Condiciones idénticas por seed:**
   - Turno de 8 horas (15:00 a 23:00).
   - Vehículo: `moto` (costo operativo: 1.20 MXN/km).
   - Zona inicial: Zona 7.
   - Perfil de simulación: `calibrated-b902d8308110`.
   - Mismo stream de órdenes y eventos de choque (`stream_sha256` idéntico para ambos agentes en cada turno).
   - Mismas restricciones físicas y de seguridad (`flagged_zone_night`, `mandatory_break`, `heat_rule`, `shift_end_infeasible`, `vehicle_capacity`).

---

## 2. Configuración de Seeds y Umbrales

### Seeds Utilizadas
Se utilizó un conjunto **completamente nuevo** de **20 seeds held-out**:
```text
[20001, 20002, 20003, 20004, 20005, 20006, 20007, 20008, 20009, 20010,
 20011, 20012, 20013, 20014, 20015, 20016, 20017, 20018, 20019, 20020]
```
- **Separación estricta:**
  - Tuning seeds históricas: `[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]` (Solapamiento: 0).
  - Held-out previo de MVP 3: `[10001, 10002, ..., 10010]` (Solapamiento: 0).
  - Cero filtración o inspección previa.

### Umbral del Baseline
- **Umbral de distancia máxima:** `14.990869288 km`
- **Origen:** Percentil 75 (P75) obtenido de la mezcla analítica del perfil empírico calibrado (distribución empírica de delivery + uniforme synthetic pickup), calculado por bisección analítica en 60 pasos (`config/first_nearby_baseline.json`).

---

## 3. Comparación por Seed

La siguiente tabla resume los resultados para cada una de las 20 seeds evaluadas:

| Seed | Baseline Net (MXN) | Smart Net (MXN) | Diferencia Absoluta (MXN) | Mejora (%) | Ganador | Pedidos Comp. (B/S) | Distancia km (B/S) | Tardías (B/S) | Violaciones Seg. (B/S) |
|:---:|---:|---:|---:|---:|:---:|:---:|:---:|:---:|:---:|
| **20001** | 1,059.45 | 1,193.16 | +133.71 | +12.62% | **Smart** | 12 / 11 | 87.08 / 84.69 | 1 / 1 | 0 / 0 |
| **20002** | 848.67 | 1,183.89 | +335.22 | +39.50% | **Smart** | 12 / 12 | 95.92 / 71.25 | 0 / 0 | 0 / 0 |
| **20003** | 784.72 | 1,048.00 | +263.27 | +33.55% | **Smart** | 11 / 11 | 87.60 / 88.93 | 1 / 1 | 0 / 0 |
| **20004** | 957.85 | 1,142.85 | +185.00 | +19.31% | **Smart** | 11 / 11 | 89.58 / 90.19 | 1 / 1 | 0 / 0 |
| **20005** | 942.43 | 1,145.05 | +202.62 | +21.50% | **Smart** | 11 / 13 | 93.13 / 93.50 | 0 / 0 | 0 / 0 |
| **20006** | 976.62 | 1,024.61 | +47.99 | +4.91% | **Smart** | 11 / 11 | 94.84 / 75.55 | 1 / 1 | 0 / 0 |
| **20007** | 1,016.79 | 1,004.95 | -11.84 | -1.16% | **Baseline** | 13 / 11 | 79.55 / 81.23 | 0 / 1 | 0 / 0 |
| **20008** | 815.41 | 808.41 | -7.00 | -0.86% | **Baseline** | 11 / 9 | 90.37 / 54.50 | 0 / 0 | 0 / 0 |
| **20009** | 932.80 | 1,097.76 | +164.96 | +17.68% | **Smart** | 12 / 12 | 86.80 / 70.76 | 0 / 1 | 0 / 0 |
| **20010** | 903.09 | 1,043.93 | +140.84 | +15.60% | **Smart** | 12 / 10 | 89.93 / 86.90 | 1 / 1 | 0 / 0 |
| **20011** | 995.97 | 1,072.53 | +76.56 | +7.69% | **Smart** | 12 / 11 | 87.51 / 87.72 | 1 / 1 | 0 / 0 |
| **20012** | 833.02 | 1,152.74 | +319.72 | +38.38% | **Smart** | 11 / 11 | 95.49 / 66.40 | 0 / 0 | 0 / 0 |
| **20013** | 848.77 | 1,209.19 | +360.42 | +42.46% | **Smart** | 11 / 13 | 90.83 / 81.37 | 1 / 1 | 0 / 0 |
| **20014** | 753.66 | 1,021.99 | +268.33 | +35.60% | **Smart** | 10 / 11 | 90.09 / 69.27 | 0 / 1 | 0 / 0 |
| **20015** | 1,010.37 | 893.27 | -117.10 | -11.59% | **Baseline** | 13 / 10 | 80.34 / 67.09 | 1 / 0 | 0 / 0 |
| **20016** | 850.39 | 958.75 | +108.36 | +12.74% | **Smart** | 10 / 10 | 86.46 / 77.37 | 1 / 0 | 0 / 0 |
| **20017** | 700.75 | 913.45 | +212.70 | +30.35% | **Smart** | 11 / 10 | 82.66 / 59.35 | 1 / 1 | 0 / 0 |
| **20018** | 941.78 | 1,048.91 | +107.13 | +11.37% | **Smart** | 11 / 11 | 91.98 / 80.94 | 1 / 0 | 0 / 0 |
| **20019** | 901.83 | 943.90 | +42.06 | +4.66% | **Smart** | 13 / 10 | 86.91 / 75.58 | 0 / 1 | 0 / 0 |
| **20020** | 860.13 | 929.10 | +68.97 | +8.02% | **Smart** | 11 / 10 | 91.31 / 71.04 | 1 / 0 | 0 / 0 |

---

## 4. Resumen Agregado

| Métrica | Baseline | SmartAgent | Impacto / Diferencia |
|---|---:|---:|:---:|
| **Ganancia Neta Promedio (MXN)** | 896.73 MXN | **1,041.82 MXN** | **+145.10 MXN** |
| **Ganancia Neta Mediana (MXN)** | 902.46 MXN | **1,045.97 MXN** | **+143.51 MXN** |
| **Mejora Promedio (%)** | — | — | **+17.12%** |
| **Mejora Mediana (%)** | — | — | **+14.17%** |
| **Tasa de Victorias (Win Rate)** | 15.0% (3/20) | **85.0% (17/20)** | **Smart +70.0 pp** |
| **Tasa de Empates** | — | — | 0.0% |
| **Pedidos Completados (Media)** | 11.45 | 10.90 | -0.55 pedidos |
| **Distancia Recorrida (Media km)** | 88.92 km | 76.68 km | **-12.24 km (-13.76%)** |
| **Entregas Tardías (Media)** | 0.60 | 0.60 | Igual (0.00) |
| **Violaciones de Seguridad (Total)** | **0** | **0** | **0 (Cumplimiento 100%)** |
| **Rendimiento por km (Media MXN/km)** | 10.15 MXN/km | **13.72 MXN/km** | **+3.57 MXN/km (+35.2%)** |
| **Rendimiento por hora (Media MXN/h)** | 112.09 MXN/h | **130.23 MXN/h** | **+18.14 MXN/h (+16.2%)** |

> [!NOTE]
> **Hallazgo Clave:** SmartAgent logra **145.10 MXN más de ingreso neto por turno (+17.12%)** recorriendo **12.24 km menos por turno (-13.8%)**. Esto se traduce en una eficiencia económica notablemente superior: **13.72 MXN/km frente a 10.15 MXN/km (+35.2%)**.

---

## 5. Diferencia de Decisiones y Análisis de Divergencia

Sobre un total de **2,401 ofertas** evaluadas en los 20 turnos:
- **Decisiones idénticas:** 2,106 (**87.71%**)
- **Desacuerdos (Disagreements):** 295 (**12.29%**)

### Clasificación de Desacuerdos
1. **Baseline ACCEPT / Smart SKIP: 153 ocasiones (51.86% de los desacuerdos)**
   - Ocurre principalmente cuando el pedido es cercano (distancia <= 14.99 km), pero su pago neto por hora proyectado es inferior al salario de reserva (125 MXN/h), o cuando la inserción comprometería los SLAs de pedidos activos.
   - **Impacto posterior:** Muy positivo para Smart. Al rechazar viajes mal pagados o marginales, Smart preserva disponibilidad para órdenes más lucrativas que llegan poco después y ahorra costos de combustible.
2. **Baseline SKIP / Smart ACCEPT: 142 ocasiones (48.14% de los desacuerdos)**
   - Ocurre cuando Smart se encuentra libre (o cuenta con capacidad de batching de alto valor) y la oferta ofrece una tarifa ajustada >= 125 MXN/h, mientras que el Baseline se encuentra ocupado realizando un viaje largo y poco rentable que aceptó previamente (y el gate FIFO de simulación lo rechaza por falta de disponibilidad).
   - **Impacto posterior:** Smart captura viajes de alta rentabilidad que el Baseline pierde por encontrarse saturado en entregas de bajo rendimiento.

---

## 6. Comportamiento del Baseline (`FirstNearbyOrderBaseline`)

El análisis confirma que el baseline opera de forma balanceada y realista, sin aceptar todo ni rechazar todo:
- **Tasa de aceptación del baseline:** **9.54%** (229 pedidos aceptados de 2,401 ofertas).
- **Tasa de rechazo (skip rate):** **90.46%** (2,172 pedidos rechazados).
- **Desglose de motivos de rechazo del baseline:**
  - **Por umbral de distancia (> 14.99 km):** **24.24%** (582 ofertas).
  - **Por restricciones duras de seguridad:** **15.79%** (379 ofertas: 206 mandatory break, 139 shift end infeasible, 32 flagged zone night, 2 vehicle capacity).
  - **Por saturación en el gate del simulador (repartidor ocupado):** **50.44%** (1,211 ofertas).
- **Distribución de distancias de viajes aceptados por el Baseline:**
  - **Media:** 7.766 km
  - **P50 (Mediana):** 7.011 km
  - **P75:** 10.623 km
  - **P95:** 14.060 km
  - **Máxima observada:** 14.987 km (estrictamente inferior al límite de 14.991 km).

---

## 7. 5 Ejemplos Detallados de Decisiones Divergentes

### Ejemplo 1: Rechazo de Pedido Ineficiente por Tarifa Baja
- **Seed:** 20001 | **Order ID:** `ORD-00028`
- **Baseline:** `ACCEPT` (distancia 14.504 km <= 14.991 km).
- **Smart:** `SKIP`
- **Binding constraint:** `reservation_wage`
- **Smart Reason:** `"Skipped: adjusted rate MXN 45.47/hr is below reservation_wage MXN 125.00/hr, including dropoff zone value."`
- **Economía del pedido:** Gross Pay: 57.06 MXN | Costo Op: 18.15 MXN | Net Pay: 38.91 MXN | Tarifa: 45.47 MXN/h vs Salario de Reserva: 125.00 MXN/h | Distancia: 14.504 km.
- **Señales:** Zone dropoff value: 0.0 MXN/h | Opportunity cost: 0.0 MXN | Stacking time: 0.0 min.
- **Impacto posterior:** El Baseline se comprometió en un viaje de 14.5 km que le pagó solo 38.91 MXN netos (45.47 MXN/h, perdiendo más de 50 minutos). Smart rechazó la orden y un minuto después (`ORD-00029`) aceptó una orden corta de 5.43 km que pagó 106.83 MXN netos (267.26 MXN/h). **Mejora directa y contundente para Smart.**

### Ejemplo 2: Captura de Oportunidad de Alta Rentabilidad
- **Seed:** 20001 | **Order ID:** `ORD-00005`
- **Baseline:** `SKIP` (rechazado por saturación del simulador, ocupado en ORD-00002).
- **Smart:** `ACCEPT`
- **Binding constraint:** `None`
- **Smart Reason:** `"Accepted: adjusted rate MXN 130.47/hr meets or exceeds reservation_wage MXN 125.00/hr, including dropoff zone value."`
- **Economía del pedido:** Gross Pay: 113.22 MXN | Costo Op: 12.78 MXN | Net Pay: 100.43 MXN | Tarifa: 130.47 MXN/h.
- **Impacto posterior:** Smart venía de rechazar `ORD-00002` (tarifa insuficiente de 87.31 MXN/h). Al estar disponible, Smart capturó este pedido ganando 100.43 MXN netos, mientras el Baseline continuaba atorado en la orden de 87 MXN/h.

### Ejemplo 3: Aceptación Inteligente de Viaje Corto y Rápido
- **Seed:** 20002 | **Order ID:** `ORD-00037`
- **Baseline:** `SKIP` (ocupado en ORD-00036 de 12.36 km y 63.92 MXN/h).
- **Smart:** `ACCEPT`
- **Binding constraint:** `None`
- **Smart Reason:** `"Accepted: adjusted rate MXN 181.59/hr meets or exceeds reservation_wage MXN 125.00/hr, including dropoff zone value."`
- **Economía del pedido:** Gross Pay: 103.49 MXN | Costo Op: 2.62 MXN | Net Pay: 100.86 MXN | Tarifa: 181.59 MXN/h | Distancia: 2.187 km.
- **Impacto posterior:** Smart acumuló 100.86 MXN netos con solo 2.19 km de recorrido y 2.62 MXN de costo. El Baseline gastó 14.83 MXN en combustible para ganar la mitad en `ORD-00036`.

### Ejemplo 4: Protección de Compromisos Activos y SLA
- **Seed:** 20001 | **Order ID:** `ORD-00024`
- **Baseline:** `ACCEPT` (distancia 4.688 km <= 14.991 km).
- **Smart:** `SKIP`
- **Binding constraint:** `reservation_wage` (bloqueo por SLA / disponibilidad)
- **Smart Reason:** `"Skipped: configured SLA or active-commitment limit prevents a feasible insertion; repositioning also reserves availability."`
- **Economía:** Tarifa bruta atractiva (177.67 MXN/h), pero con stacking time de 10.02 min que ponía en riesgo el SLA de la entrega en curso.
- **Impacto posterior:** Smart evitó entregas tardías y preservó la ventana de servicio. Baseline aceptó y posteriormente acumuló demoras.

### Ejemplo 5: Caso Donde la Selectividad de Smart Perjudicó el Resultado
- **Seed:** 20015 | **Order ID:** `ORD-00024`
- **Baseline:** `ACCEPT` (distancia 6.825 km <= 14.991 km).
- **Smart:** `SKIP`
- **Binding constraint:** `reservation_wage`
- **Smart Reason:** `"Skipped: adjusted rate MXN 120.66/hr is below reservation_wage MXN 125.00/hr, including dropoff zone value."`
- **Economía:** Tarifa ajustada: 120.66 MXN/h vs Salario de reserva: 125.00 MXN/h.
- **Impacto posterior:** La oferta pagaba 120.66 MXN/h, apenas 4.34 MXN/h por debajo del umbral de reserva. En este turno particular, la demanda subsecuente se enfrió y no llegaron pedidos mejores. Smart quedó ocioso (165 min ociosos en el turno vs 63 min del Baseline), completando 10 pedidos frente a 13 del Baseline. **El Baseline ganó esta seed (1,010.37 vs 893.27 MXN).** Este ejemplo ilustra el riesgo inherente del salario de reserva cuando el mercado sufre un shock de baja demanda.

---

## 8. Verificación de Determinismo

Se repitió la ejecución completa de 3 seeds independientes (`20001`, `20002`, `20003`).

| Seed | Stream SHA-256 Idéntico | Eventos Lógicos Idénticos | Ganancia Neta Idéntica | Estado |
|:---:|:---:|:---:|:---:|:---:|
| **20001** | `fbe53207e2b1a5...` | Sí (Exacto) | B: 1,059.45 / S: 1,193.16 | **PASS** |
| **20002** | `254e9cd1d3adb7...` | Sí (Exacto) | B: 848.67 / S: 1,183.89 | **PASS** |
| **20003** | `e17ffc4e61ffe9...` | Sí (Exacto) | B: 784.72 / S: 1,048.00 | **PASS** |

Se verificó que `logical(replay.log.events) == logical(original.log.events)`, garantizando determinismo estricto e invariancia ante latencias del sistema.

---

## 9. Auditoría de Seguridad

- **Total violaciones de seguridad en Baseline:** **0**
- **Total violaciones de seguridad en SmartAgent:** **0**
- **Estado de la auditoría de seguridad:** **PASS** (100% de los turnos cumplieron todas las restricciones de seguridad: sin entregas en zonas rojas nocturnas, descansos obligatorios cumplidos, regla de calor respetada y capacidad del vehículo preservada).

---

## 10. Limitaciones de la Comparación

1. **Umbral derivado por aproximación:** El umbral de distancia del baseline (`14.990869 km`) se deriva del percentil 75 del perfil calibrado mediante una mezcla de delivery empírico y pickup sintético, debido a la ausencia de pares históricos reales repartidor-pickup en los datos públicos crudos.
2. **Exposición sintética de demanda:** Aunque las distribuciones de distancias y tiempos provienen de datos públicos (Zomato y Order History), la tasa global de llegada de ofertas (15 pedidos/h) y el costo operativo por km (1.20 MXN/km en moto) son supuestos calibrados en el simulador.
3. **Rigidez del salario de reserva fijo:** En turnos con demanda inesperadamente baja (e.g. Seed 20015), un salario de reserva fijo de 125 MXN/h rechaza ofertas marginalmente rentables (120 MXN/h) que habrían aportado ingreso en periodos muertos.

---

## 11. Conclusión y Confirmación de No-Tuning

- **SmartAgent supera a FirstNearbyOrderBaseline** con un **85.0% de win rate** y una **mejora media de +17.12% en ganancias netas** (+145.10 MXN por turno de 8h), logrando un incremento del **+35.2% en rendimiento por kilómetro recorrido**.
- **Confirmación explícita:** Ningún agente fue modificado, reentrenado ni ajustado para esta evaluación. Los resultados reflejan el desempeño genuino de ambos agentes en condiciones de igualdad estricta.
