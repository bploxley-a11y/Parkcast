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

    def test_secondary_month_extracts_only_explicit_days(self):
        import calendar
        heading = "October 2026"
        rows = []
        for day in range(1, 32):
            weekday = __import__("datetime").date(2026, 10, day).strftime("%a")
            status = "Closed" if day in (26, 27, 28, 29, 30) else "10:00-18:00"
            rows.append(f"<div>{weekday} {day} {status}</div>")
        parsed = calendars.parse_secondary_month("<h1>" + heading + "</h1>" + "".join(rows), 2026, 10)
        self.assertEqual(parsed["2026-10-26"]["status"], "closed")
        self.assertEqual(parsed["2026-10-30"]["status"], "closed")
        self.assertEqual(parsed["2026-10-25"]["status"], "open")
        self.assertEqual(calendars.parse_secondary_month("<h1>October 2026</h1><p>Mon 26 Closed</p>", 2026, 10), {})

    def test_walsrode_is_zoo_with_explicit_2026_dates(self):
        park = next(row for row in calendars.PARKS if row[0] == "PC025")
        self.assertEqual(park[1], "Weltvogelpark Walsrode")
        result, diagnostics = {}, {}
        calendars.apply_walsrode_2026(result, diagnostics)
        self.assertEqual(result["PC025"]["days"]["2026-10-30"]["status"], "open")
        self.assertEqual(result["PC025"]["days"]["2026-11-01"]["status"], "open")
        self.assertNotIn("2026-11-02", result["PC025"]["days"])

    def test_2026_season_rule_never_rolls_into_2027(self):
        self.assertIsNone(calendars.official_season("PC020", datetime.datetime(2027, 1, 1)))

    def test_boe_source_is_official_park(self):
        url, pattern, kind = calendars.OFFICIAL_SEASON_SOURCES["PC020"]
        self.assertIn("sommarland.no", url)
        self.assertEqual(kind, "official")


if __name__ == "__main__":
    unittest.main()
