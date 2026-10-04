"""Tests for the remote data-disk probe parser (df -P + /proc/mounts)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from web.server.remote_executor import parse_disk_report  # noqa: E402


BASIC_RAW = """Filesystem     1024-blocks       Used   Available Capacity Mounted on
/dev/vda1         41152812   12345678    28807134      31% /
tmpfs              8388608          0     8388608       0% /dev/shm
tmpfs              1048576     524288      524288      50% /tmp
/dev/vdb1       3516093644  123456789  3392636855       4% /root/autodl-tmp
nas-server:/vol  4398046511          5  4398046506       1% /mnt/nfs
--- websplatserve-fstab ---
/dev/vda1 / ext4 rw,relatime 0 0
tmpfs /dev/shm tmpfs rw 0 0
tmpfs /tmp tmpfs rw 0 0
/dev/vdb1 /root/autodl-tmp ext4 rw,relatime 0 0
nas-server:/vol /mnt/nfs nfs4 rw 0 0
"""


def test_basic_ranking_and_suggestion() -> None:
  report = parse_disk_report(BASIC_RAW)
  mounts = [item["mount"] for item in report["candidates"]]
  # tmpfs (RAM-backed) is never a candidate, even under the data-disk name /tmp.
  assert "/dev/shm" not in mounts and "/tmp" not in mounts
  assert mounts == ["/mnt/nfs", "/root/autodl-tmp", "/"]
  top = report["candidates"][0]
  assert top["network"] is True and top["fstype"] == "nfs4"
  # The suggestion must prefer the biggest LOCAL disk over the bigger NFS mount.
  assert report["suggested_data_root"] == "/root/autodl-tmp"
  assert report["suggested_workspace_root"] == "/root/autodl-tmp/websplatserve/workspaces"
  assert report["suggested_output_root"] == "/root/autodl-tmp/websplatserve/outputs"


def test_missing_proc_mounts_falls_back_to_device_names() -> None:
  raw = """Filesystem 1024-blocks Used Available Capacity Mounted on
tmpfs 8388608 0 8388608 0% /dev/shm
/dev/sda1 1000000 100000 900000 10% /data
"""
  report = parse_disk_report(raw)
  mounts = [item["mount"] for item in report["candidates"]]
  assert mounts == ["/data"]  # tmpfs device name filtered without fstype info
  assert report["suggested_data_root"] == "/data"


def test_escaped_mount_paths_are_unescaped() -> None:
  raw = """Filesystem 1024-blocks Used Available Capacity Mounted on
/dev/vdc1 2000000 100000 1900000 5% /mnt/data\\0402
--- websplatserve-fstab ---
/dev/vdc1 /mnt/data\\0402 ext4 rw 0 0
"""
  report = parse_disk_report(raw)
  assert report["candidates"][0]["mount"] == "/mnt/data 2"
  assert report["suggested_workspace_root"] == "/mnt/data 2/websplatserve/workspaces"


def test_network_only_still_suggests() -> None:
  raw = """Filesystem 1024-blocks Used Available Capacity Mounted on
nas:/vol 4398046511 5 4398046506 1% /mnt/nfs
--- websplatserve-fstab ---
nas:/vol /mnt/nfs nfs4 rw 0 0
"""
  report = parse_disk_report(raw)
  assert report["suggested_data_root"] == "/mnt/nfs"
  assert report["candidates"][0]["network"] is True


def test_empty_output_is_safe() -> None:
  report = parse_disk_report("")
  assert report["candidates"] == []
  assert report["suggested_data_root"] == ""
  assert report["suggested_workspace_root"] == ""


def main() -> None:
  test_basic_ranking_and_suggestion()
  test_missing_proc_mounts_falls_back_to_device_names()
  test_escaped_mount_paths_are_unescaped()
  test_network_only_still_suggests()
  test_empty_output_is_safe()
  print("remote disk probe tests passed")


if __name__ == "__main__":
  main()
