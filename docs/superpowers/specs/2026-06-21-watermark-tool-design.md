# Watermark Tool — 批量水印 + AI 检测 设计文档 (v3)

**日期**: 2026-06-21
**状态**: 设计中
**技术栈**: Python 3.14, FastAPI, Jinja2 + htmx, blind-watermark, SPAI, opencli

---

## 1. 项目目标

构建一个 Web 应用，提供：
- **标签页 A（嵌入水印）**: 图片 + 文本 → 盲水印嵌入（单张/批量）
- **标签页 B（提取/验证）**: 带水印图片 → 水印文本提取 + AI 生成检测

## 2. watermark 调用协议

`watermark` 的实质是 `blind-watermark` Python 库的本地函数调用。

### 2.1 算法参数与鲁棒性

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `strength` | 0.8 | 嵌入强度（0.1-1.0），越高越抗攻击但可见度增加 |
| `domain` | `"dwt"` | 频域选择：`dwt`（离散小波变换）/ `dct`（离散余弦变换） |
| `password` | `""` | 可选加密密码，用于水印置乱和提取验证 |
| `wm_length` | 自动 | 水印文本长度决定，最长 1024 字符 |

**鲁棒性目标：**

| 攻击类型 | 目标 | 验证方法 |
|----------|------|----------|
| JPEG 压缩 (quality≥70) | 提取准确率 > 90% | 嵌入后压缩 → 提取 → 对比 |
| 缩放 (≥50%) | 提取准确率 > 80% | Pillow resize → 提取 → 对比 |
| 裁剪 (保留 ≥75%) | 提取准确率 > 70% | 中心裁剪 75% → 提取 → 对比 |
| 旋转 (±5°) | 提取准确率 > 60% | Pillow rotate → 提取 → 对比 |
| 无损格式转换 (PNG→JPEG→PNG) | 提取准确率 > 85% | 格式转换 → 提取 → 对比 |

### 2.2 嵌入接口

```python
def embed_watermark(
    image_path: Path,
    text: str,
    password: str = "",
    strength: float = 0.8,
    domain: Literal["dwt", "dct"] = "dwt",
    output_path: Path | None = None
) -> EmbedResult:
    """
    返回:
      EmbedResult:
        success: bool
        output_path: Path
        error: str | None          # 失败原因（字符串错误码，见 §2.4）
        elapsed_ms: int
    异常: 不抛出，全部捕获到 EmbedResult.error
    超时: 单张 60s，超时返回 error="WATERMARK_TIMEOUT"
    """
```

### 2.3 提取接口

```python
def extract_watermark(
    image_path: Path,
    password: str = ""
) -> ExtractResult:
    """
    返回:
      ExtractResult:
        success: bool
        text: str | None           # 无水印时为 None, error="WATERMARK_NOT_FOUND"
        confidence: float          # 0-1
        error: str | None
        elapsed_ms: int
    超时: 单张 30s
    """
```

### 2.4 错误码（字符串语义码）

| 错误码 | 含义 | 触发条件 |
|--------|------|----------|
| `SUCCESS` | 成功 | — |
| `FILE_NOT_FOUND` | 文件不存在/无法读取 | `Path.exists()` 为 false |
| `FORMAT_UNSUPPORTED` | 格式不支持 | 扩展名不在支持列表 |
| `WATERMARK_NOT_FOUND` | 图片中未检测到水印 | 提取置信度 < 阈值 |
| `WATERMARK_TIMEOUT` | 处理超时 | 嵌入 > 60s / 提取 > 30s |
| `WATERMARK_TEXT_TOO_LONG` | 水印文本过长 | len(text) > 1024 |
| `WATERMARK_TEXT_EMPTY` | 水印文本为空 | text == "" |
| `IMAGE_TOO_LARGE` | 图片尺寸超限 | 像素数 > MAX_IMAGE_PIXELS |
| `IMAGE_CORRUPTED` | 图片文件损坏 | PIL 无法打开 |
| `INTERNAL_ERROR` | 未知内部错误 | 未预期的异常 |

**扩展规则**: 新增错误码按 `CATEGORY_DETAIL` 命名，用下划线分隔，不超过 64 字符。

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

**核心原则（v3 修订）：**
- 单进程 FastAPI，htmx + SSE + REST 兜底（SSE 断线时查询 REST API 获取状态）
- SPAI 推理单张串行，避免 GPU 内存溢出
- opencli URL 检测按输入顺序依次执行，Chrome 单实例

### 3.1 任务队列架构（v3 修订）

**放弃单队列设计，改为类型分离 + 可配置并发：**

```
用户提交 → 任务路由器
            │
            ├── embed 队列（并发数: min(4, cpu_count)）
            ├── extract 队列（并发数: min(4, cpu_count)）
            ├── detect 队列（并发数: 1，GPU 限制）
            └── url-detect 队列（并发数: 1，Chrome 实例限制）

- 不同队列独立运行，不互相阻塞
- 同类型队列内按 FIFO + priority 排序
- 用户可提交任务到任一队列，即使另一队列正在处理
- 每个队列独立显示排队长度，前端展示"队列中 N 个任务"
```

## 4. 模块设计

### 4.1 水印服务 (`watermark_service.py`)

```
封装 blind-watermark 库：
├── embed_batch(images, mapping, mode, params) -> BatchResult
│   参数: strength=0.8, domain="dwt", password=""
├── extract_batch(images, password="") -> BatchResult
├── verify_robustness(original, watermarked, attack) -> RobustnessReport
│   攻击类型: jpeg_compress(70), resize(0.5), crop(0.75), rotate(5)
└── 索引映射规则（详见 §6）
```

### 4.2 SPAI 频谱检测 (`spai_service.py`)

```
├── detect_ai(image_path: Path) -> DetectResult
│   返回字段见下表
├── 基于 spai-main 的 __main__.py infer 流程
├── 单张推理，GPU 内存友好
└── 置信度阈值:
    - ai_score >= 0.7 → verdict="likely_ai"
    - ai_score <= 0.3 → verdict="likely_real"
    - 0.3 < ai_score < 0.7 → verdict="uncertain"
```

### 4.3 Tree-Ring 频环检测 (`ring_detector.py`)

```
策略：频谱环带异常检测（约 50 行新增代码）
├── 基于 SPAI filters.py 的 filter_image_frequencies() 输出
├── 计算 3 个半径频环的能量峰值偏离度
├── 与基线数据对比（基线详见 §4.7）
├── 输出 ring_anomaly_score（0-1），>= 0.6 标记异常
└── 注解：非硬性判定，仅作为辅助信号
```

### 4.4 SynthID 降级策略

```
策略：频谱泛化 + 异常检测
├── 复用 SPAI 频谱重建 MSE
├── 与基线 MSE 分布对比（KDE + Z-score，α=0.05）
├── |Z| > 1.96 标记 synthid_flag=true
└── 最终输出文本描述，非硬性判定
```

### 4.5 C2PA 元数据 (`c2pa_service.py`)

```
├── parse_c2pa(image_path) -> dict | None
├── parse_exif(image_path) -> dict
│   {software, artist, make, model, datetime, gps_lat, gps_lon, ai_tags: [...]}
├── 检测优先级：C2PA > EXIF AI tags > 无元数据
└── 结果不输出硬性结论，仅展示元数据
```

### 4.6 OpenCLI 服务 (`opencli_service.py`)

```
调用方式：subprocess 执行 opencli CLI（非 CDP 直连，非 Selenium）

Chrome 路径策略（v3 新增 fallback）:
  1. config.yaml 的 chrome_path（显式配置，优先级最高）
  2. 环境变量 CHROME_PATH
  3. 自动探测（按顺序尝试）:
     Windows: C:\Program Files\Google\Chrome\Application\chrome.exe
              C:\Program Files (x86)\Google\Chrome\Application\chrome.exe
              %LOCALAPPDATA%\Google\Chrome\Application\chrome.exe
     Linux:   /usr/bin/google-chrome
     macOS:   /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
  4. 以上均失败 → 服务启动时打印 WARNING 日志，OpenCLI 功能在 UI 显示 "Chrome 未安装"提示

├── fetch_images_from_url(url: str, timeout: int = 30) -> list[Path]
│   流程:
│   1. 复制 Chrome profile 到临时目录（隔离）
│   2. subprocess: opencli browser open <url> --profile <tmp>
│      参数: --no-first-run --disable-sync --no-default-browser-check
│   3. opencli extract 获取页面图片 URL
│   4. 下载到临时目录，返回本地路径
├── 超时: 导航 30s / 下载 10s / 总批 5min
├── 重试: 网络错误重试 1 次，HTTP 4xx/5xx 不重试
└── 安全: URL scheme 白名单，shlex.quote(), SSRF 防护
```

### 4.7 基线数据规范（v3 新增）

```
基线数据集（100 张真实图像）用于 Tree-Ring 频环检测和 SynthID 异常检测：

来源:
  - COCO 2017 val 随机采样 50 张（自然场景，多样性高）
  - LSUN bedroom 随机采样 30 张（室内场景）
  - MIT Places 随机采样 20 张（场景多样性）
采集标准:
  - 分辨率 ≥ 512×512，JPEG quality ≥ 90
  - 无任何后期处理（Lightroom/Photoshop 痕迹）
  - EXIF 中不含 AI 生成软件标签
  - 每一张检查通过 SPAI 检测确保 ai_score < 0.3
存储:
  - 分布式: 仅存储每张图片的频谱特征向量（~4KB/张），不存原图
  - 路径: watermark_tools/spai-main/data/baseline_features.npz
更新机制:
  - 首次启动时自动计算（约 3 分钟），结果缓存到 .npz
  - 配置项 baseline.update_on_startup: true/false（默认 false，仅首次）
用户自定义基线:
  - 提供脚本: python -m watermark_app.update_baseline --input <dir>
  - 用户提供 50-200 张"正常"图片即可重新计算基线
  - 新基线覆盖旧 .npz 文件
```

## 5. API 设计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 主页面 |
| POST | `/api/embed` | 嵌入水印（multipart） |
| POST | `/api/extract` | 提取水印（multipart） |
| POST | `/api/detect` | AI 检测（multipart） |
| POST | `/api/url-detect` | URL 检测（JSON） |
| GET | `/api/task/{id}/stream` | SSE 进度流 |
| GET | `/api/task/{id}/status` | REST 状态查询（SSE 兜底，v3 新增） |
| POST | `/api/task/{id}/cancel` | 取消任务 |
| POST | `/api/task/{id}/pause` | 暂停/恢复 |
| GET | `/api/download/{id}` | 下载结果 zip |

**任务模型（v3 更新错误码字段）：**
```json
{
  "task_id": "uuid",
  "type": "embed | extract | detect | url-detect",
  "queue": "embed | extract | detect | url-detect",
  "priority": 0,
  "status": "pending | running | paused | completed | cancelled | failed",
  "progress": { "current": 0, "total": 10, "filename": "img005.jpg" },
  "results": [{"filename": "a.jpg", "status": "success", "output": "a_wm.jpg"}],
  "errors": [{"filename": "b.jpg", "error_code": "FORMAT_UNSUPPORTED", "error": "unsupported format"}],
  "skipped": [{"filename": "c.bmp", "reason": "unsupported_format"}],
  "created_at": "ISO8601",
  "queue_position": 3,
  "stats": {"success": 0, "skipped": 0, "failed": 0}
}
```

## 6. 索引映射详细规则

### 6.1 三种输入方式（优先级：手动编辑 > CSV > 文件名匹配）
1. **手动编辑**：UI 列表逐行输入，支持剪贴板批量粘贴（TSV）
2. **CSV 导入**（UTF-8 无 BOM）：
   ```csv
   filename,watermark_text
   img001.jpg,"机密文档-2024"
   ```
   列名: `filename`/`file`/`name` + `text`/`watermark`/`content`
3. **文件名匹配**：`img001.jpg` → `img001.txt`，读取第一行

### 6.2 对齐规则
- 图片按文件名（含扩展名）升序，0-based 索引为后备
- CSV 文件名匹配：精确匹配（含扩展名）→ 回退忽略扩展名

### 6.3 异常处理
| 情况 | 处理 |
|------|------|
| 映射缺失 | skipped，reason="no_mapping" |
| 映射重复 | 取第一条，WARNING 日志 |
| 文本 > 1024 字符 | 截断至 1024，前端警告 |
| 文本为空 | error_code="WATERMARK_TEXT_EMPTY" |

## 7. 批量处理非功能性约束

| 约束项 | 值 |
|--------|-----|
| 单次最大文件数 | 1000 张 |
| 单文件最大大小 | 50MB |
| 单次上传总大小 | 500MB |
| ZIP 解压后总大小 | 2GB，解压时监控内存，超过阈值分批处理 |
| 图片最大像素 | 89478485（≈4K），超大图等比缩放 |
| embed/extract 并发 | min(4, cpu_count) 线程 |
| detect 并发 | 1（GPU 限制） |
| url-detect 并发 | 1（Chrome 限制） |
| 任务超时（总） | 30 分钟 |
| 单张水印超时 | 嵌入 60s / 提取 30s |
| opencli URL 超时 | 导航 30s / 下载 10s |

## 8. UI 状态管理（v3 修订）

### 8.1 标签页与任务队列
- 两个标签页各自提交到独立队列，不互相阻塞
- 每个标签页前端独立显示自身队列的排队状态
- 新任务可随时提交，无需等待其他队列完成
- 切换标签页不中断运行中的任务
- SSE 按 task_id 过滤，每个标签页只订阅自己的任务事件

### 8.2 预览与缩略图（v3 修订：Blob URL 生命周期）
- 文件选择后用 `URL.createObjectURL()` 生成缩略图
- **生命周期管理**：
  - 文件列表更新时：对旧 URL 调用 `URL.revokeObjectURL()`
  - 组件销毁时（标签页切换/页面卸载）：遍历所有 Blob URL 并 revoke
  - 缩略图最大内存占用：1000 张 × 200×200 ≈ 40MB（可接受上限）
  - 超过 500 张时自动切换为"仅文件名列表"模式，不生成缩略图
- 缩略图尺寸：200×200，CSS `object-fit: cover`
- 处理完成后结果图支持 Modal 放大查看
- 批量 > 500 张时自动关闭缩略图渲染，切换到文本列表模式

### 8.3 进度反馈
- SSE 推送 + REST 轮询兜底（每 5s 轮询 `/api/task/{id}/status`）
- 暂停/取消按钮状态随任务状态切换

## 9. 验证逻辑详细说明

### 9.1 水印文本对比（标签页 B）
- **基准文本来源（优先级）**：手动输入 > CSV > 同名 .txt
- **对比粒度**：行级（整条提取文本 vs 基准文本）
- **匹配规则**：完全字符串匹配（大小写敏感），可选"忽略空白"
- **可视化**：
  - 🟢 绿色：完全匹配
  - 🔴 红色：不匹配（显示差异 + Levenshtein 距离）
  - ⬜ 灰色：无水印，不参与对比
  - 🟡 黄色：置信度 < 0.5，即使匹配也标记

### 9.2 AI 检测结果展示
| 字段 | 展示形式 |
|------|----------|
| ai_score | 数值 + 颜色渐变条（绿 0 ↔ 红 1） |
| verdict | 徽章："真实"/"AI生成"/"不确定" |
| ring_anomaly | >0.6 时 ⚠️ "频环异常" |
| synthid_flag | true 时 ⚠️ "频谱异常信号" |
| c2pa | ✅"有声明" / ❌"无" / ⬜"不支持" |

## 10. 输出规范

| 场景 | 命名规则 |
|------|----------|
| 嵌入单张 | `{原文件名}_wm.{ext}` |
| 提取结果 CSV | `{原文件名}_result.csv` |
| 批量打包 | `watermark_result_{YYYYMMDD-HHMMSS}.zip` |
| 错误日志 | `errors.csv`（filename, error_code, error_message） |
| 跳过列表 | `skipped.csv`（filename, reason） |
| AI 检测汇总 | `ai_detection_summary.csv` |
| 重名处理 | 自动追加 `_1`, `_2`，不覆盖 |

## 11. 文件处理

### 支持格式（同 v2）
| 格式 | 嵌入 | 提取 | 检测 |
|------|------|------|------|
| JPEG/PNG/WebP/BMP | ✅ | ✅ | ✅ |
| TIFF | ⚠️转PNG | ⚠️转PNG | ✅ |
| SVG/GIF/其他 | ❌ | ❌ | ❌ |

## 12. 进度与错误处理（v3 修订）

### SSE + REST 双通道（v3 新增）
- **SSE 主通道**: 实时推送进度事件
- **REST 兜底**: `GET /api/task/{id}/status` 返回任务完整状态
- **SSE 心跳**: 每 15 秒发送 `event: heartbeat`，客户端 45 秒无事件则触发重连
- **客户端重连**: `EventSource` 自动重连 + 手动重连指数退避（1s/2s/4s/8s，最大 30s）
- **重连后补偿**: 重连成功 → 调用 REST API 获取最新状态 → 继续 SSE 监听

### SSE 事件类型
```
event: heartbeat
data: {"timestamp":"ISO8601"}

event: progress
data: {"current":5,"total":20,"filename":"img005.jpg","status":"embedding"}

event: paused / resumed / cancelled
event: error
data: {"filename":"x.jpg","error_code":"FORMAT_UNSUPPORTED","error":"..."}

event: complete
data: {"success":18,"skipped":1,"failed":1,"download_url":"/api/download/xxx"}
```

### 日志与隐私脱敏（v3 修订）

**日志脱敏规则：**

| 字段类型 | 策略 | 示例 |
|----------|------|------|
| 文件名 | ✅ 允许 | `img001.jpg` |
| 文件路径（完整） | ❌ 禁止 | 仅记录 `filename`，不记录完整路径 |
| 水印文本内容 | ❌ 禁止 | 仅记录长度 `len=12` |
| URL 地址 | ❌ 禁止 | 仅记录域名 `example.com` |
| IP 地址 | ❌ 禁止 | 仅记录 `remote_addr=REDACTED` |
| 错误堆栈 | ⚠️ 仅 WARNING+ | 单张处理错误不记录堆栈，仅 ERROR 级别记录 |
| 任务 ID | ✅ 允许 | `task_id=uuid` |

**日志轮转**: 按天 + 按大小（10MB），保留 7 天

### 暂停/取消
- 暂停：当前图片完成后挂起
- 恢复：从下一张未处理的继续
- 取消：立即停止，已处理结果保留
- 实现：`asyncio.Event` 检查点

## 13. 安全措施（v3 修订）

| 风险 | 等级 | 措施 |
|------|------|------|
| 路径遍历 | 🔴HIGH | `pathlib.resolve()` + 白名单目录校验 |
| Shell 注入 | 🔴HIGH | URL scheme 仅 http/https；`shlex.quote()`；`subprocess.run(shell=False)` |
| SSRF | 🔴HIGH | 解析 URL IP，拒绝私有/内网地址 |
| Chrome profile 泄露 | 🟡MED | 临时 profile 副本，任务结束删除 |
| 文件覆盖 | 🟡MED | 重名自动加后缀 |
| 图片炸弹 | 🟡MED | 上传 500MB 限制；解压 2GB；MAX_IMAGE_PIXELS；拒绝 0×0 和 >65536×65536 |
| EXIF 隐私 | 🟡MED | 结果图默认清除 EXIF，可选保留 |
| 临时文件残留 | 🟡LOW | 统一写入 `%TEMP%\watermark_tool\`，任务结束或服务关闭时清理 |
| **CSV 注入（v3 强化）** | 🟡MED | 使用 `csv.writer(quoting=csv.QUOTE_ALL)`；对所有字段自动转义 `=` `+` `-` `@` `\t` `\r` `\n` 字符；字符串开头危险字符前加单引号，中间字符用 `\` 转义 |
| **日志敏感信息** | 🟡MED | 见 §12 脱敏规则，禁止记录水印文本/URL/完整路径 |

## 14. 数据存储与隐私（v3 修订）

### 滑动过期策略（v3 修订）
放弃固定 1 小时/24 小时过期，改为基于最后访问时间的滑动窗口：

| 数据 | 存储位置 | 过期策略 |
|------|----------|----------|
| 上传图片 | `%TEMP%\watermark_tool\uploads\{task_id}\` | 最后一次下载/访问后 **1 小时** |
| 处理结果 | `%TEMP%\watermark_tool\results\{task_id}\` | 最后一次下载后 **24 小时** |
| Chrome profile | `%TEMP%\watermark_tool\chrome_profiles\{task_id}\` | 任务结束立即删除 |
| opencli 图片 | `%TEMP%\watermark_tool\opencli_images\{task_id}\` | 任务结束立即删除 |
| 日志 | `logs/app.log` | 轮转保留 7 天 |

**实现**: 后台定时任务每 5 分钟扫描过期目录并清理
**下载接口兜底**: 下载前检查文件是否存在，不存在返回 410 Gone + 友好提示"文件已过期，请重新处理"

## 15. 验收标准（v3 扩展）

| # | 标准 | 量化指标 |
|---|------|----------|
| 1 | 批量嵌入 100 张 JPEG (1024×1024) | 耗时 < 5min，成功率 > 99% |
| 2 | 批量提取 100 张 | 提取准确率 > 95% |
| 3 | 内存峰值 | 100 张处理时 < 2GB |
| 4 | opencli 超时 | 30s 终止，返回 `WATERMARK_TIMEOUT` |
| 5 | opencli 无响应 | 重试 1 次后标记 failed，不阻塞后续 |
| 6 | SPAI 检测 | 10 张测试集 AUC > 0.85 |
| 7 | 取消响应 | 5s 内当前图片处理完成并停止 |
| 8 | 不支持格式 | 跳过 + 记录 skipped.csv，不崩溃 |
| 9 | 路径遍历 | 所有攻击 payload 返回 403 |
| 10 | SSRF | 私有 IP URL 返回 400 |
| 11 | TIFF 兼容 | 自动转 PNG，结果验证 |
| 12 | 文件覆盖保护 | 重名自动重命名 |
| 13 | 单文件 > 50MB | 前端拦截 + 后端 413 |
| 14 | 空文件导入 | 前端提示，无 API 请求 |
| **15** | **JPEG 压缩鲁棒性** | quality=70 压缩后提取准确率 > 90% |
| **16** | **缩放鲁棒性** | 50% 缩放后提取准确率 > 80% |
| **17** | **多队列并发** | embed 100 张期间，extract 10 张独立执行，不等待 embed 完成 |
| **18** | **暂停恢复一致性** | 暂停后恢复，结果与不暂停完全一致（无重复、无遗漏） |
| **19** | **ZIP 解压内存** | 2GB ZIP 解压时内存峰值 < 4GB，超大 ZIP 分片处理 |
| **20** | **浏览器关闭清理** | 页面关闭后 30s 内 SSE 连接释放，任务继续运行不受影响 |
| **21** | **恶意 CSV** | `=cmd\|'/C calc'!A0` 等注入 payload 被转义，不执行公式 |
| **22** | **Blob URL 泄漏** | 1000 张图片场景，切换标签页后所有 Blob URL 被 revoke |
| **23** | **SSE 断线恢复** | SSE 断开后 15s 内心跳检测超时，30s 内完成重连 + 状态同步 |
| **24** | **Chrome 自动探测** | 无 config.yaml 时自动找到系统 Chrome，找不到时 UI 提示而非崩溃 |

## 16. 目录结构

（同 v2，无结构变更）

## 17. 测试策略（v3 扩展）

| 层级 | 工具 | 覆盖内容 |
|------|------|----------|
| 单元测试 | pytest | 各 service 函数，mapping 规则，错误码转换，**鲁棒性测试** |
| 集成测试 | pytest + httpx | API 流程，**多队列并发测试**，**暂停/恢复一致性** |
| SPAI 测试 | 10 张测试集 | AUC > 0.85，单张 < 5s |
| opencli 测试 | mock `subprocess.run` | URL 校验、超时、重试、**Chrome 路径探测** |
| 安全测试 | pytest 参数化 | 路径遍历、SSRF、Shell 注入、**CSV 注入 payload 集** |
| 前端测试 | **浏览器内存快照** | Blob URL 泄漏检查、缩略图 > 500 张切换逻辑 |
| 验收测试 | §15 逐条验证 | 手动 + CI 脚本 |

---

## 审计修订记录

### v3（当前版本）— 响应 11 条新增审查意见

| # | 审查意见 | 修订内容 | 章节 |
|---|----------|----------|------|
| 1 | 盲水印算法参数缺失 | 补充嵌入强度、频域选择、5 种攻击鲁棒性目标 | §2.1, §15 |
| 2 | 任务队列单点瓶颈 | 改为类型分离独立队列（embed/extract/detect/url-detect），并发可配置 | §3.1, §8.1 |
| 3 | SPAI 基线数据未定义 | 新增基线数据规范（来源/标准/存储/更新/用户自定义接口） | §4.7 |
| 4 | Chrome 路径硬编码 | 新增 4 级 fallback 自动探测链 + 失败降级提示 | §4.6 |
| 5 | SSE 断线可靠性 | 新增心跳(15s)、指数退避重连、REST API 兜底状态查询 | §12 |
| 6 | 文件删除竞态风险 | 改为基于最后访问时间的滑动过期策略 + 下载前文件存在性检查 | §14 |
| 7 | CSV 注入不完整 | 补充 `\t` `\r` `\n` 转义，使用 `csv.QUOTE_ALL`，白名单策略 | §13 |
| 8 | 验收标准缺边界测试 | 新增 10 条边界验收：鲁棒性、多队列并发、暂停一致性、ZIP 内存、恶意 CSV、Blob 泄漏等 | §15 |
| 9 | 错误码扩展性不足 | 改为字符串语义码（`WATERMARK_TEXT_TOO_LONG` 等），扩展规则明确 | §2.4 |
| 10 | 日志敏感信息泄露 | 新增脱敏规则表，明确禁止记录水印文本/URL/完整路径 | §12 |
| 11 | 前端 Blob URL 内存泄漏 | 新增 revokeObjectURL 生命周期管理 + >500 张切换文本列表 | §8.2 |

### v2 — 响应 10 条审查意见（首次外部审计）
### v1 — 初始设计文档
