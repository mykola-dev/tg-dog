def test_manual_run_uses_last_24_hours_by_default() -> None:
    from services.shared.runtime.time_windows import manual_last_n_hours_window

    start, end = manual_last_n_hours_window(24)
    assert end > start
    delta = end - start
    assert int(delta.total_seconds()) == 24 * 3600
