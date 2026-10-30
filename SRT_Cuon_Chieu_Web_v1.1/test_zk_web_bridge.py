import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from srt_engine import parse_srt
from zk_web_bridge import ZK_FILE, ZK_SHA256, ZKSupport, load_zk_support, merge_zk_response


class ZKBridgeTests(unittest.TestCase):
    def setUp(self):
        self.cues = parse_srt('1\n00:00:01,000 --> 00:00:02,000\n你好\n')
        self.payload = '{"items":[{"id":1,"vi":"Xin chào"}]}'

    def test_supplied_zk_binary_is_unchanged(self):
        blob = Path(__file__).with_name(ZK_FILE).read_bytes()
        self.assertEqual(hashlib.sha256(blob).hexdigest(), ZK_SHA256)
        offset = int.from_bytes(blob[60:64], 'little')
        self.assertEqual(blob[offset:offset+6], b'PE\0\0\x64\x86')

    def test_linux_does_not_import_windows_module(self):
        with patch('zk_web_bridge.sys.platform', 'linux'), patch('zk_web_bridge.importlib.util.module_from_spec') as imported:
            support = load_zk_support(True)
        self.assertIsNone(support.module)
        imported.assert_not_called()

    def test_missing_companion_module_is_reported_and_proxy_restored(self):
        loader = Mock()
        def fail(module):
            os.environ.pop('HTTPS_PROXY', None)
            raise ModuleNotFoundError("No module named 'ai_gemini'", name='ai_gemini')
        loader.exec_module.side_effect = fail
        with patch.dict(os.environ, {'HTTPS_PROXY':'http://test-proxy.invalid'}), patch('zk_web_bridge.sys.platform','win32'), patch('zk_web_bridge.sys.version_info',(3,12,0)), patch('zk_web_bridge.struct.calcsize',return_value=8), patch('zk_web_bridge.importlib.util.spec_from_file_location',return_value=SimpleNamespace(loader=loader)), patch('zk_web_bridge.importlib.util.module_from_spec',return_value=SimpleNamespace()):
            support = load_zk_support(True)
            self.assertEqual(os.environ['HTTPS_PROXY'], 'http://test-proxy.invalid')
        self.assertIsNone(support.module)
        self.assertIn('ai_gemini', support.status)

    def test_supported_loader_keeps_main_controller_uninstantiated(self):
        main = Mock(side_effect=AssertionError('Do not launch ZK application'))
        module = SimpleNamespace(ChatGPTWebView=type('View',(),{}),ChatGPTTranslatorApp=main)
        loader = Mock()
        with patch.dict('sys.modules'),patch('zk_web_bridge.sys.platform','win32'),patch('zk_web_bridge.sys.version_info',(3,12,0)),patch('zk_web_bridge.struct.calcsize',return_value=8),patch('zk_web_bridge.importlib.util.spec_from_file_location',return_value=SimpleNamespace(loader=loader)),patch('zk_web_bridge.importlib.util.module_from_spec',return_value=module):
            support = load_zk_support(True)
        self.assertIs(support.module,module)
        loader.exec_module.assert_called_once_with(module)
        main.assert_not_called()

    def test_changed_zk_binary_is_rejected_before_loading(self):
        with patch('zk_web_bridge.sys.platform','win32'),patch('zk_web_bridge.sys.version_info',(3,12,0)),patch('zk_web_bridge.struct.calcsize',return_value=8),patch('zk_web_bridge.Path.read_bytes',return_value=b'changed'),patch('zk_web_bridge.importlib.util.module_from_spec') as imported:
            support = load_zk_support(True)
        self.assertIsNone(support.module)
        self.assertIn('khác bản',support.status)
        imported.assert_not_called()

    def test_factory_uses_only_web_view(self):
        class Base:
            def __init__(self, parent=None): self.parent = parent
        class View(Base):
            def get_last_response(self, callback): callback({'text':''})
        forbidden = Mock(side_effect=AssertionError('Do not create second controller'))
        support = ZKSupport(SimpleNamespace(ChatGPTWebView=View, ChatGPTTranslatorApp=forbidden))
        view, active, _ = support.create_view('parent', Base)
        self.assertTrue(active)
        self.assertIsInstance(view, View)
        self.assertEqual(view.parent, 'parent')
        forbidden.assert_not_called()

    def test_incompatible_constructor_falls_back_explicitly(self):
        class Base:
            def __init__(self, parent=None): pass
        class View(Base):
            def __init__(self, required): raise AssertionError('Must bind before calling')
        view, active, status = ZKSupport(SimpleNamespace(ChatGPTWebView=View)).create_view(None, Base)
        self.assertFalse(active)
        self.assertIsInstance(view, Base)
        self.assertIn('Không dùng được khung ZK', status)

    def test_callback_formats_and_current_batch_priority(self):
        old = '{"items":[{"id":99,"vi":"Cũ"}]}'
        base = {'site':True,'text':old,'generating':False}
        for args in ((json.dumps({'text':self.payload,'is_generating':False}),),
                     (self.payload,), (False,self.payload), (self.payload,False)):
            value = merge_zk_response(base, args, self.cues)
            self.assertEqual(value['text'], self.payload)
            self.assertTrue(value['diagnostics']['zkReader'])
        captured = {**base,'text':self.payload,'captured':True}
        self.assertEqual(merge_zk_response(captured, ({'text':old},), self.cues)['text'],self.payload)

    def test_invalid_callback_is_not_reported_as_success(self):
        for args in ((None,), ({'error':'read failed','text':''},), (123,)):
            with self.assertRaises((ValueError, TypeError)):
                merge_zk_response({'text':self.payload}, args, self.cues)


if __name__ == '__main__':
    unittest.main()
