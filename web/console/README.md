# WebScan Console

> 中文版：[README_ZH.md](README_ZH.md)

The new frontend for Web_Scan — a rebuilt, focused UI for the remote 3DGS
training workflow. Served by the same server as the legacy UI:

- **Console (this folder, recommended):** `http://127.0.0.1:8080/web/console/`
- **Legacy workbench (kept as fallback):** `http://127.0.0.1:8080/web/`

## What it covers

- **Wizard-driven training** — Data → Algorithm → Submit. The remote
  environment check and command preview run automatically behind a single
  confirmation modal.
- **Connection profiles** — save multiple servers, paste a raw SSH command
  (`ssh -p 10526 root@host`) and the fields fill themselves. Passwords live in
  the browser session only.
- **Runs** — named runs, live log tail, metrics chart, download progress,
  cancel/rename/delete, desktop notification when training finishes.
- **Datasets** — every run grouped by its dataset with a side-by-side compare
  view (render images + metric deltas against the best pick).
- **3D viewer** — built-in demo scenes plus quick load of local PLYs.
- **Deployment Data** (`#/deploy`) — developer-only page served by the
  `--admin` server instance: TTFR/FPS/bytes/failure aggregates from the
  anonymous telemetry, plus a one-click `evidence.md` download. Hidden on
  user-facing instances (the endpoints answer 404 there).
- **English / 中文** — toggle in the top bar; the choice is remembered.

## Progressive serving (WebGS, WWW Industry Track plan)

The console also carries the first end-to-end slice of the Web serving
pipeline described in the WebGS optimization plan:

- **Export** — `web/tools/export_web_assets.py` (or `POST /api/export-web`)
  converts a trained SH PLY into `manifest.json + base.bin + refinement /
  region chunks` (32-byte splat rows + aligned 48-float SH rows, strictly
  additive).
- **Stream** — `3D Viewer → Progressive streaming` plays a manifest in the
  browser: base layer renders first (TTFR), refinement chunks arrive
  adaptively and are appended into the WebGPU pipeline incrementally.
- **Adapt** — six policies are built in for the paper's baselines:
  `joint | bandwidth | viewport | gpu | naive | full` (the URL parameter
  `&policy=` switches them). The client classifies the device (mobile UA,
  local GPU renderer keywords, device memory, core count) into three tiers
  and adapts the row cap at runtime: two consecutive 5 s windows at
  >= 1.25x the tier's target fps with the cap binding raise it 1.5x, two
  windows at <= 0.7x lower it 0.75x. `profile=` forces a tier, `maxRows=`
  is a hard experimental cap, `adapt=0` pins the cap. The HUD shows TTFR,
  the live cap with up/down counters, downloaded bytes, bandwidth
  estimate, FPS and P95 frame time.
- **Telemetry** — `window.__webgsTelemetry()` inside the progressive viewer
  returns the full trace (TTFR, per-chunk arrivals, bytes/rows-over-time,
  frame times) for the evaluation harness. Every load also POSTs one
  anonymous `serving_load` beacon to `/api/telemetry/event` (first frame,
  completion, failure) with numeric fields only: TTFR, bytes, fps, P95
  frame time, cap adaptation counters and a closed failure-stage enum.

v1 limitation: the chunk format covers SH (standard 3DGS training) PLYs;
non-SH representations are a documented P2 item.

## Under the hood

No build step. Vue 3 is vendored at `assets/vue.global.prod.js`; everything
else is plain ES modules:

```
js/app.js          entry: sidebar, topbar, hash router
js/store.js        reactive store: profiles, polling, notifications, locale
js/api.js          typed wrappers around the backend /api endpoints
js/i18n.js         en/zh dictionary (t() reads the store, so switches are live)
js/ssh-parse.js    parses pasted SSH commands
js/components/     UI kit + SVG line chart
js/pages/          dashboard, wizard, runs, datasets, algorithms, viewer, deploy, settings
```

The server injects the API access token into this page automatically; CLI
calls still need the `X-Auth-Token` header (see the main README).

## Scope notes

Legacy-only features still on the roadmap (P2): camera capture with auto
stream upload, bulk job cleanup, cross-run CSV export, detached-run reattach
UI, flow reset / staged-data management, command override editing. The legacy
UI at `/web/` remains the fallback for those until they land here.
