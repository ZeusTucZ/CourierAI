import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { AgentPanel } from '../components/AgentPanel'
import { OrdersFeed, OrderDecisionCard, ShockCard } from '../components/OrdersFeed'
import { Header } from '../components/Header'
import { ShiftCompleteModal } from '../components/ShiftCompleteModal'
import { DecisionBadge } from '../components/DecisionExplanation'
import { order, agent, state, shock, decision } from './fixtures'
import { difference } from '../format'

vi.mock('../components/CourierMap', () => ({ CourierMap: ({ agent }: { agent: string }) => <div role="img" aria-label={`${agent} map`}/> }))
const zones = new Map([[7, { zone_id: 7, name: 'Tecnológico', latitude: 25.65, longitude: -100.289 }], [1, { zone_id: 1, name: 'Centro', latitude: 25.67, longitude: -100.31 }]])

describe('Demo presentation uses recorded values', () => {
  it('renders independent baseline and smart maps with the same arriving order', () => {
    render(<><AgentPanel agent="baseline" state={agent} order={order} simTime={state.sim_time} evaluating={false} revision={0}/><AgentPanel agent="smart" state={agent} order={order} simTime={state.sim_time} evaluating={false} revision={0}/></>)
    expect(screen.getAllByRole('img')).toHaveLength(2)
    expect(screen.getByRole('heading', { name: 'Simple Baseline' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Courier AI' })).toBeInTheDocument()
    expect(screen.getAllByText('ORD-001')).toHaveLength(2)
    expect(screen.getByText(/✓ ACCEPT/)).toBeInTheDocument()
    expect(screen.getByText(/− SKIP/)).toBeInTheDocument()
  })
  it('renders orders newest first, differing decisions and backend explanation', () => {
    render(<OrdersFeed orders={[order, { ...order, order_id: 'ORD-002', sim_time: '2026-03-21T18:02:00' }]} shocks={[]} zones={zones} evaluating={null}/>)
    expect(screen.getAllByRole('article')[0]).toHaveTextContent('ORD-002')
    expect(screen.getAllByText('↔ Different decision')).toHaveLength(2)
    fireEvent.click(screen.getAllByText('Smart explanation')[0])
    expect(screen.getAllByText(decision.reason)[0].closest('details')).toHaveAttribute('open')
    expect(screen.getAllByText('$125.00/hr')[0]).toBeVisible()
  })
  it('does not invent missing economics for a safety refusal', () => {
    render(<OrderDecisionCard zones={zones} order={{ ...order, decisions: { ...order.decisions, smart: { ...decision, economics: undefined, binding_constraint: 'vehicle_capacity', reason: 'Vehicle capacity exceeded.' } } }}/>)
    expect(screen.getByText(/SKIP · SAFETY/)).toBeInTheDocument()
    expect(screen.queryByText('Net pay')).not.toBeInTheDocument()
  })
  it('shows evaluating instead of exposing the outcome during the visual delay', () => {
    render(<DecisionBadge decision={decision} evaluating/>)
    expect(screen.getByText('Evaluating…')).toBeInTheDocument()
    expect(screen.queryByText(/SKIP/)).not.toBeInTheDocument()
  })
  it('updates earnings without replacing the map panel', () => {
    const view = render(<AgentPanel agent="smart" state={agent} revision={0} evaluating={false}/>)
    expect(screen.getByText('$438.20')).toBeInTheDocument()
    view.rerender(<AgentPanel agent="smart" state={{ ...agent, net_earnings: 527.1 }} revision={0} evaluating={false}/>)
    expect(screen.getByText('$527.10')).toBeInTheDocument()
  })
  it('shows the active order over each courier map', () => {
    render(<><AgentPanel agent="baseline" state={{ ...agent, current_order: 'ORD-ACTIVE-1' }} revision={0} evaluating={false}/><AgentPanel agent="smart" state={{ ...agent, current_order: 'ORD-ACTIVE-2' }} revision={0} evaluating={false}/></>)
    expect(screen.getAllByText('Orden actual:')).toHaveLength(2)
    expect(screen.getByText('ORD-ACTIVE-1')).toBeInTheDocument()
    expect(screen.getByText('ORD-ACTIVE-2')).toBeInTheDocument()
  })
  it('opens an independent order history for each model', () => {
    const acceptedOrder = { ...order, order_id: 'ORD-ACCEPTED', decisions: { ...order.decisions, smart: { ...decision, order_id: 'ORD-ACCEPTED', decision: 'ACCEPT' as const } } }
    render(<AgentPanel agent="smart" state={agent} order={order} orders={[order, acceptedOrder]} zones={zones} revision={0} evaluating={false}/>)
    fireEvent.click(screen.getByRole('button', { name: /Ver historial/ }))
    const dialog = screen.getByRole('dialog')
    const history = within(dialog)
    expect(dialog).toHaveAccessibleName('Courier AI')
    expect(screen.getByLabelText('2 pedidos recibidos')).toBeInTheDocument()
    expect(screen.getByLabelText('1 pedidos aceptados')).toBeInTheDocument()
    expect(screen.getByLabelText('1 pedidos omitidos')).toBeInTheDocument()
    fireEvent.click(history.getByRole('button', { name: /Aceptados/ }))
    expect(history.getByText('ORD-ACCEPTED')).toBeInTheDocument()
    expect(history.queryByText('ORD-001')).not.toBeInTheDocument()
    fireEvent.click(history.getByRole('button', { name: /Omitidos/ }))
    expect(history.getByText('ORD-001')).toBeInTheDocument()
    expect(history.queryByText('ORD-ACCEPTED')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar historial' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it('shows actual closure detour', () => {
    render(<ShockCard shock={shock}/>)
    expect(screen.getByText('ϟ Road closure')).toBeInTheDocument()
    expect(screen.getByText(/0.17 km \/ 24 sec/)).toBeInTheDocument()
  })
  it('shows a truthful winner and final comparison', () => {
    render(<ShiftCompleteModal state={{ ...state, status: 'completed' }} close={vi.fn()} reset={vi.fn()}/>)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Smart wins this shift.')).toBeInTheDocument()
    expect(screen.getByText('+$88.90')).toBeInTheDocument()
  })
  it('does not force a Smart win when the baseline earns more', () => {
    render(<ShiftCompleteModal state={{ ...state, agents: { baseline: agent, smart: { ...agent, net_earnings: 100 } } }} close={vi.fn()} reset={vi.fn()}/>)
    expect(screen.getByText('Baseline wins this shift.')).toBeInTheDocument()
    expect(difference(100, 0).percentage).toBeNull()
  })
  it('retains amounts when backend disconnects and exposes controls', () => {
    const control = vi.fn()
    render(<Header state={state} seed={42} setSeed={vi.fn()} start={vi.fn()} control={control} inject={vi.fn()} connected={false} busy={false}/>)
    expect(screen.getByText('● Backend disconnected')).toBeInTheDocument()
    expect(screen.getByText('$527.10')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Ⅱ Pause'))
    expect(control).toHaveBeenCalledWith('pause')
  })
})
