"""Real QtWebEngine fixtures for Gemini Web; never log in or contact Google."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from app import App
import gemini_web
from response_capture import with_reply_capture, read_with_capture
from srt_engine import parse_srt, restore_progress


class GeminiWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setQuitOnLastWindowClosed(False)

    def window(self):
        with patch.object(App, '_load_active_web'):
            window = App(backend='gemini_web')
        # Override only the domain guard for local setHtml fixtures. Execute the
        # production JS, DOM adapter, controller, and checkpoint code unchanged.
        run = window._run_web_script
        window._run_web_script = lambda script, callback: run(
            script.replace('location.hostname', "'gemini.google.com'"), callback)
        self.addCleanup(self.close_window, window)
        return window

    @staticmethod
    def close_window(window):
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def until(self, predicate, seconds=4):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            self.qt.processEvents()
            time.sleep(.005)
        self.assertTrue(predicate(), 'Timed out waiting for QtWebEngine fixture')

    def html(self, window, html):
        loaded = []
        window.web_view.loadFinished.connect(loaded.append)
        window.web_view.setHtml(html)
        self.until(lambda: bool(loaded))
        window.web_view.loadFinished.disconnect(loaded.append)
        self.assertTrue(loaded[-1])

    def js(self, window, script, *, actual_host=False):
        result = []
        if actual_host:
            window.web_view.page().runJavaScript(
                'JSON.stringify(' + script + ')', lambda value: result.append(json.loads(value)))
        else:
            window._run_web_script(script, result.append)
        self.until(lambda: bool(result))
        return result[0]

    def test_selection_shows_web_without_key_and_isolates_chatgpt_cookies(self):
        with patch.object(App, '_load_active_web') as load:
            window = App(backend='gemini_web')
        self.addCleanup(self.close_window, window)
        self.assertEqual(load.call_count, 1)
        self.assertFalse(window.web_panel.isHidden())
        self.assertTrue(window.gemini_controls.isHidden())
        self.assertTrue(window.web_btn.isVisibleTo(window.centralWidget()))
        self.assertIn('Gemini', window.connect_btn.text())
        gemini_view = window.web_view
        gemini_profile = window.web_profile
        self.assertIn('gemini_profile', gemini_profile.persistentStoragePath())
        with patch.object(App, '_load_active_web'):
            window.backend_box.setCurrentIndex(window.backend_box.findData('web'))
        self.assertIsNot(window.web_view, gemini_view)
        self.assertIn('chatgpt_profile', window.web_profile.persistentStoragePath())
        self.assertNotEqual(window.web_profile.persistentStoragePath(), gemini_profile.persistentStoragePath())
        with patch.object(App, '_load_active_web'):
            window.backend_box.setCurrentIndex(window.backend_box.findData('gemini_web'))
        self.assertIs(window.web_view, gemini_view)
        self.assertIs(window.web_profile, gemini_profile)

    def test_switching_back_restores_visible_chatgpt_and_existing_page(self):
        with patch.object(App, '_load_active_web') as load:
            window = App(backend='web')
            self.addCleanup(self.close_window, window)
            window.show()
            window.toggle_web()
            self.html(window, '<textarea id="prompt-textarea">Bản nháp ChatGPT</textarea>')
            window._loaded_providers.add('web')
            chatgpt_view, chatgpt_profile = window.web_view, window.web_profile
            window.backend_box.setCurrentIndex(window.backend_box.findData('gemini_web'))
            self.assertTrue(window.web_panel.isVisible())
            load.reset_mock()
            window.backend_box.setCurrentIndex(window.backend_box.findData('web'))
            self.assertTrue(window.web_panel.isVisible())
            self.assertIs(window.web_view, chatgpt_view)
            self.assertIs(window.web_profile, chatgpt_profile)
            self.assertIs(window.web_stack.currentWidget(), chatgpt_view)
            self.assertIn('CHATGPT', window.web_heading.text())
            self.assertEqual(self.js(window, 'document.querySelector("textarea").value'), 'Bản nháp ChatGPT')
            load.assert_not_called()

    def test_dedicated_chatgpt_button_remains_available_in_every_backend(self):
        with patch.object(App, '_load_active_web'):
            window = App(backend='gemini')
            self.addCleanup(self.close_window, window)
            window.show()
            for backend in ('gemini', 'gemini_web', 'web'):
                with self.subTest(backend=backend):
                    window.backend_box.setCurrentIndex(window.backend_box.findData(backend))
                    self.assertTrue(window.chatgpt_btn.isVisible())
                    self.assertTrue(window.gemini_web_btn.isVisible())
                    self.assertIn('ChatGPT', window.chatgpt_btn.text())
                    with patch.object(window, 'connect_and_open') as connect:
                        window.chatgpt_btn.click()
                        self.assertEqual(window.backend_box.currentData(), 'web')
                        connect.assert_called_once()
            with patch.object(window, 'connect_and_open') as connect:
                window.gemini_web_btn.click()
                self.assertEqual(window.backend_box.currentData(), 'gemini_web')
                connect.assert_called_once()

    def test_probe_is_read_only_and_does_not_accept_login_form(self):
        window = self.window()
        self.html(window, '<form><textarea></textarea><button type="submit">Sign in</button></form>')
        self.assertFalse(self.js(window, gemini_web.PROBE_JS)['editor'])
        self.assertFalse(self.js(window, gemini_web.PROBE_JS, actual_host=True)['site'])
        self.assertNotIn('.click(', gemini_web.PROBE_JS)
        self.html(window, '<rich-textarea><div class="ql-editor" contenteditable="true"></div></rich-textarea>')
        self.assertTrue(self.js(window, gemini_web.PROBE_JS)['editor'])
        notices = []
        window.show_notice = notices.append
        with patch('app.load_web_bridge') as native, patch.object(window.gemini, 'refresh_models') as api:
            window.connect_and_open()
            self.until(lambda: bool(notices))
            native.assert_not_called()
            api.assert_not_called()
        self.assertIn('GEMINI WEB', notices[0])

    def test_login_popup_shares_gemini_profile_and_closes_with_app(self):
        window = self.window()
        pages = []
        class Request:
            def openIn(self, page):
                pages.append(page)
        window._open_web_popup(Request(), window.web_profile)
        self.assertEqual(len(pages), 1)
        self.assertIs(pages[0].profile(), window.web_profile)
        self.assertEqual(len(window._web_popups), 1)
        window.close()
        self.assertEqual(window._web_popups, [])

    def test_prepare_preserves_literal_prompt_and_send_clicks_only_once(self):
        window = self.window()
        self.html(window, '''<rich-textarea><div class="ql-editor" contenteditable="true"></div></rich-textarea>
            <button class="send-button" disabled onclick="window.clicked=(window.clicked||0)+1">Send</button>''')
        prompt = 'Dịch ` ${x} REQUEST_ID "quotes"\\\n你好\nXin chào'
        self.assertTrue(self.js(window, gemini_web.make_send_message_js(prompt, 42))['ok'])
        actual = self.js(window, 'document.querySelector(".ql-editor").innerText')
        self.assertEqual(actual, prompt)
        self.assertTrue(self.js(window, gemini_web.SEND_MESSAGE_JS)['retryable'])
        self.js(window, '(() => {document.querySelector("button").disabled=false; return true;})()')
        self.assertTrue(self.js(window, gemini_web.SEND_MESSAGE_JS)['ok'])
        self.assertTrue(self.js(window, gemini_web.SEND_MESSAGE_JS)['alreadySent'])
        self.assertEqual(self.js(window, 'window.clicked'), 1)
        self.assertFalse(self.js(window, gemini_web.make_send_message_js(prompt, 42))['ok'])

    def test_changed_draft_and_visible_stop_prevent_send(self):
        window = self.window()
        self.html(window, '''<rich-textarea><div class="ql-editor" contenteditable="true"></div></rich-textarea>
            <button class="send-button" onclick="window.clicked=true">Send</button>
            <button class="stop-button">Stop</button>''')
        self.assertTrue(self.js(window, gemini_web.make_send_message_js('batch', 1))['ok'])
        self.assertTrue(self.js(window, gemini_web.SEND_MESSAGE_JS)['retryable'])
        self.js(window, '(() => {document.querySelector(".stop-button").remove(); document.querySelector(".ql-editor").innerText="manual"; return true;})()')
        self.assertFalse(self.js(window, gemini_web.SEND_MESSAGE_JS)['ok'])
        self.assertFalse(self.js(window, gemini_web.make_send_message_js('other batch', 2))['ok'])
        self.assertFalse(self.js(window, '!!window.clicked'))

    def test_reader_ignores_user_json_and_reads_only_model_response(self):
        window = self.window()
        payload = '{"items":[{"id":1,"vi":"Xin chào"}]}'
        self.html(window, '<main><user-query>' + payload + '</user-query></main>')
        self.assertEqual(self.js(window, gemini_web.READ_LATEST_RESPONSE_JS)['text'], '')
        self.html(window, '<main><user-query>user example</user-query><model-response>'
                  '<div class="model-response-text">json Copy code<pre><code>' + payload +
                  '</code></pre></div></model-response></main><button class="stop-button">Stop</button>')
        result = self.js(window, gemini_web.READ_LATEST_RESPONSE_JS)
        self.assertEqual(result['text'], payload)
        self.assertEqual(result['assistantCount'], 1)
        self.assertTrue(result['generating'])

    def test_capture_ignores_transient_user_json_but_retains_model_json(self):
        window = self.window()
        cues = parse_srt('1\n00:00:01,000 --> 00:00:02,000\n你好\n')
        payload = '{"items":[{"id":1,"vi":"Xin chào"}]}'
        for tag, captured in [('user-query', False), ('model-response', True)]:
            with self.subTest(tag=tag):
                self.html(window, '<main><div id="messages"></div></main>')
                self.js(window, with_reply_capture('({ok:true})', cues, 99))
                self.js(window, '''(() => {
                    const node=document.createElement(TAG); node.textContent=PAYLOAD;
                    document.querySelector('#messages').appendChild(node);
                    setTimeout(()=>node.remove(),0); return true;
                })()'''.replace('TAG', json.dumps(tag)).replace('PAYLOAD', json.dumps(payload)))
                result = self.js(window, read_with_capture(gemini_web.READ_LATEST_RESPONSE_JS, 99))
                self.assertEqual(bool(result.get('captured')), captured)

    def test_two_batches_reach_table_and_checkpoint_without_native_or_api(self):
        window = self.window()
        html = '''<main><div id="messages"></div></main>
            <rich-textarea><div class="ql-editor" contenteditable="true"></div></rich-textarea>
            <button class="send-button">Send</button>
            <script>
            window.batches=[];
            document.querySelector('button').onclick=()=>{
              const editor=document.querySelector('.ql-editor');
              const prompt=editor.innerText;
              const rows=JSON.parse(prompt.split('DỮ LIỆU JSON:\\n')[1]);
              window.batches.push(rows.map(row=>row.id));
              const user=document.createElement('user-query'); user.textContent=prompt;
              const reply=document.createElement('model-response');
              reply.innerHTML='<div class="model-response-text"></div>';
              document.querySelector('#messages').append(user,reply); editor.textContent='';
              reply.firstChild.textContent=JSON.stringify({items:rows.map(row=>({id:row.id,vi:row.id===1?'Xin chào':'Tạm biệt'}))});
            };
            </script>'''
        self.html(window, html)
        source = '1\n00:00:01,000 --> 00:00:02,000\n你好\n\n2\n00:00:03,000 --> 00:00:04,000\n再见\n'
        with tempfile.TemporaryDirectory() as temp:
            window.path = Path(temp) / 'sample.srt'
            window.path.write_text(source)
            window.source_content = source
            window.model.load_cues(parse_srt(source))
            window.batch_spin.setValue(1)
            window.delay_spin.setValue(0)
            notices, failures = [], []
            window.show_notice = notices.append
            with (patch('app.load_web_bridge') as native, patch('app.WEB_BRIDGE') as bridge,
                  patch.object(window.gemini, 'translate') as api,
                  patch('app.QMessageBox.warning', side_effect=lambda p,t,m: failures.append(m))):
                bridge.native = True  # Even a loaded ChatGPT binary must never serve Gemini.
                window.start_translation()
                self.until(lambda: not window.auto_session, seconds=10)
                native.assert_not_called()
                api.assert_not_called()
            self.assertEqual(failures, [])
            self.assertEqual(len(notices), 1)
            self.assertEqual(self.js(window, 'window.batches'), [[1], [2]])
            self.assertEqual([cue.translation for cue in window.model.cues], ['Xin chào', 'Tạm biệt'])
            restored = parse_srt(source)
            self.assertEqual(restore_progress(window.path, source, restored), 2)
            self.assertEqual([cue.time_range for cue in restored], [cue.time_range for cue in parse_srt(source)])


if __name__ == '__main__':
    unittest.main()
