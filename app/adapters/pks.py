"""168 线路池适配器（1688455.com / 1688507.com 等）—— 北京PK10 / SG飞艇 / 英国乐透10。

上游：
- ``GET /api/pks/getPksDoubleCount.do``    当天统计；同时给出「最新已开 + 下一期」状态快照
- ``GET /api/pks/getLotteryPksInfo.do``    指定期号详情，含冠亚和与龙虎分析字段
- ``GET /api/pks/getPksHistoryList.do``    历史列表，时间倒序

该数据源的 ``/CQShiCai/*`` 路径不存在（404），只能走 ``/api/pks/*``；
域名池内多个域名指向同一后端，取数失败时按配置顺序轮换。

字段注意：冠亚和大小字段名是上游的拼写错误 ``sumBigSamll``（不是 ``sumBigSmall``），
这里保持与上游一致，不要"修正"。
"""

from __future__ import annotations

from typing import Any, Mapping

from app.adapters.base import (
    BIG_SMALL_LABELS,
    DRAGON_TIGER_LABELS,
    SINGLE_DOUBLE_LABELS,
    EnvelopeAdapter,
    UpstreamError,
    build_draw,
    build_next,
    pick_label,
)
from app.config import LotteryConfig
from app.models import DrawResult, NextDraw

DOUBLE_COUNT_PATH = "/api/pks/getPksDoubleCount.do"
INFO_PATH = "/api/pks/getLotteryPksInfo.do"
HISTORY_PATH = "/api/pks/getPksHistoryList.do"


def draw_from_pks(record: Mapping[str, Any]) -> DrawResult:
    """``preDrawIssue / preDrawTime / preDrawCode / sumFS / sumBigSamll /
    sumSingleDouble / firstDT`` 这一套字段的映射。"""
    return build_draw(
        issue=record.get("preDrawIssue"),
        draw_time=record.get("preDrawTime"),
        code=record.get("preDrawCode"),
        sum_value=record.get("sumFS"),
        odd_even=pick_label(SINGLE_DOUBLE_LABELS, record.get("sumSingleDouble")),  # type: ignore[arg-type]
        big_small=pick_label(BIG_SMALL_LABELS, record.get("sumBigSamll")),  # type: ignore[arg-type]
        dragon_tiger=pick_label(DRAGON_TIGER_LABELS, record.get("firstDT")),  # type: ignore[arg-type]
    )


class PksAdapter(EnvelopeAdapter):
    source = "pks"

    async def _soft_data(self, path: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        """可选接口：失败或无数据时返回空 dict，不打断整体请求。"""
        try:
            data = await self._data(path, params)
        except UpstreamError:
            return {}
        return data if isinstance(data, Mapping) else {}

    async def _with_analysis(
        self, config: LotteryConfig, snapshot: Mapping[str, Any]
    ) -> dict[str, Any]:
        """统计接口只给号码、不给分析字段，用单期接口补齐；补不到不影响最新一期。"""
        merged: dict[str, Any] = dict(await self._soft_data(
            INFO_PATH, {"issue": str(snapshot.get("preDrawIssue")), "lotCode": config.lot_code}
        ))
        # 期号 / 时间 / 号码以统计接口为准，保证三者属于同一期
        merged.update(
            {
                "preDrawIssue": snapshot.get("preDrawIssue"),
                "preDrawTime": snapshot.get("preDrawTime"),
                "preDrawCode": snapshot.get("preDrawCode"),
            }
        )
        return merged

    async def fetch_latest(self, config: LotteryConfig) -> tuple[DrawResult, NextDraw | None]:
        snapshot = await self._soft_data(DOUBLE_COUNT_PATH, {"lotCode": config.lot_code})

        if snapshot.get("preDrawIssue") not in (None, ""):
            # 快照齐全：一次统计接口拿到「最新一期 + 下一期」
            merged = await self._with_analysis(config, snapshot)
            return draw_from_pks(merged), build_next(
                snapshot.get("drawIssue"), snapshot.get("drawTime")
            )

        # 回退：线路池上部分彩种没有当天统计接口，用历史首条 + 单期接口补下期预告
        return await self._latest_from_history(config)

    async def _latest_from_history(
        self, config: LotteryConfig
    ) -> tuple[DrawResult, NextDraw | None]:
        data = await self._data(HISTORY_PATH, {"lotCode": config.lot_code})
        records = self._ensure_records(data, config, endpoint=HISTORY_PATH)
        draw = draw_from_pks(self._slice(records, 1)[0])

        next_draw: NextDraw | None = None
        info = await self._soft_data(
            INFO_PATH, {"issue": draw.issue, "lotCode": config.lot_code}
        )
        if info:
            next_draw = build_next(info.get("drawIssue"), info.get("drawTime"))
        return draw, next_draw

    async def fetch_history(self, config: LotteryConfig, limit: int) -> list[DrawResult]:
        data = await self._data(HISTORY_PATH, {"lotCode": config.lot_code})
        records = self._ensure_records(data, config, endpoint=HISTORY_PATH)
        return [draw_from_pks(record) for record in self._slice(records, limit)]
