"""Integration test: run with QT_QPA_PLATFORM=offscreen on headless machines."""
import unittest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from app import App
from web_connect import PROBE_JS, READ_LATEST_RESPONSE_JS
from srt_engine import parse_srt, extract_json, check_translations


class WebBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

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


if __name__ == '__main__':
    unittest.main()
