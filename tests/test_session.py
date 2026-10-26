import json

from ankigen import __version__
from ankigen.api import KEEP_BACKUPS, Api


def test_save_stamps_version_and_load_strips_it(tmp_path):
    api = Api(data_dir=tmp_path)
    api.save_session({"decks": [1]})
    assert json.loads((tmp_path / "session.json").read_text("utf-8"))["savedBy"] == __version__
    res = api.load_session()
    assert res["session"] == {"decks": [1]} and res["notice"] is None


def test_unreadable_session_is_kept_not_overwritten(tmp_path):
    (tmp_path / "session.json").write_text('{"decks": [1', "utf-8")
    api = Api(data_dir=tmp_path)
    res = api.load_session()
    assert res["ok"] and res["session"] is None and "couldn't be read" in res["notice"]
    kept = list(tmp_path.glob("session-unreadable-*.json"))
    assert len(kept) == 1 and kept[0].read_text("utf-8") == '{"decks": [1'
    api.save_session({"decks": []})  # the next autosave can't touch the old file
    assert kept[0].read_text("utf-8") == '{"decks": [1'


def test_backups_skip_duplicates_and_rotate(tmp_path):
    api = Api(data_dir=tmp_path)
    api.save_session({"n": 0})
    api.load_session()
    api.load_session()
    assert len(list((tmp_path / "backups").glob("session-*.json"))) == 1
    for n in range(1, KEEP_BACKUPS + 5):
        api.save_session({"n": n})
        api.load_session()
    backups = sorted((tmp_path / "backups").glob("session-*.json"))
    assert len(backups) == KEEP_BACKUPS
    assert json.loads(backups[-1].read_text("utf-8"))["n"] == KEEP_BACKUPS + 4


def test_newer_version_warns(tmp_path):
    (tmp_path / "session.json").write_text(json.dumps({"decks": [], "savedBy": "99.0.0"}), "utf-8")
    res = Api(data_dir=tmp_path).load_session()
    assert res["session"] == {"decks": []} and "newer version (99.0.0)" in res["notice"]
