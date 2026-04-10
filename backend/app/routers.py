# -*- coding: utf-8 -*-
"""
routers.py
FastAPI 라우터.

엔드포인트:
  POST /upload              FITS 파일 업로드
  POST /process             업로드된 파일 streak 검출
  POST /calibrate           샘플 좌표로 파라미터 자동 계산
  GET  /results/{job_id}    처리 결과 조회
  GET  /image/{job_id}      배경 차분 미리보기 이미지 반환
  POST /match               두 프레임 간 streak 매칭
  GET  /health              서버 상태 확인
"""

import io
import os
import uuid
import asyncio
from functools import partial

import numpy as np
import cv2
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

from astropy import units as u
from astropy.time import TimeDelta

from app.schemas import (
    UploadResponse, ProcessRequest, FileResult,
    StreakResult, PixelCoord, SkyCoord,
    CalibRequest, DetectParams, MatchResult, MatchPair,
)
from app.utils import (
    load_fits, get_timestamp, bin_image,
    pixel_to_skycoord, angular_distance,
    get_wcs_from_header, make_diff, is_fits_file,
)
from app.detector import detect_streaks, calibrate_from_sample
from app.astrometry import plate_solve

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
RESULT_DIR = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)


# ── 유틸 ────────────────────────────────────────────────────────────────────

async def run_sync(func, *args, **kwargs):
    """무거운 동기 함수를 스레드풀에서 실행 → 이벤트 루프 블로킹 방지."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))


def _job_fits_path(job_id: str) -> str:
    for ext in (".fits", ".fit", ".fts"):
        p = os.path.join(UPLOAD_DIR, f"{job_id}{ext}")
        if os.path.exists(p):
            return p
    raise HTTPException(status_code=404, detail=f"job_id '{job_id}' 를 찾을 수 없습니다.")


def _result_path(job_id: str) -> str:
    return os.path.join(RESULT_DIR, f"{job_id}.json")


def _save_result(job_id: str, result: FileResult) -> None:
    with open(_result_path(job_id), "w", encoding="utf-8") as f:
        f.write(result.model_dump_json(indent=2))


def _load_result(job_id: str) -> FileResult:
    p = _result_path(job_id)
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="아직 처리되지 않은 job 입니다.")
    with open(p, encoding="utf-8") as f:
        return FileResult.model_validate_json(f.read())


# ── 동기 처리 함수 (스레드풀에서 실행) ──────────────────────────────────────

def _do_process(fits_path: str, params: DetectParams, api_key: str | None) -> FileResult:
    """
    실제 FITS 처리 로직 (동기).
    run_sync() 를 통해 별도 스레드에서 호출된다.
    """
    data, header = load_fits(fits_path)

    # WCS
    has_wcs = True
    try:
        wcs = get_wcs_from_header(header)
    except ValueError:
        has_wcs = False
        if not api_key:
            raise ValueError(
                "FITS 헤더에 WCS 정보가 없습니다. "
                "Astrometry.net API Key 를 입력하거나 plate solving 된 파일을 사용하세요."
            )
        wcs = plate_solve(fits_path, api_key, binning=params.binning)
        has_wcs = True

    try:
        timestamp = get_timestamp(header)
    except ValueError as e:
        raise ValueError(str(e))

    exposure_time = float(header.get("EXPTIME", 3.0))
    image_binned  = bin_image(data, binning=params.binning)

    raw_streaks = detect_streaks(
        image_binned,
        brightness_min        = params.brightness_min,
        brightness_max        = params.brightness_max,
        star_thresh           = params.star_thresh,
        min_length_frac       = params.min_length_frac,
        max_length_frac       = params.max_length_frac,
        max_satellite_streaks = params.max_satellite_streaks,
        min_fill              = params.min_fill,
        min_brightness        = params.min_brightness,
    )

    streak_results = []
    for idx, (x1, y1, x2, y2, length_px) in enumerate(raw_streaks, start=1):
        ra_s, dec_s = pixel_to_skycoord(x1, y1, wcs, binning=params.binning)
        ra_e, dec_e = pixel_to_skycoord(x2, y2, wcs, binning=params.binning)
        xm, ym      = (x1 + x2) / 2, (y1 + y2) / 2
        ra_m, dec_m = pixel_to_skycoord(xm, ym, wcs, binning=params.binning)
        ang_len     = angular_distance(ra_s, dec_s, ra_e, dec_e)
        t_center    = timestamp + TimeDelta(exposure_time / 2 * u.s)

        streak_results.append(StreakResult(
            streak_id     = idx,
            start_pixel   = PixelCoord(x=x1, y=y1),
            end_pixel     = PixelCoord(x=x2, y=y2),
            length_pixel  = length_px,
            start_sky     = SkyCoord(ra=ra_s, dec=dec_s),
            end_sky       = SkyCoord(ra=ra_e, dec=dec_e),
            mid_sky       = SkyCoord(ra=ra_m, dec=dec_m),
            angular_length_deg = ang_len,
            angular_velocity   = ang_len / exposure_time,
            timestamp     = timestamp.isot,
            t_center      = t_center.isot,
        ))

    job_id = os.path.splitext(os.path.basename(fits_path))[0]
    result = FileResult(
        job_id        = job_id,
        filename      = os.path.basename(fits_path),
        exposure_time = exposure_time,
        streaks       = streak_results,
        has_wcs       = has_wcs,
        error         = None,
    )
    _save_result(job_id, result)
    return result


def _do_preview(fits_path: str, job_id: str, binning: int) -> bytes:
    """배경 차분 + streak 오버레이 PNG bytes 반환 (동기)."""
    data, _ = load_fits(fits_path)
    image_binned = bin_image(data, binning=binning)
    _, diff_uint8 = make_diff(image_binned)
    if diff_uint8 is None:
        raise ValueError("이미지가 너무 어둡습니다.")

    vis = cv2.cvtColor(diff_uint8, cv2.COLOR_GRAY2BGR)
    try:
        result = _load_result(job_id)
        for s in result.streaks:
            cv2.line(vis,
                     (int(s.start_pixel.x), int(s.start_pixel.y)),
                     (int(s.end_pixel.x),   int(s.end_pixel.y)),
                     (0, 255, 0), 2)
            cv2.circle(vis, (int(s.start_pixel.x), int(s.start_pixel.y)), 4, (255, 80, 80), -1)
            cv2.circle(vis, (int(s.end_pixel.x),   int(s.end_pixel.y)),   4, (80, 80, 255), -1)
    except HTTPException:
        pass

    _, buf = cv2.imencode(".png", vis)
    return buf.tobytes()


# ── 엔드포인트 ───────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/upload", response_model=UploadResponse)
async def upload_fits(file: UploadFile = File(...)):
    if not is_fits_file(file.filename or ""):
        raise HTTPException(status_code=400,
            detail="FITS 파일만 업로드할 수 있습니다 (.fits / .fit / .fts).")

    ext     = os.path.splitext(file.filename or ".fits")[1].lower()
    job_id  = uuid.uuid4().hex
    save_path = os.path.join(UPLOAD_DIR, f"{job_id}{ext}")

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    return UploadResponse(
        job_id=job_id,
        filename=file.filename or "",
        message="업로드 완료.",
    )


@router.post("/process", response_model=FileResult)
async def process_fits(req: ProcessRequest):
    """
    FITS 파일을 스레드풀에서 처리한다.
    무거운 numpy/cv2 연산이 이벤트 루프를 블로킹하지 않는다.
    """
    fits_path = _job_fits_path(req.job_id)
    params    = req.params or DetectParams()

    try:
        result = await run_sync(_do_process, fits_path, params, req.api_key)
        # _do_process 는 파일명 기반 job_id 를 저장하므로 req.job_id 로 덮어씀
        result = result.model_copy(update={"job_id": req.job_id})
        _save_result(req.job_id, result)
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"처리 오류: {e}")


@router.post("/calibrate", response_model=DetectParams)
async def calibrate(req: CalibRequest):
    def _do():
        data, _ = load_fits(_job_fits_path(req.job_id))
        img = bin_image(data, binning=req.binning)
        return calibrate_from_sample(img, req.x1, req.y1, req.x2, req.y2)

    calib = await run_sync(_do)
    if calib is None:
        raise HTTPException(status_code=422, detail="캘리브레이션 실패 (이미지가 너무 어둡습니다).")

    base = DetectParams()
    return DetectParams(
        brightness_min        = calib["brightness_min"],
        brightness_max        = calib["brightness_max"],
        min_length_frac       = calib["min_length_frac"],
        max_length_frac       = calib["max_length_frac"],
        star_thresh           = base.star_thresh,
        max_satellite_streaks = base.max_satellite_streaks,
        min_fill              = base.min_fill,
        min_brightness        = base.min_brightness,
        binning               = req.binning,
    )


@router.get("/results/{job_id}", response_model=FileResult)
async def get_result(job_id: str):
    return _load_result(job_id)


@router.get("/image/{job_id}")
async def preview_image(job_id: str, binning: int = 2):
    fits_path = _job_fits_path(job_id)
    try:
        png_bytes = await run_sync(_do_preview, fits_path, job_id, binning)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return StreamingResponse(io.BytesIO(png_bytes), media_type="image/png")


@router.post("/match", response_model=MatchResult)
async def match_frames(job_ids: list[str]):
    results = [_load_result(jid) for jid in job_ids]
    results.sort(key=lambda r: r.streaks[0].timestamp if r.streaks else "")

    pairs: list[MatchPair] = []
    for i in range(len(results) - 1):
        r1, r2 = results[i], results[i + 1]
        if not r1.streaks or not r2.streaks:
            continue

        from astropy.time import Time as ATime
        t1 = ATime(r1.streaks[0].timestamp, format="isot", scale="utc")
        t2 = ATime(r2.streaks[0].timestamp, format="isot", scale="utc")
        delta_t = float((t2 - t1).to_value("sec"))

        best_score = float("inf")
        best: MatchPair | None = None

        for a, s1 in enumerate(r1.streaks):
            ang1 = np.degrees(np.arctan2(
                s1.end_pixel.y - s1.start_pixel.y,
                s1.end_pixel.x - s1.start_pixel.x,
            )) % 180
            mx1 = (s1.start_pixel.x + s1.end_pixel.x) / 2
            my1 = (s1.start_pixel.y + s1.end_pixel.y) / 2

            for b, s2 in enumerate(r2.streaks):
                ang2 = np.degrees(np.arctan2(
                    s2.end_pixel.y - s2.start_pixel.y,
                    s2.end_pixel.x - s2.start_pixel.x,
                )) % 180
                mx2 = (s2.start_pixel.x + s2.end_pixel.x) / 2
                my2 = (s2.start_pixel.y + s2.end_pixel.y) / 2

                angle_diff = abs(ang1 - ang2)
                if angle_diff > 90:
                    angle_diff = 180 - angle_diff
                move_angle = np.degrees(np.arctan2(my2 - my1, mx2 - mx1)) % 180
                move_diff  = abs(move_angle - ang1)
                if move_diff > 90:
                    move_diff = 180 - move_diff
                score = angle_diff + move_diff

                if score < best_score:
                    best_score = score
                    d = angular_distance(
                        s1.mid_sky.ra, s1.mid_sky.dec,
                        s2.mid_sky.ra, s2.mid_sky.dec,
                    )
                    best = MatchPair(
                        filename_a      = r1.filename,
                        filename_b      = r2.filename,
                        streak_a        = a + 1,
                        streak_b        = b + 1,
                        delta_t_sec     = delta_t,
                        angle_diff_deg  = angle_diff,
                        move_deg        = d,
                        angular_velocity = d / delta_t if delta_t > 0 else 0.0,
                    )

        if best:
            pairs.append(best)

    return MatchResult(pairs=pairs)