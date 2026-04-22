import { useState } from 'react'
import UploadPanel  from '../components/UploadPanel'
import ImageViewer  from '../components/ImageViewer'
import ResultCard   from '../components/ResultCard'
import ParamPanel   from '../components/ParamPanel'
import { processFits } from '../api/client'
import { toCSV, download } from '../components/ResultCard'
import './UploadPage.css'

const LS_JOBS = 'leo_job_ids'

// ── 대시보드 자동 등록 ────────────────────────────────────────────
function syncToDashboard(jobId) {
  try {
    const prev = JSON.parse(localStorage.getItem(LS_JOBS) || '[]')
    if (!prev.includes(jobId)) {
      const next = [...prev, jobId]
      localStorage.setItem(LS_JOBS, JSON.stringify(next))
      // storage 이벤트로 Dashboard가 같은 탭에서도 감지하도록
      window.dispatchEvent(new StorageEvent('storage', {
        key: LS_JOBS,
        newValue: JSON.stringify(next),
      }))
    }
  } catch {}
}

// ── 전체 내보내기 바 ──────────────────────────────────────────────
function BulkExportBar({ results }) {
  if (!results.length) return null
  const totalStreaks = results.reduce((s, r) => s + r.streaks.length, 0)

  const exportJSON = () =>
    download(JSON.stringify(results, null, 2), 'leo_all_results.json', 'application/json')

  const exportCSV = () => {
    const header = toCSV(results[0]).split('\n')[0]
    const rows   = results.flatMap(r => toCSV(r).split('\n').slice(1))
    download([header, ...rows].join('\n'), 'leo_all_results.csv', 'text/csv')
  }

  const exportJobIds = () =>
    download(
      JSON.stringify({ job_ids: results.map(r => r.job_id) }, null, 2),
      'leo_job_ids.json', 'application/json'
    )

  return (
    <div className="bulk-export-bar">
      <div className="bulk-export-info">
        <span className="bulk-export-label">전체 내보내기</span>
        <span className="bulk-export-count">
          {results.length}개 파일 · {totalStreaks}개 streak
        </span>
      </div>
      <div className="bulk-export-btns">
        <button className="btn btn-ghost btn-xs" onClick={exportJSON}
          title="모든 파일 결과를 하나의 JSON으로 저장">↓ JSON</button>
        <button className="btn btn-ghost btn-xs" onClick={exportCSV}
          title="모든 streak을 하나의 CSV 표로 저장">↓ CSV</button>
        <button className="btn btn-ghost btn-xs" onClick={exportJobIds}
          title="job_id 목록 저장 (대시보드에 드롭해서 재사용)">↓ job ID 목록</button>
      </div>
    </div>
  )
}

// ── 메인 페이지 ──────────────────────────────────────────────────
export default function UploadPage() {
  const [results,     setResults]     = useState([])
  const [selected,    setSelected]    = useState(0)
  const [params,      setParams]      = useState({})
  const [calibResult, setCalibResult] = useState(null)
  const [redetecting, setRedetecting] = useState(false)
  // 재검출 시 이미지 캐시 무효화용 타임스탬프
  const [imgStamp,    setImgStamp]    = useState(Date.now())

  // 새 결과 병합 + 대시보드 자동 등록
  const handleResults = (newResults) => {
    setResults(prev => {
      const merged = [...prev]
      newResults.forEach(r => {
        const idx = merged.findIndex(x => x.job_id === r.job_id)
        if (idx >= 0) merged[idx] = r
        else merged.push(r)
      })
      return merged
    })
    // 검출 완료된 job_id를 모두 대시보드에 자동 등록
    newResults.forEach(r => syncToDashboard(r.job_id))
  }

  const current = results[selected] || null

  // 현재 파일 재검출
  const handleRedetect = async () => {
    if (!current) return
    setRedetecting(true)
    try {
      const { data } = await processFits(current.job_id, params, null)
      setResults(prev =>
        prev.map(r => r.job_id === current.job_id
          ? { ...data, job_id: current.job_id } : r)
      )
      setCalibResult(null)
      setImgStamp(Date.now()) // 이미지 캐시 무효화
    } catch (e) {
      alert(e.response?.data?.detail || '재검출 실패')
    } finally { setRedetecting(false) }
  }

  return (
    <div className="page">
      <h1 className="page-title">LEO Streak Detector</h1>
      <p className="page-sub">FITS 이미지에서 저궤도 위성 궤적을 자동 검출합니다</p>

      <div className={`upload-layout ${results.length ? 'has-result' : ''}`}>

        {/* 왼쪽 */}
        <div className="upload-left">
          <UploadPanel onResults={handleResults} />
          {results.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <ParamPanel
                params={params}
                onChange={setParams}
                onRedetect={handleRedetect}
                busy={redetecting}
                calibResult={calibResult}
              />
            </div>
          )}
        </div>

        {/* 오른쪽 */}
        {results.length > 0 && (
          <div className="upload-right fade-up">

            {/* 전체 내보내기 */}
            <BulkExportBar results={results} />

            {/* 파일 탭 */}
            {results.length > 1 && (
              <div className="result-tabs">
                {results.map((r, i) => (
                  <button key={r.job_id}
                    className={`result-tab ${i === selected ? 'active' : ''}`}
                    onClick={() => { setSelected(i); setCalibResult(null) }}>
                    <span className="tab-dot" style={{
                      background: r.streaks.length ? 'var(--teal)' : 'var(--text2)'
                    }} />
                    <span className="tab-name">{r.filename}</span>
                    <span className="tab-count">{r.streaks.length}</span>
                  </button>
                ))}
              </div>
            )}

            {/* 현재 파일 결과 */}
            {current && (
              <>
                <ImageViewer
                  jobId={current.job_id}
                  streaks={current.streaks}
                  binning={params.binning || 2}
                  onCalib={setCalibResult}
                  cacheKey={imgStamp}
                />
                <ResultCard result={current} />
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}