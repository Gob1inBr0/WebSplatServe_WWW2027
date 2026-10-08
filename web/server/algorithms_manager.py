"""Algorithm auto-install (env_setup): catalog, setup-script generation, patch
rules, self-heal signatures, and the remote install registry.

Design: docs/算法自动安装-设计实现计划.md. An install is a special platform
job (job_type=env_setup) that runs a generated bash script inside a remote tmux
session, reusing the training job machinery (log streaming, status polling,
persistence). The script clones the repo, builds a venv on top of the SHARC
torch environment, compiles CUDA submodules, applies the known-pitfall patch
rule library, installs missing deps, smoke-tests the entry point with a
self-heal retry loop, writes a dynamic-GPU wrapper, and merges the result into
the server-side registry (algs/registry.json).

Pure helpers (patch matching, signature matching, script generation) are kept
side-effect free so they can be unit-tested without SSH. The remote-side
patcher/self-heal reimplement the same matching on stdlib only — keep the two
in sync when editing rules semantics.
"""
from __future__ import annotations

import copy
import json
import logging
import re
import shlex
import time
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, List

from web.server.adapter_registry import (
  get_adapter,
  list_adapters,
  update_adapter_override,
)
from web.server.remote_executor import (
  RemoteExecutionError,
  _build_remote_tmux_start_command,
  _close_ssh_resources,
  _connect_kwargs,
  _ensure_remote_tmux_available,
  _new_ssh_client,
  _quote,
  _read_remote_text_file,
  _remote_job_paths,
  _run_remote_command,
  _write_remote_text,
  build_remote_paths,
  build_remote_run_key,
  build_remote_tmux_attach_command,
  build_remote_tmux_session_name,
  validate_remote_config,
)

LOGGER = logging.getLogger("webscan")

ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT_DIR / "web" / "config"
PATCH_RULES_PATH = CONFIG_DIR / "algs_patch_rules.json"
FIX_SIGNATURES_PATH = CONFIG_DIR / "algs_fix_signatures.json"

SETUP_JOB_TYPE = "env_setup"
SETUP_SESSION_ID = "algs-setup"
SETUP_STEP_ORDER = ["preflight", "clone", "venv", "compile", "patch", "deps", "smoke", "wrapper", "register"]
MIN_FREE_DISK_GB = 3
DEFAULT_ENTRY = "train.py"
CLONE_TIMEOUT_SECONDS = 900
SMOKE_MAX_ROUNDS = 3


# ---------------------------------------------------------------------------
# Config loading (patch rules / fix signatures)
# ---------------------------------------------------------------------------

def _load_json_config(path: Path) -> Dict[str, Any]:
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}
  except Exception:
    LOGGER.exception("Failed to read algs config %s", path)
    return {}


def load_patch_rules() -> List[Dict[str, Any]]:
  rules = _load_json_config(PATCH_RULES_PATH).get("rules", [])
  return [rule for rule in rules if isinstance(rule, dict) and rule.get("id")]


def load_fix_signatures() -> List[Dict[str, Any]]:
  signatures = _load_json_config(FIX_SIGNATURES_PATH).get("signatures", [])
  return [item for item in signatures if isinstance(item, dict) and item.get("id")]


def load_module_maps() -> tuple[Dict[str, str], Dict[str, str]]:
  data = _load_json_config(FIX_SIGNATURES_PATH)
  module_map = {str(k): str(v) for k, v in (data.get("module_map") or {}).items()}
  git_sources = {str(k): str(v) for k, v in (data.get("git_sources") or {}).items()}
  return module_map, git_sources


# ---------------------------------------------------------------------------
# Pure helpers: names, URLs, module mapping
# ---------------------------------------------------------------------------

def safe_setup_name(value: str) -> str:
  """Slug used for repo/venv/wrapper names (letters, digits, ._-)."""
  text = str(value or "").strip().lower()
  slug = re.sub(r"[^a-z0-9._-]+", "-", text).strip("-_.")
  return slug[:64].strip("-_.") or "algorithm"


def validate_repo_url(url: str) -> str:
  """Only plain https git URLs are accepted (no ssh, no shell metacharacters)."""
  text = str(url or "").strip()
  if not text:
    return ""
  if not text.startswith("https://"):
    raise RemoteExecutionError(
      "repo_url must be an https:// git URL.",
      code_hint="WGSC-ALGS-URL-001",
      stage="install",
    )
  if re.search(r"[;&|`$<>()\n\r\"'\\]", text):
    raise RemoteExecutionError(
      "repo_url contains forbidden characters.",
      code_hint="WGSC-ALGS-URL-002",
      stage="install",
    )
  return text


def module_import_name(module: str) -> str:
  return str(module or "").strip().replace("-", "_")


def module_to_pip(module: str) -> Dict[str, str]:
  """Map an import name to an install spec: {"kind": "pip"|"git", "spec": ...}."""
  name = str(module or "").strip()
  module_map, git_sources = load_module_maps()
  if name in git_sources:
    return {"kind": "git", "spec": git_sources[name]}
  if name in module_map:
    return {"kind": "pip", "spec": module_map[name]}
  return {"kind": "pip", "spec": name}


# ---------------------------------------------------------------------------
# Pure helpers: patch rule engine
# ---------------------------------------------------------------------------

def glob_to_regex(pattern: str) -> re.Pattern:
  """Translate a file_glob ('**/*.cu', '*.py') to a regex over posix relpaths."""
  text = str(pattern or "").strip() or "**/*"
  regex = ""
  index = 0
  while index < len(text):
    char = text[index]
    if char == "*":
      if text[index:index + 3] == "**/":
        regex += "(?:[^/]+/)*"
        index += 3
        continue
      if text[index:index + 2] == "**":
        regex += ".*"
        index += 2
        continue
      regex += "[^/]*"
    elif char == "?":
      regex += "[^/]"
    else:
      regex += re.escape(char)
    index += 1
  return re.compile(regex + r"\Z")


def rule_matches_file(rule: Dict[str, Any], rel_path: str, text: str) -> bool:
  when = rule.get("when") if isinstance(rule.get("when"), dict) else {}
  pattern = glob_to_regex(str(when.get("file_glob", "**/*")))
  normalized = str(rel_path or "").replace("\\", "/").lstrip("./")
  if not pattern.match(normalized):
    return False
  if "contains" in when and str(when["contains"]) not in text:
    return False
  if "not_contains" in when and str(when["not_contains"]) in text:
    return False
  if when.get("contains_regex") and not re.search(str(when["contains_regex"]), text):
    return False
  return True


_DOCSTRING_START = re.compile(r"^(\s*)('''|\"\"\")")


def apply_action(text: str, action_spec: Dict[str, Any]) -> tuple[str, int]:
  """Apply a rule's `then` block to one file's text. Returns (new_text, edits)."""
  action = str(action_spec.get("action", ""))
  line = str(action_spec.get("line", ""))
  replacements = action_spec.get("replacements") or []
  if isinstance(action_spec.get("find"), str):
    replacements = [{"find": action_spec["find"], "replace": str(action_spec.get("replace", ""))}]

  if action == "insert_after_first_include":
    lines = text.splitlines(keepends=True)
    for index, candidate in enumerate(lines):
      if re.match(r"\s*#\s*include\b", candidate):
        lines.insert(index + 1, line + "\n")
        return "".join(lines), 1
    return line + "\n" + text, 1

  if action == "insert_after_docstring":
    lines = text.splitlines(keepends=True)
    offset = 0
    # Skip leading comments / blank lines before the module docstring.
    while offset < len(lines) and (not lines[offset].strip() or lines[offset].lstrip().startswith("#")):
      offset += 1
    match = _DOCSTRING_START.match(lines[offset]) if offset < len(lines) else None
    if match:
      quote = match.group(2)
      closing = re.compile(re.escape(quote))
      index = offset + 1
      # A single-line docstring closes on the opening line already.
      if closing.search(lines[offset][match.end():].rstrip("\n")) is None:
        while index < len(lines) and closing.search(lines[index]) is None:
          index += 1
        index += 1
      insert_at = index
    else:
      insert_at = offset
    lines.insert(insert_at, line + "\n")
    return "".join(lines), 1

  if action in ("sed", "sed_regex"):
    total = 0
    for replacement in replacements:
      find = str(replacement.get("find", ""))
      replace = str(replacement.get("replace", ""))
      if not find:
        continue
      if action == "sed":
        count = text.count(find)
        if count:
          text = text.replace(find, replace)
          total += count
      else:
        try:
          text, count = re.subn(find, replace, text)
        except re.error:
          continue
        total += count
    return text, total

  return text, 0


def apply_rule_to_text(rule: Dict[str, Any], rel_path: str, text: str) -> tuple[str, int]:
  if not rule_matches_file(rule, rel_path, text):
    return text, 0
  return apply_action(text, rule.get("then") if isinstance(rule.get("then"), dict) else {})


# ---------------------------------------------------------------------------
# Pure helpers: fix signatures
# ---------------------------------------------------------------------------

def match_fix_signature(log_tail: str, signatures: List[Dict[str, Any]] | None = None) -> Dict[str, Any] | None:
  """First signature whose regex matches the log tail (list order = priority)."""
  tail = str(log_tail or "")
  for signature in (signatures if signatures is not None else load_fix_signatures()):
    pattern = str(signature.get("signature", ""))
    if not pattern:
      continue
    try:
      match = re.search(pattern, tail)
    except re.error:
      continue
    if match:
      return {**signature, "_match": match}
  return None


def extract_missing_module(log_tail: str) -> str:
  match = re.search(r"No module named ['\"]([a-zA-Z0-9_.-]+)['\"]", str(log_tail or ""))
  return match.group(1) if match else ""


def extract_traceback_files(log_tail: str) -> List[str]:
  """.py file paths as written in the traceback, deduped, order kept."""
  seen: List[str] = []
  for raw in re.findall(r"File \"([^\"]+\.py)\"", str(log_tail or "")):
    if raw not in seen:
      seen.append(raw)
  return seen


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

def _registry_entries(registry: Dict[str, Any] | None) -> Dict[str, Dict[str, Any]]:
  if not isinstance(registry, dict):
    return {}
  algorithms = registry.get("algorithms")
  if isinstance(algorithms, dict):
    return {str(k): v for k, v in algorithms.items() if isinstance(v, dict)}
  return {str(k): v for k, v in registry.items() if isinstance(v, dict)}


def get_registry_entry(registry: Dict[str, Any] | None, family: str) -> Dict[str, Any]:
  return _registry_entries(registry).get(str(family or "").strip()) or {}


def build_catalog(
  *,
  registry: Dict[str, Any] | None = None,
  active_setups: Dict[str, Dict[str, Any]] | None = None,
  failed_setups: Dict[str, Dict[str, Any]] | None = None,
  adapters: List[Dict[str, Any]] | None = None,
  discovered: List[str] | None = None,
) -> Dict[str, Any]:
  """Merge adapter declarations, the install registry, in-flight setup jobs,
  and (optionally) server-scanned repo dirs into one catalog view."""
  entries: List[Dict[str, Any]] = []
  adapters = adapters if adapters is not None else list_adapters()
  registry_entries = _registry_entries(registry)
  active_setups = active_setups or {}
  failed_setups = failed_setups or {}
  discovered = discovered or []
  known_names: set[str] = set()

  for adapter in adapters:
    family = str(adapter.get("family", "")).strip()
    if not family:
      continue
    known_names.add(family)
    known_names.add(safe_setup_name(family))
    entry = registry_entries.get(family) or registry_entries.get(safe_setup_name(family))
    active = active_setups.get(family)
    failed = failed_setups.get(family)
    if active:
      status = "installing"
    elif failed:
      status = "failed"
    elif entry:
      status = str(entry.get("status") or "ready")
    elif str(adapter.get("repo_path", "") or "").strip():
      status = "ready"  # manually configured outside auto-install
    else:
      status = "not_installed"
    live = active or failed or {}
    steps = live.get("setup_steps") if isinstance(live.get("setup_steps"), list) else []
    entries.append({
      "name": family,
      "label": adapter.get("label", family),
      "category": adapter.get("category", ""),
      "repo_url": adapter.get("repo_url", ""),
      "repo_dir": entry.get("repo_dir", "") if entry else "",
      "entry": entry.get("entry", DEFAULT_ENTRY) if entry else DEFAULT_ENTRY,
      "status": status,
      "source": "registry" if entry else "adapter",
      "manual": bool(not entry and not active and not failed and status == "ready"),
      "installed_at": entry.get("installed_at", "") if entry else "",
      "venv": entry.get("venv", "") if entry else "",
      "wrapper": entry.get("wrapper", "") if entry else "",
      "active_job_id": live.get("id", "") if live else "",
      "setup_steps": steps,
      "failure_reason": str(live.get("failure_reason", "") or "") if live else "",
      "trainable": bool((adapter.get("operations", {}).get("train", {}) or {}).get("enabled")),
    })

  for repo_dir in discovered:
    name = safe_setup_name(PurePosixPath(str(repo_dir)).name)
    if not name or name in known_names:
      continue
    known_names.add(name)
    entry = registry_entries.get(name)
    entries.append({
      "name": name,
      "label": name,
      "category": "discovered",
      "repo_url": "",
      "repo_dir": str(repo_dir),
      "entry": entry.get("entry", DEFAULT_ENTRY) if entry else DEFAULT_ENTRY,
      "status": str(entry.get("status") or "ready") if entry else "discovered",
      "source": "scan",
      "manual": False,
      "installed_at": entry.get("installed_at", "") if entry else "",
      "venv": entry.get("venv", "") if entry else "",
      "wrapper": entry.get("wrapper", "") if entry else "",
      "active_job_id": "",
      "setup_steps": [],
      "failure_reason": "",
      "trainable": False,
    })

  counts = {
    "ready": sum(1 for e in entries if e["status"] == "ready"),
    "installing": sum(1 for e in entries if e["status"] == "installing"),
    "failed": sum(1 for e in entries if e["status"] == "failed"),
    "not_installed": sum(1 for e in entries if e["status"] in ("not_installed", "discovered")),
  }
  return {"ok": True, "algorithms": entries, "counts": counts, "step_order": SETUP_STEP_ORDER}


def install_params_for(family: str) -> Dict[str, Any]:
  """Default install parameters (repo_url / pip modules / label) for a family."""
  adapter = get_adapter(family) or {}
  requirements = adapter.get("requirements", {}) or {}
  modules = [str(m).strip() for m in requirements.get("python_modules", []) if str(m).strip()]
  return {
    "repo_url": str(adapter.get("repo_url", "") or ""),
    "pip_modules": modules,
    "label": str(adapter.get("label", "") or family),
  }


# ---------------------------------------------------------------------------
# Remote layout + registry (SSH-backed)
# ---------------------------------------------------------------------------

def remote_setup_layout(validated_remote: Dict[str, Any]) -> Dict[str, str]:
  """Server-side dirs for auto-installed algorithms, derived from the profile's
  workspace_root (/home/u/websplatserve/workspaces → sibling algs/ venvs/ bin/)."""
  workspace_root = str(validated_remote.get("workspace_root", "") or "").strip()
  output_root = str(validated_remote.get("output_root", "") or "").strip()
  if not workspace_root or not output_root:
    raise RemoteExecutionError(
      "remote.workspace_root and remote.output_root are required for algorithm install.",
      code_hint="WGSC-ALGS-LAYOUT-001",
      stage="install",
    )
  data_root = str(PurePosixPath(workspace_root).parent)
  return {
    "data_root": data_root,
    "algs_root": str(PurePosixPath(data_root) / "algs"),
    "venvs_root": str(PurePosixPath(data_root) / "venvs"),
    "bin_dir": str(PurePosixPath(data_root) / "bin"),
    "registry_path": str(PurePosixPath(data_root) / "algs" / "registry.json"),
  }


def setup_remote_paths(validated_remote: Dict[str, Any], *, family: str, job_id: str) -> Dict[str, str]:
  run_key = build_remote_run_key("envsetup", family, time.time())
  paths = build_remote_paths(
    workspace_root=validated_remote["workspace_root"],
    output_root=validated_remote["output_root"],
    session_id=SETUP_SESSION_ID,
    family=family,
    job_id=job_id,
    run_key=run_key,
  )
  job_paths = _remote_job_paths(paths["output_dir"])
  tmux_session = build_remote_tmux_session_name(family=f"algs-{family}", job_id=job_id, run_key=run_key)
  return {
    "run_key": run_key,
    "remote_output_dir": paths["output_dir"],
    **job_paths,
    "remote_tmux_session": tmux_session,
    "remote_tmux_attach_command": build_remote_tmux_attach_command(validated_remote, tmux_session),
  }


def _ssh_connect(validated: Dict[str, Any]):
  client = _new_ssh_client(validated)
  client.connect(
    hostname=validated["host"],
    port=validated["port"],
    username=validated["username"],
    **_connect_kwargs(validated),
    timeout=20,
  )
  return client


def fetch_remote_registry(remote_config: Dict[str, Any]) -> Dict[str, Any]:
  validated = validate_remote_config(remote_config)
  registry_path = remote_setup_layout(validated)["registry_path"]
  client = _ssh_connect(validated)
  sftp = None
  try:
    sftp = client.open_sftp()
    raw = _read_remote_text_file(sftp, registry_path)
    if not raw.strip():
      return {"algorithms": {}}
    data = json.loads(raw)
    return data if isinstance(data, dict) else {"algorithms": {}}
  except json.JSONDecodeError:
    return {"algorithms": {}}
  finally:
    _close_ssh_resources(client, sftp)


def scan_remote_algs(remote_config: Dict[str, Any]) -> Dict[str, Any]:
  """List repo directories under the server's algs/ root (scan button)."""
  validated = validate_remote_config(remote_config)
  layout = remote_setup_layout(validated)
  client = _ssh_connect(validated)
  sftp = None
  try:
    sftp = client.open_sftp()
    try:
      names = sftp.listdir(layout["algs_root"])
    except Exception:
      names = []
    discovered = sorted(
      str(PurePosixPath(layout["algs_root"]) / name)
      for name in names
      if name != "registry.json" and not name.startswith(".")
    )
    registry = {"algorithms": {}}
    raw = _read_remote_text_file(sftp, layout["registry_path"])
    if raw.strip():
      try:
        loaded = json.loads(raw)
        if isinstance(loaded, dict):
          registry = loaded
      except json.JSONDecodeError:
        pass
    return {"ok": True, "discovered": discovered, "registry": registry, "layout": layout}
  finally:
    _close_ssh_resources(client, sftp)


def start_remote_setup_detached(
  *,
  remote_config: Dict[str, Any],
  job_id: str,
  family: str,
  script_text: str,
  run_key: str,
  log_callback: Callable[[str, str], None] | None = None,
  stage_callback: Callable[[str], None] | None = None,
) -> Dict[str, Any]:
  """Upload the generated setup script and start it in a remote tmux session."""
  validated = validate_remote_config(remote_config)
  paths = build_remote_paths(
    workspace_root=validated["workspace_root"],
    output_root=validated["output_root"],
    session_id=SETUP_SESSION_ID,
    family=family,
    job_id=job_id,
    run_key=run_key,
  )
  job_paths = _remote_job_paths(paths["output_dir"])
  tmux_session = build_remote_tmux_session_name(family=f"algs-{family}", job_id=job_id, run_key=run_key)

  client = _new_ssh_client(validated)
  sftp = None
  try:
    if stage_callback:
      stage_callback("connecting")
    client.connect(
      hostname=validated["host"],
      port=validated["port"],
      username=validated["username"],
      **_connect_kwargs(validated),
      timeout=20,
    )
    sftp = client.open_sftp()
    if stage_callback:
      stage_callback("checking_tmux")
    tmux_install = _ensure_remote_tmux_available(client, log_callback)
    if stage_callback:
      stage_callback("uploading_setup_script")
    _write_remote_text(sftp, job_paths["run_script"], script_text)
    start_command = _build_remote_tmux_start_command(job_paths, tmux_session)
    if stage_callback:
      stage_callback("starting_detached_remote_job")
    start_rc = _run_remote_command(client, f"bash -lc {_quote(start_command)}", log_callback)
    if start_rc != 0:
      raise RemoteExecutionError(
        "Failed to start detached remote setup job.",
        code_hint="WGSC-ALGS-DETACH-001",
        stage="detach",
      )
    remote_pid = _read_remote_text_file(sftp, job_paths["pid_file"]).strip()
    launcher_pid = _read_remote_text_file(sftp, job_paths["launcher_pid_file"]).strip()
    if log_callback:
      log_callback("stdout", (
        f"[Tmux] Remote setup job started in tmux session {tmux_session}. "
        f"PID: {remote_pid or launcher_pid or '-'}; log: {job_paths['runtime_log']}\n"
        f"[Tmux] Attach command: {build_remote_tmux_attach_command(validated, tmux_session)}\n"
      ))
    if stage_callback:
      stage_callback("remote_detached_running")
    return {
      "execution_backend": "tmux",
      "remote_detached": True,
      "safe_to_close_web": True,
      "remote_pid": remote_pid or launcher_pid,
      "remote_tmux_session": tmux_session,
      "remote_tmux_attach_command": build_remote_tmux_attach_command(validated, tmux_session),
      "tmux_available": True,
      "tmux_install": tmux_install,
      "remote_run_key": run_key,
      "remote_output_dir": paths["output_dir"],
      "remote_job_dir": job_paths["job_dir"],
      "remote_run_script": job_paths["run_script"],
      "remote_log_path": job_paths["runtime_log"],
      "remote_status_path": job_paths["status_file"],
      "remote_exit_code_path": job_paths["exit_code_file"],
    }
  finally:
    _close_ssh_resources(client, sftp)


def uninstall_remote_algorithm(
  *,
  remote_config: Dict[str, Any],
  name: str,
  remove_repo: bool = False,
) -> Dict[str, Any]:
  """Remove the venv and the registry entry; keep the repo dir by default.

  Step markers (.setup_state) are always cleared so a later install re-runs the
  steps instead of skipping over a deleted venv.
  """
  validated = validate_remote_config(remote_config)
  slug = safe_setup_name(name)
  layout = remote_setup_layout(validated)
  venv_dir = str(PurePosixPath(layout["venvs_root"]) / slug)
  repo_dir = str(PurePosixPath(layout["algs_root"]) / slug)
  state_dir = str(PurePosixPath(layout["algs_root"], ".setup_state", slug))
  helper_path = str(PurePosixPath(layout["data_root"]) / ".wgsc_algs_uninstall.py")
  client = _ssh_connect(validated)
  sftp = None
  try:
    sftp = client.open_sftp()
    _write_remote_text(sftp, helper_path, _UNINSTALL_HELPER)
  finally:
    _close_ssh_resources(client, sftp)

  registry_command = (
    f"{_quote(validated['python'])} {_quote(helper_path)} "
    f"{_quote(layout['registry_path'])} {_quote(slug)}"
  )
  cleanup_command = (
    f"rm -rf {_quote(venv_dir)} {_quote(state_dir)}"
    + (f" && rm -rf {_quote(repo_dir)}" if remove_repo else "")
  )
  client = _ssh_connect(validated)
  try:
    _, stdout, _ = client.exec_command(f"bash -lc {_quote(registry_command)}", timeout=30)
    registry_rc = stdout.channel.recv_exit_status()
    registry_output = stdout.read().decode("utf-8", errors="replace").strip()
    if registry_rc != 0:
      raise RemoteExecutionError(
        f"Registry update failed during uninstall (exit {registry_rc}).",
        code_hint="WGSC-ALGS-UNINSTALL-001",
        stage="uninstall",
      )
    _, stdout, _ = client.exec_command(f"bash -lc {_quote(cleanup_command)}", timeout=60)
    cleanup_rc = stdout.channel.recv_exit_status()
    if cleanup_rc != 0:
      raise RemoteExecutionError(
        f"Failed to remove venv directory {venv_dir} (exit {cleanup_rc}).",
        code_hint="WGSC-ALGS-UNINSTALL-002",
        stage="uninstall",
      )
  finally:
    client.close()

  removed = False
  try:
    removed = bool(json.loads(registry_output or "{}").get("removed"))
  except json.JSONDecodeError:
    pass
  return {
    "ok": True,
    "name": slug,
    "registry_entry_removed": removed,
    "removed_venv": venv_dir,
    "removed_repo": repo_dir if remove_repo else "",
    "repo_retained": not remove_repo,
  }


_UNINSTALL_HELPER = """import json, os, sys
registry_path, name = sys.argv[1], sys.argv[2]
data = {"algorithms": {}}
try:
    with open(registry_path, "r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    if isinstance(loaded, dict) and isinstance(loaded.get("algorithms"), dict):
        data = loaded
except Exception:
    pass
removed = data["algorithms"].pop(name, None)
tmp = registry_path + ".tmp.%d" % os.getpid()
os.makedirs(os.path.dirname(registry_path), exist_ok=True)
with open(tmp, "w", encoding="utf-8") as handle:
    json.dump(data, handle, ensure_ascii=False, indent=2)
os.replace(tmp, registry_path)
print(json.dumps({"removed": bool(removed), "registry": data}))
"""


# ---------------------------------------------------------------------------
# Adapter sync after a successful install
# ---------------------------------------------------------------------------

CUSTOM_ADAPTER_TEMPLATE: Dict[str, Any] = {
  "family": "",
  "label": "",
  "category": "custom",
  "representation": "sh",
  "compatibility": "viewer-ready",
  "repo_type": "remote",
  "repo_path": "",
  "repo_url": "",
  "default_cwd": "",
  "operations": {
    "train": {
      "enabled": True,
      "template": "python train.py -s {workspace} -m {output_dir} --eval --iterations {iterations}",
    },
    "render": {"enabled": True, "template": "python render.py -m {output_dir} --skip_train"},
    "metrics": {"enabled": True, "template": "python metrics.py -m {output_dir}"},
  },
  "requirements": {"python_modules": [], "install_commands": {}},
  "notes": "Installed via the console algorithm auto-install page.",
}


def apply_install_result_to_adapter(
  family: str,
  entry: Dict[str, Any],
  *,
  repo_url: str = "",
  label: str = "",
  pip_modules: List[str] | None = None,
) -> Dict[str, Any]:
  """Point the adapter at the freshly installed remote repo.

  Known families get a repo_path/default_cwd override (absolute remote path —
  the wizard forwards it as remote.repo_path on submit). Custom repos get a
  complete new adapter with the vanilla train template.
  """
  env_setup = {
    "status": str(entry.get("status") or "ready"),
    "repo_dir": str(entry.get("repo_dir", "")),
    "venv": str(entry.get("venv", "")),
    "venv_python": str(entry.get("venv_python", "")),
    "wrapper": str(entry.get("wrapper", "")),
    "entry": str(entry.get("entry", DEFAULT_ENTRY)),
    "installed_at": str(entry.get("installed_at", "")),
  }
  if get_adapter(family):
    return update_adapter_override(family, {
      "repo_path": env_setup["repo_dir"],
      "default_cwd": env_setup["repo_dir"],
      "env_setup": env_setup,
    })

  custom = copy.deepcopy(CUSTOM_ADAPTER_TEMPLATE)
  custom["family"] = family
  custom["label"] = label or family
  custom["repo_url"] = repo_url
  custom["repo_path"] = env_setup["repo_dir"]
  custom["default_cwd"] = env_setup["repo_dir"]
  if pip_modules:
    custom["requirements"] = {"python_modules": list(pip_modules), "install_commands": {}}
  custom["env_setup"] = env_setup
  return update_adapter_override(family, custom)


# ---------------------------------------------------------------------------
# Setup script generation (runs on the training server inside tmux)
# ---------------------------------------------------------------------------

_WRAPPER_SCRIPT_TEMPLATE = """#!/usr/bin/env bash
# Dynamic GPU wrapper (generated by WGSC algs-setup).
# Picks the GPU with the most free memory, then execs the algorithm venv python.
set -e
BEST_GPU=""
BEST_FREE=-1
while IFS=',' read -r IDX FREE; do
  FREE_NUM=$(echo "$FREE" | tr -d ' ')
  case "$FREE_NUM" in ''|*[!0-9]*) continue ;; esac
  if [ "$FREE_NUM" -gt "$BEST_FREE" ]; then BEST_FREE=$FREE_NUM; BEST_GPU=$IDX; fi
done < <(nvidia-smi --query-gpu=index,memory.free --format=csv,noheader,nounits 2>/dev/null || true)
if [ -n "$BEST_GPU" ]; then
  export CUDA_VISIBLE_DEVICES="$BEST_GPU"
  echo "[wrapper] CUDA_VISIBLE_DEVICES=$BEST_GPU (${BEST_FREE} MiB free)" >&2
fi
exec __VENV_PYTHON__ "$@"
"""


def generate_wrapper_script(venv_python: str) -> str:
  """Dynamic GPU-selection wrapper: execs the venv python on the freest GPU."""
  return _WRAPPER_SCRIPT_TEMPLATE.replace("__VENV_PYTHON__", shlex.quote(str(venv_python)))


_REMOTE_PATCHER_PY = '''#!/usr/bin/env python3
"""WGSC algs patcher: apply known-pitfall patch rules to a repository.

Standalone (stdlib only) — uploaded alongside the setup script. Mirrors the
pure matching helpers in web/server/algorithms_manager.py; keep the semantics
of glob matching and actions in sync when editing either side.
"""
import argparse
import json
import os
import re
import sys

EXCLUDED_DIRS = {".git", "build", "dist", "__pycache__", "node_modules", ".venv", "venv", ".setup_state"}


def glob_to_regex(pattern):
    text = str(pattern or "").strip() or "**/*"
    regex = ""
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "*":
            if text[i:i + 3] == "**/":
                regex += "(?:[^/]+/)*"
                i += 3
                continue
            if text[i:i + 2] == "**":
                regex += ".*"
                i += 2
                continue
            regex += "[^/]*"
        elif ch == "?":
            regex += "[^/]"
        else:
            regex += re.escape(ch)
        i += 1
    return re.compile(regex + r"\\Z")


def iter_files(repo, pattern):
    regex = glob_to_regex(pattern)
    for root, dirnames, filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for name in filenames:
            rel = os.path.relpath(os.path.join(root, name), repo).replace(os.sep, "/")
            if regex.match(rel):
                yield rel


def rule_matches(rule, rel, text):
    when = rule.get("when") or {}
    if not glob_to_regex(str(when.get("file_glob", "**/*"))).match(rel):
        return False
    if "contains" in when and str(when["contains"]) not in text:
        return False
    if "not_contains" in when and str(when["not_contains"]) in text:
        return False
    if when.get("contains_regex"):
        try:
            if not re.search(str(when["contains_regex"]), text):
                return False
        except re.error:
            return False
    return True


def apply_action(text, spec):
    action = str(spec.get("action", ""))
    line = str(spec.get("line", ""))
    replacements = spec.get("replacements") or []
    if isinstance(spec.get("find"), str):
        replacements = [{"find": spec["find"], "replace": str(spec.get("replace", ""))}]
    if action == "insert_after_first_include":
        lines = text.splitlines(keepends=True)
        for idx, cand in enumerate(lines):
            if re.match(r"\\s*#\\s*include\\b", cand):
                lines.insert(idx + 1, line + "\\n")
                return "".join(lines), 1
        return line + "\\n" + text, 1
    if action == "insert_after_docstring":
        lines = text.splitlines(keepends=True)
        off = 0
        while off < len(lines) and (not lines[off].strip() or lines[off].lstrip().startswith("#")):
            off += 1
        m = re.match(r"^(\\s*)(['\\\"]{3})", lines[off]) if off < len(lines) else None
        if m:
            quote = m.group(2)
            idx = off + 1
            if re.search(re.escape(quote), lines[off][m.end():].rstrip("\\n")) is None:
                while idx < len(lines) and re.search(re.escape(quote), lines[idx]) is None:
                    idx += 1
                idx += 1
            insert_at = idx
        else:
            insert_at = off
        lines.insert(insert_at, line + "\\n")
        return "".join(lines), 1
    if action in ("sed", "sed_regex"):
        total = 0
        for rep in replacements:
            find = str(rep.get("find", ""))
            replace = str(rep.get("replace", ""))
            if not find:
                continue
            if action == "sed":
                cnt = text.count(find)
                if cnt:
                    text = text.replace(find, replace)
                    total += cnt
            else:
                try:
                    text, cnt = re.subn(find, replace, text)
                except re.error:
                    continue
                total += cnt
        return text, total
    return text, 0


def apply_rule(repo, rule, only_files=None):
    when = rule.get("when") or {}
    changed_files = 0
    edits = 0
    for rel in iter_files(repo, when.get("file_glob", "**/*")):
        if only_files is not None and rel not in only_files:
            continue
        path = os.path.join(repo, rel)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
        except Exception:
            continue
        if not rule_matches(rule, rel, text):
            continue
        new_text, count = apply_action(text, rule.get("then") or {})
        if count and new_text != text:
            try:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(new_text)
            except Exception as exc:
                print("[patcher] WARN cannot write %s: %s" % (rel, exc))
                continue
            changed_files += 1
            edits += count
            print("[patcher] %s: %d edit(s) (rule %s)" % (rel, count, rule.get("id")))
    return changed_files, edits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--rules", required=True)
    ap.add_argument("--ids", default="")
    ap.add_argument("--files", default="")
    ap.add_argument("--proactive-only", action="store_true")
    args = ap.parse_args()
    with open(args.rules, "r", encoding="utf-8") as handle:
        rules = json.load(handle).get("rules", [])
    wanted = [r for r in args.ids.split(",") if r]
    only = set(f for f in args.files.split(",") if f) or None
    summary = []
    total_edits = 0
    for rule in rules:
        if wanted and rule.get("id") not in wanted:
            continue
        if args.proactive_only and rule.get("proactive") is False:
            continue
        changed, edits = apply_rule(args.repo, rule, only)
        total_edits += edits
        summary.append({"id": rule.get("id"), "files": changed, "edits": edits})
    print("PATCHER_RESULT " + json.dumps({"rules": summary, "total_edits": total_edits}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


_REMOTE_SELFHEAL_PY = '''#!/usr/bin/env python3
"""WGSC self-heal: match a smoke-failure log tail against fix signatures and
apply the mapped fix. Exit codes: 0 fix applied (caller retries), 10 nothing
applicable, 20 fix attempted but failed."""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wgsc_patcher

LOG_TAIL_LINES = 200


def read_tail(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return "".join(handle.readlines()[-LOG_TAIL_LINES:])
    except Exception:
        return ""


def resolve_spec(module, config):
    git_sources = config.get("git_sources") or {}
    module_map = config.get("module_map") or {}
    if module in git_sources:
        return "git:" + git_sources[module]
    if module in module_map:
        return "pip:" + module_map[module]
    return "pip:" + module


def pip_install(venv_py, spec):
    if spec.startswith("git:"):
        argv = [venv_py, "-m", "pip", "install", "--no-build-isolation", "git+" + spec[4:]]
    else:
        argv = [venv_py, "-m", "pip", "install", spec[4:]]
    print("[SelfHeal] running: %s" % " ".join(argv))
    return subprocess.call(argv)


def traceback_rel_files(tail, repo):
    files = set()
    for raw in re.findall(r\'File "([^"]+\\.py)"\', tail):
        if not os.path.isabs(raw):
            raw = os.path.join(repo, raw)
        rel = os.path.relpath(os.path.abspath(raw), os.path.abspath(repo))
        if not rel.startswith(".."):
            files.add(rel.replace(os.sep, "/"))
    return files


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "resolve-package":
        module = sys.argv[2]
        with open(sys.argv[3], "r", encoding="utf-8") as handle:
            config = json.load(handle)
        print(resolve_spec(module, config))
        return 0

    opts = {}
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i].startswith("--") and i + 1 < len(args):
            opts[args[i][2:]] = args[i + 1]
            i += 2
        else:
            i += 1
    tail = read_tail(opts.get("log", ""))
    with open(opts["signatures"], "r", encoding="utf-8") as handle:
        config = json.load(handle)
    with open(opts["rules"], "r", encoding="utf-8") as handle:
        rules = json.load(handle).get("rules", [])
    venv_py = opts.get("venv-py", sys.executable)
    repo = opts.get("repo", ".")

    for signature in config.get("signatures", []):
        try:
            match = re.search(str(signature.get("signature", "")), tail)
        except re.error:
            continue
        if not match:
            continue
        action = str(signature.get("action", ""))
        print("[SelfHeal] matched signature %s: %s" % (signature.get("id"), signature.get("note", "")))
        if action == "pip_install":
            module = match.group(1) if match.groups() else ""
            if not module:
                fallback = re.search(r"No module named [\'\\"]([a-zA-Z0-9_.-]+)[\'\\"]", tail)
                module = fallback.group(1) if fallback else ""
            if not module:
                return 10
            spec = resolve_spec(module, config)
            print("[SelfHeal] installing missing module %s as %s" % (module, spec))
            return 0 if pip_install(venv_py, spec) == 0 else 20
        if action == "apply_patch_rule":
            rule_id = str(signature.get("rule", ""))
            rule = next((r for r in rules if r.get("id") == rule_id), None)
            if rule is None:
                print("[SelfHeal] rule %s not found in patch rules" % rule_id)
                return 10
            only = None
            if str(signature.get("scope", "")) == "traceback":
                only = traceback_rel_files(tail, repo) or None
                if only:
                    print("[SelfHeal] scoped to traceback files: %s" % ", ".join(sorted(only)))
            changed, edits = wgsc_patcher.apply_rule(repo, rule, only)
            if changed:
                print("[SelfHeal] rule %s changed %d file(s)" % (rule_id, changed))
                return 0
            print("[SelfHeal] rule %s matched no files — no fix applied" % rule_id)
            return 10
        return 10  # action "none": informational only

    print("[SelfHeal] no signature matched the log tail")
    return 10


if __name__ == "__main__":
    sys.exit(main())
'''


_REMOTE_SETUPCTL_PY = '''#!/usr/bin/env python3
"""WGSC setup bookkeeping: step states, status.json writer, registry merge."""
import json
import os
import sys
import time


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_json(path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, type(fallback)) else fallback
    except Exception:
        return fallback


def atomic_write(path, payload):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""

    if cmd == "set-step":
        steps_file, name, status, detail, state_dir = sys.argv[2:7]
        steps = load_json(steps_file, {})
        steps[name] = {"status": status, "detail": str(detail or "")[:300]}
        atomic_write(steps_file, steps)
        if status == "success":
            os.makedirs(state_dir, exist_ok=True)
            with open(os.path.join(state_dir, "step_%s.done" % name), "w", encoding="utf-8") as handle:
                handle.write(utc_now())
        return 0

    if cmd == "write-status":
        status_path = sys.argv[2]
        env = os.environ
        order = [s for s in env.get("WGSC_STEP_ORDER", "").split() if s]
        steps = load_json(env.get("WGSC_STEPS_FILE", ""), {})
        setup_steps = [dict(steps[name], name=name) for name in order if name in steps]
        payload = {
            "job_id": env.get("WGSC_JOB_ID", ""),
            "family": env.get("WGSC_FAMILY", ""),
            "status": env.get("WGSC_STATUS", ""),
            "stage": env.get("WGSC_STAGE", ""),
            "pid": env.get("WGSC_PID", ""),
            "message": env.get("WGSC_MESSAGE", ""),
            "remote_log_path": env.get("WGSC_LOG_PATH", ""),
            "remote_output_dir": env.get("WGSC_OUTPUT_DIR", ""),
            "remote_command": "",
            "setup_steps": setup_steps,
            "updated_at": time.time(),
        }
        rc = env.get("WGSC_RETURN_CODE", "")
        if rc not in ("", None):
            try:
                payload["return_code"] = int(rc)
            except ValueError:
                payload["return_code"] = rc
        atomic_write(status_path, payload)
        return 0

    if cmd == "register":
        registry_path, name, family, repo_dir, venv_dir, wrapper, entry, venv_py = sys.argv[2:10]
        data = load_json(registry_path, {})
        if not isinstance(data.get("algorithms"), dict):
            data["algorithms"] = {}
        data["algorithms"][name] = {
            "family": family,
            "repo_dir": repo_dir,
            "venv": venv_dir,
            "venv_python": venv_py,
            "wrapper": wrapper,
            "entry": entry,
            "status": "ready",
            "installed_at": utc_now(),
        }
        atomic_write(registry_path, data)
        print("[register] %s -> ready (%s)" % (name, repo_dir))
        return 0

    print("usage: setupctl.py set-step|write-status|register ...", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
'''


_SETUP_SCRIPT_TEMPLATE = """#!/usr/bin/env bash
# WGSC algs-setup for __FAMILY__ — generated by web/server/algorithms_manager.py.
# Runs inside a remote tmux session. Every step updates status.json (same
# reader as training jobs) and writes a .done marker so retries skip the steps
# that already succeeded.
set +e

PYTHON_BIN=__PYTHON_BIN__
NAME=__NAME__
FAMILY=__FAMILY__
REPO_URL=__REPO_URL__
REPO_DIR=__REPO_DIR__
ENTRY=__ENTRY__
ALGS_ROOT=__ALGS_ROOT__
VENVS_ROOT=__VENVS_ROOT__
BIN_DIR=__BIN_DIR__
REGISTRY_PATH=__REGISTRY_PATH__
MIN_FREE_GB=__MIN_FREE_GB__
JOB_ID=__JOB_ID__
JOB_DIR=__JOB_DIR__
STATUS_FILE=__STATUS_FILE__
EXIT_CODE_FILE=__EXIT_CODE_FILE__
LOG_FILE=__LOG_FILE__
PID_FILE=__PID_FILE__
OUTPUT_DIR=__OUTPUT_DIR__
CLONE_TIMEOUT=__CLONE_TIMEOUT__
SMOKE_ROUNDS=__SMOKE_ROUNDS__
STEP_ORDER="preflight clone venv compile patch deps smoke wrapper register"

# Step bookkeeping lives OUTSIDE the repo dir ($ALGS_ROOT/.setup_state) so a
# fresh install never mistakes it for repo content and git clone gets a clean
# destination.
STATE_DIR="$ALGS_ROOT/.setup_state/$NAME"
STEPS_FILE="$STATE_DIR/steps.json"
DEPS_FILE="$STATE_DIR/pip_deps.txt"
SMOKE_LOG="$STATE_DIR/smoke.log"
VENV_DIR="$VENVS_ROOT/$NAME"
VENV_PY="$VENV_DIR/bin/python"
WRAPPER_PATH="$BIN_DIR/py-$NAME"

mkdir -p "$ALGS_ROOT" "$VENVS_ROOT" "$BIN_DIR" "$STATE_DIR" "$JOB_DIR" "$OUTPUT_DIR"
echo "$$" > "$PID_FILE"

cat > "$JOB_DIR/algs_patch_rules.json" <<'WGSC_JSON_EOF'
__PATCH_RULES_JSON__
WGSC_JSON_EOF
cat > "$JOB_DIR/algs_fix_signatures.json" <<'WGSC_JSON_EOF'
__FIX_SIGNATURES_JSON__
WGSC_JSON_EOF
cat > "$JOB_DIR/wgsc_patcher.py" <<'WGSC_PY_EOF'
__PATCHER_PY__
WGSC_PY_EOF
cat > "$JOB_DIR/wgsc_selfheal.py" <<'WGSC_PY_EOF'
__SELFHEAL_PY__
WGSC_PY_EOF
cat > "$JOB_DIR/wgsc_setupctl.py" <<'WGSC_PY_EOF'
__SETUPCTL_PY__
WGSC_PY_EOF
cat > "$DEPS_FILE" <<'WGSC_DEPS_EOF'
__PIP_DEPS_LINES__
WGSC_DEPS_EOF

write_status() {
  local status="$1" stage="$2" rc="${3:-}" message="${4:-}"
  WGSC_STATUS="$status" WGSC_STAGE="$stage" WGSC_RETURN_CODE="$rc" WGSC_MESSAGE="$message" \\
  WGSC_JOB_ID="$JOB_ID" WGSC_FAMILY="$FAMILY" WGSC_PID="$$" WGSC_LOG_PATH="$LOG_FILE" \\
  WGSC_OUTPUT_DIR="$OUTPUT_DIR" WGSC_STEPS_FILE="$STEPS_FILE" WGSC_STEP_ORDER="$STEP_ORDER" \\
  "$PYTHON_BIN" "$JOB_DIR/wgsc_setupctl.py" write-status "$STATUS_FILE"
}

set_step() {
  "$PYTHON_BIN" "$JOB_DIR/wgsc_setupctl.py" set-step "$STEPS_FILE" "$1" "$2" "$3" "$STATE_DIR"
}

step_done() { [ -f "$STATE_DIR/step_$1.done" ]; }

finish_with() {
  local status="$1" stage="$2" rc="$3" message="${4:-}"
  echo "$rc" > "$EXIT_CODE_FILE"
  write_status "$status" "$stage" "$rc" "$message"
  exit "$rc"
}

echo "[algs-setup] install $FAMILY started at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
write_status "running" "env_setup:starting" "" "Environment setup for $FAMILY is running. It is safe to close the page."

# ---------- preflight ----------
if step_done preflight; then
  echo "[algs-setup] preflight already done, skip"
else
  set_step preflight running "checking disk space and tools"
  if ! command -v git >/dev/null 2>&1; then
    set_step preflight failed "git not found"
    finish_with "failed" "env_setup:preflight" 3 "git is not installed on the training server."
  fi
  AVAIL_KB=$(df -Pk "$ALGS_ROOT" 2>/dev/null | awk 'NR==2 {print $4}')
  MIN_KB=$((MIN_FREE_GB * 1024 * 1024))
  if ! echo "$AVAIL_KB" | grep -Eq '^[0-9]+$' || [ "$AVAIL_KB" -lt "$MIN_KB" ]; then
    set_step preflight failed "free=${AVAIL_KB:-unknown}KB required=${MIN_KB}KB"
    finish_with "failed" "env_setup:preflight" 4 "Not enough disk space under $ALGS_ROOT (${AVAIL_KB:-unknown} KB free, need >= ${MIN_FREE_GB} GB). Clean up space and retry."
  fi
  set_step preflight success "git ok, ${AVAIL_KB} KB free"
fi

# ---------- clone ----------
if [ -d "$REPO_DIR" ] && [ -n "$(ls -A "$REPO_DIR" 2>/dev/null)" ]; then
  echo "[algs-setup] repo exists at $REPO_DIR, skip clone"
  set_step clone success "repo already present at $REPO_DIR"
elif step_done clone; then
  echo "[algs-setup] clone already done, skip"
else
  set_step clone running "git clone --depth 1 (timeout ${CLONE_TIMEOUT}s)"
  if [ -z "$REPO_URL" ]; then
    set_step clone failed "no repo_url and repo dir missing"
    finish_with "failed" "env_setup:clone" 5 "Repository directory $REPO_DIR does not exist and no repo_url was provided."
  fi
  CLONE_CMD=""
  if command -v timeout >/dev/null 2>&1; then CLONE_CMD="timeout $CLONE_TIMEOUT"; fi
  $CLONE_CMD git clone --depth 1 --recurse-submodules --shallow-submodules "$REPO_URL" "$REPO_DIR"
  clone_rc=$?
  if [ "$clone_rc" -ne 0 ]; then
    rm -rf "$REPO_DIR"
    set_step clone failed "git clone exited $clone_rc"
    finish_with "failed" "env_setup:clone" "$clone_rc" "git clone failed for $REPO_URL (exit $clone_rc). Check the URL and network, then retry."
  fi
  set_step clone success "cloned from $REPO_URL"
fi

# ---------- venv ----------
if [ -x "$VENV_PY" ]; then
  echo "[algs-setup] venv exists at $VENV_DIR, skip"
  set_step venv success "venv already present"
elif step_done venv; then
  echo "[algs-setup] venv already done, skip"
else
  set_step venv running "python -m venv --system-site-packages (SHARC torch visible)"
  "$PYTHON_BIN" -m venv --system-site-packages "$VENV_DIR"
  venv_rc=$?
  if [ "$venv_rc" -ne 0 ] || [ ! -x "$VENV_PY" ]; then
    rm -rf "$VENV_DIR"
    set_step venv failed "venv creation exited $venv_rc"
    finish_with "failed" "env_setup:venv" 6 "Failed to create venv at $VENV_DIR with $PYTHON_BIN (exit $venv_rc)."
  fi
  set_step venv success "$VENV_DIR"
fi

# ---------- compile ----------
if step_done compile; then
  echo "[algs-setup] compile already done, skip"
else
  set_step compile running "scanning submodules"
  CC_CAP=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader,nounits 2>/dev/null | head -n 1 | tr -d ' ')
  if [ -n "$CC_CAP" ]; then
    export TORCH_CUDA_ARCH_LIST="$CC_CAP"
    echo "[algs-setup] TORCH_CUDA_ARCH_LIST=$TORCH_CUDA_ARCH_LIST"
  fi
  COMPILE_FAILED=""
  for SUB_DIR in "$REPO_DIR"/submodules/*/; do
    [ -d "$SUB_DIR" ] || continue
    [ -f "$SUB_DIR/setup.py" ] || [ -f "$SUB_DIR/pyproject.toml" ] || continue
    SUB_NAME=$(basename "$SUB_DIR")
    echo "[algs-setup] compiling submodule $SUB_NAME"
    "$VENV_PY" -m pip install --no-build-isolation "$SUB_DIR"
    sub_rc=$?
    if [ "$sub_rc" -ne 0 ]; then
      echo "[algs-setup] compile failed for $SUB_NAME, applying patch rules then retrying once"
      "$VENV_PY" "$JOB_DIR/wgsc_patcher.py" --repo "$REPO_DIR" --rules "$JOB_DIR/algs_patch_rules.json" --proactive-only
      "$VENV_PY" -m pip install --no-build-isolation "$SUB_DIR"
      sub_rc=$?
    fi
    if [ "$sub_rc" -ne 0 ]; then
      COMPILE_FAILED="$SUB_NAME"
      break
    fi
  done
  if [ -n "$COMPILE_FAILED" ]; then
    set_step compile failed "submodule $COMPILE_FAILED"
    finish_with "failed" "env_setup:compile" 7 "Failed to compile submodule $COMPILE_FAILED (see log tail)."
  fi
  set_step compile success "submodules compiled"
fi

# ---------- patch ----------
if step_done patch; then
  echo "[algs-setup] patch already done, skip"
else
  set_step patch running "applying known-pitfall patch rules"
  "$VENV_PY" "$JOB_DIR/wgsc_patcher.py" --repo "$REPO_DIR" --rules "$JOB_DIR/algs_patch_rules.json" --proactive-only
  patch_rc=$?
  if [ "$patch_rc" -ne 0 ]; then
    set_step patch failed "patcher exited $patch_rc"
    finish_with "failed" "env_setup:patch" 8 "Patch rule engine failed (exit $patch_rc); check algs_patch_rules.json."
  fi
  set_step patch success "rules applied"
fi

# ---------- deps ----------
if step_done deps; then
  echo "[algs-setup] deps already done, skip"
else
  set_step deps running "checking python dependencies"
  DEP_FAILED=""
  for MOD in $(cat "$DEPS_FILE"); do
    IMPORT_NAME=$(echo "$MOD" | tr '-' '_')
    if "$VENV_PY" -c "import $IMPORT_NAME" >/dev/null 2>&1; then
      echo "[algs-setup] $MOD: already importable"
      continue
    fi
    echo "[algs-setup] $MOD: missing, resolving install spec"
    SPEC=$("$PYTHON_BIN" "$JOB_DIR/wgsc_selfheal.py" resolve-package "$MOD" "$JOB_DIR/algs_fix_signatures.json")
    SPEC_KIND="${SPEC%%:*}"
    SPEC_TARGET="${SPEC#*:}"
    if [ "$SPEC_KIND" = "git" ]; then
      echo "[algs-setup] installing git+$SPEC_TARGET"
      "$VENV_PY" -m pip install --no-build-isolation "git+$SPEC_TARGET"
    else
      echo "[algs-setup] installing $SPEC_TARGET"
      "$VENV_PY" -m pip install "$SPEC_TARGET"
    fi
    if [ $? -ne 0 ]; then
      DEP_FAILED="$MOD"
      break
    fi
  done
  if [ -n "$DEP_FAILED" ]; then
    set_step deps failed "module $DEP_FAILED"
    finish_with "failed" "env_setup:deps" 9 "pip install failed for module $DEP_FAILED (see log tail)."
  fi
  set_step deps success "dependencies ready"
fi

# ---------- smoke ----------
if step_done smoke; then
  echo "[algs-setup] smoke already done, skip"
else
  ENTRY_PATH="$REPO_DIR/$ENTRY"
  if [ ! -f "$ENTRY_PATH" ]; then
    set_step smoke failed "entry $ENTRY not found"
    finish_with "failed" "env_setup:smoke" 10 "Entry file $ENTRY not found under $REPO_DIR."
  fi
  smoke_rc=1
  for ROUND in $(seq 1 "$SMOKE_ROUNDS"); do
    set_step smoke running "round $ROUND/$SMOKE_ROUNDS: $ENTRY --help"
    ( cd "$REPO_DIR" && "$VENV_PY" "$ENTRY_PATH" --help ) > "$SMOKE_LOG" 2>&1
    smoke_rc=$?
    if [ "$smoke_rc" -eq 0 ]; then
      break
    fi
    echo "[algs-setup] smoke round $ROUND failed (exit $smoke_rc); log tail:"
    tail -n 30 "$SMOKE_LOG"
    echo "[algs-setup] running self-heal signatures"
    "$PYTHON_BIN" "$JOB_DIR/wgsc_selfheal.py" heal --log "$SMOKE_LOG" --signatures "$JOB_DIR/algs_fix_signatures.json" --rules "$JOB_DIR/algs_patch_rules.json" --repo "$REPO_DIR" --venv-py "$VENV_PY"
    heal_rc=$?
    if [ "$heal_rc" -ne 0 ]; then
      echo "[algs-setup] no automatic fix applicable (heal exit $heal_rc)"
      break
    fi
    echo "[algs-setup] fix applied, retrying smoke"
  done
  if [ "$smoke_rc" -ne 0 ]; then
    LAST_ERR=$(tail -n 5 "$SMOKE_LOG" | grep -v '^$' | tail -n 2 | tr '\\n' ' ' | cut -c1-240)
    set_step smoke failed "exit $smoke_rc after $SMOKE_ROUNDS round(s)"
    finish_with "failed" "env_setup:smoke" "$smoke_rc" "Smoke test failed: $ENTRY --help exited $smoke_rc. ${LAST_ERR}"
  fi
  set_step smoke success "entry --help ok"
fi

# ---------- wrapper ----------
if step_done wrapper; then
  echo "[algs-setup] wrapper already done, skip"
else
  set_step wrapper running "writing $WRAPPER_PATH"
  cat > "$WRAPPER_PATH" <<'WGSC_WRAPPER_EOF'
__WRAPPER_SCRIPT__
WGSC_WRAPPER_EOF
  chmod +x "$WRAPPER_PATH"
  set_step wrapper success "$WRAPPER_PATH"
fi

# ---------- register ----------
if step_done register; then
  echo "[algs-setup] register already done, skip"
else
  set_step register running "updating $REGISTRY_PATH"
  "$PYTHON_BIN" "$JOB_DIR/wgsc_setupctl.py" register "$REGISTRY_PATH" "$NAME" "$FAMILY" "$REPO_DIR" "$VENV_DIR" "$WRAPPER_PATH" "$ENTRY" "$VENV_PY"
  reg_rc=$?
  if [ "$reg_rc" -ne 0 ]; then
    set_step register failed "registry update exited $reg_rc"
    finish_with "failed" "env_setup:register" 11 "Failed to update the install registry at $REGISTRY_PATH (exit $reg_rc)."
  fi
  set_step register success "registry updated"
fi

finish_with "completed" "env_setup:ready" 0 "Algorithm $FAMILY is ready (entry=$ENTRY, venv=$VENV_DIR, wrapper=$WRAPPER_PATH)."
"""


def generate_setup_script(
  *,
  name: str,
  family: str,
  repo_url: str,
  entry: str,
  base_python: str,
  layout: Dict[str, str],
  job_paths: Dict[str, str],
  job_id: str,
  pip_modules: List[str] | None = None,
  min_free_gb: int = MIN_FREE_DISK_GB,
) -> str:
  """Render the remote algs-setup bash script (token substitution only)."""
  slug = safe_setup_name(name)
  venv_dir = str(PurePosixPath(layout["venvs_root"]) / slug)
  venv_python = str(PurePosixPath(venv_dir, "bin", "python"))
  modules = [module_import_name(m) for m in (pip_modules or []) if str(m).strip()]
  deps_lines = "\n".join(dict.fromkeys(modules))

  tokens = {
    "__PYTHON_BIN__": shlex.quote(str(base_python or "python3")),
    "__NAME__": shlex.quote(slug),
    "__FAMILY__": shlex.quote(str(family or slug)),
    "__REPO_URL__": shlex.quote(str(repo_url or "")),
    "__REPO_DIR__": shlex.quote(str(PurePosixPath(layout["algs_root"]) / slug)),
    "__ENTRY__": shlex.quote(str(entry or DEFAULT_ENTRY)),
    "__ALGS_ROOT__": shlex.quote(layout["algs_root"]),
    "__VENVS_ROOT__": shlex.quote(layout["venvs_root"]),
    "__BIN_DIR__": shlex.quote(layout["bin_dir"]),
    "__REGISTRY_PATH__": shlex.quote(layout["registry_path"]),
    "__MIN_FREE_GB__": str(int(min_free_gb)),
    "__JOB_ID__": shlex.quote(str(job_id)),
    "__JOB_DIR__": shlex.quote(job_paths["job_dir"]),
    "__STATUS_FILE__": shlex.quote(job_paths["status_file"]),
    "__EXIT_CODE_FILE__": shlex.quote(job_paths["exit_code_file"]),
    "__LOG_FILE__": shlex.quote(job_paths["runtime_log"]),
    "__PID_FILE__": shlex.quote(job_paths["pid_file"]),
    "__OUTPUT_DIR__": shlex.quote(str(job_paths.get("remote_output_dir") or job_paths["job_dir"])),
    "__CLONE_TIMEOUT__": str(CLONE_TIMEOUT_SECONDS),
    "__SMOKE_ROUNDS__": str(SMOKE_MAX_ROUNDS),
    "__PIP_DEPS_LINES__": deps_lines,
    "__PATCH_RULES_JSON__": json.dumps(_load_json_config(PATCH_RULES_PATH), ensure_ascii=False, indent=2),
    "__FIX_SIGNATURES_JSON__": json.dumps(_load_json_config(FIX_SIGNATURES_PATH), ensure_ascii=False, indent=2),
    "__PATCHER_PY__": _REMOTE_PATCHER_PY.rstrip("\n"),
    "__SELFHEAL_PY__": _REMOTE_SELFHEAL_PY.rstrip("\n"),
    "__SETUPCTL_PY__": _REMOTE_SETUPCTL_PY.rstrip("\n"),
    "__WRAPPER_SCRIPT__": generate_wrapper_script(venv_python).rstrip("\n"),
  }
  script = _SETUP_SCRIPT_TEMPLATE
  for token, value in tokens.items():
    script = script.replace(token, value)
  return script
