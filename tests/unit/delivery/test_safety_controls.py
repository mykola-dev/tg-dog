from pathlib import Path


def test_single_active_run_lock_blocks_second_run(tmp_path: Path) -> None:
    from services.shared.runtime.locks import acquire_or_assert_run_lock

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    assert acquire_or_assert_run_lock(workspace, "run-1") is True
    assert acquire_or_assert_run_lock(workspace, "run-1") is True
    assert acquire_or_assert_run_lock(workspace, "run-2") is False


def test_digest_fingerprint_dedup_detects_duplicate(tmp_path: Path) -> None:
    from services.shared.runtime.idempotency import DeliveryDedupStore

    store = DeliveryDedupStore(tmp_path)
    assert store.is_duplicate_fingerprint("fp-1") is False
    store.record_fingerprint("fp-1")
    assert store.is_duplicate_fingerprint("fp-1") is True


def test_rate_limiter_applies_bounded_base_rate_limit() -> None:
    from services.shared.runtime.rate_limits import BoundedRateLimiter

    limiter = BoundedRateLimiter(base_delay_seconds=0.1, max_chunks_per_run=5)
    assert limiter.allow_chunk(1) is True
    assert limiter.allow_chunk(5) is True
    assert limiter.allow_chunk(6) is False
