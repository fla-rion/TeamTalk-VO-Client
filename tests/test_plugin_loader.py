"""Tests für PluginLoader (v4.1.0)."""
import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from pathlib import Path
from event_bus import EventBus
from plugin_loader import PluginLoader


def _loader(plugins_dir: Path) -> PluginLoader:
    return PluginLoader(EventBus(), plugins_dir)


def test_empty_dir():
    with tempfile.TemporaryDirectory() as d:
        loader = _loader(Path(d))
        assert loader.load_all() == 0


def test_nonexistent_dir():
    loader = _loader(Path("/nonexistent_plugins_xyz"))
    assert loader.load_all() == 0


def test_loads_valid_plugin():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "myplugin.py"
        p.write_text(
            "metadata = {'name': 'Test', 'version': '1.0'}\n"
            "def register(bus, api=None): pass\n"
        )
        loader = _loader(Path(d))
        count = loader.load_all()
        assert count == 1
        assert "myplugin.py" in loader.loaded_plugins
        assert loader.get_metadata("myplugin.py")["name"] == "Test"


def test_broken_plugin_isolated():
    with tempfile.TemporaryDirectory() as d:
        bad = Path(d) / "bad.py"
        bad.write_text("raise RuntimeError('broken')\n")
        good = Path(d) / "good.py"
        good.write_text("def register(bus): pass\n")
        loader = _loader(Path(d))
        count = loader.load_all()
        assert count == 1  # nur good geladen
        assert loader.has_error("bad.py")
        assert "broken" in loader.get_errors()["bad.py"]
        assert "good.py" in loader.loaded_plugins


def test_disabled_plugin_skipped():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "skip.py"
        p.write_text("def register(bus): pass\n")
        loader = _loader(Path(d))
        count = loader.load_all(disabled=["skip.py"])
        assert count == 0
        assert "skip.py" not in loader.loaded_plugins


def test_underscore_plugins_ignored():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "_internal.py").write_text("def register(bus): pass\n")
        loader = _loader(Path(d))
        assert loader.load_all() == 0


def test_all_metadata():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "meta.py"
        p.write_text(
            "metadata = {'name': 'M', 'author': 'A', 'version': '2', 'description': 'D'}\n"
            "def register(bus): pass\n"
        )
        loader = _loader(Path(d))
        loader.load_all()
        all_m = loader.all_metadata()
        assert "meta.py" in all_m
        assert all_m["meta.py"]["author"] == "A"
