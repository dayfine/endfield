import json

from endfield import essence, pi

WANT = ["悼亡詩", "莫奈何", "苦難的盡頭", "聚合工業", "探驪"]


def test_plan_covers_weapons_and_tasks_validate():
    steps = essence.plan(WANT)
    assert {w for s in steps for w in s.weapons} == set(WANT)
    assert steps == essence.plan(WANT)  # `essence go N` relies on a stable order
    for step in steps:
        assert len(essence.fill_base(step.base)) == 3
        assert pi.validate([essence.go_task(step)]) == []


def test_skill_codes_match_autoessence_labels():
    # 苦難的盡頭: 敏捷 / 自然傷害 / 迸發
    codes = essence.needs(["苦難的盡頭"])["苦難的盡頭"]
    assert essence.skill_label(codes[0]) == "敏捷"
    assert essence.skill_label(codes[2]) == "迸發"


def test_owned_essences_drop_weapons_from_the_plan(tmp_path):
    # Shape of EssenceFilter's EssenceInventory.json: one group per skill combination.
    export = tmp_path / "EssenceInventory.json"
    export.write_text(json.dumps([
        {"weapon_ids": ["wpn_funnel_0005", "wpn_sword_0006"],
         "essences": [{"levels": [1, 2, 1], "count": 1}, {"levels": [6, 6, 3], "count": 1}]},
        {"weapon_ids": ["wpn_sword_0011"], "essences": [{"levels": [1, 1, 1], "count": 2}]},
    ]))
    have = essence.owned(export)
    assert have["悼亡詩"] == [(6, 6, 3), (1, 2, 1)]
    assert have["扶搖"] == [(1, 1, 1), (1, 1, 1)]
    assert essence.still_needed(["悼亡詩", "扶搖", "莫奈何"], have) == ["莫奈何"]
