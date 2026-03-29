# Node Toggles

Pipeline settings let you enable or disable optional nodes.

## V1 toggles

- `ocr`
- `heuristic-filter`
- `classification`

## Persistence

- Toggle values are persisted in runtime state.
- Defaults are disabled for both optional nodes.

## Effect on runs

- Disabled node is skipped.
- Enabled node is part of each manual/scheduled pipeline execution.

## OCR specifics

- Default OCR path is local `Tesseract` for weak-hardware compatibility.
- Baseline OCR languages: `eng`, `ukr`, `rus`.
