"""应用层测试：根路由、健康检查、彩种名称表、统一错误结构、参数校验。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import LOTTERY_TABLE, get_settings
from app.main import app


@pytest.fixture(scope="module")
def client():
    # 用上下文管理器进入，确保 lifespan 正常执行（truststore 注入 / 连接池释放）
    with TestClient(app) as test_client:
        yield test_client


def test_root(client: TestClient):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == get_settings().app_name
    assert body["version"]
    assert "/lottery/{id}/latest" in body["endpoints"]


def test_health(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_catalog_counts(client: TestClient):
    resp = client.get("/lottery")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 111
    assert body["count"] == len(LOTTERY_TABLE)
    # 主数据源分布：168yyy（gid 体系）、pks（168 线路池）、chuanqiking、apiote122
    # 「幸运飞艇」(pks 10057) 与 168yyy 的「168幸运飞艇」(g171) 为同一彩种，已合并
    assert body["by_source"] == {"yyy168": 16, "pks": 3, "chuanqiking": 28, "apiote122": 64}
    assert body["available"] == 33


def test_catalog_row_shape(client: TestClient):
    """彩种名称表必须带稳定 ID、名称、数据源、请求参数与适配器名称。"""
    body = client.get("/lottery").json()
    rows = {row["id"]: row for row in body["lotteries"]}

    row = rows["aozxy5"]
    assert row["name"] == "澳洲幸运5"
    assert row["source"] == "yyy168"
    assert row["adapter"] == "yyy168"
    assert row["gid"] == 109
    assert row["lot_code"] == 10010
    assert row["upstream_code"] == "aozxy5"
    assert row["status"] == "ok"

    # 无上游语义代码的彩种用 g{gid} 兜底
    assert rows["g107"]["gid"] == 107
    assert rows["g107"]["name"] == "北京赛车(PK10)"
    # 走 168 线路池的彩种
    assert rows["pk10"]["source"] == "pks"
    assert rows["pk10"]["lot_code"] == 10001
    # 字符串型 lotCode
    assert rows["etherssc"]["lot_code"] == "ether"


def test_catalog_ids_are_unique(client: TestClient):
    ids = [row["id"] for row in client.get("/lottery").json()["lotteries"]]
    assert len(ids) == len(set(ids))


def test_catalog_note_kept(client: TestClient):
    rows = {row["id"]: row for row in client.get("/lottery").json()["lotteries"]}
    assert "对应 apiote122 的「北京PK10」10001" in rows["g107"]["note"]


def test_unknown_lottery_returns_422(client: TestClient):
    resp = client.get("/lottery/not-a-lottery/latest")
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "unknown_lottery"
    assert body["error"]["detail"]["lottery_id"] == "not-a-lottery"


def test_limit_out_of_range_returns_422(client: TestClient):
    assert client.get("/lottery/hxffc/history", params={"limit": 0}).status_code == 422
    too_big = client.get("/lottery/hxffc/history", params={"limit": 201})
    assert too_big.status_code == 422
    assert too_big.json()["error"]["code"] == "invalid_parameter"


def test_unknown_route_uses_unified_error(client: TestClient):
    resp = client.get("/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "http_error"
