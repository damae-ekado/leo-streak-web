import { useState } from 'react'
import UploadPanel from '../components/UploadPanel'
import ImageViewer from '../components/ImageViewer'
import ResultCard  from '../components/ResultCard'
import './UploadPage.css'

export default function UploadPage() {
  const [results, setResults] = useState([])   // FileResult[]
  const [selected, setSelected] = useState(0) // 현재 보고 있는 결과 인덱스

  const handleResults = (newResults) => {
    setResults((prev) => {
      const merged = [...prev]
      newResults.forEach((r) => {
        const idx = merged.findIndex((x) => x.job_id === r.job_id)
        if (idx >= 0) merged[idx] = r
        else merged.push(r)
      })
      return merged
    })
    setSelected((prev) => prev)
  }

  const current = results[selected] || null

  return (
    <div className="page">
      <h1 className="page-title">LEO Streak Detector</h1>
      <p className="page-sub">FITS 이미지에서 저궤도 위성 궤적을 자동 검출합니다</p>

      <div className={`upload-layout ${results.length ? 'has-result' : ''}`}>
        {/* 왼쪽: 업로드 패널 */}
        <div className="upload-left">
          <UploadPanel onResults={handleResults} />
        </div>

        {/* 오른쪽: 결과 탭 + 뷰어 */}
        {results.length > 0 && (
          <div className="upload-right fade-up">
            {/* 파일 탭 */}
            {results.length > 1 && (
              <div className="result-tabs">
                {results.map((r, i) => (
                  <button
                    key={r.job_id}
                    className={`result-tab ${i === selected ? 'active' : ''}`}
                    onClick={() => setSelected(i)}
                  >
                    <span className="tab-dot" style={{
                      background: r.streaks.length ? 'var(--teal)' : 'var(--text2)'
                    }} />
                    <span className="tab-name">{r.filename}</span>
                    <span className="tab-count">{r.streaks.length}</span>
                  </button>
                ))}
              </div>
            )}

            {current && (
              <>
                <ImageViewer jobId={current.job_id} streaks={current.streaks} />
                <ResultCard  result={current} />
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}