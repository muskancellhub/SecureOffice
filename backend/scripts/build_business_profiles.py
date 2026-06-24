"""Convert the Business Requirements matrix (xlsx) into the runtime seed JSON.

The Excel at ``backend/app/data/business_profiles/business_requirements.xlsx``
is the human-authored *source of truth* (8 business types x ~54 requirement
attributes). The binary workbook is kept in the repo for provenance, but the
**runtime** source of truth is the generated ``business_profiles.json`` next to
it — it is diffable in PRs, needs no openpyxl at runtime, and is what the
deterministic mapper + the AI ``BusinessProfileKnowledgeTool`` load.

Re-run this whenever the workbook changes:

    python backend/scripts/build_business_profiles.py

A CI test (``tests/test_business_profiles_seed.py``) asserts the committed JSON
matches a fresh conversion, so the two can never silently drift.
"""

from __future__ import annotations

import json
from pathlib import Path

import openpyxl

DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "data" / "business_profiles"
XLSX_PATH = DATA_DIR / "business_requirements.xlsx"
JSON_PATH = DATA_DIR / "business_profiles.json"

SEED_VERSION = "1.0"

# Rows 1-3 of the sheet are author instructions ("user has to enter"), not data.
INSTRUCTION_MARKERS = ("user has to enter",)


def _coerce(value: object) -> object:
    """Coerce a cell into a typed JSON value.

    - integer-valued floats  -> int
    - 'Yes'/'No'             -> bool
    - comma-separated strings -> list[str]  (e.g. 'Toast, QuickBooks')
    - everything else         -> trimmed str / passthrough
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else float(value)
    text = str(value).strip()
    low = text.lower()
    if low == "yes":
        return True
    if low == "no":
        return False
    if "," in text:
        return [part.strip() for part in text.split(",") if part.strip()]
    return text


def build() -> dict:
    wb = openpyxl.load_workbook(XLSX_PATH, data_only=True)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(values_only=True))

    header = rows[0]
    business_types = [str(h).strip() for h in header[1:] if h is not None]

    attributes: list[str] = []
    profiles: dict[str, dict[str, object]] = {bt: {} for bt in business_types}

    for row in rows[1:]:
        label = row[0]
        if label is None:
            continue
        label = str(label).strip()
        if not label:
            continue
        values = row[1 : 1 + len(business_types)]
        # Skip instruction-only rows (label present, no per-type values).
        if all(v is None for v in values):
            if any(m in label.lower() for m in INSTRUCTION_MARKERS):
                continue
            continue
        attributes.append(label)
        for bt, val in zip(business_types, values):
            profiles[bt][label] = _coerce(val)

    return {
        "version": SEED_VERSION,
        "source": "business_requirements.xlsx",
        "businessTypes": business_types,
        "attributes": attributes,
        "profiles": profiles,
    }


def main() -> None:
    seed = build()
    JSON_PATH.write_text(json.dumps(seed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {JSON_PATH} — {len(seed['businessTypes'])} types, {len(seed['attributes'])} attributes.")


if __name__ == "__main__":
    main()
