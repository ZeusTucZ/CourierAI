# MVP 4 Demo Guide — Courier AI: Same Shift Comparison

Este documento describe la arquitectura, configuración, ejecución y el guión ensayable de 5 minutos para la demostración interactiva del **MVP 4** (Infosys Delivery Courier Challenge).

---

## 1. Arquitectura de MVP 4

MVP 4 es estrictamente una **capa de visualización y control** desacoplada del motor de decisiones y de la lógica de los agentes:

```text
       Preset / Custom Seed (e.g. 30004)
                     ↓
      Same Canonical Event Stream (Deterministic)
           ↙️                         ↘️
FirstNearbyOrderBaseline          SmartAgent
(Accepts nearest ≤14.99km)   (Dual-speed reservation wage,
                              opportunity cost, deadhead, SLA)
           ↓                         ↓
   Courier State A            Courier State B
   (Isolated State)           (Isolated State)
           ↘️                         ↙️
          Steppable Dual Simulation Engine
                     ↓
        FastAPI REST & WebSocket Layer
                     ↓
        React + Vite + Tailwind Frontend
```

### Garantías Fundamentales
* **Aislamiento Total de Estados:** Las decisiones, rutas, carga vehicular y ganancias de un agente no afectan en ningún momento el estado del otro.
* **Mismo Stream:** Ambos agentes consumen el mismo stream temporal de órdenes, shocks y reloj global. El hash SHA-256 del stream se calcula al inicio y se verifica en la UI.
* **Determinismo Puro:** La misma seed + vehículo + configuración produce siempre las mismas decisiones.
* **Cero Modificaciones:** `SmartAgent` y `FirstNearbyOrderBaseline` no fueron modificados ni retuneados.

---

## 2. Requisitos Previos

* **Python 3.12+** con virtualenv activo (`.venv`).
* **Node.js 18+** y **npm** instalados.

---

## 3. Cómo Arrancar Backend y Frontend

### Paso A: Arrancar Backend (FastAPI + WebSocket)

En una terminal en la raíz del repositorio:
```bash
# Activar entorno virtual
source .venv/bin/activate

# Iniciar servidor Uvicorn en el puerto 8000
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Verifica que responda en: `http://127.0.0.1:8000/simulation/state` o `http://127.0.0.1:8000/health`.

### Paso B: Arrancar Frontend (Vite + React)

En una segunda terminal:
```bash
cd frontend
npm install   # Si no se ha ejecutado previamente
npm run dev
```
Abre en tu navegador:
```text
http://localhost:5173
```

---

## 4. Configuración y Demo Seed Recomendada

### Demo Seed Recomendada: `30004`
* **¿Por qué fue elegida?**
  Fue seleccionada entre semillas no utilizadas para evaluación ni reportes estadísticos. Produce un turno equilibrado y didáctico:
  * Baseline Net: **$956.37 MXN** (11 órdenes completadas, 96.4 km recorridos)
  * SmartAgent Net: **$1,182.59 MXN** (12 órdenes completadas, 76.2 km recorridos)
  * Smart Uplift: **+23.65%** net profit
  * Distancia recorrida por Smart: **-20.9%** (-20.2 km menos de desgaste)
  * 15 discrepancias reales (ACCEPT vs SKIP)
  * 0 retrasos (late deliveries) y 0 violaciones de seguridad
* *Nota Ética:* Esta semilla fue evaluada exclusivamente para demostración visual; **no** se alteró ningún agente para ajustarse a ella.

### Cómo Cambiar de Semilla
1. En el Header de la aplicación web, haz clic en el botón de engranaje **"Configure Shift"**.
2. Modifica:
   * **Simulation Seed:** e.g., `30004` (o cualquier entero).
   * **Shift Duration:** 4h, 8h o 12h (default: 8h).
   * **Courier Vehicle:** `moto`, `bici`, o `auto`.
   * **Start Location Zone:** Zona 1 a 12 (default: 7).
   * **Initial Playback Speed:** 1x, 5x, 10x o 25x.
3. Haz clic en **"Start Simulation"**.

---

## 5. Controles de Reproducción y Velocidad

* **START:** Inicializa la simulación con la configuración seleccionada.
* **PAUSE:** Detiene el avance temporal manteniendo todos los estados en memoria.
* **RESUME:** Reanuda el avance temporal a la velocidad seleccionada.
* **RESET:** Limpia la sesión actual y permite reconfigurar.
* **Velocidades:** Conmutadores para `1x`, `5x`, `10x`, `25x`.
  * *Importante:* La velocidad solo acelera el despacho de eventos de la interfaz visual; los cálculos físicos y económicos permanecen idénticos.

---

## 6. Inyección de Shocks en Vivo

En el panel **"Inject Shocks & Reaction Log"** (abajo a la izquierda):

### A. Lluvia (Rain)
* Aumenta los tiempos de viaje en toda la ciudad.
* **Cómo inyectar:** Selecciona la duración (15, 30, 45 o 60 min) y haz clic en **"Inject Rain"**.
* **Efecto visual:** Aparece un banner ámbar superior. En el Reaction Log verás cómo SmartAgent re-evalúa órdenes activas ante riesgo de SLA, mientras que el Baseline continúa con su política fija.

### B. Tarifa Dinámica (Surge)
* Multiplica las ganancias de órdenes en una zona específica.
* **Cómo inyectar:** Selecciona la zona (1–12), el multiplicador (1.3x, 1.5x o 2.0x), la duración (15–60 min) y haz clic en **"Inject Surge"**.
* **Efecto visual:** La zona seleccionada en el mapa resalta y las nuevas órdenes originadas allí reflejan el multiplicador de surge en el card de orden entrante.

### C. Cierre Vial (Road Closure)
* Bloquea conexiones viales en una zona o avenida principal.
* **Cómo inyectar:** Selecciona la zona afectada y haz clic en **"Close Road"**.
* **Efecto visual:** Registra retrasos adicionales en los cálculos de ruteo.

### D. Retraso en Restaurante (Kitchen Prep Delay)
* Simula demora de preparación en cocina para la orden activa.
* **Cómo inyectar:** Selecciona los minutos de retraso (5, 10 o 15 min) y haz clic en **"Apply Delay"**.
* **Efecto visual:** Incrementa el tiempo de espera en el restaurante.

---

## 7. Escenarios de Seguridad (Safety Demo Scenarios)

En el panel **"Demo Scenarios: Verified Hard Constraints"**:

### Escenario 1: Capacidad Vehicular (`vehicle_capacity`)
* **Acción:** Clic en **"Trigger Capacity Limit"**.
* **Mecanismo:** Inyecta una orden sobredimensionada (e.g. 50 kg para motocicleta con límite de 20 kg).
* **Resultado:** SmartAgent rechaza de inmediato con:
  * `Decision: SKIP`
  * `Binding Constraint: vehicle_capacity`
  * `Reason: Order payload exceeds courier vehicle maximum capacity.`

### Escenario 2: Fin de Turno Inviable (`shift_end_infeasible`)
* **Acción:** Clic en **"Trigger Shift End Limit"**.
* **Mecanismo:** Inyecta una orden con tiempo de entrega estimado que excede el horario límite del turno del repartidor.
* **Resultado:** SmartAgent rechaza con:
  * `Decision: SKIP`
  * `Binding Constraint: shift_end_infeasible`
  * `Reason: Delivery exceeds shift end time.`

### Escenario 3: Zona Restringida Nocturna (`flagged_zone_night`)
* **Acción:** Clic en **"Trigger Night Zone Flag"**.
* **Mecanismo:** Inyecta una orden dirigida a una zona catalogada como de riesgo después de las 21:00.
* **Resultado:** SmartAgent rechaza con:
  * `Decision: SKIP`
  * `Binding Constraint: flagged_zone_night`

---

## 8. Guión de Presentación de 5 Minutos (Rehearsal Script)

### Minuto 0:00 – 1:00 | Introducción y Paridad de Condiciones
1. Abre la pantalla principal en `http://localhost:5173`.
2. Haz clic en **"Start Simulation"** (usando la seed recomendada `30004` a velocidad `5x`).
3. Explica al jurado/evaluador:
   > *"Esta interfaz demuestra el desempeño en tiempo real de dos agentes bajo condiciones idénticas: a la izquierda, el FirstNearbyOrderBaseline (que acepta cualquier pedido cercano sin análisis de rentabilidad); a la derecha, nuestro SmartAgent estratégico. Ambos corren sobre la misma semilla, el mismo stream de eventos (verificado por el Stream Hash), el mismo vehículo y la misma zona inicial."*

### Minuto 1:00 – 2:00 | Visualización de Decisiones y Discrepancias
1. Conforme llegan las primeras órdenes, señala el **Incoming Order Panel**.
2. Observa el primer momento en que ocurra un **DISAGREEMENT** (resaltado en color amarillo/ámbar).
3. Haz clic en el botón **"Inspect Decision"** de SmartAgent.
4. Explica los valores económicos reales:
   > *"Aquí podemos ver exactamente por qué Smart tomó la decisión. No es una caja negra: calculó que el rendimiento proyectado ($68 MXN/h) estaba por debajo del salario de reserva dinámico ($125 MXN/h) y que el costo de oportunidad de quedar atrapado en una zona de baja demanda destruía valor. El Baseline, en cambio, aceptó a ciegas por estar a menos de 15 km."*

### Minuto 2:00 – 3:00 | Inyección de Shock (Lluvia o Surge)
1. En el panel de shocks, selecciona **Lluvia por 30 minutos** y pulsa **"Inject Rain"**.
2. Muestra el banner superior que alerta el inicio de lluvia y el registro de reacciones:
   > *"Al inyectar lluvia, las velocidades de traslado se reducen. SmartAgent recalcula automáticamente sus tiempos de compromiso y rechaza órdenes que pondrían en riesgo los acuerdos de nivel de servicio (SLA), mientras que el Baseline se satura y acumula retrasos."*

### Minuto 3:00 – 4:00 | Demostración de Restricciones Duras de Seguridad
1. En el panel de **Demo Scenarios**, pulsa **"Trigger Capacity Limit"**.
2. Muestra la tarjeta del inspector:
   > *"Aquí forzamos una orden de carga excesiva. Vemos cómo entra en juego la capa de restricciones duras: la orden es rechazada con binding constraint 'vehicle_capacity' con 0 violaciones de seguridad."*
3. Pulsa **"Trigger Shift End Limit"** para demostrar cómo se previene que el repartidor trabaje horas extra no deseadas (`shift_end_infeasible`).

### Minuto 4:00 – 5:00 | Cierre del Turno y Resultados Certificados
1. Cambia la velocidad a **25x** para que el turno de 8 horas llegue a su fin.
2. Al completarse, se desplegará el modal **"SHIFT COMPLETE"**:
   * Ganancias netas de Smart vs Baseline (Smart gana por ~$226 MXN, +23.6%).
   * Distancia recorrida (Smart recorrió ~20 km menos).
3. Haz clic en el botón del Header **"Held-Out Benchmark"**:
   > *"Y lo más importante: esta ventaja no es casualidad de un solo turno. En nuestra evaluación estadística offline congelada sobre 20 semillas held-out independientes, SmartAgent obtuvo una mejora neta promedio del +17.12%, con una tasa de victoria del 85%, un 13.76% menos de distancia recorrida y cero violaciones de seguridad."*

---

## 9. Troubleshooting

* **El backend no arranca:** Asegúrate de tener activado el entorno virtual (`source .venv/bin/activate`) y que el puerto 8000 no esté ocupado por otra instancia (`lsof -i :8000`).
* **El frontend muestra "Connecting to simulation stream...":** Revisa que el backend esté corriendo en `127.0.0.1:8000`. Si usas otra IP o puerto, el proxy de Vite en `frontend/vite.config.ts` redirige las llamadas `/simulation` y los WebSockets `ws://127.0.0.1:8000/simulation/stream`.
* **La simulación no avanza:** Revisa si la simulación está en estado `paused` o si ya terminó (`completed`). Pulsa **"Resume"** o **"Reset"**.
