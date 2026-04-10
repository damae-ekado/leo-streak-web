# -*- coding: utf-8 -*-
"""
main.py
FastAPI 애플리케이션 진입점.

실행:
  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import router

app = FastAPI(
    title="LEO Streak Detector API",
    description="FITS 파일에서 LEO 위성 streak 를 자동 검출하는 REST API",
    version="1.0.0",
)

# ── CORS (React dev server :5173 허용) ───────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev
        "http://localhost:3000",   # CRA / 기타
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 라우터 등록 ──────────────────────────────────────────────────────────────
app.include_router(router, prefix="/api")


# ── 루트 ────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "service": "LEO Streak Detector API",
        "docs": "/docs",
        "health": "/api/health",
    }