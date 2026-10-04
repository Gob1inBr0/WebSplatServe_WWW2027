# WebSplatServe Run Checklist

## 0. Numbered Scripts

The root `scripts/` directory contains the ordered run scripts:

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

Recommended PowerShell order:

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

## 1. Pre-run Validation

Run the focused tests that cover the new WWW Industry serving code:

```bash
python web/tools/run_tests.py websplatserve telemetry web_export
```

Run syntax checks without writing `__pycache__` into the source tree:

```bash
python -X pycache_prefix=%TEMP%/websplatserve_pycache -m py_compile web/serving/manifest.py web/serving/adaptive_scheduler.py web/serving/backend_profiles.py web/tools/export_websplatserve_assets.py web/tools/run_serving_benchmark.py web/tools/collect_deployment_evidence.py web/tools/test_websplatserve_manifest.py web/tools/test_websplatserve_scheduler.py web/server/telemetry.py web/server/api_server.py
```

## 2. Export A Scene

After a backend produces a standard SH PLY:

```bash
python web/tools/export_websplatserve_assets.py /path/to/scene.ply web/generated/websplatserve/scene_a --backend-profile vanilla-3dgs-sh
```

Use one of:

- `vanilla-3dgs-sh`
- `compressed-decoded-sh`
- `compact-pruned-sh`

## 3. Run Server

```bash
python web/server/api_server.py --host 127.0.0.1 --port 8080
```

Open:

```text
http://127.0.0.1:8080/web/console/
```

## 4. Run Viewer And Browser QoE Benchmark

Single viewer:

```text
http://127.0.0.1:8080/web/viewers/progressive.html?url=/web/generated/websplatserve/scene_a/manifest.json&policy=joint&profile=auto
```

Browser QoE benchmark:

```text
http://127.0.0.1:8080/web/viewers/benchmark.html?url=/web/generated/websplatserve/scene_a/manifest.json&seconds=12
```

The browser benchmark records TTFR, downloaded bytes, resident rows, chunk arrivals, FPS/P95 frame time, client profile, browser capability and failure stage. It does not perform image-quality evaluation.

## 5. Export Deployment Evidence

Authenticated endpoint:

```text
GET /api/telemetry/evidence.md
```

Offline from a saved telemetry summary:

```bash
python web/tools/collect_deployment_evidence.py telemetry_summary.json --out deployment_evidence.md
```
