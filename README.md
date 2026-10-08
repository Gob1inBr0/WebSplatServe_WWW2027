# WebSplatServe_WWW2027

> 中文版：[README_ZH.md](README_ZH.md)

WebSplatServe is a WWW 2027 Industry Track oriented rebuild of the original `Web_Scan-feat-survey-algorithms` web platform.  It keeps the old browser workbench, Python API server, adapter registry, remote execution flow, telemetry store and progressive viewer, then adds a Web-native serving layer for adaptive 3D Gaussian delivery.

## Paper Positioning

The system target is:

> Adaptive 3D Gaussian delivery and rendering for heterogeneous Web clients.

Compared with the original Web-Scan experiment workbench, this version focuses on the deployed Web path:

1. Convert trained/compressed Gaussian scenes into a manifest, base layer and additive chunks.
2. Serve the base layer first so the browser can render before the complete scene is downloaded.
3. Select refinement chunks with network, viewport, FPS/P95 frame time and memory-budget signals.
4. Record anonymous deployment telemetry for Industry Track evidence.
5. Evaluate TTFR, time-to-interactive, bytes, chunk arrivals, FPS/P95 frame time, memory, cache behavior and failure rates.

## New Code Layout

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
      manifest.py                 # Web-native manifest normalization and validation helpers
      adaptive_scheduler.py       # bandwidth / viewport / GPU / joint chunk scheduler
      manifest_schema.json        # JSON schema for paper artifacts
    tools/
      export_websplatserve_assets.py   # PLY -> base/refinement chunks + enriched manifest
      run_serving_benchmark.py         # multi-policy network simulation
      collect_deployment_evidence.py   # telemetry summary -> paper-ready markdown
      test_websplatserve_scheduler.py  # unit tests for new scheduler and manifest layer
    config/
      websplatserve_profiles.json      # device, network and policy matrix
    docs/
      EXPERIMENT_PLAN.md
      RUN_CHECKLIST.md
    viewers/
      benchmark.html                   # same-origin browser QoE benchmark harness
```

The copied `web/server`, `web/console`, `web/viewers` and existing `web/tools/export_web_assets.py` are retained from the old Web-Scan platform so existing remote training and progressive viewer behavior still works.

## Environment

Local web server:

```bash
python -m pip install paramiko numpy
```

For actual 3DGS training/compression, configure the chosen algorithm repository with its own `setup_env.sh` on the GPU machine, as in the original Web-Scan workflow.  This rebuild does not duplicate the large algorithm repositories.

## Numbered Run Scripts

All run scripts are under `scripts/` and are numbered by execution order:

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

Optional local validation wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/09_run_all_local_checks.ps1
powershell -ExecutionPolicy Bypass -File scripts/10_smoke_local_pipeline.ps1
```

## Training Flow

Use the existing Web-Scan remote training pipeline:

```bash
cd WebSplatServe_WWW2027
python web/server/api_server.py --host 127.0.0.1 --port 8080
```

Open:

```text
http://127.0.0.1:8080/web/console/
```

Then:

1. Configure a remote GPU server in the console.
2. Select a supported adapter such as vanilla 3DGS, HAC++, ContextGS, CompGS, FCGS or another configured backend.
3. Upload/capture images or reuse an existing remote dataset.
4. Run remote precheck.
5. Submit the training/compression job.
6. Download the resulting PLY or model output.

## WebSplatServe Export

After training produces a standard binary little-endian 3DGS PLY with SH fields:

```bash
cd WebSplatServe_WWW2027
python web/tools/export_websplatserve_assets.py /path/to/scene.ply web/generated/websplatserve/scene_a --source-backend vanilla-3dgs
```

Outputs:

- `manifest.json`: legacy progressive viewer manifest.
- `websplatserve_manifest.json`: enriched manifest for scheduler experiments and paper artifacts.
- `base.bin`: first render layer.
- `q*_*.bin` and `*.sh.bin`: additive geometry/appearance refinement chunks.

## Run The Viewer

Start the server:

```bash
python web/server/api_server.py --host 127.0.0.1 --port 8080
```

Open a progressive scene:

```text
http://127.0.0.1:8080/web/viewers/progressive.html?url=/web/generated/websplatserve/scene_a/manifest.json&policy=joint
```

Available viewer policies:

```text
naive, bandwidth, viewport, gpu, joint, full
```

## Test

Run only the new scheduler tests:

```bash
python web/tools/run_tests.py websplatserve
```

Run the current pre-run validation set:

```bash
python web/tools/run_tests.py websplatserve telemetry web_export
```

Run the full inherited test suite:

```bash
python web/tools/run_tests.py
```

## Benchmark

Simulate a single policy:

```bash
python web/serving/adaptive_scheduler.py web/generated/websplatserve/scene_a/websplatserve_manifest.json --policy joint --bandwidth-mbps 10 --rtt-ms 60 --out-csv web/generated/experiments/joint_trace.csv
```

Run all paper baselines across multiple network settings:

```bash
python web/tools/run_serving_benchmark.py web/generated/websplatserve/scene_a/websplatserve_manifest.json --out web/generated/experiments/serving_benchmark.csv
```

Run real browser QoE traces:

```text
http://127.0.0.1:8080/web/viewers/benchmark.html?url=/web/generated/websplatserve/scene_a/manifest.json&seconds=12
```

This browser harness records TTFR, bytes, resident rows, chunk arrivals, FPS/P95 frame time, client profile, capabilities and failure stages. It intentionally does not run image-quality evaluation.

## Deployment Evidence

The inherited server already records anonymous telemetry under `web/generated/telemetry/` and exposes `/api/telemetry/summary`.  Save that JSON and convert it into a paper note:

```bash
python web/tools/collect_deployment_evidence.py telemetry_summary.json --out deployment_evidence.md
```

Or use the authenticated server endpoint:

```text
GET /api/telemetry/evidence.md
```

The telemetry policy remains privacy-preserving: no IP addresses, raw user-agent strings, raw scene names or user content.
