"""Tests for the GPU reset helpers (nvidia-smi output parsing)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from web.server.remote_executor import parse_gpu_compute_apps, parse_gpu_state  # noqa: E402


def test_parse_gpu_compute_apps() -> None:
    text = "\n".join([
        "3939970, 6550",
        "3944965, 5916",
        "2905716, 38386",
        "",  # blank line
        "[Not supported]",  # driver without per-process memory: non-numeric pid column
        "not-a-pid, 123",
    ])
    apps = parse_gpu_compute_apps(text)
    assert [app["pid"] for app in apps] == [3939970, 3944965, 2905716]
    assert apps[0]["memory_mib"] == 6550
    assert apps[2]["memory_mib"] == 38386

    # missing / unsupported memory column must stay None, not crash
    assert parse_gpu_compute_apps("123, [Not Supported]")[0]["memory_mib"] is None
    assert parse_gpu_compute_apps("") == []


def test_parse_gpu_state() -> None:
    text = "\n".join([
        "0, 13355, 100",
        "1, 0, 0",
        "7, 37319, [N/A]",  # utilization unsupported on some drivers
    ])
    states = parse_gpu_state(text)
    assert [s["index"] for s in states] == [0, 1, 7]
    assert states[0]["memory_used_mib"] == 13355 and states[0]["utilization_percent"] == 100
    assert states[1]["memory_used_mib"] == 0 and states[1]["utilization_percent"] == 0
    assert states[2]["memory_used_mib"] == 37319 and states[2]["utilization_percent"] is None
    assert parse_gpu_state("") == []


def main() -> None:
    test_parse_gpu_compute_apps()
    test_parse_gpu_state()
    print("remote gpu reset tests passed")


if __name__ == "__main__":
    main()
