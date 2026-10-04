"""Tests for WebSplatServe manifest enrichment and adaptive scheduling."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from web.serving.adaptive_scheduler import ClientState, score_chunk, simulate_manifest  # noqa: E402
from web.serving.manifest import normalize_manifest  # noqa: E402


def sample_manifest() -> dict:
  return {
    "format": "splat-rows-v1",
    "representation": "sh",
    "vertexCount": 300,
    "chunks": [
      {"id": "base", "type": "base", "quality": 0, "url": "base.bin", "rows": 30, "bytes": 960, "gain": 30},
      {
        "id": "front",
        "type": "region",
        "quality": 1,
        "url": "front.bin",
        "rows": 100,
        "bytes": 3200,
        "gain": 80,
        "region": {"center": [0, 0, -2], "radius": 1},
      },
      {
        "id": "back",
        "type": "region",
        "quality": 1,
        "url": "back.bin",
        "rows": 100,
        "bytes": 3200,
        "gain": 80,
        "region": {"center": [0, 0, 5], "radius": 1},
      },
    ],
  }


def test_manifest_normalization_adds_serving_fields() -> None:
  manifest = normalize_manifest(sample_manifest())
  assert manifest["servingModel"] == "progressive-chunked-gaussian"
  assert manifest["chunks"][0]["transferBytes"] == 960
  assert manifest["chunks"][1]["visualGain"] == 80
  assert manifest["qualityLevels"][0]["quality"] == 0


def test_viewport_policy_prefers_visible_region() -> None:
  manifest = normalize_manifest(sample_manifest())
  state = ClientState(viewport_forward=(0, 0, -1), camera_position=(0, 0, 0))
  front = manifest["chunks"][1]
  back = manifest["chunks"][2]
  assert score_chunk(front, state, "viewport") > score_chunk(back, state, "viewport")


def test_simulation_reports_ttfr_and_trace() -> None:
  result = simulate_manifest(sample_manifest(), policy="joint", bandwidth_mbps=5, rtt_ms=50)
  assert result["ttfr_ms"] is not None
  assert result["chunks"] == 3
  assert result["rows"] == 230
  assert len(result["trace"]) == 3


def main() -> None:
  test_manifest_normalization_adds_serving_fields()
  test_viewport_policy_prefers_visible_region()
  test_simulation_reports_ttfr_and_trace()
  print("websplatserve scheduler tests passed")


if __name__ == "__main__":
  main()

