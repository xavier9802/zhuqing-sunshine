from datetime import UTC, datetime
from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings

app = FastAPI(
    title="追晴 API",
    description="四川盆地日照预测平台 API。MVP 阶段数据接入尚在初始化。",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)


class DataStatus(BaseModel):
    status: Literal["initializing", "available", "degraded"]
    provider: str
    latest_model_run: datetime | None = None
    last_checked_at: datetime
    message: str


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/api/v1/data-status", response_model=DataStatus, tags=["data"])
def data_status() -> DataStatus:
    return DataStatus(
        status="initializing",
        provider="open-meteo",
        last_checked_at=datetime.now(UTC),
        message="气象数据采集任务尚未启用，当前没有可展示的真实预测。",
    )


@app.get("/api/v1/overview", tags=["forecast"])
def overview() -> dict[str, object]:
    return {
        "status": "initializing",
        "region": "sichuan-basin",
        "timezone": "Asia/Shanghai",
        "generated_at": datetime.now(UTC).isoformat(),
        "next_sunshine_window": None,
        "daily_sunshine_hours": [],
        "coverage": None,
        "message": "等待气象模型数据接入。",
    }
