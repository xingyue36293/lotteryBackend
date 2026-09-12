"""彩票开奖聚合路由。

对外只有两个按彩种取数的接口，``{lottery_id}`` 取 ``app.config.LOTTERY_TABLE``
里的稳定 ID（大小写不敏感）：

- ``GET /lottery/{id}/latest``   最新一期 + 下期预告
- ``GET /lottery/{id}/history``  最近 limit 期历史

外加一个 ``GET /lottery`` 返回彩种名称表，便于客户端拿 ID 与可用性。
"""

from __future__ import annotations

from fastapi import APIRouter, Path, Query

from app.config import get_settings
from app.models import HistoryResponse, LatestResponse, LotteriesResponse
from app.services import lottery_service

_settings = get_settings()

router = APIRouter(prefix="/lottery", tags=["lottery"])

_LOTTERY_ID_DESC = "彩种稳定 ID，见 GET /lottery，例如 aozxy5"


@router.get("", response_model=LotteriesResponse, summary="彩种名称表")
async def list_lotteries() -> LotteriesResponse:
    """返回全部彩种：稳定 ID、数据源、请求参数、适配器、上游可用性。"""
    return lottery_service.list_lotteries()


@router.get(
    "/{lottery_id}/latest",
    response_model=LatestResponse,
    summary="最新一期 + 下期预告",
)
async def get_latest(
    lottery_id: str = Path(description=_LOTTERY_ID_DESC),
) -> LatestResponse:
    """返回最新期号、最新结果、下一期期号与下一期开奖时间。

    结果缓存 3 秒。
    """
    return await lottery_service.get_latest(lottery_id)


@router.get(
    "/{lottery_id}/history",
    response_model=HistoryResponse,
    summary="最近 limit 期历史",
)
async def get_history(
    lottery_id: str = Path(description=_LOTTERY_ID_DESC),
    limit: int = Query(
        default=_settings.history_default_limit,
        ge=1,
        le=_settings.history_max_limit,
        description=f"返回条数，默认 {_settings.history_default_limit}，最大 {_settings.history_max_limit}",
    ),
) -> HistoryResponse:
    """返回最近 limit 期历史数据，时间倒序。

    结果按 ``(彩种 ID, limit)`` 缓存 30 秒；上游返回超出 limit 的记录会被直接丢弃。
    """
    return await lottery_service.get_history(lottery_id, limit)
