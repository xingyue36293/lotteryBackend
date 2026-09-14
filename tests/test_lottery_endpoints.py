"""按彩种取数、缓存、错误映射与适配器字段映射的测试。

上游用 FakeAdapter 打桩，测试不产生任何真实网络请求。
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.adapters.base import (
    UpstreamError,
    build_next,
    draw_from_ssc,
    parse_code,
    pick_label,
    to_int,
    BIG_SMALL_LABELS,
    DRAGON_TIGER_LABELS,
    SINGLE_DOUBLE_LABELS,
)
from app.adapters.pks import draw_from_pks
from app.adapters.yyy168 import draw_from_yyy168
from app.main import app
from app.models import DrawResult, NextDraw
from app.services import lottery_service

SAMPLE_DRAW = DrawResult(
    issue="34152320",
    draw_time="2026-09-13 00:59:18",
    code=[1, 8, 4, 9, 10, 5, 3, 2, 6, 7],
    code_text="1,8,4,9,10,5,3,2,6,7",
    sum=9,
    sum_odd_even="单",
    sum_big_small="小",
    dragon_tiger="虎",
)
SAMPLE_NEXT = NextDraw(issue="34152321", draw_time="2026-09-13 01:00:33")


class FakeAdapter:
    """替身适配器：记录调用次数，可注入异常。"""

    def __init__(
        self,
        latest: tuple[DrawResult, NextDraw | None] | None = None,
        history: list[DrawResult] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.latest = latest or (SAMPLE_DRAW, SAMPLE_NEXT)
        self.history = history if history is not None else [SAMPLE_DRAW]
        self.error = error
        self.latest_calls = 0
        self.history_calls = 0
        self.last_limit: int | None = None

    async def fetch_latest(self, config: Any):
        self.latest_calls += 1
        if self.error:
            raise self.error
        return self.latest

    async def fetch_history(self, config: Any, limit: int):
        self.history_calls += 1
        self.last_limit = limit
        if self.error:
            raise self.error
        return self.history[:limit]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _clear_caches():
    lottery_service.clear_caches()
    yield
    lottery_service.clear_caches()


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch):
    """把适配器换成 FakeAdapter，并返回它以便断言调用次数。"""

    def install(fake: FakeAdapter) -> FakeAdapter:
        monkeypatch.setattr(lottery_service, "get_adapter", lambda name: fake)
        return fake

    return install


# --------------------------------------------------------------------------- #
# /{id}/latest
# --------------------------------------------------------------------------- #
def test_latest_returns_latest_and_next(client: TestClient, stub):
    stub(FakeAdapter())
    resp = client.get("/lottery/aozxy5/latest")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "aozxy5"
    assert body["name"] == "澳洲幸运5"
    assert body["source"] == "yyy168"
    assert body["latest"]["issue"] == "34152320"
    assert body["latest"]["code"] == [1, 8, 4, 9, 10, 5, 3, 2, 6, 7]
    assert body["latest"]["sum_odd_even"] == "单"
    assert body["next"] == {"issue": "34152321", "draw_time": "2026-09-13 01:00:33"}


def test_latest_next_can_be_null(client: TestClient, stub):
    """上游不提供下期预告时，next 为 null 而不是报错。"""
    stub(FakeAdapter(latest=(SAMPLE_DRAW, None)))
    body = client.get("/lottery/hxffc/latest").json()
    assert body["next"] is None


def test_lottery_id_is_case_insensitive(client: TestClient, stub):
    stub(FakeAdapter())
    assert client.get("/lottery/AOZXY5/latest").status_code == 200
    assert client.get("/lottery/HxWfC/latest").status_code == 200


# --------------------------------------------------------------------------- #
# /{id}/history
# --------------------------------------------------------------------------- #
def test_history_default_limit_is_50(client: TestClient, stub):
    fake = stub(FakeAdapter(history=[SAMPLE_DRAW] * 120))
    body = client.get("/lottery/aozxy5/history").json()

    assert fake.last_limit == 50
    assert body["limit"] == 50
    assert body["count"] == 50
    assert len(body["history"]) == 50


def test_history_respects_limit_and_slices_extra(client: TestClient, stub):
    """上游返回 300 条时只保留前 limit 条。"""
    fake = stub(FakeAdapter(history=[SAMPLE_DRAW] * 300))
    body = client.get("/lottery/hxffc/history", params={"limit": 200}).json()

    assert fake.last_limit == 200
    assert body["count"] == 200
    assert len(body["history"]) == 200


def test_history_limit_1(client: TestClient, stub):
    stub(FakeAdapter(history=[SAMPLE_DRAW] * 10))
    body = client.get("/lottery/pk10/history", params={"limit": 1}).json()
    assert body["count"] == 1
    assert body["source"] == "pks"


# --------------------------------------------------------------------------- #
# TLRU 缓存（过期时间 = 下一期开奖时间）
# --------------------------------------------------------------------------- #
def test_latest_is_cached_until_next_draw(client: TestClient, stub):
    """样例的下期时间已是过去 -> 回退固定 TTL（3 秒），窗口内命中缓存。"""
    fake = stub(FakeAdapter())
    client.get("/lottery/aozxy5/latest")
    client.get("/lottery/aozxy5/latest")
    assert fake.latest_calls == 1


def _ts(offset_seconds: float, base: float) -> str:
    return datetime.fromtimestamp(int(base) + offset_seconds).strftime("%Y-%m-%d %H:%M:%S")


def test_expires_at_uses_future_next_draw():
    now = time.time()
    assert lottery_service._expires_at(_ts(60, now), 3.0, now) == int(now) + 60


def test_expires_at_falls_back_when_next_missing_or_past():
    now = time.time()
    # 缺失 / 已过期 / 解析失败 -> 回退固定 TTL
    assert lottery_service._expires_at(None, 3.0, now) == now + 3.0
    assert lottery_service._expires_at(_ts(-60, now), 3.0, now) == now + 3.0
    assert lottery_service._expires_at("not-a-date", 3.0, now) == now + 3.0


def test_expires_at_capped_by_max_ttl():
    """上游下期时间异常远（如旧数据彩种 next 到数年后）时封顶 cache_max_ttl。"""
    now = time.time()
    assert lottery_service._expires_at(_ts(10_000, now), 3.0, now) == now + lottery_service._settings.cache_max_ttl


def test_history_is_not_cached(client: TestClient, stub):
    """history 每次实时取上游，不缓存。"""
    fake = stub(FakeAdapter(history=[SAMPLE_DRAW] * 100))
    client.get("/lottery/aozxy5/history", params={"limit": 10})
    client.get("/lottery/aozxy5/history", params={"limit": 10})
    assert fake.history_calls == 2


def test_only_latest_is_cached(client: TestClient, stub):
    fake = stub(FakeAdapter())
    client.get("/lottery/aozxy5/latest")
    client.get("/lottery/aozxy5/latest")
    client.get("/lottery/aozxy5/history")
    client.get("/lottery/aozxy5/history")
    assert (fake.latest_calls, fake.history_calls) == (1, 2)


# --------------------------------------------------------------------------- #
# 错误映射
# --------------------------------------------------------------------------- #
def test_upstream_error_returns_502(client: TestClient, stub):
    stub(FakeAdapter(error=UpstreamError("上游请求失败：yyy168/api/lottery.php")))
    resp = client.get("/lottery/aozxy5/latest")

    assert resp.status_code == 502
    body = resp.json()
    assert body["error"]["code"] == "upstream_error"
    assert "上游请求失败" in body["error"]["message"]


def test_upstream_no_data_returns_502(client: TestClient, stub):
    stub(FakeAdapter(error=UpstreamError("暂无数据", code="upstream_no_data")))
    resp = client.get("/lottery/hxffc/history")

    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "upstream_no_data"


def test_unknown_lottery_returns_422(client: TestClient, stub):
    stub(FakeAdapter())
    resp = client.get("/lottery/xxx/latest")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "unknown_lottery"


# --------------------------------------------------------------------------- #
# 适配器字段映射（纯函数）
# --------------------------------------------------------------------------- #
def test_to_int_and_parse_code():
    assert to_int("10") == 10
    assert to_int(7) == 7
    assert to_int("") is None
    assert to_int("abc") is None
    assert to_int(None) is None
    assert parse_code("10,08,03") == [10, 8, 3]
    assert parse_code("10 08 03") == [10, 8, 3]
    assert parse_code([4, "9", None]) == [4, 9]
    assert parse_code("") == []


def test_pick_label_handles_blank_and_unknown():
    assert pick_label(SINGLE_DOUBLE_LABELS, 1) == "单"
    assert pick_label(DRAGON_TIGER_LABELS, 2) == "和"
    assert pick_label(BIG_SMALL_LABELS, "") is None
    assert pick_label(BIG_SMALL_LABELS, 9) is None


def test_build_next_returns_none_when_empty():
    assert build_next(None, "") is None
    assert build_next("34152321", "") == NextDraw(issue="34152321", draw_time=None)


def test_draw_from_ssc_maps_codes_to_labels():
    """apiote122 / chuanqiking 的 0/1/2 编码要映射成中文。"""
    draw = draw_from_ssc(
        {
            "preDrawIssue": 51350101,
            "preDrawTime": "2026-09-13 00:58:40",
            "preDrawCode": "7,2,1,5,7",
            "sumNum": 22,
            "sumSingleDouble": 1,
            "sumBigSmall": 1,
            "dragonTiger": 2,
        }
    )
    assert draw.issue == "51350101"  # int 期号统一成 str
    assert draw.code == [7, 2, 1, 5, 7]
    assert draw.code_text == "7,2,1,5,7"
    assert draw.sum == 22
    assert draw.sum_odd_even == "单"
    assert draw.sum_big_small == "大"
    assert draw.dragon_tiger == "和"


def test_draw_from_pks_uses_misspelled_field():
    """上游拼写错误 sumBigSamll 必须按原名读取。"""
    draw = draw_from_pks(
        {
            "preDrawIssue": 21359001,
            "preDrawTime": "2026-09-13 00:58:40",
            "preDrawCode": "02,07,08,05,03,04,01,06,09,10",
            "sumFS": 9,
            "sumBigSamll": 1,
            "sumSingleDouble": 0,
            "firstDT": 1,
        }
    )
    assert draw.code == [2, 7, 8, 5, 3, 4, 1, 6, 9, 10]  # 前导零已去掉
    assert draw.sum == 9
    assert draw.sum_big_small == "大"
    assert draw.sum_odd_even == "双"
    assert draw.dragon_tiger == "龙"


def test_draw_from_yyy168_handles_blank_summary():
    """六合彩类彩种 summary 里是空串，应归一化成 None。"""
    draw = draw_from_yyy168(
        {
            "issue": "2026255",
            "draw_time": "2026-09-12 21:32:32",
            "balls": [36, 22, 6, 47, 39, 11, 44],
            "summary": {"sum": 205, "odd_even": "单", "big_small": "", "dragon_tiger": "", "dragon_tigers": []},
        }
    )
    assert draw.issue == "2026255"
    assert len(draw.code) == 7
    assert draw.sum == 205
    assert draw.sum_odd_even == "单"
    assert draw.sum_big_small is None
    assert draw.dragon_tiger is None


def test_draw_from_yyy168_missing_summary():
    draw = draw_from_yyy168({"issue": "1", "balls": [1, 2, 3]})
    assert draw.sum is None
    assert draw.code == [1, 2, 3]
    assert draw.code_text == "1,2,3"


# --------------------------------------------------------------------------- #
# pks 适配器：快照路径与回退路径
# --------------------------------------------------------------------------- #
PK10_RECORD = {
    "preDrawTime": "2026-09-12 23:50:40",
    "preDrawIssue": 751963,
    "preDrawCode": "01,06,03,07,02,08,05,09,04,10",
    "sumFS": 7,
    "sumBigSamll": 1,
    "sumSingleDouble": 1,
    "firstDT": 0,
    "secondDT": 1,
    "groupCode": 1,
}


def test_pks_latest_prefers_double_count_snapshot(monkeypatch: pytest.MonkeyPatch):
    """统计接口能给全「最新一期 + 下一期」时，只用两次请求（统计 + 单期补分析）。"""
    from app.adapters.pks import PksAdapter

    adapter = PksAdapter(["https://example.invalid"])
    calls: list[str] = []

    async def fake_data(path: str, params: dict):
        calls.append(path)
        if path.endswith("getPksDoubleCount.do"):
            return {
                "preDrawIssue": 21359001,
                "preDrawTime": "2026-09-13 00:58:40",
                "preDrawCode": "02,07,08,05,03,04,01,06,09,10",
                "drawIssue": 21359002,
                "drawTime": "2026-09-13 01:03:40",
            }
        return {"sumFS": 9, "sumSingleDouble": 0, "sumBigSamll": 1, "firstDT": 1}

    monkeypatch.setattr(adapter, "_data", fake_data)
    draw, nxt = asyncio.run(adapter.fetch_latest(lottery_service.get_config("pk10")))

    assert calls[0].endswith("getPksDoubleCount.do")
    assert draw.issue == "21359001"
    assert draw.sum == 9  # 分析字段来自单期接口
    assert draw.sum_odd_even == "双"
    assert draw.dragon_tiger == "龙"
    assert nxt == NextDraw(issue="21359002", draw_time="2026-09-13 01:03:40")


def test_pks_latest_falls_back_to_history(monkeypatch: pytest.MonkeyPatch):
    """线路池上部分彩种没有当天统计接口，应回退到历史首条。"""
    from app.adapters.pks import PksAdapter

    adapter = PksAdapter(["https://example.invalid"])

    async def empty(path: str, params: dict):
        return {}

    async def history(path: str, params: dict):
        return [PK10_RECORD]

    monkeypatch.setattr(adapter, "_soft_data", empty)
    monkeypatch.setattr(adapter, "_data", history)
    draw, nxt = asyncio.run(adapter.fetch_latest(lottery_service.get_config("pk10")))

    assert draw.issue == "751963"
    assert draw.code[:3] == [1, 6, 3]
    assert nxt is None  # 单期接口也拿不到时，next 降级为 null 而不是报错
