import json
import unittest
from unittest.mock import patch
from io import StringIO
from datetime import datetime, timedelta, timezone
from scripts.time_ago import parse_timestamp, time_ago, main


class TestParseTimestamp(unittest.TestCase):
    def test_epoch_seconds(self):
        dt = parse_timestamp("1700000000")
        self.assertEqual(dt.year, 2023)
        self.assertEqual(dt.month, 11)

    def test_iso_no_suffix(self):
        dt = parse_timestamp("2023-11-14T12:00:00")
        self.assertEqual(dt.year, 2023)

    def test_iso_z_suffix(self):
        dt = parse_timestamp("2023-11-14T12:00:00Z")
        self.assertIsNotNone(dt.tzinfo)

    def test_iso_with_offset(self):
        dt = parse_timestamp("2023-11-14T12:00:00+05:00")
        self.assertIsNotNone(dt.tzinfo)

    def test_date_only(self):
        dt = parse_timestamp("2023-11-14")
        self.assertEqual(dt.year, 2023)


class TestTimeAgo(unittest.TestCase):
    def test_future_returns_now(self):
        now = datetime(2023, 11, 14, 12, 0, 0, tzinfo=timezone.utc)
        future = datetime(2023, 11, 14, 13, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(time_ago(future, now=now), "just now")

    def test_just_now(self):
        now = datetime(2023, 11, 14, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(time_ago(now, now=now), "just now")
        self.assertEqual(time_ago(now - timedelta(seconds=30), now=now), "just now")

    def test_minutes_ago(self):
        now = datetime(2023, 11, 14, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(time_ago(now - timedelta(minutes=1), now=now), "1 minute ago")
        self.assertEqual(time_ago(now - timedelta(minutes=5), now=now), "5 minutes ago")

    def test_hours_ago(self):
        now = datetime(2023, 11, 14, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(time_ago(now - timedelta(hours=1), now=now), "1 hour ago")
        self.assertEqual(time_ago(now - timedelta(hours=3), now=now), "3 hours ago")

    def test_yesterday(self):
        now = datetime(2023, 11, 14, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(time_ago(now - timedelta(days=1), now=now), "yesterday")

    def test_days_ago(self):
        now = datetime(2023, 11, 14, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(time_ago(now - timedelta(days=2), now=now), "2 days ago")

    def test_just_under_one_day(self):
        now = datetime(2023, 11, 14, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(time_ago(now - timedelta(hours=23, minutes=59), now=now), "23 hours ago")

    def test_just_under_two_days(self):
        now = datetime(2023, 11, 14, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(time_ago(now - timedelta(days=1, hours=23, minutes=59), now=now), "yesterday")

    def test_old_date(self):
        now = datetime(2023, 11, 14, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(time_ago(now - timedelta(days=10), now=now), "2023-11-04")

    def test_none_target(self):
        self.assertEqual(time_ago(None), "just now")

    def test_string_target(self):
        now = datetime(2023, 11, 14, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(time_ago("2023-11-14T11:00:00Z", now=now), "1 hour ago")

    def test_naive_target(self):
        now = datetime(2023, 11, 14, 12, 0, 0)
        target = datetime(2023, 11, 14, 11, 0, 0)
        self.assertEqual(time_ago(target, now=now), "1 hour ago")



class TestMainJSON(unittest.TestCase):
    def test_json_single(self):
        with patch('sys.argv', ['time_ago.py', '2023-11-14T11:00:00Z', '--now', '2023-11-14T12:00:00Z', '--json']):
            with patch('sys.stdout', new_callable=StringIO) as fake_out:
                main()
        result = json.loads(fake_out.getvalue().strip())
        self.assertEqual(result, "1 hour ago")

    def test_json_multiple(self):
        with patch('sys.argv', ['time_ago.py', '2023-11-14T11:00:00Z', '2023-11-13T12:00:00Z', '--now', '2023-11-14T12:00:00Z', '--json']):
            with patch('sys.stdout', new_callable=StringIO) as fake_out:
                main()
        result = json.loads(fake_out.getvalue().strip())
        self.assertEqual(result, ["1 hour ago", "yesterday"])

    def test_json_epoch_inputs(self):
        with patch('sys.argv', ['time_ago.py', '1699996400', '--now', '1700000000', '--json']):
            with patch('sys.stdout', new_callable=StringIO) as fake_out:
                main()
        result = json.loads(fake_out.getvalue().strip())
        self.assertEqual(result, "1 hour ago")

    def test_no_args_with_now(self):
        with patch('sys.argv', ['time_ago.py', '--now', '2023-11-14T12:00:00Z']):
            with patch('sys.stdout', new_callable=StringIO) as fake_out:
                main()
        self.assertEqual(fake_out.getvalue().strip(), "just now")

    def test_json_no_args_with_now(self):
        with patch('sys.argv', ['time_ago.py', '--now', '2023-11-14T12:00:00Z', '--json']):
            with patch('sys.stdout', new_callable=StringIO) as fake_out:
                main()
        result = json.loads(fake_out.getvalue().strip())
        self.assertEqual(result, "just now")


if __name__ == '__main__':
    unittest.main()
