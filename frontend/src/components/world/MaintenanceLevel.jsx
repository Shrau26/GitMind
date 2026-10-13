import { computeMaintenanceStreak } from '../../lib/repoWorld'

export default function MaintenanceLevel({ history, historyLoading }) {
  const streak = computeMaintenanceStreak(history)

  return (
    <div className="detail-panel world-panel">
      <h2 className="panel-title">Maintenance streak</h2>
      {historyLoading ? (
        <p className="panel-note" style={{ margin: 0 }}>Loading history…</p>
      ) : !streak.available ? (
        <p className="panel-note" style={{ margin: 0 }}>Not enough historical data.</p>
      ) : (
        <>
          <p className="world-streak-display">
            🔥 {streak.days} day{streak.days === 1 ? '' : 's'} maintenance streak
          </p>
          <p className="panel-note">
            Based on {streak.snapshots} consecutive real analysis snapshot{streak.snapshots === 1 ? '' : 's'} with a
            non-decreasing health score — computed only from stored history, nothing backfilled.
          </p>
        </>
      )}
    </div>
  )
}
