"""Monitor tests — psutil works on every OS we test on."""

from panelpro.core import monitor as monitor_mod


def test_snapshot_shape():
    snap = monitor_mod.MONITOR.snapshot()
    assert 0 <= snap["cpu"] <= 100 * max(snap["cpu_cores"])
    assert snap["mem_total"] > 0
    assert snap["uptime"] >= 0
    assert "net_in" in snap and "net_out" in snap
    assert isinstance(snap["disks"], list)


def test_top_processes():
    result = monitor_mod.top_processes(5)
    assert len(result["by_cpu"]) <= 5
    assert all("pid" in p for p in result["by_cpu"])


def test_disk_usage_all():
    disks = monitor_mod.disk_usage_all()
    assert isinstance(disks, list)
    if disks:
        assert {"device", "mount", "total", "used", "percent"} <= set(disks[0])


def test_history_empty_is_safe():
    rows = monitor_mod.history(since_ts=1)  # far past; may hit DB fallback
    assert isinstance(rows, list)
