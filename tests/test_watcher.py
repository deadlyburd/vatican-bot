"""Tests for the manual sniper watcher."""
from __future__ import annotations

import unittest

from desktop_app.watcher import (
    WatchTarget, Watcher, find_time_match, group_by_date_visitors, normalize_time,
)
from desktop_app.providers.base import Slot


class TestNormalizeTime(unittest.TestCase):
    def test_zero_pad(self):
        self.assertEqual(normalize_time("9:00"), "09:00")
        self.assertEqual(normalize_time("09:00"), "09:00")
        self.assertEqual(normalize_time("13:5"), "13:05")

    def test_no_colon(self):
        self.assertEqual(normalize_time("0900"), "0900")

    def test_empty(self):
        self.assertEqual(normalize_time(""), "")


class TestFindTimeMatch(unittest.TestCase):
    def _slots(self):
        return [
            Slot(date="29/10/2026", time="08:00", slot_id="a", ticket_id="t"),
            Slot(date="29/10/2026", time="09:30", slot_id="b", ticket_id="t"),
            Slot(date="29/10/2026", time="14:00", slot_id="c", ticket_id="t"),
        ]

    def test_match(self):
        m = find_time_match(self._slots(), "09:30")
        self.assertIsNotNone(m)
        self.assertEqual(m.slot_id, "b")

    def test_match_without_leading_zero(self):
        m = find_time_match(self._slots(), "9:30")
        self.assertIsNotNone(m)
        self.assertEqual(m.slot_id, "b")

    def test_no_match(self):
        self.assertIsNone(find_time_match(self._slots(), "12:00"))

    def test_empty(self):
        self.assertIsNone(find_time_match([], "09:00"))


class TestWatcher(unittest.TestCase):
    def _watcher(self):
        from desktop_app.config import default_config
        return Watcher(default_config())

    def test_add_remove_list(self):
        w = self._watcher()
        t = WatchTarget(date="29/10/2026", time="09:00", visitors=2)
        w.add(t)
        self.assertEqual(len(w.list()), 1)
        self.assertTrue(w.remove(t.id))
        self.assertEqual(len(w.list()), 0)
        self.assertFalse(w.remove("nope"))

    def test_unique_ids(self):
        w = self._watcher()
        a = WatchTarget(date="29/10/2026", time="09:00")
        b = WatchTarget(date="29/10/2026", time="10:00")
        w.add(a); w.add(b)
        self.assertNotEqual(a.id, b.id)

    def test_add_multi(self):
        w = self._watcher()
        added = w.add_multi("29/10/2026", ["09:00", "10:30", "14:00"], visitors=2, name="Mario")
        self.assertEqual(len(added), 3)
        self.assertEqual(len(w.list()), 3)
        times = {a.time for a in added}
        self.assertEqual(times, {"09:00", "10:30", "14:00"})


class TestGroupByDateVisitors(unittest.TestCase):
    def test_groups(self):
        watches = [
            WatchTarget(date="29/10/2026", time="09:00", visitors=2),
            WatchTarget(date="29/10/2026", time="10:00", visitors=2),
            WatchTarget(date="30/10/2026", time="09:00", visitors=2),
            WatchTarget(date="29/10/2026", time="11:00", visitors=3),
        ]
        groups = group_by_date_visitors(watches)
        self.assertEqual(len(groups), 3)  # (29/10,2), (30/10,2), (29/10,3)
        self.assertEqual(len(groups[("29/10/2026", 2)]), 2)
        self.assertEqual(len(groups[("30/10/2026", 2)]), 1)
        self.assertEqual(len(groups[("29/10/2026", 3)]), 1)

    def test_empty(self):
        self.assertEqual(group_by_date_visitors([]), {})


if __name__ == "__main__":
    unittest.main()
