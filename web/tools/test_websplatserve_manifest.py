"""Tests for WebSplatServe export manifest metadata."""
from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from web.serving.manifest import normalize_manifest  # noqa: E402
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


def test_content_hashes_match_file_bytes() -> None:
  # The cacheKey narrative only holds if the stored hash really is the hash of
  # the served bytes.
  with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    ply = root / "scene.ply"
    out = root / "assets"
    write_test_ply(ply, 64)
    manifest = export_websplatserve_assets(ply, out)
    for chunk in manifest["chunks"]:
      rows_digest = hashlib.sha256((out / chunk["url"]).read_bytes()).hexdigest()
      assert chunk["contentHash"] == rows_digest
      if chunk.get("shUrl"):
        sh_digest = hashlib.sha256((out / chunk["shUrl"]).read_bytes()).hexdigest()
        assert chunk["shContentHash"] == sh_digest


def test_duplicate_chunk_ids_are_rejected() -> None:
  manifest = {
    "chunks": [
      {"id": "base", "url": "base.bin", "rows": 10, "bytes": 320},
      {"id": "base", "url": "base2.bin", "rows": 10, "bytes": 320},
    ]
  }
  try:
    normalize_manifest(manifest)
    raise AssertionError("duplicate chunk ids must be rejected")
  except ValueError as exc:
    assert "unique" in str(exc)


def main() -> None:
  test_export_adds_cache_and_backend_metadata()
  test_content_hashes_match_file_bytes()
  test_duplicate_chunk_ids_are_rejected()
  print("websplatserve manifest tests passed")


if __name__ == "__main__":
  main()


