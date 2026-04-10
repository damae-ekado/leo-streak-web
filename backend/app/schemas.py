# -*- coding: utf-8 -*-
"""
schemas.py
FastAPI 요청·응답에 쓰이는 Pydantic 모델 정의.
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


# ── 공용 타입 ────────────────────────────────────────────────────────────────

class PixelCoord(BaseModel):
    x: float
    y: float


class SkyCoord(BaseModel):
    ra: float  = Field(..., description="적경 [도]")
    dec: float = Field(..., description="적위 [도]")


# ── 개별 streak ──────────────────────────────────────────────────────────────

class StreakResult(BaseModel):
    streak_id: int              = Field(..., description="이미지 내 streak 번호 (1부터)")
    start_pixel: PixelCoord
    end_pixel:   PixelCoord
    length_pixel: float         = Field(..., description="픽셀 길이")
    start_sky:   SkyCoord
    end_sky:     SkyCoord
    mid_sky:     SkyCoord
    angular_length_deg: float   = Field(..., description="각거리 [도]")
    angular_velocity:   float   = Field(..., description="각속도 [도/s]")
    timestamp:   str            = Field(..., description="관측 시각 ISO 8601")
    t_center:    str            = Field(..., description="노출 중심 시각 ISO 8601")


# ── 파일 단위 처리 결과 ──────────────────────────────────────────────────────

class FileResult(BaseModel):
    job_id:        str
    filename:      str
    exposure_time: float          = Field(..., description="노출 시간 [s]")
    streaks:       list[StreakResult]
    has_wcs:       bool           = Field(..., description="WCS 정보 보유 여부")
    error:         Optional[str]  = Field(None, description="처리 오류 메시지")


# ── 업로드 응답 ──────────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    job_id:   str
    filename: str
    message:  str


# ── 검출 파라미터 (캘리브레이션 포함) ────────────────────────────────────────

class DetectParams(BaseModel):
    brightness_min:       int   = Field(40,   ge=0,   le=255)
    brightness_max:       int   = Field(80,   ge=0,   le=255)
    star_thresh:          float = Field(17.0, gt=0)
    min_length_frac:      float = Field(0.02, gt=0,   le=1.0)
    max_length_frac:      float = Field(1.0,  gt=0,   le=2.0)
    max_satellite_streaks: int  = Field(3,    ge=1,   le=20)
    min_fill:             float = Field(0.3,  ge=0,   le=1.0)
    min_brightness:       int   = Field(6,    ge=0,   le=255)
    binning:              int   = Field(2,    ge=1,   le=8)


# ── 처리 요청 ────────────────────────────────────────────────────────────────

class ProcessRequest(BaseModel):
    job_id:       str
    params:       Optional[DetectParams] = None
    api_key:      Optional[str]          = Field(None, description="Astrometry.net API 키")


# ── 캘리브레이션 요청 ────────────────────────────────────────────────────────

class CalibRequest(BaseModel):
    job_id: str
    x1: int
    y1: int
    x2: int
    y2: int
    binning: int = 2


# ── 프레임 간 매칭 결과 ──────────────────────────────────────────────────────

class MatchPair(BaseModel):
    filename_a:     str
    filename_b:     str
    streak_a:       int
    streak_b:       int
    delta_t_sec:    float
    angle_diff_deg: float
    move_deg:       float
    angular_velocity: float   = Field(..., description="[도/s]")


class MatchResult(BaseModel):
    pairs: list[MatchPair]