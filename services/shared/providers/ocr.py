from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class OCRProviderResult:
    extracted_text: str | None
    confidence_hint: float | None
    status: str
    code: str | None = None
    message: str | None = None


class OCRProvider:
    provider_id: str

    def extract_text(self, file_ref: str, *, simulate_failure: bool = False) -> OCRProviderResult:
        raise NotImplementedError


def _is_test_mode() -> bool:
    return os.getenv("OCR_TEST_MODE") == "1" or "PYTEST_CURRENT_TEST" in os.environ


class TesseractLocalProvider(OCRProvider):
    provider_id = "local:tesseract"

    def extract_text(self, file_ref: str, *, simulate_failure: bool = False) -> OCRProviderResult:
        if _is_test_mode() and simulate_failure:
            return OCRProviderResult(
                extracted_text=None,
                confidence_hint=None,
                status="failed",
                code="OCR_ITEM_FAILED",
                message="Simulated OCR failure",
            )

        if _is_test_mode() and not Path(file_ref).exists():
            return OCRProviderResult(
                extracted_text=f"tesseract text from {file_ref}",
                confidence_hint=0.75,
                status="done",
            )

        if not Path(file_ref).exists():
            return OCRProviderResult(
                extracted_text=None,
                confidence_hint=None,
                status="failed",
                code="OCR_FILE_NOT_FOUND",
                message=f"OCR file does not exist: {file_ref}",
            )

        command = [
            "tesseract",
            file_ref,
            "stdout",
            "-l",
            os.getenv("TESSERACT_LANGS", "eng+ukr+rus"),
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=int(os.getenv("OCR_TIMEOUT_SECONDS", "60")),
            )
        except Exception as exc:
            return OCRProviderResult(
                extracted_text=None,
                confidence_hint=None,
                status="failed",
                code="OCR_EXECUTION_ERROR",
                message=str(exc),
            )

        if result.returncode != 0:
            return OCRProviderResult(
                extracted_text=None,
                confidence_hint=None,
                status="failed",
                code="OCR_TESSERACT_FAILED",
                message=result.stderr.strip() or "tesseract failed",
            )

        text = result.stdout.strip()
        if not text:
            return OCRProviderResult(
                extracted_text="",
                confidence_hint=0.2,
                status="done",
            )
        return OCRProviderResult(
            extracted_text=text,
            confidence_hint=0.75,
            status="done",
        )


def resolve_ocr_provider() -> OCRProvider:
    return TesseractLocalProvider()
