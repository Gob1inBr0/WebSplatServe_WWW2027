# WebSplatServe 运行清单

> English: [RUN_CHECKLIST.md](RUN_CHECKLIST.md)

## 0. 带编号的脚本

根目录 `scripts/` 下是按顺序编号的运行脚本：

```text
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
```

推荐的 PowerShell 执行顺序：

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

## 1. 运行前校验

运行覆盖新的 WWW Industry 分发代码的专项测试：

```bash
python web/tools/run_tests.py websplatserve telemetry web_export
```

做语法检查，且不在源码树里写 `__pycache__`：

```bash
python -X pycache_prefix=%TEMP%/websplatserve_pycache -m py_compile web/serving/manifest.py web/serving/adaptive_scheduler.py web/serving/backend_profiles.py web/tools/export_websplatserve_assets.py web/tools/run_serving_benchmark.py web/tools/collect_deployment_evidence.py web/tools/test_websplatserve_manifest.py web/tools/test_websplatserve_scheduler.py web/server/telemetry.py web/server/api_server.py
```

## 2. 导出场景

后端产出标准 SH PLY 之后：

```bash
python web/tools/export_websplatserve_assets.py /path/to/scene.ply web/generated/websplatserve/scene_a --backend-profile vanilla-3dgs-sh
```

`--backend-profile` 可选其一：

- `vanilla-3dgs-sh`
- `compressed-decoded-sh`
- `compact-pruned-sh`

## 3. 启动服务

```bash
python web/server/api_server.py --host 127.0.0.1 --port 8080
```

打开：

```text
http://127.0.0.1:8080/web/console/
```

## 4. 运行查看器与浏览器 QoE 基准

单个查看器：

```text
http://127.0.0.1:8080/web/viewers/progressive.html?url=/web/generated/websplatserve/scene_a/manifest.json&policy=joint&profile=auto
```

浏览器 QoE 基准：

```text
http://127.0.0.1:8080/web/viewers/benchmark.html?url=/web/generated/websplatserve/scene_a/manifest.json&seconds=12
```

浏览器基准会记录 TTFR、下载字节数、驻留行数、数据块到达、FPS/P95 帧时间、客户端情况、浏览器能力和失败阶段。它不做图像质量评估。

## 5. 导出部署证据

带鉴权的接口：

```text
GET /api/telemetry/evidence.md
```

离线方式，基于已保存的遥测汇总：

```bash
python web/tools/collect_deployment_evidence.py telemetry_summary.json --out deployment_evidence.md
```
