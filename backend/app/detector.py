# -*- coding: utf-8 -*-
"""
detector.py
LEO 위성 streak 검출 파이프라인 (streak_detector_감지기_최종.py 기반)

검출 방식 두 가지:
  A) 기본 모드   : Hough + 연속성 필터  (분류기 없을 때)
  B) 분류기 모드 : DBSCAN 클러스터링 + SVD 직선 피팅 + ResNet 분류기

분류기 모델(.pt)이 서버에 업로드되어 있으면 B 방식 자동 선택.
"""

import os
import numpy as np
import cv2
import sep

from app.utils import make_diff

# ── 기본 파라미터 ────────────────────────────────────────────────────────────
DEFAULT_PARAMS = dict(
    brightness_min        = 40,
    brightness_max        = 80,
    star_thresh           = 15.0,
    min_length_frac       = 0.02,
    max_length_frac       = 1.0,
    max_satellite_streaks = 4,
    min_fill              = 0.05,
    min_brightness        = 4,
    max_gap_ratio         = 0.40,
    max_cv                = 2.0,
    merge_angle_thresh    = 10,
    merge_dist_thresh     = 30,
    # DBSCAN 분류기 모드
    dbscan_eps            = 8,
    dbscan_min_pts        = 10,
    linearity_thresh      = 0.15,
    conf_thresh           = 0.95,
    edge_margin           = 20,
)

# 전역 분류기 캐시 {model_path: (model, classes, device)}
_CLASSIFIER_CACHE: dict = {}
_CURRENT_MODEL_PATH: str | None = None


# ── 분류기 로드 ──────────────────────────────────────────────────────────────

def load_classifier(model_path: str):
    """ResNet-18 분류기를 로드하고 캐시한다."""
    global _CLASSIFIER_CACHE
    if model_path in _CLASSIFIER_CACHE:
        return _CLASSIFIER_CACHE[model_path]
    try:
        import torch
        from torch import nn
        from torchvision import models
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        ckpt   = torch.load(model_path, map_location=device)
        classes = ckpt["classes"]
        model  = models.resnet18(weights=None)
        model.fc = nn.Linear(model.fc.in_features, len(classes))
        model.load_state_dict(ckpt["model_state_dict"])
        model.to(device).eval()
        _CLASSIFIER_CACHE[model_path] = (model, classes, device)
        return model, classes, device
    except Exception as e:
        raise RuntimeError(f"분류기 로드 실패: {e}")


def set_classifier_path(path: str | None):
    global _CURRENT_MODEL_PATH
    _CURRENT_MODEL_PATH = path


def get_classifier_path() -> str | None:
    return _CURRENT_MODEL_PATH


# ── Hough 기반 병합 ──────────────────────────────────────────────────────────

def merge_streaks(streaks, angle_thresh=10, dist_thresh=30):
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
        group = [s1]; used[i] = True
        a1 = line_angle(*s1[:4]); cx1, cy1 = line_center(*s1[:4])
        for j, s2 in enumerate(streaks):
            if used[j]: continue
            a2 = line_angle(*s2[:4]); cx2, cy2 = line_center(*s2[:4])
            ad = abs(a1 - a2)
            if ad > 90: ad = 180 - ad
            if ad < angle_thresh and np.hypot(cx1-cx2, cy1-cy2) < dist_thresh:
                group.append(s2); used[j] = True
        pts = np.array([(s[0],s[1]) for s in group]+[(s[2],s[3]) for s in group], dtype=float)
        mean = pts.mean(axis=0)
        _, _, vt = np.linalg.svd(pts - mean)
        d = vt[0]; proj = (pts - mean) @ d
        p1 = mean + proj.min()*d; p2 = mean + proj.max()*d
        length = np.hypot(p2[0]-p1[0], p2[1]-p1[1])
        merged.append((int(p1[0]), int(p1[1]), int(p2[0]), int(p2[1]), length))
    return merged


# ── 모드 A: Hough + 연속성 필터 ─────────────────────────────────────────────

def _detect_hough(diff_masked, params):
    h, w = diff_masked.shape
    diag = np.hypot(h, w)
    min_px = int(diag * params["min_length_frac"])
    max_px = int(diag * params["max_length_frac"])

    blurred = cv2.GaussianBlur(diff_masked, (3, 3), 0)
    lines = cv2.HoughLinesP(blurred, 1, np.pi/180, threshold=5,
                             minLineLength=min_px, maxLineGap=30)
    if lines is None:
        return []

    def _max_gap(bright):
        mg = cur = 0
        for b in bright:
            cur = (cur+1) if not b else 0
            mg = max(mg, cur)
        return mg

    def _valid(x1, y1, x2, y2):
        length = int(np.hypot(x2-x1, y2-y1))
        if length == 0: return False
        xs = np.linspace(x1, x2, length).astype(int)
        ys = np.linspace(y1, y2, length).astype(int)
        ok = (xs>=0)&(xs<w)&(ys>=0)&(ys<h)
        xs, ys = xs[ok], ys[ok]
        if len(xs) == 0: return False
        vals = diff_masked[ys, xs]
        bright = vals > params["min_brightness"]
        if bright.sum()/len(vals) < params["min_fill"]: return False
        if _max_gap(bright) > length * params["max_gap_ratio"]: return False
        bv = vals[bright]
        if len(bv) < 3: return False
        if np.std(bv)/(np.mean(bv)+1e-6) > params["max_cv"]: return False
        return True

    streaks = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        sl = np.hypot(x2-x1, y2-y1)
        if sl > max_px: continue
        if _valid(x1, y1, x2, y2):
            streaks.append((x1, y1, x2, y2, sl))

    streaks = merge_streaks(streaks, params["merge_angle_thresh"], params["merge_dist_thresh"])
    streaks.sort(key=lambda s: s[4], reverse=True)
    return streaks[:params["max_satellite_streaks"]]


# ── 모드 B: DBSCAN + SVD + 분류기 ───────────────────────────────────────────

def _detect_dbscan(diff_uint8, diff_masked, params, model_path):
    from sklearn.cluster import DBSCAN
    import torch
    from torchvision import transforms
    from PIL import Image as PILImage

    model, classes, device = load_classifier(model_path)

    transform = transforms.Compose([
        transforms.Grayscale(num_output_channels=3),
        transforms.Resize(128), transforms.CenterCrop(128),
        transforms.ToTensor(),
        transforms.Normalize([0.5,0.5,0.5],[0.25,0.25,0.25]),
    ])

    def classify(x1, y1, x2, y2):
        sl = float(np.hypot(x2-x1, y2-y1))
        pad = max(48, int(min(sl*0.25, 160)))
        xmn = max(0,int(min(x1,x2)-pad)); xmx = min(diff_uint8.shape[1],int(max(x1,x2)+pad))
        ymn = max(0,int(min(y1,y2)-pad)); ymx = min(diff_uint8.shape[0],int(max(y1,y2)+pad))
        if xmx<=xmn or ymx<=ymn: return "non_streak", 0.0
        patch = diff_uint8[ymn:ymx, xmn:xmx].astype(np.float32)
        lo, hi = np.percentile(patch,2), np.percentile(patch,99.5)
        if hi<=lo: hi=lo+1
        p8 = np.clip((patch-lo)/(hi-lo)*255,0,255).astype(np.uint8)
        t = transform(PILImage.fromarray(p8)).unsqueeze(0).to(device)
        with torch.no_grad():
            probs = torch.softmax(model(t),dim=1)[0]
        idx = int(probs.argmax())
        return classes[idx], float(probs[idx])

    h, w = diff_masked.shape
    diag = np.hypot(h, w)
    min_len = diag * params["min_length_frac"]
    em = params["edge_margin"]

    ys, xs = np.where(diff_masked > 0)
    if len(xs) < params["dbscan_min_pts"]:
        return []

    coords = np.column_stack([xs, ys]).astype(np.float32)
    db = DBSCAN(eps=params["dbscan_eps"], min_samples=params["dbscan_min_pts"]).fit(coords)
    labels = db.labels_
    unique = set(labels) - {-1}

    results = []
    for lbl in unique:
        pts = coords[labels == lbl]
        if len(pts) < params["dbscan_min_pts"]: continue
        mean = pts.mean(axis=0)
        _, s_vals, vt = np.linalg.svd(pts - mean, full_matrices=False)
        linearity = s_vals[1] / (s_vals[0] + 1e-6)
        if linearity > params["linearity_thresh"]: continue
        d = vt[0]; proj = (pts - mean) @ d
        p1 = mean + proj.min()*d; p2 = mean + proj.max()*d
        x1, y1, x2, y2 = int(p1[0]), int(p1[1]), int(p2[0]), int(p2[1])
        sl = np.hypot(x2-x1, y2-y1)
        if sl < min_len: continue
        if (x1<=em or x1>=w-em or y1<=em or y1>=h-em or
            x2<=em or x2>=w-em or y2<=em or y2>=h-em): continue
        label, conf = classify(x1, y1, x2, y2)
        if label == "streak" and conf >= params["conf_thresh"]:
            results.append((x1, y1, x2, y2, float(sl), conf))

    results.sort(key=lambda s: s[4], reverse=True)
    return [(r[0],r[1],r[2],r[3],r[4]) for r in results[:params["max_satellite_streaks"]]]


# ── 공통 전처리 ──────────────────────────────────────────────────────────────

def _preprocess(image_data, params):
    _, diff_uint8 = make_diff(image_data)
    if diff_uint8 is None:
        return None, None
    try:
        rms = np.std(diff_uint8.astype(float))
        sources = sep.extract(diff_uint8.astype(float), thresh=params["star_thresh"], err=rms)
        mask = np.zeros(diff_uint8.shape, dtype=bool)
        for src in sources:
            sep.mask_ellipse(mask, src["x"], src["y"], src["a"]*4, src["b"]*4, src["theta"])
        diff_masked = diff_uint8.copy()
        diff_masked[mask] = 0
    except Exception:
        diff_masked = diff_uint8.copy()
    diff_masked[diff_masked < params["brightness_min"]] = 0
    diff_masked[diff_masked > params["brightness_max"]] = 0
    return diff_uint8, diff_masked


# ── 메인 진입점 ──────────────────────────────────────────────────────────────

def detect_streaks(image_data: np.ndarray, **kwargs) -> list[tuple]:
    """
    streak 검출. 분류기 모델이 설정되어 있으면 DBSCAN 모드, 아니면 Hough 모드.
    Returns: [(x1,y1,x2,y2,length_px), ...]
    """
    params = {**DEFAULT_PARAMS, **kwargs}
    diff_uint8, diff_masked = _preprocess(image_data, params)
    if diff_masked is None:
        return []

    model_path = _CURRENT_MODEL_PATH
    if model_path and os.path.exists(model_path):
        try:
            return _detect_dbscan(diff_uint8, diff_masked, params, model_path)
        except Exception:
            pass  # 분류기 실패 시 Hough fallback

    return _detect_hough(diff_masked, params)


# ── 캘리브레이션 ─────────────────────────────────────────────────────────────

def calibrate_from_sample(image_data, x1, y1, x2, y2,
                           calib_pctl_low=10, calib_pctl_high=100,
                           calib_min_mult=0.5, calib_max_mult=2.0):
    _, diff_uint8 = make_diff(image_data)
    if diff_uint8 is None:
        return None
    length = int(np.hypot(x2-x1, y2-y1))
    if length == 0:
        return None
    xs = np.linspace(x1, x2, length).astype(int)
    ys = np.linspace(y1, y2, length).astype(int)
    ok = ((xs>=0)&(xs<diff_uint8.shape[1])&(ys>=0)&(ys<diff_uint8.shape[0]))
    vals = diff_uint8[ys[ok], xs[ok]]
    noise_floor = np.mean(diff_uint8) + 2.0*np.std(diff_uint8)
    streak_vals = vals[vals > noise_floor]
    if len(streak_vals) < 5: streak_vals = vals[vals > 0]
    if len(streak_vals) == 0: streak_vals = np.array([1])
    diag = np.hypot(*diff_uint8.shape)
    return {
        "brightness_min":  max(0,   int(np.percentile(streak_vals, calib_pctl_low))),
        "brightness_max":  min(255, int(np.percentile(streak_vals, calib_pctl_high))),
        "min_length_frac": float(length * calib_min_mult / diag),
        "max_length_frac": float(length * calib_max_mult / diag),
    }