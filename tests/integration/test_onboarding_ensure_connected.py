from __future__ import annotations

from unittest.mock import patch

import pytest


def test_ensure_connected_exits_zero_when_connected() -> None:
    from services.onboarding.ensure_connected import main

    with patch("services.onboarding.ensure_connected.check_and_onboard", return_value=True):
        with pytest.raises(SystemExit) as exc:
            main()

    assert exc.value.code == 0


def test_ensure_connected_exits_nonzero_when_not_connected() -> None:
    from services.onboarding.ensure_connected import main

    with patch("services.onboarding.ensure_connected.check_and_onboard", return_value=False):
        with pytest.raises(SystemExit) as exc:
            main()

    assert exc.value.code == 1
