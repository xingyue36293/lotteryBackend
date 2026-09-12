"""api.apiote122.com 适配器 —— 澳洲幸运5 / 幸运时时彩 / SG时时彩 / 台湾5分彩。

上游：
- ``GET /CQShiCai/getBaseCQShiCai.do``     单期详情；不传 ``issue`` 时返回当前状态快照
- ``GET /CQShiCai/getBaseCQShiCaiList.do`` 当天列表，时间倒序

字段映射与流程复用 :class:`~app.adapters.base.SscSnapshotAdapter`。
"""

from __future__ import annotations

from app.adapters.base import SscSnapshotAdapter

DETAIL_PATH = "/CQShiCai/getBaseCQShiCai.do"
LIST_PATH = "/CQShiCai/getBaseCQShiCaiList.do"


class Apiote122Adapter(SscSnapshotAdapter):
    source = "apiote122"

    DETAIL_PATH = DETAIL_PATH
    LIST_PATH = LIST_PATH
