from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import SessionLocal, init_db
from .routers.activity import router as activity_router
from .routers.approvals import router as approvals_router
from .routers.assets import router as assets_router
from .routers.audits import router as audits_router
from .routers.dashboard import router as dashboard_router
from .routers.guidelines import router as guidelines_router
from .routers.health import router as health_router
from .services.guideline_service import seed_default_guidelines

app = FastAPI(
    title='BrandGuard AI 2.0 API',
    version='0.1.0',
    description='Local API for the BrandGuard AI dashboard and asset review workflow.',
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            'FRONTEND_ORIGINS',
            'http://localhost:5173,http://127.0.0.1:5173',
        ).split(',')
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(health_router)
app.include_router(dashboard_router)
app.include_router(guidelines_router)
app.include_router(assets_router)
app.include_router(audits_router)
app.include_router(approvals_router)
app.include_router(activity_router)


@app.on_event('startup')
def startup_event() -> None:
    init_db()
    db = SessionLocal()
    try:
        seed_default_guidelines(db)
    finally:
        db.close()


@app.get('/')
def read_root() -> dict[str, str]:
    return {'message': 'BrandGuard AI API is running'}
