# WTO Docs Crawler — 使用教程

> **模块**：`negotiation_crawler.crawlers.wto_docs`
> **目标站点**：[docs.wto.org](https://docs.wto.org)（WTO Documents Online）
> **主要产出**：JSONL 清单（`docs_manifest/`）、PDF 文件树（`library/`）、索引文件（`index.xlsx` / `index.csv` / `index.sqlite`）

---

## 1. 概览：WTO Docs 是什么，爬什么

WTO Documents Online（`docs.wto.org`）是 WTO 官方文件数据库，基于 ASP.NET WebForms 构建，
提供按系列符号（Symbol）搜索和面向主题（Subject）的分类检索。本模块专门针对
**渔业补贴**相关的 **8 个文件系列**，通过纯 HTTP 方式（无需浏览器）枚举文件元数据，
并下载全部公开（Unrestricted）PDF。

### 1.1 爬取的 8 个文件系列

| 序号 | 系列符号 | 中文名称       | 标签      | 输出目录                   |
| ---- | -------- | -------------- | --------- | -------------------------- |
| 1    | G/FS     | 渔业补贴委员会 | `GFS`   | `01_G-FS_渔业补贴委员会` |
| 2    | TN/RL    | 谈判           | `TN`    | `02_TN_谈判`             |
| 3    | WT/MIN   | 部长会         | `WTMIN` | `03_WT-MIN_部长会`       |
| 4    | WT/L     | 法律文本       | `WTL`   | `04_WT-L_法律文本`       |
| 5    | WT/LET   | 接受书         | `WTLET` | `05_WT-LET_接受书`       |
| 6    | G/SCM    | 补贴通报       | `GSCM`  | `06_G-SCM_补贴通报`      |
| 7    | WT/GC    | 总理事会       | `WTGC`  | `07_WT-GC_总理事会`      |
| 8    | JOB/RL   | 室文件         | `JOBRL` | `09_JOB-RL_室文件`       |

### 1.2 访问权限说明

WTO Documents Online 的文件分两类：

| 权限                           | 说明                        | 行为                                          |
| ------------------------------ | --------------------------- | --------------------------------------------- |
| **Unrestricted（公开）** | 所有人可下载                | Phase 1 枚举 + Phase 2 下载 PDF               |
| **Restricted（受限）**   | 仅 WTO 成员或登录用户可访问 | Phase 1 枚举元数据，Phase 2**跳过**下载 |

受限文件会被记录在清单中（`downloadable=false`），但不会尝试下载，
也不计入已下载数量。

---

## 2. 三阶段流水线（+ 可选 Phase 0）

爬取流程分为三个常规阶段和一个可选的浏览器阶段。默认不启用 Phase 0。

```
┌─────────────────────────────────────────────────────────────┐
│ Phase 0（可选）— harvest（Playwright，默认跳过）            │
│   用真实浏览器在 FE_S_S001.aspx 搜索框中执行全文检索，      │
│   抓取搜索结果摘要 → docs_manifest/docs_manifest.jsonl      │
│   需要安装 playwright + playwright install chromium         │
└────────────────────────┬────────────────────────────────────┘
                         │（skip_harvest=True，通常跳过）
┌────────────────────────▼────────────────────────────────────┐
│ Phase 1 — detail（枚举，纯 HTTP）                           │
│   对每个系列，用 FE_S_S006.aspx 的主题 + 系列过滤器         │
│   分页枚举全部文件（含受限），写入                           │
│   docs_manifest/detail_{LABEL}.jsonl                        │
│   字段：symbol、series、title、downloadable、access、        │
│         url、date、size、pages、doc_code                     │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│ Phase 2 — download（下载，纯 HTTP）                         │
│   读取各 detail_*.jsonl，对 downloadable=true 的记录        │
│   通过 directdoc.aspx 端点直接下载 PDF                      │
│   存储路径：library/{series_folder}/{symbol}.pdf            │
│   原地回写 downloaded、raw_path、size（字节）字段到 JSONL   │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│ Phase 3 — build_index（构建索引）                           │
│   合并所有 detail_*.jsonl，生成：                           │
│   index.xlsx  — 多 Sheet Excel（全部 + 按系列分 Sheet）     │
│   index.csv   — UTF-8 BOM CSV（可直接用 Excel 打开）        │
│   index.sqlite — SQLite，表名 documents（供 RAG/查询）      │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 输出目录结构

```
output/wto_docs/                ← 默认输出目录（可通过 --out 指定）
├── docs_manifest/              ← Phase 1 生成的 JSONL 清单
│   ├── detail_GFS.jsonl        ←   G/FS 系列（渔业补贴委员会）
│   ├── detail_TN.jsonl         ←   TN/RL 系列（谈判）
│   ├── detail_WTMIN.jsonl      ←   WT/MIN 系列（部长会）
│   ├── detail_WTL.jsonl        ←   WT/L 系列（法律文本）
│   ├── detail_WTLET.jsonl      ←   WT/LET 系列（接受书）
│   ├── detail_GSCM.jsonl       ←   G/SCM 系列（补贴通报）
│   ├── detail_WTGC.jsonl       ←   WT/GC 系列（总理事会）
│   └── detail_JOBRL.jsonl      ←   JOB/RL 系列（室文件）
├── library/                    ← Phase 2 下载的 PDF（按系列目录）
│   ├── 01_G-FS_渔业补贴委员会/
│   │   ├── G_FS_W_1.pdf
│   │   ├── G_FS_W_2.pdf
│   │   └── ...
│   ├── 02_TN_谈判/
│   ├── 03_WT-MIN_部长会/
│   ├── 04_WT-L_法律文本/
│   ├── 05_WT-LET_接受书/
│   ├── 06_G-SCM_补贴通报/
│   ├── 07_WT-GC_总理事会/
│   └── 09_JOB-RL_室文件/
├── index.xlsx                  ← Phase 3 生成的 Excel 综合索引
├── index.csv                   ← Phase 3 生成的 CSV 索引（UTF-8 BOM）
└── index.sqlite                ← Phase 3 生成的 SQLite 索引
```

---

## 4. 清单数据结构（JSONL）

每个 `detail_{LABEL}.jsonl` 中每行是一个 JSON 对象（Phase 1 写入，Phase 2 回写补充）：

| 字段             | 类型    | 来源      | 说明                                                                  |
| ---------------- | ------- | --------- | --------------------------------------------------------------------- |
| `symbol`       | str     | Phase 1   | 文档符号（如`G/FS/W/1`）                                            |
| `series`       | str     | Phase 1   | 系列前缀（如`G/FS`）                                                |
| `title`        | str     | Phase 1   | 文件标题                                                              |
| `downloadable` | bool    | Phase 1   | `true` = 公开可下载；`false` = 受限                               |
| `access`       | str     | Phase 1   | 原始权限字符串（如`Unrestricted`、`Restricted`）                  |
| `url`          | str     | Phase 1   | directdoc 直链 URL                                                    |
| `date`         | str     | Phase 1   | 日期（格式`DD/MM/YYYY`）                                            |
| `size`         | str/int | Phase 1/2 | Phase 1 为字符串（如`"120 KB"`）；Phase 2 下载后覆盖为字节数（int） |
| `pages`        | str     | Phase 1   | 页数字符串（如`"12"`）                                              |
| `doc_code`     | str     | Phase 1   | 内部文档编号（如`20-0123`）                                         |
| `body`         | str     | Phase 1   | 系列标签（如`GFS`）                                                 |
| `fisheries`    | bool    | Phase 1   | 标题是否命中渔业关键词（仅 enumerate.py 路径）                        |
| `downloaded`   | bool    | Phase 2   | Phase 2 写入；下载成功为`true`                                      |
| `raw_path`     | str     | Phase 2   | 本地 PDF 路径（Phase 2 成功后写入）                                   |
| `error`        | str     | Phase 2   | Phase 2 失败时的错误信息                                              |

**JSONL 示例（Phase 2 完成后）：**

```json
{
  "symbol": "G/FS/W/1",
  "series": "G/FS",
  "title": "Communication from the Faroe Islands - Submission on Fisheries Subsidies",
  "downloadable": true,
  "access": "Unrestricted",
  "url": "https://docs.wto.org/dol2fe/Pages/SS/directdoc.aspx?filename=q%3A%2FG%2FFS%2FW%2F1.pdf&Open=True",
  "date": "15/06/2017",
  "size": 123456,
  "pages": "8",
  "doc_code": "17-3456",
  "body": "GFS",
  "downloaded": true,
  "raw_path": "/data/wto_docs/library/01_G-FS_渔业补贴委员会/G_FS_W_1.pdf"
}
```

---

## 5. CLI 使用

### 5.1 安装

```bash
# 在项目根目录
pip install -e .
# 或者
uv pip install -e .
```

如需使用 Phase 0（Playwright 搜索），额外安装：

```bash
pip install playwright
playwright install chromium
```

### 5.2 基础命令

#### 完整运行（Phase 1 + Phase 2 + Phase 3）

```bash
negotiation-crawler run wto_docs --out /data/wto_docs
```

输出目录默认为 `config.yaml` 中 `defaults.wto_docs`（`./output/wto_docs`）。

#### 指定自定义输出目录

```bash
negotiation-crawler run wto_docs --out /mnt/nas/research/wto_docs_corpus
```

#### 只运行 Phase 1（枚举清单，不下载 PDF）

```bash
negotiation-crawler run wto_docs --out /data/wto_docs --set skip_download=true
```

#### 只运行 Phase 2（清单已有，只补充下载）

```bash
negotiation-crawler run wto_docs --out /data/wto_docs --set skip_detail=true
```

#### 只运行某一个系列

```bash
# 只处理 G/FS 系列（标签为 GFS）
negotiation-crawler run wto_docs --out /data/wto_docs --set only_series=GFS

# 只处理 TN/RL 系列
negotiation-crawler run wto_docs --out /data/wto_docs --set only_series=TN
```

#### 断点续传（中途中断后继续）

```bash
# resume=true（默认值）：Phase 1 跳过已有的 JSONL；Phase 2 跳过已标记 downloaded=true 的记录
negotiation-crawler run wto_docs --out /data/wto_docs --set resume=true
```

#### 强制重新枚举（覆盖已有清单）

```bash
# resume=false 会覆盖已有 JSONL，重新全量枚举
negotiation-crawler run wto_docs --out /data/wto_docs --set resume=false
```

#### 仅下载渔业关键词相关的文件

```bash
# 只下载 title 命中渔业关键词（fisheries=true）的文件
negotiation-crawler run wto_docs --out /data/wto_docs --set fisheries_only=true
```

#### 仅重建索引（不重爬）

```bash
# 从 --out 下的 docs_manifest/ 重新生成 index.xlsx / index.csv / index.sqlite
negotiation-crawler xlsx wto_docs --out /data/wto_docs
```

#### 调整请求间隔（默认 0.8 秒）

```bash
negotiation-crawler run wto_docs --out /data/wto_docs --set delay=1.5
```

#### 启用 Phase 0（Playwright 搜索，需安装 playwright）

```bash
negotiation-crawler run wto_docs --out /data/wto_docs \
  --set skip_harvest=false \
  --set query="fisheries subsidies" \
  --set headed=false \
  --set max_harvest_pages=100
```

### 5.3 组合 `--set` 选项

```bash
# 只枚举 GFS 系列，不下载 PDF，调整延迟
negotiation-crawler run wto_docs \
  --out /data/wto_docs \
  --set only_series=GFS \
  --set skip_download=true \
  --set delay=1.0

# 续传：跳过 Phase 1，只对 WTMIN 系列补充下载
negotiation-crawler run wto_docs \
  --out /data/wto_docs \
  --set skip_detail=true \
  --set only_series=WTMIN \
  --set resume=true
```

### 5.4 可用 `--set` 参数汇总

| 参数                  | 类型  | 默认值                    | 说明                                                                  |
| --------------------- | ----- | ------------------------- | --------------------------------------------------------------------- |
| `skip_detail`       | bool  | `false`                 | 跳过 Phase 1（清单已存在时用于续传）                                  |
| `only_series`       | str   | `None`                  | 只处理指定系列（标签，如`GFS`、`TN`、`WTMIN`；见第 1.1 节表格） |
| `delay`             | float | `0.8`                   | 每次 HTTP 请求间隔（秒）；建议不低于 0.5                              |
| `resume`            | bool  | `true`                  | 断点续传：Phase 1 跳过已有 JSONL；Phase 2 跳过已下载记录              |
| `skip_download`     | bool  | `false`                 | 跳过 Phase 2（只建清单，不下载 PDF）                                  |
| `fisheries_only`    | bool  | `false`                 | Phase 2 只下载`fisheries=true` 的记录                               |
| `skip_harvest`      | bool  | `true`                  | 跳过 Phase 0（Playwright），默认不启用                                |
| `query`             | str   | `"fisheries subsidies"` | Phase 0 全文搜索词                                                    |
| `headed`            | bool  | `false`                 | Phase 0 是否显示浏览器窗口（调试时设为`true`）                      |
| `max_harvest_pages` | int   | `50`                    | Phase 0 最多爬取的结果页数                                            |

---

## 6. Python API 使用

### 6.1 通过 `WtoDocsCrawler` 类

```python
from negotiation_crawler.crawlers.wto_docs import WtoDocsCrawler

crawler = WtoDocsCrawler()
result = crawler.run(
    output_dir="/data/wto_docs",
    skip_detail=False,
    only_series=None,       # 或 "GFS"、"TN" 等
    delay=0.8,
    resume=True,
    skip_download=False,
    fisheries_only=False,
    skip_harvest=True,      # 默认不启用 Playwright
)

if result.success:
    print(f"Done → {result.output_dir}")
    print(result.log)       # 每个系列的枚举/下载摘要
else:
    print(f"Failed: {result.error}")
```

### 6.2 直接调用底层函数

#### Phase 1：枚举文件元数据

```python
from pathlib import Path
from negotiation_crawler.crawlers.wto_docs.fetch.detail import run as detail_run

manifest_dir = Path("/data/wto_docs/docs_manifest")

# 枚举 G/FS 系列
recs = detail_run(
    filter_key="SymbolList",
    filter_val='"G/FS*"',
    label="GFS",
    out_path=manifest_dir / "detail_GFS.jsonl",
    delay=0.8,
)
print(f"G/FS: {len(recs)} 条，其中可下载 {sum(1 for r in recs if r['downloadable'])} 条")

# 枚举 TN/RL 系列（使用 CollectionList 过滤器）
recs_tn = detail_run(
    filter_key="CollectionList",
    filter_val='"TN"',
    label="TN",
    out_path=manifest_dir / "detail_TN.jsonl",
    delay=0.8,
)
```

#### Phase 2：下载 PDF

```python
from pathlib import Path
from negotiation_crawler.crawlers.wto_docs.fetch.download import download_listing

stats = download_listing(
    listing_path=Path("/data/wto_docs/docs_manifest/detail_GFS.jsonl"),
    dest_dir=Path("/data/wto_docs/library/01_G-FS_渔业补贴委员会"),
    delay=0.8,
    fisheries_only=False,  # True 则只下载渔业关键词相关文件
    resume=True,           # 跳过已标记 downloaded=True 的记录
)
print(f"ok={stats['ok']}  failed={stats['failed']}  total={stats['total']}")
```

#### Phase 3：构建综合索引

```python
from pathlib import Path
from negotiation_crawler.crawlers.wto_docs.process import build_index

idx = build_index(
    manifest_dir=Path("/data/wto_docs/docs_manifest"),
    library_dir=Path("/data/wto_docs/library"),
    out_dir=Path("/data/wto_docs"),
)
print(f"total={idx['total']}  downloadable={idx['downloadable']}  restricted={idx['restricted']}")
print(f"XLSX   → {idx['xlsx']}")
print(f"CSV    → {idx['csv']}")
print(f"SQLite → {idx['sqlite']}")
```

### 6.3 直接操作 SQLite 索引

```python
import sqlite3
from pathlib import Path

con = sqlite3.connect(Path("/data/wto_docs/index.sqlite"))
con.row_factory = sqlite3.Row

# 查询所有公开的 G/FS 系列文件，按年份降序
rows = con.execute("""
    SELECT symbol, title, year, date, size_kb, pages, local_path
    FROM documents
    WHERE body = 'GFS'
      AND downloadable = 1
    ORDER BY year DESC, symbol
""").fetchall()

for r in rows:
    print(f"{r['year']}  {r['symbol']:<25}  {r['title'][:60]}")

con.close()
```

```python
# 查询所有受限文件（未下载）的分布
rows = con.execute("""
    SELECT body, COUNT(*) as cnt
    FROM documents
    WHERE downloadable = 0
    GROUP BY body
    ORDER BY cnt DESC
""").fetchall()

for r in rows:
    print(f"{r['body']:8}  {r['cnt']} 条受限文件")
```

### 6.4 只对单个系列重新枚举并下载

```python
from pathlib import Path
from negotiation_crawler.crawlers.wto_docs import SERIES
from negotiation_crawler.crawlers.wto_docs.fetch.detail import run as detail_run
from negotiation_crawler.crawlers.wto_docs.fetch.download import download_listing

out = Path("/data/wto_docs")
manifest_dir = out / "docs_manifest"
library_dir  = out / "library"

# 找到 WTMIN 系列定义
s = next(x for x in SERIES if x["label"] == "WTMIN")

# 重新枚举（覆盖旧清单）
jsonl = manifest_dir / f"detail_{s['label']}.jsonl"
detail_run(
    filter_key=s["detail_key"],
    filter_val=s["detail_val"],
    label=s["label"],
    out_path=jsonl,
    delay=1.0,
)

# 下载
download_listing(
    listing_path=jsonl,
    dest_dir=library_dir / s["folder"],
    delay=1.0,
    resume=True,
)
```

### 6.5 使用 `enumerate.py` 的符号模式查询（备用路径）

`detail.py` 使用主题+系列面向的检索方式（推荐）。`enumerate.py` 则使用 WTO 搜索语言直接按 Symbol 模式查询，产出略有不同（含 `fisheries` 布尔字段，无 `date`/`size`/`pages`）：

```python
from pathlib import Path
from negotiation_crawler.crawlers.wto_docs.fetch.enumerate import run as enum_run

recs = enum_run(
    query="(@Symbol= G/FS/*)",
    out_path=Path("/data/wto_docs/docs_manifest/enum_GFS.jsonl"),
    delay=1.0,
    fisheries_only=False,
)
print(f"符号查询结果: {len(recs)} 条，渔业关键词命中: {sum(1 for r in recs if r['fisheries'])} 条")
```

---

## 7. FastAPI HTTP 服务

爬虫提供异步 HTTP 接口，供 Java 等外部系统调用。接口即时返回 `task_id`，
任务在后台线程中运行，调用方轮询状态。

### 7.1 启动服务

```bash
# 使用 config.yaml 中的 host/port（默认 0.0.0.0:8000）
negotiation-crawler serve

# 指定端口
negotiation-crawler serve --host 127.0.0.1 --port 9000
```

启动后访问自动生成的 OpenAPI 文档：

```
http://localhost:8000/docs       ← Swagger UI（可交互）
http://localhost:8000/redoc      ← ReDoc 文档
```

### 7.2 接口一览

| 方法     | 路径                    | 说明                               |
| -------- | ----------------------- | ---------------------------------- |
| `GET`  | `/health`             | 健康检查，返回`{"status": "ok"}` |
| `GET`  | `/crawlers`           | 列出所有可用爬虫模块               |
| `POST` | `/run/{crawler_name}` | 启动爬虫（异步），返回`task_id`  |
| `GET`  | `/tasks/{task_id}`    | 查询单个任务状态和结果             |
| `GET`  | `/tasks`              | 列出当前进程内所有任务             |

`crawler_name` 可选值：`iotc`、`fishery_book`、`wto_site`、`wto_docs`、`all`。

### 7.3 接口详情

#### `POST /run/wto_docs`

**请求体**（JSON）：

```json
{
  "output_dir": "/data/wto_docs",
  "params": {
    "skip_detail": false,
    "only_series": null,
    "delay": 0.8,
    "resume": true,
    "skip_download": false,
    "fisheries_only": false,
    "skip_harvest": true
  }
}
```

> `output_dir` 和 `params` 均为可选。`params` 的键与 CLI `--set` 参数完全对应（见第 5.4 节）。

**响应**（立即返回，任务在后台运行）：

```json
{
  "task_id": "4a8b3c1d-7e05-4f9a-b6g2-1c3d5e7f9a0b",
  "crawler": "wto_docs",
  "state": "PENDING"
}
```

#### `GET /tasks/{task_id}`

**完成时**：

```json
{
  "task_id": "4a8b3c1d-...",
  "crawler": "wto_docs",
  "state": "DONE",
  "output_dir": "/data/wto_docs",
  "error": null,
  "log": "[GFS] 423 docs (389 downloadable)\n[TN] 217 docs (198 downloadable)\n..."
}
```

`state` 取值：`PENDING` → `RUNNING` → `DONE` / `FAILED`。

### 7.4 curl 完整示例

```bash
BASE="http://localhost:8000"

# 1. 启动 wto_docs 爬取（只枚举 G/FS 系列，不下载）
TASK=$(curl -s -X POST "$BASE/run/wto_docs" \
  -H "Content-Type: application/json" \
  -d '{"output_dir": "/data/wto_docs", "params": {"only_series": "GFS", "skip_download": true}}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")

echo "task_id = $TASK"

# 2. 轮询状态，直到完成
while true; do
  STATE=$(curl -s "$BASE/tasks/$TASK" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['state'])")
  echo "state = $STATE"
  [ "$STATE" = "DONE" ] || [ "$STATE" = "FAILED" ] && break
  sleep 15
done

# 3. 查看日志（包含每个系列的枚举/下载统计）
curl -s "$BASE/tasks/$TASK" | python3 -m json.tool
```

### 7.5 Python httpx 示例

```python
import time
import httpx

BASE = "http://localhost:8000"

# 启动全系列爬取
resp = httpx.post(f"{BASE}/run/wto_docs", json={
    "output_dir": "/data/wto_docs",
    "params": {
        "resume": True,
        "delay": 1.0,
        "fisheries_only": False,
    }
})
resp.raise_for_status()
task_id = resp.json()["task_id"]
print(f"Started: task_id={task_id}")

# 轮询直到完成
while True:
    task = httpx.get(f"{BASE}/tasks/{task_id}").json()
    state = task["state"]
    print(f"  state={state}")
    if state in ("DONE", "FAILED"):
        break
    time.sleep(30)   # 完整爬取耗时较长，建议间隔 30 秒以上

if state == "DONE":
    print(f"Success → {task['output_dir']}")
    if task.get("log"):
        print(task["log"])
else:
    print(f"Failed: {task['error']}")
```

### 7.6 注意事项

- **任务生命周期**：任务存储在进程内存中，重启服务后历史任务丢失。建议在业务层持久化
  `task_id` 与 `output_dir`。
- **耗时**：完整爬取 8 个系列（含下载）通常需要 **30 分钟至数小时**，视系列文件数和网络条件而定。
  轮询间隔建议 ≥ 30 秒。
- **并发**：同一进程可接受多个 `POST /run` 请求，每个任务在独立线程中运行，
  但 docs.wto.org 有速率限制，建议避免同时提交多个 wto_docs 任务。

---

## 8. 索引文件结构

Phase 3 生成三种格式的综合索引，内容相同，格式不同：

### 8.1 Excel 台账（index.xlsx）

| Sheet                    | 内容                                                   |
| ------------------------ | ------------------------------------------------------ |
| `全部`                 | 所有系列的全部记录（按 body → series → symbol 排序） |
| `G-FS—渔业补贴委员会` | 仅 G/FS 系列                                           |
| `TN-RL—谈判`          | 仅 TN/RL 系列                                          |
| `WT-MIN—部长会`       | 仅 WT/MIN 系列                                         |
| …                       | 每个系列一个 Sheet，共 8 个                            |

**数据列（XLSX_HEADERS）：**

| 列名     | 含义                                       |
| -------- | ------------------------------------------ |
| 序号     | 行号（从 1 开始）                          |
| 系列     | 系列中文名（如`G/FS — 渔业补贴委员会`） |
| 文档号   | 文档符号（如`G/FS/W/1`）                 |
| 标题     | 文件标题                                   |
| 年份     | 文件年份（整数）                           |
| 日期     | 日期（ISO 格式`YYYY-MM-DD`）             |
| 大小(KB) | 文件大小（KB，实数）                       |
| 页数     | PDF 页数（整数）                           |
| 访问权限 | `公开` / `受限`                        |
| 已下载   | `是` / `否`                            |
| 下载链接 | directdoc URL                              |
| 本地路径 | PDF 本地路径（若已下载）                   |

### 8.2 CSV 索引（index.csv）

UTF-8 BOM 编码，可直接用 Excel 打开或 DuckDB 查询：

```sql
-- DuckDB 示例
SELECT body, COUNT(*) as total, SUM(downloadable) as downloaded
FROM read_csv_auto('/data/wto_docs/index.csv', header=true)
GROUP BY body;
```

### 8.3 SQLite 索引（index.sqlite）

表名 `documents`，建有 `body`、`year`、`series` 三个索引：

| 列名             | 类型    | 说明                                            |
| ---------------- | ------- | ----------------------------------------------- |
| `doc_code`     | TEXT    | WTO 内部文档编号                                |
| `symbol`       | TEXT    | 文档符号（如`G/FS/W/1`）                      |
| `title`        | TEXT    | 标题                                            |
| `body`         | TEXT    | 系列标签（GFS、TN 等）                          |
| `series`       | TEXT    | 系列前缀（G/FS、TN/RL 等）                      |
| `year`         | INTEGER | 年份                                            |
| `date`         | TEXT    | 日期（ISO 格式）                                |
| `size_kb`      | REAL    | 文件大小（KB）                                  |
| `pages`        | INTEGER | 页数                                            |
| `access`       | TEXT    | `公开` / `受限`                             |
| `downloadable` | INTEGER | `1` = 已下载成功；`0` = 未下载              |
| `subjects`     | TEXT    | 主题标签（从 subject_tags.json 加载，通常为空） |
| `local_path`   | TEXT    | PDF 本地绝对路径                                |
| `url`          | TEXT    | directdoc 下载链接                              |

---

## 9. 典型使用场景

### 场景 A：首次完整运行

```bash
negotiation-crawler run wto_docs --out /data/wto_docs_corpus
```

预计耗时：视文件总数和网络条件，通常 **30 分钟至 2 小时**。

### 场景 B：增量更新（网站有新文件）

```bash
# resume=false 强制重新枚举所有系列（JSONL 会被覆盖）
# 已下载的 PDF 不会重复下载（文件名匹配则跳过）
negotiation-crawler run wto_docs --out /data/wto_docs_corpus \
  --set resume=false
```

### 场景 C：断点续传（中途被打断）

```bash
# Phase 1 跳过已有的 detail_*.jsonl
# Phase 2 跳过已标记 downloaded=true 的记录
negotiation-crawler run wto_docs --out /data/wto_docs_corpus --set resume=true
```

### 场景 D：只处理某一个系列

```bash
# 只枚举并下载 G/FS 系列（渔业补贴委员会）
negotiation-crawler run wto_docs \
  --out /data/wto_docs_corpus \
  --set only_series=GFS
```

### 场景 E：只建清单，稍后再下载

```bash
# Step 1：只枚举，不下载
negotiation-crawler run wto_docs --out /data/wto_docs \
  --set skip_download=true

# Step 2：只下载（跳过 Phase 1）
negotiation-crawler run wto_docs --out /data/wto_docs \
  --set skip_detail=true
```

### 场景 F：仅重建索引（不重爬）

```bash
negotiation-crawler xlsx wto_docs --out /data/wto_docs_corpus
```

### 场景 G：只保留渔业关键词相关文件（精简语料库）

```bash
negotiation-crawler run wto_docs \
  --out /data/wto_docs_corpus \
  --set fisheries_only=true
```

> 注意：`fisheries_only` 过滤在 Phase 2 基于 `fisheries` 布尔字段执行。
> 此字段由 `enumerate.py` 路径填充，`detail.py`（Phase 1 默认路径）不产生该字段，
> 因此 `fisheries_only=true` 仅对已有 `fisheries` 字段的 JSONL 有效。

---

## 10. 配置文件

`config.yaml`（项目根目录）控制默认输出路径：

```yaml
defaults:
  wto_docs: "./output/wto_docs"   # 默认输出目录；--out 参数可覆盖

api:
  host: "0.0.0.0"
  port: 8000
```

网络常量直接在源文件中定义（`fetch/detail.py`、`fetch/download.py`）：

```python
# fetch/detail.py 和 fetch/download.py 共用
UA    = "wto-fish-corpus-bot/1.0 (research; contact: research@example.com)"
BASE  = "https://docs.wto.org/dol2fe/Pages/FE_Search/FE_S_S006.aspx"
# 每次请求间隔由 delay 参数控制（默认 0.8 秒）
```

系列定义（`SERIES` 列表）在 `negotiation_crawler/crawlers/wto_docs/__init__.py` 中，
如需新增或修改系列，在此编辑。

---

## 11. 依赖

| 包                        | 用途                                                | 是否必须 |
| ------------------------- | --------------------------------------------------- | -------- |
| `httpx`                 | HTTP 请求（Phase 1/2 枚举和下载）                   | 是       |
| `openpyxl`              | Excel 导出（Phase 3）                               | 是       |
| `fastapi` + `uvicorn` | HTTP 服务（`serve` 命令）                         | 是       |
| `playwright`            | Phase 0 浏览器搜索（`skip_harvest=false` 时使用） | 可选     |

安装含 Playwright 的可选依赖：

```bash
pip install -e ".[wto-docs-harvest]"
playwright install chromium
```

---

## 12. 常见问题

**Q：运行到一半崩溃了怎么办？**
A：重新执行同一命令，保持 `resume=true`（默认值）。Phase 1 会跳过已存在的
`detail_*.jsonl`；Phase 2 会跳过 JSONL 中已标记 `downloaded=true` 的记录。

**Q：某个系列的 JSONL 文件内容不完整（总数偏少），如何重新枚举？**
A：删除对应的 `detail_{LABEL}.jsonl`，然后重新运行，或使用 `--set resume=false`
强制覆盖全部系列。

**Q：下载失败的文件能重试吗？**
A：能。`downloaded=false` 或无 `downloaded` 字段的记录会在下次运行时自动重试。
只需再次执行 `--set skip_detail=true`（保留清单，只重跑 Phase 2）：

```bash
negotiation-crawler run wto_docs --out /data/wto_docs \
  --set skip_detail=true \
  --set resume=true
```

**Q：受限文件能不能下载？**
A：受限（Restricted）文件在当前版本中不会被下载。如果您拥有 WTO 会员账号，
可以启用 Phase 0（`skip_harvest=false`、`headed=true`、`login=true`），
在浏览器中手动登录后再自动爬取结果列表，但 Phase 2 的下载逻辑仍需额外修改才能
携带登录 Cookie。

**Q：`fisheries_only=true` 但没有过滤任何结果？**
A：`fisheries` 字段由 `enumerate.py` 路径填充，而 Phase 1 默认使用 `detail.py`，
不产生该字段。若要过滤，需先用 `enumerate.py` 或手动为 JSONL 中的记录打标，
或改用 `--set only_series=GFS` 等按系列精确筛选。

**Q：`index.xlsx` 中的"本地路径"列为空？**
A：说明 Phase 2 尚未完成，或该文件是受限文件。Phase 3 中 `local_path` 字段由
`_local_path()` 函数检查对应 `library/{folder}/{symbol}.pdf` 是否存在后填入；
若文件不存在则留空。先运行 Phase 2 下载完毕后，再重建索引即可：

```bash
negotiation-crawler xlsx wto_docs --out /data/wto_docs
```

**Q：如何将结果合并到统一数据库？**
A：

```bash
negotiation-crawler export --base /data/output --module wto_docs --db /data/unified.sqlite
```

也可一次导入所有模块：

```bash
negotiation-crawler export --base /data/output --db /data/unified.sqlite
```
