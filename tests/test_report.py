import json

from endfield import report


def _ev(ts, kind, entry):
    return (f'[2026-10-23 {ts}.000][INF][Px1][Tx1][EventDispatcher.hpp][L65][x] !!!OnEventNotify!!! '
            f'[handle=true] [msg=Tasker.Task.{kind}] [details={{"entry":"{entry}","hash":"h"}}]')


def _node(ts, name):
    return (f'[2026-10-23 {ts}.000][INF][Px1][Tx1][EventDispatcher.hpp][L65][x] !!!OnEventNotify!!! '
            f'[handle=true] [msg=Node.PipelineNode.Succeeded] [details={{"focus":null,"name":"{name}"}}]')


def _agent(ts, **fields):
    return json.dumps({"level": "info", "time": f"2026-10-23T{ts}-07:00", **fields})


def test_flags_credit_overflow_and_game_restart(tmp_path):
    (tmp_path / "maafw.log").write_text("\n".join([
        _ev("10:00:00", "Starting", "OpenGame"),
        _node("10:01:30", "StuckRepairAction"),
        _ev("10:02:00", "Succeeded", "OpenGame"),
        _ev("10:02:00", "Starting", "CreditShoppingMain"),
        _ev("10:03:00", "Succeeded", "CreditShoppingMain"),
        _ev("10:03:00", "Starting", "DijiangRewards"),
        _ev("10:04:00", "Failed", "DijiangRewards"),
    ]))
    (tmp_path / "go-service.log").write_text("\n".join([
        _agent("10:02:30", component="ExpressionRecognition",
               values={"CreditShoppingReserveCreditOCRInternal": 810}),
        _agent("10:03:30", component="AddItemData", item_id="item_spaceship_credit",
               item_name="Credits", delta=120),
    ]))
    tasks, problems = report.build(tmp_path)
    assert [t.entry for t in tasks] == ["OpenGame", "CreditShoppingMain", "DijiangRewards"]
    assert tasks[0].seconds == 120
    assert f"{report.task_label('DijiangRewards')} 失敗" in problems
    assert any("930/300" in p for p in problems)
    assert any("強制重啟" in p for p in problems)
    assert f"{report.item_label('item_spaceship_credit', 'Credits')}×120" in report.render(tmp_path)


def test_table_pads_by_display_width():
    lines = report.table(["任務", "結果", "內容"], [["拜訪好友", "ok", "x"], ["OpenGame", "失敗", ""]])
    assert len({report._width(line.rsplit("|", 2)[0]) for line in lines}) == 1
