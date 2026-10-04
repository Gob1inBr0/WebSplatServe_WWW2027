"""Manifest helpers for WebSplatServe assets.

The runtime accepts the legacy progressive manifest from Web_Scan and enriches
it into a WWW submission oriented serving manifest.  The schema is intentionally
plain JSON so chunks can be hosted by any HTTP/CDN origin.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

MANIFEST_VERSION = "websplatserve-1.0"

REQUIRED_CHUNK_FIELDS = ("id", "url", "rows", "bytes")


def load_manifest(path: str | Path) -> dict[str, Any]:
  manifest_path = Path(path)
  with open(manifest_path, "r", encoding="utf-8") as handle:
    manifest = json.load(handle)
  return normalize_manifest(manifest, base_url=str(manifest_path.parent))


def normalize_manifest(manifest: dict[str, Any], *, base_url: str = "") -> dict[str, Any]:
  if not isinstance(manifest, dict):
    raise ValueError("manifest must be a JSON object")
  chunks = manifest.get("chunks")
  if not isinstance(chunks, list) or not chunks:
    raise ValueError("manifest must contain a non-empty chunks array")
  chunk_ids = [str(chunk.get("id")) if isinstance(chunk, dict) else "" for chunk in chunks]
  duplicates = sorted({cid for cid, count in zip(chunk_ids, range(len(chunk_ids))) if chunk_ids.count(cid) > 1 and cid})
  if duplicates:
    raise ValueError(f"manifest chunk ids must be unique, duplicates: {', '.join(duplicates)}")
  normalized = dict(manifest)
  normalized.setdefault("version", MANIFEST_VERSION)
  normalized.setdefault("format", manifest.get("format", "splat-rows-v1"))
  normalized.setdefault("servingModel", "progressive-chunked-gaussian")
  normalized.setdefault("schedulerHints", default_scheduler_hints())
  normalized.setdefault("qualityLevels", infer_quality_levels(chunks))
  normalized["chunks"] = [normalize_chunk(chunk, base_url=base_url, ordinal=i) for i, chunk in enumerate(chunks)]
  return normalized


def normalize_chunk(chunk: dict[str, Any], *, base_url: str = "", ordinal: int = 0) -> dict[str, Any]:
  if not isinstance(chunk, dict):
    raise ValueError("chunk entries must be JSON objects")
  for field in REQUIRED_CHUNK_FIELDS:
    if field not in chunk:
      raise ValueError(f"chunk lacks required field: {field}")
  rows = max(0, int(chunk.get("rows", 0)))
  byte_size = max(0, int(chunk.get("bytes", 0)) + int(chunk.get("shBytes", 0) or 0))
  gain = float(chunk.get("gain", rows or 1))
  quality = int(chunk.get("quality", 0) or 0)
  normalized = dict(chunk)
  normalized["ordinal"] = int(chunk.get("ordinal", ordinal))
  normalized["rows"] = rows
  normalized["transferBytes"] = byte_size
  normalized["visualGain"] = gain
  normalized["decodeCostMs"] = round(float(chunk.get("decodeCostMs", rows * 0.002)), 4)
  # 8 us/row keeps the GPU term visible next to ~224 transfer bytes/row in the
  # byte-equivalent score; at 0.4 us/row the gpu/joint policies tracked plain
  # bandwidth ordering.
  normalized["gpuCostMs"] = round(float(chunk.get("gpuCostMs", rows * 0.008)), 4)
  normalized["quality"] = quality
  normalized.setdefault("dependencies", [])
  normalized.setdefault("cacheControl", "public, max-age=31536000, immutable")
  if "contentHash" in normalized:
    normalized.setdefault("cacheKey", f"sha256:{normalized['contentHash']}")
  if base_url:
    normalized.setdefault("originHint", base_url)
  return normalized


def infer_quality_levels(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
  levels: dict[int, dict[str, Any]] = {}
  for chunk in chunks:
    quality = int(chunk.get("quality", 0) or 0)
    item = levels.setdefault(quality, {"quality": quality, "rows": 0, "transferBytes": 0, "chunks": 0})
    item["rows"] += int(chunk.get("rows", 0) or 0)
    item["transferBytes"] += int(chunk.get("bytes", 0) or 0) + int(chunk.get("shBytes", 0) or 0)
    item["chunks"] += 1
  return [levels[key] for key in sorted(levels)]


def default_scheduler_hints() -> dict[str, Any]:
  return {
    "objective": "minimize TTFR and time-to-usable-quality under network, viewport, FPS and memory constraints",
    "score": "visualGain * viewWeight / (transferBytes + lambdaDecode * decodeCostMs + muGpu * gpuCostMs), ms costs converted to byte equivalents at the current bandwidth",
    "lambdaDecode": 8.0,
    "muGpu": 2.0,
    "gpuGuardP95FrameMs": 34,
    "lowFpsThreshold": 24,
    "defaultConcurrency": 1,
  }


def write_manifest(manifest: dict[str, Any], path: str | Path) -> None:
  target = Path(path)
  target.parent.mkdir(parents=True, exist_ok=True)
  target.write_text(json.dumps(normalize_manifest(manifest), indent=2, ensure_ascii=False), encoding="utf-8")


def file_sha256(path: str | Path) -> str:
  digest = hashlib.sha256()
  with open(path, "rb") as handle:
    for block in iter(lambda: handle.read(1024 * 1024), b""):
      digest.update(block)
  return digest.hexdigest()
