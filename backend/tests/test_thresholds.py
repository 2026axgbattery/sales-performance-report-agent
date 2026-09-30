import pytest

from app.db import Database
from app.services.thresholds import (
    ALL_METRICS,
    METRIC_PLAN_ACHIEVEMENT,
    METRIC_PREV_MONTH,
    UnknownMetricError,
    get_thresholds,
    update_thresholds,
)


@pytest.fixture()
def db():
    database = Database(":memory:")
    yield database
    database.close()


def test_get_thresholds_seeds_prd_defaults(db):
    thresholds = get_thresholds(db)
    assert set(thresholds.keys()) == set(ALL_METRICS)
    assert thresholds[METRIC_PREV_MONTH].threshold_value == 10.0
    assert thresholds[METRIC_PLAN_ACHIEVEMENT].threshold_low == 90.0
    assert thresholds[METRIC_PLAN_ACHIEVEMENT].threshold_high == 120.0


def test_get_thresholds_is_idempotent(db):
    first = get_thresholds(db)
    second = get_thresholds(db)
    assert first[METRIC_PREV_MONTH].threshold_value == second[METRIC_PREV_MONTH].threshold_value
    count = db.connection.execute("SELECT COUNT(*) FROM threshold_config").fetchone()[0]
    assert count == len(ALL_METRICS)


def test_update_thresholds_changes_only_targeted_metric(db):
    updated = update_thresholds(db, [{"metric_type": METRIC_PREV_MONTH, "threshold_value": 25.0}])
    assert updated[METRIC_PREV_MONTH].threshold_value == 25.0
    assert updated[METRIC_PLAN_ACHIEVEMENT].threshold_low == 90.0  # 다른 기준은 그대로


def test_update_thresholds_rejects_unknown_metric(db):
    with pytest.raises(UnknownMetricError):
        update_thresholds(db, [{"metric_type": "존재하지않는기준", "threshold_value": 1.0}])
