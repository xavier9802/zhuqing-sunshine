from __future__ import annotations

import csv
import json
import re
from datetime import UTC, datetime
from io import BytesIO, StringIO
from pathlib import Path
from zipfile import ZipFile

import httpx

GEONAMES_CITIES_URL = "https://download.geonames.org/export/dump/cities15000.zip"
GEONAMES_ADMIN1_URL = "https://download.geonames.org/export/dump/admin1CodesASCII.txt"
GEONAMES_HOME = "https://www.geonames.org/"
GEONAMES_LICENSE = "https://creativecommons.org/licenses/by/4.0/"

CITY_DEFINITIONS = (
    ("chengdu", "成都", "Chengdu", "Sichuan"),
    ("chongqing", "重庆", "Chongqing", "Chongqing"),
    ("mianyang", "绵阳", "Mianyang", "Sichuan"),
    ("deyang", "德阳", "Deyang", "Sichuan"),
    ("suining", "遂宁", "Suining", "Sichuan"),
    ("nanchong", "南充", "Nanchong", "Sichuan"),
    ("guangan", "广安", "Guang'an", "Sichuan"),
    ("ziyang", "资阳", "Ziyang", "Sichuan"),
    ("meishan", "眉山", "Meishan", "Sichuan"),
    ("leshan", "乐山", "Leshan", "Sichuan"),
    ("neijiang", "内江", "Neijiang", "Sichuan"),
    ("zigong", "自贡", "Zigong", "Sichuan"),
    ("yibin", "宜宾", "Yibin", "Sichuan"),
    ("luzhou", "泸州", "Luzhou", "Sichuan"),
)

COLUMNS = (
    "geonameid", "name", "asciiname", "alternatenames", "latitude", "longitude",
    "feature_class", "feature_code", "country_code", "cc2", "admin1_code",
    "admin2_code", "admin3_code", "admin4_code", "population", "elevation",
    "dem", "timezone", "modification_date",
)
FEATURE_PRIORITY = {"PPLC": 0, "PPLA": 1, "PPLA2": 2, "PPLA3": 3, "PPLA4": 4, "PPL": 5}


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _download(url: str, client: httpx.Client) -> bytes:
    response = client.get(url)
    response.raise_for_status()
    return response.content


def _admin1_names(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in csv.reader(StringIO(text), delimiter="\t"):
        if len(row) >= 3 and row[0].startswith("CN."):
            result[row[0].split(".", 1)[1]] = row[2]
    return result


def parse_city_dump(
    dump_text: str,
    admin1_text: str,
    fetched_at: datetime | None = None,
) -> list[dict[str, object]]:
    admin1 = _admin1_names(admin1_text)
    rows_by_name: dict[str, list[dict[str, str]]] = {}

    for row in csv.reader(StringIO(dump_text), delimiter="\t"):
        if len(row) < len(COLUMNS):
            continue
        record = dict(zip(COLUMNS, row))
        if record["country_code"] != "CN" or record["feature_class"] != "P":
            continue
        key = _normalise(record["asciiname"] or record["name"])
        rows_by_name.setdefault(key, []).append(record)

    snapshot_time = (fetched_at or datetime.now(UTC)).isoformat()
    results: list[dict[str, object]] = []

    for slug, name_zh, name_en, expected_admin1 in CITY_DEFINITIONS:
        candidates = [
            row
            for row in rows_by_name.get(_normalise(name_en), [])
            if admin1.get(row["admin1_code"]) == expected_admin1
            and row["feature_code"] in FEATURE_PRIORITY
        ]
        if not candidates:
            raise ValueError(
                f"GeoNames cities15000 has no unambiguous candidate for "
                f"{name_en} ({expected_admin1})"
            )

        candidates.sort(
            key=lambda row: (
                FEATURE_PRIORITY[row["feature_code"]],
                -int(row["population"] or 0),
                int(row["geonameid"]),
            )
        )
        chosen = candidates[0]
        results.append(
            {
                "slug": slug,
                "name_zh": name_zh,
                "name_en": name_en,
                "geoname_id": int(chosen["geonameid"]),
                "latitude": float(chosen["latitude"]),
                "longitude": float(chosen["longitude"]),
                "population": int(chosen["population"] or 0),
                "feature_code": chosen["feature_code"],
                "admin1": expected_admin1,
                "source": "GeoNames cities15000",
                "source_url": GEONAMES_HOME,
                "source_license": "CC BY 4.0",
                "source_license_url": GEONAMES_LICENSE,
                "snapshot_fetched_at": snapshot_time,
                "coordinate_semantics": "gazetteer_populated_place_point",
            }
        )

    return results


def download_city_catalog(data_dir: Path) -> list[dict[str, object]]:
    data_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=httpx.Timeout(60, connect=15)) as client:
        cities_zip = _download(GEONAMES_CITIES_URL, client)
        admin1_text = _download(GEONAMES_ADMIN1_URL, client).decode("utf-8")

    with ZipFile(BytesIO(cities_zip)) as archive:
        member = next(
            (name for name in archive.namelist() if name.endswith("cities15000.txt")),
            None,
        )
        if member is None:
            raise ValueError("GeoNames archive does not contain cities15000.txt")
        dump_text = archive.read(member).decode("utf-8")

    catalog = parse_city_dump(dump_text, admin1_text)
    output = data_dir / "cities.json"
    output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return catalog
