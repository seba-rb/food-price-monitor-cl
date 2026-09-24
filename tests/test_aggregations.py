import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from pipeline.fetch_odepa import aggregate_records, parse_csv_bytes


FIXTURE = Path(__file__).parent / "fixtures" / "odepa-small.csv"


class AggregationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = parse_csv_bytes(FIXTURE.read_bytes(), resource_year=2025)
        cls.aggregates = aggregate_records(cls.records)

    def find(self, *, week, geography, region_id=None, point_type="Supermercado"):
        return next(
            row
            for row in self.aggregates
            if row["week_start"] == week
            and row["geography"] == geography
            and row.get("region_id") == region_id
            and row["point_type"] == point_type
            and row["product_name"] == "Manzana|Royal|Primera"
        )

    def test_averages_sectors_then_gives_each_reporting_region_equal_weight(self):
        regional = self.find(week="2025-02-24", geography="region", region_id=13)
        national = self.find(week="2025-02-24", geography="national")
        self.assertEqual(regional["average_clp"], Decimal("1100.000000"))
        self.assertEqual(national["average_clp"], Decimal("1550.000000"))

    def test_extrema_span_the_included_source_observations(self):
        regional = self.find(week="2025-02-24", geography="region", region_id=13)
        national = self.find(week="2025-02-24", geography="national")
        self.assertEqual((regional["minimum_clp"], regional["maximum_clp"]), (900, 1300))
        self.assertEqual((national["minimum_clp"], national["maximum_clp"]), (900, 2200))

    def test_week_over_week_uses_the_immediately_preceding_calendar_week(self):
        regional = self.find(week="2025-02-24", geography="region", region_id=13)
        national = self.find(week="2025-02-24", geography="national")
        self.assertEqual(regional["wow_pct"], Decimal("4.76"))
        self.assertEqual(national["wow_pct"], Decimal("47.62"))

    def test_year_over_year_uses_a_364_day_date_offset(self):
        product = self.records[0]["product_key"]
        previous = dict(self.records[0])
        previous.update(
            week_start="2024-01-08",
            week_end="2024-01-12",
            source_year=2024,
            product_key=product,
            price_avg_micros=1_000_000_000,
        )
        current = dict(self.records[0])
        current.update(
            week_start="2025-01-06",
            week_end="2025-01-10",
            source_year=2025,
            price_avg_micros=980_000_000,
        )
        rows = aggregate_records([previous, current])
        national = next(row for row in rows if row["geography"] == "national" and row["week_start"] == "2025-01-06")
        self.assertEqual(national["yoy_pct"], Decimal("-2.00"))
        self.assertEqual(date.fromisoformat("2025-01-06").toordinal() - date.fromisoformat("2024-01-08").toordinal(), 364)

    def test_missing_or_zero_comparison_is_null_and_point_types_do_not_mix(self):
        rows = [dict(row) for row in self.records if row["week_start"] == "2025-02-24"]
        zero = dict(rows[0])
        zero.update(week_start="2025-02-17", week_end="2025-02-21", price_avg_micros=0)
        # Keep a separate product identity so zero-denominator behavior is explicit.
        zero["product_name"] = "Producto de prueba"
        zero["product_key"] = "zero-product"
        rows.append(zero)
        current = dict(zero)
        current.update(week_start="2025-02-24", week_end="2025-02-28", price_avg_micros=1_000_000_000)
        rows.append(current)
        rows.extend(self.records[:1])
        aggregates = aggregate_records(rows)
        national = next(row for row in aggregates if row["geography"] == "national" and row["product_name"] == "Manzana|Royal|Primera" and row["week_start"] == "2025-02-24")
        feria = next(row for row in aggregates if row["geography"] == "national" and row["point_type"] == "Feria")
        zero_current = next(row for row in aggregates if row["geography"] == "national" and row["product_key"] == "zero-product" and row["week_start"] == "2025-02-24")
        self.assertIsNone(national["yoy_pct"])
        self.assertIsNone(feria["wow_pct"])
        self.assertIsNone(zero_current["wow_pct"])


if __name__ == "__main__":
    unittest.main()
