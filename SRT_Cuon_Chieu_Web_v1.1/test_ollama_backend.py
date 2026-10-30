"""Exercise the real asynchronous HTTP client against an Ollama-shaped local server."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
import unittest

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from ollama_backend import OllamaClient
from srt_engine import parse_srt, DEFAULT_PROMPT


class LocalServer:
    def __init__(self, respond):
        self.requests = []
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
                respond(self, self.path, data)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @staticmethod
    def json(handler, data, status=200):
        raw = json.dumps(data, ensure_ascii=False).encode()
        handler.send_response(status)
        handler.send_header('Content-Type', 'application/json')
        handler.send_header('Content-Length', str(len(raw)))
        handler.end_headers()
        try:
            handler.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    @staticmethod
    def stream(handler, packets, split_bytes=False, delay=0):
        handler.send_response(200)
        handler.send_header('Content-Type', 'application/x-ndjson')
        handler.end_headers()
        try:
            for packet in packets:
                raw = json.dumps(packet, ensure_ascii=False).encode() + b'\n'
                parts = [raw[i:i+1] for i in range(len(raw))] if split_bytes else [raw]
                for part in parts:
                    handler.wfile.write(part)
                    handler.wfile.flush()
                if delay:
                    time.sleep(delay)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class OllamaBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setQuitOnLastWindowClosed(False)
        cls.cues = parse_srt('1\n00:00:01,000 --> 00:00:02,000\n你好\n')

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
        timer.start(5000)
        action()
        loop.exec()
        timer.stop()
        signal.disconnect(good)
        client.failed.disconnect(bad)
        self.assertTrue(values or errors, 'HTTP request never completed')
        return values, errors

    def test_streaming_unicode_schema_and_local_only_request(self):
        text = '{"items":[{"id":1,"vi":"Xin chào bạn"}]}'
        def respond(handler, path, data):
            if path == '/api/show':
                LocalServer.json(handler, {'capabilities':['completion']})
            else:
                LocalServer.stream(handler, [
                    {'message':{'content':text[:28]},'done':False},
                    {'message':{'content':text[28:]},'done':False},
                    {'message':{'content':''},'done':True},
                ], split_bytes=True)
        with LocalServer(respond) as server:
            client = OllamaClient(base_url=server.url)
            values, errors = self.result(client, lambda: client.translate('qwen3:4b', self.cues, DEFAULT_PROMPT))
            self.assertEqual(errors, [])
            self.assertEqual(values, [text])
            self.assertFalse(client.busy)
            self.assertEqual([path for path, _ in server.requests], ['/api/show','/api/chat'])
            payload = server.requests[-1][1]
            self.assertFalse(payload['think'])
            self.assertTrue(payload['stream'])
            self.assertEqual(payload['format']['properties']['items']['items']['properties']['id']['enum'], [1])
            self.assertIn('你好', payload['messages'][0]['content'])
            self.assertNotIn('00:00:01', payload['messages'][0]['content'])

    def test_models_and_pull_progress(self):
        def respond(handler, path, data):
            if path == '/api/tags':
                LocalServer.json(handler, {'models':[{'name':'qwen3:4b'}, {'name':'qwen3-cloud'},
                    {'name':'remote-model','remote_host':'https://example.invalid'}]})
            else:
                LocalServer.stream(handler, [{'status':'pulling manifest'},
                    {'status':'pulling abc','total':100,'completed':50}, {'status':'success'}])
        with LocalServer(respond) as server:
            client = OllamaClient(base_url=server.url)
            values, errors = self.result(client, client.refresh_models, 'models_ready')
            self.assertEqual(errors, [])
            self.assertEqual(values, [['qwen3:4b']])
            progress = []
            client.pull_progress.connect(progress.append)
            values, errors = self.result(client, lambda: client.pull_model('qwen3:4b'), 'model_pulled')
            self.assertEqual(values, ['qwen3:4b'])
            self.assertEqual(errors, [])
            self.assertTrue(any('50%' in item for item in progress))

    def test_missing_remote_and_embedding_models_fail_before_chat(self):
        cases = [({'error':'model not found'},404),
                 ({'remote_host':'https://example.invalid'},200),
                 ({'capabilities':['embedding']},200)]
        for data, status in cases:
            with self.subTest(data=data), LocalServer(lambda h,p,d: LocalServer.json(h,data,status)) as server:
                client = OllamaClient(base_url=server.url)
                values, errors = self.result(client, lambda: client.translate('qwen3:4b', self.cues, DEFAULT_PROMPT))
                self.assertEqual(values, [])
                self.assertEqual(len(errors), 1)
                self.assertEqual(len(server.requests), 1)

    def test_truncated_error_and_malformed_stream_never_publish_translation(self):
        for packets in ([{'message':{'content':'{"items":['},'done':False}],
                        [{'message':{'content':'partial'},'done':False},{'error':'out of memory'}],
                        [{'message':None,'done':True}]):
            def respond(h,p,d):
                if p == '/api/show':
                    LocalServer.json(h,{})
                else:
                    LocalServer.stream(h,packets)
            with self.subTest(packets=packets), LocalServer(respond) as server:
                client = OllamaClient(base_url=server.url)
                values, errors = self.result(client, lambda: client.translate('qwen3:4b', self.cues, DEFAULT_PROMPT))
                self.assertEqual(values, [])
                self.assertEqual(len(errors), 1)
                self.assertFalse(client.busy)
                self.assertEqual(len(server.requests), 2)

    def test_cancel_old_request_then_start_new_ignores_late_reply(self):
        def respond(h,p,d):
            if p == '/api/show':
                LocalServer.json(h,{})
            elif p == '/api/tags':
                LocalServer.json(h,{'models':[]})
            else:
                LocalServer.stream(h,[{'message':{'content':'OLD'},'done':False},
                    {'message':{'content':'LATE'},'done':True}],delay=.2)
        with LocalServer(respond) as server:
            client = OllamaClient(base_url=server.url)
            loop, replies, errors, models = QEventLoop(), [], [], []
            client.translated.connect(replies.append)
            client.failed.connect(errors.append)
            client.models_ready.connect(models.append)
            def restart(_):
                client.translation_progress.disconnect(restart)
                client.cancel()
                client.refresh_models()
            client.translation_progress.connect(restart)
            client.translate('qwen3:4b',self.cues,DEFAULT_PROMPT)
            QTimer.singleShot(700, loop.quit)
            loop.exec()
            self.assertEqual(replies, [])
            self.assertEqual(errors, [])
            self.assertEqual(models, [[]])
            self.assertFalse(client.busy)

    def test_timeout_and_redirect_do_not_retry_or_contact_redirect_target(self):
        def stalled(h,p,d):
            time.sleep(.2)
            LocalServer.json(h,{})
        with LocalServer(stalled) as server:
            client = OllamaClient(base_url=server.url)
            def start():
                client.refresh_models()
                client._idle.start(20)
            values, errors = self.result(client,start,'models_ready')
            self.assertEqual(values, [])
            self.assertEqual(len(errors),1)
            self.assertEqual(len(server.requests),1)
        def redirect(h,p,d):
            h.send_response(307)
            h.send_header('Location','http://127.0.0.1:1/should-not-contact')
            h.end_headers()
        with LocalServer(redirect) as server:
            client = OllamaClient(base_url=server.url)
            values, errors = self.result(client, client.refresh_models,'models_ready')
            self.assertEqual(values, [])
            self.assertIn('307', errors[0])
            self.assertEqual(len(server.requests),1)

    def test_only_loopback_and_local_models_are_accepted(self):
        for url in ('https://127.0.0.1:11434','http://example.com:11434','http://user@localhost:11434',
                    'http://localhost:11434/api','http://localhost:11434/?key=x'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                OllamaClient(base_url=url)
        client = OllamaClient()
        for model in ('qwen3:cloud','qwen3-cloud','https://other/model','bad model'):
            with self.subTest(model=model), self.assertRaises(ValueError):
                client.translate(model,self.cues,DEFAULT_PROMPT)
        self.assertFalse(client.busy)


if __name__ == '__main__':
    unittest.main()
