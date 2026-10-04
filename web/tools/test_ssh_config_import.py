"""Tests for ~/.ssh/config import used by the console's host importer."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from web.server.ssh_config_import import list_ssh_config_hosts, parse_ssh_config_text  # noqa: E402


def test_basic_fields_and_alias_fallback() -> None:
  hosts = parse_ssh_config_text("""
Host gpu-box
    HostName 36.138.63.143
    Port 65022
    User root
    IdentityFile ~/.ssh/id_ed25519
""")
  assert hosts["gpu-box"] == {
    "alias": "gpu-box",
    "hostname": "36.138.63.143",
    "port": 65022,
    "user": "root",
    "identity_file": str(Path.home() / ".ssh" / "id_ed25519"),
  }


def test_first_obtained_value_wins() -> None:
  hosts = parse_ssh_config_text("""
Host a
    HostName first.example.com
    HostName second.example.com
    Port 2222
    Port 3333
""")
  assert hosts["a"]["hostname"] == "first.example.com"
  assert hosts["a"]["port"] == 2222


def test_wildcard_and_negation_patterns_are_skipped() -> None:
  hosts = parse_ssh_config_text("""
Host *
    Compression yes

Host *.example.com !skip.example.com
    User pool

Host real
    HostName real.example.com
""")
  assert set(hosts) == {"real"}
  # Options under a pattern-only Host line must not leak onto other aliases.
  assert hosts["real"]["user"] == ""


def test_multiple_aliases_share_settings_and_match_blocks_are_skipped() -> None:
  hosts = parse_ssh_config_text("""
Host web1 web2
    HostName shared.example.com
    User deploy

Match host web2
    Port 2222
""")
  assert hosts["web1"]["hostname"] == "shared.example.com"
  assert hosts["web2"]["hostname"] == "shared.example.com"
  assert hosts["web1"]["port"] is None
  assert hosts["web2"]["port"] is None  # Match-block options are conditional; skipped


def test_equals_syntax_and_case_insensitive_keys() -> None:
  hosts = parse_ssh_config_text("HOST=box\n    HOSTNAME=box.example.com\n    USER=ops\n")
  assert hosts["box"]["hostname"] == "box.example.com"
  assert hosts["box"]["user"] == "ops"


def test_list_follows_absolute_include_and_missing_file_is_empty() -> None:
  with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    included = root / "included.conf"
    included.write_text("Host inner\n    HostName 10.0.0.5\n", encoding="utf-8")
    main = root / "config"
    main.write_text(
      f"Include {included}\n"
      "Host outer\n    HostName 10.0.0.9\n    Port 2200\n",
      encoding="utf-8",
    )
    result = list_ssh_config_hosts(main)
    aliases = {entry["alias"] for entry in result["hosts"]}
    assert aliases == {"inner", "outer"}
    outer = next(entry for entry in result["hosts"] if entry["alias"] == "outer")
    assert outer["port"] == 2200

    assert list_ssh_config_hosts(root / "does-not-exist")["hosts"] == []


def main() -> None:
  test_basic_fields_and_alias_fallback()
  test_first_obtained_value_wins()
  test_wildcard_and_negation_patterns_are_skipped()
  test_multiple_aliases_share_settings_and_match_blocks_are_skipped()
  test_equals_syntax_and_case_insensitive_keys()
  test_list_follows_absolute_include_and_missing_file_is_empty()
  print("ssh config import tests passed")


if __name__ == "__main__":
  main()
