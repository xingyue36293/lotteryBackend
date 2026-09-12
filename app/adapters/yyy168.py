"""168yyy.net 适配器 —— 极速赛车 / 澳洲幸运5 等 gid 体系彩种。

上游：``GET /api/lottery.php?action=history&gid={gid}&limit={limit}``

返回结构（非 ``errorCode`` 包装）::

    {ok, server_time, game: {gid, name, ..., latest: {...}, next: {...}}, data: [...]}

特点：**一次请求同时拿到最新一期、下期预告和历史记录**，是覆盖彩种最多、
信息最完整的数据源，因此作为首选数据源。
"""

from __future__ import annotations

from typing import Any, Mapping

from app.adapters.base import BaseAdapter, UpstreamError, build_draw, build_next, pick_text
from app.config import LotteryConfig
from app.models import DrawResult, NextDraw

PATH = "/api/lottery.php"


def draw_from_yyy168(record: Mapping[str, Any]) -> DrawResult:
    """``issue / draw_time / balls / summary`` 这一套字段的映射。

    注意 ``summary.big_small`` / ``dragon_tiger`` 在六合彩类彩种上可能是空串，
    这里统一收敛成 ``None``。
    """
    summary = record.get("summary")
    summary = summary if isinstance(summary, Mapping) else {}
    balls = record.get("balls")
    code_text = ",".join(str(n) for n in balls) if isinstance(balls, list) and balls else None
    return build_draw(
        issue=record.get("issue"),
        draw_time=record.get("draw_time"),
        code=balls,
        code_text=code_text,
        sum_value=summary.get("sum"),
        odd_even=pick_text(summary.get("odd_even"), ("单", "双")),  # type: ignore[arg-type]
        big_small=pick_text(summary.get("big_small"), ("大", "小", "和")),  # type: ignore[arg-type]
        dragon_tiger=pick_text(summary.get("dragon_tiger"), ("龙", "虎", "和")),  # type: ignore[arg-type]
    )


class Yyy168Adapter(BaseAdapter):
    source = "yyy168"

    async def _fetch(self, config: LotteryConfig, limit: int) -> Mapping[str, Any]:
        if config.gid is None:
            raise UpstreamError(
                f"{config.name} 缺少 gid 配置",
                code="invalid_config",
                detail={"lottery_id": config.id},
            )
        payload = await self._request(PATH, {"action": "history", "gid": config.gid, "limit": limit})
        if not isinstance(payload, Mapping):
            raise UpstreamError(
                f"上游返回结构异常：{self.source}{PATH}", detail={"payload": payload}
            )
        if not payload.get("ok"):
            raise UpstreamError(
                f"{config.name} 上游返回 ok=false",
                code="upstream_no_data",
                detail={"lottery_id": config.id, "source": self.source, "endpoint": PATH},
            )
        return payload

    async def fetch_latest(self, config: LotteryConfig) -> tuple[DrawResult, NextDraw | None]:
        payload = await self._fetch(config, limit=1)
        game = payload.get("game")
        game = game if isinstance(game, Mapping) else {}

        latest = game.get("latest")
        if not isinstance(latest, Mapping):
            # 兜底：game.latest 缺失时用 data[0]
            records = payload.get("data") or []
            if not records:
                raise UpstreamError(
                    f"{config.name} 上游暂无数据",
                    code="upstream_no_data",
                    detail={"lottery_id": config.id, "source": self.source, "endpoint": PATH},
                )
            latest = records[0]

        nxt = game.get("next")
        nxt = nxt if isinstance(nxt, Mapping) else {}
        return draw_from_yyy168(latest), build_next(nxt.get("issue"), nxt.get("draw_time"))

    async def fetch_history(self, config: LotteryConfig, limit: int) -> list[DrawResult]:
        payload = await self._fetch(config, limit=limit)
        records = self._ensure_records(payload.get("data"), config, endpoint=PATH)
        return [draw_from_yyy168(record) for record in self._slice(records, limit)]
