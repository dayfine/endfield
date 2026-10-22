from endfield import jsonc, pi
from endfield.config import Config

CFG = Config(
    adb="/opt/adb/adb",
    serial="SERIAL1",
    package="com.gryphline.endfield.gp",
    force_size="1080x1920",
    client_version="Global",
)


def test_jsonc_strips_comments_and_trailing_commas():
    text = """{
        // line comment
        "a": "keep // this", /* block */
        "b": [1, 2,],
    }"""
    assert jsonc.loads(text) == {"a": "keep // this", "b": [1, 2]}


def test_jsonc_keeps_escaped_quotes():
    assert jsonc.loads(r'{"a": "say \"hi\" // not a comment"}') == {
        "a": 'say "hi" // not a comment'
    }


def test_task_options_by_type():
    task = pi.Task(
        "T",
        {"Sel": "Global", "Box": ["a", "b"], "In": {"count": "3"}},
    )
    assert task.to_config() == {
        "name": "T",
        "option": [
            {"name": "Sel", "value": "Global"},
            {"name": "Box", "values": ["a", "b"]},
            {"name": "In", "inputs": {"count": "3"}},
        ],
    }


def test_pi_config_names_device_like_toolkit():
    conf = pi.pi_config(CFG, [pi.Task("AndroidOpenGame")])
    assert conf["controller"] == {"name": "ADB"}
    assert conf["adb"] == {
        "name": "SERIAL1-/opt/adb/adb",
        "adb_path": "/opt/adb/adb",
        "address": "SERIAL1",
    }
    assert conf["task"] == [{"name": "AndroidOpenGame", "option": []}]


def test_jsonc_leaves_commas_inside_strings():
    assert jsonc.loads('{"a": "x,]", "b": "y, }"}') == {"a": "x,]", "b": "y, }"}


def test_task_results_from_maafw_log():
    log = (
        b'[x][INF] !!!OnEventNotify!!! [handle=true] [msg=Tasker.Task.Starting] '
        b'[details={"entry":"A","hash":"1"}]\n'
        b'[x][INF] [msg=Tasker.Task.Succeeded] [details={"entry":"A","hash":"1"}]\n'
        b'[x][INF] [msg=Tasker.Task.Failed] [details={"entry":"B","hash":"2"}]\n'
    )
    assert pi.task_results(log) == [("A", True), ("B", False)]
