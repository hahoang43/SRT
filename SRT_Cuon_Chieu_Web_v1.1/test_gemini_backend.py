"""Exercise Gemini-shaped HTTP responses without an API key or paid requests."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtNetwork import QNetworkProxy
from PySide6.QtWidgets import QApplication

from gemini_backend import API_URL, GeminiClient
from srt_engine import DEFAULT_PROMPT, parse_srt

FAKE_KEY = 'test-only-gemini-key'


class LocalServer:
    def __init__(self, respond):
        self.requests = []
        self.keys = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.handle_request(None)

            def do_POST(self):
                self.handle_request(json.loads(self.rfile.read(int(self.headers['Content-Length']))))

            def handle_request(self, data):
                outer.requests.append((self.path, data))
                outer.keys.append(self.headers.get('x-goog-api-key'))
                respond(self, self.path, data)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @staticmethod
    def json(handler, data, status=200):
        LocalServer.raw(handler, json.dumps(data, ensure_ascii=False).encode(), status)

    @staticmethod
    def raw(handler, raw, status=200):
        handler.send_response(status)
        handler.send_header('Content-Type', 'application/json')
        handler.send_header('Content-Length', str(len(raw)))
        handler.end_headers()
        try:
            handler.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    @staticmethod
    def translation(handler, rows):
        LocalServer.json(handler, {'candidates': [{'finishReason': 'STOP', 'content': {
            'parts': [{'text': json.dumps({'items': rows}, ensure_ascii=False)}]}}]})

    def __enter__(self):
        self.thread.start()
        self.route = patch('gemini_backend.API_URL', self.url + '/v1beta')
        self.route.start()
        return self

    def __exit__(self, *args):
        self.route.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class GeminiBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setQuitOnLastWindowClosed(False)
        cls.cues = parse_srt('1\n00:00:01,000 --> 00:00:02,000\n你好\n')

    def client(self):
        client = GeminiClient()
        client.manager.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        self.addCleanup(client.cancel)
        self.addCleanup(client.deleteLater)
        return client

    def result(self, client, action, success='translated'):
        loop, values, errors = QEventLoop(), [], []
        def good(value):
            values.append(value)
            loop.quit()
        def bad(value):
            errors.append(value)
            loop.quit()
        signal = getattr(client, success)
        signal.connect(good)
        client.failed.connect(bad)
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(3000)
        action()
        loop.exec()
        timer.stop()
        signal.disconnect(good)
        client.failed.disconnect(bad)
        self.assertTrue(values or errors, 'HTTP request never completed')
        self.assertFalse(client.busy)
        self.assertEqual(client._api_key, '')
        return values, errors

    def translate(self, client):
        client.translate(FAKE_KEY, 'gemini-2.5-flash', self.cues, DEFAULT_PROMPT)

    def test_rest_payload_unicode_json_and_key_header(self):
        self.assertEqual(API_URL, 'https://generativelanguage.googleapis.com/v1beta')
        with LocalServer(lambda h, p, d: LocalServer.translation(h, [{'id': 1, 'vi': 'Xin chào'}])) as server:
            client = self.client()
            values, errors = self.result(client, lambda: self.translate(client))
            self.assertEqual(errors, [])
            self.assertEqual(json.loads(values[0]), {'items': [{'id': 1, 'vi': 'Xin chào'}]})
            self.assertEqual(server.keys, [FAKE_KEY])
            path, data = server.requests[0]
            self.assertEqual(path, '/v1beta/models/gemini-2.5-flash:generateContent')
            self.assertNotIn(FAKE_KEY, path + json.dumps(data))
            self.assertEqual(data['generationConfig']['responseMimeType'], 'application/json')
            text = data['contents'][0]['parts'][0]['text']
            self.assertIn('你好', text)
            self.assertNotIn('00:00:01', text)

    def test_model_list_pagination_and_generation_filter(self):
        def respond(h, p, d):
            if '?' not in p:
                LocalServer.json(h, {'models': [
                    {'name': 'models/gemini-2.5-flash', 'supportedGenerationMethods': ['generateContent']},
                    {'name': 'models/gemini-embedding-001', 'supportedGenerationMethods': ['embedContent']}],
                    'nextPageToken': 'page+2/='})
            else:
                LocalServer.json(h, {'models': [
                    {'name': 'models/gemini-2.5-flash-lite', 'supportedGenerationMethods': ['generateContent']}]})
        with LocalServer(respond) as server:
            client = self.client()
            values, errors = self.result(client, lambda: client.refresh_models(FAKE_KEY), 'models_ready')
            self.assertEqual(errors, [])
            self.assertEqual(values, [['gemini-2.5-flash', 'gemini-2.5-flash-lite']])
            self.assertIn('pageToken=', server.requests[1][0])
            self.assertEqual(server.keys, [FAKE_KEY, FAKE_KEY])

    def test_api_errors_never_retry_or_leak_echoed_key(self):
        for status in (400, 401, 403, 404, 429, 500, 503):
            with self.subTest(status=status), LocalServer(
                    lambda h, p, d: LocalServer.json(h, {'error': {'message': FAKE_KEY}}, status)) as server:
                client = self.client()
                values, errors = self.result(client, lambda: self.translate(client))
                self.assertEqual(values, [])
                self.assertEqual(len(errors), 1)
                self.assertIn(str(status), errors[0])
                self.assertNotIn(FAKE_KEY, errors[0])
                self.assertEqual(len(server.requests), 1)

    def test_blocked_truncated_and_malformed_responses_are_not_imported(self):
        responses = [
            {'promptFeedback': {'blockReason': 'SAFETY'}},
            {'candidates': []},
            {'candidates': [{'finishReason': 'MAX_TOKENS', 'content': {'parts': [{'text': 'partial'}]}}]},
            {'candidates': [{'finishReason': 'SAFETY'}]},
            {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'thought': True, 'text': 'secret'}]}}]},
            {'candidates': [None]},
            {'candidates': [{'finishReason': 'STOP', 'content': None}]},
            [],
        ]
        for response in responses:
            with self.subTest(response=response), LocalServer(lambda h, p, d: LocalServer.json(h, response)):
                client = self.client()
                values, errors = self.result(client, lambda: self.translate(client))
                self.assertEqual(values, [])
                self.assertEqual(len(errors), 1)
        with LocalServer(lambda h, p, d: LocalServer.raw(h, ('{' + FAKE_KEY).encode())):
            client = self.client()
            values, errors = self.result(client, lambda: self.translate(client))
            self.assertEqual(values, [])
            self.assertNotIn(FAKE_KEY, errors[0])

    def test_timeout_does_not_retry(self):
        def stalled(h, p, d):
            time.sleep(.15)
            LocalServer.translation(h, [{'id': 1, 'vi': 'LATE'}])
        with LocalServer(stalled) as server:
            client = self.client()
            def start():
                self.translate(client)
                client._timer.start(20)
            values, errors = self.result(client, start)
            self.assertEqual(values, [])
            self.assertIn('thời gian chờ', errors[0])
            self.assertEqual(len(server.requests), 1)

    def test_cancel_old_reply_then_restart_ignores_old_completion(self):
        def respond(h, p, d):
            if p.endswith('/models'):
                LocalServer.json(h, {'models': []})
            else:
                time.sleep(.2)
                LocalServer.translation(h, [{'id': 1, 'vi': 'OLD'}])
        with LocalServer(respond) as server:
            client = self.client()
            translations, errors, models = [], [], []
            client.translated.connect(translations.append)
            client.failed.connect(errors.append)
            client.models_ready.connect(models.append)
            self.translate(client)
            def restart():
                client.cancel()
                client.refresh_models(FAKE_KEY)
            loop = QEventLoop()
            QTimer.singleShot(50, restart)
            QTimer.singleShot(400, loop.quit)
            loop.exec()
            self.assertEqual(translations, [])
            self.assertEqual(errors, [])
            self.assertEqual(models, [[]])
            self.assertEqual(len(server.requests), 2)

    def test_redirect_is_not_followed_with_key_or_subtitles(self):
        def respond(h, p, d):
            h.send_response(307)
            h.send_header('Location', 'http://127.0.0.1:1/must-not-contact')
            h.end_headers()
        with LocalServer(respond) as server:
            client = self.client()
            values, errors = self.result(client, lambda: self.translate(client))
            self.assertEqual(values, [])
            self.assertIn('307', errors[0])
            self.assertEqual(len(server.requests), 1)

    def test_missing_key_invalid_model_and_concurrent_requests(self):
        client = self.client()
        for key in ('', ' ', 'bad\nkey', 'khóa'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                client.refresh_models(key)
            self.assertFalse(client.busy)
        for model in ('https://elsewhere/key', '../models/x', 'bad model', 'gemini-flash?key=x'):
            with self.subTest(model=model), self.assertRaises(ValueError):
                client.translate(FAKE_KEY, model, self.cues, DEFAULT_PROMPT)
            self.assertFalse(client.busy)
        with LocalServer(lambda h, p, d: LocalServer.json(h, {'models': []})) as server:
            client.refresh_models(FAKE_KEY)
            with self.assertRaises(ValueError):
                self.translate(client)
            self.result(client, lambda: None, 'models_ready')
            self.assertEqual(len(server.requests), 1)


if __name__ == '__main__':
    unittest.main()
