import unittest
from web_connect import PROBE_JS

class WebConnectionTests(unittest.TestCase):
    def test_connection_probe_does_not_send_or_extract_messages(self):
        self.assertNotIn('Xin chào', PROBE_JS)
        self.assertNotIn('btn.click()', PROBE_JS)
        self.assertNotIn('return assistant.innerText', PROBE_JS)
        self.assertNotIn('responseText', PROBE_JS)
        self.assertIn("host !== 'chatgpt.com'", PROBE_JS)

if __name__ == '__main__':
    unittest.main()
