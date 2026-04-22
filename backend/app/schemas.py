# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


# ── 공용 ─────────────────────────────────────────────────────────────────────
class PixelCoord(BaseModel):
    x: float
    y: float

class SkyCoord(BaseModel):
    ra:  float = Field(..., description="적경 [도]")
    dec: float = Field(..., description="적위 [도]")


# ── 개별 streak ──────────────────────────────────────────────────────────────
class StreakResult(BaseModel):
    streak_id:          int
    start_pixel:        PixelCoord
    end_pixel:          PixelCoord
    length_pixel:       float
    start_sky:          SkyCoord
    end_sky:            SkyCoord
    mid_sky:            SkyCoord
    angular_length_deg: float
    angular_velocity:   float
    timestamp:          str
    t_center:           str


# ── 파일 단위 결과 ───────────────────────────────────────────────────────────
class FileResult(BaseModel):
    job_id:        str
    filename:      str
    exposure_time: float
    streaks:       list[StreakResult]
    has_wcs:       bool
    error:         Optional[str] = None


# ── 업로드 응답 ──────────────────────────────────────────────────────────────
class UploadResponse(BaseModel):
    job_id:   str
    filename: str
    message:  str


# ── 검출 파라미터 ────────────────────────────────────────────────────────────
class DetectParams(BaseModel):
    brightness_min:        int   = Field(40,   ge=0,   le=255)
    brightness_max:        int   = Field(80,   ge=0,   le=255)
    star_thresh:           float = Field(15.0, gt=0)
    min_length_frac:       float = Field(0.02, gt=0,   le=1.0)
    max_length_frac:       float = Field(1.0,  gt=0,   le=2.0)
    max_satellite_streaks: int   = Field(4,    ge=1,   le=20)
    min_fill:              float = Field(0.05, ge=0,   le=1.0)
    min_brightness:        int   = Field(4,    ge=0,   le=255)
    binning:               int   = Field(2,    ge=1,   le=8)
    # 분류기 모드 파라미터
    dbscan_eps:            float = Field(8.0,  gt=0)
    dbscan_min_pts:        int   = Field(10,   ge=1)
    linearity_thresh:      float = Field(0.15, gt=0)
    conf_thresh:           float = Field(0.95, ge=0,   le=1.0)
    edge_margin:           int   = Field(20,   ge=0)


# ── 처리 요청 ────────────────────────────────────────────────────────────────
class ProcessRequest(BaseModel):
    job_id:  str
    params:  Optional[DetectParams] = None
    api_key: Optional[str]          = None


# ── 캘리브레이션 요청 ────────────────────────────────────────────────────────
class CalibRequest(BaseModel):
    job_id:  str
    x1: int; y1: int
    x2: int; y2: int
    binning: int = 2


# ── 매칭 ─────────────────────────────────────────────────────────────────────
class MatchPair(BaseModel):
    filename_a:      str
    filename_b:      str
    streak_a:        int
    streak_b:        int
    delta_t_sec:     float
    angle_diff_deg:  float
    move_deg:        float
    angular_velocity: float

class MatchResult(BaseModel):
    pairs: list[MatchPair]


# ── 분류기 업로드 응답 ───────────────────────────────────────────────────────
class ClassifierInfo(BaseModel):
    filename: str
    classes:  list[str]
    message:  str


# ── 위성 기록 ────────────────────────────────────────────────────────────────
class SatelliteRecord(BaseModel):
    id:              str   = Field(..., description="고유 ID (UUID)")
    sat_name:        str   = Field(..., description="인공위성 이름 / 임시명")
    first_obs:       str   = Field(..., description="최초 관측 시각 ISO 8601")
    job_id:          str   = Field(..., description="관련 job_id")
    filename:        str
    streak_id:       int
    mid_ra:          float
    mid_dec:         float
    angular_velocity: float
    tle:             Optional[str]  = None
    note:            Optional[str]  = None

class SatelliteListResponse(BaseModel):
    satellites: list[SatelliteRecord]
    total:      int

class SatelliteCreateRequest(BaseModel):
    job_id:    str
    streak_id: int
    sat_name:  str = "UNKNOWN"
    tle:       Optional[str] = None
    note:      Optional[str] = None


# ── 궤도 결정 ────────────────────────────────────────────────────────────────
class ObservationPoint(BaseModel):
    t:   str
    ra:  float
    dec: float

class OrbitRequest(BaseModel):
    observations: list[ObservationPoint] = Field(..., min_length=3)
    lat: float = Field(35.26304444)
    lon: float = Field(129.08263333)
    alt: float = Field(121.0)
    norad_id: int  = Field(99999)
    sat_name: str  = Field("IOD_RESULT")

class ResidualRow(BaseModel):
    t: str; dra: float; ddec: float; total: float

class OrbitalElements(BaseModel):
    a_km: float; alt_km: float; e: float
    i_deg: float; RAAN_deg: float; argp_deg: float
    M_deg: float; n_rev_d: float; period_min: float

class OrbitResult(BaseModel):
    tle:        str
    elements:   OrbitalElements
    residuals:  list[ResidualRow]
    rms_arcsec: float
    orbit_type: str
    init_rms:   float
    dc_rms:     float