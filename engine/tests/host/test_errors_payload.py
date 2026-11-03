import sys
import tokenize
import types
from pathlib import Path

import pytest
from core import _errors
from core._errors import build_error_payload, describe_error

HAS_COLUMNS = sys.version_info >= (3, 11)
HAS_SUGGESTIONS = sys.version_info >= (3, 12)
needs_columns = pytest.mark.skipif(not HAS_COLUMNS, reason="column info needs Python 3.11+")


def run(directory: Path, source: str | bytes, name: str = "main.py") -> dict:
    """Run ``source`` as the student's script and return the error payload it produces."""
    path = directory / name
    if isinstance(source, bytes):
        path.write_bytes(source)
    else:
        path.write_text(source, encoding="utf-8")
    try:
        with tokenize.open(path) as handle:
            source_text = handle.read()
        exec(compile(source_text, str(path), "exec"), {"__name__": "__main__"})
    except BaseException as exc:
        return build_error_payload(exc, directory)
    raise AssertionError("the script did not raise")


@pytest.fixture
def scripts(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    return tmp_path


class TestPayloadShape:
    def test_name_error_at_top_level(self, scripts):
        payload = run(scripts, "x = 1\nprint(x)\nprint(missing)\nprint('after')\n")
        assert payload["t"] == "error"
        assert payload["kind"] == "NameError"
        assert payload["message"].startswith("name 'missing' is not defined")
        (frame,) = payload["frames"]
        assert frame["file"] == "main.py"
        assert frame["line"] == 3
        assert frame["function"] == "<module>"
        assert frame["code"] == "print(missing)"
        assert payload["context"] == [
            {"line": 1, "code": "x = 1"},
            {"line": 2, "code": "print(x)"},
            {"line": 3, "code": "print(missing)"},
            {"line": 4, "code": "print('after')"},
        ]

    @needs_columns
    def test_columns_are_one_based_and_end_exclusive(self, scripts):
        payload = run(scripts, "print(missing)\n")
        frame = payload["frames"][0]
        assert (frame["col"], frame["end_col"]) == (7, 14)

    @pytest.mark.skipif(HAS_COLUMNS, reason="Python 3.10 only")
    def test_no_columns_on_python_310(self, scripts):
        frame = run(scripts, "print(missing)\n")["frames"][0]
        assert "col" not in frame and "end_col" not in frame

    def test_json_serialisable(self, scripts):
        import json

        json.dumps(run(scripts, "1/0\n"))

    def test_context_at_start_and_end_of_file(self, scripts):
        first = run(scripts, "1/0\nprint(2)\nprint(3)\n")
        assert [c["line"] for c in first["context"]] == [1, 2]
        last = run(scripts, "print(1)\nprint(2)\n1/0\n")
        assert [c["line"] for c in last["context"]] == [1, 2, 3]

    def test_context_is_two_before_one_after(self, scripts):
        source = "\n".join(f"print({n})" for n in range(1, 9)) + "\n1/0\n" + "pass\n" * 5
        payload = run(scripts, source)
        assert [c["line"] for c in payload["context"]] == [7, 8, 9, 10]

    def test_blank_context_lines_are_kept(self, scripts):
        payload = run(scripts, "a = 1\n\nb = 1/0\n")
        assert payload["context"][1] == {"line": 2, "code": ""}

    def test_no_traceback_gives_no_frames(self):
        payload = build_error_payload(ValueError("boom"), Path("."))
        assert payload["frames"] == [] and payload["context"] == []
        assert payload["kind"] == "ValueError" and payload["message"] == "boom"


class TestFrames:
    def test_nested_functions_outermost_first(self, scripts):
        source = "def inner():\n    return 1 / 0\n\ndef outer():\n    inner()\n\nouter()\n"
        frames = run(scripts, source)["frames"]
        assert [(f["function"], f["line"]) for f in frames] == [
            ("<module>", 7),
            ("outer", 5),
            ("inner", 2),
        ]
        assert frames[-1]["code"] == "return 1 / 0"

    def test_last_frame_provides_the_context(self, scripts):
        source = "def go():\n    return 1 / 0\n\ngo()\n"
        payload = run(scripts, source)
        assert [c["line"] for c in payload["context"]] == [1, 2, 3]

    @needs_columns
    def test_columns_for_indented_code_count_the_indent(self, scripts):
        source = "def go():\n    bal.x += 1\n\ngo()\n"
        frame = run(scripts, source)["frames"][-1]
        assert frame["code"] == "bal.x += 1"
        assert (frame["col"], frame["end_col"]) == (5, 8)

    def test_stdlib_frames_are_dropped(self, scripts):
        source = (
            "import json\n"
            "def bad(value):\n"
            "    raise ValueError('nope')\n"
            "json.dumps(object(), default=bad)\n"
        )
        frames = run(scripts, source)["frames"]
        assert [(f["file"], f["function"]) for f in frames] == [
            ("main.py", "<module>"),
            ("main.py", "bad"),
        ]

    def test_framework_frames_are_dropped(self, scripts):
        core = pytest.importorskip("core")
        source = "Circle(x='ten')\n"
        path = scripts / "main.py"
        path.write_text(source)
        with pytest.raises(TypeError) as info:
            exec(compile(source, str(path), "exec"), {**core.namespace()})
        payload = build_error_payload(info.value, scripts)
        assert [f["file"] for f in payload["frames"]] == ["main.py"]
        assert "must be a number" in payload["message"]

    def test_handler_error_shows_caller_then_handler(self, scripts):
        (scripts / "fake_framework.py").write_text("")
        source = (
            "def run_handler(handler):\n"
            "    handler()\n"
            "\n"
            "def on_click():\n"
            "    ball.x = 1\n"
            "\n"
            "run_handler(on_click)\n"
        )
        frames = run(scripts, source)["frames"]
        assert [f["function"] for f in frames] == ["<module>", "run_handler", "on_click"]

    def test_other_files_in_the_script_directory_are_user_frames(self, scripts):
        (scripts / "helper_one.py").write_text("def explode():\n    raise RuntimeError('bang')\n")
        payload = run(scripts, "import helper_one\nhelper_one.explode()\n")
        assert [(f["file"], f["line"]) for f in payload["frames"]] == [
            ("main.py", 2),
            ("helper_one.py", 2),
        ]
        assert [c["code"] for c in payload["context"]][-1] == "    raise RuntimeError('bang')"

    def test_import_time_error_in_a_module(self, scripts):
        (scripts / "helper_two.py").write_text("x = 1\ny = nothing_here\n")
        payload = run(scripts, "import helper_two\n")
        assert [f["file"] for f in payload["frames"]] == ["main.py", "helper_two.py"]
        assert payload["kind"] == "NameError"

    def test_sub_directory_files_use_relative_paths(self, scripts):
        package = scripts / "pkg_one"
        package.mkdir()
        (package / "__init__.py").write_text("")
        (package / "tools.py").write_text("def f():\n    return [][1]\n")
        payload = run(scripts, "from pkg_one import tools\ntools.f()\n")
        assert payload["frames"][-1]["file"] == "pkg_one/tools.py"
        assert payload["kind"] == "IndexError"

    def test_files_outside_the_script_directory_are_dropped(self, tmp_path, monkeypatch):
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        (outside / "far_away.py").write_text("def f():\n    raise KeyError('k')\n")
        monkeypatch.syspath_prepend(str(outside))
        home = tmp_path / "home"
        home.mkdir()
        payload = run(home, "import far_away\nfar_away.f()\n")
        assert [f["file"] for f in payload["frames"]] == ["main.py"]

    def test_site_packages_inside_the_script_directory_are_dropped(self, scripts):
        site = scripts / ".venv" / "lib" / "site-packages"
        site.mkdir(parents=True)
        (site / "thirdparty_lib.py").write_text("def f():\n    raise OSError('x')\n")
        sys.path.insert(0, str(site))
        try:
            payload = run(scripts, "import thirdparty_lib\nthirdparty_lib.f()\n")
        finally:
            sys.path.remove(str(site))
        assert [f["file"] for f in payload["frames"]] == ["main.py"]

    def test_string_exec_frames_are_dropped(self, scripts):
        payload = run(scripts, "exec('1/0')\n")
        assert [f["file"] for f in payload["frames"]] == ["main.py"]

    def test_long_recursion_is_trimmed_but_keeps_both_ends(self, scripts):
        source = "def f(n):\n    return f(n + 1)\n\nf(0)\n"
        payload = run(scripts, source)
        assert payload["kind"] == "RecursionError"
        frames = payload["frames"]
        assert len(frames) == _errors.KEEP_FIRST_FRAMES + _errors.KEEP_LAST_FRAMES
        assert frames[0]["function"] == "<module>"
        assert frames[-1]["function"] == "f"
        assert payload["context"]

    def test_exception_chain_is_ignored(self, scripts):
        source = (
            "try:\n"
            "    1 / 0\n"
            "except ZeroDivisionError as err:\n"
            "    raise ValueError('second') from err\n"
        )
        payload = run(scripts, source)
        assert payload["kind"] == "ValueError"
        assert payload["message"] == "second"
        assert [f["line"] for f in payload["frames"]] == [4]


class TestMessages:
    def test_kind_prefix_is_stripped(self, scripts):
        assert run(scripts, "1/0\n")["message"] == "division by zero"

    def test_custom_exception_class(self, scripts):
        source = "class Oops(Exception):\n    pass\nraise Oops('boom')\n"
        payload = run(scripts, source)
        assert payload["kind"] == "Oops"
        assert payload["message"] == "boom"

    def test_empty_message(self, scripts):
        payload = run(scripts, "raise ValueError\n")
        assert payload["kind"] == "ValueError"
        assert payload["message"] == ""

    def test_multiline_message_is_kept(self, scripts):
        assert run(scripts, "raise ValueError('a\\nb')\n")["message"] == "a\nb"

    def test_our_friendly_errors_pass_through(self, scripts):
        message = "Circle has no property 'colour'. Did you mean 'color'?"
        assert run(scripts, f"raise AttributeError({message!r})\n")["message"] == message

    @pytest.mark.skipif(not HAS_SUGGESTIONS, reason="suggestions come from Python 3.12+")
    def test_name_error_suggestion_is_kept(self, scripts):
        payload = run(scripts, "ball = 1\nbal.x = 2\n")
        assert payload["message"] == "name 'bal' is not defined. Did you mean: 'ball'?"

    @pytest.mark.skipif(not HAS_SUGGESTIONS, reason="suggestions come from Python 3.12+")
    def test_attribute_error_suggestion_is_kept(self, scripts):
        payload = run(scripts, "class A:\n    color = 1\nA().colour\n")
        assert "Did you mean: 'color'?" in payload["message"]

    def test_system_exit_like_exceptions_do_not_crash_the_builder(self, scripts):
        payload = run(scripts, "raise KeyboardInterrupt\n")
        assert payload["kind"] == "KeyboardInterrupt"


class TestSyntaxErrors:
    def test_unclosed_bracket(self, scripts):
        payload = run(scripts, "print('hi')\nx = (1 +\n")
        assert payload["kind"] == "SyntaxError"
        assert "\n" not in payload["message"]
        assert payload["message"] != ""
        (frame,) = payload["frames"]
        assert frame["file"] == "main.py"
        assert frame["function"] == "<module>"
        assert frame["line"] in (2, 3)
        assert payload["context"][-1]["line"] >= frame["line"] - 1

    def test_missing_colon_points_at_the_line_and_columns(self, scripts):
        payload = run(scripts, "x = 1\nif x == 1\n    print(x)\n")
        assert payload["kind"] == "SyntaxError"
        assert payload["message"] == "expected ':'"
        (frame,) = payload["frames"]
        assert frame["line"] == 2
        assert frame["code"] == "if x == 1"
        assert frame["col"] == 10
        assert frame["end_col"] > frame["col"]
        assert [c["line"] for c in payload["context"]] == [1, 2, 3]

    def test_invalid_syntax_columns(self, scripts):
        payload = run(scripts, "print('a' 'b' 1)\n")
        (frame,) = payload["frames"]
        assert payload["message"] == "invalid syntax. Perhaps you forgot a comma?" or (
            payload["message"] == "invalid syntax"
        )
        assert 1 <= frame["col"] < frame["end_col"] <= len(frame["code"]) + 1

    def test_indentation_error(self, scripts):
        payload = run(scripts, "x = 1\n    y = 2\n")
        assert payload["kind"] == "IndentationError"
        assert payload["message"] == "unexpected indent"
        assert payload["frames"][0]["line"] == 2

    def test_expected_indented_block(self, scripts):
        payload = run(scripts, "def f():\nprint(1)\n")
        assert payload["kind"] == "IndentationError"
        assert payload["message"].startswith("expected an indented block")
        assert payload["frames"][0]["line"] == 2

    def test_tab_error(self, scripts):
        payload = run(scripts, "if True:\n        x = 1\n\ty = 2\n")
        assert payload["kind"] in ("TabError", "IndentationError")
        assert payload["frames"]

    def test_unicode_before_the_error_uses_character_columns(self, scripts):
        payload = run(scripts, 's = "héllo wörld" 1\n')
        (frame,) = payload["frames"]
        assert frame["code"] == 's = "héllo wörld" 1'
        assert frame["col"] <= len('s = "héllo wörld" ') + 1
        assert frame["end_col"] <= len(frame["code"]) + 1

    def test_unterminated_string(self, scripts):
        payload = run(scripts, "x = 1\nprint('oops)\n")
        assert payload["kind"] == "SyntaxError"
        assert payload["frames"][0]["line"] == 2

    def test_syntax_error_at_end_of_file_does_not_break(self, scripts):
        payload = run(scripts, "def f(:\n")
        assert payload["kind"] == "SyntaxError"
        assert payload["frames"] and payload["context"]

    def test_syntax_error_in_an_imported_module_shows_the_import_too(self, scripts):
        (scripts / "broken_mod.py").write_text("x = (\n")
        payload = run(scripts, "import broken_mod\n")
        assert payload["kind"] == "SyntaxError"
        assert [f["file"] for f in payload["frames"]] == ["main.py", "broken_mod.py"]

    def test_null_bytes_fall_back_gracefully(self, tmp_path):
        payload = run(tmp_path, b"x = 1\x00\n")
        assert payload["t"] == "error" and payload["kind"] in ("SyntaxError", "ValueError")

    def test_syntax_error_without_location(self, tmp_path):
        payload = build_error_payload(SyntaxError("odd"), tmp_path)
        assert payload["message"] == "odd"
        assert payload["frames"] == []


class TestTabsAndUnicode:
    def test_tabs_are_expanded_in_code_context_and_columns(self, scripts):
        payload = run(scripts, "def f():\n\treturn nothing\n\nf()\n")
        frame = payload["frames"][-1]
        assert frame["code"] == "return nothing"
        assert payload["context"][1] == {"line": 2, "code": "    return nothing"}
        if HAS_COLUMNS:
            line = payload["context"][1]["code"]
            assert line[frame["col"] - 1 : frame["end_col"] - 1] == "nothing"

    @needs_columns
    def test_columns_count_characters_not_bytes(self, scripts):
        payload = run(scripts, "print('héé€', nothing)\n")
        frame = payload["frames"][0]
        line = payload["context"][0]["code"]
        assert line[frame["col"] - 1 : frame["end_col"] - 1] == "nothing"

    @needs_columns
    def test_emoji_columns(self, scripts):
        payload = run(scripts, "print('😀😀', nothing)\n")
        frame = payload["frames"][0]
        line = payload["context"][0]["code"]
        assert line[frame["col"] - 1 : frame["end_col"] - 1] == "nothing"

    @needs_columns
    def test_multiline_spans_highlight_to_the_end_of_the_first_line(self, scripts):
        source = "x = max(\n    1,\n    'a',\n)\n"
        frame = run(scripts, source)["frames"][0]
        assert frame["line"] == 1
        assert (frame["col"], frame["end_col"]) == (5, len("x = max(") + 1)

    def test_utf8_bom_does_not_shift_lines(self, tmp_path):
        payload = run(tmp_path, b"\xef\xbb\xbfprint(1)\nprint(missing)\n")
        assert payload["frames"][0]["line"] == 2
        assert payload["context"][0]["code"] == "print(1)"

    def test_crlf_files(self, tmp_path):
        payload = run(tmp_path, b"a = 1\r\nb = 2\r\nprint(missing)\r\n")
        assert [c["code"] for c in payload["context"]] == ["a = 1", "b = 2", "print(missing)"]


def summary(**fields):
    base = {"filename": "main.py", "lineno": 1, "name": "<module>", "line": ""}
    return types.SimpleNamespace(**{**base, **fields})


class TestOlderPythonPaths:
    """Frame summaries from Python 3.10 have no column information at all."""

    def test_summary_without_column_attributes(self, tmp_path):
        (tmp_path / "main.py").write_text("x = 1\nprint(y)\n")
        sources = _errors._Sources()
        frame = _errors._summary_frame(
            summary(lineno=2, line="print(y)"), "main.py", str(tmp_path / "main.py"), sources
        )
        assert frame == {"file": "main.py", "line": 2, "function": "<module>", "code": "print(y)"}

    def test_summary_with_none_columns(self, tmp_path):
        (tmp_path / "main.py").write_text("print(y)\n")
        frame = _errors._summary_frame(
            summary(colno=None, end_colno=None),
            "main.py",
            str(tmp_path / "main.py"),
            _errors._Sources(),
        )
        assert "col" not in frame

    def test_byte_offsets_become_character_columns(self, tmp_path):
        line = "print('é€', y)"
        (tmp_path / "main.py").write_text(line + "\n", encoding="utf-8")
        start = line.encode().index(b"y)")
        frame = _errors._summary_frame(
            summary(colno=start, end_colno=start + 1, end_lineno=1),
            "main.py",
            str(tmp_path / "main.py"),
            _errors._Sources(),
        )
        assert line[frame["col"] - 1 : frame["end_col"] - 1] == "y"

    def test_multiline_span_ends_at_end_of_first_line(self, tmp_path):
        (tmp_path / "main.py").write_text("x = f(\n    1)\n")
        frame = _errors._summary_frame(
            summary(colno=4, end_colno=6, end_lineno=2),
            "main.py",
            str(tmp_path / "main.py"),
            _errors._Sources(),
        )
        assert (frame["col"], frame["end_col"]) == (5, 7)

    def test_missing_source_file_uses_the_summary_line(self, tmp_path):
        frame = _errors._summary_frame(
            summary(lineno=4, line="go()"),
            "main.py",
            str(tmp_path / "gone.py"),
            _errors._Sources(),
        )
        assert frame["code"] == "go()" and frame["line"] == 4

    def test_byte_to_char(self):
        assert _errors._byte_to_char("héllo", 0) == 0
        assert _errors._byte_to_char("héllo", 3) == 2
        assert _errors._byte_to_char("héllo", 2) == 1  # in the middle of 'é'
        assert _errors._byte_to_char("abc", 99) == 3


class TestNeverRaises:
    def test_broken_str(self, tmp_path):
        class Bad(Exception):
            def __str__(self):
                raise RuntimeError("no")

        payload = build_error_payload(Bad(), tmp_path)
        assert payload["kind"] == "Bad" and payload["frames"] == []
        assert _errors._fallback(Bad())["message"] == ""

    def test_source_file_deleted_before_formatting(self, scripts):
        path = scripts / "main.py"
        path.write_text("print(missing)\n")
        with pytest.raises(NameError) as info:
            exec(compile(path.read_text(), str(path), "exec"), {})
        path.unlink()
        payload = build_error_payload(info.value, scripts)
        assert payload["kind"] == "NameError"
        assert payload["frames"][0]["line"] == 1
        assert payload["context"] == []

    def test_formatting_failure_falls_back(self, scripts, monkeypatch):
        def explode(*args, **kwargs):
            raise RuntimeError("formatter bug")

        monkeypatch.setattr(_errors, "_build", explode)
        payload = build_error_payload(ValueError("boom"), scripts)
        assert payload == {
            "t": "error",
            "kind": "ValueError",
            "message": "boom",
            "frames": [],
            "context": [],
        }

    def test_script_directory_that_does_not_exist(self):
        payload = build_error_payload(ValueError("x"), "/no/such/dir")
        assert payload["kind"] == "ValueError"

    def test_accepts_path_objects(self, scripts):
        assert run(scripts, "1/0\n")["frames"]
        with pytest.raises(ZeroDivisionError) as info:
            exec("1 / 0")
        assert build_error_payload(info.value, scripts)["kind"] == "ZeroDivisionError"


class TestDescribe:
    def test_with_frame(self):
        payload = {
            "kind": "NameError",
            "message": "name 'x' is not defined",
            "frames": [{"file": "main.py", "line": 3}],
        }
        assert describe_error(payload) == "NameError: name 'x' is not defined (main.py, line 3)"

    def test_without_frame_or_message(self):
        assert describe_error({"kind": "Error", "message": "Stopped", "frames": []}) == (
            "Error: Stopped"
        )
        assert describe_error({"kind": "ValueError", "message": "", "frames": []}) == "ValueError"
        assert describe_error({}) == "Error"
