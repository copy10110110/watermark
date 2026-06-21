# Watermark Tool — 批量水印 + AI 检测 设计文档 (v2)

**日期**: 2026-06-21
**状态**: 设计中
**技术栈**: Python 3.14, FastAPI, Jinja2 + htmx, blind-watermark, SPAI, opencli

---

## 1. 项目目标

构建一个 Web 应用，提供：
- **标签页 A（嵌入水印）**: 图片 + 文本 → 盲水印嵌入（单张/批量）
- **标签页 B（提取/验证）**: 带水印图片 → 水印文本提取 + AI 生成检测

## 2. watermark prompt 调用协议

`watermark` 的实质是 `blind-watermark` Python 库的本地函数调用，不是外部 prompt。

### 2.1 嵌入接口
```python
def embed_watermark(
    image_path: Path,
    text: str,
    password: str = "",           # 可选加密密码，默认无
    output_path: Path | None = None
) -> EmbedResult:
    """
    返回:
      EmbedResult:
        success: bool
        output_path: Path         # 输出文件路径
        error: str | None         # 失败原因
        elapsed_ms: int           # 耗时
    异常: 不抛出，全部捕获到 EmbedResult.error
    超时: 单张 60s，超时返回 error="timeout"
    """
```

### 2.2 提取接口
```python
def extract_watermark(
    image_path: Path,
    password: str = ""            # 与嵌入时一致
) -> ExtractResult:
    """
    返回:
      ExtractResult:
        success: bool
        text: str | None          # 提取的水印文本，无水印时为 None
        confidence: float         # 盲水印库返回的置信度 0-1
        error: str | None
        elapsed_ms: int
    超时: 单张 30s
    """
```

### 2.3 错误返回码
| code | 含义 |
|------|------|
| 0 | 成功 |
| 1 | 文件不存在/无法读取 |
| 2 | 格式不支持 |
| 3 | 图片中未检测到水印（仅提取） |
| 4 | 超时 |
| 5 | 水印文本过长（>1024字符） |
| 99 | 未知内部错误 |

## 3. 架构概览

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
   │   ├── ring_detector.py       # Tree-Ring 频环检测
   │   ├── c2pa_service.py        # C2PA/EXIF 元数据解析
   │   └── opencli_service.py     # opencli URL 图片抓取
   ├── templates/          # Jinja2 模板
   └── static/             # htmx.js, 自定义 JS
```

**核心原则：**
- 单进程 FastAPI，htmx + SSE 驱动实时更新（无需 WebSocket）
- SPAI 推理单张串行处理，避免 GPU 内存溢出
- opencli URL 检测按输入顺序依次执行，Chrome 单实例
- 盲水印嵌入/提取用 `run_in_executor` 放入线程池（CPU 密集）
- 两个标签页共享同一个任务队列（`asyncio.Queue`），最多 1 个活跃任务
- 切换标签页不中断任务；任务状态通过 SSE 全局广播

## 4. 模块设计

### 4.1 水印服务 (`watermark_service.py`)
```
封装 blind-watermark 库：
├── embed_batch(images: list[Path], mapping: dict[str,str], mode: Literal["uniform","mapped"]) -> BatchResult
├── extract_batch(images: list[Path]) -> BatchResult
└── 索引映射规则（详见 §6）
```

### 4.2 SPAI 频谱检测 (`spai_service.py`)
```
├── detect_ai(image_path: Path) -> dict
│   返回: {
│     "ai_score": float,         # AI 生成概率 0-1
│     "verdict": str,            # "likely_real" | "likely_ai" | "uncertain"
│     "spectral_mse": float,     # 频谱重建 MSE
│     "ring_anomaly": float,     # Tree-Ring 频环异常度 0-1
│     "synthid_flag": bool,      # SynthID 频谱异常标记
│     "elapsed_ms": int
│   }
├── 基于 spai-main 的 __main__.py infer 流程
├── 单张推理，GPU 内存友好
└── 置信度阈值:
    - ai_score >= 0.7 → "likely_ai"
    - ai_score <= 0.3 → "likely_real"
    - 0.3 < ai_score < 0.7 → "uncertain"
```

### 4.3 Tree-Ring 频环检测 (`ring_detector.py`)
```
策略：频谱环带异常检测（约 50 行新增代码）
├── 基于 SPAI filters.py 的 filter_image_frequencies() 输出
├── 计算 3 个半径频环（低频/中频/高频）的能量峰值偏离度
├── 与预计算的 100 张真实图像基线（h=0 假设检验）对比
├── 输出 ring_anomaly_score（0-1）
│   - >= 0.6 → 标记为"频环异常"
│   - < 0.6 → 正常范围
└── 注解：非硬性判定，仅作为辅助信号
```

### 4.4 SynthID 降级策略
```
策略：频谱泛化 + 异常检测（无公开检测器时的降级方案）
├── 复用 SPAI 频谱重建 MSE
├── 将 MSE 与已知无水印的 AI 生成图像基线对比
├── Z-score 检验（双侧，α=0.05）→ |Z| > 1.96 标记 synthid_flag=true
├── 使用 Kernel Density Estimation(KDE) 估计基线分布
└── 最终输出文本描述而非硬性判定：
    "AI 水印未确认，但存在以下信号：C2PA=xxx, 频谱异常=xxx, 频环异常=xxx"
```

### 4.5 C2PA 元数据 (`c2pa_service.py`)
```
├── parse_c2pa(image_path: Path) -> dict | None
│   返回 C2PA manifest 或 None（无声明）
├── parse_exif(image_path: Path) -> dict
│   返回关键 EXIF 字段：
│   {software, artist, make, model, datetime, gps_lat, gps_lon,
│    ai_tags: [...]}  # 如 "Created with DALL-E" 等
├── 检测优先级：C2PA > EXIF AI tags > 无元数据
└── 结果不带硬性结论，仅展示元数据内容
```

### 4.6 OpenCLI 服务 (`opencli_service.py`)
```
调用方式：subprocess 执行 opencli CLI（不是 CDP 直连，不是 Selenium）

├── fetch_images_from_url(url: str, timeout: int = 30) -> list[Path]
│   流程：
│   1. 复制 Chrome profile：E:\chrome → %TEMP%\opencli_profile_{uuid}
│      （避免污染用户主 profile，任务结束自动删除）
│   2. subprocess 启动 Chrome 并导航：
│      opencli browser open <url> --profile %TEMP%\opencli_profile_{uuid}
│      参数：--no-first-run --disable-sync --disable-extensions
│   3. opencli extract 获取页面所有 <img> + background-image URL
│      使用 CDP (Chrome DevTools Protocol) 内置能力
│   4. 逐一下载图片到 %TEMP%\opencli_images_{uuid}\
│   5. 关闭 Chrome 标签页，返还本地路径列表
├── 按输入 URL 顺序依次处理，不并行（避免 Chrome 实例冲突）
├── 超时控制：
│   - 单 URL 导航超时：30s（opencli 内置）
│   - 单张图片下载超时：10s
│   - 总 URL 批处理超时：5min
├── 失败重试：单 URL 失败重试 1 次（仅网络错误，HTTP 4xx/5xx 不重试）
└── 安全措施：
    - URL scheme 仅允许 http/https（拒绝 file://、javascript: 等）
    - 子进程调用用 shlex.quote() 包裹参数
    - 临时目录任务结束立即清理
    - opencli 在沙箱模式运行（--sandbox），禁止文件系统写入外部目录
```

## 5. API 设计

| 方法 | 路径 | 说明 | 请求体 |
|------|------|------|--------|
| GET | `/` | 主页面 | — |
| POST | `/api/embed` | 嵌入水印 | multipart: files[], text, mode(uniform\|mapped), mapping_csv? |
| POST | `/api/extract` | 提取水印 | multipart: files[] |
| POST | `/api/detect` | AI 检测 | multipart: files[] |
| POST | `/api/url-detect` | URL 图片检测 | JSON: {urls: string[]} |
| GET | `/api/task/{id}/stream` | SSE 进度流 | — |
| POST | `/api/task/{id}/cancel` | 取消任务 | — |
| POST | `/api/task/{id}/pause` | 暂停/恢复 | JSON: {action: "pause"\|"resume"} |
| GET | `/api/download/{id}` | 下载结果 zip | — |

**任务模型（JSON）：**
```json
{
  "task_id": "uuid",
  "type": "embed | extract | detect | url-detect",
  "status": "pending | running | paused | completed | cancelled | failed",
  "progress": { "current": 0, "total": 10, "filename": "img005.jpg" },
  "results": [{"filename": "a.jpg", "status": "success", "output": "a_wm.jpg"}],
  "errors": [{"filename": "b.jpg", "error_code": 2, "error": "unsupported format"}],
  "skipped": [{"filename": "c.bmp", "reason": "unsupported_format"}],
  "created_at": "ISO8601",
  "stats": {"success": 0, "skipped": 0, "failed": 0}
}
```

## 6. 索引映射详细规则

### 6.1 三种输入方式（优先级：手动编辑 > CSV > 文件名匹配）
1. **手动编辑**：UI 列表逐行输入，支持从剪贴板批量粘贴（TSV 格式）
2. **CSV 导入**（UTF-8 编码，无 BOM）：
   ```csv
   filename,watermark_text
   img001.jpg,"机密文档-2024"
   img002.jpg,"内部使用-项目Alpha"
   ```
   列名识别：`filename`/`file`/`name` 列 + `text`/`watermark`/`content` 列
3. **文件名匹配**：同名 `.txt` 文件，如 `img001.jpg` → `img001.txt`，读取第一行作为水印文本

### 6.2 对齐规则
- 图片按文件名（含扩展名）升序排列，0-based 索引号作为后备
- CSV/mapping 中文件名与图片文件名的匹配：**精确匹配（含扩展名）**
- 找不到匹配时回退到忽略扩展名匹配

### 6.3 异常处理
| 情况 | 处理 |
|------|------|
| 映射缺失（图片无对应文本） | 标记为 skipped，reason="no_mapping"，不执行嵌入 |
| 映射重复（同一图片多条文本） | 取第一条，警告日志记录 |
| 文本过长（>1024字符） | 截断至 1024 字符，前端警告提示 |
| 文本为空字符串 | 标记错误，error_code=5 |

## 7. 批量处理模式（非功能性约束）

| 约束项 | 值 |
|--------|-----|
| 单次最大文件数 | 1000 张 |
| 单文件最大大小 | 50MB |
| 单次上传总大小 | 500MB |
| ZIP 解压后总大小 | 2GB |
| 图片最大像素 | 89478485（≈4K），超大图等比缩放 |
| 并发水印嵌入/提取 | 4 线程（ThreadPoolExecutor） |
| 并发 AI 检测 | 串行（SPAI 单 GPU 限制） |
| 并发 URL 检测 | 串行（Chrome 单实例限制） |
| 任务超时（总） | 30 分钟 |
| 单张水印超时 | 嵌入 60s / 提取 30s |
| opencli URL 超时 | 导航 30s / 图片下载 10s |

## 8. UI 状态管理

### 8.1 标签页行为
- 两个标签页（A:嵌入 B:提取）由客户端 JS 控制显示/隐藏，不刷新页面
- 任务队列全局共享：同一时间最多 1 个活跃任务
- 新任务提交时若已有任务运行：前端弹窗确认"是否等待当前任务完成？"
- 切换标签页不中断运行中的任务
- 当前活跃任务的状态通过 SSE 推送到两个标签页

### 8.2 预览与缩略图
- 文件选择后生成缩略图列表（前端用 `URL.createObjectURL` 实现）
- 缩略图尺寸：200×200 固定，CSS `object-fit: cover`
- 不发送到后端处理（避免额外上传开销）
- 处理完成后，结果图支持点击放大查看（Modal 弹窗）

### 8.3 进度反馈
- SSE 推送 `{current, total, filename, status}` 事件
- 前端渲染进度条 + 当前处理文件名
- 暂停时进度条变黄色；取消时变灰色
- 完成后显示统计摘要 + 下载按钮

## 9. 验证逻辑详细说明

### 9.1 水印文本对比（标签页 B）
- **基准文本来源（优先级）**：
  1. 手动输入（文本框）
  2. CSV 导入（`filename,expected_text`）
  3. 同名 `.txt` 文件
- **对比粒度**：行级（整条提取文本 vs 基准文本）
- **匹配规则**：完全字符串匹配（大小写敏感），可选"忽略空白"开关
- **可视化**：表格行背景色
  - 🟢 绿色：完全匹配
  - 🔴 红色：不匹配（显示差异文本）
  - ⬜ 灰色：图片中无水印，不参与对比
  - 🟡 黄色：提取置信度 < 0.5，即使匹配也标记低置信
- **部分匹配时**：显示提取文本、预期文本、编辑距离（Levenshtein）

### 9.2 AI 检测结果展示
| 字段 | 展示形式 |
|------|----------|
| ai_score | 数值 + 颜色渐变条形图（绿0-红1） |
| verdict | 标签徽章："真实"(绿) / "AI生成"(红) / "不确定"(黄) |
| spectral_mse | 数值，鼠标悬停显示解释："频谱重建误差，越低越接近真实图像分布" |
| ring_anomaly | >0.6 时显示 ⚠️ "频环异常" |
| synthid_flag | true 时显示 ⚠️ "频谱异常信号" |
| c2pa | 徽章：✅"有声明" / ❌"无" / ⬜"不支持" |

## 10. 输出规范

| 场景 | 命名规则 |
|------|----------|
| 嵌入单张 | `{原文件名}_wm.{ext}` |
| 提取结果 CSV | `{原文件名}_result.csv` |
| 批量打包 | `watermark_result_{YYYYMMDD-HHMMSS}.zip` |
| 错误日志 | `errors.csv`（列: filename, error_code, error_message） |
| 跳过列表 | `skipped.csv`（列: filename, reason） |
| AI 检测汇总 | `ai_detection_summary.csv`（列: filename, ai_score, verdict, c2pa, ring_anomaly, synthid_flag） |
| 重名处理 | 自动追加 `_1`, `_2` 后缀，不覆盖 |

## 11. 文件处理

### 支持格式
| 格式 | 嵌入 | 提取 | 检测 | 扩展名 |
|------|------|------|------|--------|
| JPEG | ✅ | ✅ | ✅ | .jpg .jpeg |
| PNG | ✅ | ✅ | ✅ | .png |
| WebP | ✅ | ✅ | ✅ | .webp |
| BMP | ✅ | ✅ | ✅ | .bmp |
| TIFF | ⚠️ 转PNG | ⚠️ 转PNG | ✅ | .tiff .tif |
| SVG | ❌ | ❌ | ❌ | .svg |
| GIF | ❌ | ❌ | ❌ | .gif |
| 其他 | ❌ 跳过 | ❌ 跳过 | ❌ 跳过 | — |

- ⚠️ TIFF：自动转换为 PNG 后再处理，原 TIFF 不做修改
- 不支持格式记录到 `skipped.csv`，前端黄色警告显示数量

### 图片尺寸限制
- 最大像素数：`PIL.Image.MAX_IMAGE_PIXELS` (89M ≈ 4K)
- 超大图自动等比缩放至最长边 4096px
- 缩放日志记录到 `errors.csv`（reason="downscaled"）

## 12. 进度与错误处理

### SSE 事件类型
```
event: progress
data: {"current":5,"total":20,"filename":"img005.jpg","status":"embedding"}

event: paused
data: {"current":5,"total":20,"reason":"user_requested"}

event: resumed
data: {"current":5,"total":20}

event: cancelled
data: {"current":5,"total":20,"reason":"user_requested"}

event: error
data: {"filename":"img_x.jpg","error_code":2,"error":"unsupported format"}

event: complete
data: {"success":18,"skipped":1,"failed":1,"download_url":"/api/download/xxx"}
```

### 错误恢复与日志
- 单张失败不影响后续处理
- 最终报告统计三类：成功/跳过/失败
- 所有操作日志写入 `logs/app.log`（按天轮转，保留 7 天）
- 日志级别：批量操作为 INFO，单张错误为 WARNING，系统错误为 ERROR
- 前端显示实时错误计数（红色角标）

### 暂停/取消
- 暂停：当前图片处理完成后挂起，已处理结果保留
- 恢复：从下一张未处理的图片继续
- 取消：立即停止，已处理结果保留可下载
- 实现：`asyncio.Event` 检查点 + 前端按钮状态切换

## 13. 安全措施

| 风险 | 等级 | 措施 |
|------|------|------|
| **路径遍历** — 用户输入含 `../` 逃逸 | 🔴HIGH | `pathlib.resolve()` 校验，结果必须在 `UPLOAD_DIR` 范围内 |
| **Shell 注入** — opencli URL 参数字符 | 🔴HIGH | URL scheme 仅 http/https；`shlex.quote()` 包裹所有子进程参数；`subprocess.run(shell=False)` |
| **SSRF** — 通过 URL 检测访问内网 | 🔴HIGH | URL 解析后检查 IP，拒绝私有/内网地址（10.x, 172.16-31.x, 192.168.x, 127.x, [::1]） |
| **Chrome profile 泄露** — Cookie/凭证 | 🟡MED | 每次任务复制临时 profile，任务结束删除；原 profile 只读 |
| **文件覆盖** — 输出重名静默覆盖 | 🟡MED | 检测重名自动追加 `_1`, `_2`，不覆盖 |
| **图片炸弹** — 压缩炸弹/像素炸弹 | 🟡MED | 上传限制 500MB；解压限制 2GB；`MAX_IMAGE_PIXELS` 限制；拒绝 0×0 和 >65536×65536 |
| **EXIF 隐私泄露** — GPS/相机信息 | 🟡MED | 处理结果的 EXIF 信息默认清除，可选保留；前端提示原始图含 GPS 时显示警告 |
| **临时文件残留** — 磁盘泄露 | 🟡LOW | 所有 tmp 文件写入 `%TEMP%\watermark_tool\`，任务结束或服务关闭时 `shutil.rmtree` 清理 |
| **CSV 注入** — 恶意公式 | 🟡LOW | CSV 输出时，以 `=`/`+`/`-`/`@` 开头的字段加单引号前缀 `'` |

## 14. 数据存储与隐私

| 项目 | 策略 |
|------|------|
| 上传图片存储 | `%TEMP%\watermark_tool\uploads\{task_id}\`，任务完成后 1 小时自动删除 |
| 处理结果存储 | `%TEMP%\watermark_tool\results\{task_id}\`，下载后或 24 小时后自动删除 |
| Chrome profile 副本 | `%TEMP%\watermark_tool\chrome_profiles\{task_id}\`，任务结束立即删除 |
| opencli 下载图片 | `%TEMP%\watermark_tool\opencli_images\{task_id}\`，任务结束立即删除 |
| 日志文件 | `logs/app.log`，按天轮转，保留 7 天 |
| 用户配置 | `config.yaml`，不含密码/密钥 |

## 15. 验收标准

| # | 标准 | 量化指标 |
|---|------|----------|
| 1 | 批量嵌入 100 张 JPEG (1024×1024) | 总耗时 < 5 分钟，成功率 > 99% |
| 2 | 批量提取 100 张带水印图 | 提取准确率 > 95%（与嵌入文本完全匹配） |
| 3 | 内存峰值 | 100 张批量处理时 < 2GB |
| 4 | opencli URL 超时 | 30s 后自动终止，返回明确错误码 |
| 5 | opencli URL 无响应 | 重试 1 次后标记 failed，不阻塞后续 URL |
| 6 | SPAI 检测准确率 | 预置 10 张测试集（5真+5AI），AUC > 0.85 |
| 7 | 取消操作响应 | 点击取消后 5s 内当前图片处理完成并停止 |
| 8 | 不支持格式 | 自动跳过并记录 skipped.csv，不崩溃 |
| 9 | 路径遍历攻击 | 所有路径解析被拒绝，返回 403 |
| 10 | 内网 SSRF | 私有 IP URL 被拒绝，返回 400 |
| 11 | TIFF 兼容 | 自动转 PNG 处理，结果与原图对比验证 |
| 12 | 文件覆盖保护 | 重名文件自动重命名，无数据丢失 |
| 13 | 单文件 > 50MB | 前端拦截 + 后端校验，返回 413 |
| 14 | 空文件导入 | 前端提示"无可处理的图片"，不发起 API 请求 |

## 16. 目录结构

```
watermark/
├── main.py                    # 应用入口（uvicorn 启动）
├── pyproject.toml
├── config.yaml                # 应用配置
│   # chrome_path: "E:\\chrome"
│   # upload_max_size_mb: 500
│   # max_files_per_batch: 1000
│   # log_level: "INFO"
│   # log_retention_days: 7
├── watermark_app/
│   ├── __init__.py
│   ├── main.py                # FastAPI app 工厂 + 生命周期
│   ├── config.py              # 配置加载（YAML + 环境变量覆盖）
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── embed.py
│   │   ├── extract.py
│   │   └── detect.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── watermark_service.py   # blind-watermark 封装
│   │   ├── spai_service.py        # SPAI 频谱检测
│   │   ├── ring_detector.py       # Tree-Ring 频环检测
│   │   ├── c2pa_service.py        # C2PA/EXIF 元数据
│   │   └── opencli_service.py     # opencli subprocess 封装
│   ├── models/
│   │   ├── __init__.py
│   │   ├── task.py                # 任务数据模型 + 状态机
│   │   └── results.py             # EmbedResult, ExtractResult, DetectResult
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html
│   │   └── components/            # htmx 局部刷新组件
│   │       ├── file_list.html
│   │       ├── progress_bar.html
│   │       └── result_table.html
│   └── static/
│       ├── htmx.min.js
│       └── app.js
├── watermark_tools/           # 外部工具目录（已有）
│   ├── spai-main/             # SPAI 检测引擎
│   └── node_modules/          # opencli
├── tests/
│   ├── test_watermark_service.py
│   ├── test_spai_service.py
│   ├── test_opencli_service.py
│   ├── test_api.py
│   └── conftest.py            # fixtures（测试图片、mock opencli）
└── logs/                      # 运行时日志（.gitignore）
```

## 17. 测试策略

| 层级 | 工具 | 覆盖内容 |
|------|------|----------|
| 单元测试 | pytest | 各 service 函数，mapping 规则，错误码转换 |
| 集成测试 | pytest + httpx | FastAPI TestClient，完整 API 流程（上传→处理→下载） |
| SPAI 测试 | 预置 10 张（5真+5AI） | AUC > 0.85，单张推理 < 5s |
| opencli 测试 | mock `subprocess.run` | URL 校验、超时、重试、profile 清理逻辑 |
| 安全测试 | pytest 参数化 | 路径遍历 payload、SSRF IP 列表、Shell 注入字符串 |
| 验收测试 | 按 §15 逐条验证 | 手动执行或 CI 脚本 |

---

## 审计修订记录 (v2)

根据外部审查意见（10条），v2 新增/修订：

| # | 审查意见 | 修订内容 | 所在章节 |
|---|----------|----------|----------|
| 1 | 日期笔误 | 确认 2026-06-21 为实际创建日期，非笔误 | 头部 |
| 2 | prompt 协议未定义 | 新增完整函数签名、参数、错误返回码、超时 | §2 |
| 3 | 索引映射模糊 | 新增对齐规则、匹配优先级、异常处理表 | §6 |
| 4 | AI 检测标准缺失 | 新增置信度阈值、多标准并行、结果展示格式、低置信处理 | §4.2-4.5, §9.2 |
| 5 | OpenCLI 细节缺失 | 明确 subprocess 方式、profile 隔离机制、启动参数、超时、重试、安全措施 | §4.6 |
| 6 | 非功能性需求缺失 | 新增完整 NFR 约束表、暂停/取消机制、日志轮转 | §7, §12 |
| 7 | UI 状态管理未定义 | 新增标签页行为、缩略图策略、SSE 广播、任务队列共享规则 | §8 |
| 8 | 验证高亮缺乏定义 | 新增对比粒度、匹配规则、颜色编码、部分匹配处理 | §9.1 |
| 9 | 安全与隐私缺失 | 新增数据存储策略、临时文件清理、SSRF 防护、EXIF 处理 | §13, §14 |
| 10 | 验收标准缺失 | 新增 14 条量化验收标准 | §15 |
