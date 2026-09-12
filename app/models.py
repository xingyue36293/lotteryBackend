"""统一返回模型（Pydantic v2）。

所有彩种、所有数据源最终都归一化成这里的模型，客户端无需关心上游字段差异。

归一化约定
----------
- ``issue``      期号统一为字符串（上游有的是 int，有的是 str）
- ``code``       开奖号码统一为 int 列表（上游有的是 ``"10,08,03"``，有的已是数组）
- ``sum``        冠亚和 / 号码总和（上游字段名有 ``sum`` / ``sumFS`` / ``sumNum`` 三种）
- 分析字段统一成中文标签，避免暴露上游的 0/1/2 编码
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

#: 单双
OddEven = Literal["单", "双"]
#: 大小
BigSmall = Literal["大", "小", "和"]
#: 龙虎
DragonTiger = Literal["龙", "虎", "和"]


class DrawResult(BaseModel):
    """一期开奖结果（latest 与 history 共用）。"""

    model_config = ConfigDict(frozen=True)

    issue: str = Field(description="期号")
    draw_time: str | None = Field(default=None, description="开奖时间")
    code: list[int] = Field(default_factory=list, description="开奖号码（已解析为整数）")
    code_text: str | None = Field(default=None, description="上游原始号码串，如 '10,08,03'")
    sum: int | None = Field(default=None, description="冠亚和 / 号码总和")
    sum_odd_even: OddEven | None = Field(default=None, description="冠亚和单双")
    sum_big_small: BigSmall | None = Field(default=None, description="冠亚和大小")
    dragon_tiger: DragonTiger | None = Field(default=None, description="龙虎（冠军维度）")


class NextDraw(BaseModel):
    """下一期预告。"""

    model_config = ConfigDict(frozen=True)

    issue: str | None = Field(default=None, description="下一期期号")
    draw_time: str | None = Field(default=None, description="下一期预计开奖时间")


class LatestResponse(BaseModel):
    """``GET /lottery/{id}/latest`` 的响应。"""

    id: str = Field(description="彩种稳定 ID")
    name: str = Field(description="彩种名称")
    source: str = Field(description="实际命中的数据源")
    latest: DrawResult = Field(description="最新一期")
    next: NextDraw | None = Field(default=None, description="下一期；上游不提供时为 null")


class HistoryResponse(BaseModel):
    """``GET /lottery/{id}/history`` 的响应。"""

    id: str = Field(description="彩种稳定 ID")
    name: str = Field(description="彩种名称")
    source: str = Field(description="实际命中的数据源")
    limit: int = Field(description="本次请求的条数上限")
    count: int = Field(description="实际返回条数")
    history: list[DrawResult] = Field(description="历史开奖，时间倒序")


class LotteryInfo(BaseModel):
    """彩种名称表中的一行（对外暴露）。"""

    id: str
    name: str
    source: str = Field(description="主数据源")
    adapter: str = Field(description="处理该数据源的适配器")
    gid: int | None = Field(default=None, description="168yyy.net 的 gid 参数")
    lot_code: int | str | None = Field(default=None, description="上游 lotCode 参数")
    upstream_code: str | None = Field(default=None, description="上游语义代码")
    category: str | None = Field(default=None, description="玩法类别")
    status: Literal["ok", "empty", "unsupported"] = Field(
        description="上游可用性实测结果：ok=有数据；empty=编号有效但当前无数据；unsupported=上游拒绝该编号"
    )
    note: str | None = Field(default=None, description="备注")


class LotteriesResponse(BaseModel):
    """``GET /lottery`` 的响应：彩种名称表 + 统计。"""

    count: int = Field(description="彩种总数")
    available: int = Field(description="实测可用的彩种数（status=ok）")
    by_source: dict[str, int] = Field(description="各数据源的彩种数")
    lotteries: list[LotteryInfo]


class ErrorDetail(BaseModel):
    """统一错误体。"""

    code: str = Field(description="错误码：invalid_parameter / unknown_lottery / upstream_error / upstream_no_data")
    message: str = Field(description="错误说明")
    detail: Any | None = Field(default=None, description="附加信息，如彩种 ID、上游地址")


class ErrorResponse(BaseModel):
    """统一错误响应结构，所有非 2xx 响应都长这样。"""

    error: ErrorDetail = Field(description="错误详情")
