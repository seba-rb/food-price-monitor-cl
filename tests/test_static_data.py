import json
import tempfile
import unittest
from pathlib import Path

from pipeline.fetch_odepa import (
    BENCHMARK_POINT_SLUGS,
    BENCHMARK_PRODUCTS,
    SourceError,
    _stage_database_documents,
    _validate_series_document,
    build_public_documents,
    connect_db,
    init_db,
    parse_csv_bytes,
    publish_staged_directory,
    replace_year,
    resolve_data_updated_at,
    serialize_json,
    validate_index_document,
)


FIXTURE = Path(__file__).parent / "fixtures" / "odepa-small.csv"
SOURCES = [
    {
        "source_year": 2025,
        "resource_id": "fixture-resource-2025",
        "source_url": "https://datos.odepa.gob.cl/download/fixture-2025.csv",
        "remote_hash": "remote-2025",
        "download_sha256": "a" * 64,
        "last_modified": "2025-03-01T00:00:00Z",
        "row_count": 12,
        "latest_week_start": "2025-02-24",
    }
]
DATASET = {
    "name": "precios-consumidor",
    "title": "Precios al Consumidor",
    "url": "https://datos.odepa.gob.cl/dataset/precios-consumidor",
    "license_id": "cc-by",
    "license_title": "Creative Commons Attribution",
    "license_url": "https://creativecommons.org/licenses/by/4.0/",
    "author": "Oficina de Estudios y Políticas Agrarias",
}


class PublicDataContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = parse_csv_bytes(FIXTURE.read_bytes(), resource_year=2025)
        cls.index, cls.series = build_public_documents(
            cls.records,
            SOURCES,
            DATASET,
            data_updated_at="2025-03-01T00:00:00Z",
        )
        cls.supermarket_slug = next(
            item["slug"] for item in cls.index["point_types"] if item["label"] == "Supermercado"
        )

    def test_index_schema_provenance_and_region_scope_are_public(self):
        self.assertEqual(self.index["schema_version"], 1)
        self.assertEqual(self.index["data_updated_at"], "2025-03-01T00:00:00Z")
        self.assertEqual(self.index["source"]["resources"][0]["download_sha256"], "a" * 64)
        self.assertEqual(self.index["source"]["resources"][0]["year"], 2025)
        self.assertEqual([item["year"] for item in self.index["source"]["excluded_years"]], [2019])
        self.assertTrue(self.index["source"]["excluded_years"][0]["reason"])
        self.assertIn({"id": 13, "name": "Metropolitana"}, self.index["regions"])
        self.assertIn({"slug": self.supermarket_slug, "label": "Supermercado"}, self.index["point_types"])
        self.assertEqual(self.index["latest_week_start"], "2025-02-24")

    def test_product_summary_has_precomputed_national_and_region_values(self):
        group = next(item for item in self.index["groups"] if item["group_name"] == "Frutas")
        product = next(item for item in group["products"] if item["name"] == "Manzana|Royal|Primera")
        summaries = product["latest_by_point_type"]
        feria_slug = next(
            item["slug"] for item in self.index["point_types"] if item["label"] == "Feria"
        )
        self.assertEqual(set(summaries), {self.supermarket_slug, feria_slug})
        summary = summaries[self.supermarket_slug]
        self.assertEqual(summary["national"]["average_clp"], 1550)
        series = self.series[group["slug"]]["products"][product["slug"]]["point_types"][self.supermarket_slug]["national"]
        self.assertEqual(summary["national"]["previous_week_start"], series[-2]["week_start"])
        self.assertEqual(summary["national"]["previous_average_clp"], series[-2]["average_clp"])
        self.assertEqual(summary["regions"]["13"]["average_clp"], 1100)
        self.assertEqual(summary["national"]["source_years"], [2025])
        self.assertIsNone(summary["national"]["yoy_pct"])
        self.assertEqual(summaries[feria_slug]["national"]["average_clp"], 950)

    def test_homepage_benchmarks_publish_compact_trends_for_configured_scopes(self):
        records = [dict(record) for record in self.records]
        for record in self.records:
            if record["product_name"] != "Manzana|Royal|Primera":
                continue
            rice = dict(record)
            rice.update(
                product_key="benchmark-rice",
                group_name="Abarrotes y otros",
                product_name="Arroz grano ancho grado 1",
                unit="$/kilo",
            )
            records.append(rice)

        index, series_documents = build_public_documents(
            records, SOURCES, DATASET, data_updated_at="2025-03-01T00:00:00Z"
        )
        group = next(item for item in index["groups"] if item["group_name"] == "Abarrotes y otros")
        product = next(item for item in group["products"] if item["name"] == "Arroz grano ancho grado 1")
        self.assertEqual(product["benchmark"]["key"], "rice")
        self.assertEqual(product["benchmark"]["label"], "Arroz")
        self.assertEqual(product["benchmark"]["rank_by_point_type"][self.supermarket_slug], 1)
        self.assertEqual(
            set(product["trend_by_point_type"]),
            set(product["benchmark"]["rank_by_point_type"]),
        )
        national = product["trend_by_point_type"][self.supermarket_slug]["national"]
        self.assertEqual(len(national), 8)
        self.assertEqual(national[-1]["week_start"], "2025-02-24")
        self.assertEqual(set(national[-1]), {"week_start", "average_clp"})
        self.assertEqual(len(product["trend_by_point_type"][self.supermarket_slug]["regions"]["13"]), 8)
        validate_index_document(index)
        self.assertIn(product["slug"], series_documents[group["slug"]]["products"])

    def test_homepage_reference_ranks_are_unique_and_contiguous_per_monitor(self):
        ranks_by_point = {}
        for product in BENCHMARK_PRODUCTS:
            for point_label, rank in product["point_types"].items():
                ranks_by_point.setdefault(point_label, []).append(rank)

        self.assertEqual(set(ranks_by_point), set(BENCHMARK_POINT_SLUGS))
        for ranks in ranks_by_point.values():
            self.assertEqual(sorted(ranks), list(range(1, len(ranks) + 1)))

    def test_reformatted_product_names_share_one_public_history_and_keep_alias(self):
        records = [dict(record) for record in self.records]
        for record in records:
            if record["product_name"] == "Manzana|Royal|Primera" and record["week_start"] <= "2025-01-27":
                record["product_key"] = "legacy-manzana-format"
                record["product_name"] = "Manzana | Royal | Primera"
                record["slug"] = "legacy-manzana-format"

        index, series_documents = build_public_documents(
            records, SOURCES, DATASET, data_updated_at="2025-03-01T00:00:00Z"
        )
        fruit_group = next(item for item in index["groups"] if item["group_name"] == "Frutas")
        self.assertEqual(len(fruit_group["products"]), 1)
        product = fruit_group["products"][0]
        self.assertEqual(product["name"], "Manzana|Royal|Primera")
        self.assertEqual(product["aliases"], ["Manzana | Royal | Primera"])

        series_product = series_documents[fruit_group["slug"]]["products"][product["slug"]]
        self.assertEqual(series_product["aliases"], product["aliases"])
        supermarket = series_product["point_types"][self.supermarket_slug]["national"]
        self.assertEqual(len(supermarket), 8)
        self.assertEqual([point["week_start"] for point in supermarket], sorted(point["week_start"] for point in supermarket))

        egg_group = next(item for item in index["groups"] if item["group_name"] == "Huevos")
        self.assertEqual([item["name"] for item in egg_group["products"]], ["Huevo blanco"])

    def test_semantic_product_alias_is_explicit_and_combines_history(self):
        valencia = dict(self.records[0])
        valencia.update(
            product_key="orange-valencia",
            group_name="Frutas",
            product_name="Naranja|Valencia|Segunda",
            unit="$/kilo",
            slug="orange-valencia",
        )
        valenciana = dict(valencia)
        valenciana.update(
            product_key="orange-valenciana",
            product_name="Naranja | Valenciana | Segunda",
            slug="orange-valenciana",
            week_start="2025-01-13",
            week_end="2025-01-17",
        )

        index, series_documents = build_public_documents(
            [valencia, valenciana], SOURCES, DATASET, data_updated_at="2025-03-01T00:00:00Z"
        )
        fruit_group = next(item for item in index["groups"] if item["group_name"] == "Frutas")
        product = fruit_group["products"][0]
        self.assertEqual(product["name"], "Naranja|Valencia|Segunda")
        self.assertIn("Naranja | Valenciana | Segunda", product["aliases"])
        points = series_documents[fruit_group["slug"]]["products"][product["slug"]]["point_types"]
        national = next(iter(points.values()))["national"]
        self.assertEqual([point["week_start"] for point in national], ["2025-01-06", "2025-01-13"])

    def test_aliases_with_overlapping_source_observation_fail_closed(self):
        records = [dict(record) for record in self.records]
        alias = dict(records[0])
        alias.update(
            product_key="overlapping-manzana-alias",
            product_name="Manzana | Royal | Primera",
            slug="overlapping-manzana-alias",
        )
        records.append(alias)
        with self.assertRaisesRegex(SourceError, "overlap"):
            build_public_documents(
                records, SOURCES, DATASET, data_updated_at="2025-03-01T00:00:00Z"
            )

    def test_recent_flag_uses_inclusive_28_day_scope_specific_cutoff(self):
        records = [dict(record) for record in self.records]
        egg = next(record for record in records if record["product_name"] == "Huevo blanco")
        egg["week_start"] = "2025-01-27"
        egg["week_end"] = "2025-01-31"
        index, _ = build_public_documents(
            records, SOURCES, DATASET, data_updated_at="2025-03-01T00:00:00Z"
        )
        group = next(item for item in index["groups"] if item["group_name"] == "Huevos")
        summary = group["products"][0]["latest_by_point_type"][self.supermarket_slug]
        self.assertTrue(summary["national"]["fresh_within_28_days"])
        self.assertTrue(summary["regions"]["13"]["fresh_within_28_days"])

        egg["week_start"] = "2025-01-20"
        egg["week_end"] = "2025-01-24"
        index, _ = build_public_documents(
            records, SOURCES, DATASET, data_updated_at="2025-03-01T00:00:00Z"
        )
        group = next(item for item in index["groups"] if item["group_name"] == "Huevos")
        summary = group["products"][0]["latest_by_point_type"][self.supermarket_slug]
        self.assertFalse(summary["national"]["fresh_within_28_days"])
        self.assertFalse(summary["regions"]["13"]["fresh_within_28_days"])

    def test_index_declares_freshness_cutoff_and_reference_scope(self):
        self.assertEqual(
            self.index["source"]["freshness_policy"],
            {
                "max_age_days": 28,
                "reference": "latest_week_by_point_type_and_geography",
            },
        )

    def test_group_series_are_ordered_and_include_national_regional_and_point_data(self):
        group = next(item for item in self.index["groups"] if item["group_name"] == "Frutas")
        series = self.series[group["slug"]]
        self.assertEqual(series["schema_version"], 1)
        product = next(item for item in series["products"].values() if item["name"] == "Manzana|Royal|Primera")
        supermarket = product["point_types"][self.supermarket_slug]
        weeks = [point["week_start"] for point in supermarket["national"]]
        self.assertEqual(weeks, sorted(weeks))
        self.assertEqual(len(weeks), len(set(weeks)))
        self.assertEqual(supermarket["national"][-1]["average_clp"], 1550)
        self.assertEqual(supermarket["regions"]["13"][-1]["average_clp"], 1100)
        self.assertEqual(supermarket["national"][-1]["source_years"], [2025])

    def test_all_documents_are_finite_json(self):
        json.loads(serialize_json(self.index))
        validate_index_document(self.index)
        for document in self.series.values():
            json.loads(serialize_json(document))
            _validate_series_document(document)

    def test_public_contract_rejects_malformed_product_aliases(self):
        malformed_index = json.loads(serialize_json(self.index))
        malformed_index["groups"][0]["products"][0]["aliases"] = "not-an-array"
        with self.assertRaisesRegex(SourceError, "aliases"):
            validate_index_document(malformed_index)

        group_slug = next(iter(self.series))
        malformed_series = json.loads(serialize_json(self.series[group_slug]))
        first_product = next(iter(malformed_series["products"].values()))
        first_product["aliases"] = [first_product["name"], first_product["name"]]
        with self.assertRaisesRegex(SourceError, "aliases"):
            _validate_series_document(malformed_series)

    def test_noop_refresh_preserves_public_timestamp_but_changed_source_advances_it(self):
        current = self.index["source"]["resources"]
        previous = {"data_updated_at": "2025-02-01T00:00:00Z", "source": {"resources": current}}
        self.assertEqual(
            resolve_data_updated_at(previous, SOURCES, now="2025-03-02T00:00:00Z"),
            "2025-02-01T00:00:00Z",
        )
        changed = [dict(SOURCES[0], remote_hash="new-hash")]
        self.assertEqual(
            resolve_data_updated_at(previous, changed, now="2025-03-02T00:00:00Z"),
            "2025-03-02T00:00:00Z",
        )

    def test_sqlite_build_publishes_a_complete_set_and_keeps_old_set_on_stage_failure(self):
        records = parse_csv_bytes(FIXTURE.read_bytes(), resource_year=2025)
        resource = {
            "year": 2025,
            "resource_id": "fixture-resource-2025",
            "url": "https://datos.odepa.gob.cl/download/fixture-2025.csv",
            "hash": "remote-2025",
            "last_modified": "2025-03-01T00:00:00Z",
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "data" / "prices.db"
            output = root / "site" / "data"
            output.mkdir(parents=True)
            ipc_snapshot = output / "ipc.json"
            ipc_snapshot.write_bytes(b'{"schema_version":1,"test":"preserve"}\n')
            original_ipc_snapshot = ipc_snapshot.read_bytes()
            init_db(db_path)
            connection = connect_db(db_path)
            source = replace_year(connection, resource, records, "a" * 64)
            stage = root / ".data-stage-first"
            stage.mkdir()
            _stage_database_documents(
                connection, stage, [source], DATASET, [2025], "2025-03-01T00:00:00Z"
            )
            connection.close()

            changed = publish_staged_directory(stage, output)
            self.assertTrue(any(path.endswith("index.json") for path in changed))
            self.assertEqual(ipc_snapshot.read_bytes(), original_ipc_snapshot)
            index_path = output / "index.json"
            original_index = index_path.read_bytes()
            self.assertIn(b'"average_clp":1550.000000', original_index)
            self.assertTrue(list((output / "series").glob("*.json")))
            staged_index = json.loads(original_index)
            self.assertEqual(staged_index["source"]["freshness_policy"]["max_age_days"], 28)
            freshness_values = [
                price["fresh_within_28_days"]
                for group in staged_index["groups"]
                for product in group["products"]
                for summary in product["latest_by_point_type"].values()
                for price in [summary["national"], *summary["regions"].values()]
            ]
            self.assertTrue(freshness_values)
            self.assertTrue(all(freshness is True for freshness in freshness_values))

            connection = connect_db(db_path)
            no_op_stage = root / ".data-stage-noop"
            no_op_stage.mkdir()
            _stage_database_documents(
                connection, no_op_stage, [source], DATASET, [2025], "2025-03-01T00:00:00Z"
            )
            connection.close()
            self.assertEqual(publish_staged_directory(no_op_stage, output), [])

            connection = connect_db(db_path)
            failed_stage = root / ".data-stage-failed"
            failed_stage.mkdir()
            with self.assertRaises(SourceError):
                _stage_database_documents(
                    connection, failed_stage, [source], DATASET, [2024], "2025-03-02T00:00:00Z"
                )
            connection.close()
            self.assertEqual(index_path.read_bytes(), original_index)

    def test_sqlite_generation_merges_reformatted_product_history(self):
        records = parse_csv_bytes(FIXTURE.read_bytes(), resource_year=2025)
        for record in records:
            if record["product_name"] == "Manzana|Royal|Primera" and record["week_start"] == "2025-01-06":
                record["product_key"] = "legacy-manzana-format"
                record["product_name"] = "Manzana | Royal | Primera"
                record["slug"] = "legacy-manzana-format"
        resource = {
            "year": 2025,
            "resource_id": "fixture-resource-2025",
            "url": "https://datos.odepa.gob.cl/download/fixture-2025.csv",
            "hash": "remote-2025",
            "last_modified": "2025-03-01T00:00:00Z",
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "data" / "prices.db"
            output = root / "site" / "data"
            init_db(db_path)
            connection = connect_db(db_path)
            source = replace_year(connection, resource, records, "a" * 64)
            stage = root / ".data-stage-aliases"
            stage.mkdir()
            _stage_database_documents(
                connection, stage, [source], DATASET, [2025], "2025-03-01T00:00:00Z"
            )
            connection.close()

            index = json.loads((stage / "index.json").read_text(encoding="utf-8"))
            fruit_group = next(item for item in index["groups"] if item["group_name"] == "Frutas")
            self.assertEqual(len(fruit_group["products"]), 1)
            product = fruit_group["products"][0]
            self.assertEqual(product["aliases"], ["Manzana | Royal | Primera"])
            series = json.loads((stage / fruit_group["series_url"]).read_text(encoding="utf-8"))
            product_series = series["products"][product["slug"]]
            self.assertEqual(len(product_series["point_types"][self.supermarket_slug]["national"]), 8)

    def test_sqlite_generation_rejects_overlapping_alias_observations(self):
        records = parse_csv_bytes(FIXTURE.read_bytes(), resource_year=2025)
        alias = dict(records[0])
        alias.update(
            product_key="overlapping-manzana-alias",
            product_name="Manzana | Royal | Primera",
            slug="overlapping-manzana-alias",
        )
        records.append(alias)
        resource = {
            "year": 2025,
            "resource_id": "fixture-resource-2025",
            "url": "https://datos.odepa.gob.cl/download/fixture-2025.csv",
            "hash": "remote-2025",
            "last_modified": "2025-03-01T00:00:00Z",
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "data" / "prices.db"
            stage = root / ".data-stage-overlap"
            stage.mkdir()
            init_db(db_path)
            connection = connect_db(db_path)
            source = replace_year(connection, resource, records, "a" * 64)
            with self.assertRaisesRegex(SourceError, "overlap"):
                _stage_database_documents(
                    connection, stage, [source], DATASET, [2025], "2025-03-01T00:00:00Z"
                )
            connection.close()


if __name__ == "__main__":
    unittest.main()
