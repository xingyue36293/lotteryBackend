"""适配器公共能力：连接池、重试、orjson 解析、字段归一化。

设计要点
--------
- **全局连接池**：整个进程共用一个 ``httpx.AsyncClient``，在应用关闭时统一释放。
- **重试**：``upstream_retries`` 次退避重试；线路池（pks）会按域名顺序轮换。
- **gzip**：统一带上 ``Accept-Encoding``，httpx 自动解压后再用 orjson 解析 ``response.content``。
- **归一化**：上游的 0/1/2 编码在这里映射成中文标签，各适配器只做「字段名 -> 统一字段」的搬运。
"""

from __future__ import annotations

import asyncio
from typing import Any, Iterable, Mapping, Sequence

import httpx
import orjson

from app.config import LotteryConfig, Settings, get_settings
from app.models import BigSmall, DragonTiger, DrawResult, NextDraw, OddEven

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:155.0) Gecko/20100101 Firefox/155.0"
)
ACCEPT_LANGUAGE = "zh-CN,zh;q=0.9,zh-TW;q=0.8,zh-HK;q=0.7,en-US;q=0.6,en;q=0.5"

#: 上游编码 -> 中文标签（lottery.md §1.4）
SINGLE_DOUBLE_LABELS = {1: "单", 0: "双"}
BIG_SMALL_LABELS = {1: "大", 0: "小", 2: "和"}
DRAGON_TIGER_LABELS = {0: "虎", 1: "龙", 2: "和"}


class UpstreamError(Exception):
    """上游不可用：网络错误、非 2xx、业务错误码非 0，或返回空数据。

    由 ``app.main`` 统一转换为 502 + ``ErrorResponse``。
    """

    status_code = 502

    def __init__(self, message: str, *, code: str = "upstream_error", detail: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail


_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    """返回进程内共享的 AsyncClient（懒加载，带连接池）。"""
    global _client
    if _client is None or _client.is_closed:
        settings: Settings = get_settings()
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.upstream_timeout),
            limits=httpx.Limits(
                max_connections=settings.http_max_connections,
                max_keepalive_connections=settings.http_max_keepalive_connections,
            ),
            verify=settings.upstream_verify_ssl,
            follow_redirects=True,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "*/*",
                "Accept-Language": ACCEPT_LANGUAGE,
                # 168 线路池与 chuanqiking 要求客户端支持压缩，否则返回 422
                "Accept-Encoding": "gzip, deflate",
            },
        )
    return _client


async def close_client() -> None:
    """释放连接池，应用关闭时调用。"""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


# --------------------------------------------------------------------------- #
# 归一化工具
# --------------------------------------------------------------------------- #
def to_int(value: Any) -> int | None:
    """尽最大努力把上游值转成 int，失败返回 None。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        try:
            return int(float(text))
        except ValueError:
            return None


def parse_code(value: Any) -> list[int]:
    """把 ``"10,08,03"`` / ``"10 08 03"`` / ``[10, 8, 3]`` 统一解析成 ``[10, 8, 3]``。"""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [n for n in (to_int(item) for item in value) if n is not None]
    text = str(value).strip()
    if not text:
        return []
    for separator in (",", " ", "，", "|"):
        if separator in text:
            text = text.replace(separator, ",")
    return [n for n in (to_int(part) for part in text.split(",")) if n is not None]


def pick_label(mapping: Mapping[int, str], value: Any) -> str | None:
    """查表拿中文标签；上游返回空串或未知值时返回 None。"""
    number = to_int(value)
    if number is None:
        return None
    return mapping.get(number)


def pick_text(value: Any, allowed: Iterable[str]) -> str | None:
    """上游已经返回中文时，校验取值合法性。"""
    if value is None:
        return None
    text = str(value).strip()
    return text if text in allowed else None


def build_draw(
    *,
    issue: Any,
    draw_time: Any,
    code: Any,
    code_text: Any = None,
    sum_value: Any = None,
    odd_even: OddEven | None = None,
    big_small: BigSmall | None = None,
    dragon_tiger: DragonTiger | None = None,
) -> DrawResult:
    """构造统一的 DrawResult，集中处理缺失值与类型收敛。"""
    text = str(code_text).strip() if code_text not in (None, "") else None
    if text is None and code is not None and not isinstance(code, (list, tuple)):
        raw = str(code).strip()
        text = raw or None
    return DrawResult(
        issue=str(issue).strip() if issue is not None else "",
        draw_time=str(draw_time).strip() if draw_time not in (None, "") else None,
        code=parse_code(code),
        code_text=text,
        sum=to_int(sum_value),
        sum_odd_even=odd_even,
        sum_big_small=big_small,
        dragon_tiger=dragon_tiger,
    )


def build_next(issue: Any, draw_time: Any) -> NextDraw | None:
    """构造下期预告；两者都缺失时返回 None。"""
    issue_text = str(issue).strip() if issue not in (None, "") else None
    time_text = str(draw_time).strip() if draw_time not in (None, "") else None
    if issue_text is None and time_text is None:
        return None
    return NextDraw(issue=issue_text, draw_time=time_text)


# --------------------------------------------------------------------------- #
# 适配器基类
# --------------------------------------------------------------------------- #
class BaseAdapter:
    """适配器基类：HTTP 调用 + 重试 + 字段映射的骨架。

    子类只需实现 ``fetch_latest`` / ``fetch_history``，并把上游字段映射到
    :class:`DrawResult` / :class:`NextDraw`。新增数据源才需要新增子类；
    新增彩种只要在 ``app.config.LOTTERY_TABLE`` 里加一行。
    """

    #: 数据源标识，与 LotteryConfig.source 对应
    source: str = "unknown"

    def __init__(self, base_urls: Sequence[str] | str) -> None:
        urls = [base_urls] if isinstance(base_urls, str) else list(base_urls)
        if not urls:
            raise ValueError("base_urls 不能为空")
        self._base_urls: tuple[str, ...] = tuple(urls)

    # ---- HTTP ----
    async def _request(self, path: str, params: Mapping[str, Any]) -> Any:
        """带重试与线路池轮换的 GET，返回 orjson 解析后的对象。"""
        settings = get_settings()
        attempts = max(1, settings.upstream_retries + 1)
        client = get_client()
        last_error: Exception | None = None

        for base_url in self._base_urls:
            url = f"{base_url}{path}"
            for attempt in range(1, attempts + 1):
                try:
                    response = await client.get(url, params=dict(params))
                    response.raise_for_status()
                    # httpx 已自动解压 gzip，这里直接解析原始字节
                    return orjson.loads(response.content)
                except Exception as exc:  # noqa: BLE001 - 网络/解析异常统一转 502
                    last_error = exc
                    if attempt < attempts:
                        await asyncio.sleep(settings.upstream_retry_delay)

        raise UpstreamError(
            f"上游请求失败：{self.source}{path}",
            detail={
                "source": self.source,
                "path": path,
                "params": dict(params),
                "attempts": attempts * len(self._base_urls),
                "reason": f"{type(last_error).__name__}: {last_error}",
            },
        )

    async def _request_data(self, path: str, params: Mapping[str, Any]) -> Any:
        """``{errorCode, message, result:{businessCode, data}}`` 结构的数据源用这个。

        子类若结构不同（如 168yyy），直接调用 :meth:`_request` 即可。
        """
        payload = await self._request(path, params)
        if not isinstance(payload, Mapping):
            raise UpstreamError(f"上游返回结构异常：{self.source}{path}", detail=payload)

        error_code = payload.get("errorCode")
        if error_code not in (0, None):
            raise UpstreamError(
                f"上游错误：{payload.get('message') or error_code}",
                detail={"source": self.source, "path": path, "errorCode": error_code},
            )

        result = payload.get("result")
        if not isinstance(result, Mapping):
            # 部分接口直接返回 {code, msg}（如 chuanqiking 的 lotCode Error）
            message = payload.get("msg") or payload.get("message")
            if message:
                raise UpstreamError(
                    f"上游错误：{message}",
                    code="unsupported_lot_code",
                    detail={"source": self.source, "path": path, "response": dict(payload)},
                )
            raise UpstreamError(f"上游返回结构异常：{self.source}{path}", detail=payload)

        business_code = result.get("businessCode")
        if business_code not in (0, None):
            raise UpstreamError(
                f"上游业务错误：{result.get('message') or business_code}",
                detail={"source": self.source, "path": path, "businessCode": business_code},
            )
        return result.get("data")

    # ---- 子类实现 ----
    async def fetch_latest(self, config: LotteryConfig) -> tuple[DrawResult, NextDraw | None]:
        """返回（最新一期，下期预告）。"""
        raise NotImplementedError

    async def fetch_history(self, config: LotteryConfig, limit: int) -> list[DrawResult]:
        """返回最近 limit 期，时间倒序。"""
        raise NotImplementedError

    # ---- 公共工具 ----
    @staticmethod
    def _ensure_records(data: Any, config: LotteryConfig, *, endpoint: str) -> list[Mapping[str, Any]]:
        """上游没给数据时抛统一错误，而不是静默返回空列表。"""
        if isinstance(data, list) and data:
            return [item for item in data if isinstance(item, Mapping)]
        raise UpstreamError(
            f"{config.name} 上游暂无数据",
            code="upstream_no_data",
            detail={"lottery_id": config.id, "source": config.source, "endpoint": endpoint, "status": config.status},
        )

    @staticmethod
    def _slice(records: list[Mapping[str, Any]], limit: int) -> list[Mapping[str, Any]]:
        """上游动辄返回几百条，这里只切出需要的条数，其余直接丢弃。"""
        return records[:limit]


class EnvelopeAdapter(BaseAdapter):
    """``result.data`` 包装结构的数据源基类（apiote122 / pks / chuanqiking）。"""

    async def _data(self, path: str, params: Mapping[str, Any]) -> Any:
        return await self._request_data(path, params)


# --------------------------------------------------------------------------- #
# 时时彩系列（apiote122 / chuanqiking）共用映射与流程
# --------------------------------------------------------------------------- #
def draw_from_ssc(record: Mapping[str, Any]) -> DrawResult:
    """``preDrawIssue / preDrawTime / preDrawCode / sumNum / sumSingleDouble /
    sumBigSmall / dragonTiger`` 这一套字段的映射。

    apiote122 与 chuanqiking 的列表和单期接口字段名完全一致，共用一份映射。
    """
    return build_draw(
        issue=record.get("preDrawIssue"),
        draw_time=record.get("preDrawTime"),
        code=record.get("preDrawCode"),
        sum_value=record.get("sumNum"),
        odd_even=pick_label(SINGLE_DOUBLE_LABELS, record.get("sumSingleDouble")),  # type: ignore[arg-type]
        big_small=pick_label(BIG_SMALL_LABELS, record.get("sumBigSmall")),  # type: ignore[arg-type]
        dragon_tiger=pick_label(DRAGON_TIGER_LABELS, record.get("dragonTiger")),  # type: ignore[arg-type]
    )


class SscSnapshotAdapter(EnvelopeAdapter):
    """「单期接口免 issue 返回状态快照」的数据源基类。

    该类数据源有两个接口：

    - 单期接口：不传 ``issue`` 也返回当前状态快照 —— ``preDraw*`` 是**最新已开**，
      ``drawIssue`` / ``drawTime`` 是**下一期**。因此 latest 只需一次请求。
    - 列表接口：返回当天已开记录，时间倒序。

    快照接口不可用时，自动回退到「列表首条 + 带 issue 的单期接口」，
    且下期预告缺失不会让整个请求失败（此时 ``next`` 为 null）。
    """

    DETAIL_PATH: str = ""
    LIST_PATH: str = ""

    def _detail_params(self, config: LotteryConfig, issue: Any = None) -> dict[str, Any]:
        params: dict[str, Any] = {"lotCode": config.lot_code}
        if issue not in (None, ""):
            params["issue"] = str(issue)
        return params

    async def _snapshot(self, config: LotteryConfig) -> Mapping[str, Any]:
        data = await self._data(self.DETAIL_PATH, self._detail_params(config))
        if not isinstance(data, Mapping):
            raise UpstreamError(
                f"{config.name} 单期接口返回结构异常",
                detail={"source": self.source, "path": self.DETAIL_PATH, "payload": data},
            )
        return data

    async def _history_records(self, config: LotteryConfig) -> list[Mapping[str, Any]]:
        data = await self._data(self.LIST_PATH, {"lotCode": config.lot_code})
        return self._ensure_records(data, config, endpoint=self.LIST_PATH)

    async def fetch_latest(self, config: LotteryConfig) -> tuple[DrawResult, NextDraw | None]:
        try:
            snapshot = await self._snapshot(config)
        except UpstreamError:
            return await self._latest_from_history(config)

        draw = draw_from_ssc(snapshot)
        if not draw.issue:
            return await self._latest_from_history(config)
        return draw, build_next(snapshot.get("drawIssue"), snapshot.get("drawTime"))

    async def _latest_from_history(self, config: LotteryConfig) -> tuple[DrawResult, NextDraw | None]:
        """快照不可用时的回退：列表首条即最新一期，再补一次带 issue 的单期接口。"""
        records = await self._history_records(config)
        first = self._slice(records, 1)[0]
        draw = draw_from_ssc(first)

        next_draw: NextDraw | None = None
        try:
            info = await self._data(self.DETAIL_PATH, self._detail_params(config, draw.issue))
            if isinstance(info, Mapping):
                next_draw = build_next(info.get("drawIssue"), info.get("drawTime"))
        except UpstreamError:
            # 最新一期已拿到，仅下期预告缺失，不视为整体失败
            next_draw = None
        return draw, next_draw

    async def fetch_history(self, config: LotteryConfig, limit: int) -> list[DrawResult]:
        records = await self._history_records(config)
        return [draw_from_ssc(record) for record in self._slice(records, limit)]
