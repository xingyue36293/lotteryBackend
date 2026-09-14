# Lottery Aggregator

多数据源彩票开奖聚合服务（Python + FastAPI）。

**配置驱动 + 适配器模式**：新增彩种只需在《彩种名称表》里加一行，路由与适配器代码完全不动；
只有接新数据源时才需要写一个适配器。

接口清单与字段含义来自项目根目录的 [`lottery.md`](./lottery.md)（由 [`lottery.ipynb`](./lottery.ipynb) 整理）。

## 快速开始

```bash
# 1. 激活虚拟环境
source .venv/Scripts/activate        # Git Bash
# .venv\Scripts\Activate.ps1         # PowerShell

# 2. 安装依赖
pip install -r requirements.txt

# 3. 生成配置（可选，不建 .env 则使用默认配置）
cp .env.example .env

# 4. 启动
uvicorn app.main:app --reload --port 8000
```

启动后：

- 接口文档（Swagger UI）：http://127.0.0.1:8000/docs
- 彩种名称表：http://127.0.0.1:8000/lottery
- 健康检查：http://127.0.0.1:8000/health

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/lottery` | 彩种名称表：稳定 ID、名称、数据源、请求参数、适配器、上游可用性 |
| GET | `/lottery/{id}/latest` | 最新期数、最新结果、下一期期数、下一期开奖时间 |
| GET | `/lottery/{id}/history?limit=50` | 最近 limit 期历史，默认 50，最大 200 |

### 示例请求

```bash
# 最新一期 + 下期预告
curl "http://127.0.0.1:8000/lottery/aozxy5/latest"

# 最近 100 期历史
curl "http://127.0.0.1:8000/lottery/aozxy5/history?limit=100"

# 走 168 线路池的彩种
curl "http://127.0.0.1:8000/lottery/pk10/latest"

# 哈希分分彩
curl "http://127.0.0.1:8000/lottery/hxffc/history?limit=5"
```

```jsonc
// GET /lottery/aozxy5/latest
{
  "id": "aozxy5",
  "name": "澳洲幸运5",
  "source": "yyy168",
  "latest": {
    "issue": "51350109",
    "draw_time": "2026-09-13 01:38:40",
    "code": [2, 6, 1, 7, 4],
    "code_text": "2,6,1,7,4",
    "sum": 8,
    "sum_odd_even": "双",
    "sum_big_small": "小",
    "dragon_tiger": "虎"
  },
  "next": { "issue": "51350110", "draw_time": "2026-09-13 01:43:40" }
}
```

```jsonc
// GET /lottery/aozxy5/history?limit=2
{
  "id": "aozxy5", "name": "澳洲幸运5", "source": "yyy168",
  "limit": 2, "count": 2,
  "history": [
    { "issue": "51350109", "draw_time": "2026-09-13 01:38:40", "code": [2, 6, 1, 7, 4],
      "code_text": "2,6,1,7,4", "sum": 8, "sum_odd_even": "双", "sum_big_small": "小", "dragon_tiger": "虎" },
    { "issue": "51350108", "draw_time": "2026-09-13 01:33:40", "code": [1, 9, 5, 2, 4],
      "code_text": "1,9,5,2,4", "sum": 21, "sum_odd_even": "单", "sum_big_small": "小", "dragon_tiger": "虎" }
  ]
}
```

### 错误结构

所有非 2xx 响应统一为：

```jsonc
{ "error": { "code": "upstream_no_data", "message": "北京PK10 上游暂无数据", "detail": { "lottery_id": "pk10", "source": "pks" } } }
```

| HTTP | code | 触发条件 |
| --- | --- | --- |
| 422 | `unknown_lottery` | 路径里的 `{id}` 不在彩种名称表中 |
| 422 | `invalid_parameter` | `limit` 越界（合法区间 `1~200`）等参数错误 |
| 502 | `upstream_error` | 上游网络失败、非 2xx、业务错误码非 0 |
| 502 | `upstream_no_data` | 上游返回空数据 |
| 502 | `unsupported_lot_code` | 上游明确拒绝该编号（如 chuanqiking 的 `lotCode Error`）|

## 代码结构

```
app/
├── config.py               # Settings + 《彩种名称表》LOTTERY_TABLE（配置驱动核心）
├── models.py               # Pydantic v2 统一返回模型
├── adapters/
│   ├── base.py             # 连接池 / 重试 / orjson 解析 / 字段归一化 + 适配器基类
│   ├── yyy168.py           # 168yyy.net          —— gid 体系（16 个彩种）
│   ├── apiote122.py        # api.apiote122.com   —— 时时彩系列
│   ├── pks.py              # 1688455.com 等线路池 —— /api/pks/*
│   ├── chuanqiking.py      # api.chuanqiking.com —— 分分彩 / 五分彩 / 时时彩
│   └── __init__.py         # 适配器注册表（导入期自检配置与适配器是否对齐）
├── services/
│   └── lottery_service.py  # 查表 -> 选适配器 -> 取数 -> TLRU 缓存（仅 latest）
├── routers/
│   └── lottery.py          # 路由：只做参数校验
├── main.py                 # 应用入口：lifespan、CORS、统一错误处理
└── db/                     # 预留
tests/                      # pytest（30 条用例，上游全部打桩）
requirements.txt
.env.example
```

## 《彩种名称表》

配置在 `app/config.py` 的 `LOTTERY_TABLE`，共 **111 个彩种**（以彩种名称去重后的全量对照表；「幸运飞艇」pks 10057 与 168yyy 的「168幸运飞艇」`g171` 为同一彩种，已合并）。

每行字段：

| 字段 | 说明 |
| --- | --- |
| `id` | **稳定 ID**，即路由里的 `{id}`，不随表行号变化（大小写不敏感查找） |
| `name` | 彩种名称 |
| `source` | 主数据源：`yyy168` / `pks` / `chuanqiking` / `apiote122` |
| `adapter` | 处理该数据源的适配器名称 |
| `gid` | 168yyy.net 的请求参数 |
| `lot_code` | 上游 `lotCode` 请求参数（线路池 / apiote122 / chuanqiking） |
| `upstream_code` | 上游自带的语义代码（apiote122 `lotCodeType` / chuanqiking 代码） |
| `category` | 玩法类别 |
| `status` | 上游可用性实测结果 |
| `note` | 备注（跨数据源对应关系） |

### 稳定 ID 生成规则

1. 优先取上游原生语义代码：apiote122 `lotCodeType`（如 `aozxy5`、`cqssc`）→ chuanqiking 代码（如 `hxffc`、`samlh`）；
2. 两者都没有时，取 168yyy 的 `g` + `gid`（如 `g107` 北京赛车(PK10)、`g301` 对应的新澳门六合彩因有代码故为 `samlh`）。

### 主数据源选择规则

优先 168yyy（**一次请求同时拿到最新一期 + 下期预告 + 历史**，信息最全）→ 168 线路池 `pks` →
chuanqiking → apiote122；若高优先级源在该彩种上实测无数据，则回退到实测可用的源。
因此 `北京PK10` / `SG飞艇` / `英国乐透10` 走 `pks`，`重庆时时彩` 走 `chuanqiking`。

## 上游可用性实测

`status` 字段来自对全部上游编号的真实探测（2026-09-13 实测）：

| source | 彩种数 | status=ok | 说明 |
| --- | --- | --- | --- |
| `yyy168` | 16 | **16** | gid 全表可用：101/103/107/108/109/131/132/135/170/171/172/175/200/201/202/301 |
| `pks` | 3 | **3** | lotCode `10001`/`10058`/`10079` 可用（`10012`/`10057` 也实测可用；10057 即「168幸运飞艇」，已并入 yyy168 的 `g171`） |
| `chuanqiking` | 28 | **11** | 可用 lotCode：11/12/13/14/25/26/27/29/30/31/32；7/8/9/22/23/28 编号有效但当前无数据 |
| `apiote122` | 64 | **3** | 可用 lotCode：10059/10064/10075（10010/10036 已由 yyy168 覆盖）；其余多为空响应 |

合计 **111 个彩种中 33 个 `ok`**，10 个 `empty`，68 个 `unsupported`。
`empty` / `unsupported` 的彩种调用会返回 502 + `upstream_no_data`（不会静默返回空数组）。
**上游编号的有效性会随时间变化**，建议定期用 `GET /lottery` 的 `status` 复核。

## 适配器与数据源规则

| 适配器 | 接口 | 字段映射要点 |
| --- | --- | --- |
| `yyy168` | `/api/lottery.php?action=history&gid=&limit=` | `game.latest` + `game.next` + `data[]`；`summary.big_small` / `dragon_tiger` 在六合彩类彩种上可能是空串 |
| `apiote122` | `/CQShiCai/getBaseCQShiCai.do`、`/CQShiCai/getBaseCQShiCaiList.do` | 单期接口不传 `issue` 即返回状态快照；0/1/2 编码映射为中文 |
| `pks` | `/api/pks/getPksDoubleCount.do`、`/api/pks/getLotteryPksInfo.do`、`/api/pks/getPksHistoryList.do` | 统计接口给「最新 + 下期」，单期接口补 `sumFS` / 龙虎；字段名保留上游拼写错误 **`sumBigSamll`** |
| `chuanqiking` | `/CQShiCai/getBaseCQShiCai`、`/CQShiCai/getBaseCQShiCaiList` | 路径**无** `.do` 后缀；期号是字符串；`id` 是 MongoDB ObjectId（未使用） |

共性处理：

- **gzip**：统一带 `Accept-Encoding: gzip, deflate`，规避上游 `422 please enable compression`；
- **线路池**：`pks` 多域名按配置顺序轮换，单个域名失败自动切下一个；
- **快照降级**：apiote122 / chuanqiking / pks 在拿不到「下期预告」时，`next` 返回 `null` 而不是整体失败（最新一期优先保证）；
- **字段归一化**：期号统一 `str`，号码统一 `int` 列表（自动处理 `"10,08,03"` 前导零），单双/大小/龙虎统一中文标签。

## 性能

| 项 | 实现 |
| --- | --- |
| JSON 解析 | `orjson.loads(response.content)`（上游响应）与 `orjson.dumps`（错误体） |
| 连接池 | 进程内共享一个 `httpx.AsyncClient`，`max_connections=100`，应用关闭时 `aclose()` |
| 超时 / 重试 | 超时 8 秒；每个域名重试 2 次，间隔 0.3 秒可配 |
| 缓存 | `cachetools.TLRUCache`：仅缓存 `latest`，条目过期于该彩种**下一期开奖时间**（取响应 `next.draw_time`）；下期缺失/异常时回退 3 秒，单条最长 300 秒。`history` 每次实时取上游，不缓存 |
| 大列表裁剪 | 适配器只切出前 `limit` 条再映射，其余原始响应立即丢弃 |
| 返回模型 | 只保留 `issue / draw_time / code / code_text / sum / sum_odd_even / sum_big_small / dragon_tiger`，不透传上游原始大 JSON |

## 运行测试

```bash
pytest
```

30 条用例，上游全部用 `FakeAdapter` 打桩，不产生真实网络请求；覆盖路由、缓存命中、
错误映射、`limit` 边界与三个数据源的字段映射。

## 如何扩展

**新增彩种**（不用改路由和适配器）：

1. 在 `app/config.py` 的 `LOTTERY_TABLE` 加一行，填好 `id` / `name` / `source` / `adapter` / `gid` 或 `lot_code` / `status`；
2. 完事。`GET /lottery` 与两个取数接口会自动生效。

**新增数据源**：

1. 在 `app/adapters/` 新建一个 `BaseAdapter`（或 `EnvelopeAdapter` / `SscSnapshotAdapter`）子类，实现 `fetch_latest` / `fetch_history`；
2. 在 `app/adapters/__init__.py` 的 `_create_adapters()` 登记；
3. 在 `app/config.py` 的 `Settings` 里加基地址；
4. 在 `LOTTERY_TABLE` 里把相关彩种的 `source` / `adapter` 指过去。

## 配置项

见 [`.env.example`](./.env.example)。数组类型（`CORS_ORIGINS`、`PKS_BASE_URLS`）需写成 JSON 数组。

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `YYY168_BASE_URL` | `https://www.168yyy.net` | gid 体系数据源 |
| `APIOTE122_BASE_URL` | `https://api.apiote122.com` | 时时彩数据源 |
| `PKS_BASE_URLS` | 5 个 168 域名 | 线路池，按顺序重试 |
| `CHUANQIKING_BASE_URL` | `https://api.chuanqiking.com` | 分分彩数据源 |
| `UPSTREAM_TIMEOUT` / `UPSTREAM_RETRIES` / `UPSTREAM_RETRY_DELAY` | `8` / `2` / `0.3` | 超时与重试 |
| `CACHE_LATEST_TTL` | `3` | 下期开奖时间缺失/异常时的回退缓存 TTL（秒）；`history` 不缓存 |
| `CACHE_MAX_TTL` | `300` | 单条缓存最长存活时间（秒），防御上游下期时间异常 |
| `HISTORY_DEFAULT_LIMIT` / `HISTORY_MAX_LIMIT` | `50` / `200` | 历史条数上下限 |
| `UPSTREAM_USE_TRUSTSTORE` | `true` | 用系统证书库替代 Python 默认 CA 包 |

## 注意

- 上游编号体系相互独立，168yyy 的 `gid` 与 `apiote122` 的 `lotCode` **不能混用**。
- 高频请求建议加间隔，请自行评估上游接口的可用性与合规性。
- `lottery.md` 中 `getPksDoubleCount.do` 的当天统计（`*Count` 字段）本次未对外暴露，如需统计接口可基于 `PksAdapter` 扩展。
