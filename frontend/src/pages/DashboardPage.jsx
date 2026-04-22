import { useState, useEffect, useCallback } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ScatterChart, Scatter,
} from 'recharts'
import { getResult, matchFrames, listSatellites, addSatellite, deleteSatellite } from '../api/client'
import { toCSV, download } from '../components/ResultCard'
import './DashboardPage.css'

const LS_JOBS = 'leo_job_ids'
const LS_SATS = 'leo_satellites_cache'

export default function DashboardPage() {
  const [jobIds,  setJobIds]  = useState(() => {
    try { return JSON.parse(localStorage.getItem(LS_JOBS) || '[]') } catch { return [] }
  })
  const [results, setResults] = useState([])
  const [match,   setMatch]   = useState(null)
  const [input,   setInput]   = useState('')
  const [loading, setLoading] = useState(false)
  const [tab,     setTab]     = useState('frames') // 'frames' | 'satellites' | 'chart'

  const [satellites,   setSatellites]   = useState([])
  const [satLoading,   setSatLoading]   = useState(false)
  const [addingStreak, setAddingStreak] = useState(null)
  const [satName,      setSatName]      = useState('')
  const [jsonDrag,     setJsonDrag]     = useState(false)

  // ── 프레임 결과 로드 ────────────────────────────────────────────
  const loadResults = useCallback(async (ids) => {
    if (!ids.length) { setResults([]); return }
    setLoading(true)
    const rs = await Promise.all(
      ids.map(id => getResult(id).then(r => r.data).catch(() => null))
    )
    setResults(rs.filter(Boolean))
    setLoading(false)
  }, [])

  useEffect(() => { loadResults(jobIds) }, [jobIds])

  // ── localStorage 변경 감지 (Upload 페이지에서 자동 추가) ───────
  useEffect(() => {
    const onStorage = (e) => {
      if (e.key !== LS_JOBS) return
      try {
        const ids = JSON.parse(e.newValue || '[]')
        setJobIds(ids)
      } catch {}
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  // ── 위성 목록 로드 ──────────────────────────────────────────────
  const loadSatellites = useCallback(async () => {
    setSatLoading(true)
    try {
      const { data } = await listSatellites()
      setSatellites(data.satellites)
      localStorage.setItem(LS_SATS, JSON.stringify(data.satellites))
    } catch {
      const cached = localStorage.getItem(LS_SATS)
      if (cached) setSatellites(JSON.parse(cached))
    } finally { setSatLoading(false) }
  }, [])

  useEffect(() => { loadSatellites() }, [])

  // ── job 추가/삭제 ───────────────────────────────────────────────
  const addJob = () => {
    const id = input.trim()
    if (!id || jobIds.includes(id)) return
    const next = [...jobIds, id]
    setJobIds(next)
    localStorage.setItem(LS_JOBS, JSON.stringify(next))
    setInput('')
  }

  const removeJob = (id) => {
    const next = jobIds.filter(j => j !== id)
    setJobIds(next)
    setResults(prev => prev.filter(r => r.job_id !== id))
    localStorage.setItem(LS_JOBS, JSON.stringify(next))
  }

  // ── JSON 파일 드롭 ──────────────────────────────────────────────
  const handleJsonFile = (file) => {
    if (!file || !file.name.endsWith('.json')) return
    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        const parsed = JSON.parse(e.target.result)
        const ids = Array.isArray(parsed) ? parsed : (parsed.job_ids || [])
        if (!ids.length) return alert('job_id 배열을 찾을 수 없습니다.')
        const next = [...new Set([...jobIds, ...ids])]
        setJobIds(next)
        localStorage.setItem(LS_JOBS, JSON.stringify(next))
        loadResults(next)
      } catch { alert('JSON 파싱 오류') }
    }
    reader.readAsText(file)
  }

  // ── 프레임 매칭 ────────────────────────────────────────────────
  const runMatch = async () => {
    if (results.length < 2) return
    const { data } = await matchFrames(results.map(r => r.job_id))
    setMatch(data)
  }

  // ── 위성 저장 ──────────────────────────────────────────────────
  const handleAddSatellite = async () => {
    if (!addingStreak || !satName.trim()) return
    try {
      await addSatellite({
        job_id: addingStreak.job_id,
        streak_id: addingStreak.streak_id,
        sat_name: satName,
      })
      setAddingStreak(null); setSatName('')
      loadSatellites()
    } catch (e) { alert(e.response?.data?.detail || '저장 실패') }
  }

  const handleDeleteSat = async (id) => {
    await deleteSatellite(id)
    loadSatellites()
  }

  // ── 전체 내보내기 ───────────────────────────────────────────────
  const exportAllJSON = () =>
    download(JSON.stringify(results, null, 2), 'leo_all_results.json', 'application/json')

  const exportAllCSV = () => {
    if (!results.length) return
    const header = toCSV(results[0]).split('\n')[0]
    const rows   = results.flatMap(r => toCSV(r).split('\n').slice(1))
    download([header, ...rows].join('\n'), 'leo_all_results.csv', 'text/csv')
  }

  // ── 통계 ───────────────────────────────────────────────────────
  const totalStreaks = results.reduce((s, r) => s + r.streaks.length, 0)
  const allVel = results.flatMap(r => r.streaks.map(s => s.angular_velocity))
  const meanVel = allVel.length ? allVel.reduce((a, b) => a + b, 0) / allVel.length : null

  // ── 차트 데이터 ────────────────────────────────────────────────
  const velData = results
    .flatMap(r => r.streaks.map(s => ({
      label: s.timestamp.slice(11, 19),
      t: s.timestamp,
      vel: parseFloat(s.angular_velocity.toFixed(5)),
      name: `${r.filename} #${s.streak_id}`,
    })))
    .sort((a, b) => a.t.localeCompare(b.t))

  const countData = results.map(r => ({
    name: r.filename.length > 16 ? '…' + r.filename.slice(-14) : r.filename,
    count: r.streaks.length,
  }))

  const scatterData = results.flatMap(r =>
    r.streaks.map(s => ({
      ra:  parseFloat(s.mid_sky.ra.toFixed(4)),
      dec: parseFloat(s.mid_sky.dec.toFixed(4)),
      name: `${r.filename} #${s.streak_id}`,
    }))
  )

  const CHART_STYLE = {
    contentStyle: {
      background: 'var(--bg1)',
      border: '1px solid var(--border)',
      borderRadius: 6,
      fontSize: 12,
      color: 'var(--text0)',
    },
  }

  return (
    <div className="page">
      <h1 className="page-title">Dashboard</h1>
      <p className="page-sub">검출 결과 집계 · 위성 매칭 · 기록 관리</p>

      {/* 통계 */}
      <div className="stats-row fade-up">
        <StatBox label="등록 프레임"  value={results.length} />
        <StatBox label="총 Streak"    value={totalStreaks} accent />
        <StatBox label="평균 각속도"  value={meanVel !== null ? `${meanVel.toFixed(4)}°/s` : '—'} />
        <StatBox label="저장 위성"    value={satellites.length} />
      </div>

      {/* 전체 내보내기 */}
      {results.length > 0 && (
        <div className="bulk-export fade-up">
          <span className="export-label">전체 내보내기</span>
          <span className="bulk-count">{results.length}개 파일 · {totalStreaks}개 streak</span>
          <div style={{ flex: 1 }} />
          <button className="btn btn-ghost btn-xs" onClick={exportAllJSON}>↓ JSON</button>
          <button className="btn btn-ghost btn-xs" onClick={exportAllCSV}>↓ CSV</button>
          <button className="btn btn-ghost btn-xs"
            onClick={() => download(
              JSON.stringify({ job_ids: results.map(r => r.job_id) }, null, 2),
              'leo_job_ids.json', 'application/json'
            )}>↓ job ID 목록</button>
        </div>
      )}

      {/* 탭 */}
      <div className="dash-tabs fade-up">
        {[
          { key: 'frames',     label: '프레임 관리' },
          { key: 'satellites', label: '위성 목록' },
          { key: 'chart',      label: '시계열 차트' },
        ].map(({ key, label }) => (
          <button key={key}
            className={`dash-tab ${tab === key ? 'active' : ''}`}
            onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>

      {/* ─── 프레임 탭 ───────────────────────────────────────────── */}
      {tab === 'frames' && (
        <>
          {/* job 추가 */}
          <div className="dashboard-add card fade-up">
            <div className="add-row-wrap">
              <div className="add-row">
                <input placeholder="job_id 직접 입력 후 Enter"
                  value={input} onChange={e => setInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addJob()} />
                <button className="btn btn-primary" onClick={addJob}
                  disabled={!input.trim()}>추가</button>
              </div>
              <div
                className={`json-drop ${jsonDrag ? 'drag' : ''}`}
                onDragOver={e => { e.preventDefault(); setJsonDrag(true) }}
                onDragLeave={() => setJsonDrag(false)}
                onDrop={e => { e.preventDefault(); setJsonDrag(false); handleJsonFile(e.dataTransfer.files[0]) }}
                onClick={() => {
                  const inp = document.createElement('input')
                  inp.type = 'file'; inp.accept = '.json'
                  inp.onchange = ev => handleJsonFile(ev.target.files[0])
                  inp.click()
                }}>
                📂 JSON 파일로 일괄 추가
              </div>
            </div>
          </div>

          {loading && <div className="dash-loading">로딩 중…</div>}

          {results.length > 0 && (
            <div className="result-table card fade-up">
              <div className="result-table-header">
                <span>파일명</span>
                <span>Streak</span>
                <span>최대 각속도</span>
                <span>관측 시각</span>
                <span></span>
              </div>
              {results.map(r => {
                const maxVel = r.streaks.length
                  ? Math.max(...r.streaks.map(s => s.angular_velocity)) : null
                const ts = r.streaks[0]?.timestamp ?? '—'
                return (
                  <div className="result-table-row" key={r.job_id}>
                    <span className="mono rt-filename" title={r.filename}>{r.filename}</span>
                    <span><span className="badge badge-teal">{r.streaks.length}</span></span>
                    <span className="mono rt-vel">
                      {maxVel !== null ? `${maxVel.toFixed(4)}°/s` : '—'}
                    </span>
                    <span className="mono rt-ts">{ts.slice(0, 19)}</span>
                    <div className="rt-actions">
                      {r.streaks.map(s => (
                        <button key={s.streak_id} className="btn btn-ghost btn-xs"
                          onClick={() => { setAddingStreak({ job_id: r.job_id, streak_id: s.streak_id }); setSatName('') }}>
                          #{s.streak_id} 저장
                        </button>
                      ))}
                      <button className="btn btn-danger btn-xs"
                        onClick={() => removeJob(r.job_id)}>삭제</button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {/* 위성 저장 팝업 */}
          {addingStreak && (
            <div className="sat-save-overlay" onClick={() => setAddingStreak(null)}>
              <div className="sat-save-modal card" onClick={e => e.stopPropagation()}>
                <div style={{ fontWeight: 700, marginBottom: 12 }}>위성 기록 저장</div>
                <div style={{ fontSize: 12, color: 'var(--text2)', marginBottom: 12 }}>
                  job: <span className="mono">{addingStreak.job_id.slice(0, 8)}…</span>
                  &nbsp; streak #{addingStreak.streak_id}
                </div>
                <label>인공위성 이름</label>
                <input placeholder="예: STARLINK-1234 또는 UNKNOWN"
                  value={satName} onChange={e => setSatName(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleAddSatellite()}
                  autoFocus />
                <div className="upload-actions" style={{ marginTop: 12 }}>
                  <button className="btn btn-ghost" onClick={() => setAddingStreak(null)}>취소</button>
                  <button className="btn btn-primary"
                    disabled={!satName.trim()} onClick={handleAddSatellite}>저장</button>
                </div>
              </div>
            </div>
          )}

          {/* 매칭 */}
          {results.length >= 2 && (
            <div className="match-section fade-up">
              <div className="match-header">
                <div>
                  <div style={{ fontWeight: 700 }}>프레임 간 매칭</div>
                  <div style={{ fontSize: 13, color: 'var(--text1)' }}>
                    인접 프레임 streak을 매칭해 이동 각속도를 계산합니다
                  </div>
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
                        <Stat label="Streak"     value={`#${p.streak_a} ↔ #${p.streak_b}`} />
                        <Stat label="Δt"         value={`${p.delta_t_sec.toFixed(2)}s`} />
                        <Stat label="이동 각거리" value={`${p.move_deg.toFixed(6)}°`} />
                        <Stat label="각속도"     value={`${p.angular_velocity.toFixed(6)}°/s`} accent />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {results.length === 0 && !loading && <EmptyState />}
        </>
      )}

      {/* ─── 위성 탭 ─────────────────────────────────────────────── */}
      {tab === 'satellites' && (
        <div className="satellites-section fade-up">
          {satLoading && <div className="dash-loading">로딩 중…</div>}
          {satellites.length === 0 && !satLoading && (
            <div className="dash-empty">
              <div className="dash-empty-icon">✦</div>
              <div>저장된 위성이 없습니다</div>
              <div style={{ fontSize: 13, color: 'var(--text2)' }}>
                프레임 탭에서 streak을 저장하세요
              </div>
            </div>
          )}
          {satellites.length > 0 && (
            <div className="result-table card">
              <div className="sat-table-header">
                <span>이름</span>
                <span>최초 관측</span>
                <span>RA / Dec</span>
                <span>각속도</span>
                <span>파일</span>
                <span></span>
              </div>
              {satellites.map(s => (
                <div className="sat-table-row" key={s.id}>
                  <span className="sat-name">{s.sat_name}</span>
                  <span className="mono rt-ts">{s.first_obs.slice(0, 19)}</span>
                  <span className="mono" style={{ fontSize: 11, color: 'var(--text1)' }}>
                    {s.mid_ra.toFixed(3)}° / {s.mid_dec.toFixed(3)}°
                  </span>
                  <span className="mono rt-vel">{s.angular_velocity.toFixed(4)}°/s</span>
                  <span className="mono rt-filename" title={s.filename}>{s.filename}</span>
                  <button className="btn btn-danger btn-xs"
                    onClick={() => handleDeleteSat(s.id)}>삭제</button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ─── 시계열 차트 탭 ──────────────────────────────────────── */}
      {tab === 'chart' && (
        <div className="chart-section fade-up">
          {results.length === 0 ? (
            <EmptyState />
          ) : (
            <>
              {/* 각속도 시계열 */}
              <div className="card chart-card">
                <div className="chart-title">각속도 시계열 (°/s)</div>
                {velData.length === 0 ? (
                  <div className="chart-empty">검출된 streak이 없습니다</div>
                ) : (
                  <ResponsiveContainer width="100%" height={240}>
                    <LineChart data={velData} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.06)" />
                      <XAxis dataKey="label"
                        tick={{ fontSize: 11, fill: 'var(--text2)' }}
                        interval="preserveStartEnd" />
                      <YAxis tick={{ fontSize: 11, fill: 'var(--text2)' }} width={64}
                        tickFormatter={v => `${v.toFixed(3)}°`} />
                      <Tooltip {...CHART_STYLE}
                        formatter={(v, _, p) => [`${v}°/s`, p.payload.name]} />
                      <Line type="monotone" dataKey="vel"
                        stroke="#00d4aa" strokeWidth={2}
                        dot={{ r: 4, fill: '#00d4aa', strokeWidth: 0 }}
                        activeDot={{ r: 6 }} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>

              {/* 프레임별 streak 수 */}
              <div className="card chart-card">
                <div className="chart-title">프레임별 Streak 수</div>
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={countData} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.06)" />
                    <XAxis dataKey="name"
                      tick={{ fontSize: 10, fill: 'var(--text2)' }}
                      interval={0} angle={-20} textAnchor="end" height={40} />
                    <YAxis tick={{ fontSize: 11, fill: 'var(--text2)' }} width={30}
                      allowDecimals={false} />
                    <Tooltip {...CHART_STYLE} />
                    <Line type="monotone" dataKey="count"
                      stroke="#3b82f6" strokeWidth={2}
                      dot={{ r: 4, fill: '#3b82f6', strokeWidth: 0 }}
                      activeDot={{ r: 6 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* RA/Dec 산점도 */}
              <div className="card chart-card">
                <div className="chart-title">Streak 중심점 분포 (RA / Dec)</div>
                {scatterData.length === 0 ? (
                  <div className="chart-empty">검출된 streak이 없습니다</div>
                ) : (
                  <ResponsiveContainer width="100%" height={260}>
                    <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.06)" />
                      <XAxis dataKey="ra" name="RA" unit="°"
                        tick={{ fontSize: 11, fill: 'var(--text2)' }}
                        label={{ value: 'RA (°)', position: 'insideBottom', offset: -4, fontSize: 11, fill: 'var(--text2)' }} />
                      <YAxis dataKey="dec" name="Dec" unit="°"
                        tick={{ fontSize: 11, fill: 'var(--text2)' }} width={55}
                        label={{ value: 'Dec (°)', angle: -90, position: 'insideLeft', fontSize: 11, fill: 'var(--text2)' }} />
                      <Tooltip {...CHART_STYLE}
                        cursor={{ strokeDasharray: '3 3' }}
                        formatter={(v, n, p) => [
                          n === 'RA' ? `${v.toFixed(4)}°` : `${v.toFixed(4)}°`,
                          n === 'RA' ? `RA  (${p.payload.name})` : `Dec (${p.payload.name})`,
                        ]} />
                      <Scatter data={scatterData} fill="#00d4aa"
                        fillOpacity={0.8} r={5} />
                    </ScatterChart>
                  </ResponsiveContainer>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ── 서브 컴포넌트 ─────────────────────────────────────────────────
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

function EmptyState() {
  return (
    <div className="dash-empty">
      <div className="dash-empty-icon">✦</div>
      <div>등록된 프레임이 없습니다</div>
      <div style={{ fontSize: 13, color: 'var(--text2)' }}>
        Upload 페이지에서 검출하면 자동으로 등록되거나, JSON 파일을 드롭하세요
      </div>
    </div>
  )
}