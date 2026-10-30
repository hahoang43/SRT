"""Gemini REST HTTP -> production SRT controller -> checkpoint/export."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtNetwork import QNetworkProxy

from app import App
from gemini_backend import GeminiClient
from srt_engine import parse_srt, restore_progress, srt_contents
from test_gemini_backend import LocalServer, FAKE_KEY

SOURCE = ('1\n00:00:01,000 --> 00:00:02,000\n你好\n\n'
          '2\n00:00:02,000 --> 00:00:03,000\n别担心\n我帮你\n\n'
          '3\n00:00:03,000 --> 00:00:04,000\n再见\n')
VI = {1:'Xin chào',2:'Đừng lo\nTôi giúp bạn',3:'Tạm biệt'}


class AppGeminiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setQuitOnLastWindowClosed(False)

    def window(self, server, temp):
        with patch('app.WEB_AVAILABLE',False):
            window = App(backend='gemini')
        window.gemini.manager.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        window.gemini_key.setText(FAKE_KEY)
        window.model.load_cues(parse_srt(SOURCE))
        window.path = Path(temp)/'sample.srt'
        window.path.write_text(SOURCE)
        window.source_content = SOURCE
        window.gemini_model.setCurrentText('gemini-2.5-flash')
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
        LocalServer.translation(handler, rows)

    def test_default_and_removed_backend_settings_use_chatgpt(self):
        for previous in (None, 'ollama'):
            with self.subTest(previous=previous), tempfile.TemporaryDirectory() as temp:
                settings = QSettings(str(Path(temp)/'settings.ini'), QSettings.Format.IniFormat)
                if previous:
                    settings.setValue('translation_backend', previous)
                with (patch('app.QSettings', return_value=settings), patch('app.load_web_bridge') as native,
                      patch('app.WEB_AVAILABLE', False)):
                    window = App()
                try:
                    self.assertEqual(window.backend_box.currentData(), 'web')
                    self.assertEqual([window.backend_box.itemData(i) for i in range(window.backend_box.count())],
                                     ['web', 'gemini'])
                    self.assertIsNone(window.web_view)
                    native.assert_not_called()
                    self.assertEqual(settings.value('translation_backend'), 'web')
                finally:
                    self.close_window(window)

    def test_key_is_masked_and_not_persisted_and_missing_key_prevents_request(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = QSettings(str(Path(temp)/'settings.ini'), QSettings.Format.IniFormat)
            with patch('app.QSettings', return_value=settings), patch('app.WEB_AVAILABLE', False):
                window = App(backend='gemini')
            try:
                self.assertEqual(window.gemini_key.echoMode(), window.gemini_key.EchoMode.Password)
                window.model.load_cues(parse_srt(SOURCE))
                notices = []
                window.show_notice = notices.append
                window.gemini_key.clear()
                with patch.object(window.gemini, 'translate') as translate:
                    window.start_translation()
                    translate.assert_not_called()
                self.assertEqual(len(notices), 1)
                self.assertFalse(window.auto_session)
                window.gemini_key.setText(FAKE_KEY)
                window.close()
                settings.sync()
                self.assertNotIn(FAKE_KEY, settings.fileName() and Path(settings.fileName()).read_text()
                                 if Path(settings.fileName()).exists() else '')
                self.assertNotIn(FAKE_KEY, window.log_text.toPlainText())
            finally:
                self.close_window(window)

    def test_batches_pause_resume_checkpoint_and_export_preserve_timestamps(self):
        batches=[]
        def respond(h,p,d):
            payload=json.loads(d['contents'][0]['parts'][0]['text'].split('DỮ LIỆU JSON:\n')[1])
            ids=[row['id'] for row in payload]
            batches.append(ids)
            self.send_translation(h,[{'id':i,'vi':VI[i]} for i in ids])
        with LocalServer(respond) as server, patch('gemini_backend.API_URL', server.url + '/v1beta'), tempfile.TemporaryDirectory() as temp:
            window=self.window(server,temp)
            try:
                def first_complete(text):
                    if len(batches)==1:
                        window.toggle_pause()
                        self.assertTrue(window.auto_paused)
                        self.assertFalse(window.next_batch_timer.isActive())
                        QTimer.singleShot(50,window.toggle_pause)
                window.gemini.translated.connect(first_complete)
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
            payload=json.loads(d['contents'][0]['parts'][0]['text'].split('DỮ LIỆU JSON:\n')[1])
            ids=[row['id'] for row in payload]
            batches.append(ids)
            self.send_translation(h,[{'id':i,'vi':'Sai số dòng' if i==2 else VI[i]} for i in ids])
        with LocalServer(respond) as server, patch('gemini_backend.API_URL', server.url + '/v1beta'), tempfile.TemporaryDirectory() as temp:
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
            payload=json.loads(d['contents'][0]['parts'][0]['text'].split('DỮ LIỆU JSON:\n')[1])
            ids=[row['id'] for row in payload]
            batches.append(ids)
            if len(batches)==1:
                import time
                time.sleep(.2)
                self.send_translation(h, [{'id': i, 'vi': 'OLD'} for i in ids])
            else:
                self.send_translation(h,[{'id':i,'vi':VI[i]} for i in ids])
        with LocalServer(respond) as server, patch('gemini_backend.API_URL', server.url + '/v1beta'), tempfile.TemporaryDirectory() as temp:
            window=self.window(server,temp)
            window.model.cues[0].translation=VI[1]
            try:
                def stopped():
                    window.stop_translation()
                    self.assertFalse(window.gemini.busy)
                    QTimer.singleShot(10,window.start_translation)
                QTimer.singleShot(75,stopped)
                notices,failures=self.run_session(window)
                self.assertEqual(failures,[])
                self.assertEqual(len(notices),1)
                self.assertEqual(batches,[[2,3],[2,3]])
                self.assertEqual([c.translation for c in window.model.cues],list(VI.values()))
            finally:
                self.close_window(window)


if __name__=='__main__':
    unittest.main()
