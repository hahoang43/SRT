import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from native_chatgpt_bridge import WebBridge, load_web_bridge, NATIVE_FILE, NATIVE_SHA256


class FakeHandler:
    """Same public protocol observed statically in the supplied module."""
    @staticmethod
    def get_read_js():
        return """(() => {
          const replies = [...document.querySelectorAll('main .guest-reply')];
          const last = replies[replies.length-1];
          return JSON.stringify({text:last ? last.textContent : '',
            is_generating:false,debug:'test-native-reader'});
        })();"""

    @staticmethod
    def get_send_js(message):
        return """(() => {
          const text = `PAYLOAD`;
          const input = document.querySelector('textarea, [contenteditable]');
          if (!input) return false;
          if (input.tagName === 'TEXTAREA') input.value = text; else input.innerText = text;
          input.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:text}));
          setTimeout(() => {const sendBtn = document.querySelector('#composer-submit-button'); sendBtn.click();},400);
          return true;
        })();""".replace('PAYLOAD',message)


class NativeBridgeTests(unittest.TestCase):
    def test_supplied_binary_is_unchanged_and_windows_x64(self):
        blob = Path(__file__).with_name(NATIVE_FILE).read_bytes()
        self.assertEqual(hashlib.sha256(blob).hexdigest(), NATIVE_SHA256)
        self.assertEqual(blob[:2], b'MZ')
        offset = int.from_bytes(blob[60:64],'little')
        self.assertEqual(blob[offset:offset+6], b'PE\0\0\x64\x86')

    def test_linux_does_not_attempt_to_import_windows_binary(self):
        with patch('native_chatgpt_bridge.sys.platform','linux'), patch('native_chatgpt_bridge.importlib.util.module_from_spec') as imported:
            bridge = load_web_bridge()
        self.assertFalse(bridge.native)
        imported.assert_not_called()

    def test_supported_windows_loader_uses_expected_handler(self):
        spec = SimpleNamespace(loader=Mock())
        with patch('native_chatgpt_bridge.sys.platform','win32'), patch('native_chatgpt_bridge.sys.version_info',(3,12,0)), patch('native_chatgpt_bridge.struct.calcsize',return_value=8), patch('native_chatgpt_bridge.importlib.util.spec_from_file_location',return_value=spec), patch('native_chatgpt_bridge.importlib.util.module_from_spec',return_value=SimpleNamespace(ChatGPTHandler=FakeHandler)):
            bridge = load_web_bridge()
        self.assertTrue(bridge.native)
        spec.loader.exec_module.assert_called_once()

    def test_changed_binary_is_rejected_before_loading(self):
        with patch('native_chatgpt_bridge.sys.platform','win32'), patch('native_chatgpt_bridge.sys.version_info',(3,12,0)), patch('native_chatgpt_bridge.struct.calcsize',return_value=8), patch('native_chatgpt_bridge.Path.read_bytes',return_value=b'changed'), patch('native_chatgpt_bridge.importlib.util.module_from_spec') as imported:
            bridge = load_web_bridge()
        self.assertFalse(bridge.native)
        self.assertIn('khác bản',bridge.status)
        imported.assert_not_called()

    def test_native_sender_preserves_literal_payload_and_can_cancel_delayed_click(self):
        if not shutil.which('node'):
            self.skipTest('Node.js required')
        class CaptureHandler(FakeHandler):
            @staticmethod
            def get_send_js(message):
                return "(() => { const text = `"+message+"`; const input={set textContent(value){window.received=value;},set innerHTML(value){throw new Error('unsafe HTML');}}; input.innerHTML = `<p>${text}</p>`; setTimeout(() => {window.clicks++;},400); return true; })();"
        bridge = WebBridge(CaptureHandler)
        payload = 'MESSAGE NATIVE ` ${window.clicks=99} <img src=x onerror=bad()> \\ newline\n你好'
        for cancel in (False,True):
            with self.subTest(cancel=cancel):
                script = bridge.send_js(payload,42)
                fixture = r'''
const tasks=[];
global.window={clicks:0,setTimeout:callback=>tasks.push(callback)};
global.location={hostname:'chatgpt.com'};
const editor={tagName:'TEXTAREA',matches:()=>true,getClientRects:()=>[1],closest:()=>null,
  get value(){return window.received;}};
const button={getClientRects:()=>[1],getAttribute:()=>null};
global.getComputedStyle=()=>({visibility:'visible'});
global.document={querySelectorAll:selector=>selector==='#prompt-textarea' ? [editor] :
  selector==='button#composer-submit-button' ? [button] : []};
const queued = SCRIPT;
if (CANCEL) window.__srtNativeSendId=null;
tasks.forEach(callback=>callback());
process.stdout.write(JSON.stringify({queued,received:window.received,clicks:window.clicks}));
'''
                fixture = fixture.replace('SCRIPT',script).replace('CANCEL',json.dumps(cancel))
                value = json.loads(subprocess.run(['node','-e',fixture],capture_output=True,text=True,check=True).stdout)
                self.assertTrue(value['queued']['ok'])
                self.assertEqual(value['received'],payload)
                self.assertEqual(value['clicks'],0 if cancel else 1)

    def test_invalid_native_api_fails_explicitly(self):
        class BadHandler:
            @staticmethod
            def get_read_js(): return None
        with self.assertRaises(ValueError):
            WebBridge(BadHandler)


if __name__ == '__main__':
    unittest.main()
