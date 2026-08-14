"""Tests for the software status panel data."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from host_config.detect import detect_running_software  # noqa: E402


def test_running_software_returns_all_kinds_as_bool():
    result = detect_running_software()
    assert set(result) == {"blender", "sketchup", "rhino", "autocad"}
    assert all(isinstance(value, bool) for value in result.values())


def test_running_software_filters_kinds():
    result = detect_running_software(["rhino"])
    assert set(result) == {"rhino"}
