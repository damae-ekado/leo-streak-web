# -*- coding: utf-8 -*-
"""
orbit.py
Orbit_determination.py 를 웹 API 용으로 이식.
관측 데이터(RA/Dec + 시각)를 받아 Lambert + DC 로 TLE 를 생성한다.

관측지: 부산과학고 별샘천문대
  35°15'46.96"N  129°04'57.48"E  121m
"""

import numpy as np
from scipy.optimize import least_squares, brentq
from astropy.time import Time
from astropy.coordinates import EarthLocation, AltAz, SkyCoord
import astropy.units as u

# ── 상수 ────────────────────────────────────────────────────────────────────
MU  = 3.986004418e14   # 지구 중력 상수 [m³/s²]
RE  = 6378137.0        # 지구 반경 [m]

# 기본 관측지 (부산과학고 별샘천문대)
DEFAULT_LAT = 35.26304444
DEFAULT_LON = 129.08263333
DEFAULT_ALT = 121.0


# ── 유틸 ────────────────────────────────────────────────────────────────────

def norm(v):  return np.linalg.norm(v)
def unit(v):  return v / norm(v)


def ra_dec_to_unit(ra_deg: float, dec_deg: float) -> np.ndarray:
    ra  = np.radians(ra_deg)
    dec = np.radians(dec_deg)
    return np.array([np.cos(dec) * np.cos(ra),
                     np.cos(dec) * np.sin(ra),
                     np.sin(dec)])


def obs_site_eci(t_str: str, lat: float, lon: float, alt: float) -> np.ndarray:
    """관측지 ECI 좌표 [m]."""
    t   = Time(t_str, format="isot", scale="utc")
    loc = EarthLocation.from_geodetic(lon * u.deg, lat * u.deg, alt * u.m)
    gcrs = loc.get_gcrs(t)
    return np.array([gcrs.cartesian.x.to(u.m).value,
                     gcrs.cartesian.y.to(u.m).value,
                     gcrs.cartesian.z.to(u.m).value])


def apply_refraction(
    t_str: str, ra_deg: float, dec_deg: float,
    lat: float, lon: float, alt: float,
) -> tuple[float, float]:
    """Bennett 대기굴절 보정 → 보정된 (RA, Dec) 반환."""
    t   = Time(t_str, format="isot", scale="utc")
    loc = EarthLocation.from_geodetic(lon * u.deg, lat * u.deg, alt * u.m)
    sc  = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
    aa  = sc.transform_to(AltAz(obstime=t, location=loc))
    alt_obs = aa.alt.deg
    h = max(alt_obs, 0.5)
    ref = 60 * (1 / np.tan(np.radians(h + 7.31 / (h + 4.4)))) / 3600.0  # deg
    alt_true = alt_obs - ref
    aa_true = AltAz(alt=alt_true * u.deg, az=aa.az.deg * u.deg,
                    obstime=t, location=loc)
    sc_true = SkyCoord(aa_true).icrs
    return sc_true.ra.deg, sc_true.dec.deg


# ── 궤도역학 ─────────────────────────────────────────────────────────────────

def kepler_to_rv(a, e, i, O, w, M_d):
    i = np.radians(i % 360); O = np.radians(O % 360)
    w = np.radians(w % 360); M = np.radians(M_d % 360)
    E = M
    for _ in range(100):
        dE = (M - E + e * np.sin(E)) / (1 - e * np.cos(E))
        E += dE
        if abs(dE) < 1e-12:
            break
    nu = 2 * np.arctan2(np.sqrt(max(1 + e, 0)) * np.sin(E / 2),
                        np.sqrt(max(1 - e, 0)) * np.cos(E / 2))
    rm = a * (1 - e * np.cos(E))
    p  = a * (1 - e ** 2)
    ci, si = np.cos(i), np.sin(i)
    cO, sO = np.cos(O), np.sin(O)
    cw, sw = np.cos(w), np.sin(w)
    Rot = np.array([[ cO*cw - sO*sw*ci, -cO*sw - sO*cw*ci,  sO*si],
                    [ sO*cw + cO*sw*ci, -sO*sw + cO*cw*ci, -cO*si],
                    [ sw*si,             cw*si,              ci   ]])
    r = Rot @ (rm * np.array([np.cos(nu), np.sin(nu), 0]))
    v = Rot @ (np.sqrt(MU / p) * np.array([-np.sin(nu), e + np.cos(nu), 0]))
    return r, v


def rv_to_kepler(r, v):
    rm = norm(r); vm = norm(v)
    h  = np.cross(r, v); hm = norm(h)
    n_ = np.cross([0, 0, 1], h); nm = norm(n_)
    e_ = ((vm ** 2 - MU / rm) * r - np.dot(r, v) * v) / MU
    ecc = norm(e_)
    energy = vm ** 2 / 2 - MU / rm
    if energy >= 0 or ecc >= 1:
        return None
    a   = -MU / (2 * energy)
    inc = np.degrees(np.arccos(np.clip(h[2] / hm, -1, 1)))
    RAAN = np.degrees(np.arccos(np.clip(n_[0] / nm, -1, 1)))
    if n_[1] < 0:
        RAAN = 360 - RAAN
    if ecc < 1e-8:
        argp, nu_ = 0., 0.
    else:
        argp = np.degrees(np.arccos(np.clip(np.dot(n_, e_) / (nm * ecc), -1, 1)))
        if e_[2] < 0:
            argp = 360 - argp
        nu_ = np.degrees(np.arccos(np.clip(np.dot(e_, r) / (ecc * rm), -1, 1)))
        if np.dot(r, v) < 0:
            nu_ = 360 - nu_
    E2 = 2 * np.arctan2(np.sqrt(max(1 - ecc, 1e-30)) * np.sin(np.radians(nu_) / 2),
                         np.sqrt(max(1 + ecc, 1e-30)) * np.cos(np.radians(nu_) / 2))
    M  = np.degrees(E2 - ecc * np.sin(E2)) % 360
    return a, ecc, inc, RAAN, argp, M


def lambert_izzo(r1, r2, tof, prograde=True):
    r1m = norm(r1); r2m = norm(r2)
    cos_dnu = np.clip(np.dot(r1, r2) / (r1m * r2m), -1, 1)
    cross = np.cross(r1, r2)
    if prograde:
        dnu = np.arccos(cos_dnu) if cross[2] >= 0 else 2 * np.pi - np.arccos(cos_dnu)
    else:
        dnu = 2 * np.pi - np.arccos(cos_dnu) if cross[2] >= 0 else np.arccos(cos_dnu)
    A = np.sin(dnu) * np.sqrt(r1m * r2m / (1 - np.cos(dnu)))

    def F(z):
        if abs(z) < 1e-8:
            c2, c3 = 0.5, 1 / 6.
        elif z > 0:
            sz = np.sqrt(z); c2 = (1 - np.cos(sz)) / z; c3 = (sz - np.sin(sz)) / sz ** 3
        else:
            sz = np.sqrt(-z); c2 = (1 - np.cosh(sz)) / z; c3 = (np.sinh(sz) - sz) / (-z) ** 1.5
        y = r1m + r2m + A * (z * c3 - 1) / np.sqrt(max(c2, 1e-30))
        if y < 0:
            return -1e10
        return np.sqrt(y / max(c2, 1e-30)) ** 3 * c3 + A * np.sqrt(y) - tof * np.sqrt(MU)

    z_lo, z_hi = -4 * np.pi ** 2, 4 * np.pi ** 2
    try:
        for _ in range(60):
            if F(z_hi) > 0:
                break
            z_hi *= 2
        z = brentq(F, z_lo, z_hi, xtol=1e-10)
    except Exception:
        return None, None

    if abs(z) < 1e-8:
        c2, c3 = 0.5, 1 / 6.
    elif z > 0:
        sz = np.sqrt(z); c2 = (1 - np.cos(sz)) / z; c3 = (sz - np.sin(sz)) / sz ** 3
    else:
        sz = np.sqrt(-z); c2 = (1 - np.cosh(sz)) / z; c3 = (np.sinh(sz) - sz) / (-z) ** 1.5
    y = r1m + r2m + A * (z * c3 - 1) / np.sqrt(max(c2, 1e-30))
    if y < 0:
        return None, None
    f     = 1 - y / r1m
    g_dot = 1 - y / r2m
    g     = A * np.sqrt(y / MU)
    return (r2 - f * r1) / g, (g_dot * r2 - r1) / g


def kepler_to_tle(
    a, e, i_deg, RAAN_deg, argp_deg, M_deg,
    epoch_isot: str,
    norad_id: int = 99999,
    name: str = "IOD_RESULT",
) -> str:
    t   = Time(epoch_isot, format="isot", scale="utc")
    yr  = int(t.datetime.year) % 100
    doy = float(t.strftime("%j")) + (t.mjd % 1)
    epoch_str = f"{yr:02d}{doy:012.8f}"
    n_rev_d   = np.sqrt(MU / a ** 3) * 86400 / (2 * np.pi)
    e_str     = f"{e:.7f}"[2:]
    line1 = (f"1 {norad_id:05d}U 00001A   {epoch_str}"
             f"  .00000000  00000-0  10000-4 0  9990")
    line2 = (f"2 {norad_id:05d} "
             f"{i_deg % 180:8.4f} "
             f"{RAAN_deg % 360:8.4f} "
             f"{e_str} "
             f"{argp_deg % 360:8.4f} "
             f"{M_deg % 360:8.4f} "
             f"{n_rev_d:11.8f}    10")

    def chk(ln):
        return sum(int(c) if c.isdigit() else (1 if c == "-" else 0) for c in ln[:-1]) % 10

    line1 = line1[:-1] + str(chk(line1))
    line2 = line2[:-1] + str(chk(line2))
    return f"0 {name}\n{line1}\n{line2}"


# ── 메인 파이프라인 ──────────────────────────────────────────────────────────

def determine_orbit(
    observations: list[dict],   # [{"t": "isot", "ra": float, "dec": float}, ...]
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
    alt: float = DEFAULT_ALT,
    norad_id: int = 99999,
    sat_name: str = "IOD_RESULT",
) -> dict:
    """
    관측 데이터로부터 궤도 요소 + TLE 를 계산한다.

    Parameters
    ----------
    observations : list of dict
        각 원소: {"t": "2026-04-02T12:47:02.361", "ra": 100.55, "dec": 41.40}
        최소 4개 이상 권장, 8개 이상이면 정밀도 향상.
    lat, lon, alt : 관측지 위경도 및 고도

    Returns
    -------
    dict with keys:
        tle        : str  — 3-line TLE
        elements   : dict — 궤도 요소
        residuals  : list — 잔차 테이블
        rms_arcsec : float
        orbit_type : str  — "LEO" / "MEO" / "GEO"
    """
    if len(observations) < 3:
        raise ValueError("관측 데이터가 최소 3개 이상 필요합니다.")

    # 1. 대기굴절 보정
    obs_corr = []
    for ob in observations:
        ra_c, dec_c = apply_refraction(ob["t"], ob["ra"], ob["dec"], lat, lon, alt)
        obs_corr.append({"t": ob["t"], "ra": ra_c, "dec": dec_c,
                         "ra_raw": ob["ra"], "dec_raw": ob["dec"]})

    # 2. 데이터 준비
    t0_abs = Time(obs_corr[0]["t"], format="isot", scale="utc")
    dts = np.array([(Time(o["t"], format="isot", scale="utc") - t0_abs).to_value("sec")
                    for o in obs_corr])
    Ls  = np.array([ra_dec_to_unit(o["ra"], o["dec"]) for o in obs_corr])
    Rs  = np.array([obs_site_eci(o["t"], lat, lon, alt) for o in obs_corr])
    N   = len(obs_corr)

    # 3. 잔차 함수
    def angle_res(state):
        r0, v0 = state[:3], state[3:]
        el = rv_to_kepler(r0, v0)
        if el is None:
            return np.ones(N * 2) * 1e4
        a_, ecc_, inc_, RAAN_, argp_, M0_ = el
        if ecc_ > 0.95 or a_ < 0:
            return np.ones(N * 2) * 1e4
        n_ = np.sqrt(MU / a_ ** 3)
        res = []
        for k, (dt, R) in enumerate(zip(dts, Rs)):
            M_t = (M0_ + np.degrees(n_ * dt)) % 360
            try:
                r, _ = kepler_to_rv(a_, ecc_, inc_, RAAN_, argp_, M_t)
            except Exception:
                res.extend([1e4, 1e4]); continue
            rho = r - R; ru = unit(rho)
            dc  = np.degrees(np.arcsin(np.clip(ru[2], -1, 1)))
            rc  = np.degrees(np.arctan2(ru[1], ru[0])) % 360
            cd  = np.cos(np.radians(obs_corr[k]["dec"]))
            res.extend([(rc - obs_corr[k]["ra"]) * cd * 3600,
                        (dc - obs_corr[k]["dec"]) * 3600])
        return np.array(res)

    # 4. Lambert 초기값 탐색
    n_last = N - 1
    best_state = None; best_rms = 1e9
    pairs = [(0, n_last), (0, n_last-1), (0, n_last-2), (1, n_last), (2, n_last)]
    pairs = [(i1, i2) for i1, i2 in pairs if i2 < N and i1 < i2]

    for i1, i2 in pairs:
        tof_pair = dts[i2] - dts[i1]
        for rho_km in np.arange(1400, 2200, 25):
            rho = rho_km * 1e3
            ra_ = Rs[i1] + rho * Ls[i1]
            rb_ = Rs[i2] + rho * Ls[i2]
            for prog in [True, False]:
                va, _ = lambert_izzo(ra_, rb_, tof_pair, prograde=prog)
                if va is None:
                    continue
                vm = norm(va); energy = vm ** 2 / 2 - MU / norm(ra_)
                if energy >= 0 or vm > 9000 or vm < 5000:
                    continue
                el = rv_to_kepler(ra_, va)
                if el is None:
                    continue
                a_, ecc_, inc_, R__, w_, M_ = el
                if ecc_ > 0.5:
                    continue
                n__ = np.sqrt(MU / a_ ** 3)
                M0_ = (M_ - np.degrees(n__ * dts[i1])) % 360
                r0_, v0_ = kepler_to_rv(a_, ecc_, inc_, R__, w_, M0_)
                state = np.concatenate([r0_, v0_])
                res = angle_res(state)
                rms = np.sqrt(np.mean(res ** 2))
                if rms < best_rms:
                    best_rms = rms; best_state = state.copy()

    if best_state is None:
        raise ValueError("Lambert 초기값 탐색 실패. 관측 데이터를 확인하세요.")

    # 5. Differential Correction
    result = least_squares(angle_res, best_state, method="lm",
                           ftol=1e-15, xtol=1e-15, gtol=1e-15, max_nfev=500_000)
    rms_f = np.sqrt(np.mean(result.fun ** 2))

    r0f, v0f = result.x[:3], result.x[3:]
    el = rv_to_kepler(r0f, v0f)
    if el is None:
        raise ValueError("궤도 요소 계산 실패.")

    a, ecc, inc, RAAN, argp, M = el
    n_rev_d = np.sqrt(MU / a ** 3) * 86400 / (2 * np.pi)
    alt_km  = (a - RE) / 1e3
    orbit_type = "LEO" if alt_km < 2000 else ("MEO" if alt_km < 35786 else "GEO")

    # 6. 잔차 테이블
    n_ = np.sqrt(MU / a ** 3)
    residuals = []
    all_res = []
    for k, (dt, R) in enumerate(zip(dts, Rs)):
        M_t = (M + np.degrees(n_ * dt)) % 360
        r, _ = kepler_to_rv(a, ecc, inc, RAAN, argp, M_t)
        rho = r - R; ru = unit(rho)
        dc  = np.degrees(np.arcsin(np.clip(ru[2], -1, 1)))
        rc  = np.degrees(np.arctan2(ru[1], ru[0])) % 360
        cd  = np.cos(np.radians(obs_corr[k]["dec"]))
        dra  = (rc - obs_corr[k]["ra"]) * cd * 3600
        ddec = (dc - obs_corr[k]["dec"]) * 3600
        all_res.extend([dra, ddec])
        residuals.append({
            "t":     obs_corr[k]["t"],
            "dra":   round(dra, 2),
            "ddec":  round(ddec, 2),
            "total": round(np.hypot(dra, ddec), 2),
        })

    rms_final = float(np.sqrt(np.mean(np.array(all_res) ** 2)))

    # 7. TLE 생성
    tle = kepler_to_tle(a, ecc, inc, RAAN % 360, argp % 360, M % 360,
                        obs_corr[0]["t"], norad_id=norad_id, name=sat_name)

    return {
        "tle": tle,
        "elements": {
            "a_km":     round(a / 1e3, 3),
            "alt_km":   round(alt_km, 1),
            "e":        round(ecc, 8),
            "i_deg":    round(inc, 4),
            "RAAN_deg": round(RAAN % 360, 4),
            "argp_deg": round(argp % 360, 4),
            "M_deg":    round(M % 360, 4),
            "n_rev_d":  round(n_rev_d, 4),
            "period_min": round(1440 / n_rev_d, 2),
        },
        "residuals":   residuals,
        "rms_arcsec":  round(rms_final, 3),
        "orbit_type":  orbit_type,
        "init_rms":    round(float(best_rms), 1),
        "dc_rms":      round(rms_f, 3),
    }