"""api.chuanqiking.com 适配器 —— 哈希分分彩 / 奇趣腾讯分分彩 / 重庆时时彩 等。

上游（注意：该数据源路径**没有** ``.do`` 后缀）：
- ``GET /CQShiCai/getBaseCQShiCai``     单期详情；不传 ``issue`` 时返回当前状态快照
- ``GET /CQShiCai/getBaseCQShiCaiList`` 当天列表，时间倒序

字段映射与流程复用 :class:`~app.adapters.base.SscSnapshotAdapter`。
"""

from __future__ import annotations

from app.adapters.base import SscSnapshotAdapter

DETAIL_PATH = "/CQShiCai/getBaseCQShiCai"
LIST_PATH = "/CQShiCai/getBaseCQShiCaiList"


class ChuanqikingAdapter(SscSnapshotAdapter):
    source = "chuanqiking"

    DETAIL_PATH = DETAIL_PATH
    LIST_PATH = LIST_PATH
