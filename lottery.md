# 彩票开奖 API 汇总文档

> 本文档由 `lottery.ipynb` 总结，按 **彩种 / 数据源 / 接口** 分类。  
> 涉及数据源：`168yyy.net`、`api.apiote122.com`、`1688455.com/1688507.com` 线路池、`api.chuanqiking.com`。  
> 仅作文档整理，接口可用性、风控与合法性请自行判断。

---

## 0. 接口速查表

| 数据源 | 彩种 | 接口 | 用途 |
|---|---|---|---|
| `www.168yyy.net` | 极速赛车 `gid=172` | `/api/lottery.php?action=history` | 历史开奖 / 最新 / 下期 |
| `api.apiote122.com` | 澳洲幸运5 `lotCode=10010` | `/CQShiCai/getBaseCQShiCai.do` | 指定期号 / 最新一期详情 |
| `api.apiote122.com` | 澳洲幸运5 `lotCode=10010` | `/CQShiCai/getBaseCQShiCaiList.do` | 最近约 176 期历史列表 |
| `1688455.com`、`1688507.com` 等 | 澳洲幸运10 `lotCode=10012` | `/api/pks/getLotteryPksInfo.do` | 指定期号详情 |
| `1688455.com`、`1688507.com` 等 | 澳洲幸运10 `lotCode=10012` | `/api/pks/getPksHistoryList.do` | 历史开奖列表 |
| `1688455.com`、`1688507.com` 等 | 澳洲幸运10 `lotCode=10012` | `/api/pks/getPksDoubleCount.do` | 当天单双大小龙虎统计 |
| `api.chuanqiking.com` | 哈希分分彩 `lotCode=26` | `/CQShiCai/getBaseCQShiCai` | 指定期号 / 最新一期详情 |
| `api.chuanqiking.com` | 哈希分分彩 `lotCode=26` | `/CQShiCai/getBaseCQShiCaiList` | 当天历史列表 |

---

## 1. 公共约定

### 1.1 通用请求头

```python
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:155.0) Gecko/20100101 Firefox/155.0",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    # Referer / Origin 按数据源填写
}
```

### 1.2 gzip 压缩

部分接口强制要求客户端支持压缩，否则返回：

```text
422: please enable compression in your browser
```

- `curl`：加 `--compressed`
- `requests`：默认自动处理 gzip，无需手动设置
- 注意：`--compressed` 是两个短横线，不是 `-compressed`

### 1.3 类型注意

| 项目 | 说明 |
|---|---|
| 期号 | 有的接口是字符串，如 `"202609121365"`；有的是整数，如 `21358963` |
| 开奖号码 | 有的带前导零，如 `"10,08,03"`，建议先 `split` 再 `int` |
| MongoDB ObjectId | `chuanqiking` 的 `id` 是 `{"$oid": "..."}`，取值需 `d["id"]["$oid"]` |
| 拼写错误 | `sumBigSamll` 是原接口字段名，不是 `sumBigSmall` |
| 龙虎“和” | 部分接口龙虎可能返回 `2` 表示和，统计时需单独处理 |

### 1.4 公共枚举

#### 单双

| 值 | 含义 |
|---|---|
| `1` | 单 |
| `0` | 双 |

#### 大小

| 值 | 含义 |
|---|---|
| `1` | 大 |
| `0` | 小 |
| 可能 `2` | 和 |

#### 龙虎

| 值 | 含义 |
|---|---|
| `0` | 虎 |
| `1` | 龙 |
| `2` | 和 |

#### 形态：前三 / 中三 / 后三

| 值 | 含义 |
|---|---|
| `0` | 杂六 |
| `1` | 半顺 |
| `2` | 顺子 |
| `3` | 对子 |
| `4` | 豹子 |

### 1.5 大小规则汇总

| 彩种类型 | 单球大小 | 总和 / 冠亚和大小 |
|---|---|---|
| 时时彩、哈希分分彩 | `0~4` 小，`5~9` 大 | 总和 `0~22` 小，`23~45` 大 |
| 澳洲幸运5 | `0~4` 小，`5~9` 大 | 总和 `0~22` 小，`23~45` 大 |
| 澳洲幸运10 / 极速赛车 | 名次数字 `1~5` 小，`6~10` 大 | 冠亚和 `3~10` 小，`11` 和，`12~19` 大；部分接口写 `3~11` 小 |

### 1.6 龙虎规则差异

| 彩种 | 规则 |
|---|---|
| 极速赛车 / 澳洲幸运10 | 比较对称名次数字：第1 vs 第10、第2 vs 第9、第3 vs 第8、第4 vs 第7、第5 vs 第6。前者小为“龙”，前者大为“虎”，相等为“和” |
| 澳洲幸运5 | 冠军号码 > 第五名号码为“龙”，反之为“虎”，相等为“和” |
| 哈希分分彩 | 第一球 > 第五球为“龙”，< 为“虎”，= 为“和” |

---

## 2. 极速赛车：`168yyy.net`

### 2.1 历史开奖 / 最新开奖

#### 接口地址

```text
GET https://www.168yyy.net/api/lottery.php
```

#### 请求参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|---|---|---|---|---|
| `action` | String | 是 | 查询历史列表用 `history` | `history` |
| `gid` | Integer | 是 | 游戏 ID，极速赛车为 `172` | `172` |
| `limit` | Integer | 否 | 返回记录条数，默认约 50 | `50` |

#### 返回顶层

| 字段 | 类型 | 说明 |
|---|---|---|
| `ok` | Boolean | 请求是否成功 |
| `server_time` | String | 服务器时间，ISO 8601 带时区 |
| `game` | Object | 游戏元信息 |
| `data` | Array | 开奖记录数组，时间倒序 |

#### `game` 对象

| 字段 | 类型 | 说明 |
|---|---|---|
| `gid` | Integer | 游戏 ID |
| `name` | String | 游戏名称 |
| `type` | String | 类型标识 |
| `type_label` | String | 类型中文标签 |
| `fenlei` | String | 分类编号 |
| `ball_count` | Integer | 球数 |
| `sort` | Integer | 排序权重 |
| `latest` | Object | 最新一期信息 |
| `next` | Object | 下一期预告 |

#### `game.latest` / `data[]`

| 字段 | 类型 | 说明 |
|---|---|---|
| `issue` | String | 期号 |
| `date` | String | 日期 |
| `draw_time` | String | 开奖时间 |
| `balls` | Array<Int> | 开奖号码，10 个名次 |
| `summary` | Object | 开奖摘要 |

#### `game.next`

| 字段 | 类型 | 说明 |
|---|---|---|
| `issue` | String | 下期期号 |
| `draw_time` | String | 预计开奖时间 |

#### `summary`

| 字段 | 类型 | 说明 |
|---|---|---|
| `sum` | Integer | 冠亚军号码之和，即第 1 + 第 2 名 |
| `odd_even` | String | 冠亚和单双：`单` / `双` |
| `big_small` | String | 冠亚和大小：`大` / `小` / `和` |
| `dragon_tiger` | String | 冠军与第十名龙虎：`龙` / `虎` / `和` |
| `dragon_tigers` | Array<String> | 五个龙虎位置数组 |

#### 关键规则

```text
balls = [4, 9, 7, 10, 3, 2, 8, 1, 5, 6]
         ↑冠军       ↑亚军  ↑第十名
```

- `sum = balls[0] + balls[1]`，范围 `3~19`
- `sum` 为奇数返回 `单`，偶数返回 `双`
- `big_small`：`3~10` 为 `小`，`11` 为 `和`，`12~19` 为 `大`
- `dragon_tiger`：冠军名次数字 < 第十名名次数字 → `龙`；> → `虎`；= → `和`
- `dragon_tigers` 五组：
  - `[0]` 第 1 名 vs 第 10 名
  - `[1]` 第 2 名 vs 第 9 名
  - `[2]` 第 3 名 vs 第 8 名
  - `[3]` 第 4 名 vs 第 7 名
  - `[4]` 第 5 名 vs 第 6 名

#### Python 示例

```python
import requests
import truststore

truststore.inject_into_ssl()

URL = "https://www.168yyy.net/api/lottery.php"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:155.0) Gecko/20100101 Firefox/155.0",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.168yyy.net/",
}

def fetch_history(gid=172, limit=50):
    params = {"action": "history", "gid": gid, "limit": limit}
    resp = requests.get(URL, params=params, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    return resp.json()

data = fetch_history(gid=172, limit=50)
game = data["game"]
print(game["name"], game["latest"]["issue"], game["latest"]["balls"])
```

---

## 3. 澳洲幸运5：`api.apiote122.com`

### 3.1 指定期号 / 最新一期详情

#### 接口地址

```text
GET https://api.apiote122.com/CQShiCai/getBaseCQShiCai.do
```

#### 请求参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|---|---|---|---|---|
| `issue` | String | 是 | 期号 | `51349972` |
| `lotCode` | Integer | 是 | 彩种编号，澳洲幸运5为 `10010` | `10010` |

#### 返回结构

顶层：

| 字段 | 类型 | 说明 |
|---|---|---|
| `errorCode` | Integer | 错误码，0 表示成功 |
| `message` | String | 操作结果描述 |
| `result` | Object | 业务数据包装 |

`result`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `businessCode` | Integer | 业务状态码，0 表示成功 |
| `message` | String | 业务描述 |
| `data` | Object | 开奖数据 |

`data` 彩种与状态：

| 字段 | 类型 | 说明 |
|---|---|---|
| `serverTime` | String | 服务器当前时间 |
| `lotCode` | Integer | 彩种编号 |
| `lotName` | String | 彩种名称 |
| `iconUrl` | String | 彩种图标 |
| `totalCount` | Integer | 当天总期数 |
| `shelves` | Integer | 是否上架，0=正常 |
| `groupCode` | Integer | 分组编码 |
| `frequency` | String | 频率 |
| `lotteryStatus` | Integer | 彩种状态，0=正常 |
| `category` | String | 类别 |
| `hot` | Integer | 热度标记 |
| `index` | Integer | 排序索引 |
| `id` | Integer | 数据记录 ID |

`data` 上期开奖：

| 字段 | 类型 | 说明 |
|---|---|---|
| `preDrawIssue` | Integer | 上期期号 |
| `preDrawTime` | String | 上期开奖时间 |
| `preDrawCode` | String | 上期开奖号码，逗号分隔 |
| `preDrawDate` | String | 上期开奖日期 |
| `drawCount` | Integer | 上期开奖号码计数 |

`data` 当前 / 下期：

| 字段 | 类型 | 说明 |
|---|---|---|
| `drawIssue` | Integer | 当前 / 下期期号 |
| `drawTime` | String | 预计开奖时间 |
| `status` | Integer | 当前状态，0=等待开奖 |

`data` 号码与形态：

| 字段 | 类型 | 说明 |
|---|---|---|
| `firstNum` ~ `fifthNum` | Integer | 第一~第五球号码 |
| `sumNum` | Integer | 号码总和 |
| `sumSingleDouble` | Integer | 总和单双，1=单，0=双 |
| `sumBigSmall` | Integer | 总和大小，1=大，0=小 |
| `firstSingleDouble` | Integer | 第一球单双 |
| `firstBigSmall` | Integer | 第一球大小 |
| `secondSingleDouble` | Integer | 第二球单双 |
| `secondBigSmall` | Integer | 第二球大小 |
| `thirdSingleDouble` | Integer | 第三球单双 |
| `thirdBigSmall` | Integer | 第三球大小 |
| `fourthSingleDouble` | Integer | 第四球单双 |
| `fourthBigSmall` | Integer | 第四球大小 |
| `fifthSingleDouble` | Integer | 第五球单双 |
| `fifthBigSmall` | Integer | 第五球大小 |
| `dragonTiger` | Integer | 龙虎，1=龙，0=虎 |
| `behindThree` | Integer | 后三形态 |
| `betweenThree` | Integer | 中三形态 |
| `lastThree` | Integer | 前三形态 |

#### Python 示例

```python
import requests
import truststore

truststore.inject_into_ssl()

url = "https://api.apiote122.com/CQShiCai/getBaseCQShiCai.do"
params = {"issue": "51349972", "lotCode": 10010}

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:155.0) Gecko/20100101 Firefox/155.0",
    "Accept": "*/*",
    "Referer": "https://www.chuanqiking.com/",
    "Origin": "https://www.chuanqiking.com",
}

resp = requests.get(url, params=params, headers=headers, timeout=10)
data = resp.json()

if data["errorCode"] == 0:
    d = data["result"]["data"]
    print(d["lotName"], d["preDrawIssue"], d["preDrawCode"], d["sumNum"])
```

---

### 3.2 历史开奖列表

#### 接口地址

```text
GET https://api.apiote122.com/CQShiCai/getBaseCQShiCaiList.do
```

#### 请求参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|---|---|---|---|---|
| `lotCode` | Integer | 是 | 彩种编号，澳洲幸运5为 `10010` | `10010` |

> 实测不传期号也返回数据，默认返回最近约 176 期，按时间倒序。

#### 返回结构

顶层：

| 字段 | 类型 | 说明 |
|---|---|---|
| `errorCode` | Integer | 错误码，0 表示成功 |
| `message` | String | 操作结果描述 |
| `result` | Object | 业务数据包装 |

`result`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `businessCode` | Integer | 业务状态码 |
| `message` | String | 业务描述 |
| `data` | Array | 开奖记录数组，时间倒序 |

`data[]` 单条：

| 字段 | 类型 | 说明 |
|---|---|---|
| `preDrawIssue` | Integer | 期号 |
| `preDrawTime` | String | 开奖时间 |
| `preDrawCode` | String | 开奖号码，5 个，逗号分隔 |
| `sumNum` | Integer | 号码总和 |
| `sumSingleDouble` | Integer | 总和单双，1=单，0=双 |
| `sumBigSmall` | Integer | 总和大小，1=大，0=小 |
| `dragonTiger` | Integer | 龙虎，0=虎，1=龙，2=和 |
| `firstBigSmall` | Integer | 第一球大小 |
| `firstSingleDouble` | Integer | 第一球单双 |
| `secondBigSmall` | Integer | 第二球大小 |
| `secondSingleDouble` | Integer | 第二球单双 |
| `thirdBigSmall` | Integer | 第三球大小 |
| `thirdSingleDouble` | Integer | 第三球单双 |
| `fourthBigSmall` | Integer | 第四球大小 |
| `fourthSingleDouble` | Integer | 第四球单双 |
| `fifthBigSmall` | Integer | 第五球大小 |
| `fifthSingleDouble` | Integer | 第五球单双 |
| `behindThree` | Integer | 后三形态 |
| `betweenThree` | Integer | 中三形态 |
| `lastThree` | Integer | 前三形态 |
| `groupCode` | Integer | 分组编码，澳洲系列通常为 2 |

#### Python 示例

```python
import requests
import truststore

truststore.inject_into_ssl()

URL = "https://api.apiote122.com/CQShiCai/getBaseCQShiCaiList.do"
params = {"lotCode": 10010}

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:155.0) Gecko/20100101 Firefox/155.0",
    "Accept": "*/*",
    "Referer": "https://www.chuanqiking.com/",
    "Origin": "https://www.chuanqiking.com",
}

resp = requests.get(URL, params=params, headers=headers, timeout=10)
data = resp.json()

records = data["result"]["data"]
print(len(records))
for r in records[:5]:
    print(r["preDrawIssue"], r["preDrawCode"], r["sumNum"])
```

---

## 4. 澳洲幸运10：`1688455.com` / `1688507.com` 等线路池

> 域名池：`1688455.com`、`1688507.com`、`1689690.com`、`1689691.com`、`1689687.com` 等。  
> 路径固定，建议域名池 + 重试。

### 4.1 指定期号详情

#### 接口地址

```text
GET https://1688455.com/api/pks/getLotteryPksInfo.do
```

也可替换域名为 `1688507.com` 等。

#### 请求参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|---|---|---|---|---|
| `issue` | String | 是 | 期号 | `21358960` |
| `lotCode` | Integer | 是 | 彩种编号，澳洲幸运10为 `10012` | `10012` |

#### 返回结构

`data` 彩种与状态：

| 字段 | 类型 | 说明 |
|---|---|---|
| `serverTime` | String | 服务器当前时间 |
| `lotCode` | Integer | 彩种编号 |
| `lotName` | String | 彩种名称 |
| `iconUrl` | String | 彩种图标 |
| `totalCount` | Integer | 当天总期数 |
| `shelves` | Integer | 是否上架 |
| `groupCode` | Integer | 分组编码 |
| `frequency` | String | 频率 |
| `lotteryStatus` | Integer | 彩种状态 |
| `category` | String | 类别 |
| `hot` | Integer | 热度标记 |
| `index` | Integer | 排序索引 |

`data` 上期开奖：

| 字段 | 类型 | 说明 |
|---|---|---|
| `preDrawIssue` | Integer | 上期期号 |
| `preDrawTime` | String | 上期开奖时间 |
| `preDrawCode` | String | 开奖号码，10 个名次，带前导零 |
| `preDrawDate` | String | 上期开奖日期 |
| `drawCount` | Integer | 上期开奖号码计数 |

`data` 当前 / 下期：

| 字段 | 类型 | 说明 |
|---|---|---|
| `drawIssue` | Integer | 当前 / 下期期号 |
| `drawTime` | String | 预计开奖时间 |

`data` 各名次号码：

| 字段 | 类型 | 说明 |
|---|---|---|
| `firstNum` | Integer | 第 1 名号码 |
| `secondNum` | Integer | 第 2 名号码 |
| `thirdNum` | Integer | 第 3 名号码 |
| `fourthNum` | Integer | 第 4 名号码 |
| `fifthNum` | Integer | 第 5 名号码 |
| `sixthNum` | Integer | 第 6 名号码 |
| `seventhNum` | Integer | 第 7 名号码 |
| `eighthNum` | Integer | 第 8 名号码 |
| `ninthNum` | Integer | 第 9 名号码 |
| `tenthNum` | Integer | 第 10 名号码 |

`data` 冠亚和与龙虎：

| 字段 | 类型 | 说明 |
|---|---|---|
| `sumFS` | Integer | 冠亚和，第 1 名 + 第 2 名 |
| `sumBigSamll` | Integer | 冠亚和大小，1=大，0=小，可能另有值表示和 |
| `sumSingleDouble` | Integer | 冠亚和单双，1=单，0=双 |
| `firstDT` | Integer | 冠军龙虎，0=虎，1=龙 |
| `secondDT` | Integer | 亚军龙虎 |
| `thirdDT` | Integer | 第三名龙虎 |
| `fourthDT` | Integer | 第四名龙虎 |
| `fifthDT` | Integer | 第五名龙虎 |

#### 规则

- `preDrawCode = "10,07,09,05,08,01,06,04,03,02"`
- `sumFS = firstNum + secondNum`，范围 `3~19`
- `sumSingleDouble`：奇数 `1`，偶数 `0`
- `sumBigSamll`：`3~11` 小，`12~19` 大，`11` 可能为和
- 龙虎：对称名次比较，前者小为龙 `1`，前者大为虎 `0`，相等可能为和

#### Python 示例

```python
import requests
import truststore

truststore.inject_into_ssl()

URL = "https://1688455.com/api/pks/getLotteryPksInfo.do"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:155.0) Gecko/20100101 Firefox/155.0",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.168yyy.net/",
}

def fetch_pks_info(issue, lot_code=10012):
    params = {"issue": issue, "lotCode": lot_code}
    resp = requests.get(URL, params=params, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    return resp.json()

data = fetch_pks_info("21358960", 10012)
d = data["result"]["data"]
print(d["preDrawIssue"], d["preDrawCode"], d["sumFS"])
```

---

### 4.2 历史开奖列表

#### 接口地址

```text
GET https://1688507.com/api/pks/getPksHistoryList.do
```

#### 请求参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|---|---|---|---|---|
| `lotCode` | Integer | 是 | 彩种编号，澳洲幸运10为 `10012` | `10012` |

> 一次返回约 260 条，覆盖当天全部开奖，时间倒序。

#### `data[]` 单条

| 字段 | 类型 | 说明 |
|---|---|---|
| `preDrawIssue` | Integer | 期号 |
| `preDrawTime` | String | 开奖时间 |
| `preDrawCode` | String | 开奖号码，10 个名次，带前导零 |
| `sumFS` | Integer | 冠亚和 |
| `sumBigSamll` | Integer | 冠亚和大小 |
| `sumSingleDouble` | Integer | 冠亚和单双 |
| `firstDT` | Integer | 第 1 组龙虎 |
| `secondDT` | Integer | 第 2 组龙虎 |
| `thirdDT` | Integer | 第 3 组龙虎 |
| `fourthDT` | Integer | 第 4 组龙虎 |
| `fifthDT` | Integer | 第 5 组龙虎 |
| `groupCode` | Integer | 分组编码 |

#### Python 示例

```python
import requests
import truststore

truststore.inject_into_ssl()

URL = "https://1688507.com/api/pks/getPksHistoryList.do"
params = {"lotCode": 10012}

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:155.0) Gecko/20100101 Firefox/155.0",
    "Accept": "*/*",
    "Referer": "https://www.168yyy.net/",
    "Origin": "https://www.168yyy.net",
}

resp = requests.get(URL, params=params, headers=headers, timeout=10)
data = resp.json()
records = data["result"]["data"]

for r in records[:5]:
    print(r["preDrawIssue"], r["preDrawCode"], r["sumFS"], r["firstDT"])
```

---

### 4.3 当天单双大小龙虎统计

#### 接口地址

```text
GET https://1688507.com/api/pks/getPksDoubleCount.do
```

#### 请求参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|---|---|---|---|---|
| `lotCode` | Integer | 是 | 彩种编号，澳洲幸运10为 `10012` | `10012` |
| `date` | String | 否 | 查询日期，`YYYY-MM-DD`，空则当天 | `""` 或 `"2026-09-12"` |

#### `data` 基础信息

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | Integer | 数据记录 ID |
| `preDrawCode` | String | 最近一期开奖号码 |
| `preDrawIssue` | Integer | 最近一期期号 |
| `preDrawDate` | String | 统计日期 |
| `preDrawTime` | String | 最近一期开奖时间 |
| `drawIssue` | Integer | 下一期期号 |
| `drawTime` | String | 下一期预计开奖时间 |
| `drawCount` | Integer | 当天已开奖期数 |
| `enable` | Integer | 状态标记 |

#### 各名次统计

命名规则：`{序数}{Single|Double|Big|Small}Count`

序数：`first`、`second`、`third`、`fourth`、`fifth`、`sixth`、`seventh`、`eighth`、`ninth`、`tenth`

| 后缀 | 含义 |
|---|---|
| `SingleCount` | 单次数 |
| `DoubleCount` | 双次数 |
| `BigCount` | 大次数 |
| `SmallCount` | 小次数 |

#### 冠亚和统计

| 字段 | 说明 |
|---|---|
| `sumSingleCount` | 冠亚和为单次数 |
| `sumDoubleCount` | 冠亚和为双次数 |
| `sumBigCount` | 冠亚和为大次数 |
| `sumSmallCount` | 冠亚和为小次数 |

#### 龙虎统计

| 字段 | 说明 |
|---|---|
| `firstDragonCount` / `firstTigerCount` | 第 1 组龙 / 虎次数 |
| `secondDragonCount` / `secondTigerCount` | 第 2 组龙 / 虎次数 |
| `thirdDragonCount` / `thirdTigerCount` | 第 3 组龙 / 虎次数 |
| `fourthDragonCount` / `fourthTigerCount` | 第 4 组龙 / 虎次数 |
| `fifthDragonCount` / `fifthTigerCount` | 第 5 组龙 / 虎次数 |

#### Python 示例

```python
import requests
import truststore

truststore.inject_into_ssl()

URL = "https://1688507.com/api/pks/getPksDoubleCount.do"
params = {"lotCode": 10012, "date": ""}

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:155.0) Gecko/20100101 Firefox/155.0",
    "Accept": "*/*",
    "Referer": "https://www.168yyy.net/",
}

resp = requests.get(URL, params=params, headers=headers, timeout=10)
data = resp.json()
d = data["result"]["data"]
print(d["preDrawDate"], d["drawCount"], d["sumSingleCount"], d["sumDoubleCount"])
```

---

## 5. 哈希分分彩：`api.chuanqiking.com`

### 5.1 指定期号 / 最新一期详情

#### 接口地址

```text
GET https://api.chuanqiking.com/CQShiCai/getBaseCQShiCai
```

#### 请求参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|---|---|---|---|---|
| `issue` | String | 是 | 期号，字符串，勿转 int | `"202609121362"` |
| `lotCode` | Integer | 是 | 彩种编号，哈希分分彩为 `26` | `26` |

#### `data` 彩种与状态

| 字段 | 类型 | 说明 |
|---|---|---|
| `serverTime` | String | 服务器当前时间 |
| `lotCode` | String | 彩种编号，注意响应里是字符串 |
| `lotName` | String | 彩种名称 |
| `iconUrl` | String | 彩种图标 |
| `totalCount` | Integer | 当天总期数，分分彩为 1440 |
| `shelves` | Integer | 是否上架 |
| `groupCode` | Integer | 分组编码 |
| `frequency` | String | 频率 |
| `lotteryStatus` | Integer | 彩种状态 |
| `category` | String | 类别 |
| `hot` | Integer | 热度标记 |
| `index` | Integer | 排序索引 |
| `id` | Object | MongoDB ObjectId，如 `{"$oid":"..."}` |
| `sdrawCount` | String | 空字符串 |
| `status` | Integer | 当前状态 |

#### `data` 上期开奖

| 字段 | 类型 | 说明 |
|---|---|---|
| `preDrawIssue` | String | 上期期号 |
| `preDrawTime` | String | 上期开奖时间 |
| `preDrawCode` | String | 上期开奖号码，5 个，逗号分隔 |
| `preDrawDate` | String | 上期开奖日期，`YYYY-MM-DD 00:00:00` |
| `drawCount` | Integer | 当天已开期数 |

#### `data` 当前 / 下期

| 字段 | 类型 | 说明 |
|---|---|---|
| `drawIssue` | String | 当前 / 下期期号 |
| `drawTime` | String | 预计开奖时间 |

#### `data` 号码与形态

| 字段 | 类型 | 说明 |
|---|---|---|
| `firstNum` ~ `fifthNum` | Integer | 第一~第五球号码 |
| `sumNum` | Integer | 5 球号码之和 |
| `sumSingleDouble` | Integer | 总和单双，1=单，0=双 |
| `sumBigSmall` | Integer | 总和大小，1=大，0=小 |
| `dragonTiger` | Integer | 龙虎，0=虎，1=龙，2=和 |
| `firstSingleDouble` | Integer | 第一球单双 |
| `firstBigSmall` | Integer | 第一球大小 |
| `secondSingleDouble` | Integer | 第二球单双 |
| `secondBigSmall` | Integer | 第二球大小 |
| `thirdSingleDouble` | Integer | 第三球单双 |
| `thirdBigSmall` | Integer | 第三球大小 |
| `fourthSingleDouble` | Integer | 第四球单双 |
| `fourthBigSmall` | Integer | 第四球大小 |
| `fifthSingleDouble` | Integer | 第五球单双 |
| `fifthBigSmall` | Integer | 第五球大小 |
| `behindThree` | Integer | 后三形态 |
| `betweenThree` | Integer | 中三形态 |
| `lastThree` | Integer | 前三形态 |

#### Python 示例

```python
import requests
import truststore

truststore.inject_into_ssl()

URL = "https://api.chuanqiking.com/CQShiCai/getBaseCQShiCai"
LOT_CODE = 26

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:155.0) Gecko/20100101 Firefox/155.0",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Origin": "https://www.chuanqiking.com",
    "Referer": "https://www.chuanqiking.com/",
}

def fetch_ssc(issue, lot_code=26):
    params = {"issue": issue, "lotCode": lot_code}
    resp = requests.get(URL, params=params, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    return resp.json()

data = fetch_ssc("202609121362", LOT_CODE)
d = data["result"]["data"]
print(d["lotName"], d["preDrawIssue"], d["preDrawCode"], d["sumNum"])
```

---

### 5.2 历史开奖列表

#### 接口地址

```text
GET https://api.chuanqiking.com/CQShiCai/getBaseCQShiCaiList
```

#### 请求参数

| 参数名 | 类型 | 必填 | 说明 | 示例 |
|---|---|---|---|---|
| `lotCode` | Integer | 是 | 彩种编号，哈希分分彩为 `26` | `26` |

> 一次返回当天全部已开期数，时间倒序，`data[0]` 为最新一期。

#### `data[]` 单条

| 字段 | 类型 | 说明 |
|---|---|---|
| `preDrawIssue` | String | 期号 |
| `preDrawTime` | String | 开奖时间 |
| `preDrawCode` | String | 开奖号码，5 个，逗号分隔，无前导零 |
| `sumNum` | Integer | 5 球号码之和 |
| `sumSingleDouble` | Integer | 总和单双 |
| `sumBigSmall` | Integer | 总和大小 |
| `dragonTiger` | Integer | 龙虎，0=虎，1=龙，2=和 |
| `firstBigSmall` / `firstSingleDouble` | Integer | 第一球大小 / 单双 |
| `secondBigSmall` / `secondSingleDouble` | Integer | 第二球大小 / 单双 |
| `thirdBigSmall` / `thirdSingleDouble` | Integer | 第三球大小 / 单双 |
| `fourthBigSmall` / `fourthSingleDouble` | Integer | 第四球大小 / 单双 |
| `fifthBigSmall` / `fifthSingleDouble` | Integer | 第五球大小 / 单双 |
| `behindThree` | Integer | 后三形态 |
| `betweenThree` | Integer | 中三形态 |
| `lastThree` | Integer | 前三形态 |
| `groupCode` | Integer | 分组编码 |

> 与单期接口相比，列表接口 **不返回** `firstNum ~ fifthNum`、`lotName`、`drawIssue`、`drawTime`、`id`、`serverTime`。

#### Python 示例

```python
import requests
import truststore

truststore.inject_into_ssl()

URL = "https://api.chuanqiking.com/CQShiCai/getBaseCQShiCaiList"
params = {"lotCode": 26}

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:155.0) Gecko/20100101 Firefox/155.0",
    "Accept": "*/*",
    "Origin": "https://www.chuanqiking.com",
    "Referer": "https://www.chuanqiking.com/",
}

resp = requests.get(URL, params=params, headers=headers, timeout=10)
data = resp.json()
records = data["result"]["data"]

for r in records[:5]:
    print(r["preDrawIssue"], r["preDrawTime"], r["preDrawCode"], r["sumNum"])
```

---

## 6. 彩种 ID 对照总表

### 6.1 `168yyy.net` 的 `gid` 对照

| gid | 彩种名称 | 角标 | 玩法类别 |
|---|---|---|---|
| 101 | 重庆欢乐生肖 | 重庆 | 时时彩 |
| 103 | 广东快乐十分 | 广东 | 快乐十分 |
| 107 | 北京赛车(PK10) | 北京 | 赛车 |
| 108 | 极速时时彩 | 极速 | 时时彩 |
| 109 | 澳洲幸运5 | 澳洲 | 时时彩 |
| 131 | 澳洲幸运8 | 澳洲 | 快乐十分 |
| 132 | 澳门幸运8 | 澳门 | 快乐十分 |
| 135 | 重庆幸运农场 | 重庆 | 快乐十分 |
| 170 | 极速飞艇 | 极速 | 赛车 |
| 171 | 168幸運飛艇 | 16 | 赛车 |
| 172 | 极速赛车 | 极速 | 赛车 |
| 175 | 澳洲幸运10 | 澳洲 | 赛车 |
| 200 | 极速六合彩 | 极速 | 六合彩 |
| 201 | 澳门六合彩5分 | 澳门 | 六合彩 |
| 202 | 新台湾六合彩 | 新台 | 六合彩 |
| 301 | 新澳门六合彩 | 新澳 | 六合彩 |

### 6.2 `api.apiote122.com` / `168` 线路通用 `lotCode` 对照

| lotCode | lotCodeType | 彩票名称 | 类别 |
|---|---|---|---|
| 10001 | pk10 | 北京PK10 | PK10/飞艇/赛车 |
| 10002 | cqssc | 重庆时时彩 | 时时彩系列 |
| 10003 | tjssc | 天津时时彩 | 时时彩系列 |
| 10004 | xjssc | 新疆时时彩 | 时时彩系列 |
| 10005 | gdklsf | 广东快乐十分 | 快乐十分/快乐8 |
| 10006 | gdsyxw | 广东11选5 | 11选5系列 |
| 10007 | jsksan | 江苏快3 | 快3系列 |
| 10008 | sdsyydj | 十一运夺金 | 11选5系列 |
| 10009 | cqxync | 重庆幸运农场 | 其他 |
| 10010 | aozxy5 | 澳洲幸运5 | 其他 |
| 10011 | aozxy8 | 澳洲幸运8 | 其他 |
| 10012 | aozxy10 | 澳洲幸运10 | PK10/飞艇/赛车 |
| 10013 | aozxy20 | 澳洲幸运20 | 其他 |
| 10014 | bjkl8 | 北京快乐8 | 快乐十分/快乐8 |
| 10015 | jxef | 江西11选5 | 11选5系列 |
| 10016 | jsef | 江苏11选5 | 11选5系列 |
| 10017 | ahef | 安徽11选5 | 11选5系列 |
| 10018 | shef | 上海11选5 | 11选5系列 |
| 10019 | lnef | 辽宁11选5 | 11选5系列 |
| 10020 | hbef | 湖北11选5 | 11选5系列 |
| 10021 | cqef | 重庆11选5 | 11选5系列 |
| 10022 | gxef | 广西11选5 | 11选5系列 |
| 10023 | jlef | 吉林11选5 | 11选5系列 |
| 10024 | nmgef | 内蒙古11选5 | 11选5系列 |
| 10025 | zjef | 浙江11选5 | 11选5系列 |
| 10026 | gxft | 广西快3 | 快3系列 |
| 10027 | jlft | 吉林快3 | 快3系列 |
| 10028 | hebft | 河北快3 | 快3系列 |
| 10029 | nmgft | 内蒙古快3 | 快3系列 |
| 10030 | ahft | 安徽快3 | 快3系列 |
| 10032 | hubft | 湖北快3 | 快3系列 |
| 10033 | bjft | 北京快3 | 快3系列 |
| 10034 | tjklsf | 天津快乐十分 | 快乐十分/快乐8 |
| 10035 | jisuft | 极速飞艇 | PK10/飞艇/赛车 |
| 10036 | jisussc | 极速时时彩 | 时时彩系列 |
| 10037 | jisusc | 极速赛车 | PK10/飞艇/赛车 |
| 10038 | gxklsf | 广西快乐十分 | 快乐十分/快乐8 |
| 10039 | fcssq | 福彩双色球 | 全国彩(福彩/体彩) |
| 10040 | cjdlt | 超级大乐透 | 全国彩(福彩/体彩) |
| 10041 | fcsd | 福彩3D | 全国彩(福彩/体彩) |
| 10042 | fcqlc | 福彩七乐彩 | 全国彩(福彩/体彩) |
| 10043 | pailie3 | 体彩排列3 | 全国彩(福彩/体彩) |
| 10044 | pailie5 | 体彩排列5 | 全国彩(福彩/体彩) |
| 10045 | qxc | 体彩七星彩 | 全国彩(福彩/体彩) |
| 10046 | egxy28_old | PC蛋蛋（旧） | PC蛋蛋系列 |
| 10047 | twbg | 台湾宾果 | 台湾彩 |
| 10050 | cqqxc | 重庆幸运农场 | 其他 |
| 10052 | jisuksan | 极速快3 | 快3系列 |
| 10053 | jisuklsf | 极速快乐十分 | 快乐十分/快乐8 |
| 10054 | jisukl8 | 极速快乐8 | 快乐十分/快乐8 |
| 10055 | jisuef | 极速11选5 | 11选5系列 |
| 10056 | tencentffc | 腾讯分分彩 | 时时彩系列 |
| 10057 | xingyft | 幸运飞艇 | PK10/飞艇/赛车 |
| 10058 | sgAirship | SG飞艇 | PK10/飞艇/赛车 |
| 10059 | xyssc | 幸运时时彩 | 时时彩系列 |
| 10060 | happyCZ | 重庆欢乐生肖 | 其他 |
| 10061 | shft | 上海快3 | 快3系列 |
| 10062 | gzft | 贵州快3 | 快3系列 |
| 10063 | gsft | 甘肃快3 | 快3系列 |
| 10064 | tw_5fencai | 台湾5分彩 | 时时彩系列 |
| 10070 | tw_dlt | 台湾大乐透 | 台湾彩 |
| 10071 | tw_wlc | 台湾威力彩 | 台湾彩 |
| 10072 | tw_jc539 | 台湾今彩539 | 台湾彩 |
| 10073 | kl8 | 快乐8 | 快乐十分/快乐8 |
| 10074 | egxy28 | PC蛋蛋幸运28 | PC蛋蛋系列 |
| 10075 | sgssc | SG时时彩 | 时时彩系列 |
| 10076 | sgk3 | SG快3 | 快3系列 |
| 10077 | uklotto5 | 英国乐透5 | 其他 |
| 10078 | uklotto8 | 英国乐透8 | 其他 |
| 10079 | uklotto10 | 英国乐透10 | PK10/飞艇/赛车 |
| 10080 | uklotto20 | 英国乐透20 | 其他 |
| 10081 | speedPcEgg | 极速蛋蛋 | PK10/飞艇/赛车 |
| 10082 | sgHappy8 | SG快乐8 | 快乐十分/快乐8 |
| 10083 | sgHappy10 | SG快乐十分 | 快乐十分/快乐8 |
| 10084 | sg11x5 | SG11选5 | 11选5系列 |
| 10086 | sportjisu | 极速运动会 | 运动会系列 |
| 10087 | sportkuaile | 快乐运动会 | 运动会系列 |
| ether | etherssc | 以太时时彩 | 时时彩系列 |
| tron | tronssc | 波场时时彩 | 时时彩系列 |

### 6.3 `api.chuanqiking.com` 的 `lotCode` 对照

| 彩票名称 | 代码 | lotCode ID |
|---|---|---|
| 福彩3D | fc3d | 1 |
| 体彩排列3 | tcpl3 | 2 |
| 体彩排列5 | tcpl5 | 3 |
| 香港六合彩 | sglh | 4 |
| 澳门六合彩 | amlh | 5 |
| 新澳门六合彩 | samlh | 6 |
| 台湾五分彩 | taiwanbg | 7 |
| 币安比特分分彩 | babtffc | 8 |
| 币安以太分分彩 | baytffc | 9 |
| 奇趣腾讯分分彩 | cctsffc | 11 |
| 奇趣腾讯五分彩 | cctswfc | 12 |
| 奇趣腾讯十分彩 | cctssfc | 13 |
| 老河內五分彩 | lhnwfc | 14 |
| 澳洲幸运5 | aozxy5 | 15 |
| 168极速赛车 | jssc168 | 16 |
| 澳洲幸运10 | aozxy10 | 17 |
| 168幸运飞艇 | syft168 | 18 |
| 168极速飞艇 | jsft168 | 19 |
| 广东11选5 | gd11x5 | 20 |
| 曼谷11选5 | bk11x5 | 21 |
| 上证五分彩 | sjwfc | 22 |
| 深证五分彩 | szwfc | 23 |
| 韩国28五分彩 | hg28wfc | 24 |
| 重庆时时彩 | cqssc | 25 |
| 哈希分分彩 | hxffc | 26 |
| 哈希五分彩 | hxwfc | 27 |
| 哈希十分彩 | hxshfc | 28 |
| 哈希三分彩 | hxsfc | 29 |
| 波场分分彩 | bcffc | 30 |
| 波场三分彩 | bcsfc | 31 |
| 波场五分彩 | bcwfc | 32 |
| 分分动物运动会 | dwydhssc | 33 |
| 三分动物运动会 | dwydhsfc | 34 |
| 奖杯动物运动会 | jbdwydh | 35 |
| 奖牌动物运动会 | jpdwydh | 36 |

---

## 7. 返回字段速查

| 要查的信息 | 常见字段 |
|---|---|
| 上期开的什么号 | `preDrawCode` / `balls` |
| 上期期号 | `preDrawIssue` / `issue` |
| 下期几点开 | `drawTime` |
| 下期期号 | `drawIssue` |
| 各球大小单双 | `firstSingleDouble` ~ `fifthSingleDouble`、`firstBigSmall` ~ `fifthBigSmall` |
| 龙虎 | `dragonTiger`、`firstDT` ~ `fifthDT`、`dragon_tigers` |
| 前三 / 中三 / 后三形态 | `lastThree` / `betweenThree` / `behindThree` |
| 冠亚和 | `sum`、`sumFS`、`sumNum` |
| 冠亚和单双 | `odd_even`、`sumSingleDouble` |
| 冠亚和大小 | `big_small`、`sumBigSamll`、`sumBigSmall` |
| 当天统计 | `getPksDoubleCount.do` 的 `*Count` 字段 |

---

## 8. 注意事项汇总

1. **期号类型不统一**：`apiote122` 澳洲幸运5 期号可能是整数；`chuanqiking` 哈希分分彩期号是字符串；`168` 澳洲幸运10 期号是整数。
2. **号码前导零**：澳洲幸运10 的 `preDrawCode` 如 `"10,08,03"`，解析时先 `split` 再 `int`。
3. **`sumBigSamll` 拼写错误**：原接口字段名，不要改写为 `sumBigSmall`。
4. **龙虎可能有“和”**：部分接口返回 `2` 或中文字符，统计时留分支。
5. **gzip 压缩**：`168` 线路池、`chuanqiking` 等接口要求支持 gzip，否则 `422`。
6. **域名池**：`1688455.com`、`1688507.com` 等指向同一后端，建议域名池 + 重试。
7. **MongoDB ObjectId**：`chuanqiking` 单期接口的 `id` 是 `{"$oid": "..."}`，取值用 `d["id"]["$oid"]`。
8. **列表接口字段更少**：历史列表通常不返回彩种信息、下期预告、`serverTime`，需要单期接口补充。
9. **`limit` 上限**：`168yyy.net` 的 `limit=50` 可用，更大值需自行测试。
10. **分页缺失**：`apiote122` 列表、`168` 历史列表、`chuanqiking` 列表均未发现分页参数，一次返回固定范围。
11. **高频请求风控**：建议加 `time.sleep(1)` 等间隔。
12. **编码**：JSON 均为 UTF-8，`requests` 会自动解码。