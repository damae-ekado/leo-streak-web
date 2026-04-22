import { useState } from 'react'
import './ParamPanel.css'

const FIELDS = [
  { key: 'brightness_min',        label: 'Brightness Min',     min: 0,    max: 255,  step: 1,    desc: '배경 차분 후 최소 밝기' },
  { key: 'brightness_max',        label: 'Brightness Max',     min: 0,    max: 255,  step: 1,    desc: '최대 밝기 (별 포화 제거)' },
  { key: 'star_thresh',           label: 'Star Thresh',        min: 1,    max: 50,   step: 0.5,  desc: 'sep 별 검출 임계값 (낮을수록 더 많이 마스킹)' },
  { key: 'min_length_frac',       label: 'Min Length Frac',    min: 0.01, max: 0.5,  step: 0.01, desc: '최소 streak 길이 (대각선 비율)' },
  { key: 'max_satellite_streaks', label: 'Max Streaks',        min: 1,    max: 20,   step: 1,    desc: '한 이미지 최대 검출 수' },
  { key: 'min_fill',              label: 'Min Fill',           min: 0.01, max: 1,    step: 0.01, desc: '선 위 밝은 픽셀 비율 하한' },
  { key: 'min_brightness',        label: 'Min Brightness',     min: 1,    max: 50,   step: 1,    desc: '"밝다"고 볼 최소 픽셀값' },
  { key: 'binning',               label: 'Binning',            min: 1,    max: 8,    step: 1,    desc: '다운샘플 배수 (클수록 빠름)' },
  // 분류기 모드
  { key: 'conf_thresh',           label: 'Conf Threshold',     min: 0.5,  max: 1,    step: 0.01, desc: '분류기 확신도 임계값 (DBSCAN 모드)' },
  { key: 'dbscan_eps',            label: 'DBSCAN ε',           min: 1,    max: 30,   step: 1,    desc: 'DBSCAN 클러스터 반경 (px)' },
  { key: 'dbscan_min_pts',        label: 'DBSCAN MinPts',      min: 3,    max: 50,   step: 1,    desc: 'DBSCAN 최소 픽셀 수' },
  { key: 'linearity_thresh',      label: 'Linearity Thresh',   min: 0.01, max: 1,    step: 0.01, desc: 'SVD 선형성 임계값 (낮을수록 엄격)' },
]

const DEFAULTS = {
  brightness_min: 40, brightness_max: 80, star_thresh: 15.0,
  min_length_frac: 0.02, max_satellite_streaks: 4,
  min_fill: 0.05, min_brightness: 4, binning: 2,
  conf_thresh: 0.95, dbscan_eps: 8, dbscan_min_pts: 10, linearity_thresh: 0.15,
}

export default function ParamPanel({ params, onChange, onRedetect, busy, calibResult }) {
  const [open, setOpen]     = useState(false)
  const [tooltip, setTooltip] = useState(null)

  const current = { ...DEFAULTS, ...params }

  const handleChange = (key, val) => {
    onChange({ ...current, [key]: Number(val) })
  }

  const applyCalib = () => {
    if (!calibResult) return
    onChange({ ...current, ...calibResult })
  }

  return (
    <div className="param-panel card">
      {/* 헤더 */}
      <div className="param-panel-header" onClick={() => setOpen(o => !o)}>
        <div className="param-panel-title">
          <span>파라미터 조정</span>
          {calibResult && <span className="badge badge-amber">캘리브레이션 결과 대기 중</span>}
        </div>
        <span className="param-toggle">{open ? '▲' : '▼'}</span>
      </div>

      {open && (
        <div className="param-body">
          {/* 캘리브레이션 결과 적용 버튼 */}
          {calibResult && (
            <div className="calib-apply-bar">
              <span className="calib-apply-desc">
                캘리브레이션 결과 — brightness {calibResult.brightness_min}~{calibResult.brightness_max},
                length {calibResult.min_length_frac?.toFixed(3)}~{calibResult.max_length_frac?.toFixed(3)}
              </span>
              <button className="btn btn-primary btn-xs" onClick={applyCalib}>적용</button>
            </div>
          )}

          {/* 슬라이더 그리드 */}
          <div className="param-grid">
            {FIELDS.map(f => (
              <div
                key={f.key}
                className="param-row"
                onMouseEnter={() => setTooltip(f.key)}
                onMouseLeave={() => setTooltip(null)}
              >
                <div className="param-row-top">
                  <label className="param-label">{f.label}</label>
                  <input
                    className="param-number"
                    type="number"
                    min={f.min} max={f.max} step={f.step}
                    value={current[f.key] ?? f.min}
                    onChange={e => handleChange(f.key, e.target.value)}
                  />
                </div>
                <input
                  type="range"
                  className="param-slider"
                  min={f.min} max={f.max} step={f.step}
                  value={current[f.key] ?? f.min}
                  onChange={e => handleChange(f.key, e.target.value)}
                />
                {tooltip === f.key && (
                  <div className="param-tooltip">{f.desc}</div>
                )}
              </div>
            ))}
          </div>

          {/* 액션 */}
          <div className="param-actions">
            <button className="btn btn-ghost btn-xs"
              onClick={() => onChange({ ...DEFAULTS })}>
              기본값 복원
            </button>
            <button className="btn btn-primary"
              disabled={busy} onClick={onRedetect}>
              {busy ? '검출 중…' : '이 파라미터로 재검출'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}