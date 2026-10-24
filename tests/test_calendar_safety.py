"""Regression tests for calendar safety and source integrity."""
import datetime
import unittest
from unittest.mock import patch
from scripts import update_calendars as calendars


class CalendarSafetyTests(unittest.TestCase):
    def test_missing_schedule_dates_are_not_assumed_closed(self):
        schedule = {"schedule": [{"date": "2026-10-25", "type": "OPERATING",
                                  "openingTime": "10:00", "closingTime": "18:00"}]}
        result = calendars.parse_schedule(schedule)
        self.assertEqual(result["2026-10-25"]["status"], "open")
        self.assertNotIn("2026-10-26", result)

    def test_explicit_closure(self):
        result = calendars.parse_schedule({"schedule": [{"date": "2026-10-26", "type": "CLOSED"}]})
        self.assertEqual(result["2026-10-26"]["status"], "closed")

    def test_secondary_closure_does_not_override_open(self):
        result = {"PC001": {"name": "Parque Warner Madrid",
                            "days": {"2026-10-26": {"status": "open"}}}}
        diagnostics = {"PC001": {"name": "Parque Warner Madrid"}}
        calendars.apply_dated_closures(result, diagnostics)
        self.assertEqual(result["PC001"]["days"]["2026-10-26"]["status"], "open")
        self.assertIn("2026-10-26", diagnostics["PC001"]["dated_conflicts"])

    def test_2026_season_rule_never_rolls_into_2027(self):
        self.assertIsNone(calendars.official_season("PC020", datetime.datetime(2027, 1, 1)))

    def test_boe_source_is_official_park(self):
        url, pattern, kind = calendars.OFFICIAL_SEASON_SOURCES["PC020"]
        self.assertIn("sommarland.no", url)
        self.assertEqual(kind, "official")


if __name__ == "__main__":
    unittest.main()
