"""Viewer service boundary: owned endpoints and capture-free Unicode input."""
from pathlib import Path
import tempfile
import threading
import unittest
from cage_use.service import ServiceDesktop, SessionService
from cage_mcp_test_support import FakeDesktop


class ViewerServiceTests(unittest.TestCase):
    def test_owned_endpoint_and_capture_free_text(self):
        with tempfile.TemporaryDirectory() as directory:
            desktop = FakeDesktop()
            with SessionService(Path(directory) / 'worker.sock', desktop) as service:
                thread = threading.Thread(target=service.serve_forever)
                thread.start()
                try:
                    client = ServiceDesktop(service.server_address)
                    client.launch('firefox', [])
                    self.assertEqual(client.call('vnc_endpoint', 'owned'), {'host': '127.0.0.1', 'port': 5905})
                    with self.assertRaises(ValueError):
                        client.call('vnc_endpoint', 'unknown')
                    text = "password ' $(literal) 🐦"
                    self.assertEqual(client.call('send_text', 'owned', text), {'sent': True})
                    self.assertEqual(len(desktop.calls), 1)
                    self.assertEqual(desktop.calls[0][2], text.encode())
                    for invalid in (None, 'x' * 10001, '\0'):
                        with self.assertRaises(ValueError):
                            client.call('send_text', 'owned', invalid)
                    self.assertEqual(len(desktop.calls), 1)
                finally:
                    service.shutdown()
                    thread.join()


if __name__ == '__main__':
    unittest.main()
