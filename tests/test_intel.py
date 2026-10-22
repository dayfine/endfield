from endfield.intel import fuzzy_match

NAMES = ["天師樁陣列的留音", "雨滴的留音", "源石副產物中心的報告", "源石副產物中心的日誌", "老漢斯檔案"]


def test_fuzzy_fixes_one_char_ocr_slip():
    assert fuzzy_match("天師椿陣列的留音", NAMES) == "天師樁陣列的留音"


def test_fuzzy_truncated_prefix_unique_or_ambiguous():
    assert fuzzy_match("天師樁陣列…", NAMES) == "天師樁陣列的留音"
    assert fuzzy_match("源石副產物中心..", NAMES) is None


def test_fuzzy_rejects_noise():
    assert fuzzy_match("0000000", NAMES) is None
    assert fuzzy_match("NEW", NAMES) is None
    assert fuzzy_match("老漢斯h案", NAMES) == "老漢斯檔案"
