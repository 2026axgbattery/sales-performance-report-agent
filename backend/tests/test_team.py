import pytest

from app.services.team import classify_team, classify_team_from_division, mapping_prefix


def test_classify_team_known_codes():
    assert classify_team(20342) == "모티브"
    assert classify_team(20345) == "고정형"
    assert classify_team(20313) == "차량대리점"


def test_classify_team_unknown_code_falls_back_to_default():
    assert classify_team(99999) == "차량OE"


def test_classify_team_from_division_known_values():
    # 08월 실제 "Raw Data_업로드용.xlsb" 파일 전체 7676행에서 확인된 4개 값
    assert classify_team_from_division("2630 차량대리점팀") == "차량대리점"
    assert classify_team_from_division("2640 차량OE팀") == "차량OE"
    assert classify_team_from_division("2620 산전모티브팀") == "모티브"
    assert classify_team_from_division("2610 산전고정형팀") == "고정형"


def test_classify_team_from_division_rejects_unknown_value():
    with pytest.raises(ValueError):
        classify_team_from_division("9999 알수없는팀")


def test_mapping_prefix_overrides_motive_and_fixed():
    assert mapping_prefix("모티브") == "산전"
    assert mapping_prefix("고정형") == "산전"


def test_mapping_prefix_passthrough_for_others():
    assert mapping_prefix("차량대리점") == "차량대리점"
    assert mapping_prefix("차량OE") == "차량OE"
