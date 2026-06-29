# negotiation_crawler — 渔业补贴谈判语料库爬虫

统一爬虫平台，整合4个数据源的爬取、下载、分类与 Excel 导出，支持命令行、HTTP API、Java 调用三种使用方式。

---

## 目录

1. [项目概览](#1-项目概览)
2. [快速上手（5 分钟）](#2-快速上手5-分钟)
3. [项目结构](#3-项目结构)
4. [模块详解](#4-模块详解)
   - 4.1 [wto\_site — WTO 渔业网站页面](#41-wto_site--wto-渔业网站页面)
   - 4.2 [wto\_docs — WTO 文档库 PDF](#42-wto_docs--wto-文档库-pdf)
   - 4.3 [fishery\_book — FAO 渔业出版物](#43-fishery_book--fao-渔业出版物)
   - 4.4 [iotc — IOTC 金枪鱼委员会文件](#44-iotc--iotc-金枪鱼委员会文件)
5. [整体运行与输出](#5-整体运行与输出)
6. [CLI 使用手册](#6-cli-使用手册)
7. [HTTP API 使用手册](#7-http-api-使用手册)
8. [Java 调用示例](#8-java-调用示例)
9. [配置文件 config.yaml](#9-配置文件-configyaml)
10. [常见问题](#10-常见问题)

---

## 1 项目概览

| 数据源                  | 内容                                            | 规模（估计） | 获取方式                     |
| ----------------------- | ----------------------------------------------- | ------------ | ---------------------------- |
| **wto\_site**     | WTO 渔业补贴专题页面，含 HTML 转 Markdown、PDF  | ~60 页面     | 有界广度优先爬取（纯 HTTP）  |
| **wto\_docs**     | docs.wto.org 8 个文档系列 PDF（G/FS、TN/RL 等） | 数百~数千份  | 平铺 HTTP 枚举（无需浏览器） |
| **fishery\_book** | FAO 知识仓库渔业出版物 PDF                      | 数百册       | DSpace 7 REST API            |
| **iotc**          | IOTC 金枪鱼委员会全部文档类型 PDF               | 数千份       | Drupal Facet API             |

每个模块输出同样的四类产物：

1. **原始文件**（PDF / Markdown）
2. **清单数据库**（JSONL 或 SQLite）
3. **统一索引**（`index.xlsx` + `index.csv` / `index.sqlite`）
4. **分类报告**（按主题/系列分 Sheet 的 Excel）

---

## 2 快速上手（5 分钟）

### 2.1 环境要求

- Python ≥ 3.11
- [uv](https://github.com/astral-sh/uv)（推荐）或 pip
- 磁盘空间：建议 ≥ 50 GB（wto\_docs 全量 PDF 约 20 GB）

### 2.2 安装

```bash
# 克隆项目
git clone <仓库地址>
cd negotiation_crawler

# 安装基础依赖
uv sync

# 安装 PDF 解析（可选，wto_site HTML→Markdown 需要）
uv sync --extra pdf

# 安装所有扩展（含 Playwright）
uv sync --extra all
```

### 2.3 修改输出目录

编辑项目根目录下的 `config.yaml`：

```yaml
defaults:
  fishery_book: "/data/output/fishery_books"
  iotc:         "/data/output/iotc"
  wto_site:     "/data/output/wto_site"
  wto_docs:     "/data/output/wto_docs"
```

### 2.4 运行第一个爬虫

```bash
# 列出所有可用模块
python -m negotiation_crawler list

# 运行 wto_docs（推荐首选——无需浏览器，速度稳定）
python -m negotiation_crawler run wto_docs --out ~/my_output/wto_docs

# 运行完成后查看输出
ls ~/my_output/wto_docs/
# index.xlsx  index.csv  index.sqlite  docs_manifest/  library/
```

### 2.5 一键运行全部模块

```bash
python -m negotiation_crawler run all --out ~/my_output
# 运行顺序: fishery_book → iotc → wto_site → wto_docs → 跨模块去重
# 每个模块结果在 ~/my_output/{模块名}/
```

---

## 3 项目结构

```
negotiation_crawler/
├── config.yaml                        # 输出路径 & API 端口配置
├── pyproject.toml                     # 依赖声明
└── negotiation_crawler/
    ├── __main__.py                    # python -m 入口
    ├── cli.py                         # 命令行解析
    ├── api.py                         # FastAPI HTTP 服务
    ├── config.py                      # 配置加载
    ├── dedup.py                       # 全局 SHA-256 去重
    ├── base.py                        # BaseCrawler / CrawlResult 抽象
    └── crawlers/
        ├── wto_site/
        │   ├── classifier/            # URL + 标题分类规则
        │   ├── fetch/                 # 异步 HTTP + URL 过滤规则
        │   ├── process/               # 爬取 pipeline + xlsx 生成
        │   └── storage/               # PageRecord 模型 + 去重
        ├── wto_docs/
        │   ├── classifier/            # 系列标签
        │   ├── fetch/                 # enumerate.py / detail.py / download.py
        │   ├── process/               # build_index → xlsx / csv / sqlite
        │   └── storage/
        ├── fishery_book/
        │   ├── classifier/            # 关键词模糊匹配
        │   ├── fetch/                 # DSpace REST API 客户端
        │   ├── process/               # audit_xlsx.py
        │   └── storage/               # SQLite + 文件存储
        └── iotc/
            ├── classifier/            # 文档类型分类
            ├── fetch/                 # Drupal Facet 枚举 + 下载
            ├── process/               # xlsx_builder.py
            └── storage/               # SQLite
```

---

## 4 模块详解

每个模块均由四层组成：

| 层                   | 目录            | 职责                            |
| -------------------- | --------------- | ------------------------------- |
| **classifier** | `classifier/` | 判断文档所属类别/系列           |
| **fetch**      | `fetch/`      | HTTP 请求、页面解析、文件下载   |
| **process**    | `process/`    | 数据清洗、格式转换、生成 xlsx   |
| **storage**    | `storage/`    | 持久化（SQLite / JSONL / 文件） |

---

### 4.1 wto\_site — WTO 渔业网站页面

**数据来源：** `www.wto.org` 渔业补贴专题页面
**爬取方式：** 异步 HTTP，广度优先；HTML → Trafilatura → Markdown；PDF 保留原文件
**分类依据：** URL 规则 + 标题关键词 → 16 个类别

#### 爬取流程

```
种子 URL (www.wto.org/english/tratop_e/fish_e/fish_e.htm)
  → 广度优先爬取（max_depth 层，同域内链接）
      ├── HTML → 提取正文 → .md 文件（含 YAML front matter）
      ├── PDF  → 直接保存到 raw/pdf/
      └── 视频/大文件 → 仅记录 URL，不下载（受限标注）
  → 内容哈希去重
  → 写入 manifest.jsonl
  → 生成 index.xlsx
```

#### 输出目录结构

```
{output_dir}/
├── raw/
│   ├── html/               # 原始 HTML，以 SHA256 哈希命名
│   └── pdf/                # 原始 PDF，以 SHA256 哈希命名
├── markdown/               # 转换后的 Markdown 文件
│   └── {hash[:16]}.md      # 含 YAML front matter（url/title/category/date）
├── manifest.jsonl          # 每条爬取记录一行 JSON
├── external_links.jsonl    # 外部（未爬取）链接
├── dedup_report.csv        # 内容级重复文件报告
└── index.xlsx              # 汇总 Excel
```

#### index.xlsx 说明

| Sheet                                 | 内容                                 |
| ------------------------------------- | ------------------------------------ |
| **全部**                        | 所有已爬取页面（跳过重复项和失败项） |
| **概览 / 导论 / 法律文本 / …** | 按类别分 Sheet（最多 16 个）         |

**列说明（全部 Sheet）：**

| 列       | 说明                                        |
| -------- | ------------------------------------------- |
| 序号     | 行号                                        |
| 类别     | 中文类别名                                  |
| 标题     | 页面标题或文件名                            |
| 类型     | HTML / PDF / 视频                           |
| 状态     | 已转Markdown / 已下载PDF / 受限（需浏览器） |
| 本地路径 | 相对于 output\_dir 的路径                   |
| 来源URL  | 原始页面地址                                |

**页面类别对照：**

| 类别代码                  | 中文标签         | 典型内容                |
| ------------------------- | ---------------- | ----------------------- |
| overview                  | 概览             | 专题门户首页            |
| legal\_text               | 法律文本         | 协定正式条文            |
| ratification              | 接受与批准       | 成员批准状态            |
| implementation            | 履约             | 成员履约报告            |
| publication               | 出版物           | 宣传册、情况说明        |
| negotiation\_submission   | 谈判             | TN/RL 系列文件          |
| committee                 | 委员会           | G/FS 系列、委员会文件   |
| mandate\_decision         | 部长决定与议定书 | WT/MIN、WT/L 系列       |
| fish\_fund                | 渔业基金         | WTO 技援基金页面        |
| international\_instrument | 国际文书         | UNCLOS、CCRF 等         |
| multimedia                | 音视频           | .mp4 视频（仅记录 URL） |
| news                      | 新闻             | /news\_e/ 路径下的新闻  |
| ministerial               | 部长会简报       | /minist\_e/ 路径        |
| case\_story               | 案例故事         | 成员案例页面            |
| uncategorized             | 未分类           | 未匹配任何规则          |

#### 常用 --set 参数

| 参数             | 类型  | 默认值  | 说明                     |
| ---------------- | ----- | ------- | ------------------------ |
| `max_depth`    | int   | 4       | 最大爬取深度             |
| `concurrency`  | int   | 4       | 并发请求数               |
| `delay`        | float | 1.0     | 请求间隔（秒）           |
| `resume`       | bool  | false   | 从已爬取记录续跑         |
| `include_docs` | bool  | false   | 是否下载外链 Office 文档 |
| `max_pages`    | int   | 无限制  | 最多爬取页面数           |
| `pdf_backend`  | str   | pymupdf | PDF 转 Markdown 引擎     |

#### 运行示例

```bash
# 基本运行
python -m negotiation_crawler run wto_site --out ~/out/wto_site

# 断点续跑，限速
python -m negotiation_crawler run wto_site --out ~/out/wto_site \
  --set resume=true --set delay=2.0

# 仅爬 2 层，快速测试
python -m negotiation_crawler run wto_site --out ~/out/wto_site \
  --set max_depth=2 --set max_pages=20
```

---

### 4.2 wto\_docs — WTO 文档库 PDF

**数据来源：** `docs.wto.org` 8 个渔业相关文档系列
**爬取方式：** 纯 HTTP，通过 `FE_S_S006.aspx` ASP.NET 分页枚举（无需浏览器）
**分类依据：** 文档系列（G/FS、TN/RL 等），自动打标

#### 8 个文档系列

| 标签  | 系列名称               | 内容说明                               |
| ----- | ---------------------- | -------------------------------------- |
| GFS   | G/FS — 渔业补贴委员会 | 委员会通报、履约文件（2022年起）       |
| TN    | TN/RL — 谈判          | 规则谈判组提案（2001年至今，数量最大） |
| WTMIN | WT/MIN — 部长会       | 部长会决定与宣言                       |
| WTL   | WT/L — 法律文本       | 协定、议定书正式文本                   |
| WTLET | WT/LET — 接受书       | 成员接受文书                           |
| GSCM  | G/SCM — 补贴通报      | 补贴委员会通报                         |
| WTGC  | WT/GC — 总理事会      | 总理事会文件                           |
| JOBRL | JOB/RL — 室文件       | 内部谈判工作文件                       |

#### 爬取流程（三阶段）

```
Phase 0（默认跳过）：Playwright 浏览器关键词搜索（需安装 playwright extra）
Phase 1（核心）：FE_S_S006.aspx HTTP 分页枚举
  → docs_manifest/detail_{LABEL}.jsonl（每系列一个 JSONL）
Phase 2：directdoc 端点下载 PDF
  → library/{系列文件夹}/{文档号}.pdf
Phase 3：合并清单
  → index.xlsx + index.csv + index.sqlite
```

#### 输出目录结构

```
{output_dir}/
├── index.xlsx              # 全部文档汇总（多系列 Sheet）
├── index.csv               # 同上，CSV 格式（utf-8-sig，Excel 可直接打开）
├── index.sqlite            # SQLite 数据库（表名: documents）
├── docs_manifest/
│   ├── detail_GFS.jsonl    # G/FS 系列枚举清单（含访问权限、日期、大小）
│   ├── detail_TN.jsonl
│   ├── detail_WTMIN.jsonl
│   ├── detail_WTL.jsonl
│   ├── detail_WTLET.jsonl
│   ├── detail_GSCM.jsonl
│   ├── detail_WTGC.jsonl
│   └── detail_JOBRL.jsonl
└── library/
    ├── 01_G-FS_渔业补贴委员会/    # G/FS 系列 PDF
    │   └── G_FS_1.pdf
    ├── 02_TN_谈判/
    │   └── TN_RL_31.pdf
    ├── 03_WT-MIN_部长会/
    ├── 04_WT-L_法律文本/
    ├── 05_WT-LET_接受书/
    ├── 06_G-SCM_补贴通报/
    ├── 07_WT-GC_总理事会/
    └── 09_JOB-RL_室文件/
```

#### index.xlsx 说明

| Sheet                            | 内容                           |
| -------------------------------- | ------------------------------ |
| **全部**                   | 8 个系列合并，按系列→日期排序 |
| **G-FS — 渔业补贴委员会** | 仅 G/FS 系列                   |
| **TN-RL — 谈判**          | 仅 TN/RL 系列                  |
| **WT-MIN — 部长会**       | 仅 WT/MIN 系列                 |
| **（其余系列各一 Sheet）** | …                             |

**列说明：**

| 列       | 说明                      | 备注               |
| -------- | ------------------------- | ------------------ |
| 序号     | 行号                      |                    |
| 系列     | 中文系列名                |                    |
| 文档号   | WTO 文档编号（如 G/FS/1） |                    |
| 标题     | 文档标题                  |                    |
| 年份     | 发布年份（整数）          | 从日期提取         |
| 日期     | 发布日期（YYYY-MM-DD）    |                    |
| 大小(KB) | 文件大小                  |                    |
| 页数     | PDF 页数                  |                    |
| 访问权限 | 公开 / 受限               | 受限文件不可下载   |
| 已下载   | 是 / 否                   |                    |
| 下载链接 | directdoc 直链 URL        | 公开文件可直接点开 |
| 本地路径 | 已下载 PDF 的本地路径     | 未下载则为空       |

**SQLite 数据库（index.sqlite）：**

```sql
-- 表名: documents
-- 查询所有已下载的 G/FS 系列文件
SELECT symbol, title, year, size_kb, local_path
FROM documents
WHERE body = 'GFS' AND downloadable = 1
ORDER BY year DESC;

-- 统计各系列文件数
SELECT body, COUNT(*) as total,
       SUM(downloadable) as downloaded
FROM documents
GROUP BY body;
```

#### 常用 --set 参数

| 参数               | 类型  | 默认值 | 说明                                  |
| ------------------ | ----- | ------ | ------------------------------------- |
| `skip_detail`    | bool  | false  | 跳过 Phase 1（复用已有 JSONL）        |
| `skip_download`  | bool  | false  | 跳过 Phase 2 下载                     |
| `only_series`    | str   | 全部   | 只运行指定系列，如`GFS`、`TN`     |
| `delay`          | float | 0.8    | 请求间隔（秒）                        |
| `resume`         | bool  | true   | 已有 JSONL 则跳过重新枚举             |
| `fisheries_only` | bool  | false  | 仅下载标题含渔业关键词的文件          |
| `skip_harvest`   | bool  | true   | 跳过 Playwright 阶段（推荐保持 true） |

#### 运行示例

```bash
# 只爬 G/FS 系列（最快，约 10 分钟）
python -m negotiation_crawler run wto_docs --out ~/out/wto_docs \
  --set only_series=GFS

# 全量爬取（耗时 2–4 小时）
python -m negotiation_crawler run wto_docs --out ~/out/wto_docs

# 已枚举完毕，只补充下载
python -m negotiation_crawler run wto_docs --out ~/out/wto_docs \
  --set skip_detail=true

# 仅重新生成 xlsx（不重新爬取）
python -m negotiation_crawler run wto_docs --out ~/out/wto_docs \
  --set skip_detail=true --set skip_download=true
```

---

### 4.3 fishery\_book — FAO 渔业出版物

**数据来源：** FAO 知识仓库（`www.fao.org/library`，DSpace 7）
**爬取方式：** DSpace 7 REST API，按 Collection 分批拉取
**分类依据：** 标题关键词模糊匹配（rapidfuzz）

#### 爬取流程

```
seeds.json（Collection URL 列表）
  → DSpace REST API 拉取 Item 元数据 + Bitstream 列表
  → 关键词模糊匹配筛选渔业相关出版物
  → 下载最高质量 Bitstream（PDF 优先）→ pdfs/
  → 写入 manifest.sqlite
  → 生成 index.xlsx
```

#### 输出目录结构

```
{output_dir}/
├── pdfs/
│   └── {类别}_{年份}_{文件名}.pdf    # 示例: fisheries_2023_report.pdf
├── manifest.sqlite                   # SQLite 清单（表名: manifest）
└── index.xlsx                        # 审计 Excel（见下）
```

#### index.xlsx 说明

| Sheet             | 内容                     |
| ----------------- | ------------------------ |
| **Audit**   | 所有记录，按状态颜色标注 |
| **Summary** | 按状态统计数量           |

**Audit Sheet 列说明：**

| 列             | 说明                   |
| -------------- | ---------------------- |
| 类别           | 出版物分类             |
| 年份           | 出版年份               |
| 文件名         | 下载后的本地文件名     |
| 标题           | 出版物标题             |
| 下载链接       | FAO 仓库直链（可点击） |
| 页数           | PDF 页数               |
| 大小(KB)       | 文件大小               |
| 格式           | PDF / DOCX 等          |
| **状态** | 见下表                 |
| 匹配分         | 关键词匹配分（0–100） |
| Handle         | FAO 永久标识符         |
| 来源           | api / legacy           |
| 种子ID         | 对应 seeds.json 条目   |
| 备注           | 异常信息               |

**状态颜色说明：**

| 颜色 | 状态      | 含义                     |
| ---- | --------- | ------------------------ |
| 绿色 | FOUND     | 正常下载                 |
| 蓝色 | LEGACY    | 旧 API 兼容获取          |
| 黄色 | AMBIGUOUS | 匹配有歧义，建议人工确认 |
| 橙色 | NO\_PDF   | 无 PDF，仅有元数据       |
| 红色 | MISSING   | 未找到匹配项             |
| 深红 | ERROR     | 下载失败                 |

#### 常用 --set 参数

| 参数            | 类型 | 默认值 | 说明                               |
| --------------- | ---- | ------ | ---------------------------------- |
| `no_download` | bool | false  | 只枚举，不下载 PDF                 |
| `no_resume`   | bool | false  | 强制重新爬取（忽略已有记录）       |
| `category`    | str  | 全部   | 按类别过滤                         |
| `limit`       | int  | 无限制 | 限制处理数量（测试用）             |
| `concurrency` | int  | 4      | 并发下载数                         |
| `proxy`       | str  | 无     | HTTP 代理，如`http://proxy:8080` |

#### 运行示例

```bash
# 完整运行
python -m negotiation_crawler run fishery_book --out ~/out/fishery_books

# 仅枚举，不下载
python -m negotiation_crawler run fishery_book --out ~/out/fishery_books \
  --set no_download=true

# 限制 50 本，快速测试
python -m negotiation_crawler run fishery_book --out ~/out/fishery_books \
  --set limit=50
```

---

### 4.4 iotc — IOTC 金枪鱼委员会文件

**数据来源：** IOTC 官网（`www.iotc.org`），Drupal Facet API
**爬取方式：** 先枚举全部 31 种文档类型的元数据，再下载英文 PDF
**分类依据：** 31 种文档类型 → 若干类别组（category\_group）

#### 爬取流程（四阶段）

```
Phase 1: build_manifest  — Drupal Facet 枚举所有文档 → manifest.sqlite
Phase 2: enrich_metadata — 逐条获取页数、大小、下载链接等详情
Phase 3: download_pdfs   — 下载英文 PDF → pdfs/
Phase 4: build_xlsx      — 从 SQLite 生成 index.xlsx
```

#### 输出目录结构

```
{output_dir}/
├── pdfs/
│   └── *.pdf               # 以 IOTC 文件编号命名
├── manifest.sqlite         # SQLite 清单（表名: docs）
└── index.xlsx              # 分类汇总 Excel（见下）
```

#### index.xlsx 说明

| Sheet                              | 内容                        |
| ---------------------------------- | --------------------------- |
| **全部**                     | 所有英文文档                |
| **会议报告类**               | Session Reports 等          |
| **合规报告类**               | Compliance Reports 等       |
| **（其余类别组各一 Sheet）** | 按 category\_group 自动划分 |

**列说明：**

| 列         | 说明                          |
| ---------- | ----------------------------- |
| 类别       | 中文文档类型名                |
| 文档类型组 | 所属类别组                    |
| 年份       | 文档年份                      |
| 文件名     | PDF 文件名                    |
| 标题       | 文档标题                      |
| Reference  | IOTC 文档编号                 |
| 会议       | 所属会议名称                  |
| 届次       | 会议届次                      |
| 下载链接   | 直链 URL（可点击）            |
| 页数       | PDF 页数                      |
| 大小(KB)   | 文件大小                      |
| 格式       | PDF / DOCX 等                 |
| 国家       | 提交国家（如有）              |
| 发布日期   | circulated 日期               |
| 作者       | 作者信息                      |
| 状态       | downloaded / pending / failed |

#### 常用 --set 参数

| 参数              | 类型 | 默认值 | 说明                            |
| ----------------- | ---- | ------ | ------------------------------- |
| `skip_manifest` | bool | false  | 跳过 Phase 1（复用已有 SQLite） |
| `enrich`        | bool | true   | 是否执行 Phase 2 详情获取       |
| `list_only`     | bool | false  | 仅列举，不下载                  |
| `build_xlsx`    | bool | true   | 是否生成 xlsx                   |
| `all_langs`     | bool | false  | 下载所有语言（默认仅英文）      |
| `limit`         | int  | 无限制 | 限制处理文档数                  |
| `only`          | str  | 全部   | 按文档类型代码过滤，如`SC`    |

#### 运行示例

```bash
# 完整运行
python -m negotiation_crawler run iotc --out ~/out/iotc

# 仅重新生成 xlsx（已有 SQLite 时，最快）
python -m negotiation_crawler run iotc --out ~/out/iotc \
  --set skip_manifest=true --set enrich=false

# 仅枚举，不下载
python -m negotiation_crawler run iotc --out ~/out/iotc \
  --set list_only=true
```

---

## 5 整体运行与输出

### 5.1 运行全部模块

```bash
python -m negotiation_crawler run all --out ~/output
```

运行顺序：`fishery_book` → `iotc` → `wto_site` → `wto_docs` → **全局去重**

某个模块失败不影响其他模块继续运行，失败信息汇总在最后。

### 5.2 整体输出目录结构

```
~/output/
├── fishery_book/
│   ├── index.xlsx          # Audit + Summary Sheet
│   ├── manifest.sqlite
│   └── pdfs/
│       └── fisheries_2023_*.pdf
├── iotc/
│   ├── index.xlsx          # 全部 + 按类型组 Sheet
│   ├── manifest.sqlite
│   └── pdfs/
│       └── *.pdf
├── wto_site/
│   ├── index.xlsx          # 全部 + 按类别 Sheet
│   ├── manifest.jsonl
│   ├── external_links.jsonl
│   ├── dedup_report.csv
│   ├── markdown/
│   │   └── *.md
│   └── raw/
│       ├── html/
│       └── pdf/
├── wto_docs/
│   ├── index.xlsx          # 全部 + 按系列 Sheet
│   ├── index.csv
│   ├── index.sqlite
│   ├── docs_manifest/
│   │   └── detail_*.jsonl
│   └── library/
│       ├── 01_G-FS_渔业补贴委员会/
│       └── …
└── dedup_report.json       # 跨模块去重报告
```

### 5.3 各模块交付物汇总

| 模块          | Excel 文件                                        | Sheet 结构      | PDF 位置                   | 中间数据库                |
| ------------- | ------------------------------------------------- | --------------- | -------------------------- | ------------------------- |
| wto\_site     | `index.xlsx`                                    | 全部 + 16个类别 | `raw/pdf/`（SHA256命名） | `manifest.jsonl`        |
| wto\_docs     | `index.xlsx` + `index.csv` + `index.sqlite` | 全部 + 8个系列  | `library/{系列}/`        | `docs_manifest/*.jsonl` |
| fishery\_book | `index.xlsx`                                    | Audit + Summary | `pdfs/`                  | `manifest.sqlite`       |
| iotc          | `index.xlsx`                                    | 全部 + 按类型组 | `pdfs/`                  | `manifest.sqlite`       |

### 5.4 全局去重

运行 `all` 后自动扫描所有下载文件，按 SHA-256 内容哈希去重：

- 保留字母顺序最靠前的路径为"正本"
- 删除其余副本
- 报告写入 `~/output/dedup_report.json`

```bash
# 单独运行去重（不重新爬取）
python -m negotiation_crawler dedup ~/output

# 预览要删除的文件（不实际删除）
python -m negotiation_crawler dedup ~/output --dry-run
```

---

## 6 CLI 使用手册

### 6.1 命令总览

```
python -m negotiation_crawler <命令> [选项]

命令：
  list           列出所有可用模块
  run            运行爬虫（单个或全部）
  dedup          对已下载目录执行 SHA-256 去重
  serve          启动 FastAPI HTTP 服务器（供 Java 等外部调用）
```

### 6.2 list

```bash
python -m negotiation_crawler list

# 输出示例：
# Name             Description
# ------------------------------------------------------------
# fishery_book     FAO fishery publications from the Knowledge Repository (DSpace)
# iotc             IOTC (Indian Ocean Tuna Commission) documents — all 31 document types
# wto_site         WTO fisheries subsidies agreement main site and subpages → Markdown corpus
# wto_docs         WTO Documents Online — 8 fisheries series, plain-HTTP enumeration + directdoc download
```

### 6.3 run

```bash
python -m negotiation_crawler run <模块名|all> [选项]

选项：
  --out <目录>          输出目录（覆盖 config.yaml 默认值）
  --set KEY=VALUE       传递爬虫参数（可重复多次）
  --dry-run             仅与 all 一起使用：报告去重但不删除文件
  -v / --verbose        输出详细运行日志
```

**--set 值类型自动推断：**

| 写法                          | 推断为 |
| ----------------------------- | ------ |
| `key=true` 或 `key=false` | bool   |
| `key=42`                    | int    |
| `key=1.5`                   | float  |
| `key=GFS` 等字符串          | str    |

**示例：**

```bash
# 单模块，指定输出目录
python -m negotiation_crawler run wto_docs --out /data/wto

# 带参数
python -m negotiation_crawler run iotc --out /data/iotc \
  --set limit=200 --set enrich=true

# 全部模块，预览去重
python -m negotiation_crawler run all --out /data/output --dry-run

# 详细日志
python -m negotiation_crawler run fishery_book -v
```

### 6.4 dedup

```bash
python -m negotiation_crawler dedup <目录> [--dry-run]
```

扫描指定目录下所有 `.pdf / .doc / .docx / .xlsx / .xls / .ppt / .pptx` 文件，按 SHA-256 去重。

```bash
# 实际删除
python -m negotiation_crawler dedup ~/output

# 仅报告，不删除
python -m negotiation_crawler dedup ~/output/wto_docs --dry-run
```

输出示例：

```
total=1240 unique=1198 removed=42 saved=148.8MB
```

报告保存为 `<目录>/dedup_report.json`。

### 6.5 serve

```bash
python -m negotiation_crawler serve [--host 127.0.0.1] [--port 8080]

# 不带参数时使用 config.yaml 中的 api.host 和 api.port
python -m negotiation_crawler serve

# 启动后访问 Swagger 文档
# http://localhost:8000/docs
```

---

## 7 HTTP API 使用手册

启动 API 服务后，所有爬虫任务在后台线程异步运行，调用方立即拿到 `task_id` 后轮询状态。

### 7.1 接口列表

| 方法 | 路径                    | 说明                              |
| ---- | ----------------------- | --------------------------------- |
| GET  | `/health`             | 健康检查，返回`{"status":"ok"}` |
| GET  | `/crawlers`           | 列出所有模块名称和描述            |
| POST | `/run/{crawler_name}` | 异步启动爬虫任务                  |
| GET  | `/tasks/{task_id}`    | 查询任务状态与日志                |
| GET  | `/tasks`              | 列出所有任务（当前进程内）        |

交互式文档：`http://localhost:8000/docs`

### 7.2 POST /run/ — 启动任务

`crawler_name` 可以是 `fishery_book / iotc / wto_site / wto_docs / all`。

**请求体：**

```json
{
  "output_dir": "/data/output/wto_docs",
  "params": {
    "only_series": "GFS",
    "delay": 1.0,
    "resume": true
  }
}
```

`output_dir` 省略时使用 config.yaml 默认值；`params` 对应各模块的 `--set` 参数。

**响应（立即返回）：**

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "crawler": "wto_docs",
  "state": "pending"
}
```

### 7.3 GET /tasks/ — 查询状态

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "crawler": "wto_docs",
  "state": "done",
  "output_dir": "/data/output/wto_docs",
  "error": null,
  "log": "[GFS] 287 docs (287 downloadable)\n[TN] 1423 docs ...\n..."
}
```

**state 生命周期：** `pending` → `running` → `done` | `failed`

### 7.4 启动全部模块

```json
POST /run/all
{
  "output_dir": "/data/output",
  "params": {}
}
```

完成后自动执行跨模块去重，`log` 字段包含每个模块的运行结果和去重统计。

---

## 8 Java 调用示例

### 8.1 方式一：ProcessBuilder 调用 CLI

适合简单场景，直接运行 Python 命令。

```java
import java.io.*;
import java.nio.file.*;
import java.util.*;

public class CrawlerRunner {

    private final String projectDir;
    private final String python;

    public CrawlerRunner(String projectDir, String python) {
        this.projectDir = projectDir;
        this.python = python;   // e.g. "/home/user/.venv/bin/python"
    }

    /** 运行单个爬虫，阻塞直到完成 */
    public boolean run(String module, String outputDir,
                       String... setArgs) throws IOException, InterruptedException {
        List<String> cmd = new ArrayList<>(Arrays.asList(
            python, "-m", "negotiation_crawler", "run", module,
            "--out", outputDir
        ));
        for (String kv : setArgs) {
            cmd.add("--set");
            cmd.add(kv);
        }

        ProcessBuilder pb = new ProcessBuilder(cmd);
        pb.directory(new File(projectDir));
        pb.redirectErrorStream(true);   // stderr 合并到 stdout
        Process proc = pb.start();

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(proc.getInputStream()))) {
            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println("[crawler] " + line);
            }
        }

        return proc.waitFor() == 0;
    }

    public static void main(String[] args) throws Exception {
        CrawlerRunner runner = new CrawlerRunner(
            "/path/to/negotiation_crawler",
            "/path/to/.venv/bin/python"
        );

        // 只爬 G/FS 系列
        boolean ok = runner.run("wto_docs", "/data/output/wto_docs",
            "only_series=GFS", "delay=1.0");
        System.out.println("wto_docs: " + (ok ? "成功" : "失败"));

        // 全部模块
        runner.run("all", "/data/output");
    }
}
```

### 8.2 方式二：HTTP API 调用（推荐用于生产）

**步骤：**

1. 服务器上运行 `python -m negotiation_crawler serve --port 8000`
2. Java 侧发 HTTP 请求，提交任务 → 轮询状态 → 读取结果

```java
import java.net.URI;
import java.net.http.*;
import java.time.Duration;

public class CrawlerApiClient {

    private final HttpClient http = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(10))
        .build();
    private final String base;

    public CrawlerApiClient(String baseUrl) {
        this.base = baseUrl;    // e.g. "http://localhost:8000"
    }

    /** 提交任务，立即返回 task_id */
    public String submit(String crawlerName, String outputDir,
                         String paramsJson) throws Exception {
        String body = String.format(
            "{\"output_dir\":\"%s\",\"params\":%s}",
            outputDir, paramsJson.isEmpty() ? "{}" : paramsJson
        );
        HttpRequest req = HttpRequest.newBuilder()
            .uri(URI.create(base + "/run/" + crawlerName))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(body))
            .build();

        HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
        if (resp.statusCode() != 200)
            throw new RuntimeException("HTTP " + resp.statusCode() + ": " + resp.body());

        // 提取 task_id（生产环境建议用 Jackson/Gson）
        String rb = resp.body();
        int s = rb.indexOf("\"task_id\":\"") + 11;
        return rb.substring(s, rb.indexOf("\"", s));
    }

    /** 轮询直到任务结束，返回最终 state（"done" 或 "failed"） */
    public String waitFor(String taskId, long pollMs) throws Exception {
        HttpRequest req = HttpRequest.newBuilder()
            .uri(URI.create(base + "/tasks/" + taskId))
            .GET().build();
        while (true) {
            String body = http.send(req, HttpResponse.BodyHandlers.ofString()).body();
            if (body.contains("\"state\":\"done\""))   return "done";
            if (body.contains("\"state\":\"failed\"")) return "failed";
            Thread.sleep(pollMs);
        }
    }

    /** 健康检查 */
    public boolean isHealthy() {
        try {
            HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(base + "/health")).GET().build();
            return http.send(req, HttpResponse.BodyHandlers.ofString())
                       .statusCode() == 200;
        } catch (Exception e) { return false; }
    }

    public static void main(String[] args) throws Exception {
        CrawlerApiClient client = new CrawlerApiClient("http://localhost:8000");

        if (!client.isHealthy()) {
            System.err.println("API 服务未启动");
            return;
        }

        // 提交 wto_docs G/FS 系列任务
        String taskId = client.submit(
            "wto_docs",
            "/data/output/wto_docs",
            "{\"only_series\":\"GFS\",\"delay\":1.0}"
        );
        System.out.println("已提交，task_id = " + taskId);

        // 等待完成（每 5 秒轮询）
        String state = client.waitFor(taskId, 5000);
        System.out.println("结果: " + state);

        // 并行提交多个模块（无需等待各自完成）
        String id1 = client.submit("iotc",         "/data/output/iotc",         "");
        String id2 = client.submit("fishery_book",  "/data/output/fishery_book", "");
        System.out.println("iotc: "         + client.waitFor(id1, 5000));
        System.out.println("fishery_book: " + client.waitFor(id2, 5000));
    }
}
```

### 8.3 读取输出 Excel（Java 侧，Apache POI）

```java
import org.apache.poi.ss.usermodel.*;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import java.io.FileInputStream;

public class XlsxReader {
    public static void main(String[] args) throws Exception {
        // 读取 wto_docs 输出
        try (var fis = new FileInputStream("/data/output/wto_docs/index.xlsx");
             var wb  = new XSSFWorkbook(fis)) {

            Sheet all = wb.getSheet("全部");
            for (Row row : all) {
                if (row.getRowNum() == 0) continue;          // 跳过标题行
                String symbol = str(row, 2);   // 文档号
                String title  = str(row, 3);   // 标题
                String year   = str(row, 4);   // 年份
                String path   = str(row, 11);  // 本地路径
                if (!path.isEmpty())
                    System.out.printf("%-20s (%s) %s%n", symbol, year, path);
            }

            // 只看 G/FS 系列
            Sheet gfs = wb.getSheet("G-FS — 渔业补贴委员会");
            System.out.println("G/FS 系列共 " + (gfs.getLastRowNum()) + " 条");
        }
    }

    static String str(Row row, int col) {
        Cell c = row.getCell(col);
        return c == null ? "" : c.toString().trim();
    }
}
```

---

## 9 配置文件 config.yaml

```yaml
# negotiation_crawler — 运行时配置
# 修改此文件后无需重启，下次运行时自动读取。

defaults:
  fishery_book: "./output/fishery_books"   # fishery_book 默认输出目录
  iotc:         "./output/iotc"            # iotc 默认输出目录
  wto_site:     "./output/wto_site"        # wto_site 默认输出目录
  wto_docs:     "./output/wto_docs"        # wto_docs 默认输出目录

api:
  host: "0.0.0.0"    # API 监听地址（0.0.0.0 = 所有网卡，127.0.0.1 = 仅本机）
  port: 8000         # API 监听端口
```

**配置覆盖优先级（从高到低）：**

1. 命令行 `--out <目录>`
2. 环境变量 `NEGOTIATION_CRAWLER_CONFIG=/path/to/other.yaml`
3. 项目根目录 `config.yaml`

---

## 10 常见问题

**Q: 推荐从哪个模块开始？**
A: 从 `wto_docs` 开始，原因：纯 HTTP、无需浏览器、输出结构清晰、可以只跑单个系列（`--set only_series=GFS`）快速验证环境。

**Q: wto\_docs 全量运行需要多久？**
A: 约 2–4 小时（8 个系列合计数千页，每页间隔 0.8 秒）。建议先用 `--set only_series=GFS` 测试单系列（约 10–15 分钟）。

**Q: 磁盘空间不够怎么办？**
A: 用 `--out` 指定空间充足的目录（建议 SSD，预留 ≥ 50 GB）。也可先用 `--set fisheries_only=true` 只下载含渔业关键词的文件。

**Q: 已经下载过一次，如何只补充新文件不重爬？**

| 模块          | 命令                                                                          |
| ------------- | ----------------------------------------------------------------------------- |
| wto\_docs     | 默认`resume=true`，直接重跑即可（已有 JSONL 跳过枚举，已下载 PDF 跳过下载） |
| iotc          | `--set skip_manifest=true`（复用已有 SQLite，只补充下载）                   |
| fishery\_book | 默认断点续传，加`--set no_resume=true` 可强制重跑                           |
| wto\_site     | `--set resume=true`                                                         |

**Q: 如何只重新生成 xlsx，不重新爬取？**

```bash
# wto_docs
python -m negotiation_crawler run wto_docs --out ~/out/wto_docs \
  --set skip_detail=true --set skip_download=true

# iotc
python -m negotiation_crawler run iotc --out ~/out/iotc \
  --set skip_manifest=true --set enrich=false
```

**Q: Java 调用时找不到 python 命令？**
A: 在 ProcessBuilder 中写虚拟环境的完整路径：

```java
// Linux / Mac
String python = "/home/user/negotiation_crawler/.venv/bin/python";
// Windows
String python = "C:\\Users\\user\\negotiation_crawler\\.venv\\Scripts\\python.exe";
```

**Q: API 任务失败了，如何查看错误？**
A: `GET /tasks/{task_id}` 响应中的 `error` 和 `log` 字段包含完整错误信息。

**Q: 如何同时运行多个模块（不用 run all）？**
A: 启动 API 服务，分别提交 `POST /run/iotc` 和 `POST /run/fishery_book`，两个任务在后台并行执行，各自用 `task_id` 独立轮询。
