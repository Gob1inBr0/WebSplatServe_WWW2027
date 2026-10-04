# WebSplatServe Run Scripts

Run scripts from the project root:

```powershell
cd WebSplatServe_WWW2027
```

Recommended order:

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

Optional all-in-one local validation:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/09_run_all_local_checks.ps1
powershell -ExecutionPolicy Bypass -File scripts/10_smoke_local_pipeline.ps1
```

## macOS / Linux (bash)

Every script has a `.sh` twin with the same behavior. The interpreter defaults to `python3`; override it with the `PYTHON` environment variable or the `--python` flag.

```bash
cd WebSplatServe_WWW2027
bash scripts/01_preflight.sh
bash scripts/02_start_server.sh
bash scripts/03_print_training_console.sh
bash scripts/04_export_scene.sh --ply /path/to/scene.ply --scene-id scene_a
bash scripts/05_run_scheduler_simulation.sh --scene-id scene_a
bash scripts/06_run_policy_benchmark.sh --scene-id scene_a
bash scripts/07_print_browser_benchmark_urls.sh --scene-id scene_a
bash scripts/08_export_deployment_evidence.sh
bash scripts/09_run_all_local_checks.sh
bash scripts/10_smoke_local_pipeline.sh
```

Notes:

- PowerShell scripts use `-Named` parameters; bash scripts use `--flag value` parameters.
- `02_start_server.sh` background-starts the server with `nohup` and logs to `web/generated/server.log`; port detection uses `lsof` (macOS default) with `ss`/`netstat` fallbacks, and health checks use `curl`.

Notes:

- `02_start_server.ps1` starts the local API/static server.
- `03_print_training_console.ps1` prints the remote training console URL. Actual training still needs GPU credentials and adapter choices in the Web UI.
- If you already have a standard SH PLY, start at `04_export_scene.ps1`.
- Browser QoE benchmark does not run image-quality evaluation.
- `10_smoke_local_pipeline.ps1` generates a synthetic SH PLY under `%TEMP%`, exports assets there, and runs scheduler/benchmark scripts without requiring a real scene or write access to `web/generated`.
