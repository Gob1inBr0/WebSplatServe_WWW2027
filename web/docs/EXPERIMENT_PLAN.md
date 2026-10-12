# WebSplatServe WWW 2027 Industry Track Experiment Plan

> 中文版：[EXPERIMENT_PLAN_ZH.md](EXPERIMENT_PLAN_ZH.md)

## Goal

WebSplatServe evaluates Web-native 3D Gaussian serving instead of only offline compression quality.  The core question is whether a browser can show a usable scene sooner and remain interactive under heterogeneous network, viewport and GPU constraints.

## Required Baselines

- `full`: request every chunk immediately.  This approximates full-scene download pressure.
- `naive`: fixed manifest order without adaptation.
- `bandwidth`: prioritize gain per byte.
- `viewport`: prioritize currently visible spatial chunks.
- `gpu`: throttle refinement when frame time or row budget is stressed.
- `joint`: use bandwidth, viewport, frame-time and memory signals together.

## Metrics

- TTFR: time to first rendered Gaussian rows.
- Load time: simulated or measured time until all selected chunks arrive.
- Downloaded bytes: cumulative transfer before each chunk or refinement milestone.
- Chunk arrival curve: rows and bytes resident in the browser over wall-clock time.
- FPS / P95 frame time: collected from the progressive viewer telemetry.
- Memory: resident Gaussian row budget and device class.
- Failure rate and failure stages: closed enum (`manifest | webgl | worker |
  chunks | internal`) aggregated by the deployment telemetry.
- Cap adaptation: how often the runtime controller raised / lowered the row
  cap (`adapt_up` / `adapt_down` / `cap_initial` / `cap_final` per load) —
  evidence that the client actually adapts its budget.
- Failures: chunk failures, unsupported browser/GPU, OOM or render failures.

## Minimum Matrix

Run each policy on at least:

- Three client classes: desktop discrete GPU, laptop integrated GPU and mobile/mid-range.
- Four network settings: 2 Mbps / 120 ms, 10 Mbps / 60 ms, 30 Mbps / 30 ms, 100 Mbps / 10 ms.
- Three scene sizes: small, medium and large Gaussian counts.

The repository includes `web/config/websplatserve_profiles.json` so this matrix stays explicit and reproducible.

For real-browser runs the client class is forced on the viewer URL
(`profile=android_mid_range`, `profile=laptop_integrated_gpu`,
`profile=desktop_discrete_gpu`), the row budget is pinned with `maxRows=<n>`,
and `adapt=0` disables the runtime cap controller for the fixed-budget arms.
The adaptive arms run with defaults (`profile=auto&adapt=1`).

## Commands

```bash
python web/tools/export_websplatserve_assets.py /path/to/scene.ply web/generated/websplatserve/scene_a
python web/serving/adaptive_scheduler.py web/generated/websplatserve/scene_a/websplatserve_manifest.json --policy joint --bandwidth-mbps 10 --rtt-ms 60 --out-csv web/generated/experiments/joint_trace.csv
python web/tools/run_serving_benchmark.py web/generated/websplatserve/scene_a/websplatserve_manifest.json --out web/generated/experiments/serving_benchmark.csv
```

For real browser QoE traces without image-quality evaluation:

```text
http://127.0.0.1:8080/web/viewers/benchmark.html?url=/web/generated/websplatserve/scene_a/manifest.json&seconds=12
```

The page runs the selected policies in a same-origin iframe and exports TTFR, downloaded bytes, resident rows, chunk arrivals, FPS, P95 frame time, client profile and capability data.

## Full Evaluation Campaign

The concrete test design for the full serving evaluation — export validation,
the 4320-run simulation matrix, sampled real-browser runs, acceptance
criteria and limitations — lives in `docs/服务评测-测试设计方案.md`
(serving evaluation test design, v2). It runs on the GPU server via
`scripts/campaign_runner.py`; only the browser layer needs a local machine.

## Deployment Evidence

During a public or internal deployment, keep anonymous telemetry enabled.  The summary and evidence endpoints exist only on the `--admin` server instance (run it on a separate, loopback-bound port); user-facing instances answer 404.  Pull `/api/telemetry/summary` from the admin instance, save it as JSON, then generate a paper-ready note — or just click the download button on the console's Deployment Data page:

```bash
python web/server/api_server.py --host 127.0.0.1 --port 8092 --admin
python web/tools/collect_deployment_evidence.py telemetry_summary.json --out deployment_evidence.md
```

Do not store IP addresses, raw user-agent strings, raw GPU strings, raw scene names or user content in the paper artifact.
