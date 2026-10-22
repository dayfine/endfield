from endfield import overrides


def test_nested_ocr_gets_tc_and_keeps_other_params():
    node = {"recognition": {"type": "OCR", "param": {"expected": ["情报档案库"], "roi": [0, 0, 1, 1]}}}
    assert overrides.tc_override(node) == {
        "recognition": {"type": "OCR", "param": {"expected": ["情报档案库", "情報檔案庫"], "roi": [0, 0, 1, 1]}}
    }


def test_flat_ocr_gets_tc():
    assert overrides.tc_override({"recognition": "OCR", "expected": "纸质记录"}) == {
        "expected": ["纸质记录", "紙質記錄"]
    }


def test_no_override_when_tc_present_or_not_ocr():
    assert overrides.tc_override({"recognition": "OCR", "expected": ["确认", "確認"]}) is None
    assert overrides.tc_override({"recognition": "OCR", "expected": ["(?i)confirm"]}) is None
    assert overrides.tc_override({"recognition": "TemplateMatch", "template": "a.png"}) is None


def test_inline_sub_recognitions_get_tc():
    node = {
        "recognition": "And",
        "all_of": [{"recognition": {"type": "OCR", "param": {"expected": ["音像存档"]}}}, "InIntelArchive"],
        "action": "Click",
    }
    assert overrides.tc_override(node) == {
        "all_of": [
            {"recognition": {"type": "OCR", "param": {"expected": ["音像存档", "音像存檔"]}}},
            "InIntelArchive",
        ]
    }
