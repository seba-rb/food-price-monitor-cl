import json
import math
import unittest
from pathlib import Path


IPC_PATH = Path(__file__).parents[1] / "site" / "data" / "ipc.json"


class IpcSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads(IPC_PATH.read_text(encoding="utf-8"))
        cls.observations = cls.document["observations"]

    def test_snapshot_has_official_series_provenance_and_latest_month(self):
        self.assertEqual(self.document["schema_version"], 1)
        source = self.document["source"]
        self.assertEqual(source["series_id"], "G073.IPC.IND.2023.M")
        self.assertEqual(source["base"], "Promedio 2023 = 100")
        self.assertEqual(source["latest_month"], "2026-08")
        self.assertEqual(max(self.observations), source["latest_month"])
        self.assertEqual(
            source["attribution"],
            "Instituto Nacional de Estadísticas (INE) y Banco Central de Chile. "
            "IPC general empalmado, serie G073.IPC.IND.2023.M.",
        )
        self.assertEqual(source["license"]["id"], "CC-BY-SA-4.0")
        self.assertEqual(
            source["license"]["url"],
            "https://creativecommons.org/licenses/by-sa/4.0/",
        )
        self.assertTrue(source["adaptation_note"])

    def test_snapshot_has_one_positive_value_for_every_month_since_january_2017(self):
        months = sorted(self.observations)
        self.assertEqual(len(months), 116)
        self.assertEqual(months[0], "2017-01")
        self.assertEqual(months[-1], "2026-08")
        ordinals = [int(month[:4]) * 12 + int(month[5:]) - 1 for month in months]
        self.assertEqual(ordinals, list(range(ordinals[0], ordinals[0] + len(months))))
        self.assertTrue(all(math.isfinite(value) and value > 0 for value in self.observations.values()))
        self.assertEqual(self.observations["2017-01"], 73.38)
        self.assertEqual(self.observations["2026-08"], 113.15)


if __name__ == "__main__":
    unittest.main()
