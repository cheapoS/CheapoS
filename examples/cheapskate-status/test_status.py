import unittest
from unittest.mock import patch, MagicMock
import json
import sys
import os

# Add the directory to sys.path so we can import status
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import status

class TestCheapskateStatus(unittest.TestCase):

    @patch('urllib.request.urlopen')
    @patch('socket.create_connection')
    def test_probe_endpoint(self, mock_socket, mock_url):
        mock_response = MagicMock()
        mock_response.code = 200
        mock_url.return_value.__enter__.return_value = mock_response
        
        endpoint = {"url": "https://example.com", "name": "Example"}
        result = status.probe_endpoint(endpoint)
        
        self.assertTrue(result['ok'])
        self.assertEqual(result['status'], 200)

if __name__ == '__main__':
    unittest.main()
