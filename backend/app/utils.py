# -*- coding: utf-8 -*-
"""
utils.py
FITS 파일 로드, 빈닝, 좌표 변환, 배경 차분 등 공용 유틸 함수
"""

import os
import warnings
import numpy as np
import cv2
import sep
from astropy.io import fits
from astropy.wcs import WCS, FITSFixedWarning
from astropy.time import Time

warnings.simplefilter("ignore", FITSFixedWarning)


# ── FITS 로드 ────────────────────────────────────────────────────────────────

def load_fits(file_path: str) -> tuple[np.ndarray, fits.Header]:
    """
    FITS 파일을 열어 첫 번째 데이터 HDU를 float32 배열로 반환한다.
    Returns:
        (data, header)
    """
    with fits.open(
        file_path,
        ignore_missing_simple=True,
        ignore_missing_end=True,
        checksum=False,
    ) as hdul:
        for hdu in hdul:
            if hdu.data is not None:
                return hdu.data.astype(np.float32), hdu.header
    raise ValueError(f"데이터가 있는 HDU를 찾을 수 없습니다: {file_path}")


# ── 타임스탬프 ───────────────────────────────────────────────────────────────

def get_timestamp(header: fits.Header) -> Time:
    """FITS 헤더에서 관측 시각(UTC)을 읽어 astropy Time 으로 반환한다."""
    for key in ("DATE-OBS", "DATE_OBS"):
        if key in header:
            return Time(header[key], format="isot", scale="utc")
    if "MJD-OBS" in header:
        return Time(header["MJD-OBS"], format="mjd", scale="utc")
    raise ValueError("관측 시각 키워드(DATE-OBS / MJD-OBS)를 찾을 수 없습니다.")


# ── 빈닝 ────────────────────────────────────────────────────────────────────

def bin_image(data: np.ndarray, binning: int = 2) -> np.ndarray:
    """
    data를 binning × binning 픽셀 평균으로 다운샘플한다.
    입력 크기가 binning 의 배수가 아니면 잘라낸다.
    """
    h, w = data.shape
    h = (h // binning) * binning
    w = (w // binning) * binning
    return (
        data[:h, :w]
        .reshape(h // binning, binning, w // binning, binning)
        .mean(axis=(1, 3))
        .astype(np.float32)
    )


# ── 좌표 변환 ────────────────────────────────────────────────────────────────

def pixel_to_skycoord(
    x: float, y: float, wcs: WCS, binning: int = 2
) -> tuple[float, float]:
    """
    빈닝된 이미지의 픽셀 좌표 (x, y) → (RA, Dec) [도].
    binning 을 곱해 원본 픽셀 기준으로 변환한다.
    """
    sky = wcs.pixel_to_world(x * binning, y * binning)
    return sky.ra.deg, sky.dec.deg


def angular_distance(
    ra1: float, dec1: float, ra2: float, dec2: float
) -> float:
    """두 천구 좌표 사이의 각거리 [도]를 구면 코사인 법칙으로 계산한다."""
    ra1, dec1, ra2, dec2 = map(np.radians, [ra1, dec1, ra2, dec2])
    cos_theta = np.sin(dec1) * np.sin(dec2) + np.cos(dec1) * np.cos(dec2) * np.cos(
        ra1 - ra2
    )
    return np.degrees(np.arccos(np.clip(cos_theta, -1.0, 1.0)))


# ── 배경 차분 ────────────────────────────────────────────────────────────────

def make_diff(image_data: np.ndarray) -> tuple[np.ndarray | None, np.ndarray | None]:
    """
    sep.Background 로 배경을 추정해 차분한 뒤 uint8 로 정규화한다.
    sep 실패 시 GaussianBlur fallback.

    Returns:
        (diff_float32, diff_uint8)  또는  (None, None) — 이미지가 너무 어두울 때
    """
    try:
        bkg = sep.Background(
            image_data.astype(np.float64), bw=64, bh=64, fw=3, fh=3
        )
        diff = np.clip(image_data - bkg.back(), 0, None).astype(np.float32)
    except Exception:
        blur = cv2.GaussianBlur(image_data.astype(np.float32), (101, 101), 0)
        diff = np.clip(image_data - blur, 0, None)

    p_high = np.percentile(diff, 99.9)
    if p_high == 0:
        return None, None

    diff_uint8 = np.clip(diff / p_high * 255, 0, 255).astype(np.uint8)
    return diff, diff_uint8


# ── WCS ─────────────────────────────────────────────────────────────────────

def get_wcs_from_header(header: fits.Header) -> WCS:
    """
    FITS 헤더에서 WCS 를 읽는다.
    천구 좌표 정보가 없으면 ValueError 를 발생시킨다.
    """
    wcs = WCS(header)
    if not wcs.has_celestial:
        raise ValueError("FITS 헤더에 WCS(천구 좌표) 정보가 없습니다.")
    return wcs


def save_wcs_to_fits(fits_path: str, wcs: WCS) -> None:
    """plate solving 결과 WCS 를 원본 FITS 헤더에 저장한다."""
    wcs_header = wcs.to_header(relax=True)
    with fits.open(fits_path, mode="update") as hdul:
        for hdu in hdul:
            if hdu.data is not None:
                for key, value in wcs_header.items():
                    hdu.header[key] = value
                hdul.flush()
                return
    raise ValueError(f"데이터 HDU 없음: {fits_path}")


# ── 파일 유틸 ────────────────────────────────────────────────────────────────

def is_fits_file(filename: str) -> bool:
    """파일 확장자가 FITS 계열인지 확인한다."""
    return os.path.splitext(filename)[1].lower() in (".fits", ".fit", ".fts")