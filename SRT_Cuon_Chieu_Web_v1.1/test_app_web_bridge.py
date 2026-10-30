"""Integration test: run with QT_QPA_PLATFORM=offscreen on headless machines."""
import unittest
import json
import time
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QEventLoop, QTimer, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from app import App
from web_connect import PROBE_JS, READ_LATEST_RESPONSE_JS
from srt_engine import parse_srt, extract_json, check_translations


class WebBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setQuitOnLastWindowClosed(False)

    def test_local_web_response_reaches_translation_table(self):
        window = App()
        loop = QEventLoop()
        values = []
        payload = '{"items":[{"id":1,"vi":"Xin chào"}]}'

        def received(result):
            values.append(result)
            loop.quit()

        def probed(result):
            values.append(result)
            # Only override the host check for this entirely local HTML fixture.
            window._run_web_script(
                READ_LATEST_RESPONSE_JS.replace('location.hostname', "'chatgpt.com'"),
                received)

        def loaded(ok):
            if not ok:
                loop.quit()
                return
            window._run_web_script(
                PROBE_JS.replace('window.location.hostname', "'chatgpt.com'"), probed)

        window.web_view.loadFinished.connect(loaded)
        window.web_view.setHtml(
            '<textarea id="prompt-textarea"></textarea><article>'
            '<div data-message-author-role="assistant"><div class="markdown">'
            'Kết quả: json<button>Copy code</button><pre><code>' + payload +
            '</code></pre></div></div></article>')
        deadline = QTimer()
        deadline.setSingleShot(True)
        deadline.timeout.connect(loop.quit)
        deadline.start(10000)
        loop.exec()
        deadline.stop()
        try:
            self.assertEqual(len(values), 2, values)
            probe, response = values
            self.assertTrue(probe['editor'])
            self.assertEqual(probe['assistantCount'], response['assistantCount'])
            self.assertEqual(response['text'], payload)
            window.model.load_cues(parse_srt('1\n00:00:01,000 --> 00:00:02,000\n你好\n'))
            mapping = check_translations(window.model.cues, extract_json(response['text']))
            window.apply_translations(mapping)
            self.assertEqual(window.model.cues[0].translation, 'Xin chào')
            notices = []
            window.show_notice = notices.append
            window._connection_state = 'looking_for_editor'
            window._on_probe(probe, 'looking_for_editor')
            self.assertEqual(window._connection_state, 'success')
            self.assertEqual(len(notices), 1)
            self.assertIn('THÀNH CÔNG', notices[0])
            window._finish_auto_session()
            self.assertFalse(window.batch_waiting_for_json)
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_guest_dom_without_author_role(self):
        window = App()
        loop = QEventLoop()
        values = []
        payload = '{"items":[{"id":1,"vi":"Chào bạn"}]}'
        html = ('<article data-testid="conversation-turn-1" data-turn="user">'
                '<div data-message-author-role="user"><div class="markdown">DO NOT READ</div></div></article>'
                '<article data-testid="conversation-turn-2"><div class="markdown">'
                + payload + '</div></article>')
        def received(value):
            values.append(value)
            loop.quit()
        def loaded(ok):
            if ok:
                window._run_web_script(READ_LATEST_RESPONSE_JS.replace('location.hostname', "'chatgpt.com'"), received)
            else:
                loop.quit()
        window.web_view.loadFinished.connect(loaded)
        window.web_view.setHtml(html)
        deadline = QTimer()
        deadline.setSingleShot(True)
        deadline.timeout.connect(loop.quit)
        deadline.start(10000)
        loop.exec()
        deadline.stop()
        try:
            self.assertEqual(len(values), 1)
            self.assertEqual(values[0]['assistantCount'], 1)
            self.assertEqual(values[0]['text'], payload)
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_guest_json_fallback_excludes_user_content(self):
        window = App()
        loop = QEventLoop()
        values = []
        payload = '{"items":[{"id":1,"vi":"Chào bạn"}]}'
        def received(value):
            values.append(value)
            loop.quit()
        def loaded(ok):
            if ok:
                window._run_web_script(READ_LATEST_RESPONSE_JS.replace('location.hostname', "'chatgpt.com'"), received)
            else:
                loop.quit()
        window.web_view.loadFinished.connect(loaded)
        window.web_view.setHtml('<main><div class="markdown">' + payload + '</div>'
            '<div data-turn="user"><div class="markdown">'
            '{"items":[{"id":1,"vi":"Do not import"}]}</div></div></main>')
        deadline = QTimer()
        deadline.setSingleShot(True)
        deadline.timeout.connect(loop.quit)
        deadline.start(10000)
        loop.exec()
        deadline.stop()
        try:
            self.assertEqual(len(values), 1)
            self.assertEqual(values[0]['text'], payload)
            self.assertEqual(values[0]['assistantCount'], 1)
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_plain_guest_conversation_without_message_selectors(self):
        window = App()
        loop = QEventLoop()
        values = []
        payload = '{"items":[{"id":1,"vi":"Chào \\"bạn\\" {mới}\\nHẹn gặp"}]}'
        # Realistic failure: no role, turn, markdown or pre/code nodes. Include
        # an unmarked user prompt with a valid example to detect false imports.
        example = '{"items":[{"id":123,"vi":"Không được nhập"}]}'
        prompt = 'Dịch phụ đề. Ví dụ: ' + example
        html = ('<main><section>' + prompt + '</section><section>'
                'Kết quả của bạn: <div>' + payload + '</div>Hoàn tất.</section>'
                '<form><textarea>' + example + '</textarea></form></main>')
        def received(value):
            values.append(value)
            loop.quit()
        def loaded(ok):
            if not ok:
                loop.quit()
                return
            script = ('window.__srtOutboundPrompt = ' + json.dumps(prompt) + ';')
            window._run_web_script('(() => {' + script + 'return true;})()', lambda _: read())
        def read():
            window._run_web_script(READ_LATEST_RESPONSE_JS.replace('location.hostname', "'chatgpt.com'"), received)
        window.web_view.loadFinished.connect(loaded)
        window.web_view.setHtml(html)
        deadline = QTimer()
        deadline.setSingleShot(True)
        deadline.timeout.connect(loop.quit)
        deadline.start(10000)
        loop.exec()
        deadline.stop()
        try:
            self.assertEqual(len(values), 1)
            result = values[0]
            self.assertEqual(result['assistantCount'], 1, result)
            self.assertEqual(json.loads(result['text']), json.loads(payload))
            self.assertEqual(result['diagnostics']['roles'], 0)
            self.assertEqual(result['diagnostics']['turns'], 0)
            self.assertEqual(result['diagnostics']['fallbackMatches'], 1)
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_plain_guest_fallback_rejects_partial_and_prompt_examples(self):
        cases = [
            '<main><div>{"items":[{"id":1,"vi":"Chưa xong"}</div></main>',
            '<main><div>{"items":[{"id":123,"vi":"..."}]}</div></main>',
            '<main><div data-turn="user">{"items":[{"id":1,"vi":"Prompt"}]}</div></main>',
            '<main><div>{"items":[{"id":1,"zh":"你好"}]}</div></main>',
        ]
        for html in cases:
            with self.subTest(html=html):
                window = App()
                loop = QEventLoop()
                values = []
                def received(value):
                    values.append(value)
                    loop.quit()
                def loaded(ok):
                    if ok:
                        window._run_web_script(READ_LATEST_RESPONSE_JS.replace('location.hostname', "'chatgpt.com'"), received)
                    else:
                        loop.quit()
                window.web_view.loadFinished.connect(loaded)
                window.web_view.setHtml(html)
                deadline = QTimer()
                deadline.setSingleShot(True)
                deadline.timeout.connect(loop.quit)
                deadline.start(10000)
                loop.exec()
                deadline.stop()
                try:
                    self.assertEqual(len(values), 1)
                    self.assertEqual(values[0]['assistantCount'], 0)
                    self.assertEqual(values[0]['text'], '')
                finally:
                    window.close()
                    window.deleteLater()
                    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_guest_page_sends_two_batches_and_populates_table(self):
        self._assert_two_batches('<textarea id="prompt-textarea"></textarea>')

    def test_generic_contenteditable_sends_two_batches(self):
        self._assert_two_batches('<div role="textbox" contenteditable="true"></div>')

    def test_native_adapter_sends_two_batches_without_builtin_double_send(self):
        from native_chatgpt_bridge import WebBridge
        from test_native_chatgpt_bridge import FakeHandler
        bridge = WebBridge(FakeHandler)
        with patch('app.WEB_BRIDGE',bridge), patch('app.PROBE_JS',bridge.probe_js), patch('app.READ_LATEST_RESPONSE_JS',bridge.read_js):
            self._assert_two_batches('<textarea id="prompt-textarea"></textarea>', native=True)

    def _assert_two_batches(self, editor_markup, native=False):
        window = App()
        loop = QEventLoop()
        notices = []
        window.model.load_cues(parse_srt(
            '1\n00:00:01,000 --> 00:00:02,000\n你好\n\n'
            '2\n00:00:02,000 --> 00:00:03,000\n再见\n'))
        window.batch_spin.setValue(1)
        window.delay_spin.setValue(0)
        # Run the production scripts on a local guest-page fixture.
        original = window._run_web_script
        window._run_web_script = lambda script, callback: original(
            script.replace('window.location.hostname', "'chatgpt.com'")
                  .replace('location.hostname', "'chatgpt.com'"), callback)
        def notice(message):
            notices.append(message)
            loop.quit()
        window.show_notice = notice
        failures = []
        def failed(message):
            failures.append(message)
            window.stop_translation()
            loop.quit()
        window._auto_failed = failed
        html = editor_markup + r'''
<button id="composer-submit-button" disabled>Send</button><main></main>
<script>
let sent = 0;
const editor = document.querySelector('textarea, [contenteditable]');
const button = document.querySelector('button');
editor.addEventListener('input', () => setTimeout(() => {button.disabled = false;}, NATIVE_READY ? 100 : (sent === 0 ? 1200 : 2200)));
button.onclick = () => {
  sent++;
  const turn = document.createElement('article');
  // Guest layout deliberately omits all role, turn and markdown selectors.
  const content = document.createElement('div');
  content.className = 'guest-reply';
  content.textContent = JSON.stringify({items:[{id:sent, vi:sent === 1 ? 'Xin chào' : 'Tạm biệt'}]});
  turn.appendChild(content); document.querySelector('main').appendChild(turn);
  if (editor.tagName === 'TEXTAREA') editor.value = ''; else editor.textContent = '';
  button.disabled = true;
};
</script>'''.replace('NATIVE_READY', 'true' if native else 'false')
        def loaded(ok):
            if ok:
                window.web_panel.show()  # Prevent start_translation from loading a remote page.
                window.start_translation()
            else:
                loop.quit()
        window.web_view.loadFinished.connect(loaded)
        window.show()
        window.web_panel.show()
        window.web_view.setHtml(html)
        deadline = QTimer()
        deadline.setSingleShot(True)
        deadline.timeout.connect(loop.quit)
        deadline.start(15000)
        loop.exec()
        deadline.stop()
        try:
            self.assertEqual(failures, [], window.log_text.toPlainText())
            self.assertEqual([c.translation for c in window.model.cues], ['Xin chào', 'Tạm biệt'])
            self.assertFalse(window.auto_session)
            self.assertEqual(len(notices), 1)
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def make_session(self):
        window = App()
        window.show_notice = lambda message: None
        window.model.load_cues(parse_srt(
            '1\n00:00:01,000 --> 00:00:02,000\n你好\n\n'
            '2\n00:00:02,000 --> 00:00:03,000\n别担心\n我帮你\n\n'
            '3\n00:00:03,000 --> 00:00:04,000\n再见\n'))
        window.auto_session = True
        window.auto_retries = {}
        window.delay_spin.setValue(0)
        window.batch_spin.setValue(2)
        window._schedule_poll = lambda *args: None
        # Avoid external browsing; drive only the app's actual batch callbacks.
        window._run_web_script = lambda script, callback: None
        return window

    def deliver(self, window, rows, *, count=1, text_prefix=''):
        window.auto_baseline = 0
        window.auto_baseline_text = ''
        result = {'assistantCount':count, 'text':text_prefix + json.dumps({'items':rows}),
                  'generating':False}
        window._on_batch_response(result)
        window._on_batch_response(result)

    def test_multiple_batches_and_retry_only_invalid_lines(self):
        window = self.make_session()
        try:
            window._queue_next_auto_batch()
            window._on_batch_probe({'site':True,'editor':True,'assistantCount':0}, 'prompt')
            self.deliver(window, [{'id':1,'vi':'Xin chào'}, {'id':2,'vi':'Sai số dòng'}],
                         text_prefix='Kết quả JSON:\n')
            self.assertEqual(window.model.cues[0].translation, 'Xin chào')
            self.assertEqual(window.model.cues[1].translation, '')
            self.assertTrue(window.next_batch_timer.isActive())
            window.next_batch_timer.stop()
            window._queue_next_auto_batch()
            self.assertEqual([c.number for c in window.auto_batch], [2])
            self.deliver(window, [{'id':2,'vi':'Đừng lo\nTôi giúp bạn'}])
            window.next_batch_timer.stop()
            window._queue_next_auto_batch()
            self.assertEqual([c.number for c in window.auto_batch], [3])
            self.deliver(window, [{'id':3,'vi':'Tạm biệt'}])
            self.assertFalse(window.auto_session)
            self.assertFalse(window.batch_waiting_for_json)
            self.assertEqual(len(window._missing()), 0)
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_streaming_extends_idle_timeout_and_old_reply_is_ignored(self):
        window = self.make_session()
        try:
            window._queue_next_auto_batch()
            window.auto_baseline = 1
            window.auto_baseline_text = 'old'
            window.auto_deadline = time.monotonic() + 1
            window._on_batch_response({'assistantCount':1, 'text':'old', 'lastText':'old', 'generating':False})
            self.assertEqual(window.auto_last_response, '')
            window._on_batch_response({'assistantCount':1, 'text':'new partial', 'lastText':'new partial', 'generating':True})
            self.assertGreater(window.auto_deadline, time.monotonic() + 10)
            self.assertEqual(len(window._missing()), 3)
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_reply_visible_once_is_checkpointed_before_dom_disappears(self):
        window = self.make_session()
        try:
            with tempfile.TemporaryDirectory() as folder:
                window.path = Path(folder) / 'source.srt'
                window.source_content = 'test source'
                window._queue_next_auto_batch()
                window.auto_baseline = 0
                window.auto_baseline_text = ''
                text = json.dumps({'items':[{'id':1,'vi':'Xin chào'},
                                             {'id':2,'vi':'Đừng lo\nTôi giúp bạn'}]})
                window._on_batch_response({'site':True,'assistantCount':1,'text':text,
                    'lastText':text,'generating':True,'stopVisible':True})
                checkpoint = json.loads(window.path.with_suffix('.progress.json').read_text(encoding='utf-8'))
                self.assertEqual(checkpoint['translations'], {'1':'Xin chào','2':'Đừng lo\nTôi giúp bạn'})
                self.assertTrue(window.batch_waiting_for_json)
                self.assertFalse(window.next_batch_timer.isActive())
                # Exact shape of the user's log: 1 complete reply -> 0 replies.
                window._on_batch_response({'site':True,'assistantCount':0,'text':'',
                    'lastText':'','generating':False,'stopVisible':False})
                self.assertFalse(window.batch_waiting_for_json)
                self.assertTrue(window.next_batch_timer.isActive())
                window.next_batch_timer.stop()
                window._queue_next_auto_batch()
                self.assertEqual([cue.number for cue in window.auto_batch], [3])
                self.assertIsNone(window.auto_received)
        finally:
            window.path = None
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_invalid_transient_reply_is_never_cached(self):
        cases = [
            {'items':[{'id':1,'vi':'Chào'}]},  # missing ID 2
            {'items':[{'id':1,'vi':'Chào'},{'id':2,'vi':'Gộp sai dòng'}]},
            {'items':[{'id':1,'vi':'Chào'},{'id':1,'vi':'Trùng'}]},
            {'items':[{'id':99,'vi':'Sai lô'}]},
        ]
        for data in cases:
            with self.subTest(data=data):
                window = self.make_session()
                try:
                    window._queue_next_auto_batch()
                    window.auto_baseline = 0
                    window.auto_baseline_text = ''
                    text = json.dumps(data)
                    window._on_batch_response({'site':True,'assistantCount':1,'text':text,
                        'lastText':text,'generating':True,'stopVisible':True})
                    window._on_batch_response({'site':True,'assistantCount':0,'text':'',
                        'lastText':'','generating':False,'stopVisible':False})
                    self.assertIsNone(window.auto_received)
                    self.assertEqual([c.translation for c in window.model.cues], ['', '', ''])
                    self.assertTrue(window.batch_waiting_for_json)
                    self.assertFalse(window.next_batch_timer.isActive())
                finally:
                    window.close()
                    window.deleteLater()
                    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_stop_preserves_early_checkpoint_and_drops_pending_batch(self):
        window = self.make_session()
        try:
            window.batch_spin.setValue(1)
            window._queue_next_auto_batch()
            window.auto_baseline = 0
            window.auto_baseline_text = ''
            text = '{"items":[{"id":1,"vi":"Xin chào"}]}'
            window._on_batch_response({'site':True,'assistantCount':1,'text':text,
                'lastText':text,'generating':True,'stopVisible':True})
            window.stop_translation()
            self.assertEqual(window.model.cues[0].translation, 'Xin chào')
            self.assertIsNone(window.auto_received)
            self.assertFalse(window.next_batch_timer.isActive())
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_cooldown_notice_detection_in_real_dom_excludes_user_and_code(self):
        clock = datetime.fromtimestamp(time.time()+120).strftime('%I:%M %p')
        message = "We're doing a quick check to keep ChatGPT reliable. Try again after " + clock + '.'
        cases = [('<p role="alert">'+message+'</p>',True),
                 ('<form><p>'+message+'</p><textarea></textarea></form>',True),
                 ('<div data-turn="user">'+message+'</div>',False),
                 ('<pre>'+message+'</pre>',False),
                 ('<p hidden>'+message+'</p>',False)]
        for markup, blocked in cases:
            with self.subTest(blocked=blocked,markup=markup):
                window = App()
                loop = QEventLoop()
                values = []
                def received(value):
                    values.append(value)
                    loop.quit()
                def loaded(ok):
                    if ok:
                        window._run_web_script(PROBE_JS.replace('window.location.hostname', "'chatgpt.com'").replace('location.hostname', "'chatgpt.com'"), received)
                    else:
                        loop.quit()
                window.web_view.loadFinished.connect(loaded)
                window.web_view.setHtml(markup+'<textarea id="prompt-textarea"></textarea>')
                deadline = QTimer()
                deadline.setSingleShot(True)
                deadline.timeout.connect(loop.quit)
                deadline.start(10000)
                loop.exec()
                deadline.stop()
                try:
                    self.assertEqual(len(values),1)
                    self.assertEqual(values[0].get('cooldown',False),blocked)
                    if blocked:
                        self.assertGreater(values[0]['retryAt'],time.time())
                    else:
                        self.assertTrue(values[0]['editor'])
                finally:
                    window.close()
                    window.deleteLater()
                    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_service_notice_pauses_all_sends_until_deadline_then_resumes(self):
        window = self.make_session()
        scripts = []
        window._run_web_script = lambda script, callback: scripts.append((script,callback))
        try:
            window._queue_next_auto_batch()
            expiry = time.time() + 60
            scripts[0][1]({'cooldown':True,'retryAt':expiry,'clock':'15:05'})
            self.assertEqual(window.auto_send_state,'cooldown')
            self.assertTrue(window.service_wait_timer.isActive())
            self.assertFalse(window.batch_waiting_for_json)
            self.assertEqual(len(scripts),1)
            window._queue_next_auto_batch()
            window._tick_service_wait()
            self.assertEqual(len(scripts),1)
            with patch('app.time.time',return_value=expiry+1):
                window._tick_service_wait()
            self.assertFalse(window.service_wait_timer.isActive())
            self.assertEqual(len(scripts),2)
            self.assertEqual(scripts[1][0],PROBE_JS)
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_stop_cancels_cooldown_resume_and_preserves_translations(self):
        window = self.make_session()
        scripts = []
        window._run_web_script = lambda script, callback: scripts.append(script)
        try:
            window.model.cues[0].translation = 'Xin chào'
            expiry = time.time()+60
            window._wait_for_service({'cooldown':True,'retryAt':expiry})
            window.stop_translation()
            with patch('app.time.time',return_value=expiry+1):
                window._tick_service_wait()
            self.assertEqual(scripts,[])
            self.assertEqual(window.model.cues[0].translation,'Xin chào')
            self.assertFalse(window.service_wait_timer.isActive())
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_editor_detection_uses_writable_node_not_wrapper_or_disabled_field(self):
        cases = [
            ('<div id="prompt-textarea"><div contenteditable="true"></div></div>', True, 'div'),
            ('<div role="textbox" contenteditable="plaintext-only"></div>', True, 'div'),
            ('<textarea id="prompt-textarea" readonly></textarea>', False, ''),
            ('<textarea id="prompt-textarea" disabled></textarea>', False, ''),
            ('<div id="prompt-textarea" contenteditable="false"></div>', False, ''),
            ('<div contenteditable="true" style="display:none"></div>', False, ''),
        ]
        for html, ready, kind in cases:
            with self.subTest(html=html):
                window = App()
                loop = QEventLoop()
                values = []
                def received(value):
                    values.append(value)
                    loop.quit()
                def loaded(ok):
                    if ok:
                        window._run_web_script(PROBE_JS.replace('window.location.hostname', "'chatgpt.com'"), received)
                    else:
                        loop.quit()
                window.web_view.loadFinished.connect(loaded)
                window.web_view.setHtml(html)
                deadline = QTimer()
                deadline.setSingleShot(True)
                deadline.timeout.connect(loop.quit)
                deadline.start(10000)
                loop.exec()
                deadline.stop()
                try:
                    self.assertEqual(len(values), 1)
                    self.assertEqual(values[0]['editor'], ready)
                    self.assertEqual(values[0]['editorKind'], kind)
                finally:
                    window.close()
                    window.deleteLater()
                    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_editor_wait_retries_without_sending_then_prepares_once_ready(self):
        window = self.make_session()
        timers, scripts = [], []
        window._run_web_script = lambda script, callback: scripts.append((script, callback))
        try:
            window._queue_next_auto_batch()
            scripts.clear()
            with patch('app.QTimer.singleShot', side_effect=lambda delay, fn: timers.append(fn)):
                window._on_batch_probe({'site':True,'editor':False}, 'prompt')
                self.assertTrue(window.auto_session)
                self.assertEqual(scripts, [])
                timers.pop()()
            self.assertEqual(scripts[0][0], PROBE_JS)
            scripts[0][1]({'site':True,'editor':True,'assistantCount':0})
            self.assertEqual(len(scripts), 2)
            self.assertIn('insertText', scripts[1][0])
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_editor_wait_timeout_and_stop_never_send_a_batch(self):
        for stop in (False, True):
            with self.subTest(stop=stop):
                window = self.make_session()
                scripts, timers, failures = [], [], []
                def failed(message):
                    failures.append(message)
                    window.stop_translation()
                window._auto_failed = failed
                window._run_web_script = lambda script, callback: scripts.append(script)
                try:
                    window._queue_next_auto_batch()
                    scripts.clear()
                    with patch('app.QTimer.singleShot', side_effect=lambda delay, fn: timers.append(fn)):
                        window._on_batch_probe({'site':True,'editor':False}, 'prompt')
                    window.auto_editor_deadline = time.monotonic() - 1
                    if stop:
                        window.stop_translation()
                        timers[-1]()
                        self.assertEqual(failures, [])
                    else:
                        window._on_batch_probe({'site':True,'editor':False}, 'prompt')
                        self.assertEqual(len(failures), 1)
                        self.assertIn('ô chat', failures[0])
                    self.assertEqual(scripts, [])
                finally:
                    window.close()
                    window.deleteLater()
                    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_send_waits_when_disabled_and_success_is_processed_once(self):
        window = self.make_session()
        scheduled, polls = [], []
        window._schedule_send = lambda delay=500: scheduled.append(delay)
        window._schedule_poll = polls.append
        try:
            window.auto_batch = window.model.cues[:1]
            window.auto_send_state = 'checking'
            window.auto_send_deadline = time.monotonic() + 30
            window.auto_send_reason = ''
            window._on_batch_sent({'ok':False, 'retryable':True, 'why':'Nút gửi đang bị vô hiệu hóa.'})
            self.assertTrue(window.auto_session)
            self.assertEqual(window.auto_send_state, 'waiting')
            self.assertEqual(scheduled, [500])
            window.auto_send_state = 'checking'
            window._on_batch_sent({'ok':True})
            self.assertEqual(window.auto_send_state, 'sent')
            self.assertEqual(polls, [1500])
            window._on_batch_sent({'ok':True})
            self.assertEqual(polls, [1500])
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_waiting_send_times_out_without_clicking_or_losing_translations(self):
        window = self.make_session()
        timers, failures, scripts = [], [], []
        window.model.cues[0].translation = 'Xin chào'
        window._run_web_script = lambda script, callback: scripts.append(script)
        def failed(message):
            failures.append(message)
            window.stop_translation()
        window._auto_failed = failed
        try:
            window.auto_send_state = 'waiting'
            window.auto_send_deadline = time.monotonic() - 1
            window.auto_send_reason = 'Nút gửi đang bị vô hiệu hóa.'
            with patch('app.QTimer.singleShot', side_effect=lambda delay, fn: timers.append(fn)):
                window._schedule_send()
            timers[0]()
            self.assertEqual(len(failures), 1)
            self.assertEqual(scripts, [])
            self.assertFalse(window.auto_session)
            self.assertEqual(window.model.cues[0].translation, 'Xin chào')
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_stopped_session_cancels_pending_send(self):
        window = self.make_session()
        timers, scripts = [], []
        window._run_web_script = lambda script, callback: scripts.append(script)
        try:
            window.auto_send_state = 'waiting'
            window.auto_send_deadline = time.monotonic() + 30
            with patch('app.QTimer.singleShot', side_effect=lambda delay, fn: timers.append(fn)):
                window._schedule_send()
            window.stop_translation()
            window.auto_session = True
            timers[0]()
            self.assertEqual(scripts, [])
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_missing_javascript_callback_stops_with_diagnostic(self):
        window = self.make_session()
        timers, failures = [], []
        window.batch_waiting_for_json = True
        def failed(message):
            failures.append(message)
            window.stop_translation()
        window._auto_failed = failed
        try:
            with patch('app.QTimer.singleShot', side_effect=lambda delay, fn: timers.append(fn)):
                window._run_batch_script('script', window._on_batch_response)
            self.assertEqual(len(timers), 1)
            timers[0]()
            self.assertFalse(window.auto_session)
            self.assertEqual(len(failures), 1)
            self.assertIn('10 giây', failures[0])
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_stale_streaming_class_does_not_block_complete_translation(self):
        window = self.make_session()
        try:
            window.batch_spin.setValue(1)
            window._queue_next_auto_batch()
            window.auto_baseline = 0
            window.auto_baseline_text = ''
            result = {'assistantCount':1, 'text':'{"items":[{"id":1,"vi":"Xin chào"}]}',
                      'lastText':'new', 'generating':True, 'stopVisible':False}
            for _ in range(3):
                window._on_batch_response(result)
                self.assertEqual(window.model.cues[0].translation, 'Xin chào')
                self.assertFalse(window.next_batch_timer.isActive())
            window._on_batch_response(result)
            self.assertEqual(window.model.cues[0].translation, 'Xin chào')
            self.assertTrue(window.next_batch_timer.isActive())
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_visible_stop_button_blocks_next_batch(self):
        window = self.make_session()
        try:
            window.batch_spin.setValue(1)
            window._queue_next_auto_batch()
            window.auto_baseline = 0
            window.auto_baseline_text = ''
            result = {'assistantCount':1, 'text':'{"items":[{"id":1,"vi":"Xin chào"}]}',
                      'lastText':'new', 'generating':True, 'stopVisible':True}
            for _ in range(5):
                window._on_batch_response(result)
            self.assertEqual(window.model.cues[0].translation, 'Xin chào')
            self.assertFalse(window.next_batch_timer.isActive())
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_stopped_session_ignores_pending_web_callback(self):
        window = self.make_session()
        callbacks, received = [], []
        window._run_web_script = lambda script, callback: callbacks.append(callback)
        try:
            window._run_batch_script('test', received.append)
            window.stop_translation()
            window.auto_session = True
            callbacks[0]({'ok':True})
            self.assertEqual(received, [])
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_retries_are_bounded_and_valid_translations_retained(self):
        window = self.make_session()
        failures = []
        def failed(message):
            failures.append(message)
            window.stop_translation()
        window._auto_failed = failed
        try:
            for attempt in range(3):
                window._queue_next_auto_batch()
                self.deliver(window, [{'id':1,'vi':'Xin chào'}, {'id':2,'vi':'Sai số dòng'}])
                window.next_batch_timer.stop()
            self.assertEqual(len(failures), 1)
            self.assertIn('2 lần thử lại', failures[0])
            self.assertEqual(window.model.cues[0].translation, 'Xin chào')
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == '__main__':
    unittest.main()
