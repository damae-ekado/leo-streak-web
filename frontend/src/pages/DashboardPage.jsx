import { useState, useEffect } from 'react'
import { getResult, matchFrames } from '../api/client'
import './DashboardPage.css'

export default function DashboardPage() {
  const [jobIds, setJobIds]   = useState(() => {
    try { return JSON.parse(localStorage.getItem('leo_job_ids') || '[]') } catch { return [] }
  })
  const [results, setResults] = useState([])
  const [match, setMatch]     = useState(null)
  const [input, setInput]     = useState('')
  const [loading, setLoading] = useState(false)

  // job_ids 로드
  useEffect(() => {
    if (!jobIds.length) return
    setLoading(true)
    Promise.all(jobIds.map((id) => getResult(id).then((r) => r.data).catch(() => null)))
      .then((rs) => setResults(rs.filter(Boolean)))
      .finally(() => setLoading(false))
  }, [jobIds])

  const addJob = () => {
    const id = input.trim()
    if (!id || jobIds.includes(id)) return
    const next = [...jobIds, id]
    setJobIds(next)
    localStorage.setItem('leo_job_ids', JSON.stringify(next))
    setInput('')
  }

  const removeJob = (id) => {
    const next = jobIds.filter((j) => j !== id)
    setJobIds(next)
    setResults(results.filter((r) => r.job_id !== id))
    localStorage.setItem('leo_job_ids', JSON.stringify(next))
  }

  const runMatch = async () => {
    if (results.length < 2) return
    const ids = results.map((r) => r.job_id)
    const { data } = await matchFrames(ids)
    setMatch(data)
  }

  const totalStreaks = results.reduce((s, r) => s + r.streaks.length, 0)
  const avgVel = results.flatMap((r) => r.streaks.map((s) => s.angular_velocity))
  const meanVel = avgVel.length ? avgVel.reduce((a, b) => a + b, 0) / avgVel.length : null

  return (
    <div className="page">
      <h1 className="page-title">Dashboard</h1>
      <p className="page-sub">여러 프레임의 검출 결과를 집계하고 위성을 매칭합니다</p>

      {/* 통계 요약 */}
      <div className="stats-row fade-up">
        <StatBox label="등록 프레임" value={results.length} />
        <StatBox label="총 Streak"   value={totalStreaks} accent />
        <StatBox label="평균 각속도" value={meanVel !== null ? `${meanVel.toFixed(4)}°/s` : '—'} />
      </div>

      {/* job 추가 */}
      <div className="dashboard-add card fade-up" style={{ animationDelay: '.05s' }}>
        <label>Job ID 추가</label>
        <div className="add-row">
          <input
            placeholder="업로드 후 받은 job_id 를 입력"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addJob()}
          />
          <button className="btn btn-primary" onClick={addJob} disabled={!input.trim()}>추가</button>
        </div>
      </div>

      {/* 결과 목록 */}
      {loading && <div className="dash-loading">로딩 중…</div>}

      {results.length > 0 && (
        <div className="result-table card fade-up" style={{ animationDelay: '.1s' }}>
          <div className="result-table-header">
            <span>파일명</span>
            <span>Streak 수</span>
            <span>각속도 (최대)</span>
            <span>관측 시각</span>
            <span></span>
          </div>
          {results.map((r) => {
            const maxVel = r.streaks.length
              ? Math.max(...r.streaks.map((s) => s.angular_velocity))
              : null
            const ts = r.streaks[0]?.timestamp ?? '—'
            return (
              <div className="result-table-row" key={r.job_id}>
                <span className="mono rt-filename" title={r.filename}>{r.filename}</span>
                <span>
                  <span className="badge badge-teal">{r.streaks.length}</span>
                </span>
                <span className="mono rt-vel">
                  {maxVel !== null ? `${maxVel.toFixed(4)}°/s` : '—'}
                </span>
                <span className="mono rt-ts">{ts.slice(0, 19)}</span>
                <button
                  className="btn btn-danger btn-xs"
                  onClick={() => removeJob(r.job_id)}
                >
                  삭제
                </button>
              </div>
            )
          })}
        </div>
      )}

      {/* 프레임 매칭 */}
      {results.length >= 2 && (
        <div className="match-section fade-up" style={{ animationDelay: '.15s' }}>
          <div className="match-header">
            <div>
              <div style={{ fontWeight: 700 }}>프레임 간 매칭</div>
              <div style={{ fontSize: 13, color: 'var(--text1)' }}>인접 프레임 streak 를 매칭해 이동 각속도를 계산합니다</div>
            </div>
            <button className="btn btn-primary" onClick={runMatch}>매칭 실행</button>
          </div>

          {match?.pairs?.length > 0 && (
            <div className="match-results card-sm">
              {match.pairs.map((p, i) => (
                <div className="match-pair" key={i}>
                  <div className="match-pair-files mono">
                    <span>{p.filename_a}</span>
                    <span className="match-arrow">→</span>
                    <span>{p.filename_b}</span>
                  </div>
                  <div className="match-pair-stats">
                    <Stat label="Streak"   value={`#${p.streak_a} ↔ #${p.streak_b}`} />
                    <Stat label="Δt"       value={`${p.delta_t_sec.toFixed(2)}s`} />
                    <Stat label="이동 각거리" value={`${p.move_deg.toFixed(6)}°`} />
                    <Stat label="각속도"    value={`${p.angular_velocity.toFixed(6)}°/s`} accent />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {results.length === 0 && !loading && (
        <div className="dash-empty">
          <div className="dash-empty-icon">✦</div>
          <div>등록된 프레임이 없습니다</div>
          <div style={{ fontSize: 13, color: 'var(--text2)' }}>Upload 페이지에서 처리 후 job_id 를 추가하세요</div>
        </div>
      )}
    </div>
  )
}

function StatBox({ label, value, accent }) {
  return (
    <div className="stat-box card">
      <div className="stat-label">{label}</div>
      <div className={`stat-value mono ${accent ? 'accent' : ''}`}>{value}</div>
    </div>
  )
}

function Stat({ label, value, accent }) {
  return (
    <div className="inline-stat">
      <span className="inline-stat-label">{label}</span>
      <span className={`inline-stat-value mono ${accent ? 'accent' : ''}`}>{value}</span>
    </div>
  )
}