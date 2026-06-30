# IOTC Crawler — 使用教程

> **模块**：`negotiation_crawler.crawlers.iotc`  
> **目标站点**：[iotc.org/documents](https://iotc.org/documents)  
> **主要产出**：SQLite 清单（`manifest.sqlite`）、PDF 文件树、Excel 台账（`index.xlsx`）

---

## 1. 概览：IOTC 是什么，爬什么

IOTC（Indian Ocean Tuna Commission，印度洋金枪鱼委员会）在其网站上以 Drupal 视图的形式
公开了 **31 种文件类型**的完整档案，涵盖会议报告、养护管理措施提案、合规报告、国家报告、
科学数据等。本模块系统地抓取这些文件，并将元数据和 PDF 文件整理为结构化的研究语料库。

### 1.1 爬取范围

| 类别组 | 包含类型（英文） |
|--------|-----------------|
| 会议报告类 | Meeting Report |
| 会议文件类 | Meeting documents, Meeting information, Meeting Minutes, Executive Summaries |
| 通函类 | Circulars |
| 提案类 | CMM Proposals, Implementation reports |
| 合规报告类 | Compliance Reports, Final/Provisional/Summary compliance reports, Compliance questionnaires, Response to feedback letter |
| 国家报告类 | National Reports |
| 信息文件类 | Information papers, NGO Statements |
| 参考报告类 | Reports from other meetings, Consultant reports, Project report, FAO Documents |
| 科学数据类 | Datasets, Stock Assessment Input and Output files |
| 参考文件类 | Reference Documents |
| 出版物类 | Publications |
| 指南类 | Guidelines |
| 通用文件类 | General |
| 行政文件类 | CNCP applications, Inspection reports, Letters of Credentials (×2) |

默认只抓取**英文文件**（URL 参数 `langcode=en`），法语文件会通过文件名 `*F.pdf` 和
reference 中的 `CTOI` / `CIRCULAIRE` 标记自动过滤。

---

## 2. 四阶段流水线

爬取流程分为四个独立的可控阶段，每个阶段都可以单独重跑而不影响其他阶段的已有结果。

```
┌─────────────────────────────────────────────────────────┐
│ Phase 1 — build_manifest                                │
│   遍历 31 种文件类型的列表页（分页），提取每条记录的   │
│   reference、title、landing_url、pdf_url、circulated，  │
│   写入 manifest.sqlite（pdf_url 为主键，重复跳过）      │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│ Phase 2 — enrich_metadata                               │
│   对每条记录访问其 landing_url（文档详情页），          │
│   补充 meta_type、year、meeting、session、authors 字段  │
│   同时用文件名 NR## 模式识别 National Report 的国家     │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│ Phase 3 — download_pdfs                                 │
│   下载所有 status='pending' 的 PDF                      │
│   存储路径：pdf_dir/<doc_type>/<year>/<filename>.pdf    │
│   记录 SHA-256、文件大小、页数；重复文件（SHA-256 相同）│
│   复用已有路径，不重复下载                              │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│ Phase 4 — build_xlsx                                    │
│   读取 manifest.sqlite，生成 index.xlsx                 │
│   Sheet 1: All - 全部（所有记录）                       │
│   Sheet 2…N: 每种 doc_type 一个 sheet（按类别组排序）  │
│   最后: Statistics - 汇总统计                           │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 输出目录结构

```
output/iotc/                     ← 默认输出目录（可通过 --out 指定）
├── manifest.sqlite              ← 核心清单数据库
├── index.xlsx                   ← Excel 台账
├── pdfs/                        ← PDF 文件树
│   ├── Meeting Report/
│   │   ├── 2023/
│   │   │   └── IOTC-2023-SC26-R[E].pdf
│   │   └── 2024/
│   ├── National Reports/
│   │   ├── 2023/
│   │   └── ...
│   └── ...（每种 doc_type 一个子目录）
└── (crawl.log)                  ← 运行日志（如果配置了）
```

---

## 4. 数据库 Schema

`manifest.sqlite` 中有一张 `docs` 表：

| 列名 | 类型 | 说明 |
|------|------|------|
| `pdf_url` | TEXT PK | PDF 直链，用作唯一键 |
| `reference` | TEXT | IOTC 文件编号（如 `IOTC-2024-SC27-R01[E]`） |
| `doc_type` | TEXT | 文件类型英文名（如 `Meeting Report`） |
| `doc_type_zh` | TEXT | 文件类型中文名 |
| `category_group` | TEXT | 类别组（如 `会议报告类`） |
| `title` | TEXT | 文件标题 |
| `landing_url` | TEXT | 详情页 URL |
| `circulated` | TEXT | 发布/流通日期（格式 `DD/MM/YYYY`） |
| `language` | TEXT | 语言代码（`en`） |
| `meta_type` | TEXT | 详情页抓取的类型（Phase 2 填入） |
| `meeting` | TEXT | 会议名称（Phase 2 填入） |
| `session` | TEXT | 届次（Phase 2 填入） |
| `year` | TEXT | 年份（从 URL 或 reference 提取） |
| `authors` | TEXT | 作者（Phase 2 填入） |
| `country` | TEXT | 国家（National Reports 专用，Phase 2 填入） |
| `local_path` | TEXT | PDF 本地存储路径（Phase 3 填入） |
| `sha256` | TEXT | PDF 文件 SHA-256（Phase 3 填入） |
| `file_size_kb` | REAL | 文件大小（KB，Phase 3 填入） |
| `page_count` | INTEGER | PDF 页数（需安装 `pypdf`，Phase 3 填入） |
| `status` | TEXT | `pending` → `downloaded` / `failed` |

---

## 5. CLI 使用

### 5.1 安装

```bash
# 在项目根目录
pip install -e .
# 或者
uv pip install -e .
```

### 5.2 基础命令

#### 完整运行（四个阶段全部执行）

```bash
negotiation-crawler run iotc --out /data/iotc
```

输出目录默认为 `config.yaml` 中 `defaults.iotc`（`./output/iotc`）。

#### 指定自定义输出目录

```bash
negotiation-crawler run iotc --out /mnt/nas/research/iotc_corpus
```

#### 仅构建清单（Phase 1），不下载 PDF

```bash
negotiation-crawler run iotc --out /data/iotc --set list_only=true
```

#### 仅运行 Phase 1 和 Phase 2（建清单 + 丰富元数据），不下载 PDF

```bash
negotiation-crawler run iotc --out /data/iotc \
  --set enrich=true \
  --set build_xlsx=false
```
> 注意：`list_only=true` 会跳过 PDF 下载（Phase 3），但仍执行 Phase 4（生成 xlsx）。

#### 跳过 Phase 1（清单已存在，继续未完成的工作）

```bash
negotiation-crawler run iotc --out /data/iotc --set skip_manifest=true
```

#### 仅处理特定文件类型

```bash
# 只下载 "National Reports"（Phase 3 和 Phase 2 只处理该类型）
negotiation-crawler run iotc --out /data/iotc --set only="National Reports"
```

#### PDF 存储在单独的磁盘

```bash
negotiation-crawler run iotc \
  --out /data/iotc \
  --set pdf_dir=/mnt/large_disk/iotc_pdfs
```

#### 限制处理数量（适合测试）

```bash
# 每个阶段最多处理 10 条记录
negotiation-crawler run iotc --out /data/test_run --set limit=10
```

#### 包含法语文件

```bash
negotiation-crawler run iotc --out /data/iotc --set all_langs=true
```

#### 仅重建 Excel 台账（不重爬）

```bash
# 从 --out 推断 manifest.sqlite 和 index.xlsx 路径
negotiation-crawler xlsx iotc --out /data/iotc

# 显式指定路径
negotiation-crawler xlsx iotc \
  --db /data/iotc/manifest.sqlite \
  --xlsx /data/iotc/2024_report.xlsx
```

### 5.3 组合 `--set` 选项

`--set` 支持多次使用，布尔值写 `true`/`false`，整数会自动转换：

```bash
negotiation-crawler run iotc \
  --out /data/iotc \
  --set skip_manifest=true \
  --set enrich=true \
  --set build_xlsx=true \
  --set only="Meeting Report" \
  --set limit=50
```

### 5.4 可用 `--set` 参数汇总

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `skip_manifest` | bool | `false` | 跳过 Phase 1（清单已存在时用于续传） |
| `list_only` | bool | `false` | 只建清单和生成 xlsx，不下载 PDF |
| `enrich` | bool | `true` | 是否执行 Phase 2（访问详情页补充元数据） |
| `build_xlsx` | bool | `true` | 是否执行 Phase 4（生成 xlsx） |
| `all_langs` | bool | `false` | 包含所有语言（默认只抓英文） |
| `limit` | int | `None` | 每阶段最多处理 N 条记录（测试用） |
| `only` | str | `None` | 只处理指定 doc_type（精确匹配英文名） |
| `pdf_dir` | str | `{out}/pdfs` | PDF 存储目录（可独立指定到大磁盘） |

---

## 6. Python API 使用

### 6.1 通过 `IotcCrawler` 类

```python
from negotiation_crawler.crawlers.iotc import IotcCrawler

crawler = IotcCrawler()
result = crawler.run(
    output_dir="/data/iotc",
    skip_manifest=False,
    enrich=True,
    build_xlsx=True,
    all_langs=False,
    limit=None,
    only=None,
    pdf_dir=None,
)

if result.success:
    print(f"Done → {result.output_dir}")
else:
    print(f"Failed: {result.error}")
```

### 6.2 直接调用底层函数

各阶段函数在 `negotiation_crawler.crawlers.iotc.fetch.crawler` 中：

```python
from pathlib import Path
from negotiation_crawler.crawlers.iotc.fetch.crawler import (
    build_manifest,
    enrich_metadata,
    download_pdfs,
)
from negotiation_crawler.crawlers.iotc.process.xlsx_builder import build_xlsx
from negotiation_crawler.crawlers.iotc.storage.db import init_db, get_stats

db_path   = Path("/data/iotc/manifest.sqlite")
pdf_dir   = Path("/data/iotc/pdfs")
xlsx_path = Path("/data/iotc/index.xlsx")

# Phase 1：建立清单
build_manifest(db_path=db_path, english_only=True, limit=None)

# Phase 2：丰富元数据
enrich_metadata(db_path=db_path, limit=None, doc_type_filter=None)

# Phase 3：下载 PDF
download_pdfs(db_path=db_path, pdf_dir=pdf_dir, limit=None, doc_type_filter=None)

# Phase 4：生成 Excel
build_xlsx(db_path, xlsx_path)

# 查询统计
conn = init_db(db_path)
stats = get_stats(conn)
conn.close()
print(f"total={stats['total']}  downloaded={stats['downloaded']}  "
      f"pending={stats['pending']}  failed={stats['failed']}")
```

### 6.3 直接操作数据库

```python
import sqlite3
from pathlib import Path

db_path = Path("/data/iotc/manifest.sqlite")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# 查询所有已下载的国家报告
rows = conn.execute("""
    SELECT reference, title, country, year, file_size_kb, page_count
    FROM docs
    WHERE doc_type = 'National Reports'
      AND status = 'downloaded'
      AND language = 'en'
    ORDER BY year DESC, country
""").fetchall()

for r in rows:
    print(f"{r['year']}  {r['country']:25}  {r['reference']}")

conn.close()
```

### 6.4 只针对某类文件执行特定阶段

```python
from pathlib import Path
from negotiation_crawler.crawlers.iotc.fetch.crawler import download_pdfs

# 只补充下载"Meeting Report"类型（Phase 3 续传）
download_pdfs(
    db_path=Path("/data/iotc/manifest.sqlite"),
    pdf_dir=Path("/data/iotc/pdfs"),
    doc_type_filter="Meeting Report",
)
```

### 6.5 分类工具：国家识别与行标提取

```python
from negotiation_crawler.crawlers.iotc.classifier.classifier import (
    country_from_name,
    classify_row,
    fix_manifest_countries,
)

# 从 PDF URL 识别国家
url = "https://iotc.org/sites/default/files/2024/IOTC-2024-SC27-NR07_China.pdf"
country = country_from_name(url, title="National Report - China")
print(country)  # → "China"

# 提取展示分类标签和会议缩写
result = classify_row(
    doc_type="Meeting Report",
    meta_type="Meeting report",
    meeting="27th Session of the Scientific Committee (SC27)",
    year="2024",
)
print(result)  # → {"display_category": "Meeting report", "meeting_abbr": "SC27"}

# 批量修复数据库中所有国家报告的国家字段
from pathlib import Path
fix_manifest_countries(Path("/data/iotc/manifest.sqlite"))
```

---

## 7. FastAPI HTTP 服务

爬虫提供了一个异步 HTTP 接口，供 Java 等外部系统调用。所有爬取任务在后台线程中执行，
接口即时返回 `task_id`，调用方轮询任务状态。

### 7.1 启动服务

```bash
# 使用 config.yaml 中的 host/port（默认 0.0.0.0:8000）
negotiation-crawler serve

# 指定端口
negotiation-crawler serve --host 127.0.0.1 --port 9000
```

启动后可通过浏览器访问自动生成的 OpenAPI 文档：

```
http://localhost:8000/docs       ← Swagger UI（可交互）
http://localhost:8000/redoc      ← ReDoc 文档
```

---

### 7.2 接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查，返回 `{"status": "ok"}` |
| `GET` | `/crawlers` | 列出所有可用爬虫模块 |
| `POST` | `/run/{crawler_name}` | 启动爬虫（异步），返回 `task_id` |
| `GET` | `/tasks/{task_id}` | 查询单个任务状态和结果 |
| `GET` | `/tasks` | 列出当前进程内所有任务 |

`crawler_name` 可选值：`iotc`、`fishery_book`、`wto_site`、`wto_docs`、`all`。

---

### 7.3 接口详情

#### `GET /health`

```bash
curl http://localhost:8000/health
```
```json
{"status": "ok"}
```

---

#### `GET /crawlers`

```bash
curl http://localhost:8000/crawlers
```
```json
[
  {"name": "fishery_book", "description": "..."},
  {"name": "iotc",         "description": "IOTC (Indian Ocean Tuna Commission) documents — all 31 document types"},
  {"name": "wto_site",     "description": "..."},
  {"name": "wto_docs",     "description": "..."}
]
```

---

#### `POST /run/{crawler_name}`

**请求体**（JSON）：

```json
{
  "output_dir": "/data/iotc",
  "params": {
    "skip_manifest": false,
    "enrich": true,
    "build_xlsx": true,
    "all_langs": false,
    "limit": null,
    "only": null,
    "pdf_dir": null
  }
}
```

> `output_dir` 和 `params` 均为可选。`params` 的键与 CLI `--set` 参数完全对应（见第 5.4 节）。

**响应**（立即返回，任务在后台运行）：

```json
{
  "task_id": "3f7a1c2e-9b04-4d8e-a5f1-0e2c3b4d5e6f",
  "crawler": "iotc",
  "state": "PENDING"
}
```

---

#### `GET /tasks/{task_id}`

```bash
curl http://localhost:8000/tasks/3f7a1c2e-9b04-4d8e-a5f1-0e2c3b4d5e6f
```

**运行中**：
```json
{
  "task_id": "3f7a1c2e-...",
  "crawler": "iotc",
  "state": "RUNNING",
  "output_dir": null,
  "error": null,
  "log": null
}
```

**完成**：
```json
{
  "task_id": "3f7a1c2e-...",
  "crawler": "iotc",
  "state": "DONE",
  "output_dir": "/data/iotc",
  "error": null,
  "log": null
}
```

**失败**：
```json
{
  "task_id": "3f7a1c2e-...",
  "crawler": "iotc",
  "state": "FAILED",
  "output_dir": "/data/iotc",
  "error": "Connection refused: iotc.org:443",
  "log": null
}
```

`state` 可能取值：`PENDING` → `RUNNING` → `DONE` / `FAILED`。

---

#### `GET /tasks`

列出本次进程启动以来的所有任务（重启后清空）：

```bash
curl http://localhost:8000/tasks
```
```json
[
  {"task_id": "3f7a1c2e-...", "crawler": "iotc",        "state": "DONE"},
  {"task_id": "8a2b4d6f-...", "crawler": "fishery_book", "state": "RUNNING"}
]
```

---

### 7.4 curl 完整示例

```bash
BASE="http://localhost:8000"

# 1. 启动 IOTC 爬取（只建清单，不下载 PDF）
TASK=$(curl -s -X POST "$BASE/run/iotc" \
  -H "Content-Type: application/json" \
  -d '{"output_dir": "/data/iotc", "params": {"list_only": true}}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")

echo "task_id = $TASK"

# 2. 轮询状态，直到完成
while true; do
  STATE=$(curl -s "$BASE/tasks/$TASK" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['state'])")
  echo "state = $STATE"
  [ "$STATE" = "DONE" ] || [ "$STATE" = "FAILED" ] && break
  sleep 10
done

# 3. 查看最终结果
curl -s "$BASE/tasks/$TASK" | python3 -m json.tool
```

---

### 7.5 Python httpx 示例

```python
import time
import httpx

BASE = "http://localhost:8000"

# 启动爬取
resp = httpx.post(f"{BASE}/run/iotc", json={
    "output_dir": "/data/iotc",
    "params": {
        "skip_manifest": False,
        "enrich": True,
        "build_xlsx": True,
        "only": "Meeting Report",   # 只处理会议报告
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
    time.sleep(15)

if state == "DONE":
    print(f"Success → {task['output_dir']}")
else:
    print(f"Failed: {task['error']}")
```

---

### 7.6 运行所有爬虫（`all`）

`all` 会依次运行全部四个爬虫，完成后执行跨爬虫 SHA-256 去重。

```bash
curl -X POST http://localhost:8000/run/all \
  -H "Content-Type: application/json" \
  -d '{"output_dir": "/data/corpus"}'
```

每个爬虫的输出写入 `/data/corpus/<crawler_name>/`，去重日志写入 `log` 字段。

---

### 7.7 注意事项

- **任务生命周期**：任务存储在进程内存中，重启服务后历史任务丢失。如需持久化，
  请在业务层记录 `task_id` 与完成状态。
- **并发**：同一进程可同时接受多个 `POST /run` 请求，每个任务在独立的后台线程中运行。
  大量并发任务共用同一 HTTP 客户端池，请注意 IOTC 网站的速率限制。
- **超时**：FastAPI 接口本身不设超时；完整爬取可能需要数小时，调用方轮询间隔建议 ≥ 10 秒。

---

## 8. Excel 台账结构（index.xlsx）

### Sheet 结构

| Sheet | 内容 |
|-------|------|
| `All - 全部` | 所有英文记录（按 category_group → doc_type → year → reference 排序） |
| `Meeting Report - 会议报告` | 仅该类型的记录 |
| `National Reports - 国家报告` | 仅该类型的记录 |
| … | 每种文件类型一个 sheet（共最多 31 个） |
| `Statistics - 汇总统计` | 按类别组统计数量 + 总计 + 去重数 |

### 数据列

| 列名 | 含义 |
|------|------|
| 类别 | 文件类型中文名 |
| 文档类型组 | 类别组（如 会议文件类） |
| 年份 | 文件年份 |
| 文件名 | PDF 文件名（从 URL 末段提取） |
| 标题 | 文件标题 |
| Reference | IOTC 文件编号 |
| 会议 | 会议名称 |
| 届次 | 届次编号 |
| 下载链接 | PDF 直链（可点击超链接） |
| 页数 | PDF 页数（需 `pypdf`） |
| 大小(KB) | 文件大小 |
| 格式 | 文件格式（通常为 PDF） |
| 国家 | 提交国（National Reports 专用） |
| 发布日期 | 流通日期 |
| 作者 | 作者字段 |
| 状态 | `pending` / `downloaded` / `failed` |

---

## 9. 典型使用场景

### 场景 A：首次完整运行

```bash
negotiation-crawler run iotc --out /data/iotc_corpus
```

预计耗时：约 2-4 小时（受网络和限速影响）。

### 场景 B：增量更新（网站有新文件）

```bash
# 重新扫描列表页，新记录写入 manifest；已有记录不受影响
negotiation-crawler run iotc --out /data/iotc_corpus

# 等价于显式执行 Phase 1+2+3+4
negotiation-crawler run iotc --out /data/iotc_corpus \
  --set skip_manifest=false \
  --set enrich=true \
  --set build_xlsx=true
```

### 场景 C：断点续传（中途被打断）

```bash
# 跳过 Phase 1（清单不变），直接继续 Phase 2-3-4
# Phase 2 和 3 各自只处理尚未处理的行
negotiation-crawler run iotc --out /data/iotc_corpus --set skip_manifest=true
```

### 场景 D：仅重建 Excel 报告

```bash
negotiation-crawler xlsx iotc --out /data/iotc_corpus
```

### 场景 E：测试运行（快速验证流程）

```bash
# 每个阶段各跑 5 条记录
negotiation-crawler run iotc --out /data/test_iotc --set limit=5
```

### 场景 F：仅下载合规报告类

```bash
negotiation-crawler run iotc \
  --out /data/iotc_corpus \
  --set skip_manifest=false \
  --set only="Compliance Reports"
```

---

## 10. 配置文件

`config.yaml`（项目根目录）控制默认输出路径：

```yaml
defaults:
  iotc: "./output/iotc"   # 默认输出目录；--out 参数可覆盖

api:
  host: "0.0.0.0"
  port: 8000
```

网络常量在 `negotiation_crawler/crawlers/iotc/config.py` 中调整：

```python
BASE_URL       = "https://iotc.org"
REQUEST_DELAY  = 1.5   # 每次请求间隔（秒）；请勿过低，避免被封
TIMEOUT        = 30.0  # 请求超时（秒）
HEADERS        = {"User-Agent": "..."}
```

---

## 11. 依赖

| 包 | 用途 | 是否必须 |
|----|------|----------|
| `httpx` | HTTP 请求 | 是 |
| `selectolax` | HTML 解析（列表页） | 是 |
| `openpyxl` | Excel 导出 | 是 |
| `fastapi` + `uvicorn` | HTTP 服务（`serve` 命令） | 是 |
| `pypdf` | PDF 页数读取 | 可选（不安装时 `page_count` 为 0） |

安装含可选依赖：

```bash
pip install -e ".[pdf]"
```

---

## 12. 常见问题

**Q：运行到一半崩溃了怎么办？**  
A：用 `--set skip_manifest=true` 跳过 Phase 1，直接从 Phase 2 继续。Phase 2 只处理
`meta_type IS NULL` 的行，Phase 3 只处理 `status='pending'` 的行，均支持幂等重跑。

**Q：同一个 PDF 被多个列表页引用，会重复下载吗？**  
A：不会。`pdf_url` 是数据库主键，Phase 1 的 `upsert_row` 函数在重复时直接跳过。
Phase 3 还额外通过 SHA-256 比对，同内容文件复用已有的本地路径。

**Q：`page_count` 全是 0？**  
A：安装 `pypdf`：`pip install pypdf` 或 `pip install -e ".[pdf]"`，然后重新运行
Phase 3（`skip_manifest=true`，`enrich=false`，`build_xlsx=false`）。

**Q：某些法语文件混入了英文结果怎么办？**  
A：过滤逻辑在 `fetch/crawler.py` 的 `_is_french()` 函数。它检查文件名是否以 `F.pdf`
结尾，以及 reference 中是否含 `CTOI` 或 `CIRCULAIRE`。如有遗漏可在该函数中补充规则。

**Q：如何只重新生成 Excel 而不动数据库？**  
A：`negotiation-crawler xlsx iotc --out /data/iotc_corpus`（或用 `--db`/`--xlsx`
精确指定路径）。这只读取数据库，不写入任何新行。

**Q：FastAPI 服务重启后任务记录丢失了？**  
A：任务状态存储在进程内存中，重启即清空。建议在调用方（如 Java 服务）持久化
`task_id` 及对应的完成时间和 `output_dir`，以便重启后仍能定位产出文件。

**Q：如何将结果合并到统一数据库？**  
A：
```bash
negotiation-crawler export --base /data/output --module iotc --db /data/unified.sqlite
```
