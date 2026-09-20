from app.resources import collect_capacity, collect_usage


def test_collect_capacity_returns_positive_values():
    capacity = collect_capacity()
    assert capacity["cpu_total"] >= 1
    assert capacity["ram_total_mb"] > 0
    assert capacity["storage_total_gb"] > 0


def test_collect_usage_returns_non_negative_values():
    usage = collect_usage()
    assert usage["cpu_used"] >= 0
    assert usage["ram_used_mb"] >= 0
    assert usage["storage_used_gb"] >= 0
