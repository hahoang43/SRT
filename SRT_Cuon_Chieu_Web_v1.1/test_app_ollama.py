"""Local Ollama HTTP -> production SRT controller -> checkpoint/export."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication

from app import App
from ollama_backend import OllamaClient
from srt_engine import parse_srt, restore_progress, srt_contents
from test_ollama_backend import LocalServer

SOURCE = ('1\n00:00:01,000 --> 00:00:02,000\n你好\n\n'
          '2\n00:00:02,000 --> 00:00:03,000\n别担心\n我帮你\n\n'
          '3\n00:00:03,000 --> 00:00:04,000\n再见\n')
VI = {1:'Xin chào',2:'Đừng lo\nTôi giúp bạn',3:'Tạm biệt'}


class AppOllamaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setQuitOnLastWindowClosed(False)

    def window(self, server, temp):
        with patch('app.WEB_AVAILABLE',False):
            window = App(backend='ollama')
        window.ollama.deleteLater()
        window.ollama = OllamaClient(window,server.url)
        window.ollama.translated.connect(window._on_ollama_response)
        window.ollama.translation_progress.connect(window._ollama_translation_progress)
        window.ollama.failed.connect(window._ollama_failed)
        window.model.load_cues(parse_srt(SOURCE))
        window.path = Path(temp)/'sample.srt'
        window.path.write_text(SOURCE)
        window.source_content = SOURCE
        window.ollama_model.setCurrentText('qwen3:4b')
        window.batch_spin.setValue(2)
        window.delay_spin.setValue(0)
        return window

    def close_window(self, window):
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def run_session(self, window, before_start=None):
        loop, notices, failures = QEventLoop(), [], []
        window.show_notice = lambda text: (notices.append(text),loop.quit())
        def failed(text):
            failures.append(text)
            window.stop_translation()
            loop.quit()
        window._auto_failed = failed
        timer=QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(5000)
        if before_start:
            before_start(loop)
        window.start_translation()
        loop.exec()
        timer.stop()
        return notices,failures

    @staticmethod
    def send_translation(handler, rows):
        text=json.dumps({'items':rows},ensure_ascii=False)
        LocalServer.stream(handler,[{'message':{'content':text[:len(text)//2]},'done':False},
            {'message':{'content':text[len(text)//2:]},'done':True}])

    def test_default_is_local_without_loading_native_or_browsing_web(self):
        with tempfile.TemporaryDirectory() as temp:
            settings=QSettings(str(Path(temp)/'settings.ini'),QSettings.Format.IniFormat)
            with (patch('app.QSettings',return_value=settings),patch('app.load_web_bridge') as native,
                  patch('app.WEB_AVAILABLE',False)):
                window=App()
            try:
                self.assertTrue(window._uses_ollama())
                self.assertEqual(window.ollama_model.currentText(),'qwen3:4b')
                self.assertEqual(window.delay_spin.value(),0)
                self.assertIsNone(window.web_view)
                native.assert_not_called()
            finally:
                self.close_window(window)

    def test_batches_pause_resume_checkpoint_and_export_preserve_timestamps(self):
        batches=[]
        def respond(h,p,d):
            if p=='/api/show':
                LocalServer.json(h,{})
                return
            payload=json.loads(d['messages'][0]['content'].split('DỮ LIỆU JSON:\n')[1])
            ids=[row['id'] for row in payload]
            batches.append(ids)
            self.send_translation(h,[{'id':i,'vi':VI[i]} for i in ids])
        with LocalServer(respond) as server,tempfile.TemporaryDirectory() as temp:
            window=self.window(server,temp)
            try:
                def first_complete(text):
                    if len(batches)==1:
                        window.toggle_pause()
                        self.assertTrue(window.auto_paused)
                        self.assertFalse(window.next_batch_timer.isActive())
                        QTimer.singleShot(50,window.toggle_pause)
                window.ollama.translated.connect(first_complete)
                notices,failures=self.run_session(window)
                self.assertEqual(failures,[],window.log_text.toPlainText())
                self.assertEqual(len(notices),1)
                self.assertEqual(batches,[[1,2],[3]])
                self.assertEqual([c.translation for c in window.model.cues],list(VI.values()))
                restored=parse_srt(SOURCE)
                self.assertEqual(restore_progress(window.path,SOURCE,restored),3)
                exported=parse_srt(srt_contents(restored))
                self.assertEqual([c.time_range for c in exported],[c.time_range for c in parse_srt(SOURCE)])
                self.assertEqual([c.source for c in exported],list(VI.values()))
            finally:
                self.close_window(window)

    def test_retries_only_invalid_cue_and_stops_after_two_retries(self):
        batches=[]
        def respond(h,p,d):
            if p=='/api/show':
                LocalServer.json(h,{})
                return
            payload=json.loads(d['messages'][0]['content'].split('DỮ LIỆU JSON:\n')[1])
            ids=[row['id'] for row in payload]
            batches.append(ids)
            self.send_translation(h,[{'id':i,'vi':'Sai số dòng' if i==2 else VI[i]} for i in ids])
        with LocalServer(respond) as server,tempfile.TemporaryDirectory() as temp:
            window=self.window(server,temp)
            try:
                notices,failures=self.run_session(window)
                self.assertEqual(notices,[])
                self.assertEqual(len(failures),1)
                self.assertEqual(batches,[[1,2],[2],[2]])
                self.assertEqual(window.model.cues[0].translation,'Xin chào')
                self.assertEqual(window.model.cues[1].translation,'')
                self.assertEqual(restore_progress(window.path,SOURCE,parse_srt(SOURCE)),1)
            finally:
                self.close_window(window)

    def test_stop_aborts_inflight_reply_and_restart_sends_only_missing(self):
        batches=[]
        def respond(h,p,d):
            if p=='/api/show':
                LocalServer.json(h,{})
                return
            payload=json.loads(d['messages'][0]['content'].split('DỮ LIỆU JSON:\n')[1])
            ids=[row['id'] for row in payload]
            batches.append(ids)
            if len(batches)==1:
                LocalServer.stream(h,[{'message':{'content':'partial'},'done':False},
                    {'message':{'content':'LATE'},'done':True}],delay=.2)
            else:
                self.send_translation(h,[{'id':i,'vi':VI[i]} for i in ids])
        with LocalServer(respond) as server,tempfile.TemporaryDirectory() as temp:
            window=self.window(server,temp)
            window.model.cues[0].translation=VI[1]
            try:
                def stopped(_):
                    window.ollama.translation_progress.disconnect(stopped)
                    window.stop_translation()
                    self.assertFalse(window.ollama.busy)
                    QTimer.singleShot(10,window.start_translation)
                window.ollama.translation_progress.connect(stopped)
                notices,failures=self.run_session(window)
                self.assertEqual(failures,[])
                self.assertEqual(len(notices),1)
                self.assertEqual(batches,[[2,3],[2,3]])
                self.assertEqual([c.translation for c in window.model.cues],list(VI.values()))
            finally:
                self.close_window(window)


if __name__=='__main__':
    unittest.main()
