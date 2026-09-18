import unittest
from unittest.mock import patch, MagicMock, mock_open
import json
import sys
import datetime
import os
import io
import importlib.util
import os
spec = importlib.util.spec_from_file_location("status", os.path.join(os.path.dirname(__file__), "status.py"))
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)
import sys; sys.modules['status'] = status
class TestCheapskateStatus(unittest.TestCase):

    def test_load_endpoints_success(self):
        config_data = [{"name": "Test", "url": "https://test.com"}]
        with patch("builtins.open", mock_open(read_data=json.dumps(config_data))):
            endpoints = status.load_endpoints("fake.json")
            self.assertEqual(endpoints, config_data)

    def test_load_endpoints_error(self):
        with patch("builtins.open", side_effect=FileNotFoundError):
            with patch("sys.exit") as mock_exit:
                status.load_endpoints("nonexistent.json")
                mock_exit.assert_called_with(2)

    @patch("urllib.request.urlopen")
    @patch("status.get_ssl_expiry")
    def test_probe_endpoint_success(self, mock_ssl, mock_urlopen):
        mock_response = MagicMock()
        mock_response.code = 200
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response
        mock_ssl.return_value = "2025-01-01"
        
        endpoint = {"name": "Test", "url": "https://test.com"}
        result = status.probe_endpoint(endpoint)
        
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], 200)

    def test_generate_badge_ok(self):
        results = [{"ok": True}]
        badge = status.generate_badge(results)
        self.assertIn("green", badge)

    def test_generate_badge_error(self):
        results = [{"ok": False}]
        badge = status.generate_badge(results)
        self.assertIn("red", badge)

    def test_generate_page(self):
        results = [{"name": "Test", "ok": True, "latency": 0.123}]
        page = status.generate_page(results)
        self.assertIn("<h1>System Status</h1>", page)

    @patch("status.load_endpoints")
    @patch("status.probe_endpoint")
    def test_main_probe(self, mock_probe, mock_load):
        mock_load.return_value = [{"name": "Test", "url": "https://test.com"}]
        mock_probe.return_value = {"url": "https://test.com", "ok": True}
        
        with patch("sys.argv", ["status.py", "probe", "config.json"]):
            with patch("sys.stdout", new=io.StringIO()) as fake_out:
                status.main()
                self.assertIn("ok", fake_out.getvalue())
    def test_main_help(self):
        with patch("sys.argv", ["status.py", "--help"]):
            with patch("sys.stdout", new=io.StringIO()) as fake_out:
                with self.assertRaises(SystemExit) as cm:
                    status.main()
                self.assertEqual(cm.exception.code, 0)
                self.assertIn("usage", fake_out.getvalue())

    @patch("status.socket.create_connection")
    def test_get_ssl_expiry(self, mock_socket):
        mock_sock = MagicMock()
        mock_socket.return_value.__enter__.return_value = mock_sock
        with patch("ssl.create_default_context") as mock_ctx:
            mock_ssock = mock_ctx.return_value.wrap_socket.return_value.__enter__.return_value
            mock_ssock.getpeercert.return_value = {'notAfter': '2025-01-01'}
            expiry = status.get_ssl_expiry("https://test.com")
            self.assertEqual(expiry, '2025-01-01')
    def test_telem_json_roundtrip(self):
        data = [{"name": "Test", "ok": True}]
        json_str = json.dumps(data)
        loaded = json.loads(json_str)
        self.assertEqual(data, loaded)

    def test_compute_uptime(self):
        results = [{"ok": True}, {"ok": False}, {"ok": True}]
        # Expected uptime = 2/3 * 100 = 66.666...
        self.assertAlmostEqual(status.compute_uptime(results), 66.67, places=2)

    def test_check_cert_expiry_valid(self):
        # expiry 10 days from now
        future = (datetime.datetime.utcnow() + datetime.timedelta(days=10)).strftime("%b %d %H:%M:%S %Y GMT")
        is_valid, days = status.check_cert_expiry(future, now=datetime.datetime.utcnow())
        self.assertTrue(is_valid)
        self.assertAlmostEqual(days, 10.0, places=1)

if __name__ == '__main__':
    unittest.main()