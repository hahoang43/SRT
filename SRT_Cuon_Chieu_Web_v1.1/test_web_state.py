"""Local QtWebEngine fixtures for blocks, manual restart and adaptive batches."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QUrl
from PySide6.QtWidgets import QApplication

from app import App
import gemini_web
import web_connect
from srt_engine import parse_srt, restore_progress
from web_state import WEB_BLOCK_JS


class WebStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setQuitOnLastWindowClosed(False)

    def window(self, provider='web'):
        with patch.object(App, '_load_active_web'):
            window = App(backend=provider)
        self.addCleanup(self.close_window, window)
        return window

    @staticmethod
    def close_window(window):
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def until(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            self.qt.processEvents()
            time.sleep(.005)
        self.assertTrue(predicate(), 'Local WebEngine fixture timed out')

    def html(self, window, html):
        loaded = []
        window.web_view.loadFinished.connect(loaded.append)
        window.web_view.setHtml(html)
        self.until(lambda: bool(loaded))
        window.web_view.loadFinished.disconnect(loaded.append)
        self.assertTrue(loaded[-1])

    def js(self, window, script, provider='web'):
        host = json.dumps('gemini.google.com' if provider == 'gemini_web' else 'chatgpt.com')
        script = script.replace('window.location.hostname', host).replace('location.hostname', host)
        values = []
        window._run_web_script(script, values.append)
        self.until(lambda: bool(values))
        return values[0]

    def test_challenge_blocks_probe_prepare_send_and_read_for_both_providers(self):
        for provider, adapter in (('web', web_connect), ('gemini_web', gemini_web)):
            with self.subTest(provider=provider):
                window = self.window(provider)
                self.html(window, '<form id="challenge-form">Verify you are human</form>'
                          '<textarea id="prompt-textarea">keep draft</textarea>')
                prepare = (adapter.make_send_message_js('new prompt', 1) if provider == 'gemini_web'
                           else adapter.make_send_message_js('new prompt'))
                for script in (adapter.PROBE_JS, prepare, adapter.SEND_MESSAGE_JS,
                               adapter.READ_LATEST_RESPONSE_JS):
                    self.assertEqual(self.js(window, script, provider)['blocked'], 'challenge')
                self.assertEqual(self.js(window, 'document.querySelector("textarea").value'), 'keep draft')

    def test_visible_captcha_and_rate_limit_but_not_quotes_or_hidden_challenges(self):
        window = self.window()
        for html, expected in (
                ('<iframe src="/recaptcha/api2/bframe"></iframe>', 'challenge'),
                ('<div role="alert">Too many requests</div>', 'rate_limit'),
                ('<div>You\'ve reached our limit</div>', 'rate_limit'),
                ('<h1>403 Forbidden</h1>', 'access_denied'),
                ('<div data-message-author-role="user">Too many requests</div>'
                 '<model-response>Access denied</model-response>'
                 '<pre>You\'ve reached our limit</pre><textarea>403 Forbidden</textarea>'
                 '<div id="challenge-form" hidden>Verify</div>'
                 '<iframe src="/recaptcha/api2/anchor" style="width:0;height:0;border:0"></iframe>'
                 '<style>.old-notice{display:none}</style><div class="old-notice">Too many requests</div>', None)):
            with self.subTest(expected=expected, html=html):
                self.html(window, html)
                result = self.js(window, WEB_BLOCK_JS)
                self.assertEqual(result.get('blocked') if result else None, expected)

    def test_block_invalidates_callbacks_and_keeps_checkpoint_and_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            window = self.window()
            source = '1\n00:00:01,000 --> 00:00:02,000\n你好\n\n2\n00:00:02,000 --> 00:00:03,000\n再见\n'
            window.path = Path(temp) / 'sample.srt'
            window.source_content = source
            window.model.load_cues(parse_srt(source))
            window.model.cues[0].translation = 'Xin chào'
            window.auto_session = True
            window.batch_waiting_for_json = True
            window.auto_batch = window.model.cues[1:]
            window.next_batch_timer.start(10000)
            profile = window.web_profile
            callbacks, accepted = [], []
            window._run_web_script = lambda script, callback: callbacks.append(callback)
            window._run_batch_script('pending', accepted.append)
            old_callback = callbacks.pop()
            window._run_batch_script('blocked', accepted.append)
            callbacks.pop()({'blocked': 'challenge', 'why': 'Xác minh CAPTCHA.'})
            old_callback({'site': True, 'text': 'stale'})
            self.assertEqual(accepted, [])
            self.assertFalse(window.auto_session)
            self.assertFalse(window.next_batch_timer.isActive())
            self.assertFalse(window.web_state_timer.isActive())
            self.assertIs(window.web_profile, profile)
            self.assertEqual(window._connection_state, 'blocked')
            restored = parse_srt(source)
            self.assertEqual(restore_progress(window.path, source, restored), 1)
            self.assertEqual(restored[0].translation, 'Xin chào')
            self.assertFalse(restored[1].translation)

    def test_redirect_and_http_403_stop_only_the_active_web_provider(self):
        from types import SimpleNamespace
        window = self.window()
        window.auto_session = True
        window._web_navigation_changed(window.web_view, QUrl('https://challenges.cloudflare.com/check'))
        self.assertFalse(window.auto_session)
        window.auto_session = True
        window._web_loading_changed(object(), SimpleNamespace(errorCode=lambda: 403))
        self.assertTrue(window.auto_session)
        window._web_loading_changed(window.web_view, SimpleNamespace(errorCode=lambda: 403))
        self.assertFalse(window.auto_session)

    def test_web_truncation_waits_until_generation_stops_then_halves_once(self):
        window = self.window()
        window.model.load_cues(parse_srt(
            '1\n00:00:01,000 --> 00:00:02,000\n你好\n\n'
            '2\n00:00:02,000 --> 00:00:03,000\n再见\n'))
        window.auto_session = True
        window.auto_batch_limit = 2
        window.auto_batch = window.model.cues[:]
        window.batch_waiting_for_json = True
        window.auto_baseline = 0
        window.auto_baseline_text = ''
        window.auto_diagnostic = None
        window._schedule_poll = lambda *args: None
        window.delay_spin.setValue(0)
        result = {'site': True, 'assistantCount': 1, 'lastText': 'new',
                  'text': '{"items":[{"id":1,"vi":"Xin chào"},{"id":2,"vi":"Tạm',
                  'generating': True, 'stopVisible': True}
        for _ in range(5):
            window._on_batch_response(result)
        self.assertEqual(window.auto_batch_limit, 2)
        self.assertFalse(window.next_batch_timer.isActive())
        result.update(generating=False, stopVisible=False)
        window._on_batch_response(result)
        self.assertEqual(window.auto_batch_limit, 1)
        self.assertFalse(any(c.translation for c in window.model.cues))
        self.assertTrue(window.next_batch_timer.isActive())
        window.next_batch_timer.stop()
        with patch.object(window, '_run_web_script'):
            window._queue_next_auto_batch()
        self.assertEqual([c.number for c in window.auto_batch], [1])

    def test_native_delayed_click_stops_when_challenge_appears_after_preparation(self):
        from native_chatgpt_bridge import WebBridge
        from test_native_chatgpt_bridge import FakeHandler
        window = self.window()
        self.html(window, '<textarea id="prompt-textarea"></textarea>'
                  '<button id="composer-submit-button" onclick="window.clicks++">Send</button>'
                  '<script>window.clicks=0;</script>')
        self.assertTrue(self.js(window, WebBridge(FakeHandler).send_js('prompt', 10))['ok'])
        # The native adapter scheduled its click. Expose a challenge before the
        # delayed callback, then execute that exact pending callback immediately.
        result = self.js(window, '''(() => {
            const challenge=document.createElement('form');
            challenge.id='challenge-form'; challenge.textContent='Verify';
            document.body.append(challenge);
            const state=window.__srtNativeState;
            clearTimeout(state.timer); state.check();
            return {clicks:window.clicks,failed:state.failed};
        })()''')
        self.assertEqual(result, {'clicks': 0, 'failed': True})


if __name__ == '__main__':
    unittest.main()
