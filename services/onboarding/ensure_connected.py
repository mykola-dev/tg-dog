from __future__ import annotations

import sys

from services.onboarding.startup import check_and_onboard


def main() -> None:
    success = check_and_onboard()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
