"""Tests for WebSplatServe export manifest metadata."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from web.tools.export_websplatserve_assets import export_websplatserve_assets  # noqa: E402
from web.tools.test_web_export import write_test_ply  # noqa: E402


def test_export_adds_cache_and_backend_metadata() -> None:
  with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    ply = root / "scene.ply"
    out = root / "assets"
    write_test_ply(ply, 96)
    manifest = export_websplatserve_assets(
      ply,
      out,
      backend_profile="compressed-decoded-sh",
    )
    assert manifest["backendProfile"]["id"] == "compressed-decoded-sh"
    assert (out / "websplatserve_manifest.json").is_file()
    for chunk in manifest["chunks"]:
      assert chunk["contentHash"]
      assert chunk["cacheKey"].startswith("sha256:")
      assert chunk["cacheControl"].startswith("public")
      if chunk.get("shUrl"):
        assert chunk["shContentHash"]


def main() -> None:
  test_export_adds_cache_and_backend_metadata()
  print("websplatserve manifest tests passed")


if __name__ == "__main__":
  main()

