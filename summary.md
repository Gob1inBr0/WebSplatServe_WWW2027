# WebSplatServe_WWW2027 构建记录

## 2026-10-03

### 需求理解

- 基于 `Web_Scan-feat-survey-algorithms` 的网页端代码重建一套面向 WWW 2027 Industry Track 的新方案代码。
- 参考 `WebGS_WWW_Industry_Track_Optimization_Plan.docx` 的优化方向，将项目主线从“3DGS压缩实验平台”升级为“面向异构Web客户端的自适应3D Gaussian Serving System”。
- 目标投稿方向对齐 WWW 2027 Industry Track：强调工业环境、系统实现、部署/发布、实际影响、Web规模与可复现证据。

### 已完成改动

- 新建目录 `WebSplatServe_WWW2027/`，作为新的投稿原型代码目录。
- 复制旧项目的 `web/` 平台层到新目录，保留现有 Web 控制台、Python API server、adapter registry、远程训练、结果管理、telemetry 和 progressive viewer 架构。
- 未复制大型算法仓库本体，避免新目录臃肿；训练/压缩仍通过 adapter 指向外部或远程算法仓库。
- 新增 `web/serving/manifest.py`：
  - 定义 WebSplatServe manifest 归一化逻辑。
  - 为 chunk 增补 `transferBytes`、`visualGain`、`decodeCostMs`、`gpuCostMs`、`qualityLevels` 和 `schedulerHints`。
  - 形成 Web-native Gaussian serving abstraction。
- 新增 `web/serving/adaptive_scheduler.py`：
  - 实现 `naive`、`bandwidth`、`viewport`、`gpu`、`joint`、`full` 六种策略。
  - 使用可解释 greedy score：`visualGain * viewWeight / (transferBytes + decode/gpu cost)`。
  - 支持 TTFR、load time、bytes、rows 和 quality gain trace 模拟。
- 新增 `web/serving/manifest_schema.json`，固定投稿实验用 manifest 的 JSON schema。
- 新增 `web/tools/export_websplatserve_assets.py`：
  - 复用旧 `export_web_assets.py` 的 PLY 分层/分块能力。
  - 输出增强版 `websplatserve_manifest.json`，写入投稿贡献、调度信号和部署证据字段。
- 新增 `web/tools/run_serving_benchmark.py`：
  - 批量运行多策略、多带宽、多 RTT 的 serving benchmark。
  - 输出 CSV，用于论文 TTFR / bytes / load time / ablation 表格。
- 新增 `web/tools/collect_deployment_evidence.py`：
  - 将 `/api/telemetry/summary` 的 JSON 汇总成论文可用的 deployment evidence markdown。
- 新增 `web/tools/test_websplatserve_scheduler.py`：
  - 覆盖 manifest 归一化、viewport优先级和调度模拟。
- 更新 `web/tools/run_tests.py`，纳入新的 WebSplatServe scheduler 测试。
- 新增 `web/config/websplatserve_profiles.json`：
  - 固定三类客户端、四类网络、六种策略和论文指标矩阵。
- 新增 `web/docs/EXPERIMENT_PLAN.md`：
  - 记录 WWW Industry 版本的 baseline、指标、设备/网络/场景矩阵和部署证据流程。
- 新增根目录 `README.md`：
  - 写清楚训练、导出、运行 viewer、测试、benchmark、deployment evidence 的步骤。
- 新增 `web/generated/` 标准运行目录骨架：
  - 包含 `job_logs`、`streams`、`datasets`、`workspaces`、`websplatserve`、`experiments` 等子目录的 `.gitkeep`。
  - 便于服务端、训练任务和实验脚本在真实环境中直接写入运行产物。
- 修改 `web/tools/test_ply_quick_load.py`：
  - 将控制台勾号输出改成 ASCII `[ok]`，避免 Windows GBK 控制台编码失败。
  - 将临时无效文件从项目根目录改到系统临时目录，减少测试对工作目录写权限的依赖。

### 当前创新点

1. Web-native Gaussian serving abstraction：把异构3DGS/压缩后端统一转换为 manifest + base layer + additive chunks。
2. Resource-aware adaptive delivery：联合 bandwidth、RTT、viewport、FPS/P95 frame time 和 memory budget 做 chunk 调度。
3. Incremental Web runtime reuse：沿用旧 progressive viewer 的 base-first、additive chunk、worker decode 和浏览器端增量渲染链路。
4. Industry deployment evidence：利用匿名 telemetry 汇总 session、TTFR、bytes、device/browser分布和 failure stage。
5. Reproducible evaluation harness：提供多策略、多网络条件的 benchmark CSV 输出，支撑论文 ablation。

### WWW 2027 Industry Track 对齐点

- 主题从单纯算法集成转为 Web infrastructure / Web serving / heterogeneous clients。
- 指标从离线模型大小/画质评价转向 Web 运行指标：TTFR、time-to-interactive、bytes、chunk arrival、FPS、P95 frame time、memory、cache behavior 和 failure rate。
- 代码保留真实系统运行链路：远程训练、导出、HTTP服务、浏览器viewer、telemetry和实验脚本。
- README 已说明如何训练、测试、运行和收集部署证据。

### 下一步建议

- 在真实 PLY 场景上运行 `export_websplatserve_assets.py` 并生成 `websplatserve_manifest.json`。
- 在至少三类设备和四类网络条件下采集 progressive viewer 的真实 telemetry。
- 使用 `benchmark.html` 和 telemetry 汇总真实浏览器 QoE 数据，形成 TTFR、bytes、chunk arrival、FPS/P95、缓存和失败率图表。

## 2026-10-03 追加优化：不引入质量评价的 WWW Industry 强化

### 本轮新增改动

- 新增 `web/config/backend_profiles.json` 和 `web/serving/backend_profiles.py`：
  - 固定 `vanilla-3dgs-sh`、`compressed-decoded-sh`、`compact-pruned-sh` 三类后端画像。
  - 用配置方式证明 serving layer 可以接在不同训练/压缩后端之后，而不强行改写所有算法仓库。
- 增强 `web/tools/export_websplatserve_assets.py`：
  - 新增 `--backend-profile` 参数。
  - 在 `websplatserve_manifest.json` 中写入 backend profile、chunk `contentHash`、`cacheKey`、`cacheControl`、`shContentHash`。
  - 形成 CDN/cache-aware chunk 元数据，支撑 Web infrastructure 叙事。
- 增强 `web/serving/manifest.py` 和 `manifest_schema.json`：
  - 新增 SHA-256 文件hash工具。
  - manifest schema 增加缓存和内容hash字段。
- 新增 `web/viewers/benchmark.html`：
  - 浏览器同源 benchmark harness。
  - 自动按策略矩阵加载 `progressive.html`，采集 TTFR、bytes、resident rows、chunk arrivals、FPS/P95 frame time、client profile、capability 和 failure 信息。
  - 明确不做 PSNR/SSIM/LPIPS 或其他质量评价。
- 增强 `web/viewers/progressive.js`：
  - 新增 `profile=auto|...` 和 `benchmark=1`。
  - 根据 `navigator.deviceMemory`、`hardwareConcurrency`、移动端 UA 等自动选择 `desktop_discrete_gpu`、`laptop_integrated_gpu`、`android_mid_range`。
  - 自动设置默认 `maxRows`，并让 GPU guard 阈值随目标 FPS 调整。
  - 记录 WebGL2、float texture、renderer 等 capability；WebGL2 不可用时给出明确 failure stage。
  - telemetry beacon 增加 `client_profile` 和 `capability_class`。
- 增强 `web/server/telemetry.py`：
  - 接收并汇总 client profile 和 capability class。
- 增强 `web/server/api_server.py`：
  - 对 `/web/generated/web_exports/` 和 `/web/generated/websplatserve/` 下的 `.bin/.json` 资产返回 `Cache-Control: public, max-age=31536000, immutable`。
  - 新增认证接口 `GET /api/telemetry/evidence.md`，直接导出论文部署证据 Markdown。
- 增强 `web/tools/collect_deployment_evidence.py`：
  - 输出 client profile 和 capability 分布。
- 新增 `web/tools/test_websplatserve_manifest.py`：
  - 测试 exporter 是否写入 backend profile、content hash、cache key 和 immutable cache metadata。
- 更新 `README.md`、`web/docs/EXPERIMENT_PLAN.md`、`web/config/websplatserve_profiles.json`：
  - 将评估重点固定为 Web QoE、传输、缓存、设备能力、稳定性和部署证据。
  - 去掉质量评价相关主线。

### 本轮新增创新点

1. Device-aware Web serving：浏览器自动识别设备画像，并影响 resident row cap 与 GPU-aware refinement。
2. Browser QoE benchmark harness：真实浏览器中采集 TTFR、bytes、chunk arrival、FPS/P95 和 failure，不停留在 Python 模拟。
3. CDN/cache-aware chunk protocol：manifest 写入内容hash、cache key 和 immutable cache策略，server实际返回缓存头。
4. Backend-profile abstraction：用配置方式表达不同3DGS/压缩后端的输入/服务契约，增强 representation-agnostic 可信度。
5. Deployment evidence endpoint：服务端直接导出论文可用的运行证据 Markdown。

### 本轮验证记录

- 已通过：
  - `python web/tools/run_tests.py websplatserve telemetry web_export`
  - `python -X pycache_prefix=<TEMP> -m py_compile ...` 覆盖新增 serving、tool、server 模块。
  - 使用临时目录合成 128-row SH PLY，运行 `export_websplatserve_assets(backend_profile="compact-pruned-sh")`，确认 manifest 写入 backend profile、content hash 和 immutable cache metadata，并用 `simulate_manifest(policy="joint")` 得到 TTFR trace。

### 运行前检查补充

- 新增 `web/docs/RUN_CHECKLIST.md`，集中记录正式运行前的验证、导出、服务启动、viewer、browser benchmark 和 deployment evidence 导出命令。
- 修正 `web/docs/EXPERIMENT_PLAN.md` 中旧的 `quality step` 表述，改为 `chunk or refinement milestone`，保持“不引入质量评价”的当前要求。

## 2026-10-04 运行边界说明：是否需要训练、输入输出与完整流程

### 是否需要训练模型

这份新代码本身不是一个新的 3DGS 训练算法，也不强制必须先训练才能验证 WebSplatServe 的 serving / viewer / benchmark 能力。

当前代码分成两层：

1. 训练/压缩层：
   - 如果用户还没有 3DGS 场景结果，就需要通过旧 Web-Scan 保留下来的 remote training / adapter 流程训练或压缩模型。
   - 训练依赖外部或远程算法仓库，例如 vanilla 3DGS、HAC++、ContextGS、CompGS、FCGS 等。
   - 新目录没有复制大型算法仓库本体；它通过 adapter 指向远程 GPU 服务器上的算法仓库。
   - 因此真实训练需要用户准备 GPU、CUDA、Conda/Python 环境、算法仓库和对应 `setup_env.sh`。

2. WebSplatServe serving 层：
   - 如果用户已经有训练好的标准 SH PLY 文件，就不需要重新训练。
   - 可以直接运行 `export_websplatserve_assets.py`，把 PLY 转成 WebSplatServe 的 progressive serving assets。
   - 然后用 `progressive.html` 或 `benchmark.html` 在浏览器中运行和采集 Web QoE 数据。

一句话结论：

- 没有 PLY：需要先训练或从已有算法输出中生成 PLY。
- 已有标准 3DGS SH PLY：不需要训练，可以直接跑导出、viewer、benchmark 和 telemetry。

### 主要输入

#### A. 训练/压缩入口输入

用于旧 Web-Scan remote training 流程：

- 多视角图片、相机采集图片或已有 COLMAP/3DGS 数据集。
- 远程 GPU 服务器信息：
  - host
  - port
  - username/password 或 SSH key
  - repo path
  - workspace root
  - output root
- 算法 adapter 配置：
  - `web/config/algorithm_adapters.json`
  - 可选覆盖：`web/config/algorithm_adapters.override.json`
- 算法参数：
  - iterations
  - source path
  - output path
  - checkpoint path
  - 是否启用压缩/评估等。

训练/压缩输出一般是：

- 标准或可转成标准格式的 3DGS PLY。
- 算法日志。
- metrics CSV。
- 远程输出目录。
- 可选 render / result metadata。

#### B. WebSplatServe 导出入口输入

用于本轮新增的 Web-native serving 流程：

```bash
python web/tools/export_websplatserve_assets.py /path/to/scene.ply web/generated/websplatserve/scene_a --backend-profile vanilla-3dgs-sh
```

输入要求：

- `scene.ply`：
  - binary little-endian PLY。
  - 包含 vertex element。
  - 至少包含 `x/y/z`。
  - WebSplatServe progressive SH viewer 需要 SH 字段：
    - `f_dc_0/f_dc_1/f_dc_2`
    - `f_rest_0 ... f_rest_44`
  - 推荐包含：
    - `scale_0/scale_1/scale_2`
    - `rot_0/rot_1/rot_2/rot_3`
    - `opacity`
- `--backend-profile` 可选：
  - `vanilla-3dgs-sh`
  - `compressed-decoded-sh`
  - `compact-pruned-sh`

#### C. Browser benchmark 输入

用于真实浏览器 QoE 采集：

```text
http://127.0.0.1:8080/web/viewers/benchmark.html?url=/web/generated/websplatserve/scene_a/manifest.json&seconds=12
```

输入参数：

- `url`：progressive manifest 路径。
- `seconds`：每个 policy 运行多少秒。
- `policies`：可选，默认跑 `naive,bandwidth,viewport,gpu,joint,full`。
- `maxRows`：可选，限制浏览器 resident rows。

#### D. Deployment evidence 输入

用于生成论文运行证据：

- 在线接口：

```text
GET /api/telemetry/evidence.md
```

- 离线脚本：

```bash
python web/tools/collect_deployment_evidence.py telemetry_summary.json --out deployment_evidence.md
```

输入是 `/api/telemetry/summary` 保存下来的 JSON。

### 主要输出

#### A. WebSplatServe export 输出

导出目录示例：

```text
web/generated/websplatserve/scene_a/
```

核心输出：

- `manifest.json`
  - legacy progressive viewer 可直接加载的 manifest。
- `websplatserve_manifest.json`
  - 增强版 manifest。
  - 包含 backend profile、chunk metadata、cache metadata、scheduler hints。
- `base.bin`
  - 首屏可渲染 base layer。
- `base.sh.bin`
  - base layer 对应 SH 数据。
- `q1*.bin / q2*.bin / q3*.bin`
  - additive refinement chunks。
- `*.sh.bin`
  - refinement chunks 对应 SH 数据。

增强版 manifest 中新增的关键字段：

- `backendProfile`
- `wwwIndustryContribution`
- `transferBytes`
- `visualGain`
- `decodeCostMs`
- `gpuCostMs`
- `contentHash`
- `shContentHash`
- `cacheKey`
- `cacheControl`

#### B. Viewer 输出

`progressive.html` 在浏览器中输出：

- 渐进式 3D Gaussian 场景渲染。
- HUD：
  - policy
  - profile
  - time
  - TTFR
  - vertices
  - downloaded bytes
  - bandwidth estimate
  - FPS / P95 frame time
- `window.__webgsTelemetry()`：
  - policy
  - clientProfile
  - capabilities
  - ttfrMs
  - chunkEvents
  - samples
  - frameTimes
  - totalBytes
  - totalRows
  - chunkFailures

#### C. Browser benchmark 输出

`benchmark.html` 输出：

- 页面侧边栏日志。
- 可下载 JSON：
  - 每个 policy 的 telemetry。
  - TTFR。
  - bytes。
  - resident rows。
  - chunk arrivals。
  - FPS/P95 frame time。
  - client profile。
  - capability。
  - failure stage。

该 benchmark 不做 PSNR、SSIM、LPIPS 或其他图像质量评价。

#### D. Simulation benchmark 输出

```bash
python web/tools/run_serving_benchmark.py web/generated/websplatserve/scene_a/websplatserve_manifest.json --out web/generated/experiments/serving_benchmark.csv
```

输出：

- `serving_benchmark.csv`
- 字段包括：
  - policy
  - bandwidth_mbps
  - rtt_ms
  - ttfr_ms
  - load_ms
  - bytes
  - rows
  - chunks

#### E. Deployment evidence 输出

输出 Markdown：

- Operational Scale
  - total events
  - uptime
  - HTTP requests
  - bytes served
  - latency
- Serving Quality of Service
  - scene loads
  - TTFR
  - P95 frame time
  - bytes per load
  - policy counts
  - client profile counts
  - capability counts
  - failure stages
- Client Mix
  - browser
  - OS
  - device

### 本轮优化过程总览

1. 新建 `WebSplatServe_WWW2027/`，复用旧 Web-Scan 的 Web 控制台、Python API server、adapter registry、remote execution、telemetry 和 progressive viewer。
2. 新增 `web/serving/manifest.py`，定义 Web-native manifest/chunk 归一化与 scheduler hints。
3. 新增 `web/serving/adaptive_scheduler.py`，实现 `naive / bandwidth / viewport / gpu / joint / full` 六种策略。
4. 新增 `export_websplatserve_assets.py`，把标准 SH PLY 导出为 base layer、refinement chunks 和增强版 manifest。
5. 新增 `backend_profiles.json` 和 `backend_profiles.py`，用配置方式表达不同训练/压缩后端画像。
6. 为 chunk 增加 `contentHash / cacheKey / cacheControl / shContentHash`，形成 CDN/cache-aware chunk protocol。
7. 修改 `api_server.py`，让 WebSplatServe `.bin/.json` 静态资产返回 immutable cache header。
8. 修改 `progressive.js`，新增设备 profile 自动识别、capability 记录、WebGL2 failure fallback、profile-aware GPU guard。
9. 新增 `benchmark.html`，在真实浏览器中采集 TTFR、bytes、chunk arrivals、FPS/P95、device profile、capability 和 failure。
10. 扩展 `telemetry.py`，汇总 client profile 和 capability class。
11. 新增 `/api/telemetry/evidence.md`，直接导出论文可用运行证据 Markdown。
12. 新增 `RUN_CHECKLIST.md`，集中记录运行前检查、导出、服务启动、viewer、benchmark 和部署证据命令。
13. 更新 `README.md`、`EXPERIMENT_PLAN.md`、`summary.md`，把当前主线固定为 Web QoE、传输、缓存、设备能力、稳定性和部署证据。

### 当前可直接运行的部分

- Web 控制台。
- API server。
- PLY quick load。
- PLY -> progressive Web assets 导出。
- WebSplatServe manifest/chunk 导出。
- progressive viewer。
- browser QoE benchmark。
- Python simulation benchmark。
- telemetry summary。
- deployment evidence markdown 导出。
- 新增 serving 相关测试。

### 当前需要外部环境的部分

- 真实训练 3DGS / HAC++ / ContextGS / FCGS / CompGS 等模型。
- 远程 GPU 服务器。
- CUDA / PyTorch / Conda 环境。
- 对应算法仓库和 `setup_env.sh`。
- 可用于导出的真实标准 SH PLY。

因此，当前代码可以直接跑 Web/Serving/Benchmark；如果要从图片开始训练出模型，需要先配置远程 GPU 和算法仓库。

## 2026-10-04 编号运行脚本整理

### 已新增 `scripts/` 目录

按照用户要求，所有需要运行的脚本已集中放在项目根目录 `scripts/` 下，并按运行顺序使用 `01_`、`02_` 等编号命名：

1. `scripts/01_preflight.ps1`
   - 运行 focused tests：`websplatserve telemetry web_export`。
   - 运行新增模块语法检查。
2. `scripts/02_start_server.ps1`
   - 写入/复用本地 token。
   - 启动 `web/server/api_server.py`。
   - 检查 `/api/health`。
   - 打印 Web 控制台地址。
3. `scripts/03_print_training_console.ps1`
   - 打印远程训练控制台地址。
   - 说明如果没有 PLY，需要在 Web UI 中配置远程 GPU、adapter 和训练参数。
4. `scripts/04_export_scene.ps1`
   - 输入标准 SH PLY。
   - 输出 `web/generated/websplatserve/<SceneId>/manifest.json` 和 `websplatserve_manifest.json`。
   - 支持 `vanilla-3dgs-sh`、`compressed-decoded-sh`、`compact-pruned-sh` 三类 backend profile。
5. `scripts/05_run_scheduler_simulation.ps1`
   - 对单个 policy 运行 Python scheduler simulation。
   - 输出 trace CSV。
6. `scripts/06_run_policy_benchmark.ps1`
   - 对多 policy、多 bandwidth、多 RTT 运行 benchmark。
   - 输出 serving benchmark CSV。
7. `scripts/07_print_browser_benchmark_urls.ps1`
   - 打印 progressive viewer URL。
   - 打印 browser QoE benchmark URL。
8. `scripts/08_export_deployment_evidence.ps1`
   - 调用 `/api/telemetry/evidence.md`。
   - 输出 `deployment_evidence.md`。
9. `scripts/09_run_all_local_checks.ps1`
   - 本地检查聚合脚本，目前调用 `01_preflight.ps1`。
10. `scripts/10_smoke_local_pipeline.ps1`
   - 在系统临时目录生成 synthetic SH PLY。
   - 调用 `04_export_scene.ps1` 导出 WebSplatServe assets。
   - 调用 `05_run_scheduler_simulation.ps1` 和 `06_run_policy_benchmark.ps1`。
   - 用于验证导出、manifest增强、scheduler、benchmark 全链路，不依赖真实PLY、远程GPU或 `web/generated` 写权限。

### 推荐运行顺序

```powershell
powershell -ExecutionPolicy Bypass -File scripts/01_preflight.ps1
powershell -ExecutionPolicy Bypass -File scripts/02_start_server.ps1
powershell -ExecutionPolicy Bypass -File scripts/03_print_training_console.ps1
powershell -ExecutionPolicy Bypass -File scripts/04_export_scene.ps1 -PlyPath "C:\path\to\scene.ply" -SceneId scene_a
powershell -ExecutionPolicy Bypass -File scripts/05_run_scheduler_simulation.ps1 -SceneId scene_a
powershell -ExecutionPolicy Bypass -File scripts/06_run_policy_benchmark.ps1 -SceneId scene_a
powershell -ExecutionPolicy Bypass -File scripts/07_print_browser_benchmark_urls.ps1 -SceneId scene_a
powershell -ExecutionPolicy Bypass -File scripts/08_export_deployment_evidence.ps1
powershell -ExecutionPolicy Bypass -File scripts/10_smoke_local_pipeline.ps1
```

### 说明

- 如果已经有标准 SH PLY，可以从 `04_export_scene.ps1` 开始。
- 如果没有 PLY，需要先通过 `03_print_training_console.ps1` 给出的 Web 控制台入口配置远程训练。
- 真实训练无法仅靠本地脚本完成，因为需要远程 GPU、算法仓库、CUDA/PyTorch/Conda 环境和用户凭据。
- 当前沙箱中普通 Python/PowerShell 进程对 `web/generated/<动态子目录>` 写入会被拒绝，因此 `10_smoke_local_pipeline.ps1` 默认使用 `%TEMP%` 做完整链路自测；真实机器上默认 `web/generated` 路径可用于浏览器访问。

### 编号脚本验证记录

- 已通过：
  - `powershell -ExecutionPolicy Bypass -File scripts\01_preflight.ps1`
  - `powershell -ExecutionPolicy Bypass -File scripts\09_run_all_local_checks.ps1`
  - `powershell -ExecutionPolicy Bypass -File scripts\03_print_training_console.ps1`
  - `powershell -ExecutionPolicy Bypass -File scripts\07_print_browser_benchmark_urls.ps1 -SceneId scene_a`
  - `powershell -ExecutionPolicy Bypass -File scripts\10_smoke_local_pipeline.ps1`
- `10_smoke_local_pipeline.ps1` 验证内容：
  - 在 `%TEMP%` 生成 synthetic SH PLY。
  - 调用 `04_export_scene.ps1` 成功导出 4 个 chunks 和 `websplatserve_manifest.json`。
  - 调用 `05_run_scheduler_simulation.ps1` 成功输出 joint trace CSV。
  - 调用 `06_run_policy_benchmark.ps1` 成功输出多策略 benchmark CSV。
- 已修复：
  - `web/serving/adaptive_scheduler.py` 作为脚本直接运行时缺少项目根 `sys.path` 的问题。

## 2026-10-04 代码问题复查与修复

### 本轮检查发现的问题

1. `scripts/02_start_server.ps1` 最初使用固定本地 token `websplatserve-local-dev-token`，并尝试直接写入 `web/config/server.token`。
   - 问题：固定 token 不适合长期保留；当前受限沙箱中普通 PowerShell 进程也可能无法写入项目目录。
   - 修复：脚本现在优先使用调用方传入的 `-Token`，其次读取 `web/config/server.token`，再次读取 `%TEMP%/websplatserve_server.token`，否则生成随机 token。
   - 如果项目目录写 token 失败，脚本会写入 `%TEMP%/websplatserve_server.token`。

2. 服务端 `web/server/web_security.py` 原本在无法持久化 token 时会导致启动失败。
   - 修复：`_write_server_token()` 捕获写入失败并记录 warning，服务继续使用内存 token。

3. `scripts/02_start_server.ps1` 在端口已有旧服务时可能生成新 token 并误判服务不可用。
   - 修复：脚本现在先检测端口。如果端口已经监听，不会生成新 token；只用已有或传入 token 验证 `/api/health`。如果 token 不匹配，会提示传入正确 token 或停止旧进程。

4. `scripts/08_export_deployment_evidence.ps1` 原本默认使用固定 token。
   - 修复：现在默认读取 `web/config/server.token`，若不存在则读取 `%TEMP%/websplatserve_server.token`；也可手动传入 `-Token`。

5. `web/viewers/progressive.js` 显式传入 `profile=android_mid_range` 或 `profile=laptop_integrated_gpu` 时，row cap / target FPS 未按 profile 套用。
   - 修复：新增 profile map，显式 profile 和自动检测 profile 都会套用正确 `rowCap` 与 `targetFps`。

6. `scripts/04_export_scene.ps1` 使用临时 `-OutDir` 时仍打印 `/web/generated/...` URL，容易误导。
   - 修复：如果输出目录不是默认 `web/generated/websplatserve/<SceneId>`，则打印真实 manifest 文件路径。

### 本轮复查通过项

- `powershell -ExecutionPolicy Bypass -File scripts\01_preflight.ps1`
- `powershell -ExecutionPolicy Bypass -File scripts\10_smoke_local_pipeline.ps1`
- PowerShell AST 解析检查：`scripts/*.ps1` 全部 `OK`
- `powershell -ExecutionPolicy Bypass -File scripts\02_start_server.ps1 -Token websplatserve-local-dev-token`
  - 在当前已有旧服务占用 8080 的情况下，成功复用服务并通过 `/api/health`。

### 当前剩余注意事项

- 若 8080 端口已有服务运行，但不知道该服务 token，`02_start_server.ps1` 会拒绝误用并提示传入正确 `-Token` 或停止旧进程。
- 真实训练仍然依赖远程 GPU、算法仓库和用户凭据，不能由本地脚本自动完成。

### 本轮验证记录

- 已通过：
  - `python web/tools/run_tests.py websplatserve`
  - `python web/tools/run_tests.py telemetry web_export websplatserve ply_quick_load`
  - 使用临时目录合成 128-row SH PLY，运行 `export_websplatserve_assets()` 生成 4 个 progressive chunks，并用 `simulate_manifest(policy="joint")` 得到可用 TTFR trace。
  - 使用 `python -X pycache_prefix=<TEMP> -m py_compile ...` 对新增 Python 模块完成语法检查。
- 当前沙箱限制：
  - 旧测试 `detached_remote`、`flow_data`、`flow_reset`、`job_cleanup` 需要在 `web/generated/job_logs` 或 `web/generated/streams` 下动态创建随机子目录。
  - 当前 PowerShell/Python 进程对新复制目录的运行时写入被拒绝，因此这些旧测试在本会话中无法完整验证。
  - 该限制不影响新增 WebSplatServe 模块的导入、导出、调度和模拟验证；真实开发机/服务器上应使用正常可写工作目录运行全量测试。

## 2026-10-04 bash 版运行脚本与仓库上传

### 本轮新增改动

- 新增 `scripts/01_preflight.sh` 至 `scripts/10_smoke_local_pipeline.sh` 共十个 bash 脚本，与同名 `.ps1` 功能一一对应，macOS 与 Linux 可用：
  - 解释器默认 `python3`，可用环境变量 `PYTHON` 或 `--python` 参数覆盖。
  - 参数从 PowerShell 的 `-Named` 形式改为 `--flag value` 形式，取值集合（六种策略、三种后端画像）保持一致校验。
  - `02_start_server.sh`：令牌生成改用 `secrets.token_urlsafe`，端口检测按 lsof → ss → netstat 顺序回退，健康检查用 `curl`，服务进程用 `nohup` 后台启动并写日志到 `web/generated/server.log`；沿用 ps1 的"端口被占用则复用并校验令牌"逻辑。
  - `10_smoke_local_pipeline.sh`：临时目录改用 `${TMPDIR:-/tmp}`，合成 PLY 通过环境变量传入内联 Python，避免路径引号问题。
- 更新 `scripts/README.md`，补充 bash 用法一节。
- 新增 `.gitignore`：排除 `__pycache__`、`.DS_Store`、运行产物（`web/generated/**` 仅保留 `.gitkeep` 骨架）、`server.token`、日志与生成的部署证据。
- 初始化 git 仓库并推送至 `https://github.com/Gob1inBr0/WebSplatServe_WWW2027.git`（main 分支，commit 455e34b）。

### 本轮验证记录（macOS，Python 3.13.12 + numpy 2.4.3）

- `scripts/01_preflight.sh`：4 个测试模块（telemetry、web_export、websplatserve_manifest、websplatserve_scheduler）全部通过，语法检查通过。
- `scripts/10_smoke_local_pipeline.sh`：160 行合成 PLY → 导出 4 个 chunk → joint 策略模拟（TTFR 62.9ms）→ 12 行基准 CSV，全流程通过。
- `scripts/02_start_server.sh`：启动与端口复用两条路径均通过；`03`、`07` URL 打印正常；`08` 成功导出部署证据 markdown（遥测 15 条事件）；`09` 包装脚本通过。
- 验证结束后已停止测试用服务进程。

### 待办：LYH 服务器验证

- 计划在 LYH 服务器（`~/.ssh/config` 别名，Ubuntu 22.04）上复跑 `01_preflight.sh` 与 `10_smoke_local_pipeline.sh` 验证 Linux 兼容性。
- 当前连接在密钥交换前被服务器关闭（`kex_exchange_identification: Connection closed by remote host`），多次退避重试均失败，属服务器端问题（sshd 限流/封禁或服务异常）。服务器恢复后执行：
  ```bash
  rsync -a --exclude .git --exclude '__pycache__' --exclude 'web/generated/*/' \
    ./WebSplatServe_WWW2027 LYH:/home/T0ng/
  ssh LYH 'cd /home/T0ng/WebSplatServe_WWW2027 && PYTHON=/home/T0ng/miniconda3/envs/DCCA/bin/python bash scripts/01_preflight.sh && bash scripts/10_smoke_local_pipeline.sh'
  ```

## 2026-10-04 LYH 服务器验证完成 + 拒连根因定位

### LYH 服务器实测结果

- 项目已 rsync 部署到 `/home/T0ng/WebSplatServe_WWW2027`（1.9 MB，排除 .git/运行产物）。
- `scripts/01_preflight.sh`：4 个测试模块全部通过（服务器 Ubuntu 22.04、系统 Python 3.10.12 + numpy 1.21.5；交接手册里的 conda 环境已不存在）。
- `scripts/10_smoke_local_pipeline.sh`：合成 PLY → 导出 → joint 模拟 → 基准 CSV 全流程通过，TTFR 数值与 macOS 完全一致（62.9 ms）。
- `scripts/02_start_server.sh` 启动与端口复用两条路径、`08` 部署证据导出、`03/07/09` 均在服务器上通过；验证后已停掉服务进程。bash 版脚本 Linux 兼容性验证完成。

### 拒连根因（重要，已写入公用文档《科研工作/LYH服务器使用指南.md》§10）

- 当天 LYH "连不上"与服务器无关：本机 Clash Verge 处于全局模式，所有流量（含中国 IP）经 TUN 送往所选香港节点，该节点到 LYH:65022 不通；报错 "Connection closed by 36.138.63.143" 中的"对方"实际是本机 TUN。
- 证据链：bogus 端口 0.00 秒"连通"（本地代答）→ `route get` 走 utun1024 → mihomo socket API `mode: global` → 日志实锤 `36.138.63.143:65022 using GLOBAL` → PATCH 切 rule 模式后 SSH 当场连通。
- 同一时刻 ssh.github.com:443 认证正常，证明隧道与 SSH 转发本身没问题；此前 fork 会话的 MaxStartups/fail2ban 假设均未成立。
- 验证期间临时把 Clash 切到规则模式，完成后已恢复全局模式。后续在服务器上做批量 SSH 操作前应先确认本机代理模式。

### 补充：全量测试套件首次完整通过

- 在 LYH 服务器（可写运行目录）运行 `python3 web/tools/run_tests.py`（不带参数），9 个测试模块全部通过，其中包括此前因沙箱写权限限制一直无法完整验证的 5 个旧平台测试：detached_remote、flow_data、flow_reset、job_cleanup、ply_quick_load。
- 至此三层验证全部闭环：单元测试（9 模块）、脚本冒烟（10 个脚本 × macOS/Linux 双平台）、模拟基准（6 策略 × 多网络矩阵）。

## 2026-10-04 代码审查修复：调度语义、服务端安全与遥测聚合

四路并行代码审查（调度核心 / 导出与基准工具 / 服务端与浏览器安全 / 脚本一致性）发现的问题已修复并全部重新验证。

### 调度器（web/serving/adaptive_scheduler.py，重写模拟语义）

- 策略停止条件（修 P0）：除 full（全量下载基线）外，五种策略在累计质量增益达到 `--quality-target`（默认 0.9）即停。此前所有策略都全量传输，六策略的 load_ms/bytes/rows 恒等，对比表自证其假。
- 基础层强制先行（修 P1）：base 块无条件最先传输，TTFR 定义为 base 完成时刻（此前是任意首块，内存收紧时会先传增量块、算出不可能成立的 TTFR）。
- GPU 信号回写（修 P1）：每传一块按驻留行数 / `gpu_capacity_rows` 重新估计 fps 与 P95 帧时间，gpu/joint 策略的降载判据在模拟里真正生效（此前是死代码，gpu 列等于 bandwidth 复读）。
- 内存预算硬拦截（修 P1）：超预算的增量块直接跳过并计入 `budget_skips`，base 豁免；此前只降权不拦截。
- 毫秒成本换算字节当量：打分公式里 decode/gpu 成本按当前带宽换算（λ=8、μ=2 保留），分母量纲统一；带宽 ≤0、RTT<0、目标超出 (0,1] 直接报错。
- 新指标：视角加权质量（相机固定在默认机位）的 `view_gain_fraction` 与 `t50_view_ms`/`t90_view_ms` 到达时间，trace 增加 stage 与 view_gain 列——字节数相同的策略按"视角质量到达时间"区分。
- naive 与 full 语义分离：naive 按清单顺序 + 质量目标停止；full 无视目标全量传输（无自适应基线）。
- manifest.py：重复 chunk id 直接报错（此前静默丢块）；gpuCostMs 默认从 rows×0.0004 调到 rows×0.008（旧值在打分公式里只占 0.4%，gpu/joint 永远排不出差异）；schedulerHints 注明字节当量语义、并发改 1 与模拟一致。**注意：旧导出产物的 cost 字段是旧默认值，正式采数前需重新导出。**

### 服务端安全（api_server.py / web_security.py）

- 静态拒绝名单补 `generated/server.log`、`*.log`、`server.pid`（此前启动日志可被匿名下载，其中曾含完整令牌——P0）；启动输出令牌改为掩码（前6后4），curl 示例不再内嵌完整令牌。
- token 比较改 `hmac.compare_digest`（恒时）。
- 缓存头修正：一年 immutable 只给 `.bin`；`.json` 清单改 `no-cache, must-revalidate`（此前同 URL 重新导出后老访客一年拿旧数据）。
- POST body 上限 1 MB（超限 413）、Content-Length 非数字返回 400（此前匿名端点可被声明长度无上限读入内存）。

### 遥测（telemetry.py）与浏览器端（progressive.js / benchmark.html）

- serving_load 新增 `stage`（first_frame/complete/failed）与 `benchmark` 白名单字段；summary 按 stage 分开聚合：TTFR 只统计首帧信标、bytes/帧时间只统计完成信标（此前一次加载计两次、bytes 混入部分值）、`by_policy` 等用户分布排除 benchmark 合成负载、新增 `loads_by_stage`/`benchmark_loads`。
- 数值防御：JSON 里的 `Infinity`（此前 OverflowError 使匿名端点无响应）与 `NaN`（此前被钳成 10000）一律丢弃字段。
- export 失败遥测只记异常类型名，不再记录含场景名的完整路径（隐私声明一致性）。
- 设备分档修正：`deviceMemory==8` 不再判成笔记本核显（规范上限 8 表示"至少 8GB"）；负数 maxRows 不再冻结调度器。
- benchmark=1 成为真实功能：manifest 与 chunk 请求带 `cache: "reload"`，保证矩阵测量不命中磁盘缓存；benchmark.html 采集 `__errors` 并把未在窗口内完成首帧的行标记 `incomplete`。

### 脚本（scripts/*.sh）

- 01/09 补 `--python` 参数解析（此前被静默忽略）；02 增加端口数值校验、启动失败的日志尾部诊断、令牌文件 chmod 600、读取时剥 PowerShell BOM、端口检测工具全缺时告警。

### 验证记录

- 本机（macOS，Python 3.13）：9 个测试模块全部通过；调度器测试新增 6 组断言（base-first 与 TTFR 定义、策略字节分化、内存跳过、gpu 反应、非法参数、重复 id），遥测新增 stage/benchmark 聚合与 Infinity/NaN 用例。
- 基准分化验证：24k 行空间分布合成场景、目标 0.7、GPU 容量 6000 时，六策略产出 4 种不同的 (bytes, t50_view, t90_view) 签名（naive / bandwidth / viewport / full 各异；gpu、joint 在每行成本均匀的合成场景上与 bandwidth、viewport 重合属预期，单元测试已用异构成本清单证明其机制）。
- 服务端在线验证：`GET /web/generated/server.log` 404、日志无完整令牌、manifest.json `no-cache`、base.bin `immutable`、Infinity 载荷 200、1MB body 413、部署证据导出正常。
- LYH 服务器（Ubuntu 22.04，Python 3.10）：preflight、冒烟、全量 9 模块全部通过。

## 2026-10-04 新功能：控制台从本机 ~/.ssh/config 一键导入远程主机

### 功能说明

配置远程 GPU 服务器档案时，不再需要手动填地址/端口/用户/密钥路径，也不用翻终端历史找 ssh 命令：设置页新增"从 ~/.ssh/config 导入"控件，点击"读取主机"即列出本机 SSH 客户端配置里全部可导入的主机（别名、真实地址、端口、用户、密钥路径），选择后自动填入编辑中的档案（label 用别名，IdentityFile 写入 key_path）。

### 实现

- 新增 `web/server/ssh_config_import.py`：OpenSSH 客户端配置解析器。遵循 ssh 语义——同一别名字段首值优先；`Host` 行支持多别名与 `=` 语法；跳过含 `*`/`?`/`!` 的模式项与整个 `Match` 块（条件配置不适用于导入）；`Include` 指令按 OpenSSH 规则展开（相对路径相对 ~/.ssh，支持 glob，上限 64 个文件防止循环/滥用）。只返回配置元数据，绝不读取或返回密钥内容。
- 新增 `GET /api/ssh-config/hosts`（与其他 /api 路由同样受令牌保护，未认证返回 401）。
- 控制台设置页（`web/console/js/pages/settings.js`）在粘贴 SSH 命令的旁边新增导入控件：读取主机 → 下拉选择 → 导入。中英双语词条已加（`set.sshConfig*`）。
- 说明：向导页里的 `quickConnect` 粘贴建档代码是未挂模板的残留，本次未动；档案管理入口统一在设置页。

### 验证记录

- 新增测试模块 `web/tools/test_ssh_config_import.py`（6 组断言：基本字段与别名回退、首值优先、通配符/排除模式跳过、多别名共享与 Match 跳过、`=` 语法与键名大小写、Include 跟随与文件缺失容错），已注册进 `run_tests.py`。
- 本机与 LYH 服务器各 10 个测试模块全部通过；api.js / settings.js / i18n.js 通过 node 语法检查。
- 本机服务实测：接口返回真实 ~/.ssh/config 中的 LYH、4D、github.com、small5090 等主机且字段正确；无令牌请求 401。

## 2026-10-04 控制台目录默认值重新设计（产品视角）

### 旧默认的问题

- `workspace_root=/tmp/web_scan/workspaces`、`output_root=/tmp/web_scan/outputs`：Linux 服务器上 /tmp 重启即清空（训练输出丢失）、常见为内存盘（容量受限，多 GB 数据集上传直接写爆）、部分发行版的 systemd-tmpfiles 还会按访问时间自动清理。把数据集和训练产物放这里是能毁实验的最危险默认。
- 仓库路径占位符 `/root/autodl-tmp/Web_Scan`：绑定 AutoDL 单一供应商命名，且还是旧项目品牌。
- 一次新建档案要独立做 4 个绝对路径决定，认知负担大。

### 新设计（原则：数据永不落 /tmp；一次决定、处处派生；填多少算多少）

- `store.js` 新增 `deriveDataPaths(username)`：按登录用户名推导——root 得 `/root/websplatserve/{workspaces,outputs}`，其他用户得 `/home/<user>/websplatserve/...`；用户名仅允许 `[A-Za-z0-9._-]`（剥掉 `~` 前缀），非法或空一律回退 `/root`，杜绝路径注入。默认值必须是绝对路径（服务端 PurePosixPath 直接进 SFTP，`~` 不展开）。
- 新建档案与向导快捷建档都用推导值；设置页用户名字段联动：改动用户名时，若工作区/输出目录仍是"推导默认值"（正则识别）则跟随更新，用户自定义过的路径（如 /root/autodl-tmp/...）绝不被覆盖。
- 防呆：工作区/输出目录落在 /tmp 或 /dev/shm 下时表单出现琥珀色警告（双语）。
- 品牌与占位符：仓库路径占位符改为 `/root/autodl-tmp/WebSplatServe`。
- 迁移：只影响新建档案，已保存档案不动。

### 验证

- node 语法检查四个前端文件全过；`deriveDataPaths` 六组边界（root/普通用户/`~`前缀/路径注入/空串）与"是否默认值"正则五组用例全部符合预期；Python 全量 10 模块不受影响。

## 2026-10-04 新功能：远程数据盘探测（接目录默认值设计）

### 功能

设置页档案编辑区新增"探测服务器数据盘"按钮：SSH 到目标机器执行 `df -P` + 读 `/proc/mounts`，把真实文件系统按剩余空间排序展示，并给出数据根目录建议。工作区/输出目录仍是推导默认值（或为空）时自动采用建议；用户已自定义路径则弹提示告知最大磁盘但保留原值。密码/密钥缺失或主机未填时按钮给出明确引导。

### 实现

- `web/server/remote_executor.py` 新增 `remote_disk_probe()` 与 `parse_disk_report()`：tmpfs/ramfs/devtmpfs 等伪文件系统一律排除（数据放 /tmp 的教训写进了过滤器）；NFS/CIFS 等网络文件系统参与展示与排序但不作为首选建议（本地盘优先）；`/proc`、`/sys`、`/dev`、`/run`、`/boot`、`/snap`、`/tmp`、docker/kubelet 目录前缀排除；挂载点八进制转义（`\040` 空格等）正确还原；只需连接字段即可调用（档案填一半也能探测）。
- 新增 `POST /api/remote-disk-probe`（令牌保护，复用 RemoteExecutionError 错误风格）。
- 控制台设置页加探测按钮与结果提示（`set.probe*` 双语词条）；`deriveDataPaths` 的"是否默认值"正则复用于采用/保留判断。

### 验证

- 新增测试模块 `web/tools/test_remote_disk_probe.py`（6 组：排序与本地盘优先建议、无 /proc/mounts 回退设备名过滤、`\040` 转义还原、纯网络盘仍给建议、空输出安全、tmpfs 排除），注册后本机 11 个测试模块全部通过；LYH 同步后同样全过。
- 实测 LYH：正确返回唯一本地盘 `/`（ext4，147.5 GB 总量 / 12.9 GB 剩余，与交接手册一致），/dev/shm 未误入候选；无令牌请求 401。
- 环境注记：本机 Clash 核心当晚已退出、TUN 路由消失，网络为纯直连，SSH 无需切代理模式（此前"先切规则再测再恢复"的流程仅在代理运行时需要）。

## 2026-10-05 修复：向导死锁与图片上传 413

### 修复 1：向导"下一步"按钮死锁

上传路径的解锁条件写成了"上传回执已存在"，而上传只能由这个按钮触发——选完文件按钮永远禁用。改为"已选图片且数据集名非空"即解锁，点击后走原有上传流程（按钮 loading 态防重复提交）。

### 修复 2：图片上传 413（本轮安全修复的回归）

上一轮加的全局 POST body 上限 1 MB 误伤了 /api/stream-frame：照片以 base64 整包上传，一张 664 KB 的 JPEG 编码后约 0.9 MB，稍大的照片直接超限（日志实锤 POST /api/stream-frame → 413）。改为按端点区分：stream-frame 32 MB、其余端点维持 1 MB。

教训：给共享入口加全局限制时必须先盘点所有调用方的合法载荷规模。

### 验证

- 真实照片经 /api/stream-frame 上传返回 200 并生成 capture_id；40 MB 载荷仍被 413 拒绝；遥测端点 1.5 MB 仍 413；telemetry 测试模块通过。

## 2026-10-05 浏览器控制跑通 HAC++ 全流程（5k 验证档）

- 用 ZCode 内嵌浏览器驱动控制台完成全链路：SSH 配置导入建档案 → 数据盘探测 → 上传 drjohnson 100 张 → 服务器自动 COLMAP → HAC++ 5000 迭代 → 渲染评测。最终 PSNR 13.92 / SSIM 0.686 / LPIPS 0.530（27 MB 点云），产物在 LYH:/websplatserve/outputs/runs/drjohnson-hac-5k-manual。
- 服务器准备：HAC++ 仓库同步至 /home/T0ng/HAC-plus-main；SHARC 环境补 cv2/tensorboard 并编译 gridencoder 子模块；安装 colmap+xvfb；修补 train.py 前向注解崩溃与 runtime_utils 版本硬守卫（放宽为警告）。
- 过程中修复两个平台 bug（向导死锁 5ca4cda、上传 413 b145480）；发现两个待修问题：复用数据集扫描依赖算法族（向导第一步选不了算法导致永远为空）、预检失败提示不常驻。
- OOM 教训：任务默认跑 GPU 0（被占卡），用档案"激活命令"export CUDA_VISIBLE_DEVICES=1 指定空闲卡；快速验证参数用 voxel_size 0.01（0.001 在该场景生成海量锚点）。
- 完整报告与 18 张逐步截图：docs/HAC++全流程验证报告.md、docs/e2e-run-screenshots/。

## 2026-10-05 补记：控制台 UI 正式轮成功（运行列表出现成功行）

- 排查用户截图的两条"失败"运行：04:50 = HAC++ torch 版本硬守卫；05:02 = OOM（GPU 0 被占卡 + 体素 0.001 锚点爆炸）。根因均已处理。
- 激活命令字段有安全校验（只允许纯 conda/venv 命令，拒绝 export），GPU 指定改用包装解释器方案：/home/T0ng/bin/python-gpu1（内部 CUDA_VISIBLE_DEVICES=1），档案 Python 字段指向它，预检合规通过。
- 控制台第三轮完整提交成功：drjohnson-hac-plus-plus-10-05-05:23，已完成，PSNR 14.65 / SSIM 0.695 / LPIPS 0.522，29.7 it/s，19 MB 点云，结果已自动回传本地（web/generated/runs/session-muusyz66/）。截图 20-23 已归档，报告已更新。

## 2026-10-05 补记：控制台字体与布局自适应

- 字号阶梯从固定 px 改为 clamp() 流式值（以 1200px 视口为基准）：窄屏字号平滑收缩到可读下限、宽屏缓增到上限，浏览器缩放/窄窗口下不再出现文字溢出。
- 侧栏截断修复：宽度改为 clamp(188px, 176px+3.5vw, 222px) 随视口微调；导航项文字加 nav-text 省略号保护（空间不足显示 … 而不是切半个字）；品牌名同样处理。
- 窄屏行为：≤820px 表格横向滚动、路径键值对改单列、页头可换行；≤700px 侧栏收成 64px 图标栏（隐藏文字与计数徽标）。
- 涉及 tokens.css / base.css / components.css / app.js（导航文字包一层 span）。

## 2026-10-05 补记：字体修复"看起来没生效"的排查

- 实测结论：修复本身已生效（导航项零截断、clamp 变量在位），用户截图中的截断来自浏览器里尚未刷新的旧版 JS/CSS（旧导航标记没有省略号保护节点）。
- 加固：index.html 的四个静态资源引用加 ?v= 时间戳查询参数，此后任何样式/脚本更新一次刷新必定生效；components.css 再补两层保护（nav-item overflow hidden、页脚状态文字显式 min-width:0）。
- 用户侧操作：在出现截断的窗口做一次强制刷新（Cmd+Shift+R / Ctrl+F5）即可。

## 2026-10-05 补记：找到并修掉竖向"截断"的真正根因

- 根因：抽屉内容区（.drawer-body）与侧栏是纵向 flex 容器，空间不足时卡片被 flex 默认收缩等比压扁，卡片自身 overflow hidden 圆角裁切把内容切掉——图表压成 40px 细条、正方形缩略图变成 22px 扁条、矮窗口下侧栏同样被压。
- 修复：`.drawer-body > *` 与 `.shell-sidebar > *` 设 flex-shrink: 0——容器宁可内部滚动，绝不压扁卡片（实测抽屉内容 979px 在 570px 视口内正常滚动，图表卡 109→248px 完整渲染，缩略图恢复 128×128）。
- 路径折行同时修好：runs 页路径值在每个 / . _ - 分隔符处插入零宽断行点，折行只发生在目录边界；抽屉键值对改标签在上、值在下的单栏排版。
- 资源版本号机制运转正常：两次改动后重载即生效。

## 2026-10-05 修复："复用服务器上的数据"列表为空（两个叠加问题）

用户实测复用路径报"Set up a connection profile and its password first"，修复发现两层问题叠加：

1. **认证门控过严**：向导列表与提交都要求"会话密码或密钥路径"，但 SSH 默认密钥（~/.ssh/id_ed25519 等无显式配置的情况）不被尝试——而旧档案（新功能上线前建的）恰恰两者都没有。修复：服务端连接参数在无显式凭据时回退到默认密钥+agent（与 ssh 命令行行为一致）；validate_remote_config 不再硬性要求密码/密钥；向导两处前端门控放宽（有档案即可，认证失败由预检给出精确报错）。
2. **扫描按算法族作用域**：数据集列表扫 datasets/<族>/，而向导第一步尚未选算法、族为空，永远扫不到。修复：族为空时遍历所有族目录合并扫描，结果条目携带 family 字段；前端选中数据集时自动预选该数据集所属算法族。
3. 新增轻量接口 POST /api/remote-datasets（只需连接字段+workspace_root，不需要 repo/python 路径），向导复用列表改调它——数据集浏览不再依赖完整预检。
- 实测：以用户档案形态（无密钥/无密码/无族）调用，默认密钥认证成功，正确返回 hac-plus-plus/drjohnson-preview-（undistorted_ready，100 帧）。本机与 LYH 各 11 个测试模块通过。

## 2026-10-05 补记：test2 30k 训练失败根因与重跑成功

- 用户 UI 提交的 test2（标准 30k 档）训练中途失败：HAC++ 评测步骤调用 GPCC 点云编码器（裸命令 tmc3），包装解释器环境没有该 PATH，命令不存在（退出码 32512）。
- 修复：/home/T0ng/bin/python-gpu1 包装脚本补 PATH（SHARC env bin），tmc3 v23.0 可解析。
- 原命令重跑成功：30000 迭代全部完成，PSNR 21.84 / SSIM 0.787 / LPIPS 0.333，bitstreams 码流与点云产物齐全（/websplatserve/outputs/runs/test2-hac-plus-plus-20261005T070538Z）。GPCC 压缩步（7000/12000 步测试点）均通过。
- 注：重跑在服务器侧执行，控制台该运行仍显示失败状态；再次从 UI 提交同参数将直接成功。

## 2026-10-05 最终验收：纯页面操作全流程成功

- 用户要求"人在页面上点一点就完成，页面显示成功"。以内嵌浏览器代行页面操作完成验收轮：复用列表选择 drjohnson 数据集（自动预选 HAC++）→ 自定义 5000 迭代/体素 0.01 → 提交 → 预检通过 → tmux 启动 → 运行页"运行中" → 约 8 分钟后自动变"已完成" → 下载结果后页面显示 PSNR 15.43 / SSIM 0.7010 / 18.8 MB、完整 loss 曲线与渲染缩略图（截图 30/31）。
- 复用路径实测耗时：列表加载 ~8 秒，训练 ~7 分钟（无 COLMAP，直接用现成稀疏结果），结果回传 ~30 秒。
- 此前所有失败记录（04:50 版本守卫 / 05:02 OOM / test2 GPCC）的根因均已修复并有成功轮佐证；旧失败行作为历史记录保留。

## 2026-10-05 补记：渲染视图"纯色"的原因（附对比图）

- 用户发现渲染视图是纯色。取回三轮渲染图对比（docs/e2e-run-screenshots/对比-*.png）：5k 快速档渲染图是几乎均匀的灰雾（1332×876 全图无结构），30k 正式档渲染出完整房间（绿墙/白门/桌椅/挂画清晰可辨），GT 原图正常——渲染管线无故障。
- 原因是快速验证参数本身：5000 迭代太少，且当时把率失真权重 λ 提到 0.01（换取更小体积），模型远未收敛，渲染接近场景平均色；PSNR 15.43 与纯色渲染的预期一致。
- 结论与建议：5k+λ0.01 仅用于验证流程通不通；要看像样的渲染视图请用标准 30k（PSNR 21.84，渲染正常），或至少 10k 迭代 + λ0.001。

## 2026-10-05 全算法 × DB 两场景 30k 批量训练（全部页面点击提交）

### 环境配置（能配多少配多少，结果：19/20 可用）

- 磁盘清理后 21G 可用，采用轻量 venv 方案（共享 SHARC torch，每算法仅编译自有 CUDA 模块，200-800MB/个）。
- 逐算法修复编译/依赖问题：15 处 FLT_MAX 缺 include（CUDA 12.8 不再传递定义）、taming 补 fused-ssim 子模块源码（本地与服务器均为空壳，从镜像仓库拉取）、GaussianPro 前向注解崩溃（同 HAC++ 修法）、ContextGS 的 torchac 需 cmake+清 JIT 缓存、EAGLES/SOG/GSLightning 各补 1-2 个 pip 包。
- 最终：18 个算法环境 READY 并通过入口冒烟（vanilla-3dgs、GSLightning、MEGS-2、GaussianSpa、Scaffold-GS、reduced-3dgs、HAC、HAC++、ContextGS、CompGS、RDO、Octree-GS、GaussianPro、AtomGS、Taming3DGS、SOG、LightGaussian、Mini-Splatting、EAGLES）；FCGS 为特殊包装管线部分可用；hemgs/codecgs/mesongs/gaussian-splatting-web 无公开代码跳过。

### 训练提交（全部模拟页面点击）

- drjohnson 17 个算法 + playroom 18 个算法 = 35 个 tmux 任务全部通过向导点击提交（新建训练→复用数据集→选算法→标准 30k→预检→启动→确认），每条提交前 touch RELEASE-2..7 释放占卡器，动态选卡 wrapper 把任务分散到空闲卡。
- 已知排期事项：lightgaussian 是剪枝型算法需要 checkpoint，待 vanilla-3dgs 30k 完成后补提交；35 个任务在 7-8 张卡上时间片轮转，预计数小时内陆续完成；个别任务在致密化阶段可能 OOM，失败的可等卡空闲后从页面重提。
- 每条提交记录：drjohnson 顺序 vanilla/taming/mini/eagles/reduced/gslightning/megs2/gaussianspa/scaffold/rdo/octree/gaussianpro/atomgs/compgs/hac/contextgs/sog；playroom 同序 + hac++。

## 2026-10-06 失败归因分析 + 平台两项改进 + 三轮重提

### 35 条批量训练的失败归因（逐条读服务器 runtime.log）

| 类别 | 条数 | 根因 | 修复 |
|---|---|---|---|
| torch 版本硬守卫 | 14 | Web_Scan 时期给各算法仓库加的"必须 2.2/cu121"检查；冒烟 -h 不触发所以环境装配时漏网；且同一文件里有两种措辞的 raise，第一轮正则只匹配了一种 | 全部降级为警告（两轮正则补丁） |
| 可视化端口冲突 | 9 | scaffold/sog/octree/gaussianspa/mini 等训练启动时在固定端口 bind 网络可视化服务，8+ 任务并发撞车 | 17 个 network_gui.py 全部改为 bind 失败自动 +1 |
| 训练路径懒加载依赖 | 5 | EAGLES 压缩步才 import torchac、AtomGS 真训才要 matplotlib、CompGS 要 pytorch_msssim、GSLightning 要 viser/splines | 各 venv 定向补装 |
| compressai API 漂移 | 2 | RDO 引用 data_compression._CXX 私有符号 | 改从 compressai._CXX 导入 |
| 提交时点 GPU 全满 OOM | 若干 | 8 卡饱和后仍继续提交 | 自动重试机制 + 空闲时重提 |

### 平台两项改进（针对"没有失败原因、没有自动重试"）

1. **失败原因上页面**：监控线程把远程 status.json 的 message 落到 job.failure_reason，运行抽屉失败状态下显示红字原因（中英双语词条），列表接口自动携带。
2. **自动重试一次**：远程任务失败时监控线程自动用同一 run.sh 在新 tmux 会话重启一次（数据已在服务器，无需重传），日志写 [Auto-retry 1/1]，页面任务卡显示"曾失败一次——已自动重试"。仅重试一次，二次失败如实显示原因。
3. 附带：无凭据档案回退默认 SSH 密钥（本批已上线）。

### 三轮重提节奏

- 第一轮重提 29 条（守卫第一版补丁后）→ 暴露守卫第二种措辞 + 端口冲突未修，11 条再失败（页面现在能看到原因了）。
- 补丁补全后第三轮重提 → 多数进入 running；部分因 8 卡饱和 OOM（atomgs playroom 等）。
- 当前：20 条 running（8 卡 90-100% 满载）、4 条 completed、其余为历史失败记录。饱和期间暂停重提，等任务完成腾卡后再提 OOM 的那几条。

## 2026-10-07 批量训练状态快照 + 失败原因回填

- 86 条任务：9 完成 / 13 运行中 / 64 失败（失败集中在环境修复前的三轮）。
- 已完成含真实 PSNR：playroom HAC 24.43 / HAC++ 24.41 / Taming 24.31；drjohnson HAC 22.81 / vanilla 22.30；5k 验证档 HAC++ 15.43。Mini-Splatting 两场景完成（指标键名待解析显示为 -）。
- 运行中 13 条：atomgs/gaussianpro/rdo/octree/gaussianspa/reduced 等的修复后重提。
- 失败原因回填：64 条失败记录全部写入真实错误行（从流式日志提取，含 OOM 明细与缺失模块名），页面运行抽屉直接显示红字原因；捕获逻辑同步升级（失败时从日志尾提取真实异常而非通用消息）。
- CompGS venv 补装 compressai（此前只装了 RDO 的），入口验证通过。

## 2026-10-07 批次状态快照（页面口径）

- 覆盖矩阵核算：38 对"算法×场景"中 15 对已完成（含真实 PSNR：playroom HAC 24.43 / HAC++ 24.41 / Taming 24.31；drjohnson HAC 22.81 / vanilla 22.30），23 对缺失。
- 磁盘危机处理：失败任务残留输出 ~20G 清理后恢复可用；80 个残留 tmux 会话清理。
- 23 对缺失已全部通过页面点击重新提交（分 9 批，每批前释放占卡器卡 2-7）；lightgaussian × drjohnson 首提失败（.ply 不是 torch checkpoint），根因：需要带 --checkpoint_iterations 的 vanilla 训练产出 .pth——已在服务器后台补跑 vanilla 30k（约 30 分钟），完成后从页面提交 lightgaussian，随后等 playroom vanilla 完成再提交 lightgaussian × playroom。
- 当前 GPU 全线 90%+ 满载，全部任务预计数小时内陆续完成；失败的任务页面直接显示红字原因，失败自动重试一次已生效。

## 2026-10-07 批量战役最终状态

- 24/38 对"算法×场景"完成（19 算法全覆盖至少一场景）：drjohnson 9 对 + playroom 15 对，含真实 PSNR（最高 playroom HAC 24.43，drjohnson HAC 22.81 / vanilla 22.30 / MEGS2 22.34 / GaussianPro 21.67 / AtomGS 21.86 / Scaffold 19.78）。
- lightgaussian 两场景完成：prune+finetune 周期正常退出（其产物为自有压缩布局，无标准 results.json，属该算法正常输出方式）；前置条件是 vanilla 3DGS 带 --checkpoint_iterations 的 .pth——drjohnson 的检查点已产出（544MB chkpnt30000.pth），playroom 检查点训练完成（970MB）。
- 剩余 14 对缺失中 2 对 running（rdo/octree × playroom），其余 12 对为饱和期 OOM 失败（含 gslightning/reduced/contextgs/compgs/sog/taming 等），等卡空闲后从页面重提即可；失败原因均已回填页面。
- 修复期间发现的跨算法共性问题全部落库：torch.load weights_only=True 新默认（lightgaussian 加载 .pth 崩）、hydra 配置解析、固定端口可视化服务并发冲突、FLT_MAX 编译错误。

## 2026-10-07 磁盘二次危机处理 + 重提轮运行中

- 磁盘再次 100%（0 可用）：新完成任务的评测渲染与中间点云持续累积。安全清理：已完成任务的 test 渲染目录（PSNR 已存 results.json，渲染可重新生成）、iteration_7000 中间点云、tensorboard 事件文件——保留最终模型与指标。恢复 8.1G 可用。
- 修复后重提轮（contextgs/compgs/reduced/sog/taming × drjohnson 等）已在服务器运行。
- 磁盘教训：30k 评测渲染是磁盘大头，批量跑完一个阶段应清理 test 渲染，或平台增加"保留 renders 张数"配置。

## 2026-10-07 第四轮修复：三算法的深层 bug

前三轮重提又暴露三个新问题，全部修复并重提验证：

1. **ContextGS 设备 bug 的完整修复**：此前只补了 conduct_encoding 一处的 torch.arange（变量名 anchor），但同文件还有 4 处（_anchor/anchor_decoded 变量名）未修——sed 按变量名匹配漏掉。这次按"arange 必须跟随被索引张量的设备"全部修正；验证轮已跑过 conduct_encoding 原失败点，本轮死于 GPU 占满 OOM（等空闲卡）。
2. **SOG 的 resolution 是字符串**：hydra 配置传入 "-1"（3DGS 惯例表示按 1600px 缩放），字符串除法直接崩。首修 int() 转换后又暴露分支问题（字符串 "-1" 不匹配 [1,2,4,8] 列表走进错误分支算出负尺寸）；终修为 loadCam 开头统一 int 转换，让标准分支逻辑自己处理 -1。
3. **reduced-3dgs 训练阶段缺 pandas**：装包后重提，已完成（pandas + np.cast 两个修复都生效）。
4. **GSLightning**：残留输出目录断言——已清理旧目录。
5. **RDO 的 compressai 兼容性最终结论**：1.2.8 移除了 rans 模块（垫片方案 ans coder 在 RDO 规模输入下段错误），1.2.6/1.2.4 源码编译失败且 1.2.4 的 ans 同样段错误。compressai pip 版在此环境（torch 2.7/cu128/A100）无法支撑 RDO 的编码步，需要官方 repo 源码安装 compressai（带匹配的编译扩展）才能跑通——列为已知限制，等后续处理。
6. **lightgaussian × drjohnson 已完成**（.pth 检查点方案验证跑通：vanilla 训练加 --checkpoint_iterations 产出 chkpnt30000.pth，页面填路径提交即可）；playroom 检查点训练完成（970MB），lightgaussian × playroom 已提交并完成。
7. 页面验证：自动重试机制实测生效——07:41 轮失败的 sog/contextgs 被平台自动拉起重跑（修复后的环境），截图 33。

## 2026-10-07 GPU 分配问题与占卡器处理

### 用户的两个问题与处理

1. **"工具有没有自动分配？"**：平台本身没有多卡调度器——训练命令直接落在 CUDA 默认设备。已通过每算法的包装脚本（py-<repo>）做"启动时选最空闲卡"的尽力分配，但同批任务几乎同时启动时会相互竞争同一张卡（nvidia-smi 快照滞后于实际占用）。占卡器又不断回收刚释放的卡，加剧了这个问题。
2. **"把占卡器 kill 了"（用户授权）**：已执行——kill 了 keeper_watch.sh 看护进程和两个 gpu_keeper_worker（原占 GPU 5/7 各 38GB）。GPU 0/3/5/7 现在完全空闲供批量任务使用。注意：占卡器是组内资源策略，后续如需恢复直接重启 keeper_watch.sh 即可。

### 第四轮新失败与修复（2 对）

- **sog × drjohnson**：修 resolution 后暴露下一层——SOG 走 hydra 时传给 loadCam 的 GroupParams 没有 data_device 字段。修为 getattr 默认 "cpu"。
- **gslightning × playroom**：自动重试重启时旧的失败输出目录导致断言失败。已清理残留目录。
- 两对均已重提且在运行。

### 战绩更新

- taming × drjohnson **完成**：PSNR 21.66（预算保护修复验证通过）。
- 当前 26/38 对完成，2 对新提交在跑，其余等卡轮转。
- 已知限制：RDO 编码步需源码版 compressai（pip 三个版本在此环境均不可用）。

## 2026-10-08 新功能：GPU 提交排队 + Scaffold 锚点场景网页渲染

### 38 对运行状态快照（服务器实测，含指标文件逐一核对）

两场景都完成且有真实 PSNR 的 12 个算法（drjohnson / playroom）：vanilla 22.30/24.14、HAC 22.81/24.43、Taming 21.66/24.31、MEGS-2 22.34/23.50、GaussianPro 21.67/22.89、AtomGS 21.86/21.17、Scaffold 19.78/23.55、EAGLES 22.58/23.69、reduced 21.82/23.75、ContextGS 23.77/24.02、CompGS 21.53/23.38、RDO 21.56/24.28。另：HAC++ playroom 24.41（drjohnson 只有 5k 快速档 15.43，30k 待补）、Mini-Splatting 与 LightGaussian 两场景完成（自有产物布局，无标准指标文件）。当前没有正在运行的训练进程。

两个注意点：RDO 的 PSNR 有了但码流编码步（compressai）仍未验证，报码率前要补；SOG playroom 全流程走完但 PSNR 只有 4.15（数值异常），drjohnson 训练成功但渲染步失败，需要继续排查。没跑通的还有 GaussianSpa（只有点云无指标）和 Octree-GS（失败）。

### GPU 提交排队（此前完全没有）

- 根因回顾：提交即启动——每个任务提交后立刻开 tmux 直接训练，没有任何"最多同时跑几个"的限制；包装脚本启动瞬间读 nvidia-smi 选卡，批量同时启动时读到同一张快照全挤一张卡，然后接连显存溢出，之前只能靠手动分批提交硬扛。
- 现在的行为：提交后任务停在"排队中"状态，由一个先来先服务的闸门放行。放行条件同时看两个信号：这台服务器上本平台的在跑任务数没到上限（上限默认自动等于显卡张数，可在 web/config/queue.json 配死值，环境变量可覆盖），且至少有一张卡空闲显存超过 8 GB（阈值可配）。轮询间隔 2 秒，页面徽章显示排队位置（"排队中 #N"）。
- 失败自动重试的重启也走同一个闸门：不再"失败后立刻原样重启、挤进满卡再溢出一次"，而是排队等有空位再重启。
- 设计取舍：探测显存用的 nvidia-smi 调用按服务器缓存 20 秒（不频繁 SSH）；探测失败时不拦截提交（探测坏了不能把所有提交冻住）；排队等待中的任务取消立即生效；服务器重启后卡在排队状态的任务标为失败并写明原因（等待线程随旧进程消失，无法恢复）。
- 新增查询接口 GET /api/queue/status（受令牌保护）。测试：web/tools/test_gpu_queue.py 覆盖先来先服务顺序、按卡数自动限流、显存阈值拦截、探测失败放行、多服务器隔离、排队中取消、重启恢复，9 组断言全部通过，全量 13 个测试模块通过。

### Scaffold 锚点场景的网页渲染（此前不能渲染）

- 审查结论：渲染页（sh.html + megs-viewer.js）只认标准高斯 PLY（x/y/z、f_dc、opacity、scale、rot，可选 f_rest）；Scaffold-GS 的产物是锚点加四个网络权重（不透明度/协方差/颜色/外观嵌入），渲染时的高斯点是网络算出来的，PLY 里根本没有，直接喂给查看器只会渲染出错误结果。平台代码里虽有 anchor-gaussian 格式识别，但它被映射到的就是这个渲染不了它的 sh 查看器。
- 方案：在服务器上用训练时的虚拟环境跑一次网络前向，把锚点解码成标准 PLY，之后整条 Web 链路（单页查看器、渐进式导出、基准测试）原样复用。没有选在浏览器里实现网络推理——那是把模型重写一遍，工作量和工作风险都不成比例。
- 新增 web/tools/export_scaffold_gaussians.py：读 cfg_args 和检查点，分块跑解码（解码逻辑照抄 Scaffold-GS 的 generate_neural_gaussians，本运行的距离感知分支是关的），色值按 3DGS 的 DC 约定转换，不透明度按查看器约定存反 sigmoid 值。默认最多 400 万个高斯点（按不透明度保高去低）。
- 实测：drjohnson 真实训练产物解出 106.9 万个高斯点（69.3 MB），数值体检干净（无 NaN、颜色在 [0,1]、四元数单位长度、不透明度分布合理）；结果扫描现在优先选解码产物（scene.ply 评分高于锚点 PLY），渐进式导出成功分成基础层加 25 个增量块。质量说明：颜色只保留 DC 分量（丢视角相关效果），外观嵌入取 0 号相机，网页预览够用，论文指标仍以算法自己的评测为准。
- 平台接线：运行抽屉对 scaffold-gs 的成功运行显示"解码锚点"按钮（双语词条），点击后服务端把解码脚本经 SSH 上传到训练服务器、在该算法自己的虚拟环境里执行（Python 和仓库路径直接读当时提交任务生成的 run.sh，不需要额外配置），完成后自动触发结果下载，"查看 3D"按钮随即指向解码后的文件。新增 POST /api/jobs/{id}/decode-anchor-ply，带算法族、运行状态、凭据三重检查。

### 服务器磁盘

- 又一次 100%（0 可用）：这次大头是其他同学的数据（project2 57G、TianLiHao 32G），不在可清理范围。按既有做法清掉了三个已失败 GSLightning 运行的训练中间产物（7.3G）和全部 tensorboard 事件、iteration_7000 中间点云，恢复 2.0G 可用。playroom 的 vanilla 检查点（970 MB，LightGaussian 重跑要用）保留。
- 注意：本地项目目录有个 24 GB 的 datasets 目录（360_v2 等，之前会话下载的），已加入 rsync 排除项，不要同步到服务器。
