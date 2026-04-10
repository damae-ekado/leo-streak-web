import { useState, useEffect } from 'react'
import { previewUrl } from '../api/client'
import './ImageViewer.css'

export default function ImageViewer({ jobId, streaks = [] }) {
  const [loaded, setLoaded] = useState(false)
  const [zoom, setZoom]     = useState(false)
  const [active, setActive] = useState(null) // 강조할 streak_id

  useEffect(() => { setLoaded(false) }, [jobId])

  if (!jobId) return null

  const url = previewUrl(jobId)

  return (
    <div className={`image-viewer card ${zoom ? 'zoom' : ''}`}>
      <div className="image-viewer-header">
        <span className="image-viewer-title">Preview</span>
        <div className="image-viewer-tools">
          <span className="badge badge-teal">{streaks.length} streak{streaks.length !== 1 ? 's' : ''}</span>
          <button className="btn btn-ghost btn-xs" onClick={() => setZoom(z => !z)}>
            {zoom ? '⊟ 축소' : '⊞ 확대'}
          </button>
        </div>
      </div>

      <div className="image-viewer-body">
        {!loaded && (
          <div className="image-viewer-loading">
            <div className="spinner-ring" />
            <span>이미지 로딩 중…</span>
          </div>
        )}
        <img
          src={url}
          alt="FITS preview"
          className="viewer-img"
          style={{ opacity: loaded ? 1 : 0 }}
          onLoad={() => setLoaded(true)}
          onError={() => setLoaded(true)}
        />
      </div>

      {/* streak 목록 */}
      {streaks.length > 0 && (
        <div className="streak-chips">
          {streaks.map((s) => (
            <button
              key={s.streak_id}
              className={`streak-chip ${active === s.streak_id ? 'active' : ''}`}
              onClick={() => setActive(active === s.streak_id ? null : s.streak_id)}
            >
              <span className="chip-id">#{s.streak_id}</span>
              <span className="chip-vel">{s.angular_velocity.toFixed(4)}°/s</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}