#!/usr/bin/env python3
"""Fetch, validate, aggregate, and publish weekly ODEPA consumer prices."""

from __future__ import annotations

import argparse
import csv
from contextlib import closing
import hashlib
import io
import json
import logging
import os
import re
import shutil
import sqlite3
import tempfile
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "prices.db"
DEFAULT_OUTPUT = ROOT / "site" / "data"
METADATA_URL = "https://datos.odepa.gob.cl/api/3/action/package_show?id=precios-consumidor"
DATASTORE_URL = "https://datos.odepa.gob.cl/api/3/action/datastore_search"
DATASET_ID = "precios-consumidor"
MIN_SOURCE_YEAR = 2017
FRESHNESS_MAX_AGE_DAYS = 28
BENCHMARK_HISTORY_WEEKS = 52
# A curated reference basket per monitor, not an automatic popularity ranking.
# Current candidates were checked for everyday relevance, source-specific variety,
# comparable units where possible, and at least 40 observations in the last 52 weeks.
# The homepage still suppresses any candidate whose selected scope is no longer fresh.
BENCHMARK_PRODUCTS = (
    {
        "key": "rice",
        "label": "Arroz",
        "group_name": "Abarrotes y otros",
        "product_name": "Arroz grano ancho grado 1",
        "unit": "$/kilo",
        "point_types": {"Supermercado": 1, "Supermercado en Línea": 1},
    },
    {
        "key": "bread",
        "label": "Marraqueta",
        "group_name": "Pan",
        "product_name": "Marraqueta",
        "unit": "$/kilo",
        "point_types": {"Panadería": 1, "Supermercado": 2, "Supermercado en Línea": 2},
    },
    {
        "key": "milk",
        "label": "Leche entera",
        "group_name": "Lácteos - Huevos - Margarinas",
        "product_name": "Leche Fluida Entera",
        "unit": "$/Caja de 1 Litro",
        "point_types": {"Supermercado": 3, "Supermercado en Línea": 3},
    },
    {
        "key": "eggs",
        "label": "Huevo blanco",
        "group_name": "Lácteos - Huevos - Margarinas",
        "product_name": "Huevo blanco grande (primera)",
        "unit": "$/bandeja 12 unidades",
        "point_types": {
            "Feria libre": 5,
            "Supermercado": 4,
            "Supermercado en Línea": 4,
        },
    },
    {
        "key": "chicken",
        "label": "Pollo entero",
        "group_name": "Carne de Cerdo - Ave - Cordero",
        "product_name": "Pollo Entero",
        "unit": "$/kilo",
        "point_types": {
            "Carnicería": 2,
            "Supermercado": 5,
            "Supermercado en Línea": 5,
        },
    },
    {
        "key": "potato",
        "label": "Papa Asterix",
        "group_name": "Hortalizas",
        "product_name": "Papa|Asterix|Primera",
        "unit": "$/kilo",
        "point_types": {
            "Feria libre": 1,
            "Mercado Minorista": 1,
            "Supermercado": 6,
            "Supermercado en Línea": 6,
        },
    },
    {
        "key": "beef-abastero",
        "label": "Abastero",
        "group_name": "Carne bovina",
        "product_name": "Abastero",
        "unit": "$/kilo",
        "point_types": {"Carnicería": 1},
    },
    {
        "key": "pork-loin",
        "label": "Lomo de cerdo",
        "group_name": "Carne de Cerdo - Ave - Cordero",
        "product_name": "Cerdo Lomo",
        "unit": "$/kilo",
        "point_types": {"Carnicería": 3},
    },
    {
        "key": "pork-center-chop",
        "label": "Chuleta de centro",
        "group_name": "Carne de Cerdo - Ave - Cordero",
        "product_name": "Chuleta (centro)",
        "unit": "$/kilo",
        "point_types": {"Carnicería": 4},
    },
    {
        "key": "avocado-hass",
        "label": "Palta Hass",
        "group_name": "Frutas",
        "product_name": "Palta|Hass|Primera",
        "unit": "$/kilo",
        "point_types": {"Feria libre": 2, "Mercado Minorista": 2},
    },
    {
        "key": "tomato-long-life",
        "label": "Tomate larga vida",
        "group_name": "Hortalizas",
        "product_name": "Tomate|Larga vida|Primera",
        "unit": "$/kilo",
        "point_types": {"Feria libre": 3, "Mercado Minorista": 3},
    },
    {
        "key": "banana",
        "label": "Plátano",
        "group_name": "Frutas",
        "product_name": "Plátano|Sin especificar|Primera",
        "unit": "$/kilo",
        "point_types": {"Feria libre": 4, "Mercado Minorista": 4},
    },
    {
        "key": "minorista-white-eggs",
        "label": "Huevo blanco (primera)",
        "group_name": "Lácteos - Huevos - Margarinas",
        "product_name": "Huevo blanco - Primera",
        "unit": "$/bandeja 30 unidades",
        "point_types": {"Mercado Minorista": 5},
    },
    {
        "key": "hallulla",
        "label": "Hallulla corriente",
        "group_name": "Pan",
        "product_name": "Hallulla corriente",
        "unit": "$/kilo",
        "point_types": {"Panadería": 2},
    },
    {
        "key": "pan-amasado",
        "label": "Pan amasado",
        "group_name": "Pan",
        "product_name": "Pan amasado",
        "unit": "$/kilo",
        "point_types": {"Panadería": 3},
    },
    {
        "key": "wholesale-split-peas",
        "label": "Arvejas partidas · saco 25 kg",
        "group_name": "Abarrotes y otros",
        "product_name": "Arvejas verdes partidas",
        "unit": "$/kilo (en saco de 25 kilos)",
        "point_types": {"Mercado Mayorista": 1},
    },
    {
        "key": "wholesale-chickpeas",
        "label": "Garbanzos · saco 25 kg",
        "group_name": "Abarrotes y otros",
        "product_name": "Garbanzos sin piel",
        "unit": "$/kilo (en saco de 25 kilos)",
        "point_types": {"Mercado Mayorista": 2},
    },
    {
        "key": "wholesale-lentils",
        "label": "Lentejas 6 mm · saco 25 kg",
        "group_name": "Abarrotes y otros",
        "product_name": "Lentejas 6mm",
        "unit": "$/kilo (en saco de 25 kilos)",
        "point_types": {"Mercado Mayorista": 3},
    },
    {
        "key": "wholesale-tortola-beans",
        "label": "Poroto tórtola · saco 25 kg",
        "group_name": "Abarrotes y otros",
        "product_name": "Poroto Tórtola",
        "unit": "$/kilo (en saco de 25 kilos)",
        "point_types": {"Mercado Mayorista": 4},
    },
)
EXCLUDED_SOURCE_YEARS = {
    2019: "Recurso anual omitido por una inconsistencia detectada en precios mínimos y máximos de ODEPA."
}
KNOWN_INVALID_OBSERVATIONS = (
    {
        "year": 2021,
        "week_number": 47,
        "week_start": "2021-11-22",
        "region_id": 9,
        "region_name": "Región de La Araucanía",
        "sector": "Barrio Inglés - Estadio",
        "point_type": "Mercado Minorista",
        "group_name": "Lácteos - Huevos - Margarinas",
        "product_name": "Huevo blanco - Segunda",
        "unit": "$/bandeja 12 unidades",
        "minimum": 980,
        "maximum": 2,
        "average": Decimal("1.14"),
    },
    {
        "year": 2021,
        "week_number": 47,
        "week_start": "2021-11-22",
        "region_id": 9,
        "region_name": "Región de La Araucanía",
        "sector": "Barrio Inglés - Estadio",
        "point_type": "Mercado Minorista",
        "group_name": "Lácteos - Huevos - Margarinas",
        "product_name": "Huevo color - Segunda",
        "unit": "$/bandeja 12 unidades",
        "minimum": 980,
        "maximum": 2,
        "average": Decimal("1.8"),
    },
)
MICROS = Decimal(1_000_000)
PRICE_QUANTUM = Decimal("0.000001")
PERCENT_QUANTUM = Decimal("0.01")
USER_AGENT = "food-price-monitor-cl/1.0 (public ODEPA data monitor)"
LOG = logging.getLogger("food_price_monitor")


class SourceError(Exception):
    """An upstream response or source row cannot be used safely."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS source_files (
    source_year INTEGER PRIMARY KEY CHECK (source_year >= 2017),
    resource_id TEXT NOT NULL,
    source_url TEXT NOT NULL CHECK (source_url LIKE 'https://datos.odepa.gob.cl/%'),
    remote_hash TEXT,
    download_sha256 TEXT NOT NULL,
    last_modified TEXT,
    imported_at TEXT NOT NULL,
    row_count INTEGER NOT NULL CHECK (row_count >= 0),
    latest_week_start TEXT,
    excluded_observations_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS products (
    product_key TEXT PRIMARY KEY,
    group_name TEXT NOT NULL,
    group_slug TEXT NOT NULL,
    product_name TEXT NOT NULL,
    unit TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    UNIQUE (group_name, product_name, unit)
);

CREATE TABLE IF NOT EXISTS history (
    week_start TEXT NOT NULL,
    week_end TEXT NOT NULL CHECK (week_end >= week_start),
    product_key TEXT NOT NULL REFERENCES products(product_key),
    region_id INTEGER NOT NULL,
    region_name TEXT NOT NULL,
    sector TEXT NOT NULL,
    point_type TEXT NOT NULL,
    price_min_clp INTEGER NOT NULL CHECK (price_min_clp >= 0),
    price_max_clp INTEGER NOT NULL CHECK (price_max_clp >= price_min_clp),
    price_avg_micros INTEGER NOT NULL CHECK (price_avg_micros >= 0),
    source_year INTEGER NOT NULL REFERENCES source_files(source_year) ON DELETE CASCADE,
    PRIMARY KEY (week_start, product_key, region_id, sector, point_type)
);

CREATE INDEX IF NOT EXISTS history_product_period
    ON history (product_key, week_start, point_type, region_id);
CREATE INDEX IF NOT EXISTS history_source_year
    ON history (source_year);
"""


HEADER_ALIASES = {
    "anio": "anio",
    "ano": "anio",
    "semana": "semana",
    "fecha inicio": "fecha_inicio",
    "fecha termino": "fecha_termino",
    "id region": "id_region",
    "region": "region",
    "sector": "sector",
    "tipo de punto monitoreo": "tipo_punto",
    "grupo": "grupo",
    "producto": "producto",
    "unidad": "unidad",
    "precio minimo": "precio_minimo",
    "precio maximo": "precio_maximo",
    "precio promedio": "precio_promedio",
}
REQUIRED_FIELDS = frozenset(HEADER_ALIASES.values())
DELIMITERS = (",", ";", "\t", "|")


def connect_db(path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    """Open a database with foreign-key enforcement and a useful row factory."""
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def init_db(path: Path | str = DEFAULT_DB) -> None:
    """Create the schema idempotently."""
    with closing(connect_db(path)) as connection:
        connection.executescript(SCHEMA)
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(source_files)")}
        if "excluded_observations_json" not in columns:
            connection.execute(
                "ALTER TABLE source_files ADD COLUMN excluded_observations_json TEXT NOT NULL DEFAULT '[]'"
            )


def _normalise_header(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text.casefold().strip())


def _normalise_identity(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _normalise_product_label(value: str) -> str:
    """Normalize cosmetic ODEPA label changes without erasing product facets."""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold().replace("’", "").replace("'", "")
    text = re.sub(r"\s*\|\s*", "|", text)
    return " ".join(text.split())


BENCHMARK_IDENTITIES = {
    tuple(_normalise_product_label(str(item[field])) for field in ("group_name", "product_name", "unit")): item
    for item in BENCHMARK_PRODUCTS
}
# This one source typo has the same group, cultivar, grade, unit, and no
# duplicate observation cells as the established Valencia product. Keep this
# semantic exception explicit; do not infer aliases from fuzzy name similarity.
PRODUCT_ALIAS_RULES = (
    (
        ("Frutas", "Naranja | Valenciana | Segunda", "$/kilo"),
        ("Frutas", "Naranja|Valencia|Segunda", "$/kilo"),
    ),
)


def _canonical_product_identity(group_name: str, product_name: str, unit: str) -> tuple[str, str, str]:
    identity = tuple(_normalise_product_label(value) for value in (group_name, product_name, unit))
    for source, target in PRODUCT_ALIAS_RULES:
        normalized_source = tuple(_normalise_product_label(value) for value in source)
        if identity == normalized_source:
            return tuple(_normalise_product_label(value) for value in target)
    return identity


def _stable_key(parts: Iterable[str]) -> str:
    payload = json.dumps([_normalise_identity(part) for part in parts], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stable_slug(label: str, identity: str | None = None) -> str:
    """Create a readable stable slug with a collision-resistant suffix."""
    identity = identity or label
    normalized = unicodedata.normalize("NFKD", label)
    ascii_label = normalized.encode("ascii", "ignore").decode("ascii").casefold()
    base = re.sub(r"[^a-z0-9]+", "-", ascii_label).strip("-")[:48].rstrip("-") or "item"
    suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]
    return f"{base}-{suffix}"


BENCHMARK_POINT_SLUGS = {
    label: stable_slug(label, _normalise_identity(label))
    for item in BENCHMARK_PRODUCTS
    for label in item["point_types"]
}


def validate_resource_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "datos.odepa.gob.cl":
        raise SourceError("resource URL must use HTTPS on datos.odepa.gob.cl")
    return url


def _year_from_metadata(resource: Mapping[str, object]) -> int | None:
    for field in ("name", "description"):
        value = str(resource.get(field) or "")
        years = {int(match) for match in re.findall(r"\b(20\d{2})\b", value)}
        if years:
            if len(years) != 1:
                raise SourceError(f"resource metadata has ambiguous year in {field}: {value[:120]}")
            return years.pop()
    return None


def select_annual_resources(
    dataset: Mapping[str, object], *, current_year: int | None = None
) -> list[dict[str, object]]:
    """Select one active annual CSV resource per in-scope year."""
    current_year = current_year or date.today().year
    resources = dataset.get("resources")
    if not isinstance(resources, list):
        raise SourceError("CKAN dataset metadata has no resources list")

    selected: dict[int, dict[str, object]] = {}
    for raw in resources:
        if not isinstance(raw, Mapping):
            continue
        if str(raw.get("state") or "").casefold() != "active":
            continue
        year = _year_from_metadata(raw)
        if year is None or year < MIN_SOURCE_YEAR or year > current_year:
            continue
        if year in EXCLUDED_SOURCE_YEARS:
            continue
        resource_format = str(raw.get("format") or "").strip().casefold()
        url = str(raw.get("url") or "")
        if resource_format and resource_format != "csv":
            continue
        if not resource_format and not urlparse(url).path.casefold().endswith(".csv"):
            continue
        resource_id = str(raw.get("resource_id") or raw.get("id") or "").strip()
        if not resource_id:
            raise SourceError(f"active CSV resource for {year} has no resource_id")
        if year in selected:
            raise SourceError(f"ambiguous active CSV resources for year {year}")
        resource = dict(raw)
        resource["year"] = year
        resource["resource_id"] = resource_id
        resource["url"] = validate_resource_url(url)
        selected[year] = resource

    if not selected:
        raise SourceError(f"no active annual CSV resources found from {MIN_SOURCE_YEAR} onward")
    return [selected[year] for year in sorted(selected)]


def parse_package_show(payload: object) -> dict[str, object]:
    if not isinstance(payload, Mapping) or payload.get("success") is not True:
        raise SourceError("ODEPA package_show did not return success=true")
    result = payload.get("result")
    if not isinstance(result, dict) or result.get("state", "active") != "active":
        raise SourceError("ODEPA package_show result is missing or inactive")
    return result


def _parse_decimal(value: object, field: str) -> Decimal:
    text = str(value or "").strip().replace("\u00a0", "").replace(" ", "")
    if not text:
        raise SourceError(f"required price field {field} is empty")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise SourceError(f"invalid price in {field}: {value!r}") from exc
    if not number.is_finite():
        raise SourceError(f"non-finite price in {field}: {value!r}")
    return number


def _parse_integer(value: object, field: str) -> int:
    number = _parse_decimal(value, field)
    if number != number.to_integral_value():
        raise SourceError(f"{field} must be an integer: {value!r}")
    return int(number)


def _parse_date(value: object, field: str) -> date:
    text = str(value or "").strip()
    if not text:
        raise SourceError(f"required date field {field} is empty")
    candidates = [text[:10], text]
    for candidate in candidates:
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise SourceError(f"invalid date in {field}: {value!r}")


def _clean_text(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SourceError(f"required source field {field} is empty")
    return text


def _normalise_source_values(row: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in row.items():
        key_text = str(key or "").strip()
        canonical = key_text if key_text in REQUIRED_FIELDS else HEADER_ALIASES.get(_normalise_header(key_text))
        if canonical:
            normalized[canonical] = value
    return normalized


def _record_from_mapping(row: Mapping[str, object], resource_year: int, row_number: int) -> dict[str, object]:
    normalized = _normalise_source_values(row)
    missing = REQUIRED_FIELDS - normalized.keys()
    if missing:
        raise SourceError(f"row {row_number} is missing required fields: {', '.join(sorted(missing))}")

    try:
        year = _parse_integer(normalized["anio"], "Anio")
        week_number = _parse_integer(normalized["semana"], "Semana")
        region_id = _parse_integer(normalized["id_region"], "ID region")
        week_start = _parse_date(normalized["fecha_inicio"], "Fecha inicio")
        week_end = _parse_date(normalized["fecha_termino"], "Fecha termino")
        minimum = _parse_integer(normalized["precio_minimo"], "Precio minimo")
        maximum = _parse_integer(normalized["precio_maximo"], "Precio maximo")
        average = _parse_decimal(normalized["precio_promedio"], "Precio promedio")
    except SourceError as exc:
        raise SourceError(f"row {row_number}: {exc}") from exc

    if year != resource_year:
        raise SourceError(f"row {row_number}: Anio {year} does not match resource year {resource_year}")
    if not 1 <= week_number <= 53:
        raise SourceError(f"row {row_number}: Semana must be between 1 and 53")
    if region_id <= 0:
        raise SourceError(f"row {row_number}: ID region must be positive")
    if week_start.weekday() != 0:
        raise SourceError(f"row {row_number}: Fecha inicio must be a Monday")
    if week_end < week_start:
        raise SourceError(f"row {row_number}: Fecha termino precedes Fecha inicio")
    group_name = _clean_text(normalized["grupo"], "Grupo")
    product_name = _clean_text(normalized["producto"], "Producto")
    unit = _clean_text(normalized["unidad"], "Unidad")
    region_name = _clean_text(normalized["region"], "Region")
    sector = _clean_text(normalized["sector"], "Sector")
    point_type = _clean_text(normalized["tipo_punto"], "Tipo de punto monitoreo")
    if minimum < 0 or maximum < minimum or average < 0:
        raise SourceError(
            f"row {row_number}: price values are outside the allowed range "
            f"(minimum={minimum}, maximum={maximum}, average={average}); "
            f"group={group_name!r}, product={product_name!r}, unit={unit!r}, "
            f"week_start={week_start.isoformat()}, region={region_name!r}, "
            f"sector={sector!r}, point_type={point_type!r}"
        )
    natural_identity = (group_name, product_name, unit)
    product_key = _stable_key(natural_identity)
    return {
        "source_year": resource_year,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "product_key": product_key,
        "group_name": group_name,
        "group_slug": stable_slug(group_name, _normalise_identity(group_name)),
        "product_name": product_name,
        "unit": unit,
        "slug": stable_slug(product_name, product_key),
        "region_id": region_id,
        "region_name": region_name,
        "sector": sector,
        "point_type": point_type,
        "point_slug": stable_slug(point_type, _normalise_identity(point_type)),
        "price_min_clp": minimum,
        "price_max_clp": maximum,
        "price_avg_micros": int((average * MICROS).to_integral_value(rounding=ROUND_HALF_UP)),
    }


def _match_known_invalid_observation(
    row: Mapping[str, object], resource_year: int
) -> dict[str, object] | None:
    normalized = _normalise_source_values(row)
    if REQUIRED_FIELDS - normalized.keys():
        return None
    try:
        year = _parse_integer(normalized["anio"], "Anio")
        week_number = _parse_integer(normalized["semana"], "Semana")
        week_start = _parse_date(normalized["fecha_inicio"], "Fecha inicio")
        week_end = _parse_date(normalized["fecha_termino"], "Fecha termino")
        region_id = _parse_integer(normalized["id_region"], "ID region")
        minimum = _parse_integer(normalized["precio_minimo"], "Precio minimo")
        maximum = _parse_integer(normalized["precio_maximo"], "Precio maximo")
        average = _parse_decimal(normalized["precio_promedio"], "Precio promedio")
        region_name = _clean_text(normalized["region"], "Region")
        sector = _clean_text(normalized["sector"], "Sector")
        point_type = _clean_text(normalized["tipo_punto"], "Tipo de punto monitoreo")
        group_name = _clean_text(normalized["grupo"], "Grupo")
        product_name = _clean_text(normalized["producto"], "Producto")
        unit = _clean_text(normalized["unidad"], "Unidad")
    except SourceError:
        return None
    if (
        year != resource_year
        or week_start.weekday() != 0
        or week_end < week_start
        or not 1 <= week_number <= 53
        or region_id <= 0
    ):
        return None

    values = {
        "year": year,
        "week_number": week_number,
        "week_start": week_start.isoformat(),
        "region_id": region_id,
        "region_name": region_name,
        "sector": sector,
        "point_type": point_type,
        "group_name": group_name,
        "product_name": product_name,
        "unit": unit,
        "minimum": minimum,
        "maximum": maximum,
        "average": average,
    }
    for known in KNOWN_INVALID_OBSERVATIONS:
        if all(
            _normalise_identity(str(values[field])) == _normalise_identity(str(known[field]))
            if field in {"region_name", "sector", "point_type", "group_name", "product_name", "unit"}
            else values[field] == known[field]
            for field in known
        ):
            return {
                "year": year,
                "week_start": week_start.isoformat(),
                "region_id": region_id,
                "region_name": region_name,
                "sector": sector,
                "point_type": point_type,
                "group_name": group_name,
                "product_name": product_name,
                "unit": unit,
                "price_min_clp": minimum,
                "price_max_clp": maximum,
                "reported_average": str(normalized["precio_promedio"]),
                "reason": (
                    f"ODEPA informó un precio mínimo de {minimum} superior al máximo de {maximum}; "
                    "se omitió la observación sin corregir el dato fuente."
                ),
            }
    return None


def parse_source_records(
    rows: Iterable[Mapping[str, object]],
    resource_year: int,
    *,
    excluded_observations: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    records: dict[tuple[object, ...], dict[str, object]] = {}
    excluded_keys: set[tuple[object, ...]] = set()
    parsed_count = 0
    for row_number, row in enumerate(rows, start=2):
        if not any(str(value or "").strip() for value in row.values()):
            continue
        try:
            record = _record_from_mapping(row, resource_year, row_number)
        except SourceError as exc:
            if "price values are outside the allowed range" not in str(exc):
                raise
            omitted = _match_known_invalid_observation(row, resource_year)
            if omitted is None:
                raise
            omitted_key = (
                omitted["week_start"], omitted["product_name"], omitted["region_id"],
                omitted["sector"], omitted["point_type"],
            )
            if omitted_key in excluded_keys:
                raise SourceError(f"row {row_number}: duplicate allowlisted invalid observation {omitted_key!r}")
            excluded_keys.add(omitted_key)
            if excluded_observations is not None:
                excluded_observations.append(omitted)
            continue
        parsed_count += 1
        key = (
            record["week_start"],
            record["product_key"],
            record["region_id"],
            record["sector"],
            record["point_type"],
        )
        previous = records.get(key)
        if previous is not None:
            if previous != record:
                raise SourceError(f"row {row_number}: conflicting duplicate primary key {key!r}")
            continue
        records[key] = record
    if parsed_count == 0:
        raise SourceError(f"resource year {resource_year} contains no source rows")
    return list(records.values())


def parse_csv_bytes(
    data: bytes,
    resource_year: int,
    *,
    excluded_observations: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SourceError("source CSV is not UTF-8") from exc
    if not text.strip():
        raise SourceError(f"resource year {resource_year} downloaded an empty CSV")

    first_line = next((line for line in text.splitlines() if line.strip()), "")
    matching: list[str] = []
    for delimiter in DELIMITERS:
        try:
            header = next(csv.reader([first_line], delimiter=delimiter))
        except (csv.Error, StopIteration):
            continue
        canonical = {HEADER_ALIASES.get(_normalise_header(item)) for item in header}
        if REQUIRED_FIELDS <= canonical:
            matching.append(delimiter)
    if len(matching) != 1:
        raise SourceError("could not identify a unique CSV delimiter from the required ODEPA headers")

    reader = csv.reader(io.StringIO(text, newline=""), delimiter=matching[0])
    try:
        raw_header = next(reader)
    except StopIteration as exc:
        raise SourceError("source CSV has no header") from exc
    canonical_header = [HEADER_ALIASES.get(_normalise_header(item)) or _normalise_header(item) for item in raw_header]
    if len(set(canonical_header)) != len(canonical_header):
        raise SourceError("source CSV contains duplicate normalized headers")
    missing = REQUIRED_FIELDS - set(canonical_header)
    if missing:
        raise SourceError(f"source CSV is missing required headers: {', '.join(sorted(missing))}")

    mapped_rows = []
    for row_number, values in enumerate(reader, start=2):
        if not values or not any(value.strip() for value in values):
            continue
        if len(values) != len(canonical_header):
            raise SourceError(f"row {row_number} has {len(values)} fields; expected {len(canonical_header)}")
        mapped_rows.append(dict(zip(canonical_header, values)))
    return parse_source_records(mapped_rows, resource_year, excluded_observations=excluded_observations)


def _resource_public_record(source: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {
        "year": int(source.get("source_year", source.get("year"))),
        "resource_id": str(source["resource_id"]),
        "download_sha256": str(source["download_sha256"]),
        "latest_week_start": source.get("latest_week_start"),
    }
    url = source.get("source_url", source.get("url"))
    if url:
        result["url"] = str(url)
    remote_hash = source.get("remote_hash", source.get("hash"))
    if remote_hash:
        result["hash"] = str(remote_hash)
    last_modified = source.get("last_modified")
    if last_modified:
        result["last_modified"] = str(last_modified)
    exclusions = source.get("excluded_observations")
    if exclusions is None:
        exclusions_json = source.get("excluded_observations_json")
        if exclusions_json:
            try:
                exclusions = json.loads(str(exclusions_json))
            except json.JSONDecodeError as exc:
                raise SourceError("cached excluded-observation provenance is not valid JSON") from exc
    if exclusions:
        if not isinstance(exclusions, list):
            raise SourceError("cached excluded-observation provenance must be an array")
        result["excluded_observations"] = exclusions
    return result


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_data_updated_at(
    previous_index: Mapping[str, object] | None,
    source_files: Iterable[Mapping[str, object]],
    *,
    now: str | None = None,
) -> str:
    current_resources = [_resource_public_record(item) for item in source_files]
    current_resources.sort(key=lambda item: item["year"])
    previous_timestamp = previous_index.get("data_updated_at") if previous_index else None
    previous_source = previous_index.get("source", {}) if previous_index else {}
    previous_resources = previous_source.get("resources", []) if isinstance(previous_source, Mapping) else []
    if previous_timestamp and previous_resources == current_resources:
        return str(previous_timestamp)
    return now or _utc_now_iso()


def _average_clp(sum_micros: int, count: int) -> Decimal:
    return Decimal(sum_micros) / Decimal(count) / MICROS


def _percent_change(current: Decimal, previous: Decimal | None) -> Decimal | None:
    if previous is None or previous == 0:
        return None
    return ((current / previous - Decimal(1)) * Decimal(100)).quantize(
        PERCENT_QUANTUM, rounding=ROUND_HALF_UP
    )


def _add_variations(points: list[dict[str, object]]) -> None:
    by_week = {str(point["week_start"]): point for point in points}
    for point in points:
        week = date.fromisoformat(str(point["week_start"]))
        current = point["average_clp"]
        assert isinstance(current, Decimal)
        previous_week = by_week.get((week - timedelta(days=7)).isoformat())
        previous_year = by_week.get((week - timedelta(days=364)).isoformat())
        point["wow_pct"] = _percent_change(
            current,
            previous_week["average_clp"] if previous_week else None,  # type: ignore[arg-type]
        )
        point["yoy_pct"] = _percent_change(
            current,
            previous_year["average_clp"] if previous_year else None,  # type: ignore[arg-type]
        )


def _build_product_catalog(
    source_products: Iterable[Mapping[str, object]],
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    """Map source identities to canonical public products and their aliases."""
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    for source in source_products:
        source_key = str(source["product_key"])
        group_name = str(source["group_name"])
        product_name = str(source["product_name"])
        unit = str(source["unit"])
        source_identity = tuple(
            _normalise_product_label(value) for value in (group_name, product_name, unit)
        )
        canonical_identity = _canonical_product_identity(group_name, product_name, unit)
        candidate = {
            "source_product_key": source_key,
            "source_identity": source_identity,
            "group_name": group_name,
            "product_name": product_name,
            "unit": unit,
            "latest_week_start": str(source.get("latest_week_start") or ""),
            "observation_count": int(source.get("observation_count") or 0),
        }
        grouped.setdefault(canonical_identity, []).append(candidate)

    source_to_canonical: dict[str, dict[str, object]] = {}
    canonical_products: dict[str, dict[str, object]] = {}
    for identity, candidates in grouped.items():
        preferred = [item for item in candidates if item["source_identity"] == identity]
        display_candidates = preferred or candidates
        latest_week = max(str(item["latest_week_start"]) for item in display_candidates)
        latest_candidates = [
            item for item in display_candidates if str(item["latest_week_start"]) == latest_week
        ]
        most_observed = max(int(item["observation_count"]) for item in latest_candidates)
        display_candidates = [
            item for item in latest_candidates if int(item["observation_count"]) == most_observed
        ]
        display = min(
            display_candidates,
            key=lambda item: (
                str(item["product_name"]).casefold(),
                str(item["product_name"]),
                str(item["source_product_key"]),
            ),
        )
        product_name = str(display["product_name"])
        group_name = str(display["group_name"])
        requires_canonical_key = len(candidates) > 1 or any(
            item["source_identity"] != identity for item in candidates
        )
        product_key = (
            _stable_key(("public-product", *identity))
            if requires_canonical_key
            else str(display["source_product_key"])
        )
        aliases = sorted(
            {
                str(item["product_name"])
                for item in candidates
                if str(item["product_name"]) != product_name
            },
            key=lambda value: (value.casefold(), value),
        )
        metadata: dict[str, object] = {
            "product_key": product_key,
            "group_name": group_name,
            "group_slug": stable_slug(group_name, _normalise_identity(group_name)),
            "product_name": product_name,
            "unit": str(display["unit"]),
            "slug": stable_slug(product_name, product_key),
            "aliases": aliases,
        }
        canonical_products[product_key] = metadata
        for candidate in candidates:
            source_key = str(candidate["source_product_key"])
            existing = source_to_canonical.get(source_key)
            if existing is not None and existing["product_key"] != product_key:
                raise SourceError("one source product key maps to multiple canonical products")
            source_to_canonical[source_key] = metadata
    return source_to_canonical, canonical_products


def _product_catalog_from_records(
    records: Iterable[Mapping[str, object]],
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    source_products: dict[str, dict[str, object]] = {}
    for record in records:
        source_key = str(record["product_key"])
        identity = tuple(str(record[field]) for field in ("group_name", "product_name", "unit"))
        product = source_products.get(source_key)
        if product is None:
            product = {
                "product_key": source_key,
                "group_name": identity[0],
                "product_name": identity[1],
                "unit": identity[2],
                "latest_week_start": str(record["week_start"]),
                "observation_count": 0,
            }
            source_products[source_key] = product
        elif identity != tuple(str(product[field]) for field in ("group_name", "product_name", "unit")):
            raise SourceError("one source product key maps to conflicting source labels")
        product["latest_week_start"] = max(
            str(product["latest_week_start"]), str(record["week_start"])
        )
        product["observation_count"] = int(product["observation_count"]) + 1
    return _build_product_catalog(source_products.values())


def _validate_alias_observation_overlaps(
    records: Iterable[Mapping[str, object]], source_to_canonical: Mapping[str, Mapping[str, object]]
) -> None:
    seen: dict[tuple[object, ...], str] = {}
    for record in records:
        source_key = str(record["product_key"])
        metadata = source_to_canonical[source_key]
        cell = (
            str(metadata["product_key"]),
            str(record["week_start"]),
            int(record["region_id"]),
            _normalise_identity(str(record["sector"])),
            str(record["point_slug"]),
        )
        previous = seen.get(cell)
        if previous is not None and previous != source_key:
            raise SourceError(
                f"product alias overlap for {metadata['product_name']!r} at "
                f"{record['week_start']} in region {record['region_id']}"
            )
        seen[cell] = source_key


def _canonicalize_records(
    records: Iterable[Mapping[str, object]],
    source_to_canonical: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    records = list(records)
    _validate_alias_observation_overlaps(records, source_to_canonical)
    public_identity_fields = (
        "product_key", "group_name", "group_slug", "product_name", "unit", "slug"
    )
    return [
        {
            **record,
            **{field: source_to_canonical[str(record["product_key"])][field] for field in public_identity_fields},
        }
        for record in records
    ]


def _aggregate_region_records(records: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    buckets: dict[tuple[object, ...], dict[str, object]] = {}
    metadata_fields = ("product_key", "group_name", "group_slug", "product_name", "unit", "slug", "point_slug", "point_type")
    for record in records:
        key = (
            record["product_key"],
            record["week_start"],
            record["point_slug"],
            record["region_id"],
        )
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {field: record[field] for field in metadata_fields}
            bucket.update(
                week_start=record["week_start"],
                region_id=int(record["region_id"]),
                region_name=str(record["region_name"]),
                sector_count=0,
                sum_micros=0,
                minimum=2**63 - 1,
                maximum=0,
                source_years=set(),
            )
            buckets[key] = bucket
        bucket["sector_count"] = int(bucket["sector_count"]) + 1
        bucket["sum_micros"] = int(bucket["sum_micros"]) + int(record["price_avg_micros"])
        bucket["minimum"] = min(int(bucket["minimum"]), int(record["price_min_clp"]))
        bucket["maximum"] = max(int(bucket["maximum"]), int(record["price_max_clp"]))
        years = bucket["source_years"]
        assert isinstance(years, set)
        years.add(int(record["source_year"]))
    result = []
    for bucket in buckets.values():
        count = int(bucket["sector_count"])
        result.append(
            {
                **{field: bucket[field] for field in metadata_fields},
                "week_start": bucket["week_start"],
                "region_id": int(bucket["region_id"]),
                "region_name": bucket["region_name"],
                "average_clp": _average_clp(int(bucket["sum_micros"]), count),
                "minimum_clp": int(bucket["minimum"]),
                "maximum_clp": int(bucket["maximum"]),
                "source_years": sorted(bucket["source_years"]),
            }
        )
    return result


def _build_aggregate_series(regional_rows: Iterable[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    rows = list(regional_rows)
    points: dict[str, dict[str, object]] = {}
    national_buckets: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        point_slug = str(row["point_slug"])
        point = points.setdefault(point_slug, {"national": [], "regions": {}})
        region_map = point["regions"]
        assert isinstance(region_map, dict)
        region_key = str(row["region_id"])
        region_points = region_map.setdefault(region_key, [])
        assert isinstance(region_points, list)
        region_points.append(
            {
                "week_start": str(row["week_start"]),
                "region_id": int(row["region_id"]),
                "region_name": str(row["region_name"]),
                "product_key": row["product_key"],
                "product_name": row["product_name"],
                "group_name": row["group_name"],
                "group_slug": row["group_slug"],
                "slug": row["slug"],
                "point_type": row["point_type"],
                "point_slug": point_slug,
                "average_clp": row["average_clp"],
                "minimum_clp": int(row["minimum_clp"]),
                "maximum_clp": int(row["maximum_clp"]),
                "source_years": sorted(int(year) for year in row["source_years"]),
            }
        )
        key = (point_slug, str(row["week_start"]))
        bucket = national_buckets.get(key)
        if bucket is None:
            bucket = {
                "metadata": row,
                "sum_average": Decimal(0),
                "region_count": 0,
                "minimum": 2**63 - 1,
                "maximum": 0,
                "source_years": set(),
            }
            national_buckets[key] = bucket
        bucket["sum_average"] += row["average_clp"]  # type: ignore[operator]
        bucket["region_count"] = int(bucket["region_count"]) + 1
        bucket["minimum"] = min(int(bucket["minimum"]), int(row["minimum_clp"]))
        bucket["maximum"] = max(int(bucket["maximum"]), int(row["maximum_clp"]))
        bucket["source_years"].update(int(year) for year in row["source_years"])  # type: ignore[union-attr]

    for (point_slug, week_start), bucket in national_buckets.items():
        point = points[point_slug]
        national_points = point["national"]
        assert isinstance(national_points, list)
        metadata = bucket["metadata"]
        national_points.append(
            {
                "week_start": week_start,
                "average_clp": bucket["sum_average"] / int(bucket["region_count"]),  # type: ignore[operator]
                "minimum_clp": int(bucket["minimum"]),
                "maximum_clp": int(bucket["maximum"]),
                "source_years": sorted(bucket["source_years"]),
                "point_type": metadata["point_type"],
                "product_key": metadata["product_key"],
                "product_name": metadata["product_name"],
                "group_name": metadata["group_name"],
                "unit": metadata["unit"],
                "slug": metadata["slug"],
                "group_slug": metadata["group_slug"],
                "point_slug": point_slug,
                "geography": "national",
                "region_id": None,
            }
        )

    for point_slug, point in points.items():
        national_points = point["national"]
        assert isinstance(national_points, list)
        national_points.sort(key=lambda item: str(item["week_start"]))
        _add_variations(national_points)
        region_map = point["regions"]
        assert isinstance(region_map, dict)
        for region_id, region_points in region_map.items():
            region_points.sort(key=lambda item: str(item["week_start"]))
            _add_variations(region_points)
            for item in region_points:
                item.update(geography="region", region_id=int(region_id))
    return points


def aggregate_records(records: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """Compute regional and national weekly summaries from sector observations."""
    records = list(records)
    regional = _aggregate_region_records(records)
    by_product: dict[str, list[dict[str, object]]] = {}
    for row in regional:
        by_product.setdefault(str(row["product_key"]), []).append(row)
    aggregated = []
    for product_rows in by_product.values():
        series = _build_aggregate_series(product_rows)
        for point_data in series.values():
            national = point_data["national"]
            assert isinstance(national, list)
            aggregated.extend(national)
            regions = point_data["regions"]
            assert isinstance(regions, dict)
            for region_points in regions.values():
                aggregated.extend(region_points)
    return sorted(
        aggregated,
        key=lambda row: (
            str(row["product_key"]),
            str(row["point_slug"]),
            str(row["week_start"]),
            str(row["geography"]),
            int(row["region_id"] or 0),
        ),
    )


def _public_point(point: Mapping[str, object]) -> dict[str, object]:
    average = point["average_clp"]
    assert isinstance(average, Decimal)
    wow = point.get("wow_pct")
    yoy = point.get("yoy_pct")
    return {
        "week_start": str(point["week_start"]),
        "source_years": sorted(int(year) for year in point["source_years"]),
        "average_clp": average.quantize(PRICE_QUANTUM, rounding=ROUND_HALF_UP),
        "minimum_clp": int(point["minimum_clp"]),
        "maximum_clp": int(point["maximum_clp"]),
        "wow_pct": wow.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP) if isinstance(wow, Decimal) else None,
        "yoy_pct": yoy.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP) if isinstance(yoy, Decimal) else None,
    }


def _freshness_references(
    regional_rows: Iterable[Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    """Find each point type's latest week nationally and in each region."""
    latest_by_region: dict[str, dict[str, str]] = {}
    for row in regional_rows:
        point_slug = str(row["point_slug"])
        region_id = str(row["region_id"])
        week_start = str(row["week_start"])
        regions = latest_by_region.setdefault(point_slug, {})
        if week_start > regions.get(region_id, ""):
            regions[region_id] = week_start

    return {
        point_slug: {
            "national": max(regions.values()),
            "regions": regions,
        }
        for point_slug, regions in latest_by_region.items()
    }


def _is_within_freshness_window(observed_week: str, reference_week: str) -> bool:
    age = date.fromisoformat(reference_week) - date.fromisoformat(observed_week)
    return timedelta(0) <= age <= timedelta(days=FRESHNESS_MAX_AGE_DAYS)


def _latest_public_point(
    point: Mapping[str, object],
    reference_week: str | None,
    previous_point: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return {
        **point,
        "previous_week_start": previous_point["week_start"] if previous_point else None,
        "previous_average_clp": previous_point["average_clp"] if previous_point else None,
        "fresh_within_28_days": bool(
            reference_week
            and _is_within_freshness_window(str(point["week_start"]), reference_week)
        ),
    }


def _benchmark_trends(
    series: Mapping[str, Mapping[str, object]], point_slugs: Iterable[str]
) -> dict[str, object]:
    """Keep compact one-year traces only for the scopes using this reference."""
    trends: dict[str, object] = {}
    selected_points = set(point_slugs)
    for point_slug, point_data in sorted(series.items()):
        if point_slug not in selected_points:
            continue
        national = point_data["national"]
        regions = point_data["regions"]
        assert isinstance(national, list) and isinstance(regions, dict)

        def compact(points: list[Mapping[str, object]]) -> list[dict[str, object]]:
            return [
                {
                    "week_start": str(point["week_start"]),
                    "average_clp": point["average_clp"],
                }
                for point in points[-BENCHMARK_HISTORY_WEEKS:]
            ]

        trends[point_slug] = {
            "national": compact(national),
            "regions": {
                region_id: compact(points)
                for region_id, points in sorted(regions.items(), key=lambda item: int(item[0]))
            },
        }
    return trends


def _product_payload(
    metadata: Mapping[str, object],
    regional_rows: Iterable[Mapping[str, object]],
    freshness_references: Mapping[str, Mapping[str, object]],
) -> tuple[dict[str, object], dict[str, object]]:
    series = _build_aggregate_series(regional_rows)
    public_types: dict[str, object] = {}
    latest_by_type: dict[str, object] = {}
    for point_slug, point_data in sorted(series.items()):
        national = [_public_point(point) for point in point_data["national"]]  # type: ignore[index]
        references = freshness_references.get(point_slug, {})
        national_reference = references.get("national")
        regional_references = references.get("regions", {})
        if not isinstance(regional_references, Mapping):
            regional_references = {}
        regions: dict[str, list[dict[str, object]]] = {}
        latest_regions: dict[str, dict[str, object]] = {}
        raw_regions = point_data["regions"]
        assert isinstance(raw_regions, dict)
        for region_id, points in sorted(raw_regions.items(), key=lambda item: int(item[0])):
            formatted = [_public_point(point) for point in points]
            regions[region_id] = formatted
            if formatted:
                regional_reference = regional_references.get(region_id)
                latest_regions[region_id] = _latest_public_point(
                    formatted[-1],
                    str(regional_reference) if regional_reference else None,
                    formatted[-2] if len(formatted) > 1 else None,
                )
        public_types[point_slug] = {"national": national, "regions": regions}
        if national:
            latest_by_type[point_slug] = {
                "national": _latest_public_point(
                    national[-1],
                    str(national_reference) if national_reference else None,
                    national[-2] if len(national) > 1 else None,
                ),
                "regions": latest_regions,
            }
    series_product = {
        "name": str(metadata["product_name"]),
        "unit": str(metadata["unit"]),
        "aliases": list(metadata.get("aliases", [])),
        "point_types": public_types,
    }
    summary = {
        "slug": str(metadata["slug"]),
        "name": str(metadata["product_name"]),
        "unit": str(metadata["unit"]),
        "aliases": list(metadata.get("aliases", [])),
        "latest_by_point_type": latest_by_type,
    }
    identity = tuple(
        _normalise_product_label(str(metadata[field]))
        for field in ("group_name", "product_name", "unit")
    )
    benchmark = BENCHMARK_IDENTITIES.get(identity)
    if benchmark:
        rank_by_point_type = {
            BENCHMARK_POINT_SLUGS[point_label]: rank
            for point_label, rank in benchmark["point_types"].items()
            if BENCHMARK_POINT_SLUGS[point_label] in series
        }
        if rank_by_point_type:
            summary["benchmark"] = {
                "key": benchmark["key"],
                "label": benchmark["label"],
                "rank_by_point_type": rank_by_point_type,
            }
            summary["trend_by_point_type"] = _benchmark_trends(series, rank_by_point_type)
    return series_product, summary


def _public_resources(source_files: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    resources = [_resource_public_record(item) for item in source_files]
    return sorted(resources, key=lambda item: int(item["year"]))


def _excluded_year_records() -> list[dict[str, object]]:
    return [
        {"year": year, "reason": reason}
        for year, reason in sorted(EXCLUDED_SOURCE_YEARS.items())
    ]


def build_public_documents(
    records: Iterable[Mapping[str, object]],
    source_files: Iterable[Mapping[str, object]],
    dataset_metadata: Mapping[str, object],
    *,
    data_updated_at: str,
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    """Build a complete index and group-series set; primarily useful for tests."""
    records = list(records)
    source_files = list(source_files)
    if any(int(record["source_year"]) in EXCLUDED_SOURCE_YEARS for record in records):
        raise SourceError("public documents must not contain observations from an excluded source year")
    if any(int(item.get("source_year", item.get("year"))) in EXCLUDED_SOURCE_YEARS for item in source_files):
        raise SourceError("public provenance must not include an excluded source year")
    if not records:
        raise SourceError("cannot publish a dataset with no valid observations")
    source_to_canonical, product_metadata = _product_catalog_from_records(records)
    records = _canonicalize_records(records, source_to_canonical)
    regional = _aggregate_region_records(records)
    freshness_references = _freshness_references(regional)
    regional_by_product: dict[str, list[dict[str, object]]] = {}
    for row in regional:
        regional_by_product.setdefault(str(row["product_key"]), []).append(row)

    grouped_products: dict[str, list[dict[str, object]]] = {}
    series_documents: dict[str, dict[str, object]] = {}
    for product_key, metadata in product_metadata.items():
        series_product, summary = _product_payload(
            metadata, regional_by_product[product_key], freshness_references
        )
        group_slug = str(metadata["group_slug"])
        group_products = grouped_products.setdefault(group_slug, [])
        group_products.append(summary)
        group_document = series_documents.setdefault(
            group_slug,
            {
                "schema_version": 1,
                "data_updated_at": data_updated_at,
                "group_slug": group_slug,
                "group_name": str(metadata["group_name"]),
                "products": {},
            },
        )
        group_document["products"][str(metadata["slug"])] = series_product  # type: ignore[index]

    regions_by_id: dict[int, tuple[str, str]] = {}
    point_types: dict[str, str] = {}
    for row in records:
        region_id = int(row["region_id"])
        week = str(row["week_start"])
        current = regions_by_id.get(region_id)
        if current is None or week > current[0]:
            regions_by_id[region_id] = (week, str(row["region_name"]))
        point_types[str(row["point_slug"])] = str(row["point_type"])

    groups = []
    for group_slug, products in sorted(
        grouped_products.items(), key=lambda item: str(series_documents[item[0]]["group_name"]).casefold()
    ):
        group_name = str(series_documents[group_slug]["group_name"])
        products.sort(key=lambda item: (str(item["name"]).casefold(), str(item["unit"]).casefold(), str(item["slug"])))
        groups.append(
            {
                "group_name": group_name,
                "slug": group_slug,
                "series_url": f"series/{group_slug}.json",
                "products": products,
            }
        )
    for document in series_documents.values():
        document["products"] = dict(sorted(document["products"].items()))  # type: ignore[union-attr]

    source_resources = _public_resources(source_files)
    source = {
        "dataset": str(dataset_metadata.get("name") or DATASET_ID),
        "title": str(dataset_metadata.get("title") or "Precios al Consumidor"),
        "url": str(dataset_metadata.get("url") or "https://datos.odepa.gob.cl/dataset/precios-consumidor"),
        "license": {
            "id": dataset_metadata.get("license_id"),
            "title": dataset_metadata.get("license_title"),
            "url": dataset_metadata.get("license_url"),
        },
        "attribution": str(dataset_metadata.get("author") or "Oficina de Estudios y Políticas Agrarias (ODEPA)"),
        "resources": source_resources,
        "excluded_years": _excluded_year_records(),
        "freshness_policy": {
            "max_age_days": FRESHNESS_MAX_AGE_DAYS,
            "reference": "latest_week_by_point_type_and_geography",
        },
    }
    index = {
        "schema_version": 1,
        "data_updated_at": data_updated_at,
        "source": source,
        "latest_week_start": max(str(row["week_start"]) for row in records),
        "regions": [
            {"id": region_id, "name": name}
            for region_id, (_, name) in sorted(regions_by_id.items())
        ],
        "point_types": [
            {"slug": slug, "label": label}
            for slug, label in sorted(point_types.items(), key=lambda item: item[1].casefold())
        ],
        "groups": groups,
    }
    return index, series_documents


def serialize_json(value: object) -> str:
    """Encode Decimal values as JSON numbers while preserving declared scale."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("JSON cannot contain a non-finite Decimal")
        return format(value, "f")
    if value is None or isinstance(value, (bool, int, float, str)):
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if isinstance(value, Mapping):
        items = [
            json.dumps(str(key), ensure_ascii=False) + ":" + serialize_json(item)
            for key, item in value.items()
        ]
        return "{" + ",".join(items) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(serialize_json(item) for item in value) + "]"
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def validate_index_document(index: Mapping[str, object]) -> None:
    if index.get("schema_version") != 1:
        raise SourceError("public index has an unsupported schema version")
    if not index.get("data_updated_at") or not isinstance(index.get("source"), Mapping):
        raise SourceError("public index is missing update timestamp or source metadata")
    for field in ("regions", "point_types", "groups"):
        if not isinstance(index.get(field), list):
            raise SourceError(f"public index field {field} must be an array")
    point_type_slugs = {
        str(point_type["slug"])
        for point_type in index["point_types"]
        if isinstance(point_type, Mapping) and isinstance(point_type.get("slug"), str)
    }
    source = index["source"]
    if not isinstance(source, Mapping) or not isinstance(source.get("resources"), list):
        raise SourceError("public index is missing source resource provenance")
    excluded = source.get("excluded_years")
    if not isinstance(excluded, list):
        raise SourceError("public index is missing excluded source-year disclosure")
    freshness_policy = source.get("freshness_policy")
    if (
        not isinstance(freshness_policy, Mapping)
        or freshness_policy.get("max_age_days") != FRESHNESS_MAX_AGE_DAYS
        or freshness_policy.get("reference") != "latest_week_by_point_type_and_geography"
    ):
        raise SourceError("public index is missing the supported product freshness policy")
    excluded_years: set[int] = set()
    for item in excluded:
        if not isinstance(item, Mapping) or not isinstance(item.get("reason"), str) or not item["reason"].strip():
            raise SourceError("public index contains malformed excluded source-year metadata")
        excluded_years.add(int(item["year"]))
    resource_years: set[int] = set()
    for item in source["resources"]:
        if not isinstance(item, Mapping) or "year" not in item:
            raise SourceError("public index contains malformed source resource metadata")
        year = int(item["year"])
        resource_years.add(year)
        observations = item.get("excluded_observations", [])
        if not isinstance(observations, list):
            raise SourceError("public resource excluded_observations must be an array")
        for observation in observations:
            required = {
                "year", "week_start", "product_name", "price_min_clp", "price_max_clp", "reason"
            }
            if (
                not isinstance(observation, Mapping)
                or not required <= observation.keys()
                or int(observation["year"]) != year
                or int(observation["price_min_clp"]) <= int(observation["price_max_clp"])
                or not isinstance(observation["reason"], str)
                or not observation["reason"].strip()
            ):
                raise SourceError("public index contains malformed excluded-observation provenance")
    if excluded_years & resource_years:
        raise SourceError("public source resources contain an excluded source year")
    for group in index["groups"]:
        if not isinstance(group, Mapping) or not isinstance(group.get("products"), list):
            raise SourceError("public index group products must be an array")
        for product in group["products"]:
            if not isinstance(product, Mapping) or not isinstance(product.get("name"), str):
                raise SourceError("public index contains a malformed product summary")
            aliases = product.get("aliases")
            if (
                not isinstance(aliases, list)
                or any(not isinstance(alias, str) or not alias.strip() for alias in aliases)
                or len(aliases) != len(set(aliases))
                or product["name"] in aliases
            ):
                raise SourceError("public product aliases must be unique non-empty labels")
            benchmark = product.get("benchmark")
            trends = product.get("trend_by_point_type")
            if benchmark is not None:
                ranks = benchmark.get("rank_by_point_type") if isinstance(benchmark, Mapping) else None
                if (
                    not isinstance(benchmark, Mapping)
                    or not isinstance(benchmark.get("key"), str)
                    or not isinstance(benchmark.get("label"), str)
                    or not isinstance(ranks, Mapping)
                    or not ranks
                    or any(
                        point_slug not in point_type_slugs
                        or type(rank) is not int
                        or rank < 1
                        for point_slug, rank in ranks.items()
                    )
                    or not isinstance(trends, Mapping)
                    or set(trends) != set(ranks)
                ):
                    raise SourceError("public benchmark product has invalid point ranks or compact trends")
                for point_data in trends.values():
                    if not isinstance(point_data, Mapping) or not isinstance(point_data.get("national"), list):
                        raise SourceError("public benchmark trends are malformed")
                    trend_arrays = [point_data["national"]]
                    regions = point_data.get("regions")
                    if not isinstance(regions, Mapping):
                        raise SourceError("public benchmark regional trends are malformed")
                    trend_arrays.extend(regions.values())
                    for points in trend_arrays:
                        if not isinstance(points, list) or len(points) > BENCHMARK_HISTORY_WEEKS:
                            raise SourceError("public benchmark history exceeds its supported window")
                        weeks = [str(point.get("week_start")) for point in points if isinstance(point, Mapping)]
                        if len(weeks) != len(points) or weeks != sorted(weeks) or len(weeks) != len(set(weeks)):
                            raise SourceError("public benchmark weeks must be unique and ascending")
                        if any(
                            not isinstance(point.get("average_clp"), (int, float, Decimal))
                            for point in points
                        ):
                            raise SourceError("public benchmark prices must be numeric")
            elif trends is not None:
                raise SourceError("non-benchmark product must not publish homepage trend history")


def _validate_series_document(document: Mapping[str, object]) -> None:
    if document.get("schema_version") != 1 or not document.get("data_updated_at"):
        raise SourceError("group series has an invalid schema header")
    products = document.get("products")
    if not isinstance(products, Mapping) or not products:
        raise SourceError("group series must contain products")
    for product in products.values():
        if not isinstance(product, Mapping) or not isinstance(product.get("point_types"), Mapping):
            raise SourceError("group series product has no point types")
        aliases = product.get("aliases")
        if (
            not isinstance(product.get("name"), str)
            or not isinstance(product.get("unit"), str)
            or not isinstance(aliases, list)
            or any(not isinstance(alias, str) or not alias.strip() for alias in aliases)
            or len(aliases) != len(set(aliases))
            or product["name"] in aliases
        ):
            raise SourceError("group series product has malformed aliases or identity")
        for point_type in product["point_types"].values():  # type: ignore[union-attr]
            if not isinstance(point_type, Mapping):
                raise SourceError("group series point-type data is malformed")
            arrays = [point_type.get("national")]
            regions = point_type.get("regions")
            if not isinstance(regions, Mapping):
                raise SourceError("group series regions must be an object")
            arrays.extend(regions.values())
            for points in arrays:
                if not isinstance(points, list):
                    raise SourceError("group series weekly values must be arrays")
                weeks = [str(point.get("week_start")) for point in points]
                if weeks != sorted(weeks) or len(weeks) != len(set(weeks)):
                    raise SourceError("group series weeks must be unique and ascending")
                for point in points:
                    if not isinstance(point, Mapping):
                        raise SourceError("group series contains a malformed weekly point")
                    required = {"week_start", "source_years", "average_clp", "minimum_clp", "maximum_clp", "wow_pct", "yoy_pct"}
                    if not required <= point.keys():
                        raise SourceError("group series weekly point is missing fields")
                    if int(point["minimum_clp"]) > int(point["maximum_clp"]):
                        raise SourceError("group series minimum exceeds maximum")
                    for field in ("wow_pct", "yoy_pct"):
                        if point[field] is not None and not isinstance(point[field], (int, float, Decimal)):
                            raise SourceError(f"group series {field} must be numeric or null")


def _validate_json_file(path: Path, *, is_index: bool) -> None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceError(f"generated JSON is invalid: {path.name}") from exc
    if not isinstance(document, Mapping):
        raise SourceError(f"generated JSON must be an object: {path.name}")
    if is_index:
        validate_index_document(document)
    else:
        _validate_series_document(document)


def _database_product_batches(
    connection: sqlite3.Connection, selected_years: list[int]
) -> Iterable[tuple[dict[str, object], list[dict[str, object]]]]:
    placeholders = ",".join("?" for _ in selected_years)
    source_products = [
        dict(row)
        for row in connection.execute(
            f"""
            SELECT p.product_key, p.group_name, p.product_name, p.unit,
                   MAX(h.week_start) AS latest_week_start, COUNT(*) AS observation_count
              FROM history h
              JOIN products p ON p.product_key = h.product_key
             WHERE h.source_year IN ({placeholders})
             GROUP BY p.product_key, p.group_name, p.product_name, p.unit
             ORDER BY p.product_key
            """,
            selected_years,
        )
    ]
    source_to_canonical, _ = _build_product_catalog(source_products)
    connection.execute("DROP TABLE IF EXISTS temp.public_product_map")
    connection.execute(
        """
        CREATE TEMP TABLE public_product_map (
            source_product_key TEXT PRIMARY KEY,
            product_key TEXT NOT NULL,
            group_name TEXT NOT NULL,
            group_slug TEXT NOT NULL,
            product_name TEXT NOT NULL,
            unit TEXT NOT NULL,
            product_slug TEXT NOT NULL,
            aliases_json TEXT NOT NULL
        )
        """
    )
    connection.executemany(
        """
        INSERT INTO public_product_map
            (source_product_key, product_key, group_name, group_slug, product_name,
             unit, product_slug, aliases_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                source_key,
                str(metadata["product_key"]),
                str(metadata["group_name"]),
                str(metadata["group_slug"]),
                str(metadata["product_name"]),
                str(metadata["unit"]),
                str(metadata["slug"]),
                json.dumps(metadata["aliases"], ensure_ascii=False),
            )
            for source_key, metadata in source_to_canonical.items()
        ],
    )
    conflict = connection.execute(
        f"""
        SELECT m.product_name, h.week_start, h.region_id, h.sector, h.point_type
          FROM history h
          JOIN public_product_map m ON m.source_product_key = h.product_key
         WHERE h.source_year IN ({placeholders})
         GROUP BY m.product_key, h.week_start, h.region_id, h.sector, h.point_type
        HAVING COUNT(DISTINCT h.product_key) > 1
         LIMIT 1
        """,
        selected_years,
    ).fetchone()
    if conflict:
        raise SourceError(
            f"product alias overlap for {conflict['product_name']!r} at "
            f"{conflict['week_start']} in region {conflict['region_id']}"
        )

    query = f"""
        SELECT m.product_key, m.group_name, m.group_slug, m.product_name,
               m.unit, m.product_slug, m.aliases_json,
               h.week_start, h.region_id, MIN(h.region_name) AS region_name,
               h.point_type, SUM(h.price_avg_micros) AS sum_micros,
               COUNT(*) AS sector_count, MIN(h.price_min_clp) AS minimum_clp,
               MAX(h.price_max_clp) AS maximum_clp,
               GROUP_CONCAT(DISTINCT h.source_year) AS source_years
          FROM history h
          JOIN public_product_map m ON m.source_product_key = h.product_key
         WHERE h.source_year IN ({placeholders})
         GROUP BY m.product_key, m.group_name, m.group_slug, m.product_name,
                  m.unit, m.product_slug, m.aliases_json,
                  h.week_start, h.region_id, h.point_type
         ORDER BY m.group_slug, m.group_name, m.product_name, m.unit,
                  m.product_key, h.point_type, h.week_start, h.region_id
    """
    cursor = connection.execute(query, selected_years)
    current_key: str | None = None
    metadata: dict[str, object] | None = None
    regional_rows: list[dict[str, object]] = []
    for raw in cursor:
        key = str(raw["product_key"])
        if current_key is not None and key != current_key:
            assert metadata is not None
            yield metadata, regional_rows
            regional_rows = []
            metadata = None
        if metadata is None:
            metadata = {
                "product_key": key,
                "group_name": str(raw["group_name"]),
                "group_slug": str(raw["group_slug"]),
                "product_name": str(raw["product_name"]),
                "unit": str(raw["unit"]),
                "slug": str(raw["product_slug"]),
                "aliases": json.loads(str(raw["aliases_json"])),
            }
        current_key = key
        years = sorted(int(item) for item in str(raw["source_years"]).split(",") if item)
        regional_rows.append(
            {
                **metadata,
                "week_start": str(raw["week_start"]),
                "region_id": int(raw["region_id"]),
                "region_name": str(raw["region_name"]),
                "point_type": str(raw["point_type"]),
                "point_slug": stable_slug(str(raw["point_type"]), _normalise_identity(str(raw["point_type"]))),
                "average_clp": _average_clp(int(raw["sum_micros"]), int(raw["sector_count"])),
                "minimum_clp": int(raw["minimum_clp"]),
                "maximum_clp": int(raw["maximum_clp"]),
                "source_years": years,
            }
        )
    if metadata is not None:
        yield metadata, regional_rows


def _write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_json(document) + "\n", encoding="utf-8")


def _open_group_file(path: Path, group_slug: str, group_name: str, data_updated_at: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("w", encoding="utf-8", newline="\n")
    header = {
        "schema_version": 1,
        "data_updated_at": data_updated_at,
        "group_slug": group_slug,
        "group_name": group_name,
    }
    prefix = serialize_json(header)
    stream.write(prefix[:-1] + ',"products":{')
    return stream


def _finish_group_file(stream, path: Path) -> None:
    stream.write("}}\n")
    stream.close()
    _validate_json_file(path, is_index=False)


def _database_regions(connection: sqlite3.Connection, years: list[int]) -> list[dict[str, object]]:
    placeholders = ",".join("?" for _ in years)
    query = f"""
        SELECT region_id, region_name, MAX(week_start) AS latest_week
          FROM history WHERE source_year IN ({placeholders})
         GROUP BY region_id, region_name ORDER BY latest_week DESC
    """
    names: dict[int, tuple[str, str]] = {}
    for row in connection.execute(query, years):
        region_id = int(row["region_id"])
        if region_id not in names:
            names[region_id] = (str(row["latest_week"]), str(row["region_name"]))
    return [{"id": region_id, "name": value[1]} for region_id, value in sorted(names.items())]


def _database_point_types(connection: sqlite3.Connection, years: list[int]) -> list[dict[str, str]]:
    placeholders = ",".join("?" for _ in years)
    labels: dict[str, str] = {}
    query = f"SELECT DISTINCT point_type FROM history WHERE source_year IN ({placeholders})"
    for row in connection.execute(query, years):
        label = str(row["point_type"])
        labels[stable_slug(label, _normalise_identity(label))] = label
    return [{"slug": slug, "label": label} for slug, label in sorted(labels.items(), key=lambda item: item[1].casefold())]


def _database_freshness_references(
    connection: sqlite3.Connection, years: list[int]
) -> dict[str, dict[str, object]]:
    placeholders = ",".join("?" for _ in years)
    query = f"""
        SELECT point_type, region_id, MAX(week_start) AS latest_week
          FROM history WHERE source_year IN ({placeholders})
         GROUP BY point_type, region_id
    """
    rows = (
        {
            "point_slug": stable_slug(
                str(row["point_type"]), _normalise_identity(str(row["point_type"]))
            ),
            "region_id": int(row["region_id"]),
            "week_start": str(row["latest_week"]),
        }
        for row in connection.execute(query, years)
    )
    return _freshness_references(rows)


def _stage_database_documents(
    connection: sqlite3.Connection,
    staging_dir: Path,
    source_files: list[dict[str, object]],
    dataset_metadata: Mapping[str, object],
    selected_years: list[int],
    data_updated_at: str,
) -> dict[str, object]:
    if set(selected_years) & EXCLUDED_SOURCE_YEARS.keys():
        raise SourceError("selected source years contain an excluded annual resource")
    series_dir = staging_dir / "series"
    series_dir.mkdir(parents=True, exist_ok=True)
    group_index: dict[str, dict[str, object]] = {}
    freshness_references = _database_freshness_references(connection, selected_years)
    current_group_slug: str | None = None
    current_group_name: str | None = None
    group_stream = None
    group_path: Path | None = None
    first_product_in_group = True
    product_count = 0

    def close_current_group() -> None:
        nonlocal group_stream, group_path
        if group_stream is not None and group_path is not None:
            _finish_group_file(group_stream, group_path)
            group_stream = None
            group_path = None

    for metadata, regional_rows in _database_product_batches(connection, selected_years):
        group_slug = str(metadata["group_slug"])
        group_name = str(metadata["group_name"])
        if group_slug != current_group_slug:
            close_current_group()
            current_group_slug = group_slug
            current_group_name = group_name
            group_path = series_dir / f"{group_slug}.json"
            group_stream = _open_group_file(group_path, group_slug, group_name, data_updated_at)
            first_product_in_group = True
            group_index[group_slug] = {
                "group_name": group_name,
                "slug": group_slug,
                "series_url": f"series/{group_slug}.json",
                "products": [],
            }
        product_series, product_summary = _product_payload(
            metadata, regional_rows, freshness_references
        )
        assert group_stream is not None
        if not first_product_in_group:
            group_stream.write(",")
        group_stream.write(json.dumps(str(metadata["slug"]), ensure_ascii=False) + ":" + serialize_json(product_series))
        first_product_in_group = False
        group_index[group_slug]["products"].append(product_summary)  # type: ignore[union-attr]
        product_count += 1
    close_current_group()
    if product_count == 0:
        raise SourceError("selected resources contain no valid observations")

    for group in group_index.values():
        group["products"].sort(
            key=lambda item: (str(item["name"]).casefold(), str(item["unit"]).casefold(), str(item["slug"]))
        )
    groups = sorted(group_index.values(), key=lambda item: str(item["group_name"]).casefold())
    placeholders = ",".join("?" for _ in selected_years)
    latest_row = connection.execute(
        f"SELECT MAX(week_start) AS latest FROM history WHERE source_year IN ({placeholders})", selected_years
    ).fetchone()
    if not latest_row or not latest_row["latest"]:
        raise SourceError("selected resources contain no latest observation date")

    source = {
        "dataset": str(dataset_metadata.get("name") or DATASET_ID),
        "title": str(dataset_metadata.get("title") or "Precios al Consumidor"),
        "url": str(dataset_metadata.get("url") or "https://datos.odepa.gob.cl/dataset/precios-consumidor"),
        "license": {
            "id": dataset_metadata.get("license_id"),
            "title": dataset_metadata.get("license_title"),
            "url": dataset_metadata.get("license_url"),
        },
        "attribution": str(dataset_metadata.get("author") or "Oficina de Estudios y Políticas Agrarias (ODEPA)"),
        "resources": _public_resources(source_files),
        "excluded_years": _excluded_year_records(),
        "freshness_policy": {
            "max_age_days": FRESHNESS_MAX_AGE_DAYS,
            "reference": "latest_week_by_point_type_and_geography",
        },
    }
    index = {
        "schema_version": 1,
        "data_updated_at": data_updated_at,
        "source": source,
        "latest_week_start": str(latest_row["latest"]),
        "regions": _database_regions(connection, selected_years),
        "point_types": _database_point_types(connection, selected_years),
        "groups": groups,
    }
    validate_index_document(index)
    index_path = staging_dir / "index.json"
    _write_json(index_path, index)
    _validate_json_file(index_path, is_index=True)
    return index


def publish_staged_directory(staging_dir: Path, output_dir: Path) -> list[str]:
    """Replace price documents while retaining static snapshots not built here."""
    output_dir = output_dir.resolve()
    staging_dir = staging_dir.resolve()
    ipc_snapshot = output_dir / "ipc.json"
    staged_ipc_snapshot = staging_dir / "ipc.json"
    if ipc_snapshot.is_file() and not staged_ipc_snapshot.exists():
        shutil.copy2(ipc_snapshot, staged_ipc_snapshot)

    old_files = {
        path.relative_to(output_dir).as_posix(): path.read_bytes()
        for path in output_dir.rglob("*")
        if output_dir.exists() and path.is_file()
    }
    new_files = {
        path.relative_to(staging_dir).as_posix(): path.read_bytes()
        for path in staging_dir.rglob("*")
        if path.is_file()
    }
    changed = sorted(
        filename for filename, content in new_files.items() if old_files.get(filename) != content
    )
    deleted = sorted(set(old_files) - set(new_files))
    if not changed and not deleted:
        shutil.rmtree(staging_dir)
        return []

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage_parent = output_dir.parent.parent
    backup_dir = stage_parent / f".data-backup-{uuid.uuid4().hex}"
    had_old_output = output_dir.exists()
    if had_old_output:
        os.replace(output_dir, backup_dir)
    try:
        os.replace(staging_dir, output_dir)
    except Exception:
        if had_old_output and backup_dir.exists() and not output_dir.exists():
            os.replace(backup_dir, output_dir)
        raise
    if backup_dir.exists():
        shutil.rmtree(backup_dir)

    prefix = output_dir.relative_to(ROOT).as_posix() if output_dir.is_relative_to(ROOT) else output_dir.name
    paths = [f"{prefix}/{name}" for name in changed]
    paths.extend(f"deleted: {prefix}/{name}" for name in deleted)
    return paths


def _http_bytes(url: str, timeout: int = 90) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urlopen(request, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        if status < 200 or status >= 300:
            raise SourceError(f"HTTP {status} while fetching ODEPA data")
        data = response.read()
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) != len(data):
            raise SourceError("downloaded resource length does not match Content-Length")
        if not data:
            raise SourceError("ODEPA returned an empty response")
        return data


def _http_json(url: str) -> dict[str, object]:
    try:
        payload = json.loads(_http_bytes(url).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceError(f"invalid JSON response from {url}") from exc
    if not isinstance(payload, dict):
        raise SourceError(f"JSON response from {url} is not an object")
    return payload


def fetch_datastore_records(resource: Mapping[str, object], *, page_size: int = 10_000) -> list[dict[str, object]]:
    if page_size < 1:
        raise ValueError("DataStore page_size must be positive")
    if resource.get("datastore_active") is not True:
        raise SourceError("ODEPA DataStore fallback is not active for this resource")
    resource_id = str(resource.get("resource_id") or "")
    if not resource_id:
        raise SourceError("cannot query DataStore without the dynamic resource_id")
    offset = 0
    all_records: list[dict[str, object]] = []
    total: int | None = None
    previous_page_hash: str | None = None
    while True:
        url = f"{DATASTORE_URL}?{urlencode({'resource_id': resource_id, 'limit': page_size, 'offset': offset})}"
        payload = _http_json(url)
        if payload.get("success") is not True or not isinstance(payload.get("result"), Mapping):
            raise SourceError(f"CKAN datastore_search failed at offset {offset}")
        result = payload["result"]
        page = result.get("records")
        if not isinstance(page, list):
            raise SourceError(f"CKAN datastore_search has no records at offset {offset}")
        if result.get("total") is not None:
            try:
                total = int(result["total"])
            except (TypeError, ValueError) as exc:
                raise SourceError(f"CKAN datastore_search has an invalid total at offset {offset}") from exc
            if total < 0:
                raise SourceError(f"CKAN datastore_search has an invalid total at offset {offset}")
        if not page:
            if total is not None and offset < total:
                raise SourceError(f"CKAN datastore_search returned an incomplete page at offset {offset}")
            break
        page_digest = hashlib.sha256(serialize_json(page).encode("utf-8")).hexdigest()
        if previous_page_hash == page_digest:
            raise SourceError("CKAN datastore_search repeated a page; refusing a partial import")
        previous_page_hash = page_digest
        if not all(isinstance(item, Mapping) for item in page):
            raise SourceError(f"CKAN datastore_search has malformed records at offset {offset}")
        all_records.extend(dict(item) for item in page)
        offset += len(page)
        if total is not None and offset >= total:
            break
    if not all_records:
        raise SourceError("CKAN datastore_search returned no records")
    return all_records


def _datastore_to_csv_bytes(records: list[Mapping[str, object]]) -> bytes:
    serialized = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return serialized.encode("utf-8")


def _download_resource(
    resource: Mapping[str, object],
    *,
    excluded_observations: list[dict[str, object]] | None = None,
) -> tuple[list[dict[str, object]], str]:
    url = validate_resource_url(str(resource["url"]))
    resource_context = f"resource year {resource['year']} (resource_id={resource['resource_id']})"
    try:
        raw = _http_bytes(url)
    except (OSError, TimeoutError, URLError, SourceError) as download_error:
        if resource.get("datastore_active") is not True:
            raise SourceError(f"could not download resource year {resource['year']}: {download_error}") from download_error
        LOG.warning("CSV download failed for year %s; using complete CKAN DataStore fallback", resource["year"])
        try:
            raw_records = fetch_datastore_records(resource)
            records = parse_source_records(
                raw_records,
                int(resource["year"]),
                excluded_observations=excluded_observations,
            )
        except SourceError as exc:
            raise SourceError(f"{resource_context} failed CKAN DataStore validation: {exc}") from exc
        serialized = _datastore_to_csv_bytes(raw_records)
        return records, hashlib.sha256(serialized).hexdigest()
    try:
        records = parse_csv_bytes(
            raw,
            int(resource["year"]),
            excluded_observations=excluded_observations,
        )
    except SourceError as exc:
        raise SourceError(f"{resource_context} failed CSV validation: {exc}") from exc
    return records, hashlib.sha256(raw).hexdigest()


def _resource_changed(resource: Mapping[str, object], existing: Mapping[str, object] | None, connection: sqlite3.Connection) -> bool:
    if existing is None:
        return True
    year = int(resource["year"])
    row_count = connection.execute("SELECT COUNT(*) FROM history WHERE source_year = ?", (year,)).fetchone()[0]
    if int(row_count) != int(existing["row_count"]):
        return True
    current_id = str(resource["resource_id"])
    current_url = str(resource["url"])
    current_hash = str(resource.get("hash") or "") or None
    current_modified = str(resource.get("last_modified") or "") or None
    if (
        str(existing["resource_id"]) != current_id
        or str(existing["source_url"]) != current_url
        or existing["remote_hash"] != current_hash
        or existing["last_modified"] != current_modified
    ):
        return True
    if current_hash is None and current_modified is None:
        return True
    return False


def replace_year(
    connection: sqlite3.Connection,
    resource: Mapping[str, object],
    records: list[dict[str, object]],
    download_sha256: str,
    *,
    excluded_observations: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Replace one fully staged year in a single SQLite transaction."""
    if not records:
        raise SourceError(f"resource year {resource['year']} contains no accepted observations")
    year = int(resource["year"])
    latest = max(str(record["week_start"]) for record in records)
    source_url = validate_resource_url(str(resource["url"]))
    imported_at = _utc_now_iso()
    exclusions_json = json.dumps(
        excluded_observations or [], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    try:
        with connection:
            connection.execute("DELETE FROM history WHERE source_year = ?", (year,))
            connection.execute(
                """INSERT INTO source_files
                   (source_year, resource_id, source_url, remote_hash, download_sha256,
                    last_modified, imported_at, row_count, latest_week_start, excluded_observations_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source_year) DO UPDATE SET
                     resource_id=excluded.resource_id, source_url=excluded.source_url,
                     remote_hash=excluded.remote_hash, download_sha256=excluded.download_sha256,
                     last_modified=excluded.last_modified, imported_at=excluded.imported_at,
                     row_count=excluded.row_count, latest_week_start=excluded.latest_week_start,
                     excluded_observations_json=excluded.excluded_observations_json""",
                (
                    year,
                    str(resource["resource_id"]),
                    source_url,
                    resource.get("hash") or None,
                    download_sha256,
                    resource.get("last_modified") or None,
                    imported_at,
                    len(records),
                    latest,
                    exclusions_json,
                ),
            )
            connection.executemany(
                """INSERT INTO products
                   (product_key, group_name, group_slug, product_name, unit, slug)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(product_key) DO UPDATE SET
                     group_name=excluded.group_name, group_slug=excluded.group_slug,
                     product_name=excluded.product_name, unit=excluded.unit, slug=excluded.slug""",
                [
                    (
                        row["product_key"],
                        row["group_name"],
                        row["group_slug"],
                        row["product_name"],
                        row["unit"],
                        row["slug"],
                    )
                    for row in records
                ],
            )
            connection.executemany(
                """INSERT INTO history
                   (week_start, week_end, product_key, region_id, region_name, sector,
                    point_type, price_min_clp, price_max_clp, price_avg_micros, source_year)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        row["week_start"],
                        row["week_end"],
                        row["product_key"],
                        row["region_id"],
                        row["region_name"],
                        row["sector"],
                        row["point_type"],
                        row["price_min_clp"],
                        row["price_max_clp"],
                        row["price_avg_micros"],
                        year,
                    )
                    for row in records
                ],
            )
    except sqlite3.IntegrityError as exc:
        raise SourceError(f"SQLite rejected staged resource year {year}: {exc}") from exc
    return {
        "source_year": year,
        "resource_id": str(resource["resource_id"]),
        "source_url": source_url,
        "remote_hash": resource.get("hash") or None,
        "download_sha256": download_sha256,
        "last_modified": resource.get("last_modified") or None,
        "row_count": len(records),
        "latest_week_start": latest,
        "excluded_observations_json": exclusions_json,
    }


def _source_file_rows(connection: sqlite3.Connection, years: list[int]) -> list[dict[str, object]]:
    placeholders = ",".join("?" for _ in years)
    return [dict(row) for row in connection.execute(
        f"SELECT * FROM source_files WHERE source_year IN ({placeholders}) ORDER BY source_year", years
    )]


def _purge_excluded_source_years(connection: sqlite3.Connection) -> list[int]:
    """Remove previously cached partitions that are no longer in product scope."""
    purged: list[int] = []
    with connection:
        for year in sorted(EXCLUDED_SOURCE_YEARS):
            has_source = connection.execute(
                "SELECT 1 FROM source_files WHERE source_year = ?", (year,)
            ).fetchone()
            has_history = connection.execute(
                "SELECT 1 FROM history WHERE source_year = ? LIMIT 1", (year,)
            ).fetchone()
            if not has_source and not has_history:
                continue
            connection.execute("DELETE FROM history WHERE source_year = ?", (year,))
            connection.execute("DELETE FROM source_files WHERE source_year = ?", (year,))
            purged.append(year)
        connection.execute(
            "DELETE FROM products WHERE NOT EXISTS "
            "(SELECT 1 FROM history WHERE history.product_key = products.product_key)"
        )
    return purged


def _load_previous_index(output_dir: Path) -> dict[str, object] | None:
    try:
        value = json.loads((output_dir / "index.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def run_refresh(
    *,
    db_path: Path | str = DEFAULT_DB,
    output_dir: Path | str = DEFAULT_OUTPUT,
    full_refresh: bool = False,
    summary_file: Path | str | None = None,
    current_year: int | None = None,
) -> dict[str, object]:
    db_path = Path(db_path)
    output_dir = Path(output_dir)
    init_db(db_path)
    previous_index = _load_previous_index(output_dir)
    payload = _http_json(METADATA_URL)
    dataset = parse_package_show(payload)
    resources = select_annual_resources(dataset, current_year=current_year)
    current_year = current_year or date.today().year
    selected_years = [int(resource["year"]) for resource in resources]
    fallback_year = None if current_year in selected_years else max(selected_years)
    imported_years: list[int] = []
    skipped_years: list[int] = []

    with closing(connect_db(db_path)) as connection:
        for resource in resources:
            existing_row = connection.execute(
                "SELECT * FROM source_files WHERE source_year = ?", (resource["year"],)
            ).fetchone()
            existing = dict(existing_row) if existing_row else None
            changed = full_refresh or _resource_changed(resource, existing, connection)
            if not changed:
                LOG.info("year %s unchanged; skipping download", resource["year"])
                skipped_years.append(int(resource["year"]))
                continue
            excluded_observations: list[dict[str, object]] = []
            records, source_sha = _download_resource(
                resource, excluded_observations=excluded_observations
            )
            replaced = replace_year(
                connection,
                resource,
                records,
                source_sha,
                excluded_observations=excluded_observations,
            )
            excluded_details = json.loads(str(replaced["excluded_observations_json"]))
            LOG.info(
                "imported year=%s resource_id=%s remote_hash=%s sha256=%s rows=%s latest_week=%s excluded_observations=%s",
                replaced["source_year"],
                replaced["resource_id"],
                resource.get("hash") or "(none)",
                replaced["download_sha256"],
                replaced["row_count"],
                replaced["latest_week_start"],
                [item["product_name"] for item in excluded_details],
            )
            imported_years.append(int(resource["year"]))

        purged_years = _purge_excluded_source_years(connection)
        if purged_years:
            LOG.info("purged excluded cached source years=%s", purged_years)

        source_files = _source_file_rows(connection, selected_years)
        if len(source_files) != len(resources):
            raise SourceError("not every selected annual resource has a validated SQLite record")
        data_updated_at = resolve_data_updated_at(previous_index, source_files)
        staging_parent = output_dir.resolve().parent.parent
        staging_parent.mkdir(parents=True, exist_ok=True)
        staging_dir = Path(tempfile.mkdtemp(prefix=".data-stage-", dir=staging_parent))
        try:
            index = _stage_database_documents(
                connection,
                staging_dir,
                source_files,
                dataset,
                selected_years,
                data_updated_at,
            )
            changed_files = publish_staged_directory(staging_dir, output_dir)
        except Exception:
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
            raise
        accepted_rows = sum(int(source["row_count"]) for source in source_files)
        summary = {
            "dataset": DATASET_ID,
            "source_years": selected_years,
            "fallback_year": fallback_year,
            "imported_years": imported_years,
            "unchanged_years": skipped_years,
            "excluded_source_years": sorted(EXCLUDED_SOURCE_YEARS),
            "excluded_observations": sum(
                len(json.loads(str(source.get("excluded_observations_json") or "[]")))
                for source in source_files
            ),
            "latest_week_start": index["latest_week_start"],
            "accepted_rows": accepted_rows,
            "changed_files": changed_files,
            "data_updated_at": data_updated_at,
        }

    if summary_file:
        summary_path = Path(summary_file)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite cache path (default: data/prices.db)")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT, help="public JSON directory (default: site/data)")
    parser.add_argument("--full-refresh", action="store_true", help="redownload and rebuild every selected annual resource")
    parser.add_argument("--summary-file", type=Path, help="write machine-readable refresh summary to this path")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        summary = run_refresh(
            db_path=args.db,
            output_dir=args.output_dir,
            full_refresh=args.full_refresh,
            summary_file=args.summary_file,
        )
    except (SourceError, OSError, sqlite3.Error, ValueError) as exc:
        LOG.error("refresh failed: %s", exc)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
