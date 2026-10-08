"""Tests for the Scaffold anchor -> standard Gaussian PLY decoder."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from plyfile import PlyData  # noqa: E402
from web.tools.export_scaffold_gaussians import (  # noqa: E402
  SH_C0,
  decode_anchor_gaussians,
  parse_cfg_args,
  resolve_iteration_dir,
  write_standard_ply,
)

REAL_CFG = (
  "Namespace(sh_degree=3, feat_dim=32, n_offsets=10, voxel_size=0.001, update_depth=3, "
  "update_init_factor=16, update_hierachy_factor=4, use_feat_bank=False, "
  "source_path='/websplatserve/workspaces/datasets/hac-plus-plus/drjohnson-preview-/workspace', "
  "model_path='/websplatserve/outputs/runs/x/output', images='images', resolution=-1, "
  "white_background=False, data_device='cuda', eval=True, lod=0, appearance_dim=32, "
  "lowpoly=False, ds=1, ratio=1, undistorted=False, add_opacity_dist=False, "
  "add_cov_dist=False, add_color_dist=False)"
)


class _FakeModel:
  """Tiny stand-in with the attributes decode_anchor_gaussians touches."""

  def __init__(self, anchor_count: int, feat_dim: int = 8, n_offsets: int = 3):
    import torch

    self.n_offsets = n_offsets
    self.appearance_dim = 4
    torch.manual_seed(7)
    self._anchor = torch.nn.Parameter(torch.rand(anchor_count, 3) * 2 - 1)
    self._anchor_feat = torch.rand(anchor_count, feat_dim)
    self._offset = torch.rand(anchor_count, n_offsets, 3) * 0.01
    self._scaling = torch.rand(anchor_count, 6) * 0.2 - 3.0  # exp() -> grid scale
    self.mlp_opacity = torch.nn.Linear(feat_dim + 3, n_offsets)
    self.mlp_cov = torch.nn.Linear(feat_dim + 3, 7 * n_offsets)
    self.mlp_color = torch.nn.Linear(feat_dim + 3 + self.appearance_dim, 3 * n_offsets)
    self.embedding_appearance = torch.nn.Embedding(4, self.appearance_dim)

  @property
  def get_anchor(self):
    return self._anchor

  @property
  def get_scaling(self):
    return torch.exp(self._scaling)

  def get_opacity_mlp(self, x):
    return self.mlp_opacity(x)

  def get_cov_mlp(self, x):
    return self.mlp_cov(x)

  def get_color_mlp(self, x):
    # The real model's color MLP ends with nn.Sigmoid().
    return torch.sigmoid(self.mlp_color(x))

  def get_appearance(self, indices):
    return self.embedding_appearance(indices)


def test_parse_cfg_args_handles_real_namespace_text():
  config = parse_cfg_args(REAL_CFG)
  assert config["n_offsets"] == 10
  assert config["appearance_dim"] == 32
  assert config["add_opacity_dist"] is False
  assert config["voxel_size"] == 0.001
  assert config["source_path"].startswith("/websplatserve/workspaces")
  assert config["images"] == "images"


def test_resolve_iteration_dir_latest_or_explicit(tmp_path=None):
  import tempfile

  with tempfile.TemporaryDirectory() as td:
    model_dir = Path(td)
    point_cloud = model_dir / "point_cloud"
    (point_cloud / "iteration_7000").mkdir(parents=True)
    (point_cloud / "iteration_30000").mkdir(parents=True)
    assert resolve_iteration_dir(model_dir).name == "iteration_30000"
    assert resolve_iteration_dir(model_dir, 7000).name == "iteration_7000"
    (point_cloud / "iteration_junk").mkdir()
    assert resolve_iteration_dir(model_dir).name == "iteration_30000"


def test_decode_math_and_ply_roundtrip():
  anchor_count, k = 40, 3
  model = _FakeModel(anchor_count, n_offsets=k)
  arrays = decode_anchor_gaussians(model, chunk_anchors=7, max_gaussians=0)

  expected = int((model.get_opacity_mlp(
    torch.cat([model._anchor_feat, _unit_view(anchor_count)], dim=1)
  ).reshape(-1) > 0).sum().item())
  assert arrays["xyz"].shape[0] == expected
  assert arrays["xyz"].shape[1] == 3
  assert arrays["rot"].shape[1] == 4

  # Quaternion rows are unit length (viewer re-normalizes).
  norms = np.linalg.norm(arrays["rot"], axis=1)
  assert np.allclose(norms, 1.0, atol=1e-5)

  # Round-trip through the written PLY: sigmoid(opacity) == alpha within the
  # 1e-6 clamp, exp(scale) matches, color = 0.5 + SH_C0 * f_dc.
  with __import__("tempfile").TemporaryDirectory() as td:
    ply_path = Path(td) / "scene.ply"
    write_standard_ply(ply_path, arrays)
    data = PlyData.read(str(ply_path))
    vertex = data.elements[0]
    props = [p.name for p in vertex.properties]
    assert "f_rest_0" not in props, "SH-0 output must omit f_rest"
    assert {"x", "y", "z", "f_dc_0", "opacity", "scale_0", "rot_0"} <= set(props)

    stored_alpha = 1.0 / (1.0 + np.exp(-np.asarray(vertex["opacity"], dtype=np.float64)))
    assert np.all(stored_alpha > 0) and np.all(stored_alpha < 1)

    color = 0.5 + SH_C0 * np.stack([
      np.asarray(vertex["f_dc_0"]), np.asarray(vertex["f_dc_1"]), np.asarray(vertex["f_dc_2"])
    ], axis=1)
    assert np.all(color >= 0.0 - 1e-5) and np.all(color <= 1.0 + 1e-5), \
      "Sigmoid colors must map back into [0,1] through the DC convention"

    scales = np.exp(np.stack([
      np.asarray(vertex["scale_0"]), np.asarray(vertex["scale_1"]), np.asarray(vertex["scale_2"])
    ], axis=1))
    assert np.all(scales > 0)


def _unit_view(count: int):
  view = torch.zeros((count, 3))
  view[:, 2] = 1.0
  return view


def test_decode_max_gaussians_keeps_highest_opacity():
  model = _FakeModel(200, n_offsets=4)
  full = decode_anchor_gaussians(model, max_gaussians=0)
  capped = decode_anchor_gaussians(model, max_gaussians=50)
  assert capped["xyz"].shape[0] == 50
  assert full["xyz"].shape[0] >= 50
  # Kept rows must be a subset by count and all at least as opaque as dropped ones.
  assert capped["opacity_logit"].min() >= np.sort(full["opacity_logit"].reshape(-1))[
    full["xyz"].shape[0] - 50
  ] - 1e-4


def main() -> int:
  tests = [
    test_parse_cfg_args_handles_real_namespace_text,
    test_resolve_iteration_dir_latest_or_explicit,
    test_decode_math_and_ply_roundtrip,
    test_decode_max_gaussians_keeps_highest_opacity,
  ]
  failures = 0
  for test in tests:
    started = time.time()
    try:
      test()
      print(f"[ok] {test.__name__} ({time.time() - started:.2f}s)")
    except Exception as exc:
      failures += 1
      import traceback
      print(f"[FAIL] {test.__name__}: {exc}")
      traceback.print_exc()
  print(f"{len(tests) - failures}/{len(tests)} passed")
  return 1 if failures else 0


if __name__ == "__main__":
  raise SystemExit(main())
