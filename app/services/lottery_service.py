"""彩种业务逻辑：查表 -> 选适配器 -> 取数 -> TTL 缓存。

这一层是路由与适配器之间的唯一桥梁：

- 路由只做参数校验；
- 适配器只做「上游字段 -> 统一模型」；
- **新增彩种不需要改这里**，只要彩种名称表里加了行，本层自动生效。

缓存策略（cachetools.TTLCache，进程内）
--------------------------------------
- ``latest``  3 秒：开奖是高频事件，缓存窗口必须远小于开奖间隔；
- ``history`` 30 秒，键为 ``(彩种 ID, limit)``。
"""

from __future__ import annotations

from cachetools import TTLCache

from app.adapters import BaseAdapter, get_adapter
from app.config import LOTTERY_INDEX, LOTTERY_TABLE, LotteryConfig, SourceKey, get_settings
from app.models import (
    DrawResult,
    HistoryResponse,
    LatestResponse,
    LotteryInfo,
    LotteriesResponse,
    NextDraw,
)

_settings = get_settings()


class LotteryError(Exception):
    """业务异常基类；``app.main`` 会把它转成统一错误结构。"""

    status_code = 422

    def __init__(self, code: str, message: str, *, status_code: int | None = None, detail: object = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.detail = detail


class UnknownLotteryError(LotteryError):
    """路由中的 {id} 不在彩种名称表里 —— 属于参数错误，返回 422。"""

    def __init__(self, lottery_id: str) -> None:
        super().__init__(
            "unknown_lottery",
            f"未知彩种 ID：{lottery_id}，可用 ID 见 GET /lottery",
            status_code=422,
            detail={"lottery_id": lottery_id},
        )


#: latest 缓存：3 秒
LATEST_CACHE: TTLCache = TTLCache(maxsize=_settings.cache_maxsize, ttl=_settings.cache_latest_ttl)
#: history 缓存：30 秒
HISTORY_CACHE: TTLCache = TTLCache(maxsize=_settings.cache_maxsize, ttl=_settings.cache_history_ttl)


def clear_caches() -> None:
    """清空缓存（测试与运维手动刷新用）。"""
    LATEST_CACHE.clear()
    HISTORY_CACHE.clear()


def get_config(lottery_id: str) -> LotteryConfig:
    """按稳定 ID 查彩种配置（大小写不敏感）。"""
    config = LOTTERY_INDEX.get(str(lottery_id).strip().lower())
    if config is None:
        raise UnknownLotteryError(lottery_id)
    return config


def _adapter_of(config: LotteryConfig) -> BaseAdapter:
    return get_adapter(config.adapter)


async def get_latest(lottery_id: str) -> LatestResponse:
    """最新一期 + 下期预告。"""
    config = get_config(lottery_id)
    cached = LATEST_CACHE.get(config.id)
    if cached is not None:
        return cached

    latest: DrawResult
    next_draw: NextDraw | None
    latest, next_draw = await _adapter_of(config).fetch_latest(config)

    response = LatestResponse(
        id=config.id,
        name=config.name,
        source=config.source,
        latest=latest,
        next=next_draw,
    )
    LATEST_CACHE[config.id] = response
    return response


async def get_history(lottery_id: str, limit: int | None = None) -> HistoryResponse:
    """最近 limit 期历史，时间倒序。"""
    config = get_config(lottery_id)
    limit = _normalize_limit(limit)
    key = (config.id, limit)
    cached = HISTORY_CACHE.get(key)
    if cached is not None:
        return cached

    history = await _adapter_of(config).fetch_history(config, limit)
    response = HistoryResponse(
        id=config.id,
        name=config.name,
        source=config.source,
        limit=limit,
        count=len(history),
        history=history,
    )
    HISTORY_CACHE[key] = response
    return response


def _normalize_limit(limit: int | None) -> int:
    """收敛 limit 到 ``[1, history_max_limit]``。"""
    if limit is None:
        return _settings.history_default_limit
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return _settings.history_default_limit
    return max(1, min(value, _settings.history_max_limit))


def _build_catalog() -> LotteriesResponse:
    """把彩种名称表转成对外结构；静态数据，导入期构造一次。"""
    lotteries = [
        LotteryInfo(
            id=config.id,
            name=config.name,
            source=config.source,
            adapter=config.adapter,
            gid=config.gid,
            lot_code=config.lot_code,
            upstream_code=config.upstream_code,
            category=config.category,
            status=config.status,
            note=config.note,
        )
        for config in LOTTERY_TABLE
    ]
    by_source: dict[str, int] = {}
    for config in LOTTERY_TABLE:
        by_source[config.source] = by_source.get(config.source, 0) + 1
    return LotteriesResponse(
        count=len(lotteries),
        available=sum(1 for config in LOTTERY_TABLE if config.status == "ok"),
        by_source=by_source,
        lotteries=lotteries,
    )


_CATALOG: LotteriesResponse = _build_catalog()


def list_lotteries() -> LotteriesResponse:
    """返回彩种名称表。"""
    return _CATALOG


def source_of(lottery_id: str) -> SourceKey:
    """便捷函数：取某彩种的主数据源。"""
    return get_config(lottery_id).source

