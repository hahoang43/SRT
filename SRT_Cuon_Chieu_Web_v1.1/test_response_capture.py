import json
import unittest
from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from app import App
from response_capture import with_reply_capture, read_with_capture, STOP_CAPTURE_JS
from srt_engine import parse_srt, check_translations, extract_json
from web_connect import READ_LATEST_RESPONSE_JS


class ReplyCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setQuitOnLastWindowClosed(False)

    def run_capture(self, transient, *, initial='', read_id=17, stop=False):
        window = App()
        loop = QEventLoop()
        values = []
        cues = parse_srt('1\n00:00:01,000 --> 00:00:02,000\n你好\n')
        # Add and remove the response between polls, in separate browser tasks.
        action = """(() => {
          setTimeout(() => {
            const reply=document.createElement('section');
            reply.textContent=PAYLOAD;
            document.querySelector('main').appendChild(reply);
            setTimeout(()=>reply.remove(),0);
          },0);
          return {ok:true};
        })()""".replace('PAYLOAD',json.dumps(transient,ensure_ascii=False))
        def received(value):
            values.append(value)
            loop.quit()
        def read():
            script = read_with_capture(READ_LATEST_RESPONSE_JS,read_id)
            window._run_web_script(script.replace('location.hostname',"'chatgpt.com'"),received)
        def installed(_):
            if stop:
                window.web_view.page().runJavaScript(STOP_CAPTURE_JS)
            QTimer.singleShot(300,read)
        def loaded(ok):
            if ok:
                script = with_reply_capture(action,cues,17)
                window._run_web_script(script.replace('location.hostname',"'chatgpt.com'"),installed)
            else:
                loop.quit()
        window.web_view.loadFinished.connect(loaded)
        window.web_view.setHtml('<main>'+initial+'</main>')
        deadline=QTimer()
        deadline.setSingleShot(True)
        deadline.timeout.connect(loop.quit)
        deadline.start(10000)
        loop.exec()
        deadline.stop()
        try:
            self.assertEqual(len(values),1)
            return values[0],cues
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_complete_reply_is_retained_even_after_dom_removes_it_between_polls(self):
        payload='{"items":[{"id":1,"vi":"Xin chào"}]}'
        result,cues=self.run_capture(payload)
        self.assertTrue(result['captured'])
        self.assertEqual(result['assistantCount'],0)
        self.assertEqual(check_translations(cues,extract_json(result['text'])),{1:'Xin chào'})

    def test_old_reply_cannot_be_reimported_from_parent_mutation(self):
        payload='{"items":[{"id":1,"vi":"Câu cũ"}]}'
        result,_=self.run_capture('đang tải',initial='<section>'+payload+'</section>')
        self.assertFalse(result.get('captured',False))

    def test_invalid_or_wrong_batch_json_is_not_retained(self):
        for payload in ('{"items":[{"id":99,"vi":"Sai lô"}]}',
                        '{"items":[{"id":1,"vi":"Bị cắt"}',
                        '{"items":[{"id":1,"vi":"Sai\\nhai dòng"}]}'):
            with self.subTest(payload=payload):
                result,_=self.run_capture(payload)
                self.assertFalse(result.get('captured',False))
                self.assertEqual(result['text'],'')

    def test_other_request_id_cannot_use_previous_capture(self):
        result,_=self.run_capture('{"items":[{"id":1,"vi":"Xin chào"}]}',read_id=18)
        self.assertFalse(result.get('captured',False))
        self.assertEqual(result['text'],'')
