import asyncio
import logging
import os
from contextlib import asynccontextmanager

from core.logging_setup import apply_access_log_filters, configure_logging, studio_print

configure_logging(logging.INFO)

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from comfyui import client as comfyui
from core.comfyui_settings import comfyui_http_url
from core.config import settings
from db.init_db import init_database
from routers import (
    admin,
    admin_models,
    agent,
    assets,
    audio,
    auth,
    canvas,
    canvas_ws,
    media,
    models,
    prompt,
    screenplay,
    tasks,
    teams,
    upload,
    user,
    ws,
    notifications,
    exports,
    import_document,
    style_reference,
    lut,
)
from services.redis_client import get_redis
from services.local_model_sync import sync_local_models
from services.rate_limit import check_ip_rate_limit, clear_rate_limit_keys


@asynccontextmanager
async def lifespan(application: FastAPI):
    apply_access_log_filters()
    init_database()
    current = comfyui.init_model_config(comfyui.MODEL_CONFIG_PATH)
    asyncio.create_task(sync_local_models())
    studio_print("boot", "后端启动")
    studio_print("boot", f"图像模型: {current['image_model']}")
    studio_print("boot", f"视频模型: {current['video_model']}")
    studio_print("boot", f"ComfyUI: {comfyui_http_url()}")
    if get_redis() is not None:
        cleared = clear_rate_limit_keys()
        studio_print("boot", f"Redis: 已连接（已清除 {cleared} 个限流键）")
    else:
        studio_print("boot", "Redis: 未连接（限流/顶号将降级）")
    yield
    print("AI Studio 后端关闭")


app = FastAPI(
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)


_RATE_LIMIT_SKIP_PREFIXES = (
    "/api/auth/register",
    "/api/auth/refresh",
    "/api/teams/mine",
)


@app.middleware("http")
async def ip_rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and not any(path.startswith(p) for p in _RATE_LIMIT_SKIP_PREFIXES):
        try:
            check_ip_rate_limit(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("uploads/images", exist_ok=True)
os.makedirs("uploads/videos", exist_ok=True)
os.makedirs("uploads/exports", exist_ok=True)
os.makedirs("uploads/luts", exist_ok=True)
os.makedirs("uploads/audio", exist_ok=True)

app.include_router(auth.router)
app.include_router(teams.router)
app.include_router(agent.router)
app.include_router(canvas.router)
app.include_router(canvas_ws.router)
app.include_router(user.router)
app.include_router(admin_models.router)
app.include_router(admin.router)
app.include_router(tasks.router)
app.include_router(prompt.router)
app.include_router(screenplay.router)
app.include_router(models.router)
app.include_router(media.router)
app.include_router(ws.router)
app.include_router(upload.router)
app.include_router(assets.router)
app.include_router(notifications.router)
app.include_router(exports.router)
app.include_router(import_document.router)
app.include_router(style_reference.router)
app.include_router(lut.router)
app.include_router(audio.router)

if not settings.is_production:
    from routers import debug_trace

    app.include_router(debug_trace.router)


@app.get("/")
async def root():
    return {"message": "后端启动成功"}


@app.get("/health")
@app.get("/api/health")
async def health():
    redis_ok = get_redis() is not None
    return {
        "status": "ok",
        "env": settings.app_env,
        "redis": redis_ok,
        "agent_mock_generation": settings.agent_mock_generation,
        "comfyui_url": comfyui_http_url(),
    }


if __name__ == "__main__":
    import uvicorn

    from core.logging_setup import build_uvicorn_log_config

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=7788,
        reload=not settings.is_production,
        log_config=build_uvicorn_log_config(),
    )
