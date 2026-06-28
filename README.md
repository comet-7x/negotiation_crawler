# negotiation_crawler

渔业谈判材料统一爬虫，支持命令行直接运行、定时任务调度和 Java 程序远程调用。

| 模块              | 爬取来源                        | 输出内容                         |
| ----------------- | ------------------------------- | -------------------------------- |
|  `fishery_book` | FAO 知识库（DSpace API）        | PDF 文件 + Excel 审计表          |
| `iotc`          | 印度洋金枪鱼委员会（IOTC 网站） | PDF 文件 + Excel 清单            |
| `wto_site`      | WTO 渔业补贴协定主网页及子页    | Markdown 语料库                  |
| `wto_docs`      | WTO 文档库（docs.wto.org）      | PDF 文件（TN/RL、WT/MIN 等系列） |

---

## 目录结构

```
negotiation_crawler/          ← 项目根目录（可直接 git clone 使用）
├── config.yaml               ← 配置文件（输出目录、API 端口）
├── pyproject.toml            ← 依赖声明
├── README.md
└── negotiation_crawler/      ← Python 包
    ├── cli.py                ← 命令行入口
    ├── api.py                ← HTTP API（供 Java 调用）
    ├── dedup.py              ← 全局 SHA-256 去重工具
    ├── base.py               ← 基类定义
    ├── config.py             ← 配置加载
    └── crawlers/
        ├── fishery_book/
        │   ├── classifier/   ← 国家/机构识别
        │   ├── fetch/        ← DSpace HTTP 客户端
        │   ├── process/      ← PDF 元数据 + Excel 生成
        │   └── storage/      ← SQLite manifest 持久化
        ├── iotc/
        │   ├── classifier/   ← 来源国识别
        │   ├── fetch/        ← IOTC 页面爬取
        │   ├── process/      ← Excel 生成
        │   └── storage/      ← SQLite manifest
        ├── wto_site/
        │   ├── classifier/   ← 文档分类
        │   ├── fetch/        ← 异步 HTTP + URL 规则
        │   ├── process/      ← HTML/PDF → Markdown 转换
        │   └── storage/      ← 内容去重 + 数据模型
        └── wto_docs/
            ├── fetch/        ← Playwright 浏览器搜索 + 直连下载
            ├── classifier/
            ├── process/
            └── storage/
```

---

## 快速开始（5 分钟上手）

### 第一步：安装 Python

需要 **Python 3.11 或更高版本**。

```bash
# 检查版本（需要显示 3.11 及以上）
python3 --version
```

如果没有安装，前往 https://www.python.org/downloads/ 下载安装。

---

### 第二步：获取项目代码

```bash
git clone <你的仓库地址>
cd negotiation_crawler
```

---

### 第三步：安装依赖

```bash
# 安装核心依赖（必须）
pip install -e .

# 如果需要 PDF 页数识别和 Markdown 转换（可选，推荐安装）
pip install -e ".[pdf]"

# 如果需要 WTO 文档库浏览器搜索（可选，需额外下载 Chromium）
pip install -e ".[wto-docs-harvest]"
playwright install chromium

# 一次安装全部功能
pip install -e ".[all]"
playwright install chromium
```

> **说明：** `pip install -e .` 中的 `-e` 表示"可编辑模式"，让 Python 直接读取项目源码，修改代码后不需要重新安装。

---

### 第四步：运行爬虫

```bash
# 查看所有可用模块
python -m negotiation_crawler list

# 运行单个模块（结果保存到 config.yaml 中配置的默认目录）
python -m negotiation_crawler run iotc

# 指定输出目录
python -m negotiation_crawler run fishery_book --out /data/fishery

# 一次性运行全部 4 个模块，完成后自动去重
python -m negotiation_crawler run all --out /data/output
```

---

## 配置文件说明（config.yaml）

```yaml
defaults:
  fishery_book: "./output/fishery_books"   # fishery_book 模块的默认输出目录
  iotc:         "./output/iotc"            # iotc 模块的默认输出目录
  wto_site:     "./output/wto_site"        # wto_site 模块的默认输出目录
  wto_docs:     "./output/wto_docs"        # wto_docs 模块的默认输出目录

api:
  host: "0.0.0.0"   # HTTP API 监听地址（0.0.0.0 表示接受所有网络请求）
  port: 8000         # HTTP API 端口号
```

**路径说明：**

- 相对路径（`./output/...`）以项目根目录为基准
- 也可以填写绝对路径（如 `/data/output/iotc`）
- 命令行 `--out` 参数优先级高于此配置

---

## 常用命令参考

### 运行单个模块

```bash
# FAO 渔业书籍
python -m negotiation_crawler run fishery_book --out ./output/fishery_books

# IOTC（跳过下载，只抓列表 + 生成 Excel）
python -m negotiation_crawler run iotc --set list_only=true

# WTO 主网页（限制爬取深度为 2 层）
python -m negotiation_crawler run wto_site --set max_depth=2

# WTO 文档库（跳过 Playwright 浏览器阶段，直接按已知文号下载）
python -m negotiation_crawler run wto_docs --set skip_harvest=true
```

### 一次爬取全部模块（推荐）

```bash
# 全量爬取，完成后自动对 PDF/Office 文件做 SHA-256 去重
python -m negotiation_crawler run all --out ./output

# 先预览会删除哪些重复文件（不实际删除）
python -m negotiation_crawler run all --out ./output --dry-run
```

输出结构：

```
output/
├── fishery_books/   ← fishery_book 模块输出
├── iotc/            ← iotc 模块输出
├── wto_site/        ← wto_site 模块输出
├── wto_docs/        ← wto_docs 模块输出
└── dedup_report.json  ← 去重报告（记录每个重复文件的正本路径和副本路径）
```

### 对已有输出单独去重

```bash
# 扫描 ./output，删除 SHA-256 相同的重复 PDF/Office 文件
python -m negotiation_crawler dedup ./output

# 只预览，不删除
python -m negotiation_crawler dedup ./output --dry-run
```

### 启动 HTTP API

```bash
python -m negotiation_crawler serve
# 默认监听 http://0.0.0.0:8000

python -m negotiation_crawler serve --port 9000  # 自定义端口
```

---

## `--set` 参数列表

通过 `--set KEY=VALUE` 向单个模块传递额外参数（可重复使用多个 `--set`）：

### fishery_book

| 参数            | 类型 | 默认值 | 说明                   |
| --------------- | ---- | ------ | ---------------------- |
| `no_download` | bool | false  | 只建立清单，不下载 PDF |
| `no_resume`   | bool | false  | 从头爬取，忽略已有进度 |
| `concurrency` | int  | 4      | 并发下载数             |
| `limit`       | int  | 无限制 | 最多处理多少条记录     |

### iotc

| 参数              | 类型 | 默认值 | 说明                                   |
| ----------------- | ---- | ------ | -------------------------------------- |
| `skip_manifest` | bool | false  | 跳过第一阶段（列表页抓取）             |
| `list_only`     | bool | false  | 只建清单 + 生成 Excel，不下载 PDF      |
| `enrich`        | bool | true   | 访问每篇文档的落地页补充元数据         |
| `build_xlsx`    | bool | true   | 生成 Excel 清单                        |
| `all_langs`     | bool | false  | 同时抓取法语文档                       |
| `limit`         | int  | 无限制 | 最多处理多少条                         |
| `only`          | str  | 全部   | 只处理某种类型（如`Meeting Report`） |

### wto_site

| 参数             | 类型  | 默认值 | 说明                               |
| ---------------- | ----- | ------ | ---------------------------------- |
| `max_depth`    | int   | 4      | 从种子 URL 出发的最大爬取深度      |
| `concurrency`  | int   | 4      | 并发请求数                         |
| `delay`        | float | 1.0    | 每次请求后的等待秒数（礼貌性延迟） |
| `include_docs` | bool  | false  | 同时爬取 docs.wto.org 上的文件     |
| `max_pages`    | int   | 无限制 | 最多保留多少篇 Markdown            |
| `resume`       | bool  | false  | 断点续爬                           |

### wto_docs

| 参数             | 类型  | 默认值                  | 说明                       |
| ---------------- | ----- | ----------------------- | -------------------------- |
| `query`        | str   | `fisheries subsidies` | 搜索关键词（Phase 1）      |
| `query_type`   | str   | `fulltext`            | `fulltext` 或 `symbol` |
| `max_pages`    | int   | 50                      | 最多翻多少页搜索结果       |
| `headed`       | bool  | false                   | 显示浏览器窗口（调试用）   |
| `skip_harvest` | bool  | false                   | 跳过 Playwright 搜索阶段   |
| `skip_fetch`   | bool  | false                   | 跳过直连下载阶段           |
| `delay`        | float | 0.5                     | 下载间隔秒数               |

---

## Java 集成

### 方式一：命令行调用（ProcessBuilder）

适合简单的定时任务，无需常驻进程。

```java
import java.io.*;

public class CrawlerCaller {

    public static void runCrawler(String module, String outputDir) throws Exception {
        ProcessBuilder pb = new ProcessBuilder(
            "python", "-m", "negotiation_crawler",
            "run", module,
            "--out", outputDir
        );
        pb.directory(new File("/path/to/negotiation_crawler"));  // ← 改为项目根目录
        pb.redirectErrorStream(true);

        Process proc = pb.start();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(proc.getInputStream()))) {
            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println("[crawler] " + line);
            }
        }

        int exitCode = proc.waitFor();
        if (exitCode != 0) {
            throw new RuntimeException("Crawler exited with code " + exitCode);
        }
    }

    public static void main(String[] args) throws Exception {
        // 运行单个模块
        runCrawler("iotc", "/data/output/iotc");

        // 运行全部模块并自动去重
        runCrawler("all", "/data/output");
    }
}
```

---

### 方式二：HTTP API（推荐用于定时调度）

**第一步：启动 API 服务**（建议配置为系统服务常驻运行）

```bash
python -m negotiation_crawler serve --port 8000
```

**第二步：Java 调用**

```java
import java.net.URI;
import java.net.http.*;
import java.time.Duration;

public class CrawlerApiClient {

    private static final String BASE_URL = "http://localhost:8000";
    private final HttpClient http = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(10))
        .build();

    /** 提交爬取任务，立即返回 task_id（后台异步执行） */
    public String submitTask(String crawlerName, String outputDir) throws Exception {
        String requestBody = String.format(
            "{\"output_dir\": \"%s\", \"params\": {}}", outputDir);

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(BASE_URL + "/run/" + crawlerName))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(requestBody))
            .build();

        HttpResponse<String> response = http.send(request,
            HttpResponse.BodyHandlers.ofString());

        // 简单提取 task_id（生产环境请用 Jackson 或 Gson 解析 JSON）
        String json = response.body();
        String taskId = json.replaceAll(".*\"task_id\":\\s*\"([^\"]+)\".*", "$1");
        System.out.println("Task submitted, id = " + taskId);
        return taskId;
    }

    /** 轮询任务状态，直到完成或失败 */
    public String waitForTask(String taskId) throws Exception {
        while (true) {
            HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/tasks/" + taskId))
                .GET().build();

            HttpResponse<String> response = http.send(request,
                HttpResponse.BodyHandlers.ofString());
            String json = response.body();

            if (json.contains("\"DONE\"")) {
                System.out.println("Task completed: " + taskId);
                return json;
            } else if (json.contains("\"FAILED\"")) {
                throw new RuntimeException("Task failed: " + json);
            }

            System.out.println("Still running, retry in 30s...");
            Thread.sleep(30_000);
        }
    }

    public static void main(String[] args) throws Exception {
        CrawlerApiClient client = new CrawlerApiClient();

        // 运行全部模块（"all" 会依次执行 4 个爬虫后自动去重）
        String taskId = client.submitTask("all", "/data/output");
        String result  = client.waitForTask(taskId);
        System.out.println("Final result: " + result);
    }
}
```

**API 端点一览：**

| 方法 | 路径                 | 说明                         |
| ---- | -------------------- | ---------------------------- |
| GET  | `/crawlers`        | 查看所有可用模块             |
| POST | `/run/{模块名}`    | 提交任务（`all` 运行全部） |
| GET  | `/tasks/{task_id}` | 查询任务状态                 |
| GET  | `/tasks`           | 查看所有任务                 |
| GET  | `/health`          | 健康检查                     |

**任务状态：**

| 状态        | 含义                                   |
| ----------- | -------------------------------------- |
| `PENDING` | 已提交，排队中                         |
| `RUNNING` | 正在爬取                               |
| `DONE`    | 成功完成                               |
| `FAILED`  | 执行失败（查看响应中的`error` 字段） |

---

## 常见问题

**Q: 提示 `No module named 'playwright'`**

wto_docs 的 Phase 1 需要 Playwright，可选安装：

```bash
pip install playwright && playwright install chromium
```

如果不需要浏览器搜索，直接跳过：`--set skip_harvest=true`

**Q: IOTC 爬取很慢**

IOTC 有 31 种文档类型，先用单类型测试：

```bash
python -m negotiation_crawler run iotc --set only="Meeting Report" --set limit=50
```

**Q: 上次没跑完，能断点续爬吗？**

- `fishery_book` / `iotc`：自动支持，重新运行会跳过已有记录
- `wto_site`：加 `--set resume=true`
- `wto_docs`：加 `--set skip_harvest=true` 跳过浏览器阶段

**Q: 如何只去重已有文件，不重新爬取？**

```bash
python -m negotiation_crawler dedup ./output
```
