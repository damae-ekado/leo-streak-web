# -*- coding: utf-8 -*-
"""
routers.py  —  FastAPI 라우터
엔드포인트:
  POST /upload                FITS 파일 업로드
  POST /process               streak 검출
  POST /calibrate             캘리브레이션
  GET  /results/{job_id}      결과 조회
  GET  /image/{job_id}        미리보기 이미지
  POST /match                 프레임 매칭
  POST /classifier/upload     ResNet 분류기 모델(.pt) 업로드
  GET  /classifier/info       현재 분류기 정보
  DELETE /classifier          분류기 삭제 (Hough 모드 복귀)
  GET  /satellites            위성 목록
  POST /satellites            위성 기록 추가
  DELETE /satellites/{id}     위성 기록 삭제
  POST /orbit                 궤도 결정
  GET  /health                서버 상태
"""

import io, os, uuid, asyncio, json
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
    ClassifierInfo, SatelliteRecord, SatelliteListResponse, SatelliteCreateRequest,
    OrbitRequest, OrbitResult,
)
from app.utils import (
    load_fits, get_timestamp, bin_image,
    pixel_to_skycoord, angular_distance,
    get_wcs_from_header, make_diff, is_fits_file,
)
from app.detector import (
    detect_streaks, calibrate_from_sample,
    load_classifier, set_classifier_path, get_classifier_path,
)
from app.astrometry import plate_solve
from app.orbit import determine_orbit

router = APIRouter()

UPLOAD_DIR     = os.path.join(os.path.dirname(__file__), "uploads")
RESULT_DIR     = os.path.join(os.path.dirname(__file__), "results")
CLASSIFIER_DIR = os.path.join(os.path.dirname(__file__), "classifiers")
SATELLITE_DB   = os.path.join(os.path.dirname(__file__), "satellites.json")

for d in (UPLOAD_DIR, RESULT_DIR, CLASSIFIER_DIR):
    os.makedirs(d, exist_ok=True)


# ── 유틸 ─────────────────────────────────────────────────────────────────────

async def run_sync(func, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))


def _job_fits_path(job_id):
    for ext in (".fits", ".fit", ".fts"):
        p = os.path.join(UPLOAD_DIR, f"{job_id}{ext}")
        if os.path.exists(p): return p
    raise HTTPException(404, f"job_id '{job_id}' 를 찾을 수 없습니다.")

def _result_path(job_id): return os.path.join(RESULT_DIR, f"{job_id}.json")

def _save_result(job_id, result):
    with open(_result_path(job_id), "w", encoding="utf-8") as f:
        f.write(result.model_dump_json(indent=2))

def _load_result(job_id):
    p = _result_path(job_id)
    if not os.path.exists(p):
        raise HTTPException(404, "아직 처리되지 않은 job 입니다.")
    with open(p, encoding="utf-8") as f:
        return FileResult.model_validate_json(f.read())

def _load_satellites():
    if not os.path.exists(SATELLITE_DB): return []
    with open(SATELLITE_DB, encoding="utf-8") as f:
        return json.load(f)

def _save_satellites(data):
    with open(SATELLITE_DB, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── 동기 처리 ─────────────────────────────────────────────────────────────────

def _do_process(fits_path, params, api_key):
    data, header = load_fits(fits_path)
    has_wcs = True
    try:
        wcs = get_wcs_from_header(header)
    except ValueError:
        has_wcs = False
        if not api_key:
            raise ValueError("FITS 헤더에 WCS 정보가 없습니다. API Key 를 입력하거나 plate solving 된 파일을 사용하세요.")
        wcs = plate_solve(fits_path, api_key, binning=params.binning)
        has_wcs = True

    timestamp     = get_timestamp(header)
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
        dbscan_eps            = params.dbscan_eps,
        dbscan_min_pts        = params.dbscan_min_pts,
        linearity_thresh      = params.linearity_thresh,
        conf_thresh           = params.conf_thresh,
        edge_margin           = params.edge_margin,
    )

    streak_results = []
    for idx, (x1, y1, x2, y2, length_px) in enumerate(raw_streaks, start=1):
        ra_s, dec_s = pixel_to_skycoord(x1, y1, wcs, binning=params.binning)
        ra_e, dec_e = pixel_to_skycoord(x2, y2, wcs, binning=params.binning)
        xm, ym      = (x1+x2)/2, (y1+y2)/2
        ra_m, dec_m = pixel_to_skycoord(xm, ym, wcs, binning=params.binning)
        ang_len     = angular_distance(ra_s, dec_s, ra_e, dec_e)
        t_center    = timestamp + TimeDelta(exposure_time/2 * u.s)
        streak_results.append(StreakResult(
            streak_id=idx,
            start_pixel=PixelCoord(x=x1, y=y1), end_pixel=PixelCoord(x=x2, y=y2),
            length_pixel=length_px,
            start_sky=SkyCoord(ra=ra_s, dec=dec_s), end_sky=SkyCoord(ra=ra_e, dec=dec_e),
            mid_sky=SkyCoord(ra=ra_m, dec=dec_m),
            angular_length_deg=ang_len, angular_velocity=ang_len/exposure_time,
            timestamp=timestamp.isot, t_center=t_center.isot,
        ))

    job_id = os.path.splitext(os.path.basename(fits_path))[0]
    result = FileResult(
        job_id=job_id, filename=os.path.basename(fits_path),
        exposure_time=exposure_time, streaks=streak_results,
        has_wcs=has_wcs, error=None,
    )
    _save_result(job_id, result)
    return result

def _do_preview(fits_path, job_id, binning):
    data, _ = load_fits(fits_path)
    img = bin_image(data, binning=binning)
    _, diff_uint8 = make_diff(img)
    if diff_uint8 is None: raise ValueError("이미지가 너무 어둡습니다.")
    vis = cv2.cvtColor(diff_uint8, cv2.COLOR_GRAY2BGR)
    try:
        result = _load_result(job_id)
        for s in result.streaks:
            cv2.line(vis,(int(s.start_pixel.x),int(s.start_pixel.y)),
                     (int(s.end_pixel.x),int(s.end_pixel.y)),(0,255,0),2)
            cv2.circle(vis,(int(s.start_pixel.x),int(s.start_pixel.y)),4,(255,80,80),-1)
            cv2.circle(vis,(int(s.end_pixel.x),int(s.end_pixel.y)),4,(80,80,255),-1)
    except HTTPException: pass
    _, buf = cv2.imencode(".png", vis)
    return buf.tobytes()


# ── 헬스 ──────────────────────────────────────────────────────────────────────
@router.get("/health")
async def health():
    clf = get_classifier_path()
    return {"status": "ok", "classifier": os.path.basename(clf) if clf else None}


# ── FITS 업로드 ───────────────────────────────────────────────────────────────
@router.post("/upload", response_model=UploadResponse)
async def upload_fits(file: UploadFile = File(...)):
    if not is_fits_file(file.filename or ""):
        raise HTTPException(400, "FITS 파일만 업로드할 수 있습니다.")
    ext     = os.path.splitext(file.filename or ".fits")[1].lower()
    job_id  = uuid.uuid4().hex
    content = await file.read()
    with open(os.path.join(UPLOAD_DIR, f"{job_id}{ext}"), "wb") as f:
        f.write(content)
    return UploadResponse(job_id=job_id, filename=file.filename or "", message="업로드 완료.")


# ── 검출 ──────────────────────────────────────────────────────────────────────
@router.post("/process", response_model=FileResult)
async def process_fits(req: ProcessRequest):
    fits_path = _job_fits_path(req.job_id)
    params    = req.params or DetectParams()
    try:
        result = await run_sync(_do_process, fits_path, params, req.api_key)
        result = result.model_copy(update={"job_id": req.job_id})
        _save_result(req.job_id, result)
        return result
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"처리 오류: {e}")


# ── 캘리브레이션 ──────────────────────────────────────────────────────────────
@router.post("/calibrate", response_model=DetectParams)
async def calibrate(req: CalibRequest):
    def _do():
        data, _ = load_fits(_job_fits_path(req.job_id))
        img = bin_image(data, binning=req.binning)
        return calibrate_from_sample(img, req.x1, req.y1, req.x2, req.y2)
    calib = await run_sync(_do)
    if calib is None:
        raise HTTPException(422, "캘리브레이션 실패.")
    base = DetectParams()
    return DetectParams(
        brightness_min=calib["brightness_min"], brightness_max=calib["brightness_max"],
        min_length_frac=calib["min_length_frac"], max_length_frac=calib["max_length_frac"],
        star_thresh=base.star_thresh, max_satellite_streaks=base.max_satellite_streaks,
        min_fill=base.min_fill, min_brightness=base.min_brightness, binning=req.binning,
        dbscan_eps=base.dbscan_eps, dbscan_min_pts=base.dbscan_min_pts,
        linearity_thresh=base.linearity_thresh, conf_thresh=base.conf_thresh,
        edge_margin=base.edge_margin,
    )


# ── 결과 조회 ─────────────────────────────────────────────────────────────────
@router.get("/results/{job_id}", response_model=FileResult)
async def get_result(job_id: str):
    return _load_result(job_id)


# ── 이미지 미리보기 ───────────────────────────────────────────────────────────
@router.get("/image/{job_id}")
async def preview_image(job_id: str, binning: int = 2):
    fits_path = _job_fits_path(job_id)
    try:
        png = await run_sync(_do_preview, fits_path, job_id, binning)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return StreamingResponse(io.BytesIO(png), media_type="image/png")


# ── 분류기 업로드 ─────────────────────────────────────────────────────────────
@router.post("/classifier/upload", response_model=ClassifierInfo)
async def upload_classifier(file: UploadFile = File(...)):
    if not (file.filename or "").endswith(".pt"):
        raise HTTPException(400, ".pt 모델 파일만 업로드할 수 있습니다.")
    save_path = os.path.join(CLASSIFIER_DIR, file.filename)
    content   = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)
    try:
        _, classes, _ = load_classifier(save_path)
        set_classifier_path(save_path)
    except Exception as e:
        os.unlink(save_path)
        raise HTTPException(422, f"모델 로드 실패: {e}")
    return ClassifierInfo(filename=file.filename, classes=list(classes),
                          message="분류기 로드 완료. DBSCAN 모드로 전환됩니다.")

@router.get("/classifier/info")
async def classifier_info():
    path = get_classifier_path()
    if not path:
        return {"mode": "hough", "classifier": None}
    try:
        _, classes, _ = load_classifier(path)
        return {"mode": "dbscan", "classifier": os.path.basename(path), "classes": list(classes)}
    except Exception:
        return {"mode": "hough", "classifier": None}

@router.delete("/classifier")
async def delete_classifier():
    set_classifier_path(None)
    return {"message": "분류기 제거 완료. Hough 모드로 복귀합니다."}


# ── 위성 기록 ─────────────────────────────────────────────────────────────────
@router.get("/satellites", response_model=SatelliteListResponse)
async def list_satellites():
    data = _load_satellites()
    return SatelliteListResponse(satellites=data, total=len(data))

@router.post("/satellites", response_model=SatelliteRecord)
async def add_satellite(req: SatelliteCreateRequest):
    result = _load_result(req.job_id)
    streak = next((s for s in result.streaks if s.streak_id == req.streak_id), None)
    if not streak:
        raise HTTPException(404, f"streak_id {req.streak_id} 를 찾을 수 없습니다.")
    record = SatelliteRecord(
        id=uuid.uuid4().hex,
        sat_name=req.sat_name,
        first_obs=streak.timestamp,
        job_id=req.job_id,
        filename=result.filename,
        streak_id=req.streak_id,
        mid_ra=streak.mid_sky.ra,
        mid_dec=streak.mid_sky.dec,
        angular_velocity=streak.angular_velocity,
        tle=req.tle,
        note=req.note,
    )
    data = _load_satellites()
    data.append(record.model_dump())
    _save_satellites(data)
    return record

@router.delete("/satellites/{sat_id}")
async def delete_satellite(sat_id: str):
    data = _load_satellites()
    new  = [s for s in data if s["id"] != sat_id]
    if len(new) == len(data):
        raise HTTPException(404, "위성 기록을 찾을 수 없습니다.")
    _save_satellites(new)
    return {"message": "삭제 완료"}


# ── 프레임 매칭 ───────────────────────────────────────────────────────────────
@router.post("/match", response_model=MatchResult)
async def match_frames(job_ids: list[str]):
    results = [_load_result(j) for j in job_ids]
    results.sort(key=lambda r: r.streaks[0].timestamp if r.streaks else "")
    pairs = []
    for i in range(len(results)-1):
        r1, r2 = results[i], results[i+1]
        if not r1.streaks or not r2.streaks: continue
        from astropy.time import Time as ATime
        t1 = ATime(r1.streaks[0].timestamp, format="isot", scale="utc")
        t2 = ATime(r2.streaks[0].timestamp, format="isot", scale="utc")
        delta_t = float((t2-t1).to_value("sec"))
        best_score = float("inf"); best = None
        for a, s1 in enumerate(r1.streaks):
            ang1 = np.degrees(np.arctan2(s1.end_pixel.y-s1.start_pixel.y,
                                          s1.end_pixel.x-s1.start_pixel.x)) % 180
            mx1 = (s1.start_pixel.x+s1.end_pixel.x)/2
            my1 = (s1.start_pixel.y+s1.end_pixel.y)/2
            for b, s2 in enumerate(r2.streaks):
                ang2 = np.degrees(np.arctan2(s2.end_pixel.y-s2.start_pixel.y,
                                              s2.end_pixel.x-s2.start_pixel.x)) % 180
                mx2 = (s2.start_pixel.x+s2.end_pixel.x)/2
                my2 = (s2.start_pixel.y+s2.end_pixel.y)/2
                ad = abs(ang1-ang2); ad = 180-ad if ad>90 else ad
                ma = np.degrees(np.arctan2(my2-my1, mx2-mx1)) % 180
                md = abs(ma-ang1); md = 180-md if md>90 else md
                score = ad+md
                if score < best_score:
                    best_score = score
                    d = angular_distance(s1.mid_sky.ra, s1.mid_sky.dec,
                                         s2.mid_sky.ra, s2.mid_sky.dec)
                    best = MatchPair(filename_a=r1.filename, filename_b=r2.filename,
                                     streak_a=a+1, streak_b=b+1, delta_t_sec=delta_t,
                                     angle_diff_deg=ad, move_deg=d,
                                     angular_velocity=d/delta_t if delta_t>0 else 0.0)
        if best: pairs.append(best)
    return MatchResult(pairs=pairs)


# ── 궤도 결정 ─────────────────────────────────────────────────────────────────
@router.post("/orbit", response_model=OrbitResult)
async def orbit_determination(req: OrbitRequest):
    try:
        obs = [{"t": o.t, "ra": o.ra, "dec": o.dec} for o in req.observations]
        result = await run_sync(determine_orbit, obs,
                                req.lat, req.lon, req.alt, req.norad_id, req.sat_name)
        return OrbitResult(**result)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"궤도 결정 오류: {e}")