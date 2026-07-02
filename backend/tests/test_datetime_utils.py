import unittest
from datetime import datetime, timezone

from core.datetime_utils import to_utc_iso


class ToUtcIsoTests(unittest.TestCase):
    def test_none(self):
        self.assertIsNone(to_utc_iso(None))

    def test_naive_as_utc(self):
        dt = datetime(2026, 7, 2, 10, 30, 45, 123456)
        self.assertEqual(to_utc_iso(dt), "2026-07-02T10:30:45.123Z")

    def test_aware_converts_to_z(self):
        dt = datetime(2026, 7, 2, 18, 30, 45, tzinfo=timezone.utc)
        self.assertEqual(to_utc_iso(dt), "2026-07-02T18:30:45.000Z")


if __name__ == "__main__":
    unittest.main()
