import threading

from ankigen import shortcuts


class FakeWindow:
    def __init__(self):
        self.scripts = []
        self.done = threading.Event()

    def evaluate_js(self, script):
        self.scripts.append(script)
        self.done.set()


def test_ctrl_f_and_f3_are_forwarded_to_the_page():
    w = FakeWindow()
    assert shortcuts.handle_key(w, ctrl=True, shift=False, key="F")
    assert w.done.wait(2)
    assert w.scripts == [shortcuts.find_script()]
    assert "ankigen:find" in w.scripts[0] and '"step": false' in w.scripts[0]
    assert '"shift": true, "step": true' in shortcuts.find_script(shift=True, step=True)
    assert shortcuts.handle_key(w, ctrl=False, shift=True, key="F3")


def test_other_keys_are_left_alone():
    w = FakeWindow()
    assert not shortcuts.handle_key(w, ctrl=False, shift=False, key="F")
    assert not shortcuts.handle_key(w, ctrl=True, shift=False, key="S")
    assert not shortcuts.handle_key(w, ctrl=True, shift=True, key="F")


def test_install_never_raises(monkeypatch):
    monkeypatch.setattr(shortcuts.sys, "platform", "win32")
    assert shortcuts.install(object()) is False  # no native control

    class Control:
        def __init__(self):
            self.handlers = []

        @property
        def KeyDown(self):
            return self

        @KeyDown.setter
        def KeyDown(self, value):
            pass

        def __iadd__(self, handler):
            self.handlers.append(handler)
            return self

    control = Control()

    class Native:
        class browser:
            webview = control

    w = FakeWindow()
    w.native = Native
    assert shortcuts.install(w) is True

    class Args:
        Control, Shift, KeyCode, Handled = True, False, "F", False

    args = Args()
    control.handlers[0](None, args)
    assert args.Handled is True and w.done.wait(2)
    monkeypatch.setattr(shortcuts.sys, "platform", "linux")
    assert shortcuts.install(w) is False
