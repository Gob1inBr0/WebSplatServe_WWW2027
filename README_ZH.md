# WebSplatServe_WWW2027

> English: [README.md](README.md)

WebSplatServe 是面向 WWW 2027 Industry Track，对原 `Web_Scan-feat-survey-algorithms` 网络平台的重构版本。它保留了原有的浏览器工作台、Python API 服务、适配器注册表、远程执行流程、遥测存储和渐进式查看器，并新增了一层 Web 原生的自适应 3D 高斯分发服务。

## 论文定位

系统的目标一句话：

> 面向异构 Web 客户端的自适应 3D 高斯分发与渲染。

与原来用于实验的 Web-Scan 工作台相比，本版本聚焦在真正部署上线的 Web 侧流程：

1. 把训练好/压缩后的高斯场景转换成清单文件（manifest）、基础层和可叠加的数据块。
2. 先分发基础层，让浏览器在完整场景下载完成之前就能开始渲染。
3. 依据网络带宽、视口、FPS/P95 帧时间和内存预算等信号挑选后续精细化数据块。
4. 记录匿名的线上运行遥测，作为 Industry Track 的证据。
5. 评估 TTFR（首次渲染时间）、可交互时间、传输字节数、数据块到达过程、FPS/P95 帧时间、内存、缓存行为和失败率。

## 新增代码结构

```text
WebSplatServe_WWW2027/
  README.md
  summary.md
  scripts/
    01_preflight.ps1
    02_start_server.ps1
    03_print_training_console.ps1
    04_export_scene.ps1
    05_run_scheduler_simulation.ps1
    06_run_policy_benchmark.ps1
    07_print_browser_benchmark_urls.ps1
    08_export_deployment_evidence.ps1
    09_run_all_local_checks.ps1
    10_smoke_local_pipeline.ps1
  web/
    serving/
      manifest.py                 # Web 原生清单文件的规范化与校验辅助
      adaptive_scheduler.py       # 带宽 / 视口 / GPU / 联合策略的数据块调度器
      manifest_schema.json        # 论文产物的 JSON schema
    tools/
      export_websplatserve_assets.py   # PLY -> 基础层/精细化数据块 + 增强清单
      run_serving_benchmark.py         # 多策略网络仿真
      collect_deployment_evidence.py   # 遥测汇总 -> 论文可用的 markdown
      test_websplatserve_scheduler.py  # 新调度器与清单层的单元测试
    config/
      websplatserve_profiles.json      # 设备、网络与策略矩阵
    docs/
      EXPERIMENT_PLAN.md
      RUN_CHECKLIST.md
    viewers/
      benchmark.html                   # 同源浏览器 QoE 基准测试页
```

原平台拷贝过来的 `web/server`、`web/console`、`web/viewers` 和既有的 `web/tools/export_web_assets.py` 全部保留，因此原有的远程训练和渐进式查看器行为不受影响。

## 环境准备

本地 Web 服务：

```bash
python -m pip install paramiko numpy
```

真正要跑 3DGS 训练/压缩时，在 GPU 机器上按所选算法仓库自带的 `setup_env.sh` 配置环境，与原 Web-Scan 流程相同。本仓库不重复收纳庞大的算法仓库。

## 带编号的运行脚本

所有运行脚本都在 `scripts/` 目录下，按执行顺序编号：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/01_preflight.ps1
powershell -ExecutionPolicy Bypass -File scripts/02_start_server.ps1
powershell -ExecutionPolicy Bypass -File scripts/03_print_training_console.ps1
powershell -ExecutionPolicy Bypass -File scripts/04_export_scene.ps1 -PlyPath "C:\path\to\scene.ply" -SceneId scene_a
powershell -ExecutionPolicy Bypass -File scripts/05_run_scheduler_simulation.ps1 -SceneId scene_a
powershell -ExecutionPolicy Bypass -File scripts/06_run_policy_benchmark.ps1 -SceneId scene_a
powershell -ExecutionPolicy Bypass -File scripts/07_print_browser_benchmark_urls.ps1 -SceneId scene_a
powershell -ExecutionPolicy Bypass -File scripts/08_export_deployment_evidence.ps1
```

可选的本地校验脚本：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/09_run_all_local_checks.ps1
powershell -ExecutionPolicy Bypass -File scripts/10_smoke_local_pipeline.ps1
```

## 训练流程

沿用原有的 Web-Scan 远程训练流程：

```bash
cd WebSplatServe_WWW2027
python web/server/api_server.py --host 127.0.0.1 --port 8080
```

打开：

```text
http://127.0.0.1:8080/web/console/
```

然后：

1. 在控制台配置一台远程 GPU 服务器。
2. 选择一个已支持的适配器，例如 vanilla 3DGS、HAC++、ContextGS、CompGS、FCGS 或其他已配置的后端。
3. 上传/拍摄图像，或复用服务器上已有的数据集。
4. 运行远程环境预检。
5. 提交训练/压缩任务。
6. 下载得到的 PLY 或模型输出。

## WebSplatServe 导出

训练产出标准的二进制小端序、带 SH 字段的 3DGS PLY 之后：

```bash
cd WebSplatServe_WWW2027
python web/tools/export_websplatserve_assets.py /path/to/scene.ply web/generated/websplatserve/scene_a --source-backend vanilla-3dgs
```

输出文件：

- `manifest.json`：旧版渐进式查看器的清单。
- `websplatserve_manifest.json`：增强版清单，用于调度实验和论文产物。
- `base.bin`：首个渲染层。
- `q*_*.bin` 和 `*.sh.bin`：可叠加的几何/外观精细化数据块。

## 运行查看器

启动服务：

```bash
python web/server/api_server.py --host 127.0.0.1 --port 8080
```

打开一个渐进式场景：

```text
http://127.0.0.1:8080/web/viewers/progressive.html?url=/web/generated/websplatserve/scene_a/manifest.json&policy=joint
```

可用的查看器策略：

```text
naive, bandwidth, viewport, gpu, joint, full
```

## 测试

只运行新的调度器测试：

```bash
python web/tools/run_tests.py websplatserve
```

运行当前提交前的校验集：

```bash
python web/tools/run_tests.py websplatserve telemetry web_export
```

运行继承下来的完整测试集：

```bash
python web/tools/run_tests.py
```

## 基准测试

仿真单个策略：

```bash
python web/serving/adaptive_scheduler.py web/generated/websplatserve/scene_a/websplatserve_manifest.json --policy joint --bandwidth-mbps 10 --rtt-ms 60 --out-csv web/generated/experiments/joint_trace.csv
```

在多种网络设置下运行论文所需的全部基线：

```bash
python web/tools/run_serving_benchmark.py web/generated/websplatserve/scene_a/websplatserve_manifest.json --out web/generated/experiments/serving_benchmark.csv
```

在真实浏览器里采集 QoE 轨迹：

```text
http://127.0.0.1:8080/web/viewers/benchmark.html?url=/web/generated/websplatserve/scene_a/manifest.json&seconds=12
```

该浏览器测试页会记录 TTFR、传输字节数、已驻留行数、数据块到达、FPS/P95 帧时间、客户端情况、设备能力和失败阶段。它刻意不做图像质量评估。

## 部署证据

继承来的服务已经在 `web/generated/telemetry/` 下记录匿名遥测，并提供 `/api/telemetry/summary` 接口。把该 JSON 保存下来并转成论文备注：

```bash
python web/tools/collect_deployment_evidence.py telemetry_summary.json --out deployment_evidence.md
```

或者使用带鉴权的服务端接口：

```text
GET /api/telemetry/evidence.md
```

遥测策略保持保护隐私：不记录 IP 地址、原始 User-Agent 字符串、原始场景名或用户内容。
