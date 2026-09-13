export const money = (value: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'MXN', currencyDisplay: 'narrowSymbol', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)
export const time = (stamp?: string) => stamp ? stamp.slice(11, 19) : '—'
export const formatReason = (reason: string) => reason.replace(/\b\d+\.\d+\b/g, value => Number(value).toFixed(2))
export function difference(smart: number, baseline: number) {
  const delta = smart - baseline
  return { delta, percentage: baseline > 0 ? delta / baseline * 100 : null }
}
export const safety = new Set(['flagged_zone_night', 'mandatory_break', 'heat_rule', 'shift_end_infeasible', 'vehicle_capacity'])
