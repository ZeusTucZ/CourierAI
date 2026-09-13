import React, { useState, useEffect, useRef } from 'react';
import { SimpleHeader } from './components/SimpleHeader';
import { IndependentCourierMap } from './components/IndependentCourierMap';
import { OrdersFeed } from './components/OrdersFeed';
import { DecisionInspectorModal } from './components/DecisionInspectorModal';
import { SimpleShiftCompleteModal } from './components/SimpleShiftCompleteModal';
import { ValidatedHistoricalModal } from './components/ValidatedHistoricalModal';
import type { SimulationState, TimelineEventItem, DecisionInspectorData, HistoricalEvaluationData } from './types';

export const App: React.FC = () => {
  const [state, setState] = useState<SimulationState | null>(null);
  const [events, setEvents] = useState<TimelineEventItem[]>([]);
  const [inspectorData, setInspectorData] = useState<DecisionInspectorData | null>(null);
  const [historicalData, setHistoricalData] = useState<HistoricalEvaluationData | null>(null);

  const [isHistoricalOpen, setIsHistoricalOpen] = useState<boolean>(false);
  const [isCompleteOpen, setIsCompleteOpen] = useState<boolean>(false);

  const wsRef = useRef<WebSocket | null>(null);
  const previousStatusRef = useRef<string>('idle');

  // Initial Data Fetching
  useEffect(() => {
    fetch('/simulation/state')
      .then((res) => res.json())
      .then((data) => setState(data))
      .catch((err) => console.error('Error fetching state:', err));

    fetch('/simulation/events')
      .then((res) => res.json())
      .then((data) => setEvents(data))
      .catch((err) => console.error('Error fetching events:', err));

    fetch('/simulation/historical')
      .then((res) => res.json())
      .then((data) => setHistoricalData(data))
      .catch((err) => console.error('Error fetching historical:', err));
  }, []);

  // WebSocket Live Updates Connection
  useEffect(() => {
    let ws: WebSocket;
    let reconnectTimeout: any;

    const connectWebSocket = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/simulation/stream`;

      ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'state_update') {
            const newState = msg.state as SimulationState;
            setState(newState);

            if (previousStatusRef.current === 'running' && newState.status === 'completed') {
              setIsCompleteOpen(true);
            }
            previousStatusRef.current = newState.status;
          } else if (msg.type === 'new_event') {
            setEvents((prev) => [msg.event, ...prev]);
          } else if (msg.type === 'reset') {
            setEvents([]);
            setIsCompleteOpen(false);
          }
        } catch (e) {
          console.error('Error parsing WS message:', e);
        }
      };

      ws.onclose = () => {
        reconnectTimeout = setTimeout(connectWebSocket, 1500);
      };

      ws.onerror = (err) => {
        console.warn('WS fallback to polling:', err);
      };
    };

    connectWebSocket();

    return () => {
      if (ws) ws.close();
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, []);

  // Polling Fallback (1.5s)
  useEffect(() => {
    const interval = setInterval(() => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        fetch('/simulation/state')
          .then((res) => res.json())
          .then((data) => setState(data))
          .catch(() => {});
      }
    }, 1500);

    return () => clearInterval(interval);
  }, []);

  const refreshEvents = () => {
    fetch('/simulation/events')
      .then((res) => res.json())
      .then((data) => setEvents(data))
      .catch(() => {});
  };

  // User Actions
  const handleStart = async () => {
    const res = await fetch('/simulation/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ seed: 30004, speed: 5 }),
    });
    const data = await res.json();
    setState(data);
    refreshEvents();
  };

  const handlePause = async () => {
    const res = await fetch('/simulation/pause', { method: 'POST' });
    const data = await res.json();
    setState(data);
  };

  const handleResume = async () => {
    const res = await fetch('/simulation/resume', { method: 'POST' });
    const data = await res.json();
    setState(data);
  };

  const handleReset = async () => {
    const res = await fetch('/simulation/reset', { method: 'POST' });
    const data = await res.json();
    setState(data);
    setEvents([]);
    setIsCompleteOpen(false);
  };

  const handleSpeedChange = async (speed: 1 | 5 | 10 | 25) => {
    const res = await fetch('/simulation/speed', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ speed }),
    });
    const data = await res.json();
    setState(data);
  };

  const handleInjectShock = async (params: any) => {
    await fetch('/simulation/shock', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    refreshEvents();
  };

  const handleFetchDecisionInspector = async (orderId: string): Promise<DecisionInspectorData | null> => {
    try {
      const res = await fetch(`/simulation/decisions/${orderId}`);
      if (res.ok) {
        return await res.json();
      }
    } catch (e) {
      console.error('Error fetching decision detail:', e);
    }
    return null;
  };

  const handleOpenInspectorModal = async (orderId: string) => {
    const data = await handleFetchDecisionInspector(orderId);
    if (data) {
      setInspectorData(data);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans">
      {/* 1. Header (Simple, clean, prominent earnings) */}
      <SimpleHeader
        state={state}
        onStart={handleStart}
        onPause={handlePause}
        onResume={handleResume}
        onReset={handleReset}
        onSpeedChange={handleSpeedChange}
        onInjectShock={handleInjectShock}
        onOpenBenchmark={() => setIsHistoricalOpen(true)}
      />

      {/* 2. Main 3-Column Work Area */}
      <main className="flex-1 max-w-[1700px] w-full mx-auto p-4 sm:p-6">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
          {/* Column 1 (Left 4 cols): Simple Baseline */}
          <div className="lg:col-span-4">
            <IndependentCourierMap
              agentType="baseline"
              title="Simple Baseline"
              subtitle="First Nearby Order"
              agent={state?.baseline || null}
              incomingOrder={state?.incoming_order || null}
              currentShock={state?.current_shock || null}
              simTime={state?.sim_time || '15:00'}
            />
          </div>

          {/* Column 2 (Center 4 cols): Courier AI (Smart Agent) */}
          <div className="lg:col-span-4">
            <IndependentCourierMap
              agentType="smart"
              title="Courier AI"
              subtitle="Smart Agent"
              agent={state?.smart || null}
              incomingOrder={state?.incoming_order || null}
              currentShock={state?.current_shock || null}
              simTime={state?.sim_time || '15:00'}
              onInspectOrder={handleOpenInspectorModal}
            />
          </div>

          {/* Column 3 (Right 4 cols): Orders & Decisions Feed */}
          <div className="lg:col-span-4">
            <OrdersFeed
              events={events}
              onFetchDecisionInspector={handleFetchDecisionInspector}
            />
          </div>
        </div>
      </main>

      {/* Modals */}
      <DecisionInspectorModal
        data={inspectorData}
        onClose={() => setInspectorData(null)}
      />

      <ValidatedHistoricalModal
        isOpen={isHistoricalOpen}
        onClose={() => setIsHistoricalOpen(false)}
        data={historicalData}
      />

      <SimpleShiftCompleteModal
        isOpen={isCompleteOpen}
        state={state}
        onReset={handleReset}
        onClose={() => setIsCompleteOpen(false)}
      />
    </div>
  );
};

export default App;
