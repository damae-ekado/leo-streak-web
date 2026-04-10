# -*- coding: utf-8 -*-
"""
detector.py
LEO 위성 streak 검출 파이프라인.
  1. sep.Background 배경 차분
  2. 별 마스킹 (sep.extract)
  3. 밝기 필터
  4. HoughLinesP
  5. 연속성 필터
  6. 중복 선분 병합
"""

import numpy as np
import cv2
import sep

from app.utils import make_diff

# ── 기본 파라미터 ────────────────────────────────────────────────────────────

DEFAULT_PARAMS = dict(
    brightness_min=40,
    brightness_max=80,
    star_thresh=17.0,
    min_length_frac=0.02,
    max_length_frac=1.0,
    max_satellite_streaks=3,
    min_fill=0.3,
    min_brightness=6,
    max_gap_ratio=0.25,
    max_cv=1.2,
    merge_angle_thresh=10,
    merge_dist_thresh=30,
)


# ── 선분 병합 ────────────────────────────────────────────────────────────────

def merge_streaks(
    streaks: list[tuple],
    angle_thresh: float = 10,
    dist_thresh: float = 30,
) -> list[tuple]:
    """
    비슷한 방향·위치의 선분을 SVD 로 하나의 선분으로 합친다.

    Args:
        streaks: [(x1, y1, x2, y2, length), ...]
    Returns:
        병합된 [(x1, y1, x2, y2, length), ...]
    """
    if not streaks:
        return []

    def line_angle(x1, y1, x2, y2):
        return np.degrees(np.arctan2(y2 - y1, x2 - x1)) % 180

    def line_center(x1, y1, x2, y2):
        return (x1 + x2) / 2, (y1 + y2) / 2

    merged = []
    used = [False] * len(streaks)

    for i, s1 in enumerate(streaks):
        if used[i]:
            continue
        group = [s1]
        used[i] = True
        a1 = line_angle(*s1[:4])
        cx1, cy1 = line_center(*s1[:4])

        for j, s2 in enumerate(streaks):
            if used[j]:
                continue
            a2 = line_angle(*s2[:4])
            cx2, cy2 = line_center(*s2[:4])
            angle_diff = abs(a1 - a2)
            if angle_diff > 90:
                angle_diff = 180 - angle_diff
            center_dist = np.hypot(cx1 - cx2, cy1 - cy2)
            if angle_diff < angle_thresh and center_dist < dist_thresh:
                group.append(s2)
                used[j] = True

        all_pts = np.array(
            [(s[0], s[1]) for s in group] + [(s[2], s[3]) for s in group],
            dtype=float,
        )
        mean = all_pts.mean(axis=0)
        _, _, vt = np.linalg.svd(all_pts - mean)
        direction = vt[0]
        proj = (all_pts - mean) @ direction
        min_pt = mean + proj.min() * direction
        max_pt = mean + proj.max() * direction
        x1n, y1n = int(min_pt[0]), int(min_pt[1])
        x2n, y2n = int(max_pt[0]), int(max_pt[1])
        length = np.hypot(x2n - x1n, y2n - y1n)
        merged.append((x1n, y1n, x2n, y2n, length))

    return merged


# ── 메인 검출 함수 ───────────────────────────────────────────────────────────

def detect_streaks(
    image_data: np.ndarray,
    brightness_min: int = DEFAULT_PARAMS["brightness_min"],
    brightness_max: int = DEFAULT_PARAMS["brightness_max"],
    star_thresh: float = DEFAULT_PARAMS["star_thresh"],
    min_length_frac: float = DEFAULT_PARAMS["min_length_frac"],
    max_length_frac: float = DEFAULT_PARAMS["max_length_frac"],
    max_satellite_streaks: int = DEFAULT_PARAMS["max_satellite_streaks"],
    min_fill: float = DEFAULT_PARAMS["min_fill"],
    min_brightness: int = DEFAULT_PARAMS["min_brightness"],
    max_gap_ratio: float = DEFAULT_PARAMS["max_gap_ratio"],
    max_cv: float = DEFAULT_PARAMS["max_cv"],
    merge_angle_thresh: float = DEFAULT_PARAMS["merge_angle_thresh"],
    merge_dist_thresh: float = DEFAULT_PARAMS["merge_dist_thresh"],
) -> list[tuple[int, int, int, int, float]]:
    """
    배경 차분된 이미지에서 LEO 위성 streak 를 검출한다.

    Returns:
        [(x1, y1, x2, y2, length_px), ...]  길이 내림차순, 최대 max_satellite_streaks 개
    """
    h, w = image_data.shape
    diag = np.hypot(h, w)
    min_length_px = int(diag * min_length_frac)
    max_length_px = int(diag * max_length_frac)

    # 1. 배경 차분
    _, diff_uint8 = make_diff(image_data)
    if diff_uint8 is None:
        return []

    # 2. 별 마스킹
    try:
        bkg_rms = np.std(diff_uint8.astype(float))
        sources = sep.extract(diff_uint8.astype(float), thresh=star_thresh, err=bkg_rms)
        mask = np.zeros(diff_uint8.shape, dtype=bool)
        for src in sources:
            sep.mask_ellipse(mask, src["x"], src["y"], src["a"] * 4, src["b"] * 4, src["theta"])
        diff_masked = diff_uint8.copy()
        diff_masked[mask] = 0
    except Exception:
        diff_masked = diff_uint8.copy()

    # 3. 밝기 필터
    diff_masked[diff_masked < brightness_min] = 0
    diff_masked[diff_masked > brightness_max] = 0

    # 4. HoughLinesP
    blurred = cv2.GaussianBlur(diff_masked, (3, 3), 0)
    lines = cv2.HoughLinesP(
        blurred,
        rho=1,
        theta=np.pi / 180,
        threshold=5,
        minLineLength=min_length_px,
        maxLineGap=30,
    )
    if lines is None:
        return []

    # 5. 연속성 필터
    def _max_consecutive_dark(bright_mask: np.ndarray) -> int:
        max_gap = cur = 0
        for b in bright_mask:
            cur = (cur + 1) if not b else 0
            max_gap = max(max_gap, cur)
        return max_gap

    def _is_real_streak(x1, y1, x2, y2) -> bool:
        length = int(np.hypot(x2 - x1, y2 - y1))
        if length == 0:
            return False
        xs = np.linspace(x1, x2, length).astype(int)
        ys = np.linspace(y1, y2, length).astype(int)
        valid = (xs >= 0) & (xs < diff_masked.shape[1]) & (ys >= 0) & (ys < diff_masked.shape[0])
        xs, ys = xs[valid], ys[valid]
        if len(xs) == 0:
            return False
        vals = diff_masked[ys, xs]
        bright = vals > min_brightness

        if bright.sum() / len(vals) < min_fill:
            return False
        if _max_consecutive_dark(bright) > length * max_gap_ratio:
            return False
        bv = vals[bright]
        if len(bv) < 3:
            return False
        if np.std(bv) / (np.mean(bv) + 1e-6) > max_cv:
            return False
        return True

    streaks = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        seg_len = np.hypot(x2 - x1, y2 - y1)
        if seg_len > max_length_px:
            continue
        if _is_real_streak(x1, y1, x2, y2):
            streaks.append((x1, y1, x2, y2, seg_len))

    # 6. 병합 + 정렬
    streaks = merge_streaks(streaks, angle_thresh=merge_angle_thresh, dist_thresh=merge_dist_thresh)
    streaks.sort(key=lambda s: s[4], reverse=True)
    return streaks[:max_satellite_streaks]


# ── 캘리브레이션 ─────────────────────────────────────────────────────────────

def calibrate_from_sample(
    image_data: np.ndarray,
    x1: int, y1: int,
    x2: int, y2: int,
) -> dict | None:
    """
    사용자가 지정한 streak 샘플 좌표로부터 최적 파라미터를 자동 계산한다.

    Returns:
        {'brightness_min', 'brightness_max', 'min_length_frac', 'max_length_frac'}
        또는 None (배경 차분 실패 시)
    """
    _, diff_uint8 = make_diff(image_data)
    if diff_uint8 is None:
        return None

    length = int(np.hypot(x2 - x1, y2 - y1))
    if length == 0:
        return None

    xs = np.linspace(x1, x2, length).astype(int)
    ys = np.linspace(y1, y2, length).astype(int)
    valid = (
        (xs >= 0) & (xs < diff_uint8.shape[1]) &
        (ys >= 0) & (ys < diff_uint8.shape[0])
    )
    vals = diff_uint8[ys[valid], xs[valid]]

    noise_floor = np.mean(diff_uint8) + 2.0 * np.std(diff_uint8)
    streak_vals = vals[vals > noise_floor]
    if len(streak_vals) < 5:
        streak_vals = vals[vals > 0]
    if len(streak_vals) == 0:
        streak_vals = np.array([1])

    diag = np.hypot(*diff_uint8.shape)

    return {
        "brightness_min": max(0, int(np.percentile(streak_vals, 30))),
        "brightness_max": min(255, int(np.percentile(streak_vals, 90))),
        "min_length_frac": float(length * 0.8 / diag),
        "max_length_frac": float(length * 1.5 / diag),
    }