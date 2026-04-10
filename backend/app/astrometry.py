# -*- coding: utf-8 -*-
"""
astrometry.py
Astrometry.net API 를 통한 plate solving.
결과 WCS 를 반환하며, 이미 헤더에 WCS 가 있으면 호출 불필요.
"""

import os
import time
import tempfile

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from astropy.io import fits
from astropy.wcs import WCS

from app.utils import load_fits, bin_image, save_wcs_to_fits

ASTROMETRY_API_URL = "https://nova.astrometry.net/api/"


# ── 세션 팩토리 ──────────────────────────────────────────────────────────────

def _get_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[500, 502, 503, 504],
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


# ── 로그인 ───────────────────────────────────────────────────────────────────

def login(api_key: str) -> str:
    """Astrometry.net 에 로그인하고 session 토큰을 반환한다."""
    s = _get_session()
    r = s.post(
        ASTROMETRY_API_URL + "login",
        data={"request-json": f'{{"apikey": "{api_key}"}}'},
        timeout=30,
    )
    r.raise_for_status()
    result = r.json()
    if result.get("status") != "success":
        raise ValueError(f"Astrometry.net 로그인 실패: {result}")
    return result["session"]


# ── 업로드 ───────────────────────────────────────────────────────────────────

def upload(session_token: str, fits_path: str) -> int:
    """FITS 파일을 업로드하고 submission ID 를 반환한다."""
    s = _get_session()
    with open(fits_path, "rb") as f:
        r = s.post(
            ASTROMETRY_API_URL + "upload",
            files={"file": f},
            data={
                "request-json": (
                    f'{{"session": "{session_token}", '
                    f'"allow_commercial_use": "n", "publicly_visible": "n"}}'
                )
            },
            timeout=120,
        )
    r.raise_for_status()
    result = r.json()
    if result.get("status") != "success":
        raise ValueError(f"Astrometry.net 업로드 실패: {result}")
    return result["subid"]


# ── 완료 대기 ────────────────────────────────────────────────────────────────

def wait_for_job(subid: int, timeout: int = 300) -> int:
    """
    submission 이 완료될 때까지 폴링한다.
    Returns:
        job_id (int)
    Raises:
        TimeoutError: timeout 초 내에 완료되지 않을 때
        ValueError:   plate solving 실패할 때
    """
    s = _get_session()
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = s.get(
                ASTROMETRY_API_URL + f"submissions/{subid}", timeout=30
            )
            r.raise_for_status()
            data = r.json()
            jobs = data.get("jobs", [])
            if jobs and jobs[0] is not None:
                job_id = jobs[0]
                jr = s.get(ASTROMETRY_API_URL + f"jobs/{job_id}", timeout=30)
                jr.raise_for_status()
                status = jr.json().get("status")
                if status == "success":
                    return job_id
                if status == "failure":
                    raise ValueError(f"Plate solving 실패 (job {job_id})")
        except requests.exceptions.SSLError:
            pass  # 재시도
        time.sleep(5)
    raise TimeoutError(f"Plate solving 시간 초과 ({timeout}초)")


# ── WCS 다운로드 ─────────────────────────────────────────────────────────────

def get_wcs(job_id: int) -> WCS:
    """job_id 로부터 WCS FITS 를 다운로드해 astropy WCS 를 반환한다."""
    s = _get_session()
    r = s.get(
        f"https://nova.astrometry.net/wcs_file/{job_id}", timeout=60
    )
    r.raise_for_status()
    with tempfile.NamedTemporaryFile(suffix=".fits", delete=False) as tmp:
        tmp.write(r.content)
        tmp_path = tmp.name
    try:
        with fits.open(tmp_path) as hdul:
            wcs_header = hdul[0].header
        return WCS(wcs_header)
    finally:
        os.unlink(tmp_path)


# ── 통합 plate solve ─────────────────────────────────────────────────────────

def plate_solve(fits_path: str, api_key: str, binning: int = 2) -> WCS:
    """
    FITS 파일을 binning 후 Astrometry.net 에 제출해 WCS 를 얻는다.
    성공하면 원본 FITS 헤더에도 WCS 를 저장한다.
    """
    data, header = load_fits(fits_path)
    data_bin = bin_image(data, binning=binning)

    with tempfile.NamedTemporaryFile(suffix=".fits", delete=False) as tmp:
        tmp_path = tmp.name
    fits.writeto(tmp_path, data_bin, header, overwrite=True)

    try:
        session_token = login(api_key)
        subid = upload(session_token, tmp_path)
        job_id = wait_for_job(subid)
        wcs = get_wcs(job_id)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    # 다음 실행 때 재사용하도록 헤더에 저장 (실패해도 계속)
    try:
        save_wcs_to_fits(fits_path, wcs)
    except Exception:
        pass

    return wcs