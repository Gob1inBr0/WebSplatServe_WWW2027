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


def test_duplicate_chunk_ids_are_rejected() -> None:
  manifest = sample_manifest()
  manifest["chunks"].append(dict(manifest["chunks"][1]))
  try:
    normalize_manifest(manifest)
    raise AssertionError("duplicate chunk ids must be rejected")
  except ValueError as exc:
    assert "unique" in str(exc)


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


def test_base_layer_is_always_delivered_first_and_defines_ttfr() -> None:
  # The refinements are much cheaper per gain than the base, so every policy
  # would prefer them — the base must still arrive first and TTFR is its
  # completion time (before it, nothing can render).
  manifest = {
    "format": "splat-rows-v1",
    "representation": "sh",
    "vertexCount": 250,
    "chunks": [
      {"id": "base", "type": "base", "quality": 0, "url": "base.bin", "rows": 50, "bytes": 8000, "gain": 30},
      {"id": "cheap_front", "type": "region", "quality": 1, "url": "cf.bin", "rows": 100, "bytes": 400,
       "gain": 40, "region": {"center": [0, 0, -2], "radius": 1}},
      {"id": "cheap_back", "type": "region", "quality": 1, "url": "cb.bin", "rows": 100, "bytes": 400,
       "gain": 40, "region": {"center": [0, 0, 5], "radius": 1}},
    ],
  }
  result = simulate_manifest(manifest, policy="joint", bandwidth_mbps=10, rtt_ms=20, quality_target=0.5)
  assert result["trace"][0]["chunk_id"] == "base"
  assert result["trace"][0]["stage"] == "base"
  assert result["ttfr_ms"] == result["trace"][0]["time_ms"]


def test_policies_diverge_in_bytes_and_order() -> None:
  # With a 50% quality target the adaptive policies can stop once the visible
  # high-gain chunk is in; naive must crawl through the expensive first
  # refinement in manifest order. Their byte counts must differ — identical
  # outputs across policies is exactly the bug class this guards against.
  manifest = {
    "format": "splat-rows-v1",
    "representation": "sh",
    "vertexCount": 250,
    "chunks": [
      {"id": "base", "type": "base", "quality": 0, "url": "base.bin", "rows": 50, "bytes": 2000, "gain": 100},
      {"id": "heavy_back", "type": "region", "quality": 1, "url": "hb.bin", "rows": 100, "bytes": 4000,
       "gain": 500, "region": {"center": [0, 0, 5], "radius": 1}},
      {"id": "light_front", "type": "region", "quality": 1, "url": "lf.bin", "rows": 100, "bytes": 400,
       "gain": 400, "region": {"center": [0, 0, -2], "radius": 1}},
    ],
  }
  joint = simulate_manifest(manifest, policy="joint", bandwidth_mbps=10, rtt_ms=20, quality_target=0.5)
  naive = simulate_manifest(manifest, policy="naive", bandwidth_mbps=10, rtt_ms=20, quality_target=0.5)
  full = simulate_manifest(manifest, policy="full", bandwidth_mbps=10, rtt_ms=20, quality_target=0.5)
  assert joint["stopped_early"] and naive["stopped_early"] and not full["stopped_early"]
  assert joint["bytes"] < naive["bytes"] < full["bytes"]
  assert joint["quality_fraction"] >= 0.5 and full["quality_fraction"] == 1.0
  joint_ids = [entry["chunk_id"] for entry in joint["trace"]]
  naive_ids = [entry["chunk_id"] for entry in naive["trace"]]
  assert joint_ids != naive_ids
  # Viewpoint-weighted quality arrives earlier under joint: it fronts the
  # in-frustum chunk, while naive burns the window on the rear chunk and never
  # reaches 50% of the view-weighted total within its stop set.
  assert joint["t50_view_ms"] is not None
  assert naive["t50_view_ms"] is None
  assert joint["view_gain_fraction"] > naive["view_gain_fraction"]


def test_memory_budget_skips_oversized_chunks() -> None:
  manifest = sample_manifest()  # rows: base 30, front 100, back 100
  result = simulate_manifest(
    manifest,
    policy="joint",
    bandwidth_mbps=10,
    rtt_ms=20,
    memory_budget_rows=120,
    quality_target=1.0,
  )
  assert result["rows"] <= 120
  assert result["budget_skips"] >= 1
  assert result["trace"][0]["chunk_id"] == "base"  # base is exempt from the budget skip


def test_gpu_policy_reacts_to_render_pressure() -> None:
  # With GPU capacity between base and full scene size, delivering early
  # chunks pushes resident rows past capacity; the gpu/joint policies must
  # diverge from plain bandwidth ordering once frame time exceeds budget.
  manifest = {
    "format": "splat-rows-v1",
    "representation": "sh",
    "vertexCount": 450,
    "chunks": [
      {"id": "base", "type": "base", "quality": 0, "url": "base.bin", "rows": 50, "bytes": 2000, "gain": 100},
      {"id": "gpu_heavy", "type": "region", "quality": 1, "url": "gh.bin", "rows": 200, "bytes": 3000,
       "gain": 300, "gpuCostMs": 4.0, "region": {"center": [0, 0, -2], "radius": 1}},
      {"id": "gpu_light", "type": "region", "quality": 1, "url": "gl.bin", "rows": 200, "bytes": 3000,
       "gain": 300, "gpuCostMs": 0.1, "region": {"center": [0, 0, -1], "radius": 1}},
      {"id": "fill", "type": "region", "quality": 2, "url": "fi.bin", "rows": 100, "bytes": 12000,
       "gain": 200, "region": {"center": [0, 0, -1], "radius": 1}},
    ],
  }
  common = dict(bandwidth_mbps=100, rtt_ms=5, memory_budget_rows=450, gpu_capacity_rows=100, quality_target=1.0)
  gpu = simulate_manifest(manifest, policy="gpu", **common)
  bandwidth = simulate_manifest(manifest, policy="bandwidth", **common)
  # capacity 100 rows: after base(50) + one chunk the estimated fps drops below
  # 24, so the gpu policy must downweight gpu_heavy and finish with a strictly
  # lower gpuCostMs chunk set than bandwidth, which ignores GPU cost entirely.
  def gpu_cost_of(result):
    by_id = {str(c["id"]): c for c in manifest["chunks"]}
    return sum(float(by_id[str(entry["chunk_id"])].get("gpuCostMs", 0.0)) for entry in result["trace"])
  assert gpu["trace"][0]["chunk_id"] == "base"
  assert gpu_cost_of(gpu) < gpu_cost_of(bandwidth)


def test_invalid_simulation_parameters_are_rejected() -> None:
  manifest = sample_manifest()
  for kwargs in (
    {"bandwidth_mbps": 0},
    {"bandwidth_mbps": -5},
    {"rtt_ms": -1},
    {"quality_target": 0.0},
    {"quality_target": 1.5},
  ):
    try:
      simulate_manifest(manifest, **kwargs)
      raise AssertionError(f"expected ValueError for {kwargs}")
    except ValueError:
      pass


def main() -> None:
  test_manifest_normalization_adds_serving_fields()
  test_duplicate_chunk_ids_are_rejected()
  test_viewport_policy_prefers_visible_region()
  test_simulation_reports_ttfr_and_trace()
  test_base_layer_is_always_delivered_first_and_defines_ttfr()
  test_policies_diverge_in_bytes_and_order()
  test_memory_budget_skips_oversized_chunks()
  test_gpu_policy_reacts_to_render_pressure()
  test_invalid_simulation_parameters_are_rejected()
  print("websplatserve scheduler tests passed")


if __name__ == "__main__":
  main()
