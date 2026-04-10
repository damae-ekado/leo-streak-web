import './ResultCard.css'

export default function ResultCard({ result }) {
  if (!result) return null

  const { filename, exposure_time, streaks, has_wcs } = result

  return (
    <div className="result-card card fade-up">
      <div className="result-card-header">
        <div>
          <div className="result-filename mono">{filename}</div>
          <div className="result-meta">
            <span className="badge badge-teal">{streaks.length} streak{streaks.length !== 1 ? 's' : ''}</span>
            {has_wcs && <span className="badge badge-blue">WCS</span>}
            <span className="result-exptime mono">EXPTIME {exposure_time}s</span>
          </div>
        </div>
      </div>

      {streaks.length === 0 ? (
        <div className="result-empty">검출된 streak 없음</div>
      ) : (
        <div className="streak-list">
          {streaks.map((s) => (
            <StreakRow key={s.streak_id} streak={s} />
          ))}
        </div>
      )}
    </div>
  )
}

function StreakRow({ streak: s }) {
  return (
    <div className="streak-row">
      <div className="streak-row-id">#{s.streak_id}</div>

      <div className="streak-row-grid">
        <DataItem label="시작점 (px)" value={`${s.start_pixel.x}, ${s.start_pixel.y}`} />
        <DataItem label="끝점 (px)"   value={`${s.end_pixel.x}, ${s.end_pixel.y}`} />
        <DataItem label="길이 (px)"   value={s.length_pixel.toFixed(1)} />
        <DataItem label="각속도"      value={`${s.angular_velocity.toFixed(6)}°/s`} accent />
        <DataItem label="시작 RA/Dec" value={`${s.start_sky.ra.toFixed(5)}°  ${s.start_sky.dec.toFixed(5)}°`} />
        <DataItem label="끝 RA/Dec"   value={`${s.end_sky.ra.toFixed(5)}°  ${s.end_sky.dec.toFixed(5)}°`} />
        <DataItem label="중심 RA/Dec" value={`${s.mid_sky.ra.toFixed(5)}°  ${s.mid_sky.dec.toFixed(5)}°`} />
        <DataItem label="각거리"      value={`${s.angular_length_deg.toFixed(6)}°`} />
        <DataItem label="관측 시각"   value={s.timestamp} span2 />
        <DataItem label="중심 시각"   value={s.t_center}  span2 />
      </div>
    </div>
  )
}

function DataItem({ label, value, accent, span2 }) {
  return (
    <div className={`data-item ${span2 ? 'span2' : ''}`}>
      <div className="data-label">{label}</div>
      <div className={`data-value mono ${accent ? 'accent' : ''}`}>{value}</div>
    </div>
  )
}