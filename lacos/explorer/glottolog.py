"""Lightweight Glottolog data loader for explorer views."""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path


DATA_PATH = Path(__file__).resolve().parent / "data" / "glottolog" / "languages_and_dialects_geo.csv"


@lru_cache(maxsize=1)
def _load_glottolog_geo():
    by_glottocode: dict[str, dict] = {}
    by_iso: dict[str, dict] = {}

    try:
        with DATA_PATH.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                glottocode = row.get("glottocode", "").strip()
                isocodes = row.get("isocodes", "").strip()
                entry = {
                    "name": row.get("name", "").strip(),
                    "macroarea": row.get("macroarea", "").strip(),
                    "latitude": float(row["latitude"]) if row.get("latitude") else None,
                    "longitude": float(row["longitude"]) if row.get("longitude") else None,
                    "level": row.get("level", "").strip(),
                }

                if glottocode:
                    by_glottocode[glottocode] = entry

                if isocodes:
                    for code in isocodes.replace(";", ",").split(","):
                        code = code.strip()
                        if code:
                            by_iso[code] = entry
    except FileNotFoundError:
        return {}, {}

    return by_glottocode, by_iso


def lookup_glottolog_entry(*, glottocode: str | None = None, iso_code: str | None = None) -> dict | None:
    by_glottocode, by_iso = _load_glottolog_geo()
    if glottocode and glottocode in by_glottocode:
        return by_glottocode[glottocode]
    if iso_code and iso_code in by_iso:
        return by_iso[iso_code]
    return None
