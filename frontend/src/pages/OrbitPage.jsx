import { useState } from 'react'
import { orbitDetermination } from '../api/client'
import { download } from '../components/ResultCard'
import './OrbitPage.css'

const BLANK_OBS = { t: '', ra: '', dec: '' }

export default function OrbitPage() {
  const [obs,      setObs]      = useState([{ ...BLANK_OBS }, { ...BLANK_OBS }, { ...BLANK_OBS }])
  const [site,     setSite]     = useState({ lat: 35.26304444, lon: 129.08263333, alt: 121.0 })
  const [satName,  setSatName]  = useState('BSSH_IOD')
  const [result,   setResult]   = useState(null)
  const [busy,     setBusy]     = useState(false)
  const [error,    setError]    = useState('')

  const addRow    = () => setObs(prev => [...prev, { ...BLANK_OBS }])
  const removeRow = i  => setObs(prev => prev.filter((_, j) => j !== i))
  const patchObs  = (i, key, val) =>
    setObs(prev => prev.map((o, j) => j === i ? { ...o, [key]: val } : o))

  const runOrbit = async () => {
    const valid = obs.filter(o => o.t && o.ra !== '' && o.dec !== '')
    if (valid.length < 3) { setError('유효한 관측 데이터가 최소 3개 필요합니다.'); return }
    setError(''); setBusy(true); setResult(null)
    try {
      const { data } = await orbitDetermination({
        observations: valid.map(o => ({ t: o.t, ra: Number(o.ra), dec: Number(o.dec) })),
        lat: Number(site.lat), lon: Number(site.lon), alt: Number(site.alt),
        sat_name: satName || 'IOD_RESULT',
      })
      setResult(data)
    } catch (e) {
      setError(e.response?.data?.detail || '궤도 결정 실패')
    } finally { setBusy(false) }
  }

  const exportTLE = () => {
    if (!result) return
    download(result.tle, `${satName || 'IOD'}.tle`, 'text/plain')
  }

  const exportJSON = () => {
    if (!result) return
    download(JSON.stringify(result, null, 2), `${satName || 'IOD'}.json`, 'application/json')
  }

  return (
    <div className="page">
      <h1 className="page-title">궤도 결정</h1>
      <p className="page-sub">관측 데이터(RA/Dec + 시각)로 Lambert + DC 법을 통해 TLE를 생성합니다</p>

      <div className="orbit-layout">
        {/* 왼쪽: 입력 */}
        <div className="orbit-left">

          {/* 관측지 */}
          <div className="card orbit-section">
            <div className="orbit-section-title">관측지</div>
            <div className="site-grid">
              {[['lat','위도 (°N)'],['lon','경도 (°E)'],['alt','고도 (m)']].map(([k,lbl]) => (
                <div key={k} className="orbit-field">
                  <label>{lbl}</label>
                  <input type="number" step="any" value={site[k]}
                    onChange={e => setSite(s => ({ ...s, [k]: e.target.value }))} />
                </div>
              ))}
            </div>
          </div>

          {/* 위성 이름 */}
          <div className="card orbit-section">
            <div className="orbit-section-title">위성 이름 (TLE 헤더)</div>
            <input value={satName} onChange={e => setSatName(e.target.value)}
              placeholder="예: BSSH_IOD" />
          </div>

          {/* 관측 데이터 테이블 */}
          <div className="card orbit-section">
            <div className="orbit-section-header">
              <div className="orbit-section-title">관측 데이터</div>
              <button className="btn btn-ghost btn-xs" onClick={addRow}>+ 행 추가</button>
            </div>

            <div className="obs-table">
              <div className="obs-header">
                <span>#</span>
                <span>관측 시각 (ISO UTC)</span>
                <span>RA (°)</span>
                <span>Dec (°)</span>
                <span></span>
              </div>
              {obs.map((o, i) => (
                <div className="obs-row" key={i}>
                  <span className="obs-num mono">{i + 1}</span>
                  <input className="obs-input"
                    placeholder="2026-04-02T12:47:02.361"
                    value={o.t} onChange={e => patchObs(i, 't', e.target.value)} />
                  <input className="obs-input obs-num-input"
                    type="number" step="any" placeholder="100.55"
                    value={o.ra} onChange={e => patchObs(i, 'ra', e.target.value)} />
                  <input className="obs-input obs-num-input"
                    type="number" step="any" placeholder="41.40"
                    value={o.dec} onChange={e => patchObs(i, 'dec', e.target.value)} />
                  <button className="btn btn-ghost btn-xs"
                    onClick={() => removeRow(i)} disabled={obs.length <= 3}>✕</button>
                </div>
              ))}
            </div>

            {/* 샘플 데이터 채우기 */}
            <button className="btn btn-ghost btn-xs" style={{ marginTop: 8 }}
              onClick={() => setObs([
                { t:'2026-04-02T12:47:02.361', ra:'100.553494', dec:'41.397132' },
                { t:'2026-04-02T12:47:11.103', ra:'103.251154', dec:'40.913704' },
                { t:'2026-04-02T12:47:20.909', ra:'106.213091', dec:'40.277645' },
                { t:'2026-04-02T12:47:29.043', ra:'108.515900', dec:'39.753608' },
                { t:'2026-04-02T12:47:37.499', ra:'110.943424', dec:'39.122131' },
                { t:'2026-04-02T12:47:47.118', ra:'113.690875', dec:'38.311137' },
                { t:'2026-04-02T12:48:04.779', ra:'118.263193', dec:'36.762564' },
                { t:'2026-04-02T12:48:13.823', ra:'120.418432', dec:'35.952007' },
              ])}>
              샘플 데이터 채우기
            </button>
          </div>

          {error && <div className="orbit-error">⚠ {error}</div>}

          <button className="btn btn-primary orbit-run-btn" disabled={busy} onClick={runOrbit}>
            {busy ? '계산 중… (수십 초 소요)' : '궤도 결정 실행'}
          </button>
        </div>

        {/* 오른쪽: 결과 */}
        {result && (
          <div className="orbit-right fade-up">

            {/* TLE */}
            <div className="card orbit-section">
              <div className="orbit-section-header">
                <div className="orbit-section-title">TLE</div>
                <div style={{ display:'flex', gap:6 }}>
                  <button className="btn btn-ghost btn-xs" onClick={exportTLE}>TLE 저장</button>
                  <button className="btn btn-ghost btn-xs" onClick={exportJSON}>JSON 저장</button>
                </div>
              </div>
              <pre className="tle-block mono">{result.tle}</pre>
              <div style={{ display:'flex', gap:12, marginTop:10, flexWrap:'wrap' }}>
                <a className="ext-link" href="https://www.heavens-above.com/" target="_blank" rel="noreferrer">
                  Heavens-Above ↗
                </a>
                <a className="ext-link"
                  href={`https://celestrak.org/SOCRATES/?MEAN_MOTION=${(result.elements?.n_rev_d-0.3).toFixed(2)}~${(result.elements?.n_rev_d+0.3).toFixed(2)}`}
                  target="_blank" rel="noreferrer">
                  CelesTrak ↗
                </a>
                <a className="ext-link" href="https://www.space-track.org/" target="_blank" rel="noreferrer">
                  Space-Track ↗
                </a>
              </div>
            </div>

            {/* 궤도 요소 */}
            <div className="card orbit-section">
              <div className="orbit-section-title">궤도 요소</div>
              <div className="elements-grid">
                {result.elements && Object.entries({
                  '반장축 (km)':    result.elements.a_km.toFixed(3),
                  '고도 (km)':      result.elements.alt_km.toFixed(1),
                  '이심률':         result.elements.e.toFixed(8),
                  '경사각 (°)':     result.elements.i_deg.toFixed(4),
                  'RAAN (°)':       result.elements.RAAN_deg.toFixed(4),
                  '근지점각 (°)':   result.elements.argp_deg.toFixed(4),
                  '평균이각 (°)':   result.elements.M_deg.toFixed(4),
                  '평균운동 (rev/d)': result.elements.n_rev_d.toFixed(4),
                  '주기 (분)':      result.elements.period_min.toFixed(2),
                  '궤도 종류':      result.orbit_type,
                }).map(([k, v]) => (
                  <div key={k} className="element-item">
                    <div className="element-label">{k}</div>
                    <div className="element-value mono">{v}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* 정확도 */}
            <div className="card orbit-section">
              <div className="orbit-section-title">정확도</div>
              <div className="rms-row">
                <div className="rms-item">
                  <div className="element-label">초기값 RMS</div>
                  <div className="element-value mono">{result.init_rms?.toFixed(1)}"</div>
                </div>
                <div className="rms-item">
                  <div className="element-label">DC 수렴 RMS</div>
                  <div className={`element-value mono ${result.dc_rms < 5 ? 'good' : 'warn'}`}>
                    {result.dc_rms?.toFixed(3)}"
                  </div>
                </div>
                <div className="rms-item">
                  <div className="element-label">최종 RMS</div>
                  <div className={`element-value mono ${result.rms_arcsec < 5 ? 'good' : 'warn'}`}>
                    {result.rms_arcsec?.toFixed(3)}"
                  </div>
                </div>
              </div>

              {/* 잔차 테이블 */}
              <div className="residual-table">
                <div className="residual-header">
                  <span>시각</span><span>ΔRA (")</span><span>ΔDec (")</span><span>합 (")</span>
                </div>
                {result.residuals?.map((r, i) => (
                  <div className="residual-row" key={i}>
                    <span className="mono" style={{fontSize:11}}>{r.t.slice(11,19)}</span>
                    <span className={`mono ${Math.abs(r.dra)>5?'warn':''}`}>{r.dra > 0 ? '+' : ''}{r.dra.toFixed(1)}</span>
                    <span className={`mono ${Math.abs(r.ddec)>5?'warn':''}`}>{r.ddec > 0 ? '+' : ''}{r.ddec.toFixed(1)}</span>
                    <span className={`mono ${r.total>5?'warn':'good'}`}>{r.total.toFixed(1)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}