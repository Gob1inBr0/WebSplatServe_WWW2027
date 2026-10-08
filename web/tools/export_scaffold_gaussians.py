#!/usr/bin/env python3
"""Decode a Scaffold-GS anchor checkpoint into a standard 3DGS SH-0 PLY.

The web viewer and the progressive exporter only understand standard Gaussian
PLYs (x/y/z, f_dc, opacity, scale, rot). Scaffold-GS instead stores anchors
plus four MLPs (opacity / covariance / color / appearance embedding); the
render-time Gaussians only exist after evaluating those MLPs. This script runs
that evaluation once and writes the result as a standard PLY, so the whole
existing web chain renders the scene unchanged.

Run it inside the Scaffold-GS virtualenv on the training server (the model
code lives in the algorithm repo):

    <venv-python> web/tools/export_scaffold_gaussians.py \
        --model-dir /websplatserve/outputs/runs/<run>/output \
        --repo /home/T0ng/algs/Scaffold-GS-main

Output: point_cloud/iteration_<latest>/scene.ply (SH degree 0 — the DC term
approximates the view-dependent color; the appearance embedding of camera uid
0 is used). Requires a CUDA GPU: the loader puts anchors and MLPs on cuda.
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

import numpy as np

SH_C0 = 0.28209479177387814


def parse_cfg_args(text: str) -> dict:
  """Parse the `Namespace(...)` text written by 3DGS-style training scripts."""
  raw = str(text).strip()
  if raw.startswith("Namespace(") and raw.endswith(")"):
    raw = raw[len("Namespace("):-1]
  config: dict = {}
  for token in _split_top_level(raw):
    if "=" not in token:
      continue
    key, _, value = token.partition("=")
    key = key.strip()
    value = value.strip()
    try:
      config[key] = ast.literal_eval(value)
    except (ValueError, SyntaxError):
      config[key] = value
  return config


def _split_top_level(text: str) -> list[str]:
  parts: list[str] = []
  depth = 0
  quote = ""
  current: list[str] = []
  for char in text:
    if quote:
      current.append(char)
      if char == quote:
        quote = ""
      continue
    if char in {"'", '"'}:
      quote = char
      current.append(char)
      continue
    if char in "([{":
      depth += 1
    elif char in ")]}":
      depth -= 1
    elif char == "," and depth == 0:
      joined = "".join(current).strip()
      if joined:
        parts.append(joined)
      current = []
      continue
    current.append(char)
  joined = "".join(current).strip()
  if joined:
    parts.append(joined)
  return parts


def resolve_iteration_dir(model_dir: Path, iteration: int | None = None) -> Path:
  """point_cloud/iteration_<N>; latest when iteration is None."""
  point_cloud_dir = model_dir / "point_cloud"
  if not point_cloud_dir.is_dir():
    raise SystemExit(f"[scaffold-decode] no point_cloud directory under {model_dir}")
  if iteration is not None:
    candidate = point_cloud_dir / f"iteration_{iteration}"
    if not candidate.is_dir():
      raise SystemExit(f"[scaffold-decode] missing iteration directory: {candidate}")
    return candidate
  found: list[tuple[int, Path]] = []
  for child in point_cloud_dir.iterdir():
    if child.is_dir() and child.name.startswith("iteration_"):
      suffix = child.name[len("iteration_"):]
      if suffix.isdigit():
        found.append((int(suffix), child))
  if not found:
    raise SystemExit(f"[scaffold-decode] no iteration_* directory under {point_cloud_dir}")
  return max(found, key=lambda item: item[0])[1]


def load_scaffold_model(repo_root: Path, iteration_dir: Path, config: dict):
  """Import GaussianModel from the repo and load anchors + MLP weights."""
  repo_str = str(repo_root)
  if repo_str not in sys.path:
    sys.path.insert(0, repo_str)
  try:
    from scene.gaussian_model import GaussianModel  # type: ignore
  except ImportError as exc:
    raise SystemExit(
      f"[scaffold-decode] cannot import GaussianModel from {repo_str}: {exc}. "
      "Run this script inside the Scaffold-GS virtualenv with --repo pointing at the repo."
    )
  use_feat_bank = bool(config.get("use_feat_bank", False))
  if use_feat_bank:
    raise SystemExit("[scaffold-decode] use_feat_bank models are not supported by this decoder")

  model = GaussianModel(
    feat_dim=int(config.get("feat_dim", 32)),
    n_offsets=int(config.get("n_offsets", 10)),
    voxel_size=float(config.get("voxel_size", 0.01)),
    update_depth=int(config.get("update_depth", 3)),
    update_init_factor=int(config.get("update_init_factor", 16)),
    update_hierachy_factor=int(config.get("update_hierachy_factor", 4)),
    use_feat_bank=False,
    appearance_dim=int(config.get("appearance_dim", 32)),
    ratio=int(config.get("ratio", 1)),
    add_opacity_dist=bool(config.get("add_opacity_dist", False)),
    add_cov_dist=bool(config.get("add_cov_dist", False)),
    add_color_dist=bool(config.get("add_color_dist", False)),
  )
  anchor_ply = iteration_dir / "point_cloud.ply"
  if not anchor_ply.is_file():
    raise SystemExit(f"[scaffold-decode] missing anchor checkpoint: {anchor_ply}")
  model.load_ply_sparse_gaussian(str(anchor_ply))
  model.load_mlp_checkpoints(str(iteration_dir), mode="split")
  try:
    model.eval()
  except Exception:
    pass
  return model


def decode_anchor_gaussians(
  model,
  *,
  chunk_anchors: int = 50_000,
  appearance_uid: int = 0,
  max_gaussians: int = 4_000_000,
):
  """Evaluate the anchor MLPs and return standard-Gaussian arrays (numpy).

  Mirrors gaussian_renderer.generate_neural_gaussians with the distance-aware
  branches off (this run's config disables add_*_dist) and a fixed unit view
  direction standing in for a camera.
  """
  import torch
  from torch.nn import functional as torch_functional

  # The loader places anchors and MLPs on cuda; run everything there.
  device = model._anchor_feat.device

  with torch.no_grad():
    feat = model._anchor_feat
    anchor = model.get_anchor
    grid_offsets = model._offset
    grid_scaling = model.get_scaling
    anchor_count = anchor.shape[0]

    view_dir = torch.zeros((anchor_count, 3), device=device)
    view_dir[:, 2] = 1.0
    appearance = None
    if model.appearance_dim > 0:
      indices = torch.full(
        (anchor_count,), int(appearance_uid), dtype=torch.long, device=device
      )
      appearance = model.get_appearance(indices)

    out_xyz, out_f_dc, out_logit, out_log_scale, out_rot = [], [], [], [], []
    for start in range(0, anchor_count, chunk_anchors):
      stop = min(start + chunk_anchors, anchor_count)
      cat_wodist = torch.cat([feat[start:stop], view_dir[start:stop]], dim=1)
      if appearance is not None:
        color_in = torch.cat([cat_wodist, appearance[start:stop]], dim=1)
      else:
        color_in = cat_wodist

      neural_opacity = model.get_opacity_mlp(cat_wodist).reshape(-1)  # [n*k]
      color = model.get_color_mlp(color_in).reshape(-1, 3)  # [n*k, 3]
      scale_rot = model.get_cov_mlp(cat_wodist).reshape(-1, 7)  # [n*k, 7]
      offsets = grid_offsets[start:stop].reshape(-1, 3)
      # Same as einops repeat(x, "n (c) -> (n k) (c)", k): each anchor row is
      # repeated k times consecutively so mask/keep indices stay aligned with
      # the flattened per-offset rows.
      repeated = torch.repeat_interleave(
        torch.cat([grid_scaling[start:stop], anchor[start:stop]], dim=-1),
        model.n_offsets,
        dim=0,
      )

      keep = neural_opacity > 0.0
      alpha = neural_opacity[keep]
      scaling_repeat = repeated[keep][:, :6]
      xyz = repeated[keep][:, 6:9] + offsets[keep] * scaling_repeat[:, :3]
      scaling = scaling_repeat[:, 3:] * torch.sigmoid(scale_rot[keep][:, :3])
      rot = torch_functional.normalize(scale_rot[keep][:, 3:7], dim=1)
      # Sigmoid color -> 3DGS DC convention: color = 0.5 + SH_C0 * f_dc.
      f_dc = (color[keep] - 0.5) / SH_C0
      # Viewer applies sigmoid to the stored opacity; Tanh alpha in (0,1)
      # must be stored as its logit.
      alpha_clamped = alpha.clamp(1e-6, 1.0 - 1e-6)
      logit = torch.log(alpha_clamped / (1.0 - alpha_clamped))
      log_scale = torch.log(scaling.clamp(1e-8, None))

      out_xyz.append(xyz)
      out_f_dc.append(f_dc)
      out_logit.append(logit)
      out_log_scale.append(log_scale)
      out_rot.append(rot)

    xyz = torch.cat(out_xyz, dim=0)
    f_dc = torch.cat(out_f_dc, dim=0)
    logit = torch.cat(out_logit, dim=0)
    log_scale = torch.cat(out_log_scale, dim=0)
    rot = torch.cat(out_rot, dim=0)

    if max_gaussians > 0 and xyz.shape[0] > max_gaussians:
      # Keep the highest-opacity Gaussians — the ones the render relies on.
      top = torch.topk(logit.squeeze(-1), k=max_gaussians).indices
      xyz, f_dc, logit, log_scale, rot = (
        xyz[top], f_dc[top], logit[top], log_scale[top], rot[top]
      )

  return {
    "xyz": xyz.detach().cpu().numpy().astype(np.float32),
    "f_dc": f_dc.detach().cpu().numpy().astype(np.float32),
    "opacity_logit": logit.detach().cpu().numpy().astype(np.float32),
    "log_scale": log_scale.detach().cpu().numpy().astype(np.float32),
    "rot": rot.detach().cpu().numpy().astype(np.float32),
  }


def write_standard_ply(path: Path, arrays: dict) -> None:
  """Write an SH-0 standard Gaussian PLY (f_rest omitted; viewers pad zeros)."""
  from plyfile import PlyData, PlyElement

  count = arrays["xyz"].shape[0]
  dtype = [
    ("x", "f4"), ("y", "f4"), ("z", "f4"),
    ("nx", "f4"), ("ny", "f4"), ("nz", "f4"),
    ("f_dc_0", "f4"), ("f_dc_1", "f4"), ("f_dc_2", "f4"),
    ("opacity", "f4"),
    ("scale_0", "f4"), ("scale_1", "f4"), ("scale_2", "f4"),
    ("rot_0", "f4"), ("rot_1", "f4"), ("rot_2", "f4"), ("rot_3", "f4"),
  ]
  elements = np.empty(count, dtype=dtype)
  elements["x"], elements["y"], elements["z"] = arrays["xyz"].T
  elements["nx"] = elements["ny"] = elements["nz"] = 0.0
  elements["f_dc_0"], elements["f_dc_1"], elements["f_dc_2"] = arrays["f_dc"].T
  elements["opacity"] = arrays["opacity_logit"].reshape(-1)
  elements["scale_0"], elements["scale_1"], elements["scale_2"] = arrays["log_scale"].T
  elements["rot_0"], elements["rot_1"], elements["rot_2"], elements["rot_3"] = arrays["rot"].T
  path.parent.mkdir(parents=True, exist_ok=True)
  vertex = np.ascontiguousarray(elements, dtype=dtype)
  PlyData([PlyElement.describe(vertex, "vertex")]).write(str(path))


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--model-dir", required=True, help="Scaffold-GS run output directory")
  parser.add_argument("--repo", required=True, help="Scaffold-GS repository root")
  parser.add_argument("--iteration", type=int, default=None, help="iteration_N (default: latest)")
  parser.add_argument("--output", default=None, help="output PLY (default: <iter dir>/scene.ply)")
  parser.add_argument("--chunk-anchors", type=int, default=50_000)
  parser.add_argument("--appearance-uid", type=int, default=0)
  parser.add_argument("--max-gaussians", type=int, default=4_000_000)
  args = parser.parse_args()

  import torch  # noqa: F401  (fail early with a clear error if missing)

  model_dir = Path(args.model_dir).resolve()
  cfg_path = model_dir / "cfg_args"
  if not cfg_path.is_file():
    raise SystemExit(f"[scaffold-decode] missing {cfg_path}")
  config = parse_cfg_args(cfg_path.read_text(encoding="utf-8"))

  iteration_dir = resolve_iteration_dir(model_dir, args.iteration)
  print(f"[scaffold-decode] iteration dir: {iteration_dir}")
  model = load_scaffold_model(Path(args.repo).resolve(), iteration_dir, config)

  arrays = decode_anchor_gaussians(
    model,
    chunk_anchors=args.chunk_anchors,
    appearance_uid=args.appearance_uid,
    max_gaussians=args.max_gaussians,
  )
  output = Path(args.output).resolve() if args.output else iteration_dir / "scene.ply"
  write_standard_ply(output, arrays)

  xyz = arrays["xyz"]
  size_mb = output.stat().st_size / (1024 * 1024)
  print(
    f"[scaffold-decode] wrote {xyz.shape[0]} gaussians -> {output} ({size_mb:.1f} MB); "
    f"bbox min {np.round(xyz.min(axis=0), 2).tolist()} max {np.round(xyz.max(axis=0), 2).tolist()}"
  )
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
