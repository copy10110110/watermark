# Watermark Tool — 批量水印 + AI 检测 设计文档

**日期**: 2026-06-21
**状态**: 设计中
**技术栈**: Python 3.14, FastAPI, Jinja2 + htmx, blind-watermark, SPAI, opencli

---

## 1. 项目目标

构建一个 Web 应用，提供：
- **标签页 A（嵌入水印）**: 图片 + 文本 → 盲水印嵌入（单张/批量）
- **标签页 B（提取/验证）**: 带水印图片 → 水印文本提取 + AI 生成检测

## 2. 架构概览

```
浏览器 (Jinja2 + htmx + SSE)
        │
        ▼
  uvicorn (单进程)
        │
        ▼
   FastAPI 服务
   ├── routers/
   │   ├── embed.py      # 水印嵌入 API
   │   ├── extract.py     # 水印提取 API
   │   └── detect.py      # AI 检测 API
   ├── services/
   │   ├── watermark_service.py   # blind-watermark 封装
   │   ├── spai_service.py        # SPAI 频谱检测
   │   ├── ring_detector.py       # Tree-Ring 频环检测（~50行）
   │   ├── c2pa_service.py        # C2PA/EXIF 元数据解析
   │   └── opencli_service.py     # opencli URL 图片抓取
   ├── templates/          # Jinja2 模板
   └── static/             # htmx.js, 自定义 JS
```

**核心原则：**
- 单进程 FastAPI，htmx + SSE 驱动实时更新（无需 WebSocket）
- SPAI 推理单张串行处理，避免 GPU 内存溢出
- opencli URL 检测按输入顺序依次执行，Chrome 单实例
- 盲水印嵌入/提取不限制并发（CPU 密集型用 `run_in_executor`）

## 3. 模块设计

### 3.1 水印服务 (`watermark_service.py`)

```
封装 blind-watermark 库：
├── embed(images: list[Path], texts: list[str], mode: str) -> list[Path]
│   mode: "uniform" (统一水印) | "mapped" (索引映射)
├── extract(images: list[Path]) -> list[dict]
│   返回: [{filename, extracted_text, confidence}]
└── 索引映射规则：
    - 按文件名升序排列 → 0-based 索引
    - CSV 映射表：两列 [filename, watermark_text]
    - UI 列表编辑：手动逐行输入后提交
```

### 3.2 SPAI 频谱检测 (`spai_service.py`)

```
├── detect_ai(image_path: Path) -> dict
│   返回: {
│     "score": float,           # AI 生成概率 0-1
│     "is_ai_generated": bool,
│     "spectral_error": float,  # 频谱重建 MSE
│     "ring_anomaly": float,    # Tree-Ring 频环异常度
│   }
├── 基于 spai-main 的 __main__.py infer 流程
└── 单张推理，GPU 内存友好
```

### 3.3 Tree-Ring 频环检测 (`ring_detector.py`)

```
策略：频谱环带异常检测（约 50 行新增代码）
├── 基于 SPAI filters.py 的 filter_image_frequencies() 输出
├── 计算特定半径频环内的能量峰值偏离度
├── 与已知无 Tree-Ring 的真实图像基线对比
├── 输出 ring_anomaly_score（0-1，越高越可疑）
└── 注解：非硬性判定，仅作为辅助信号
```

### 3.4 SynthID 降级策略

```
策略：频谱泛化 + 异常检测
├── 复用 SPAI 频谱重建 MSE
├── 将 MSE 与已知无水印的 AI 生成图像基线对比
├── Z-score 检验，P < 0.05 标记为"频谱异常"
└── 最终输出文本描述而非硬性判定：
    "AI 水印未确认，但存在以下信号：C2PA=xxx, 频谱异常=xxx, 频环异常=xxx"
```

### 3.5 C2PA 元数据 (`c2pa_service.py`)

```
├── parse_c2pa(image_path: Path) -> dict
│   返回: {
│     "has_c2pa": bool,
│     "issuer": str | None,
│     "timestamp": str | None,
│     "claims": dict
│   }
├── parse_exif(image_path: Path) -> dict
│   返回 EXIF 关键字段（Software, Artist, Make 等）
└── c2pa-python 库解析 C2PA manifest
```

### 3.6 OpenCLI 服务 (`opencli_service.py`)

```
├── fetch_images_from_url(url: str) -> list[Path]
│   流程：
│   1. opencli browser open <url> --profile E:\chrome
│   2. opencli extract 获取页面所有图片 URL
│   3. 下载图片到临时目录
│   4. 返回本地路径列表
├── 按输入 URL 顺序依次处理
├── 每次任务使用临时 Chrome profile 副本（隔离）
└── 超时 30s，超时则跳过该 URL
```

## 4. API 设计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 主页面（双标签页 UI） |
| POST | `/api/embed` | 嵌入水印（multipart/form-data） |
| POST | `/api/extract` | 提取水印 |
| POST | `/api/detect` | AI 检测（单张/批量） |
| POST | `/api/url-detect` | URL 图片检测（opencli） |
| GET | `/api/task/{id}` | 查询任务进度（SSE） |
| POST | `/api/task/{id}/cancel` | 取消任务 |
| GET | `/api/download/{id}` | 下载结果 zip |

**任务模型：**
```json
{
  "task_id": "uuid",
  "type": "embed | extract | detect | url-detect",
  "status": "pending | running | completed | cancelled | failed",
  "progress": { "current": 0, "total": 10 },
  "results": [],
  "errors": [],
  "skipped": []
}
```

## 5. 批量处理模式

### 5.1 统一水印 (Uniform)
- 所有图片应用相同水印文本
- 文件夹导入 → 自动过滤支持的格式 → 单文本框输入水印内容 → 执行

### 5.2 索引映射 (Mapped)
- 三种输入方式（优先级：手动编辑 > CSV 导入 > 文件名匹配）：
  1. **文件名匹配**：`{原名}.txt` 同名文本文件内容作为水印
  2. **CSV 导入**：两列表格 `[filename, watermark_text]`
  3. **手动编辑**：UI 列表逐行编辑，支持批量粘贴
- 未匹配到的图片标记警告，可选择跳过或使用默认文本

## 6. 输出规范

| 场景 | 命名规则 |
|------|----------|
| 嵌入单张 | `{原文件名}_wm.{ext}` |
| 提取结果 | `{原文件名}_result.csv`（含提取文本、置信度、AI 分数） |
| 批量打包 | `watermark_result_{timestamp}.zip` |
| 错误日志 | `errors.csv`（文件名、错误类型、错误信息） |
| 跳过列表 | `skipped.csv`（文件名、跳过原因） |
| 重名处理 | 自动追加 `_1`, `_2` 后缀，不覆盖 |

## 7. 文件处理

### 支持格式
| 格式 | 嵌入 | 提取 | 检测 |
|------|------|------|------|
| JPEG | ✅ | ✅ | ✅ |
| PNG | ✅ | ✅ | ✅ |
| WebP | ✅ | ✅ | ✅ |
| BMP | ✅ | ✅ | ✅ |
| TIFF | ⚠️ | ⚠️ | ✅ |
| 其他 | ❌ 跳过 | ❌ 跳过 | ❌ 跳过 |

### 图片尺寸限制
- 最大像素数：`PIL.Image.MAX_IMAGE_PIXELS` (89M ≈ 4K)
- 超大图自动等比缩放至 4K
- 不支持格式记录到 `skipped.csv`

## 8. 进度与错误处理

### 进度推送 (SSE)
```
event: progress
data: {"current": 5, "total": 20, "filename": "img005.jpg", "status": "embedding"}

event: complete
data: {"success": 18, "skipped": 1, "failed": 1, "download_url": "/api/download/xxx"}
```

### 错误恢复
- 单张失败不影响后续处理
- 最终报告统计 成功/跳过/失败 三类
- 支持取消操作（`asyncio.Event` + 前端取消按钮）

## 9. 安全措施

| 风险 | 措施 |
|------|------|
| 路径遍历 | `pathlib.resolve()` 校验在允许目录范围内 |
| Shell 注入 (opencli URL) | URL scheme 白名单 http/https，`shlex.quote()` 包裹 |
| Chrome profile 泄露 | 每次任务复制临时 profile，结束后删除 |
| 文件覆盖 | 重名自动加后缀，不静默覆盖 |
| 上传大小 | 限制 500MB，ZIP 解压后限制 2GB |

## 10. UI 设计

### 布局
```
┌─────────────────────────────────────────┐
│  Watermark Tool                     🔗  │
├──────────┬──────────────────────────────┤
│ Tab A    │ Tab B                        │
│ 嵌入水印 │ 提取/验证                      │
├──────────┴──────────────────────────────┤
│ [通用控件区]                               │
│ 模式选择: [统一水印] [索引映射]              │
│ 文件导入: [选择文件夹] [选择文件]            │
│ 水印文本: [________] (统一模式)             │
│ CSV映射:  [上传CSV]     (映射模式)          │
│ [开始处理] [取消]                          │
├──────────────────────────────────────────┤
│ 文件列表 (带状态图标)                       │
│ ✅ img001.jpg → img001_wm.jpg            │
│ ⏳ img002.jpg                            │
│ ❌ img003.bmp (不支持)                    │
├──────────────────────────────────────────┤
│ [进度条 ████████░░░░ 8/10]               │
│ 成功: 7  跳过: 1  失败: 0                 │
│ [下载结果 ZIP]                            │
└──────────────────────────────────────────┘
```

### 标签页 B 附加列
| 文件名 | 提取文本 | 基准文本 | 匹配 | AI 概率 | C2PA | 异常信号 |
|--------|----------|----------|------|---------|------|----------|
| img01 | "hello" | "hello" | ✅ | 0.02 | ❌ | — |
| img02 | — | — | ⬜无水印 | 0.89 | ❌ | 频谱异常, 频环异常 |
| img03 | "test" | "test1" | ❌ | 0.15 | ✅ Adobe | — |

## 11. 目录结构

```
watermark/
├── main.py                    # 应用入口（uvicorn 启动）
├── pyproject.toml
├── config.yaml                # 应用配置（Chrome 路径等）
├── watermark_app/
│   ├── __init__.py
│   ├── main.py                # FastAPI app 工厂
│   ├── config.py              # 配置加载
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── embed.py
│   │   ├── extract.py
│   │   └── detect.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── watermark_service.py
│   │   ├── spai_service.py
│   │   ├── ring_detector.py
│   │   ├── c2pa_service.py
│   │   └── opencli_service.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── task.py            # 任务数据模型
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html
│   │   └── components/        # htmx 局部刷新组件
│   └── static/
│       ├── htmx.min.js
│       └── app.js
├── watermark_tools/           # 外部工具目录（已有）
│   ├── spai-main/             # SPAI 检测引擎
│   └── node_modules/          # opencli
└── tests/
    ├── test_watermark_service.py
    ├── test_spai_service.py
    ├── test_opencli_service.py
    └── test_api.py
```

## 12. 测试策略

| 层级 | 工具 | 覆盖内容 |
|------|------|----------|
| 单元测试 | pytest | 各 service 函数 |
| 集成测试 | pytest + httpx | FastAPI TestClient，完整 API 流程 |
| SPAI 测试 | 预置 5 张真实图 + 5 张 AI 图 | 检测准确率 > 80% |
| opencli 测试 | mock CLI 输出 | URL 抓取逻辑，不透彻测试 |

---

## 审计总结

### 已解决的歧义
1. "watermark prompt" → `blind-watermark` 库 + `opencli` CLI
2. "Chrome 硬编码/可配置" → 默认 `E:\chrome`，`config.yaml` 覆盖
3. 文件名匹配规则 → 精确匹配含扩展名，备选忽略扩展名
4. 提取失败行为 → 标记"无水印"，不参与对比
5. URL 并发 → 按输入顺序串行，单 Chrome 实例

### 已补充的缺口
1. 进度条 → SSE 推送
2. 取消操作 → `asyncio.Event` + 前端按钮
3. 输出命名 → 统一规范
4. 格式降级 → skipped.csv + UI 警告
5. Chrome 隔离 → 临时 profile 副本
6. 内存限制 → MAX_IMAGE_PIXELS + 自动缩放
7. 错误恢复 → 单张失败不中断
8. 安全措施 → 路径校验、Shell 注入防护、profile 隔离、文件覆盖保护
