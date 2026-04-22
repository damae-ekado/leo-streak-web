import { useState, useEffect, useRef, useCallback } from 'react'
import { previewUrl, calibrate } from '../api/client'
import './ImageViewer.css'

/**
 * ImageViewer
 * props:
 *   jobId    - 서버 job_id
 *   streaks  - streak 배열
 *   binning  - 빈닝 배수
 *   onCalib  - 캘리브레이션 결과 콜백 (params 객체)
 *   cacheKey - 이 값이 바뀌면 이미지를 강제 재요청 (재검출 후 캐시 무효화)
 */
export default function ImageViewer({ jobId, streaks = [], onCalib, binning = 2, cacheKey }) {
  const [loaded,  setLoaded]  = useState(false)
  const [zoom,    setZoom]    = useState(false)
  const [mode,    setMode]    = useState('view')   // 'view' | 'calib'
  const [points,  setPoints]  = useState([])       // [{x,y}, ...]
  const [calibing, setCalib]  = useState(false)
  const [imgSize, setImgSize] = useState({ nw: 1, nh: 1 })
  const imgRef  = useRef()

  // jobId나 cacheKey가 바뀌면 상태 초기화
  useEffect(() => {
    setLoaded(false)
    setPoints([])
    setMode('view')
  }, [jobId, cacheKey])

  if (!jobId) return null

  // cacheKey를 쿼리스트링에 붙여 브라우저 캐시 무효화
  const url = `${previewUrl(jobId, binning)}${cacheKey ? `&t=${cacheKey}` : ''}`

  // ── 이미지 클릭 → 픽셀 좌표 변환 ────────────────────────────
  const handleImgClick = useCallback((e) => {
    if (mode !== 'calib') return
    const rect = imgRef.current.getBoundingClientRect()
    const px = Math.round((e.clientX - rect.left) * imgSize.nw / rect.width)
    const py = Math.round((e.clientY - rect.top)  * imgSize.nh / rect.height)
    setPoints(prev => prev.length >= 2 ? [{ x: px, y: py }] : [...prev, { x: px, y: py }])
  }, [mode, imgSize])

  // ── 캘리브레이션 실행 ────────────────────────────────────────
  const runCalib = async () => {
    if (points.length < 2) return
    setCalib(true)
    try {
      const [p1, p2] = points
      const { data } = await calibrate(jobId, p1.x, p1.y, p2.x, p2.y, binning)
      onCalib?.(data)
      setMode('view')
      setPoints([])
    } catch (e) {
      alert(e.response?.data?.detail || '캘리브레이션 실패')
    } finally { setCalib(false) }
  }

  // ── 점 display 위치 계산 ─────────────────────────────────────
  const dotPos = (p) => {
    if (!imgRef.current) return {}
    const rect = imgRef.current.getBoundingClientRect()
    return {
      left: p.x * rect.width  / imgSize.nw,
      top:  p.y * rect.height / imgSize.nh,
    }
  }

  return (
    <div className={`image-viewer card ${zoom ? 'zoom' : ''}`}>
      <div className="image-viewer-header">
        <span className="image-viewer-title">Preview</span>
        <div className="image-viewer-tools">
          <span className="badge badge-teal">
            {streaks.length} streak{streaks.length !== 1 ? 's' : ''}
          </span>

          {mode === 'view' ? (
            <>
              {onCalib && (
                <button className="btn btn-ghost btn-xs"
                  onClick={() => { setMode('calib'); setPoints([]) }}>
                  ✛ 캘리브레이션
                </button>
              )}
              <button className="btn btn-ghost btn-xs"
                onClick={() => setZoom(z => !z)}>
                {zoom ? '⊟ 축소' : '⊞ 확대'}
              </button>
            </>
          ) : (
            <>
              <span className="calib-hint">
                {points.length === 0 && '① streak 시작점 클릭'}
                {points.length === 1 && '② streak 끝점 클릭'}
                {points.length === 2 && '확인 또는 다시 클릭'}
              </span>
              <button className="btn btn-primary btn-xs"
                disabled={points.length < 2 || calibing} onClick={runCalib}>
                {calibing ? '계산 중…' : '✓ 확인'}
              </button>
              <button className="btn btn-ghost btn-xs"
                onClick={() => { setMode('view'); setPoints([]) }}>취소</button>
            </>
          )}
        </div>
      </div>

      {/* 이미지 + 오버레이 */}
      <div className={`image-viewer-body ${mode === 'calib' ? 'calib-mode' : ''}`}>
        {!loaded && (
          <div className="image-viewer-loading">
            <div className="spinner-ring" />
            <span>이미지 로딩 중…</span>
          </div>
        )}
        <img
          ref={imgRef}
          src={url}
          alt="FITS preview"
          className="viewer-img"
          style={{ opacity: loaded ? 1 : 0 }}
          onLoad={e => {
            setLoaded(true)
            setImgSize({ nw: e.target.naturalWidth, nh: e.target.naturalHeight })
          }}
          onError={() => setLoaded(true)}
          onClick={handleImgClick}
          draggable={false}
        />

        {/* 캘리브레이션 점 */}
        {mode === 'calib' && loaded && points.map((p, i) => (
          <div key={i}
            className={`calib-dot ${i === 0 ? 'start' : 'end'}`}
            style={dotPos(p)}>
            <span className="calib-dot-label">{i === 0 ? 'S' : 'E'}</span>
          </div>
        ))}

        {/* 두 점 연결선 */}
        {mode === 'calib' && loaded && points.length === 2 && imgRef.current && (() => {
          const rect = imgRef.current.getBoundingClientRect()
          const sx = rect.width  / imgSize.nw
          const sy = rect.height / imgSize.nh
          return (
            <svg style={{ position:'absolute', inset:0, width:'100%', height:'100%', pointerEvents:'none' }}>
              <line
                x1={points[0].x * sx} y1={points[0].y * sy}
                x2={points[1].x * sx} y2={points[1].y * sy}
                stroke="rgba(0,212,170,.8)" strokeWidth="1.5" strokeDasharray="6 3"
              />
            </svg>
          )
        })()}
      </div>

      {/* streak 칩 */}
      {streaks.length > 0 && (
        <div className="streak-chips">
          {streaks.map(s => (
            <div key={s.streak_id} className="streak-chip">
              <span className="chip-id">#{s.streak_id}</span>
              <span className="chip-vel">{s.angular_velocity.toFixed(4)}°/s</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}