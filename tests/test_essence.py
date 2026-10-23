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
