import csv
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from pipeline.fetch_odepa import (
    SourceError,
    _stage_database_documents,
    _download_resource,
    connect_db,
    fetch_datastore_records,
    init_db,
    parse_csv_bytes,
    replace_year,
    run_refresh,
    select_annual_resources,
    validate_resource_url,
)


FIXTURE = Path(__file__).parent / "fixtures" / "odepa-small.csv"


class ResourceSelectionTests(unittest.TestCase):
    def test_selects_active_annual_csv_resources_dynamically(self):
        metadata = {
            "resources": [
                self.resource(2016, "old"),
                self.resource(2017, "resource-2017"),
                self.resource(2019, "excluded-resource-2019"),
                self.resource(2025, "resource-2025"),
                self.resource(2026, "resource-2026"),
                {**self.resource(2024, "inactive"), "state": "deleted"},
                {**self.resource(2023, "json"), "format": "JSON"},
                {key: value for key, value in self.resource(2022, "unknown-state").items() if key != "state"},
            ]
        }

        selected = select_annual_resources(metadata, current_year=2026)

        self.assertEqual([item["year"] for item in selected], [2017, 2025, 2026])
        self.assertEqual([item["resource_id"] for item in selected], ["resource-2017", "resource-2025", "resource-2026"])

    def test_uses_latest_available_year_when_current_year_is_absent(self):
        selected = select_annual_resources(
            {"resources": [self.resource(2024, "a"), self.resource(2025, "b")]},
            current_year=2026,
        )
        self.assertEqual([item["year"] for item in selected], [2024, 2025])

    def test_excludes_2019_even_when_it_is_an_active_csv_resource(self):
        selected = select_annual_resources(
            {"resources": [self.resource(2018, "a"), self.resource(2019, "blocked"), self.resource(2020, "b")]},
            current_year=2020,
        )
        self.assertEqual([item["year"] for item in selected], [2018, 2020])

    def test_rejects_ambiguous_active_resources_for_one_year(self):
        with self.assertRaisesRegex(SourceError, "ambiguous"):
            select_annual_resources(
                {"resources": [self.resource(2025, "a"), self.resource(2025, "b")]},
                current_year=2025,
            )

    def test_requires_https_odepa_resource_url(self):
        validate_resource_url("https://datos.odepa.gob.cl/files/price.csv")
        with self.assertRaises(SourceError):
            validate_resource_url("http://datos.odepa.gob.cl/files/price.csv")
        with self.assertRaises(SourceError):
            validate_resource_url("https://example.com/price.csv")

    @staticmethod
    def resource(year, resource_id):
        return {
            "resource_id": resource_id,
            "name": f"Detalle de Precios Consumidor año {year}",
            "format": "CSV",
            "state": "active",
            "url": f"https://datos.odepa.gob.cl/download/{resource_id}.csv",
            "hash": f"hash-{year}",
            "last_modified": f"{year}-02-01T00:00:00Z",
            "datastore_active": False,
        }


class CsvParsingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = FIXTURE.read_bytes()

    def test_parses_decimal_comma_and_deduplicates_exact_keys(self):
        records = parse_csv_bytes(self.raw, resource_year=2025)
        self.assertEqual(len(records), 12)
        apple = next(row for row in records if row["week_start"] == "2025-01-20")
        self.assertEqual(apple["price_avg_micros"], 1_000_000_000)
        self.assertEqual(apple["product_name"], "Manzana|Royal|Primera")
        self.assertEqual(apple["week_end"], "2025-01-24")

    def test_accepts_utf8_bom_and_normalizes_accented_headers(self):
        raw = self.raw.decode("utf-8").replace("Precio promedio", "  PRECIO PROMÉDIO  ", 1)
        records = parse_csv_bytes(("\ufeff" + raw).encode("utf-8"), resource_year=2025)
        self.assertEqual(len(records), 12)

    def test_rejects_resource_year_mismatch(self):
        raw = self.raw.replace(b"2025,1,2,2025-01-06", b"2024,1,2,2025-01-06", 1)
        with self.assertRaisesRegex(SourceError, "resource year"):
            parse_csv_bytes(raw, resource_year=2025)

    def test_rejects_conflicting_duplicate_primary_key(self):
        rows = list(csv.DictReader(io.StringIO(self.raw.decode("utf-8"))))
        conflicting = dict(rows[0])
        conflicting["Precio promedio"] = "981,000000"
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows([*rows, conflicting])
        with self.assertRaisesRegex(SourceError, "conflicting duplicate"):
            parse_csv_bytes(stream.getvalue().encode("utf-8"), resource_year=2025)

    def test_rejects_malformed_required_price_instead_of_coercing_to_zero(self):
        raw = self.raw.replace(b'"980,000000"', b'"no-es-precio"', 1)
        with self.assertRaisesRegex(SourceError, "price"):
            parse_csv_bytes(raw, resource_year=2025)

    def test_rejects_minimum_greater_than_maximum_with_source_context(self):
        raw = self.raw.replace(b",900,1100,", b",1200,1100,", 1)
        with self.assertRaises(SourceError) as raised:
            parse_csv_bytes(raw, resource_year=2025)

        message = str(raised.exception)
        for detail in (
            "row 2",
            "minimum=1200, maximum=1100",
            "product='Manzana|Royal|Primera'",
            "week_start=2025-01-06",
            "region='Metropolitana'",
            "sector='Centro'",
            "point_type='Supermercado'",
        ):
            with self.subTest(detail=detail):
                self.assertIn(detail, message)

    def test_preserves_source_average_even_when_it_exceeds_reported_maximum(self):
        raw = self.raw.replace(b'"980,000000"', b'"1.200,000000"', 1)
        records = parse_csv_bytes(raw, resource_year=2025)
        first_week = next(row for row in records if row["week_start"] == "2025-01-06")
        self.assertEqual(first_week["price_max_clp"], 1100)
        self.assertEqual(first_week["price_avg_micros"], 1_200_000_000)

    def test_omits_only_the_two_confirmed_invalid_2021_observations(self):
        rows = [
            self.invalid_2021_row("Huevo blanco - Segunda", "1,140000"),
            self.invalid_2021_row("Huevo color - Segunda", "1,800000"),
            self.invalid_2021_row("Huevo blanco - Primera", "1.100,000000", minimum="980", maximum="1200"),
        ]
        raw = self.csv_bytes(rows)
        omitted = []

        records = parse_csv_bytes(raw, resource_year=2021, excluded_observations=omitted)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["product_name"], "Huevo blanco - Primera")
        self.assertEqual(len(omitted), 2)
        self.assertEqual([item["product_name"] for item in omitted], [
            "Huevo blanco - Segunda", "Huevo color - Segunda"
        ])
        self.assertTrue(all(item["price_min_clp"] == 980 and item["price_max_clp"] == 2 for item in omitted))
        self.assertEqual({item["week_start"] for item in omitted}, {"2021-11-22"})

    def test_does_not_omit_a_different_invalid_2021_observation(self):
        target = self.invalid_2021_row("Huevo blanco - Segunda", "1,140000", maximum="3")
        with self.assertRaisesRegex(SourceError, "price values are outside the allowed range"):
            parse_csv_bytes(self.csv_bytes([target]), resource_year=2021)

    def test_rejects_duplicate_allowlisted_observation_instead_of_hiding_extra_rows(self):
        target = self.invalid_2021_row("Huevo blanco - Segunda", "1,140000")
        with self.assertRaisesRegex(SourceError, "duplicate allowlisted"):
            parse_csv_bytes(self.csv_bytes([target, target]), resource_year=2021)

    @staticmethod
    def invalid_2021_row(product, average, *, minimum="980", maximum="2"):
        return {
            "Anio": "2021",
            "Semana": "47",
            "Fecha inicio": "2021-11-22",
            "Fecha termino": "2021-11-26",
            "ID region": "9",
            "Region": "Región de La Araucanía",
            "Sector": "Barrio Inglés - Estadio",
            "Tipo de punto monitoreo": "Mercado Minorista",
            "Grupo": "Lácteos - Huevos - Margarinas",
            "Producto": product,
            "Unidad": "$/bandeja 12 unidades",
            "Precio minimo": minimum,
            "Precio maximo": maximum,
            "Precio promedio": average,
        }

    @staticmethod
    def csv_bytes(rows):
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        return stream.getvalue().encode("utf-8")

    def test_persists_exclusions_with_resource_provenance_and_publishes_them(self):
        rows = [
            self.invalid_2021_row("Huevo blanco - Segunda", "1,140000"),
            self.invalid_2021_row("Huevo color - Segunda", "1,800000"),
            self.invalid_2021_row("Huevo blanco - Primera", "1.100,000000", minimum="980", maximum="1200"),
        ]
        omitted = []
        records = parse_csv_bytes(self.csv_bytes(rows), 2021, excluded_observations=omitted)
        resource = {
            "year": 2021,
            "resource_id": "confirmed-2021",
            "url": "https://datos.odepa.gob.cl/download/2021.csv",
            "hash": "source-hash",
            "last_modified": "2026-09-18T12:45:14Z",
        }

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "prices.db"
            init_db(db_path)
            with closing(connect_db(db_path)) as connection:
                replace_year(connection, resource, records, "a" * 64, excluded_observations=omitted)
                persisted = connection.execute(
                    "SELECT excluded_observations_json FROM source_files WHERE source_year = 2021"
                ).fetchone()[0]
                self.assertEqual(json.loads(persisted), omitted)
                staged = root / "staged"
                staged.mkdir()
                index = _stage_database_documents(
                    connection,
                    staged,
                    [dict(resource, source_year=2021, source_url=resource["url"], download_sha256="a" * 64,
                         remote_hash=resource["hash"], row_count=len(records), latest_week_start="2021-11-22",
                         excluded_observations_json=persisted)],
                    {"name": "precios-consumidor"},
                    [2021],
                    "2026-09-22T00:00:00Z",
                )
                public_exclusions = index["source"]["resources"][0]["excluded_observations"]
                self.assertEqual(len(public_exclusions), 2)
                self.assertEqual(public_exclusions[0]["price_max_clp"], 2)


class DataStoreFallbackTests(unittest.TestCase):
    def test_invalid_csv_error_identifies_the_dynamic_source_resource(self):
        resource = ResourceSelectionTests.resource(2025, "dynamic-invalid-resource")
        resource["year"] = 2025
        invalid = FIXTURE.read_bytes().replace(b",900,1100,", b",1200,1100,", 1)

        with patch("pipeline.fetch_odepa._http_bytes", return_value=invalid):
            with self.assertRaises(SourceError) as raised:
                _download_resource(resource)

        message = str(raised.exception)
        self.assertIn("resource year 2025", message)
        self.assertIn("resource_id=dynamic-invalid-resource", message)
        self.assertIn("product='Manzana|Royal|Primera'", message)

    def test_csv_failure_uses_active_datastore_records_with_the_same_parser(self):
        rows = list(csv.DictReader(io.StringIO(FIXTURE.read_text(encoding="utf-8"))))
        resource = {
            "year": 2025,
            "resource_id": "dynamic-id-17",
            "url": "https://datos.odepa.gob.cl/download/source.csv",
            "datastore_active": True,
        }
        with patch("pipeline.fetch_odepa._http_bytes", side_effect=OSError("offline")):
            with patch("pipeline.fetch_odepa.fetch_datastore_records", return_value=rows) as fallback:
                records, digest = _download_resource(resource)
        self.assertEqual(len(records), 12)
        self.assertEqual(len(digest), 64)
        fallback.assert_called_once_with(resource)

    def test_csv_failure_does_not_use_datastore_when_inactive(self):
        resource = {
            "year": 2025,
            "resource_id": "dynamic-id-17",
            "url": "https://datos.odepa.gob.cl/download/source.csv",
            "datastore_active": False,
        }
        with patch("pipeline.fetch_odepa._http_bytes", side_effect=OSError("offline")):
            with patch("pipeline.fetch_odepa.fetch_datastore_records") as fallback:
                with self.assertRaisesRegex(SourceError, "could not download"):
                    _download_resource(resource)
        fallback.assert_not_called()

    def test_fetches_all_pages_using_the_dynamic_resource_id(self):
        pages = [
            {"success": True, "result": {"records": [{"id": "a"}, {"id": "b"}], "total": 3}},
            {"success": True, "result": {"records": [{"id": "c"}], "total": 3}},
        ]
        resource = {"resource_id": "dynamic-id-17", "datastore_active": True}
        with patch("pipeline.fetch_odepa._http_json", side_effect=pages) as request:
            records = fetch_datastore_records(resource, page_size=2)

        self.assertEqual([row["id"] for row in records], ["a", "b", "c"])
        requested = [parse_qs(urlparse(call.args[0]).query) for call in request.call_args_list]
        self.assertEqual([params["resource_id"][0] for params in requested], ["dynamic-id-17"] * 2)
        self.assertEqual([params["offset"][0] for params in requested], ["0", "2"])

    def test_rejects_a_repeated_page_instead_of_accepting_a_partial_import(self):
        repeated = {"success": True, "result": {"records": [{"id": "same"}], "total": 3}}
        with patch("pipeline.fetch_odepa._http_json", side_effect=[repeated, repeated]):
            with self.assertRaisesRegex(SourceError, "repeated a page"):
                fetch_datastore_records(
                    {"resource_id": "dynamic-id-17", "datastore_active": True},
                    page_size=1,
                )

    def test_short_page_continues_when_ckan_reports_more_records(self):
        pages = [
            {"success": True, "result": {"records": [{"id": "a"}], "total": 2}},
            {"success": True, "result": {"records": [{"id": "b"}], "total": 2}},
        ]
        with patch("pipeline.fetch_odepa._http_json", side_effect=pages) as request:
            records = fetch_datastore_records(
                {"resource_id": "dynamic-id-17", "datastore_active": True},
                page_size=10,
            )
        self.assertEqual([row["id"] for row in records], ["a", "b"])
        self.assertEqual(request.call_count, 2)

    def test_rejects_an_empty_page_before_the_reported_total(self):
        pages = [
            {"success": True, "result": {"records": [{"id": "a"}], "total": 2}},
            {"success": True, "result": {"records": [], "total": 2}},
        ]
        with patch("pipeline.fetch_odepa._http_json", side_effect=pages):
            with self.assertRaisesRegex(SourceError, "incomplete page"):
                fetch_datastore_records(
                    {"resource_id": "dynamic-id-17", "datastore_active": True},
                    page_size=10,
                )

    def test_rejects_datastore_when_metadata_does_not_enable_it(self):
        with self.assertRaisesRegex(SourceError, "not active"):
            fetch_datastore_records({"resource_id": "dynamic-id-17", "datastore_active": False})


class RefreshOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "data" / "prices.db"
        self.output = self.root / "site" / "data"
        self.raw = FIXTURE.read_bytes()
        self.resource = {
            "resource_id": "current-resource-2025",
            "name": "Precios consumidor 2025",
            "description": "",
            "format": "CSV",
            "state": "active",
            "url": "https://datos.odepa.gob.cl/download/current-resource-2025.csv",
            "hash": "remote-v1",
            "last_modified": "2025-03-01T00:00:00Z",
            "datastore_active": False,
        }
        self.dataset_payload = {
            "success": True,
            "result": {
                "name": "precios-consumidor",
                "title": "Precios al Consumidor",
                "state": "active",
                "url": "https://datos.odepa.gob.cl/dataset/precios-consumidor",
                "license_id": "cc-by",
                "license_title": "Creative Commons Attribution",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "author": "Oficina de Estudios y Políticas Agrarias",
                "resources": [self.resource],
            },
        }

    def tearDown(self):
        self.temp.cleanup()

    def refresh(self, *, full_refresh=False, raw=None):
        staged_raw = self.raw if raw is None else raw
        with patch("pipeline.fetch_odepa._http_json", return_value=self.dataset_payload):
            with patch(
                "pipeline.fetch_odepa._download_resource",
                return_value=(parse_csv_bytes(staged_raw, 2025), hashlib.sha256(staged_raw).hexdigest()),
            ) as download:
                result = run_refresh(
                    db_path=self.db_path,
                    output_dir=self.output,
                    full_refresh=full_refresh,
                    current_year=2025,
                )
        return result, download

    def test_cache_miss_builds_complete_publication_then_noop_skips_download(self):
        initial, initial_download = self.refresh()
        self.assertEqual(initial["imported_years"], [2025])
        self.assertEqual(initial["accepted_rows"], 12)
        self.assertTrue((self.output / "index.json").is_file())
        self.assertEqual(initial_download.call_count, 1)
        original_index = (self.output / "index.json").read_bytes()

        repeated, repeated_download = self.refresh()
        self.assertEqual(repeated["unchanged_years"], [2025])
        self.assertEqual(repeated["changed_files"], [])
        self.assertEqual(repeated["data_updated_at"], initial["data_updated_at"])
        self.assertEqual(repeated_download.call_count, 0)
        self.assertEqual((self.output / "index.json").read_bytes(), original_index)

    def test_refresh_omits_and_purges_cached_2019_and_discloses_the_exclusion(self):
        excluded_resource = ResourceSelectionTests.resource(2019, "excluded-resource-2019")
        excluded_resource.update(
            url="https://datos.odepa.gob.cl/download/excluded-resource-2019.csv",
            hash="excluded-2019",
            last_modified="2026-03-25T00:00:00Z",
            datastore_active=True,
        )
        excluded_raw = self.raw.replace(b"2025,", b"2019,")
        excluded_records = parse_csv_bytes(excluded_raw, 2019)
        for week_offset, record in enumerate(excluded_records):
            record["week_start"] = (date(2019, 1, 7) + timedelta(weeks=week_offset)).isoformat()
            record["week_end"] = (date(2019, 1, 11) + timedelta(weeks=week_offset)).isoformat()
        init_db(self.db_path)
        with closing(connect_db(self.db_path)) as connection:
            replace_year(
                connection,
                {**excluded_resource, "year": 2019},
                excluded_records,
                hashlib.sha256(excluded_raw).hexdigest(),
            )

        self.dataset_payload["result"]["resources"] = [excluded_resource, self.resource]
        result, download = self.refresh()

        self.assertEqual(result["source_years"], [2025])
        self.assertEqual(result["excluded_source_years"], [2019])
        self.assertEqual(download.call_count, 1)
        with closing(connect_db(self.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM history WHERE source_year=2019").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM source_files WHERE source_year=2019").fetchone()[0], 0)
        index = json.loads((self.output / "index.json").read_text(encoding="utf-8"))
        self.assertEqual([item["year"] for item in index["source"]["resources"]], [2025])
        self.assertEqual([item["year"] for item in index["source"]["excluded_years"]], [2019])

    def test_changed_resource_replaces_year_without_duplicate_rows(self):
        self.refresh()
        previous_index = (self.output / "index.json").read_bytes()
        self.resource["hash"] = "remote-v2"
        changed_bytes = self.raw.replace(b'"1.000,000000"', b'"1.050,000000"')

        changed, download = self.refresh(raw=changed_bytes)

        self.assertEqual(self.resource["hash"], "remote-v2")
        self.assertEqual(changed["imported_years"], [2025])
        self.assertEqual(download.call_count, 1)
        with closing(connect_db(self.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM history WHERE source_year=2025").fetchone()[0], 12)
            self.assertEqual(connection.execute("SELECT remote_hash FROM source_files WHERE source_year=2025").fetchone()[0], "remote-v2")
        self.assertNotEqual((self.output / "index.json").read_bytes(), previous_index)

    def test_invalid_changed_source_keeps_database_and_publication_unchanged(self):
        self.refresh()
        before_index = (self.output / "index.json").read_bytes()
        self.resource["hash"] = "remote-invalid"
        with patch("pipeline.fetch_odepa._http_json", return_value=self.dataset_payload):
            with patch("pipeline.fetch_odepa._download_resource", side_effect=SourceError("invalid required source field")):
                with self.assertRaisesRegex(SourceError, "invalid required"):
                    run_refresh(db_path=self.db_path, output_dir=self.output, current_year=2025)

        self.assertEqual((self.output / "index.json").read_bytes(), before_index)
        with closing(connect_db(self.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT remote_hash FROM source_files WHERE source_year=2025").fetchone()[0], "remote-v1")
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM history WHERE source_year=2025").fetchone()[0], 12)

    def test_sqlite_constraint_failure_rolls_back_the_entire_year_replacement(self):
        records = parse_csv_bytes(self.raw, 2025)
        init_db(self.db_path)
        with closing(connect_db(self.db_path)) as connection:
            original_resource = dict(self.resource, year=2025)
            replace_year(connection, original_resource, records, "a" * 64)
            broken = [dict(record) for record in records]
            broken.append(dict(broken[0], price_min_clp=broken[0]["price_min_clp"] + 1))
            updated_resource = dict(original_resource, hash="remote-v2")
            with self.assertRaisesRegex(SourceError, "SQLite rejected staged resource year"):
                replace_year(connection, updated_resource, broken, "b" * 64)

        with closing(connect_db(self.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT remote_hash FROM source_files WHERE source_year=2025").fetchone()[0], "remote-v1")
            self.assertEqual(connection.execute("SELECT download_sha256 FROM source_files WHERE source_year=2025").fetchone()[0], "a" * 64)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM history WHERE source_year=2025").fetchone()[0], 12)

    def test_full_refresh_redownloads_an_unchanged_resource(self):
        self.refresh()
        _, download = self.refresh(full_refresh=True)
        self.assertEqual(download.call_count, 1)


if __name__ == "__main__":
    unittest.main()
