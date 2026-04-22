import './ResultCard.css'

// ── 내보내기 유틸 ────────────────────────────────────────────────
function toCSV(result) {
  const cols = [
    'filename','job_id','streak_id','exposure_time',
    'timestamp','t_center',
    'start_px_x','start_px_y','end_px_x','end_px_y','length_pixel',
    'start_ra','start_dec','end_ra','end_dec','mid_ra','mid_dec',
    'angular_length_deg','angular_velocity_deg_s',
  ]
  const rows = result.streaks.map(s => [
    result.filename, result.job_id, s.streak_id, result.exposure_time,
    s.timestamp, s.t_center,
    s.start_pixel.x, s.start_pixel.y, s.end_pixel.x, s.end_pixel.y, s.length_pixel.toFixed(3),
    s.start_sky.ra.toFixed(6), s.start_sky.dec.toFixed(6),
    s.end_sky.ra.toFixed(6),   s.end_sky.dec.toFixed(6),
    s.mid_sky.ra.toFixed(6),   s.mid_sky.dec.toFixed(6),
    s.angular_length_deg.toFixed(6), s.angular_velocity.toFixed(6),
  ])
  return [cols.join(','), ...rows.map(r => r.join(','))].join('\n')
}

function download(content, filename, mime) {
  const blob = new Blob([content], { type: mime })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

function ExportButtons({ result }) {
  if (!result?.streaks?.length) return null
  const stem = result.filename.replace(/\.[^.]+$/, '')
  return (
    <div className="export-row">
      <span className="export-label">내보내기</span>
      <button className="btn btn-ghost btn-xs"
        onClick={() => download(JSON.stringify(result, null, 2), `${stem}.json`, 'application/json')}>
        JSON
      </button>
      <button className="btn btn-ghost btn-xs"
        onClick={() => download(toCSV(result), `${stem}.csv`, 'text/csv')}>
        CSV
      </button>
    </div>
  )
}

// ── 컴포넌트 ─────────────────────────────────────────────────────
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
        <ExportButtons result={result} />
      </div>

      {streaks.length === 0 ? (
        <div className="result-empty">검출된 streak 없음</div>
      ) : (
        <div className="streak-list">
          {streaks.map(s => <StreakRow key={s.streak_id} streak={s} />)}
        </div>
      )}
    </div>
  )
}

// ── 개별 streak 행 ───────────────────────────────────────────────
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

// 여러 결과를 한 번에 내보내는 유틸 (DashboardPage에서 import해서 사용)
export { toCSV, download }