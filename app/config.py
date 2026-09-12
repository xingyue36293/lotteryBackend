"""应用配置与《彩种名称表》。

本模块包含两部分：

1. ``Settings``：运行期配置（各数据源地址、超时、重试、缓存 TTL 等），
   优先级 环境变量 > .env > 代码默认值。
2. ``LOTTERY_TABLE``：**配置驱动的彩种名称表**，新增彩种只需在这里加一行，
   路由与适配器代码无需改动。

彩种名称表字段
--------------
- ``id``            稳定 ID（路由中的 ``{id}``），不随表行号变化
- ``name``          彩种名称
- ``source``        数据源标识：yyy168 / pks / chuanqiking / apiote122
- ``adapter``       处理该数据源的适配器名称（本项目与 source 同名）
- ``gid``           168yyy.net 的请求参数
- ``lot_code``      上游的 lotCode 请求参数（168 线路池 / apiote122 / chuanqiking）
- ``upstream_code`` 上游自带的语义代码（apiote122 lotCodeType / chuanqiking 代码）
- ``category``      上游标注的玩法类别
- ``status``        上游可用性实测结果：ok / empty / unsupported
- ``note``          备注（跨数据源对应关系）

稳定 ID 生成规则
----------------
优先取上游原生语义代码（apiote122 ``lotCodeType``，其次 chuanqiking ``代码``）；
两者都没有时取 168yyy 的 ``g`` + ``gid``（如 ``g107``）。ID 大小写不敏感查找。

主数据源选择规则
----------------
优先 168yyy（一次请求即可拿到最新一期 + 下期预告 + 历史）> 168 线路池 pks >
chuanqiking > apiote122；若高优先级数据源在该彩种上实测无数据，则回退到实测可用的源。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

#: 数据源标识
SourceKey = Literal["yyy168", "pks", "chuanqiking", "apiote122"]

#: 上游可用性实测结果
#: - ok          实测可返回数据
#: - empty       上游接受该编号，但当前无数据（多为时段性）
#: - unsupported 上游拒绝该编号（lotCode Error / 空响应 / 404）
UpstreamStatus = Literal["ok", "empty", "unsupported"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Lottery Aggregator"
    debug: bool = False
    cors_origins: list[str] = ["*"]

    # ---- 上游地址 ----
    # 极速赛车等 168yyy 彩种（gid）
    yyy168_base_url: str = "https://www.168yyy.net"
    # 澳洲幸运5 等
    apiote122_base_url: str = "https://api.apiote122.com"
    # 澳洲幸运10 等，多域名线路池，按顺序重试
    pks_base_urls: list[str] = [
        "https://1688455.com",
        "https://1688507.com",
        "https://1689690.com",
        "https://1689691.com",
        "https://1689687.com",
    ]
    # 哈希分分彩等
    chuanqiking_base_url: str = "https://api.chuanqiking.com"

    # ---- 上游请求策略 ----
    upstream_timeout: float = 8.0
    upstream_retries: int = 2
    upstream_retry_delay: float = 0.3
    upstream_verify_ssl: bool = True
    # 该线路池证书在 Python 默认 CA 包下验证失败，启用后改用系统证书库
    upstream_use_truststore: bool = True

    # ---- 连接池 ----
    http_max_connections: int = 100
    http_max_keepalive_connections: int = 20

    # ---- 进程内缓存 TTL（秒）----
    cache_latest_ttl: float = 3.0
    cache_history_ttl: float = 30.0
    cache_maxsize: int = 2048

    # ---- 历史条数 ----
    history_default_limit: int = 50
    history_max_limit: int = 200


@lru_cache
def get_settings() -> Settings:
    return Settings()


@dataclass(frozen=True, slots=True)
class LotteryConfig:
    """彩种名称表中的一行。"""

    id: str
    name: str
    source: SourceKey
    adapter: str
    gid: int | None = None
    lot_code: int | str | None = None
    upstream_code: str | None = None
    category: str | None = None
    status: UpstreamStatus = "ok"
    note: str | None = None


# --------------------------------------------------------------------------- #
# 彩种名称表
# 列顺序：id / name / source / adapter / gid / lot_code / upstream_code /
#         category / status / note
# --------------------------------------------------------------------------- #
LOTTERY_TABLE: tuple[LotteryConfig, ...] = (
    # ===== 168yyy.net（gid）=====
    LotteryConfig("happyCZ", "重庆欢乐生肖", "yyy168", "yyy168", gid=101, lot_code=10060, upstream_code="happyCZ", category="时时彩", note="168yyy 归时时彩，apiote122 归其他"),
    LotteryConfig("gdklsf", "广东快乐十分", "yyy168", "yyy168", gid=103, lot_code=10005, upstream_code="gdklsf", category="快乐十分"),
    LotteryConfig("g107", "北京赛车(PK10)", "yyy168", "yyy168", gid=107, category="赛车", note="对应 apiote122 的「北京PK10」10001"),
    LotteryConfig("jisussc", "极速时时彩", "yyy168", "yyy168", gid=108, lot_code=10036, upstream_code="jisussc", category="时时彩"),
    LotteryConfig("aozxy5", "澳洲幸运5", "yyy168", "yyy168", gid=109, lot_code=10010, upstream_code="aozxy5", category="时时彩", note="168yyy 归时时彩，apiote122 归其他"),
    LotteryConfig("aozxy8", "澳洲幸运8", "yyy168", "yyy168", gid=131, lot_code=10011, upstream_code="aozxy8", category="快乐十分"),
    LotteryConfig("g132", "澳门幸运8", "yyy168", "yyy168", gid=132, category="快乐十分"),
    LotteryConfig("cqxync", "重庆幸运农场", "yyy168", "yyy168", gid=135, lot_code=10009, upstream_code="cqxync", category="快乐十分", note="apiote122 有两个编号：10009/cqxync、10050/cqqxc"),
    LotteryConfig("jisuft", "极速飞艇", "yyy168", "yyy168", gid=170, lot_code=10035, upstream_code="jisuft", category="赛车", note="chuanqiking 有「168极速飞艇」19"),
    LotteryConfig("g171", "168幸運飛艇", "yyy168", "yyy168", gid=171, category="赛车", note="chuanqiking 有「168幸运飞艇」18"),
    LotteryConfig("jisusc", "极速赛车", "yyy168", "yyy168", gid=172, lot_code=10037, upstream_code="jisusc", category="赛车", note="chuanqiking 有「168极速赛车」16"),
    LotteryConfig("aozxy10", "澳洲幸运10", "yyy168", "yyy168", gid=175, lot_code=10012, upstream_code="aozxy10", category="赛车", note="168 线路池 pks 亦提供 10012"),
    LotteryConfig("g200", "极速六合彩", "yyy168", "yyy168", gid=200, category="六合彩"),
    LotteryConfig("g201", "澳门六合彩5分", "yyy168", "yyy168", gid=201, category="六合彩", note="chuanqiking 有「澳门六合彩」5"),
    LotteryConfig("g202", "新台湾六合彩", "yyy168", "yyy168", gid=202, category="六合彩"),
    LotteryConfig("samlh", "新澳门六合彩", "yyy168", "yyy168", gid=301, upstream_code="samlh", category="六合彩"),

    # ===== 168 线路池 pks =====
    LotteryConfig("pk10", "北京PK10", "pks", "pks", lot_code=10001, upstream_code="pk10", category="PK10/飞艇/赛车", note="对应 168yyy 的「北京赛车(PK10)」107"),
    LotteryConfig("xingyft", "幸运飞艇", "pks", "pks", lot_code=10057, upstream_code="xingyft", category="PK10/飞艇/赛车", note="chuanqiking 有「168幸运飞艇」18"),
    LotteryConfig("sgAirship", "SG飞艇", "pks", "pks", lot_code=10058, upstream_code="sgAirship", category="PK10/飞艇/赛车"),
    LotteryConfig("uklotto10", "英国乐透10", "pks", "pks", lot_code=10079, upstream_code="uklotto10", category="PK10/飞艇/赛车"),

    # ===== chuanqiking（可用的分分彩/五分彩/时时彩）=====
    LotteryConfig("cctsffc", "奇趣腾讯分分彩", "chuanqiking", "chuanqiking", lot_code=11, upstream_code="cctsffc", category="时时彩"),
    LotteryConfig("cctswfc", "奇趣腾讯五分彩", "chuanqiking", "chuanqiking", lot_code=12, upstream_code="cctswfc", category="时时彩"),
    LotteryConfig("cctssfc", "奇趣腾讯十分彩", "chuanqiking", "chuanqiking", lot_code=13, upstream_code="cctssfc", category="时时彩"),
    LotteryConfig("lhnwfc", "老河內五分彩", "chuanqiking", "chuanqiking", lot_code=14, upstream_code="lhnwfc", category="时时彩"),
    LotteryConfig("cqssc", "重庆时时彩", "chuanqiking", "chuanqiking", lot_code=25, upstream_code="cqssc", category="时时彩"),
    LotteryConfig("hxffc", "哈希分分彩", "chuanqiking", "chuanqiking", lot_code=26, upstream_code="hxffc", category="时时彩"),
    LotteryConfig("hxwfc", "哈希五分彩", "chuanqiking", "chuanqiking", lot_code=27, upstream_code="hxwfc", category="时时彩"),
    LotteryConfig("hxsfc", "哈希三分彩", "chuanqiking", "chuanqiking", lot_code=29, upstream_code="hxsfc", category="时时彩"),
    LotteryConfig("bcffc", "波场分分彩", "chuanqiking", "chuanqiking", lot_code=30, upstream_code="bcffc", category="时时彩"),
    LotteryConfig("bcsfc", "波场三分彩", "chuanqiking", "chuanqiking", lot_code=31, upstream_code="bcsfc", category="时时彩"),
    LotteryConfig("bcwfc", "波场五分彩", "chuanqiking", "chuanqiking", lot_code=32, upstream_code="bcwfc", category="时时彩"),

    # ===== apiote122（可用的时时彩）=====
    LotteryConfig("xyssc", "幸运时时彩", "apiote122", "apiote122", lot_code=10059, upstream_code="xyssc", category="时时彩系列"),
    LotteryConfig("tw_5fencai", "台湾5分彩", "apiote122", "apiote122", lot_code=10064, upstream_code="tw_5fencai", category="时时彩系列", note="chuanqiking 有「台湾五分彩」7"),
    LotteryConfig("sgssc", "SG时时彩", "apiote122", "apiote122", lot_code=10075, upstream_code="sgssc", category="时时彩系列"),

    # ===== chuanqiking（编号有效、当前无数据）=====
    LotteryConfig("taiwanbg", "台湾五分彩", "chuanqiking", "chuanqiking", lot_code=7, upstream_code="taiwanbg", category="时时彩", status="empty", note="apiote122 有「台湾5分彩」10064"),
    LotteryConfig("babtffc", "币安比特分分彩", "chuanqiking", "chuanqiking", lot_code=8, upstream_code="babtffc", category="时时彩", status="empty"),
    LotteryConfig("baytffc", "币安以太分分彩", "chuanqiking", "chuanqiking", lot_code=9, upstream_code="baytffc", category="时时彩", status="empty"),
    LotteryConfig("sjwfc", "上证五分彩", "chuanqiking", "chuanqiking", lot_code=22, upstream_code="sjwfc", category="时时彩", status="empty"),
    LotteryConfig("szwfc", "深证五分彩", "chuanqiking", "chuanqiking", lot_code=23, upstream_code="szwfc", category="时时彩", status="empty"),
    LotteryConfig("hxshfc", "哈希十分彩", "chuanqiking", "chuanqiking", lot_code=28, upstream_code="hxshfc", category="时时彩", status="empty"),

    # ===== chuanqiking（上游拒绝该编号）=====
    LotteryConfig("sglh", "香港六合彩", "chuanqiking", "chuanqiking", lot_code=4, upstream_code="sglh", category="六合彩", status="unsupported"),
    LotteryConfig("amlh", "澳门六合彩", "chuanqiking", "chuanqiking", lot_code=5, upstream_code="amlh", category="六合彩", status="unsupported", note="168yyy 有「澳门六合彩5分」201"),
    LotteryConfig("jssc168", "168极速赛车", "chuanqiking", "chuanqiking", lot_code=16, upstream_code="jssc168", category="赛车", status="unsupported", note="168yyy/apiote122 有「极速赛车」172 / 10037"),
    LotteryConfig("syft168", "168幸运飞艇", "chuanqiking", "chuanqiking", lot_code=18, upstream_code="syft168", category="赛车", status="unsupported", note="168yyy 有「168幸運飛艇」171；apiote122 有「幸运飞艇」10057"),
    LotteryConfig("jsft168", "168极速飞艇", "chuanqiking", "chuanqiking", lot_code=19, upstream_code="jsft168", category="赛车", status="unsupported", note="168yyy/apiote122 有「极速飞艇」170 / 10035"),
    LotteryConfig("bk11x5", "曼谷11选5", "chuanqiking", "chuanqiking", lot_code=21, upstream_code="bk11x5", category="11选5系列", status="unsupported"),
    LotteryConfig("hg28wfc", "韩国28五分彩", "chuanqiking", "chuanqiking", lot_code=24, upstream_code="hg28wfc", category="时时彩", status="unsupported"),
    LotteryConfig("dwydhssc", "分分动物运动会", "chuanqiking", "chuanqiking", lot_code=33, upstream_code="dwydhssc", category="运动会系列", status="unsupported"),
    LotteryConfig("dwydhsfc", "三分动物运动会", "chuanqiking", "chuanqiking", lot_code=34, upstream_code="dwydhsfc", category="运动会系列", status="unsupported"),
    LotteryConfig("jbdwydh", "奖杯动物运动会", "chuanqiking", "chuanqiking", lot_code=35, upstream_code="jbdwydh", category="运动会系列", status="unsupported"),
    LotteryConfig("jpdwydh", "奖牌动物运动会", "chuanqiking", "chuanqiking", lot_code=36, upstream_code="jpdwydh", category="运动会系列", status="unsupported"),

    # ===== apiote122（编号有效、当前无数据）=====
    LotteryConfig("tjssc", "天津时时彩", "apiote122", "apiote122", lot_code=10003, upstream_code="tjssc", category="时时彩系列", status="empty"),
    LotteryConfig("xjssc", "新疆时时彩", "apiote122", "apiote122", lot_code=10004, upstream_code="xjssc", category="时时彩系列", status="empty"),
    LotteryConfig("tencentffc", "腾讯分分彩", "apiote122", "apiote122", lot_code=10056, upstream_code="tencentffc", category="时时彩系列", status="empty", note="chuanqiking 有「奇趣腾讯分分彩」等"),
    LotteryConfig("uklotto5", "英国乐透5", "apiote122", "apiote122", lot_code=10077, upstream_code="uklotto5", category="其他", status="empty"),

    # ===== apiote122（上游拒绝该编号）=====
    LotteryConfig("gdsyxw", "广东11选5", "apiote122", "apiote122", lot_code=10006, upstream_code="gdsyxw", category="11选5系列", status="unsupported", note="chuanqiking 有「广东11选5」20"),
    LotteryConfig("jsksan", "江苏快3", "apiote122", "apiote122", lot_code=10007, upstream_code="jsksan", category="快3系列", status="unsupported"),
    LotteryConfig("sdsyydj", "十一运夺金", "apiote122", "apiote122", lot_code=10008, upstream_code="sdsyydj", category="11选5系列", status="unsupported"),
    LotteryConfig("aozxy20", "澳洲幸运20", "apiote122", "apiote122", lot_code=10013, upstream_code="aozxy20", category="其他", status="unsupported"),
    LotteryConfig("bjkl8", "北京快乐8", "apiote122", "apiote122", lot_code=10014, upstream_code="bjkl8", category="快乐十分/快乐8", status="unsupported"),
    LotteryConfig("jxef", "江西11选5", "apiote122", "apiote122", lot_code=10015, upstream_code="jxef", category="11选5系列", status="unsupported"),
    LotteryConfig("jsef", "江苏11选5", "apiote122", "apiote122", lot_code=10016, upstream_code="jsef", category="11选5系列", status="unsupported"),
    LotteryConfig("ahef", "安徽11选5", "apiote122", "apiote122", lot_code=10017, upstream_code="ahef", category="11选5系列", status="unsupported"),
    LotteryConfig("shef", "上海11选5", "apiote122", "apiote122", lot_code=10018, upstream_code="shef", category="11选5系列", status="unsupported"),
    LotteryConfig("lnef", "辽宁11选5", "apiote122", "apiote122", lot_code=10019, upstream_code="lnef", category="11选5系列", status="unsupported"),
    LotteryConfig("hbef", "湖北11选5", "apiote122", "apiote122", lot_code=10020, upstream_code="hbef", category="11选5系列", status="unsupported"),
    LotteryConfig("cqef", "重庆11选5", "apiote122", "apiote122", lot_code=10021, upstream_code="cqef", category="11选5系列", status="unsupported"),
    LotteryConfig("gxef", "广西11选5", "apiote122", "apiote122", lot_code=10022, upstream_code="gxef", category="11选5系列", status="unsupported"),
    LotteryConfig("jlef", "吉林11选5", "apiote122", "apiote122", lot_code=10023, upstream_code="jlef", category="11选5系列", status="unsupported"),
    LotteryConfig("nmgef", "内蒙古11选5", "apiote122", "apiote122", lot_code=10024, upstream_code="nmgef", category="11选5系列", status="unsupported"),
    LotteryConfig("zjef", "浙江11选5", "apiote122", "apiote122", lot_code=10025, upstream_code="zjef", category="11选5系列", status="unsupported"),
    LotteryConfig("gxft", "广西快3", "apiote122", "apiote122", lot_code=10026, upstream_code="gxft", category="快3系列", status="unsupported"),
    LotteryConfig("jlft", "吉林快3", "apiote122", "apiote122", lot_code=10027, upstream_code="jlft", category="快3系列", status="unsupported"),
    LotteryConfig("hebft", "河北快3", "apiote122", "apiote122", lot_code=10028, upstream_code="hebft", category="快3系列", status="unsupported"),
    LotteryConfig("nmgft", "内蒙古快3", "apiote122", "apiote122", lot_code=10029, upstream_code="nmgft", category="快3系列", status="unsupported"),
    LotteryConfig("ahft", "安徽快3", "apiote122", "apiote122", lot_code=10030, upstream_code="ahft", category="快3系列", status="unsupported"),
    LotteryConfig("hubft", "湖北快3", "apiote122", "apiote122", lot_code=10032, upstream_code="hubft", category="快3系列", status="unsupported"),
    LotteryConfig("bjft", "北京快3", "apiote122", "apiote122", lot_code=10033, upstream_code="bjft", category="快3系列", status="unsupported"),
    LotteryConfig("tjklsf", "天津快乐十分", "apiote122", "apiote122", lot_code=10034, upstream_code="tjklsf", category="快乐十分/快乐8", status="unsupported"),
    LotteryConfig("gxklsf", "广西快乐十分", "apiote122", "apiote122", lot_code=10038, upstream_code="gxklsf", category="快乐十分/快乐8", status="unsupported"),
    LotteryConfig("fcssq", "福彩双色球", "apiote122", "apiote122", lot_code=10039, upstream_code="fcssq", category="全国彩(福彩/体彩)", status="unsupported"),
    LotteryConfig("cjdlt", "超级大乐透", "apiote122", "apiote122", lot_code=10040, upstream_code="cjdlt", category="全国彩(福彩/体彩)", status="unsupported"),
    LotteryConfig("fcsd", "福彩3D", "apiote122", "apiote122", lot_code=10041, upstream_code="fcsd", category="全国彩(福彩/体彩)", status="unsupported"),
    LotteryConfig("fcqlc", "福彩七乐彩", "apiote122", "apiote122", lot_code=10042, upstream_code="fcqlc", category="全国彩(福彩/体彩)", status="unsupported"),
    LotteryConfig("pailie3", "体彩排列3", "apiote122", "apiote122", lot_code=10043, upstream_code="pailie3", category="全国彩(福彩/体彩)", status="unsupported"),
    LotteryConfig("pailie5", "体彩排列5", "apiote122", "apiote122", lot_code=10044, upstream_code="pailie5", category="全国彩(福彩/体彩)", status="unsupported"),
    LotteryConfig("qxc", "体彩七星彩", "apiote122", "apiote122", lot_code=10045, upstream_code="qxc", category="全国彩(福彩/体彩)", status="unsupported"),
    LotteryConfig("egxy28_old", "PC蛋蛋（旧）", "apiote122", "apiote122", lot_code=10046, upstream_code="egxy28_old", category="PC蛋蛋系列", status="unsupported"),
    LotteryConfig("twbg", "台湾宾果", "apiote122", "apiote122", lot_code=10047, upstream_code="twbg", category="台湾彩", status="unsupported"),
    LotteryConfig("jisuksan", "极速快3", "apiote122", "apiote122", lot_code=10052, upstream_code="jisuksan", category="快3系列", status="unsupported"),
    LotteryConfig("jisuklsf", "极速快乐十分", "apiote122", "apiote122", lot_code=10053, upstream_code="jisuklsf", category="快乐十分/快乐8", status="unsupported"),
    LotteryConfig("jisukl8", "极速快乐8", "apiote122", "apiote122", lot_code=10054, upstream_code="jisukl8", category="快乐十分/快乐8", status="unsupported"),
    LotteryConfig("jisuef", "极速11选5", "apiote122", "apiote122", lot_code=10055, upstream_code="jisuef", category="11选5系列", status="unsupported"),
    LotteryConfig("shft", "上海快3", "apiote122", "apiote122", lot_code=10061, upstream_code="shft", category="快3系列", status="unsupported"),
    LotteryConfig("gzft", "贵州快3", "apiote122", "apiote122", lot_code=10062, upstream_code="gzft", category="快3系列", status="unsupported"),
    LotteryConfig("gsft", "甘肃快3", "apiote122", "apiote122", lot_code=10063, upstream_code="gsft", category="快3系列", status="unsupported"),
    LotteryConfig("tw_dlt", "台湾大乐透", "apiote122", "apiote122", lot_code=10070, upstream_code="tw_dlt", category="台湾彩", status="unsupported"),
    LotteryConfig("tw_wlc", "台湾威力彩", "apiote122", "apiote122", lot_code=10071, upstream_code="tw_wlc", category="台湾彩", status="unsupported"),
    LotteryConfig("tw_jc539", "台湾今彩539", "apiote122", "apiote122", lot_code=10072, upstream_code="tw_jc539", category="台湾彩", status="unsupported"),
    LotteryConfig("kl8", "快乐8", "apiote122", "apiote122", lot_code=10073, upstream_code="kl8", category="快乐十分/快乐8", status="unsupported"),
    LotteryConfig("egxy28", "PC蛋蛋幸运28", "apiote122", "apiote122", lot_code=10074, upstream_code="egxy28", category="PC蛋蛋系列", status="unsupported"),
    LotteryConfig("sgk3", "SG快3", "apiote122", "apiote122", lot_code=10076, upstream_code="sgk3", category="快3系列", status="unsupported"),
    LotteryConfig("uklotto8", "英国乐透8", "apiote122", "apiote122", lot_code=10078, upstream_code="uklotto8", category="其他", status="unsupported"),
    LotteryConfig("uklotto20", "英国乐透20", "apiote122", "apiote122", lot_code=10080, upstream_code="uklotto20", category="其他", status="unsupported"),
    LotteryConfig("speedPcEgg", "极速蛋蛋", "apiote122", "apiote122", lot_code=10081, upstream_code="speedPcEgg", category="PK10/飞艇/赛车", status="unsupported"),
    LotteryConfig("sgHappy8", "SG快乐8", "apiote122", "apiote122", lot_code=10082, upstream_code="sgHappy8", category="快乐十分/快乐8", status="unsupported"),
    LotteryConfig("sgHappy10", "SG快乐十分", "apiote122", "apiote122", lot_code=10083, upstream_code="sgHappy10", category="快乐十分/快乐8", status="unsupported"),
    LotteryConfig("sg11x5", "SG11选5", "apiote122", "apiote122", lot_code=10084, upstream_code="sg11x5", category="11选5系列", status="unsupported"),
    LotteryConfig("sportjisu", "极速运动会", "apiote122", "apiote122", lot_code=10086, upstream_code="sportjisu", category="运动会系列", status="unsupported"),
    LotteryConfig("sportkuaile", "快乐运动会", "apiote122", "apiote122", lot_code=10087, upstream_code="sportkuaile", category="运动会系列", status="unsupported"),
    LotteryConfig("etherssc", "以太时时彩", "apiote122", "apiote122", lot_code="ether", upstream_code="etherssc", category="时时彩系列", status="unsupported"),
    LotteryConfig("tronssc", "波场时时彩", "apiote122", "apiote122", lot_code="tron", upstream_code="tronssc", category="时时彩系列", status="unsupported"),
)


def _build_index(table: tuple[LotteryConfig, ...]) -> dict[str, LotteryConfig]:
    """按小写 ID 建索引，并在导入期拦截重复 ID。"""
    index: dict[str, LotteryConfig] = {}
    for config in table:
        key = config.id.lower()
        if key in index:
            raise ValueError(f"彩种名称表存在重复 ID：{config.id}")
        index[key] = config
    return index


#: 小写 ID -> 配置，路由查找用
LOTTERY_INDEX: dict[str, LotteryConfig] = _build_index(LOTTERY_TABLE)

#: 数据源 -> 该数据源下可用的彩种数量（便于自检）
SOURCE_COUNTS: dict[str, int] = {}
for _config in LOTTERY_TABLE:
    SOURCE_COUNTS[_config.source] = SOURCE_COUNTS.get(_config.source, 0) + 1
