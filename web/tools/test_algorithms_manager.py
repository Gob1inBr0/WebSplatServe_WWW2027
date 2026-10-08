"""Tests for the algorithm auto-install (env_setup) machinery.

Covers the pure halves of web/server/algorithms_manager.py: patch-rule
matching and actions, fix-signature matching, module mapping, URL/name
validation, catalog merging, setup-script generation (including a real run of
the embedded remote patcher against a temp repo), and the adapter-override
sync after a successful install.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from web.server import adapter_registry  # noqa: E402
from web.server import algorithms_manager as am  # noqa: E402
from web.server.remote_executor import RemoteExecutionError  # noqa: E402


def _rules_by_id() -> dict:
  return {rule["id"]: rule for rule in am.load_patch_rules()}


# ------------------------------------------------------------------ globbing

def test_glob_to_regex() -> None:
  cu = am.glob_to_regex("**/*.cu")
  assert cu.match("a.cu") and cu.match("sub/a.cu") and cu.match("deep/nest/a.cu")
  assert not cu.match("a.py") and not cu.match("sub/a.cu.txt")
  top = am.glob_to_regex("*.py")
  assert top.match("train.py") and not top.match("sub/train.py")
  train = am.glob_to_regex("**/train.py")
  assert train.match("train.py") and train.match("x/train.py")
  assert not train.match("train_py")


# ------------------------------------------------------------- patch rules

def test_cfloat_rule_inserts_after_first_include() -> None:
  rule = _rules_by_id()["cfloat-cuda12"]
  src = '#include <cuda_runtime.h>\n__global__ void k(){ float x = FLT_MAX; }\n'
  assert am.rule_matches_file(rule, "submodules/x/a.cu", src)
  patched, edits = am.apply_rule_to_text(rule, "submodules/x/a.cu", src)
  assert edits == 1
  assert patched.splitlines()[1] == "#include <cfloat>"
  # Already has the include → rule no longer matches.
  assert not am.rule_matches_file(rule, "a.cu", src.replace("#include <cuda_runtime.h>", "#include <cfloat>\n#include <cuda_runtime.h>"))
  # No FLT_MAX → no match.
  assert not am.rule_matches_file(rule, "a.cu", "#include <cuda_runtime.h>\nint x;\n")
  # Wrong extension → no match.
  assert not am.rule_matches_file(rule, "a.py", src)


def test_np_cast_rule_rewrites_to_asarray() -> None:
  rule = _rules_by_id()["np-cast-numpy2"]
  src = "img = np.cast[np.float32](raw / 255.0)\nother = np.cast[np.uint8](x * 255)\n"
  assert am.rule_matches_file(rule, "utils/img.py", src)
  patched, edits = am.apply_rule_to_text(rule, "utils/img.py", src)
  assert edits == 2
  assert patched == ("img = np.asarray(raw / 255.0, dtype=np.float32)\n"
                     "other = np.asarray(x * 255, dtype=np.uint8)\n")


def test_future_annotations_rule_inserts_after_docstring() -> None:
  rule = _rules_by_id()["future-annotations"]
  src = '"""Trainer."""\nimport torch\nfrom scene import Scene\ndef f(opt: Scene, gs: GaussianModel):\n    pass\n'
  assert am.rule_matches_file(rule, "train.py", src)
  patched, edits = am.apply_rule_to_text(rule, "train.py", src)
  assert edits == 1
  lines = patched.splitlines()
  assert lines[0] == '"""Trainer."""'
  assert lines[1] == "from __future__ import annotations"
  # With leading comments before the docstring, insert after the docstring.
  src2 = "#!/usr/bin/env python\n# vim: set ft=python\n\n\"\"\"Doc.\"\"\"\nimport torch\ndef f(x: Scene):\n    pass\n"
  patched2, edits2 = am.apply_rule_to_text(rule, "train.py", src2)
  assert edits2 == 1
  assert patched2.splitlines()[4] == "from __future__ import annotations"
  # No docstring at all → insert at the top (below leading comments).
  src3 = "# comment\nimport torch\ndef f(x: Scene):\n    pass\n"
  patched3, _ = am.apply_rule_to_text(rule, "train.py", src3)
  assert patched3.splitlines()[1] == "from __future__ import annotations"
  # Only matches train.py, not arbitrary files.
  assert not am.rule_matches_file(rule, "scene/__init__.py", src)


def test_arange_rule_adds_device() -> None:
  rule = _rules_by_id()["arange-device"]
  src = "ids = torch.arange(len(cams))\nflat = torch.arange(t.shape[0])\nfixed = torch.arange(10)\n"
  patched, edits = am.apply_rule_to_text(rule, "scene/gs.py", src)
  assert "torch.arange(len(cams), device=cams.device)" in patched
  assert "torch.arange(t.shape[0], device=t.device)" in patched
  # Bare-constant aranges cannot infer a device → left untouched.
  assert "fixed = torch.arange(10)" in patched


def test_torch_load_rule_not_proactive() -> None:
  rule = _rules_by_id()["torch-load-weights-only"]
  assert rule.get("proactive") is False
  # The pure engine still applies it when invoked explicitly (self-heal path).
  src = "state = torch.load(path)\n"
  patched, edits = am.apply_rule_to_text(rule, "train.py", src)
  assert edits == 1
  assert "torch.load(path, weights_only=False)" in patched


def test_insert_after_first_include_without_include_prepends() -> None:
  text = "int x = FLT_MAX;\n"
  patched, edits = am.apply_action(text, {"action": "insert_after_first_include", "line": "#include <cfloat>"})
  assert edits == 1
  assert patched.startswith("#include <cfloat>\n")


# ---------------------------------------------------------- fix signatures

def test_fix_signature_matching() -> None:
  cases = {
    "ModuleNotFoundError: No module named 'pandas'": "pip-missing-module",
    'error: identifier "FLT_MAX" is undefined': "flt-max-undefined",
    "AttributeError: module 'numpy' has no attribute 'cast'": "np-cast-removed",
    "NameError: name 'Scene' is not defined": "scene-not-defined",
    "_pickle.UnpicklingError: Unsupported global: GLOBAL numpy.x": "torch-weights-only",
    "RuntimeError: indices should be either on cpu or on the same device as the indexed tensor": "arange-device-mismatch",
    "OSError: [Errno 98] Address already in use": "port-in-use",
    "AttributeError: 'GaussianEntropyBottleneck' object has no attribute '_encoder'": "compressai-rans-encoder",
  }
  for tail, expected_id in cases.items():
    matched = am.match_fix_signature(tail)
    assert matched is not None, f"no signature matched: {tail}"
    assert matched["id"] == expected_id, f"{tail!r} matched {matched['id']}, expected {expected_id}"
  assert am.match_fix_signature("some unrelated failure: bad luck 42") is None


def test_missing_module_and_traceback_extraction() -> None:
  assert am.extract_missing_module("ModuleNotFoundError: No module named 'cv2'") == "cv2"
  assert am.extract_missing_module("nothing here") == ""
  tail = (
    'Traceback (most recent call last):\n'
    '  File "/home/u/algs/x/train.py", line 10, in <module>\n'
    '    from scene import Scene\n'
    '  File "/home/u/algs/x/scene/__init__.py", line 3, in <module>\n'
    'NameError: name \'Scene\' is not defined\n'
  )
  files = am.extract_traceback_files(tail)
  assert files == ["/home/u/algs/x/train.py", "/home/u/algs/x/scene/__init__.py"]


# ------------------------------------------------------- module/url/name

def test_module_to_pip_mapping() -> None:
  assert am.module_to_pip("cv2") == {"kind": "pip", "spec": "opencv-python-headless"}
  assert am.module_to_pip("yaml") == {"kind": "pip", "spec": "pyyaml"}
  assert am.module_to_pip("fused_ssim")["kind"] == "git"
  assert am.module_to_pip("fused_ssim")["spec"].startswith("https://")
  assert am.module_to_pip("brand_new_pkg") == {"kind": "pip", "spec": "brand_new_pkg"}


def test_validate_repo_url_and_slug() -> None:
  assert am.validate_repo_url("https://github.com/org/repo") == "https://github.com/org/repo"
  assert am.validate_repo_url("") == ""
  for bad in ("git@github.com:org/repo.git", "http://x.com/r", "https://x.com/r;rm -rf /",
              "https://x.com/r$(id)", "https://x.com/r`id`"):
    try:
      am.validate_repo_url(bad)
    except RemoteExecutionError:
      continue
    raise AssertionError(f"repo_url should have been rejected: {bad!r}")
  assert am.safe_setup_name("ContextGS (2024)") == "contextgs-2024"
  assert am.safe_setup_name("") == "algorithm"
  assert am.safe_setup_name("taming3dgs") == "taming3dgs"


# ------------------------------------------------------------------ catalog

def _fake_adapter(family: str, repo_url: str = "", repo_path: str = "", trainable: bool = True) -> dict:
  return {
    "family": family,
    "label": family.title(),
    "category": "test",
    "repo_url": repo_url,
    "repo_path": repo_path,
    "operations": {"train": {"enabled": trainable, "template": "python train.py"}},
  }


def test_build_catalog_merge_and_status_priority() -> None:
  adapters = [
    _fake_adapter("alpha", repo_url="https://github.com/a/alpha"),
    _fake_adapter("beta", repo_url="https://github.com/b/beta", repo_path="/srv/beta"),
    _fake_adapter("gamma", repo_url="https://github.com/c/gamma"),
    _fake_adapter("delta"),
  ]
  registry = {"algorithms": {
    "alpha": {"status": "ready", "repo_dir": "/srv/alpha", "entry": "train.py", "venv": "/venvs/alpha"},
  }}
  catalog = am.build_catalog(
    registry=registry,
    active_setups={"beta": {"id": "job-beta", "setup_steps": [{"name": "clone", "status": "success"}]}},
    failed_setups={"gamma": {"id": "job-gamma", "failure_reason": "No module named 'pandas'", "setup_steps": []}},
    adapters=adapters,
    discovered=["/srv/algs/orphan-repo"],
  )
  entries = {e["name"]: e for e in catalog["algorithms"]}
  assert entries["alpha"]["status"] == "ready" and entries["alpha"]["source"] == "registry"
  assert entries["beta"]["status"] == "installing" and entries["beta"]["active_job_id"] == "job-beta"
  assert entries["gamma"]["status"] == "failed" and entries["gamma"]["failure_reason"] == "No module named 'pandas'"
  # delta has neither registry entry nor repo_path → not installed.
  assert entries["delta"]["status"] == "not_installed"
  # Discovered repo not in adapters shows up as scan source.
  assert entries["orphan-repo"]["source"] == "scan"
  assert catalog["counts"]["ready"] == 1
  assert catalog["counts"]["installing"] == 1
  assert catalog["counts"]["failed"] == 1


# ------------------------------------------------------- setup script build

def _generate_for_test(pip_modules: list[str]) -> str:
  layout = {
    "algs_root": "/home/u/websplatserve/algs",
    "venvs_root": "/home/u/websplatserve/venvs",
    "bin_dir": "/home/u/websplatserve/bin",
    "registry_path": "/home/u/websplatserve/algs/registry.json",
  }
  return am.generate_setup_script(
    name="ContextGS",
    family="contextgs",
    repo_url="https://github.com/wyf0912/ContextGS",
    entry="train.py",
    base_python="/opt/sharc/bin/python",
    layout=layout,
    job_paths={
      "job_dir": "/o/.wgsc_job",
      "status_file": "/o/.wgsc_job/status.json",
      "exit_code_file": "/o/.wgsc_job/exit_code",
      "runtime_log": "/o/.wgsc_job/runtime.log",
      "pid_file": "/o/.wgsc_job/pid",
      "remote_output_dir": "/o",
    },
    job_id="job-123",
    pip_modules=pip_modules,
  )


def test_generate_setup_script_structure() -> None:
  script = _generate_for_test(["torch", "cv2", "fused-ssim"])
  # No un-substituted tokens and no shell-unsafe leakage of the URL.
  assert not re.findall(r"__[A-Z_]+__", script)
  assert "https://github.com/wyf0912/ContextGS" in script
  # Steps present in order, with skip markers for idempotent retries.
  for step in am.SETUP_STEP_ORDER:
    assert f"step_done {step}" in script, f"missing skip guard for {step}"
  assert script.index("step_done preflight") < script.index("step_done clone") < script.index("step_done register")
  # Deps list is embedded (deduped, import-name normalized).
  assert "torch" in script and "cv2" in script and "fused_ssim" in script
  # Config payloads embedded for the remote helpers.
  assert '"cfloat-cuda12"' in script
  assert '"pip-missing-module"' in script
  # Dynamic-GPU wrapper writes CUDA_VISIBLE_DEVICES.
  assert "CUDA_VISIBLE_DEVICES" in script
  # Status format includes step progress for the poll passthrough.
  assert "setup_steps" in script
  # bash -n guards heredoc quoting regressions (writes to a temp file so the
  # check works the same on macOS and Linux).
  with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as handle:
    handle.write(script)
    script_file = handle.name
  try:
    result = subprocess.run(["bash", "-n", script_file], capture_output=True, text=True)
  finally:
    Path(script_file).unlink(missing_ok=True)
  if result.returncode != 0:
    raise AssertionError(f"generated script failed bash -n: {result.stderr[:400]}")


def _extract_heredoc(script: str, marker: str) -> str:
  start = script.index(f"<<'{marker}'\n") + len(f"<<'{marker}'\n")
  end = script.index(f"\n{marker}", start)
  return script[start:end]


def test_setup_script_executes_end_to_end() -> None:
  """Run the real generated setup script locally against a tiny git repo.

  Exercises the full bash flow offline: clone (from a local repo), venv
  creation, submodule scan (none), proactive patching of the cloned .cu file,
  empty deps list, argparse --help smoke, wrapper, and the registry merge.
  Requires git + bash + venv support; skipped silently where unavailable.
  """
  import shutil

  if not (shutil.which("git") and shutil.which("bash")):
    print("[skip] end-to-end setup script test (git/bash unavailable)")
    return

  with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)

    # A tiny source repo with a CUDA-pitfall file and an argparse entry.
    src_repo = tmp_path / "src-repo"
    src_repo.mkdir()
    (src_repo / "train.py").write_text(
      "import argparse\n"
      "parser = argparse.ArgumentParser(description='smoke')\n"
      "parser.parse_args()\n",
      encoding="utf-8",
    )
    (src_repo / "k.cu").write_text("#include <cuda_runtime.h>\nfloat m = FLT_MAX;\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=src_repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"], cwd=src_repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"], cwd=src_repo, check=True)

    data_root = tmp_path / "data"
    layout = {
      "algs_root": str(data_root / "algs"),
      "venvs_root": str(data_root / "venvs"),
      "bin_dir": str(data_root / "bin"),
      "registry_path": str(data_root / "algs" / "registry.json"),
    }
    job_dir = tmp_path / "job" / ".wgsc_job"
    script = am.generate_setup_script(
      name="fakegs",
      family="fakegs",
      repo_url=str(src_repo),  # local path: script-side clone accepts it; the API layer enforces https
      entry="train.py",
      base_python=sys.executable,
      layout=layout,
      job_paths={
        "job_dir": str(job_dir),
        "status_file": str(job_dir / "status.json"),
        "exit_code_file": str(job_dir / "exit_code"),
        "runtime_log": str(job_dir / "runtime.log"),
        "pid_file": str(job_dir / "pid"),
        "remote_output_dir": str(tmp_path / "job"),
      },
      job_id="job-e2e",
      pip_modules=[],
    )

    script_path = tmp_path / "algs-setup.sh"
    script_path.write_text(script, encoding="utf-8")
    run = subprocess.run(["bash", str(script_path)], capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, f"setup script failed:\n{run.stdout[-1500:]}\n{run.stderr[-1500:]}"

    status = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "completed"
    assert status["stage"] == "env_setup:ready"
    assert status["job_id"] == "job-e2e" and status["family"] == "fakegs"
    steps = {s["name"]: s["status"] for s in status["setup_steps"]}
    for step in am.SETUP_STEP_ORDER:
      assert steps.get(step) == "success", f"step {step} not successful: {steps}"

    # The known-pitfall patch fired on the cloned .cu file.
    cloned_cu = Path(layout["algs_root"], "fakegs", "k.cu")
    assert cloned_cu.exists()
    assert cloned_cu.read_text(encoding="utf-8").splitlines()[1] == "#include <cfloat>"

    # Wrapper + registry landed where the docs promise.
    wrapper = Path(layout["bin_dir"], "py-fakegs")
    assert wrapper.exists() and wrapper.stat().st_mode & 0o111
    registry = json.loads(Path(layout["registry_path"]).read_text(encoding="utf-8"))
    entry = registry["algorithms"]["fakegs"]
    assert entry["status"] == "ready" and entry["family"] == "fakegs"
    assert entry["repo_dir"] == str(Path(layout["algs_root"], "fakegs"))

    # Idempotent re-run: every step skips, still completes.
    run2 = subprocess.run(["bash", str(script_path)], capture_output=True, text=True, timeout=120)
    assert run2.returncode == 0, run2.stderr[-800:]
    assert "already done, skip" in run2.stdout or "skip" in run2.stdout


def test_embedded_remote_patcher_runs() -> None:
  """Extract the real wgsc_patcher.py from a generated script and run it
  against a temp repo — proves the heredoc escaping is sound end to end."""
  script = _generate_for_test([])
  with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    patcher_path = tmp_path / "wgsc_patcher.py"
    patcher_path.write_text(_extract_heredoc(script, "WGSC_PY_EOF"), encoding="utf-8")
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(json.dumps({"rules": am.load_patch_rules()}), encoding="utf-8")

    repo = tmp_path / "repo"
    (repo / "submodules" / "rasterizer").mkdir(parents=True)
    cu_file = repo / "submodules" / "rasterizer" / "k.cu"
    cu_file.write_text("#include <cuda_runtime.h>\nfloat m = FLT_MAX;\n", encoding="utf-8")
    py_file = repo / "helpers.py"
    py_file.write_text("x = np.cast[np.float32](v)\n", encoding="utf-8")
    (repo / ".git").mkdir()
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    result = subprocess.run(
      [sys.executable, str(patcher_path), "--repo", str(repo), "--rules", str(rules_path), "--proactive-only"],
      capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr[:400]
    assert "PATCHER_RESULT" in result.stdout
    payload = json.loads(result.stdout.split("PATCHER_RESULT", 1)[1].strip())
    assert payload["total_edits"] >= 2
    assert cu_file.read_text(encoding="utf-8").splitlines()[1] == "#include <cfloat>"
    assert "np.asarray(v, dtype=np.float32)" in py_file.read_text(encoding="utf-8")
    # .git content is never touched.
    assert (repo / ".git" / "HEAD").exists()
    # Idempotent: a second run makes no further edits.
    result2 = subprocess.run(
      [sys.executable, str(patcher_path), "--repo", str(repo), "--rules", str(rules_path), "--proactive-only"],
      capture_output=True, text=True, timeout=60,
    )
    payload2 = json.loads(result2.stdout.split("PATCHER_RESULT", 1)[1].strip())
    assert payload2["total_edits"] == 0


# ------------------------------------------------------------ adapter sync

def test_adapter_sync_writes_overrides() -> None:
  original_override_path = adapter_registry.ADAPTER_OVERRIDE_PATH
  with tempfile.TemporaryDirectory() as tmp:
    override_path = Path(tmp) / "override.json"
    adapter_registry.ADAPTER_OVERRIDE_PATH = override_path
    try:
      # Known family: override points the adapter at the installed repo.
      entry = {
        "status": "ready",
        "repo_dir": "/home/u/websplatserve/algs/taming3dgs",
        "venv": "/home/u/websplatserve/venvs/taming3dgs",
        "venv_python": "/home/u/websplatserve/venvs/taming3dgs/bin/python",
        "wrapper": "/home/u/websplatserve/bin/py-taming3dgs",
        "entry": "train.py",
        "installed_at": "2026-10-08T00:00:00Z",
      }
      updated = am.apply_install_result_to_adapter("taming3dgs", entry)
      assert updated["repo_path"] == entry["repo_dir"]
      assert updated["env_setup"]["wrapper"] == entry["wrapper"]
      # The base adapter family resolves through the registry as usual.
      assert adapter_registry.get_adapter("taming3dgs")["repo_path"] == entry["repo_dir"]

      # Custom repo: a complete override-only adapter appears in the registry.
      custom = am.apply_install_result_to_adapter(
        "my-new-gs", entry, repo_url="https://github.com/x/y", label="My New GS", pip_modules=["cv2"],
      )
      assert custom["family"] == "my-new-gs"
      assert custom["operations"]["train"]["enabled"]
      loaded = adapter_registry.get_adapter("my-new-gs")
      assert loaded is not None and loaded["repo_path"] == entry["repo_dir"]
      assert adapter_registry.validate_adapter(loaded)["is_ready"]

      # Partial/stale override fragments never become adapters.
      stale = json.loads(override_path.read_text(encoding="utf-8"))
      stale["overrides"]["half-written"] = {"repo_path": "/nowhere"}
      override_path.write_text(json.dumps(stale), encoding="utf-8")
      assert adapter_registry.get_adapter("half-written") is None
    finally:
      adapter_registry.ADAPTER_OVERRIDE_PATH = original_override_path


def main() -> int:
  tests = [
    test_glob_to_regex,
    test_cfloat_rule_inserts_after_first_include,
    test_np_cast_rule_rewrites_to_asarray,
    test_future_annotations_rule_inserts_after_docstring,
    test_arange_rule_adds_device,
    test_torch_load_rule_not_proactive,
    test_insert_after_first_include_without_include_prepends,
    test_fix_signature_matching,
    test_missing_module_and_traceback_extraction,
    test_module_to_pip_mapping,
    test_validate_repo_url_and_slug,
    test_build_catalog_merge_and_status_priority,
    test_generate_setup_script_structure,
    test_embedded_remote_patcher_runs,
    test_setup_script_executes_end_to_end,
    test_adapter_sync_writes_overrides,
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
