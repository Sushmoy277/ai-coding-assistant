import pytest

from assistant.tools import ToolError, Workspace


def allow(_description):
    return True


def deny(_description):
    return False


@pytest.fixture
def ws(tmp_path):
    (tmp_path / "hello.py").write_text("print('hi')\nprint('bye')\n")
    return Workspace(tmp_path, approve=allow)


def edit(ws, **tool_input):
    return ws.execute("str_replace_based_edit_tool", tool_input)


# ------------------------------------------------------------- path safety

@pytest.mark.parametrize("bad", ["../secret.txt", "/etc/passwd", "sub/../../x", "%2e%2e/x"])
def test_paths_outside_root_are_rejected(ws, bad):
    with pytest.raises(ToolError):
        ws.resolve(bad)


def test_symlink_escape_is_rejected(ws, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    (ws.root / "link").symlink_to(outside)
    with pytest.raises(ToolError):
        ws.resolve("link/file.txt")


def test_absolute_path_inside_root_is_allowed(ws):
    assert ws.resolve(str(ws.root / "hello.py")) == ws.root / "hello.py"


# ------------------------------------------------------------- text editor

def test_view_file_numbers_lines(ws):
    content, is_error = edit(ws, command="view", path="hello.py")
    assert not is_error
    assert "     1\tprint('hi')" in content
    assert "     2\tprint('bye')" in content


def test_view_range(ws):
    content, _ = edit(ws, command="view", path="hello.py", view_range=[2, -1])
    assert "bye" in content and "hi'" not in content


def test_view_directory(ws):
    content, _ = edit(ws, command="view", path=".")
    assert "hello.py" in content


def test_create_new_file(ws):
    content, is_error = edit(ws, command="create", path="pkg/new.py", file_text="x = 1\n")
    assert not is_error
    assert (ws.root / "pkg/new.py").read_text() == "x = 1\n"


def test_create_overwrite_keeps_backup(ws):
    edit(ws, command="create", path="hello.py", file_text="new\n")
    assert (ws.root / "hello.py").read_text() == "new\n"
    assert (ws.root / "hello.py.bak").read_text().startswith("print('hi')")


def test_str_replace_once(ws):
    _, is_error = edit(ws, command="str_replace", path="hello.py", old_str="hi", new_str="hello")
    assert not is_error
    assert (ws.root / "hello.py").read_text() == "print('hello')\nprint('bye')\n"


def test_str_replace_no_match_is_error(ws):
    content, is_error = edit(ws, command="str_replace", path="hello.py", old_str="nope", new_str="x")
    assert is_error and "not found" in content


def test_str_replace_multiple_matches_is_error(ws):
    content, is_error = edit(ws, command="str_replace", path="hello.py", old_str="print", new_str="log")
    assert is_error and "2 places" in content


def test_insert_at_start(ws):
    _, is_error = edit(ws, command="insert", path="hello.py", insert_line=0, insert_text="# top")
    assert not is_error
    assert (ws.root / "hello.py").read_text().startswith("# top\nprint('hi')")


def test_declined_change_leaves_file_alone(tmp_path):
    (tmp_path / "a.txt").write_text("keep\n")
    ws = Workspace(tmp_path, approve=deny)
    content, is_error = ws.execute(
        "str_replace_based_edit_tool",
        {"command": "str_replace", "path": "a.txt", "old_str": "keep", "new_str": "gone"},
    )
    assert is_error and "declined" in content
    assert (tmp_path / "a.txt").read_text() == "keep\n"


# -------------------------------------------------------------------- bash

def test_bash_runs_in_root(ws):
    content, is_error = ws.execute("bash", {"command": "ls"})
    assert not is_error and "hello.py" in content


def test_bash_reports_exit_code(ws):
    content, is_error = ws.execute("bash", {"command": "exit 3"})
    assert not is_error and "[exit code 3]" in content


def test_bash_declined(tmp_path):
    ws = Workspace(tmp_path, approve=deny)
    content, is_error = ws.execute("bash", {"command": "touch made.txt"})
    assert is_error and "declined" in content
    assert not (tmp_path / "made.txt").exists()


def test_bash_timeout(tmp_path):
    ws = Workspace(tmp_path, approve=allow, bash_timeout=1)
    content, is_error = ws.execute("bash", {"command": "sleep 5"})
    assert is_error and "timed out" in content


def test_unknown_tool(ws):
    content, is_error = ws.execute("teleport", {})
    assert is_error and "Unknown tool" in content
