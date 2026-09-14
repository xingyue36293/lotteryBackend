"""彩种业务逻辑：查表 -> 选适配器 -> 取数 -> TLRU 缓存。

这一层是路由与适配器之间的唯一桥梁：

- 路由只做参数校验；
- 适配器只做「上游字段 -> 统一模型」；
- **新增彩种不需要改这里**，只要彩种名称表里加了行，本层自动生效。

缓存策略（cachetools.TLRUCache，进程内）
------------------------------------------
仅缓存 ``latest``，过期时间 = **该彩种下一期开奖时间**（开奖即出新数据，正好失效）：

- 过期时间取响应里的 ``next.draw_time``；下期预告缺失 / 已过期 / 解析失败时
  回退固定 ``cache_latest_ttl``（默认 3 秒）；
- 最长存活 ``cache_max_ttl``（默认 300 秒），防御上游下期时间异常
  （如线路池彩种数据停在旧年份、next 给到数年后）；
- ``history`` 每次实时取上游，不缓存。
"""

from __future__ import annotations

import time
from datetime import datetime

from cachetools import TLRUCache

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


def _parse_draw_time(value: str | None) -> float | None:
    """上游时间字符串（如 ``2026-09-13 01:38:40``）-> 本地时间戳；解析失败返回 None。"""
    if not value:
        return None
    text = value.strip()
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _expires_at(next_draw_time: str | None, fallback_ttl: float, now: float | None = None) -> float:
    """缓存条目的绝对过期时间（epoch 秒）。

    优先取下一期开奖时间；缺失、解析失败或已经过去时回退固定 TTL，
    并封顶 ``cache_max_ttl``，防止上游给出异常远的下期时间导致数据长期不刷新。
    """
    if now is None:
        now = time.time()
    next_ts = _parse_draw_time(next_draw_time)
    if next_ts is not None and next_ts > now:
        return min(next_ts, now + _settings.cache_max_ttl)
    return now + fallback_ttl


def _latest_ttu(key: str, value: LatestResponse, now: float) -> float:
    """TLRUCache 的 ttu：latest 条目过期于响应中的下一期开奖时间。"""
    next_time = value.next.draw_time if value.next is not None else None
    return _expires_at(next_time, _settings.cache_latest_ttl, now)


#: latest 缓存：过期于该彩种下一期开奖时间
LATEST_CACHE: TLRUCache[str, LatestResponse] = TLRUCache(
    maxsize=_settings.cache_maxsize, ttu=_latest_ttu, timer=time.time
)


def clear_caches() -> None:
    """清空缓存（测试与运维手动刷新用）。"""
    LATEST_CACHE.clear()


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
    """最近 limit 期历史，时间倒序（每次实时取上游，不缓存）。"""
    config = get_config(lottery_id)
    limit = _normalize_limit(limit)

    history = await _adapter_of(config).fetch_history(config, limit)
    return HistoryResponse(
        id=config.id,
        name=config.name,
        source=config.source,
        limit=limit,
        count=len(history),
        history=history,
    )


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

