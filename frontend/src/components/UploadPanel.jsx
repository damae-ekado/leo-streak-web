import { useState, useRef } from 'react'
import { uploadFits, processFits } from '../api/client'
import './UploadPanel.css'

function makeEntry(file) {
  return { file, phase: 'pending', uploadPct: 0, jobId: null, error: null }
}

export default function UploadPanel({ onResults }) {
  const [entries, setEntries] = useState([])
  const [drag, setDrag]       = useState(false)
  const [apiKey, setApiKey]   = useState('')
  const [running, setRunning] = useState(false)
  const inputRef = useRef()

  const FITS_EXT = ['fits', 'fit', 'fts']

  const addFiles = (fileList) => {
    const valid = Array.from(fileList).filter((f) =>
      FITS_EXT.includes(f.name.split('.').pop().toLowerCase())
    )
    if (!valid.length) return
    setEntries((prev) => {
      const existing = new Set(prev.map((e) => e.file.name))
      const fresh = valid.filter((f) => !existing.has(f.name)).map(makeEntry)
      return [...prev, ...fresh]
    })
  }

  const onDrop = (e) => {
    e.preventDefault(); setDrag(false)
    addFiles(e.dataTransfer.files)
  }

  const removeEntry = (name) =>
    setEntries((prev) => prev.filter((e) => e.file.name !== name))

  const reset = () => setEntries([])

  const patch = (name, updates) =>
    setEntries((prev) =>
      prev.map((e) => (e.file.name === name ? { ...e, ...updates } : e))
    )

  const run = async () => {
    const pending = entries.filter((e) => e.phase === 'pending' || e.phase === 'error')
    if (!pending.length) return
    setRunning(true)
    const results = []
    for (const entry of pending) {
      const name = entry.file.name
      try {
        patch(name, { phase: 'uploading', uploadPct: 0, error: null })
        const { data: up } = await uploadFits(entry.file, (pct) =>
          patch(name, { uploadPct: pct })
        )
        patch(name, { phase: 'processing', jobId: up.job_id })
        const { data: result } = await processFits(up.job_id, null, apiKey || null)
        patch(name, { phase: 'done' })
        results.push(result)
      } catch (err) {
        patch(name, {
          phase: 'error',
          error: err.response?.data?.detail || err.message || '알 수 없는 오류',
        })
      }
    }
    setRunning(false)
    if (results.length) onResults?.(results)
  }

  const pendingCount = entries.filter((e) => e.phase === 'pending' || e.phase === 'error').length
  const doneCount    = entries.filter((e) => e.phase === 'done').length

  return (
    <div className="upload-panel card fade-up">
      <div className="upload-panel-header">
        <h2>FITS 파일 업로드</h2>
        <p>여러 파일을 한꺼번에 올려 streak 를 순차 검출합니다</p>
      </div>

      <div
        className={`dropzone ${drag ? 'drag' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".fits,.fit,.fts"
          multiple
          style={{ display: 'none' }}
          onChange={(e) => addFiles(e.target.files)}
        />
        <div className="dropzone-icon">⊕</div>
        <div className="dropzone-label">파일을 드래그하거나 클릭하여 선택</div>
        <div className="dropzone-hint">.fits  .fit  .fts  · 여러 파일 가능</div>
      </div>

      {entries.length > 0 && (
        <div className="file-list">
          {entries.map((e) => (
            <FileRow
              key={e.file.name}
              entry={e}
              onRemove={() => removeEntry(e.file.name)}
              disabled={running}
            />
          ))}
        </div>
      )}

      <div className="upload-field">
        <label>Astrometry.net API Key (WCS 없는 파일만)</label>
        <input
          type="password"
          placeholder="WCS 헤더가 있으면 비워두세요"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          disabled={running}
        />
      </div>

      {entries.length > 0 && (
        <div className="upload-summary">
          <span className="badge badge-blue">{entries.length}개 파일</span>
          {doneCount > 0 && <span className="badge badge-teal">완료 {doneCount}</span>}
          {entries.some((e) => e.phase === 'error') && (
            <span className="badge badge-red">
              오류 {entries.filter((e) => e.phase === 'error').length}
            </span>
          )}
        </div>
      )}

      <div className="upload-actions">
        {entries.length > 0 && !running && (
          <button className="btn btn-ghost" onClick={reset}>전체 초기화</button>
        )}
        <button
          className="btn btn-primary"
          disabled={!pendingCount || running}
          onClick={run}
        >
          {running ? <><Spinner /> 처리 중…</> : `검출 시작 (${pendingCount}개)`}
        </button>
      </div>
    </div>
  )
}

function FileRow({ entry, onRemove, disabled }) {
  const { file, phase, uploadPct, error } = entry
  const phaseLabel = {
    pending: null, uploading: `업로드 ${uploadPct}%`,
    processing: '🔭 검출 중…', done: null, error: null,
  }[phase]
  return (
    <div className={`file-row ${phase}`}>
      <div className="file-row-main">
        <StatusDot phase={phase} />
        <span className="file-row-name mono">{file.name}</span>
        <span className="file-row-size">{(file.size / 1024 / 1024).toFixed(1)} MB</span>
        {phase === 'done'  && <span className="badge badge-teal" style={{ fontSize: 10 }}>완료</span>}
        {phase === 'error' && <span className="badge badge-red"  style={{ fontSize: 10 }}>오류</span>}
        {(phase === 'pending' || phase === 'error') && !disabled && (
          <button className="btn btn-ghost btn-xs" onClick={onRemove}>✕</button>
        )}
      </div>
      {(phase === 'uploading' || phase === 'processing') && (
        <div className="file-row-progress">
          <div className="progress-bar">
            <div className="progress-fill"
              style={{ width: phase === 'uploading' ? `${uploadPct}%` : '100%' }} />
          </div>
          <span className="progress-label">{phaseLabel}</span>
        </div>
      )}
      {phase === 'error' && error && (
        <div className="file-row-error">⚠ {error}</div>
      )}
    </div>
  )
}

function StatusDot({ phase }) {
  const colors = {
    pending: 'var(--text2)', uploading: 'var(--amber)',
    processing: 'var(--blue)', done: 'var(--teal)', error: 'var(--red)',
  }
  const color = colors[phase]
  return (
    <span style={{
      width: 8, height: 8, borderRadius: '50%', background: color,
      boxShadow: phase === 'done' ? `0 0 6px ${color}` : 'none',
      flexShrink: 0, display: 'inline-block',
    }} />
  )
}

function Spinner() {
  return (
    <span style={{
      display: 'inline-block', width: 14, height: 14,
      border: '2px solid rgba(0,0,0,.3)', borderTopColor: 'var(--bg0)',
      borderRadius: '50%', animation: 'spin .7s linear infinite',
    }} />
  )
}