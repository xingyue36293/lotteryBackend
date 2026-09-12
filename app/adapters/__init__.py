"""适配器注册表。

**新增数据源**才需要动这里：写一个 :class:`~app.adapters.base.BaseAdapter`
子类，然后在 :data:`ADAPTERS` 里登记。
**新增彩种**不用改这里，只要在 ``app.config.LOTTERY_TABLE`` 加一行。
"""

from __future__ import annotations

from app.adapters.apiote122 import Apiote122Adapter
from app.adapters.base import (
    BaseAdapter,
    EnvelopeAdapter,
    SscSnapshotAdapter,
    UpstreamError,
    close_client,
    get_client,
)
from app.adapters.chuanqiking import ChuanqikingAdapter
from app.adapters.pks import PksAdapter
from app.adapters.yyy168 import Yyy168Adapter
from app.config import LOTTERY_TABLE, get_settings


def _create_adapters() -> dict[str, BaseAdapter]:
    """按配置创建各数据源适配器（每个数据源一个实例，进程内复用）。"""
    settings = get_settings()
    return {
        "yyy168": Yyy168Adapter(settings.yyy168_base_url),
        "pks": PksAdapter(settings.pks_base_urls),
        "chuanqiking": ChuanqikingAdapter(settings.chuanqiking_base_url),
        "apiote122": Apiote122Adapter(settings.apiote122_base_url),
    }


#: 数据源标识 -> 适配器实例
ADAPTERS: dict[str, BaseAdapter] = _create_adapters()

# 导入期自检：彩种名称表里引用的适配器必须都已登记
_missing = sorted({item.adapter for item in LOTTERY_TABLE if item.adapter not in ADAPTERS})
if _missing:
    raise ValueError(f"彩种名称表引用了未登记的适配器：{_missing}")


def get_adapter(name: str) -> BaseAdapter:
    """按适配器名称取实例。"""
    try:
        return ADAPTERS[name]
    except KeyError:  # pragma: no cover - 导入期已自检过
        raise UpstreamError(
            f"未登记的适配器：{name}", code="invalid_config", detail={"adapter": name}
        ) from None


__all__ = [
    "ADAPTERS",
    "Apiote122Adapter",
    "BaseAdapter",
    "ChuanqikingAdapter",
    "EnvelopeAdapter",
    "PksAdapter",
    "SscSnapshotAdapter",
    "UpstreamError",
    "Yyy168Adapter",
    "close_client",
    "get_adapter",
    "get_client",
]
