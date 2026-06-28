# negotiation_crawler

统一爬虫调度中心，将以下四个独立爬虫模块整合为一个可被 Java 定时调用的服务：

| 模块 | 数据来源 | 输出 |
|------|---------|------|
| `fishery_book` | FAO 知识库（DSpace REST API）| PDF + Excel 审计表 |
| `iotc` | 印度洋金枪鱼委员会（IOTC Drupal 网站）| PDF + 多 Sheet Excel |
| `wto_site` | WTO 渔业补贴协定主网页及子页面 | Markdown 语料库 + JSON manifest |
| `wto_docs` | WTO 文档库（docs.wto.org）| PDF（TN/RL、WT/MIN、WT/L 系列）|

---

## 项目结构

```
negotiation_crawler/
├── pyproject.toml                  # 项目依赖和入口点定义
├── config.yaml                     # 运行时配置（原始项目路径、输出目录）
├── README.md
├── .gitignore
└── negotiation_crawler/            # Python 包
    ├── __init__.py
    ├── __main__.py                 # python -m negotiation_crawler 入口
    ├── base.py                     # BaseCrawler 基类、CrawlResult、TaskInfo
    ├── config.py                   # YAML 配置加载
    ├── cli.py                      # 命令行接口
    ├── api.py                      # FastAPI HTTP 服务（供 Java 调用）
    └── crawlers/
        ├── __init__.py             # 爬虫注册表（新增模块只需在此添加）
        ├── fishery_book.py         # FAO 渔业书籍爬虫
        ├── iotc.py                 # IOTC 文档爬虫
        ├── _iotc_runner.py         # IOTC 专用子进程 helper
        ├── wto_site.py             # WTO 主网页爬虫
        └── wto_docs.py             # WTO 文档库下载
```

---

## 依赖关系

本项目是调度层，**不包含**各爬虫的具体爬取逻辑。实际爬取代码仍在各自原始项目中：

```
virtual_negotiation_crawler/src/
├── fishery_book_crawler/   ← fishery_book 模块依赖
├── iotc_crawler/           ← iotc 模块依赖
└── wto_fish_crawler/       ← wto_site 和 wto_docs 模块共同依赖
```

`config.yaml` 中的 `src_dir` 配置项指向这些目录。

---

## 安装

### 1. 安装 Python 依赖

```bash
cd negotiation_crawler

# 安装核心调度层
pip install -e .

# 按需安装对应爬虫的依赖（可多选）
pip install -e ".[fishery-book]"
pip install -e ".[iotc]"
pip install -e ".[wto-site]"
pip install -e ".[wto-docs]"

# 或全部安装
pip install -e ".[all]"
```

### 2. 配置原始项目路径

编辑 `config.yaml`，将 `src_dir` 改为实际路径：

```yaml
projects:
  fishery_book:
    src_dir: "/mnt/steins/zhihao/SHOU_Project/virtual_negotiation_crawler/src/fishery_book_crawler"
    default_out: "./output/fishery_books"

  iotc:
    src_dir: "/mnt/steins/zhihao/SHOU_Project/virtual_negotiation_crawler/src/iotc_crawler"
    default_out: "./output/iotc"

  wto_site:
    src_dir: "/mnt/steins/zhihao/SHOU_Project/virtual_negotiation_crawler/src/wto_fish_crawler"
    default_out: "./output/wto_site"

  wto_docs:
    src_dir: "/mnt/steins/zhihao/SHOU_Project/virtual_negotiation_crawler/src/wto_fish_crawler"
    default_out: "./output/wto_docs"
```

也可以通过环境变量指定不同的配置文件：

```bash
export NEGOTIATION_CRAWLER_CONFIG=/path/to/my_config.yaml
```

### 3. WTO 文档库（wto_docs）额外步骤

`wto_docs` 模块的 Phase 1（网页枚举）依赖 Playwright：

```bash
pip install playwright
playwright install chromium
```

Phase 2（PDF 下载）不需要 Playwright，可以单独运行（`--set skip_harvest=true`）。

---

## 命令行使用

### 查看可用模块

```bash
python -m negotiation_crawler list
```

输出：
```
Name             Description
------------------------------------------------------------
fishery_book     FAO fishery publications from the Knowledge Repository (DSpace)
iotc             IOTC (Indian Ocean Tuna Commission) documents — all 31 document types
wto_site         WTO fisheries subsidies agreement main site and subpages → Markdown corpus
wto_docs         WTO Documents Online — TN/RL, WT/MIN, WT/L fisheries series download
```

### 运行单个模块

```bash
# FAO 渔业书籍（元数据审计，不下载 PDF）
python -m negotiation_crawler run fishery_book --out /data/output/fishery_books \
    --set no_download=true

# FAO 渔业书籍（完整爬取）
python -m negotiation_crawler run fishery_book --out /data/output/fishery_books

# IOTC 文档（增量更新，典型月度调用）
python -m negotiation_crawler run iotc --out /data/output/iotc \
    --set skip_manifest=true --set enrich=true --set build_xlsx=true

# IOTC 文档（首次全量爬取）
python -m negotiation_crawler run iotc --out /data/output/iotc \
    --set enrich=true --set build_xlsx=true

# WTO 主网页爬取（深度4，输出 Markdown）
python -m negotiation_crawler run wto_site --out /data/output/wto_site \
    --set max_depth=4

# WTO 主网页爬取（从上次中断处续爬）
python -m negotiation_crawler run wto_site --out /data/output/wto_site \
    --set resume=true

# WTO 文档库（跳过 Playwright 枚举，仅下载已知文号的 PDF）
python -m negotiation_crawler run wto_docs --out /data/output/wto_docs \
    --set skip_harvest=true

# WTO 文档库（完整两阶段，需要 Playwright）
python -m negotiation_crawler run wto_docs --out /data/output/wto_docs
```

`--set` 参数支持任意布尔值、整数、浮点数和字符串，可重复使用。`--out` 省略时使用 `config.yaml` 中的 `default_out`。

---

## Java 集成

### 方式一：命令行调用（ProcessBuilder）

```java
import java.util.List;

public class NegotiationCrawlerScheduler {

    /**
     * 运行指定爬虫模块。outputDir 为 null 时使用 config.yaml 默认路径。
     */
    public static int runCrawler(String crawlerName, String outputDir, List<String> extraArgs)
            throws Exception {
        List<String> cmd = new ArrayList<>(List.of(
            "python3", "-m", "negotiation_crawler", "run", crawlerName
        ));
        if (outputDir != null) {
            cmd.addAll(List.of("--out", outputDir));
        }
        cmd.addAll(extraArgs);

        ProcessBuilder pb = new ProcessBuilder(cmd);
        pb.directory(new File("/mnt/steins/zhihao/SHOU_Project/negotiation_crawler"));
        pb.environment().put(
            "NEGOTIATION_CRAWLER_CONFIG",
            "/mnt/steins/zhihao/SHOU_Project/negotiation_crawler/config.yaml"
        );
        pb.redirectErrorStream(true);

        Process p = pb.start();
        // 读取输出（防止缓冲区阻塞）
        try (var reader = new java.io.BufferedReader(
                new java.io.InputStreamReader(p.getInputStream()))) {
            reader.lines().forEach(System.out::println);
        }
        return p.waitFor();
    }

    // 示例：月度定时调用 IOTC 增量更新
    public static void scheduleIotcMonthly() throws Exception {
        int exitCode = runCrawler(
            "iotc",
            "/data/output/iotc",
            List.of("--set", "skip_manifest=true",
                    "--set", "enrich=true",
                    "--set", "build_xlsx=true")
        );
        if (exitCode != 0) {
            throw new RuntimeException("IOTC crawler failed with exit code " + exitCode);
        }
    }
}
```

### 方式二：HTTP API 调用（推荐用于生产调度）

首先启动 API 服务：

```bash
python -m negotiation_crawler serve --host 0.0.0.0 --port 8000
```

然后从 Java 发起 HTTP 请求：

```java
import java.net.http.*;
import java.net.URI;

public class NegotiationCrawlerClient {

    private static final String BASE_URL = "http://localhost:8000";
    private final HttpClient http = HttpClient.newHttpClient();

    /** 提交爬虫任务，立即返回 task_id */
    public String submitTask(String crawlerName, String outputDir, Map<String, Object> params)
            throws Exception {
        String body = String.format(
            "{\"output_dir\": \"%s\", \"params\": %s}",
            outputDir, new ObjectMapper().writeValueAsString(params)
        );
        HttpRequest req = HttpRequest.newBuilder()
            .uri(URI.create(BASE_URL + "/run/" + crawlerName))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(body))
            .build();
        HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
        // 从响应 JSON 中取 task_id
        return new ObjectMapper().readTree(resp.body()).get("task_id").asText();
    }

    /** 轮询任务状态直到完成 */
    public String waitForTask(String taskId) throws Exception {
        while (true) {
            HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/tasks/" + taskId))
                .GET().build();
            HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString());
            var node = new ObjectMapper().readTree(resp.body());
            String state = node.get("state").asText();
            if (state.equals("DONE") || state.equals("FAILED")) {
                return state;
            }
            Thread.sleep(5000);  // 每5秒轮询一次
        }
    }
}
```

**API 端点一览：**

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/crawlers` | 列出所有可用模块 |
| `POST` | `/run/{crawler_name}` | 启动爬虫任务（异步，立即返回 `task_id`）|
| `GET` | `/tasks/{task_id}` | 查询任务状态（PENDING/RUNNING/DONE/FAILED）|
| `GET` | `/tasks` | 列出所有任务 |
| `GET` | `/health` | 健康检查 |

---

## 各模块详细参数

### fishery_book

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `no_download` | bool | false | 仅获取元数据，不下载 PDF |
| `no_resume` | bool | false | 重新解析所有种子（忽略已有 manifest） |
| `category` | list[str] | null | 只爬指定类别（如 `["SOFIA"]`） |
| `limit` | int | null | 限制处理的种子数（调试用） |
| `concurrency` | int | 4 | 并发请求数 |
| `http1` | bool | false | 强制使用 HTTP/1.1 |
| `proxy` | str | null | 代理地址（如 `http://127.0.0.1:7890`）|
| `log_level` | str | INFO | 日志级别 |
| `seeds` | str | null | 自定义种子文件路径 |

**输出：**
```
<output_dir>/
├── manifest.sqlite3          # SQLite 索引
├── fishery_books_audit.xlsx  # Excel 审计表（含状态颜色）
└── pdf/                      # 下载的 PDF 文件
```

### iotc

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `skip_manifest` | bool | false | 跳过目录页爬取（manifest 已存在时使用）|
| `list_only` | bool | false | 仅建立 manifest，不下载 PDF |
| `enrich` | bool | true | 爬取详情页补充元数据 |
| `build_xlsx` | bool | true | 生成 Excel 报告 |
| `all_langs` | bool | false | 保留法语文档（默认只保留英语）|
| `limit` | int | null | 限制处理数量（调试用）|
| `only` | str | null | 只处理指定文档类型（如 `"National Reports"`）|

**典型月度调用：** `skip_manifest=true, enrich=true, build_xlsx=true`

**输出：**
```
<output_dir>/
├── manifest.sqlite           # SQLite 索引（28列，28,000+条记录）
├── iotc_documents.xlsx       # 多 Sheet Excel（11个分类 Sheet）
└── pdfs/                     # 按类型/年份组织的 PDF
    ├── Meeting Report/2024/
    ├── National Reports/2025/
    └── ...（共31种文档类型）
```

### wto_site

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_depth` | int | 4 | 最大递归深度 |
| `concurrency` | int | 4 | 并发请求数 |
| `delay` | float | 1.0 | 请求间隔（秒，礼貌爬取）|
| `include_docs` | bool | false | 同时爬取 docs.wto.org 文档库 |
| `max_pages` | int | null | 最多保留页数（冒烟测试用）|
| `pdf_backend` | str | pymupdf | PDF 解析后端（`pymupdf` 或 `mineru`）|
| `resume` | bool | false | 从上次中断处续爬 |
| `seeds` | list[str] | null | 覆盖默认起始 URL |

**输出：**
```
<output_dir>/
├── markdown/                 # Markdown 文件（含 YAML front matter）
│   └── <content_hash>.md
├── raw/html/                 # 原始 HTML
├── raw/pdf/                  # 原始 PDF
├── manifest.jsonl            # 每个资源一条记录
├── external_links.jsonl      # 外部链接列表
├── dedup_report.csv          # 内容去重报告
└── crawl.log
```

### wto_docs

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | str | "fisheries subsidies" | 搜索关键词（Phase 1）|
| `query_type` | str | "fulltext" | 搜索类型：`fulltext` 或 `symbol` |
| `max_pages` | int | 50 | 最多翻页数（Phase 1）|
| `headed` | bool | false | 显示浏览器窗口（Phase 1 调试用）|
| `login` | bool | false | 暂停等待手动登录（Phase 1）|
| `skip_harvest` | bool | false | 跳过 Phase 1（复用已有 manifest）|
| `extra_symbols` | list[str] | null | 额外指定文号（Phase 2）|
| `skip_fetch` | bool | false | 跳过 Phase 2（仅枚举，不下载）|
| `delay` | float | 0.5 | 下载间隔（秒，Phase 2）|

**注意：** Phase 1 需要安装 Playwright (`pip install playwright && playwright install chromium`)。  
Phase 2 使用直链下载，不需要 Playwright，可单独运行（`skip_harvest=true`）。

**输出：**
```
<output_dir>/
├── docs_manifest/
│   └── docs_manifest.jsonl   # Phase 1 枚举结果
└── raw/docs/                 # Phase 2 下载的 PDF
```

---

## 扩展：接入新爬虫

1. 在 `negotiation_crawler/crawlers/` 新建 `my_crawler.py`，继承 `BaseCrawler`：

```python
from ..base import BaseCrawler, CrawlResult

class MyCrawler(BaseCrawler):
    name = "my_crawler"
    description = "我的新爬虫描述"

    def run(self, output_dir: str | None = None, **kwargs) -> CrawlResult:
        # 在这里实现爬取逻辑
        ...
        return CrawlResult(success=True, output_dir=output_dir)
```

2. 在 `negotiation_crawler/crawlers/__init__.py` 中注册：

```python
from .my_crawler import MyCrawler

_REGISTRY = {
    c.name: c()
    for c in [FisheryBookCrawler, IotcCrawler, WtoSiteCrawler, WtoDocsCrawler, MyCrawler]
}
```

3. 在 `config.yaml` 中添加配置项（如果有原始项目需要引用）。

---

## 许可证

本项目仅供学术研究使用。
