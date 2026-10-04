"""Backend profile registry for WebSplatServe exports."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
PROFILE_FILE = ROOT_DIR / "web" / "config" / "backend_profiles.json"


def load_backend_profiles(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
  source = Path(path) if path else PROFILE_FILE
  with open(source, "r", encoding="utf-8") as handle:
    payload = json.load(handle)
  profiles = {}
  for profile in payload.get("profiles", []):
    if isinstance(profile, dict) and profile.get("id"):
      profiles[str(profile["id"])] = dict(profile)
  return profiles


def get_backend_profile(profile_id: str, path: str | Path | None = None) -> dict[str, Any]:
  profiles = load_backend_profiles(path)
  if profile_id not in profiles:
    known = ", ".join(sorted(profiles)) or "(none)"
    raise ValueError(f"unknown backend profile: {profile_id}. Known profiles: {known}")
  return profiles[profile_id]

