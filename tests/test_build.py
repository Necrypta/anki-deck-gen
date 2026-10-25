import importlib.util
from pathlib import Path

import ankigen
from ankigen import _build
from ankigen.api import Api, app_data_dir

ROOT = Path(__file__).resolve().parent.parent


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_dev_build_is_not_release(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(_build, "BUILD", "PR #4 · a1b2c3d")
    assert not ankigen.is_release()
    assert app_data_dir() == tmp_path / "AnkiDeckGenerator-test"


def test_release_build_uses_real_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(_build, "BUILD", f"v{ankigen.__version__}")
    assert ankigen.is_release()
    assert app_data_dir() == tmp_path / "AnkiDeckGenerator"


def test_info_reports_build(monkeypatch, tmp_path):
    monkeypatch.setattr(_build, "BUILD", "main · deadbee")
    info = Api(data_dir=tmp_path).info()
    assert info["build"] == "main · deadbee"
    assert info["release"] is False
    assert info["data_dir"] == str(tmp_path)


def test_versions_in_sync():
    stamp = _load_script("stamp_build")
    assert stamp.project_version() == stamp.package_version() == ankigen.__version__


def test_changelog_section():
    cl = _load_script("changelog_section")
    text = "# Changelog\n\n## [Unreleased]\n\n- new\n\n## [0.2.0]\n\n- two\n\n## [0.1.0]\n\n- one\n"
    assert cl.section("0.2.0", text) == "- two"
    assert cl.section("0.1.0", text) == "- one"
    assert cl.section("0.3.0", text) == "- new"
