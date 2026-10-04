"""Read host definitions from the local OpenSSH client config.

The console's remote-server form can import entries directly from
``~/.ssh/config`` instead of re-typing host/port/user/key paths.  This module
only ever returns configuration *metadata* (aliases, addresses, key paths) —
never key contents or passwords.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import Any

DEFAULT_SSH_CONFIG = Path.home() / ".ssh" / "config"
_MAX_INCLUDE_FILES = 64
_MAX_CONFIG_BYTES = 1_000_000


def _split_tokens(line: str) -> list[str]:
  # ssh accepts "key value" and "key=value"; values may be quoted.
  if "=" in line.split()[0]:
    key, _, rest = line.partition("=")
    return [key.strip(), *rest.split()]
  return line.split()


def _strip_quotes(value: str) -> str:
  if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
    return value[1:-1]
  return value


def _resolve_include(pattern: str, including_file: Path) -> list[Path]:
  pattern = os.path.expanduser(pattern.strip())
  if not os.path.isabs(pattern):
    # Relative include paths resolve against ~/.ssh (OpenSSH semantics).
    pattern = str(Path.home() / ".ssh" / pattern)
  matches = [Path(p) for p in sorted(glob.glob(pattern))]
  return [p for p in matches if p.is_file()]


def _empty_host_entry(alias: str) -> dict[str, Any]:
  return {"alias": alias, "hostname": "", "port": None, "user": "", "identity_file": ""}


def parse_ssh_config_text(text: str) -> dict[str, dict[str, Any]]:
  """Parse ssh config content into {alias: entry}, first-value-wins per alias."""
  hosts: dict[str, dict[str, Any]] = {}
  current_aliases: list[str] = []
  in_match_block = False

  for raw_line in text.splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#"):
      continue
    tokens = _split_tokens(line)
    if not tokens:
      continue
    key = tokens[0].lower()

    if key == "host":
      in_match_block = False
      current_aliases = []
      for alias in tokens[1:]:
        if "*" in alias or "?" in alias or "!" in alias:
          continue  # patterns/negations are not importable concrete hosts
        alias = _strip_quotes(alias)
        if alias and alias not in hosts:
          hosts[alias] = _empty_host_entry(alias)
        if alias:
          current_aliases.append(alias)
      continue

    if key == "match":
      # Conditional options are skipped: they may not apply to a plain import.
      in_match_block = True
      current_aliases = []
      continue
    if in_match_block or not current_aliases:
      continue

    value = _strip_quotes(tokens[1]) if len(tokens) > 1 else ""
    for alias in current_aliases:
      entry = hosts[alias]
      if key == "hostname":
        if not entry["hostname"]:
          entry["hostname"] = value
      elif key == "port":
        if entry["port"] is None:
          try:
            entry["port"] = int(value)
          except ValueError:
            pass
      elif key == "user":
        if not entry["user"]:
          entry["user"] = value
      elif key == "identityfile":
        if not entry["identity_file"]:
          entry["identity_file"] = os.path.expanduser(value)
  return hosts


def list_ssh_config_hosts(config_path: str | Path | None = None) -> dict[str, Any]:
  """List importable hosts from the ssh client config (follows Include)."""
  start = Path(config_path) if config_path else DEFAULT_SSH_CONFIG
  hosts: dict[str, dict[str, Any]] = {}
  visited: set[Path] = set()
  queue = [start]
  while queue and len(visited) < _MAX_INCLUDE_FILES:
    path = queue.pop(0)
    try:
      path = path.resolve()
      if path in visited:
        continue
      visited.add(path)
      text = path.read_text(encoding="utf-8", errors="replace")[:_MAX_CONFIG_BYTES]
    except (OSError, ValueError):
      continue

    for raw_line in text.splitlines():
      stripped = raw_line.strip()
      if stripped.startswith("#") or not stripped:
        continue
      tokens = _split_tokens(stripped)
      if tokens and tokens[0].lower() == "include":
        for inc in tokens[1:]:
          queue.extend(_resolve_include(inc, path))

    for alias, entry in parse_ssh_config_text(text).items():
      hosts.setdefault(alias, entry)

  ordered = [
    hosts[alias]
    for alias in sorted(hosts)
    if hosts[alias]["hostname"] or hosts[alias]["user"] or hosts[alias]["port"] or hosts[alias]["identity_file"]
  ]
  # An alias with no HostName is still usable (ssh resolves the alias via DNS),
  # but only when it carries at least one other useful field.
  for entry in ordered:
    if not entry["hostname"]:
      entry["hostname"] = entry["alias"]
  return {"source": str(start), "hosts": ordered}
