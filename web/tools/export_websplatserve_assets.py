#!/usr/bin/env python3
"""Export a trained 3DGS PLY into WebSplatServe assets.

This script reuses the old Web_Scan progressive exporter, then adds the paper
oriented serving metadata needed by the adaptive scheduler and benchmark tools.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from web.serving.backend_profiles import get_backend_profile  # noqa: E402
from web.serving.manifest import MANIFEST_VERSION, file_sha256, normalize_manifest  # noqa: E402
from web.tools.export_web_assets import export_web_assets  # noqa: E402


def enrich_for_websplatserve(
  manifest: dict,
  *,
  source_backend: str,
  target_profile: str,
  backend_profile: str,
  out_dir: Path,
) -> dict:
  enriched = normalize_manifest(manifest)
  enriched["version"] = MANIFEST_VERSION
  enriched["system"] = "WebSplatServe"
  enriched["sourceBackend"] = source_backend
  enriched["targetClientProfile"] = target_profile
  enriched["backendProfile"] = get_backend_profile(backend_profile)
  enriched["wwwIndustryContribution"] = {
    "webNativeRepresentation": "manifest + base layer + additive quality/spatial chunks",
    "adaptiveSignals": ["bandwidth", "rtt", "viewport", "fps", "p95_frame_ms", "memory_budget_rows"],
    "deploymentEvidence": ["anonymous serving_load telemetry", "HTTP latency/bytes summary", "failure-stage counts"],
  }
  for chunk in enriched["chunks"]:
    chunk.setdefault("deliveryClass", "critical" if chunk.get("type") == "base" else "refinement")
    chunk.setdefault("experimentRole", "base-layer" if chunk.get("quality") == 0 else "quality-or-viewport-refinement")
    rows_path = out_dir / str(chunk.get("url", ""))
    if rows_path.is_file():
      chunk["contentHash"] = file_sha256(rows_path)
      chunk["cacheKey"] = f"sha256:{chunk['contentHash']}"
      chunk["cacheControl"] = "public, max-age=31536000, immutable"
    sh_url = chunk.get("shUrl")
    if sh_url:
      sh_path = out_dir / str(sh_url)
      if sh_path.is_file():
        chunk["shContentHash"] = file_sha256(sh_path)
  return enriched


def export_websplatserve_assets(
  ply_path: Path,
  out_dir: Path,
  *,
  base_fraction: float = 0.10,
  source_backend: str = "generic-3dgs",
  target_profile: str = "heterogeneous-web",
  backend_profile: str = "vanilla-3dgs-sh",
) -> dict:
  legacy_manifest = export_web_assets(ply_path, out_dir, base_fraction=base_fraction)
  manifest = enrich_for_websplatserve(
    legacy_manifest,
    source_backend=source_backend,
    target_profile=target_profile,
    backend_profile=backend_profile,
    out_dir=out_dir,
  )
  (out_dir / "websplatserve_manifest.json").write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False),
    encoding="utf-8",
  )
  return manifest


def main() -> int:
  parser = argparse.ArgumentParser(description="Export a 3DGS PLY into WebSplatServe progressive serving assets.")
  parser.add_argument("ply_path")
  parser.add_argument("out_dir")
  parser.add_argument("--base-fraction", type=float, default=0.10)
  parser.add_argument("--source-backend", default="generic-3dgs")
  parser.add_argument("--target-profile", default="heterogeneous-web")
  parser.add_argument("--backend-profile", default="vanilla-3dgs-sh")
  args = parser.parse_args()
  manifest = export_websplatserve_assets(
    Path(args.ply_path),
    Path(args.out_dir),
    base_fraction=args.base_fraction,
    source_backend=args.source_backend,
    target_profile=args.target_profile,
    backend_profile=args.backend_profile,
  )
  print(json.dumps({
    "manifest": str(Path(args.out_dir) / "websplatserve_manifest.json"),
    "vertexCount": manifest.get("vertexCount"),
    "chunks": len(manifest.get("chunks", [])),
    "qualityLevels": manifest.get("qualityLevels", []),
  }, ensure_ascii=False))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
