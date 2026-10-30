import json
import shutil
import subprocess
import unittest
from web_connect import PROBE_JS, READ_LATEST_RESPONSE_JS, SEND_MESSAGE_JS, _guard_service_limit


class WebConnectionTests(unittest.TestCase):
    def test_connection_probe_does_not_send_or_extract_messages(self):
        self.assertNotIn('Xin chào', PROBE_JS)
        self.assertNotIn('.click(', PROBE_JS)
        # Probe reads only the latest reply fingerprint to correlate batches.
        self.assertIn("host !== 'chatgpt.com'", PROBE_JS)

    def run_dom(self, script, replies, *, host='chatgpt.com', stop=False):
        if not shutil.which('node'):
            self.skipTest('Node.js is required for DOM fixture tests')
        fixture = r'''
const replies = DATA.map(data => ({
  innerText:data.wrapper, textContent:data.wrapper,
  querySelectorAll: selector => selector === 'pre code' ?
    data.blocks.map(text => ({textContent:text})) : [],
  querySelector: selector => selector === '.markdown' ?
    {innerText:data.wrapper} : null
}));
global.location = {hostname:HOST}; global.window = {location};
global.getComputedStyle = () => ({visibility:'visible'});
const editor = {getClientRects:()=>[1],getAttribute:()=>null,tagName:'TEXTAREA',matches:()=>true};
global.document = {querySelectorAll: selector => {
  if(['[data-testid^="conversation-turn-"]', 'main .markdown, main pre code',
      'main, [role="main"], #thread, #conversation'].includes(selector)) return [];
  if(selector === '[data-message-author-role="assistant"]') return replies;
  if(selector.includes('#prompt-textarea')) return [editor];
  if(selector.includes('stop-button')) return STOP ? [editor] : [];
  throw new Error('Unexpected selector: '+selector);
}};
process.stdout.write(JSON.stringify(SCRIPT));
'''
        fixture = fixture.replace('DATA', json.dumps(replies)).replace('HOST', json.dumps(host)).replace('STOP', json.dumps(stop)).replace('SCRIPT', script)
        result = subprocess.run(['node', '-e', fixture], capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def test_same_count_before_and_after_new_reply(self):
        old = {'wrapper':'old reply', 'blocks':[]}
        baseline = self.run_dom(PROBE_JS, [old])
        current = self.run_dom(READ_LATEST_RESPONSE_JS, [old])
        self.assertTrue(baseline['editor'])
        self.assertEqual(baseline['assistantCount'], current['assistantCount'])
        new = {'wrapper':'new reply', 'blocks':[]}
        current = self.run_dom(READ_LATEST_RESPONSE_JS, [old, new])
        self.assertEqual(current['assistantCount'], baseline['assistantCount']+1)
        self.assertEqual(current['text'], 'new reply')

    def test_json_excludes_copy_button_and_prose(self):
        payload = '{"items":[{"id":1,"vi":"Xin chào"}]}'
        reply = {'wrapper':'Here is the result\njson\nCopy code\n'+payload,
                 'blocks':['invalid block', payload]}
        result = self.run_dom(READ_LATEST_RESPONSE_JS, [reply])
        self.assertEqual(result['text'], payload)
        self.assertFalse(result['generating'])
        self.assertTrue(self.run_dom(READ_LATEST_RESPONSE_JS, [reply], stop=True)['generating'])

    def test_send_never_clicks_disabled_controls_changed_drafts_or_login(self):
        if not shutil.which('node'):
            self.skipTest('Node.js required')
        fixture = r'''
let clicked = 0;
const shown = {getClientRects:()=>[1],getAttribute:()=>null};
const editor = {...shown, tagName:'TEXTAREA', value:DRAFT, closest:()=>null,matches:()=>true};
const send = {...shown, disabled:DISABLED, click:()=>clicked++};
global.location = {hostname:'chatgpt.com'};
global.window = {__srtOutboundPrompt:'batch'};
global.getComputedStyle = () => ({visibility:'visible'});
global.document = {querySelectorAll: selector => {
  if(selector.includes('#prompt-textarea')) return [editor];
  if(selector.includes('stop-button')) return STOP ? [shown] : [];
  if(selector === 'button#composer-submit-button') return PRESENT ? [send] : [];
  if(selector === 'button[type="submit"]') throw new Error('Must not query unrelated login submit button');
  return [];
}};
const result = SCRIPT;
process.stdout.write(JSON.stringify({result, clicked}));
'''
        for present, disabled, draft, stop, clicks, retry in [
            (True, True, 'batch', False, 0, True),
            (False, False, 'batch', False, 0, True),
            (True, False, 'edited draft', False, 0, False),
            (True, False, 'batch', True, 0, True),
            (True, False, 'batch', False, 1, None),
        ]:
            with self.subTest(present=present, disabled=disabled, draft=draft, stop=stop):
                code = fixture.replace('DRAFT', json.dumps(draft)).replace('DISABLED', json.dumps(disabled)).replace('PRESENT', json.dumps(present)).replace('STOP', json.dumps(stop)).replace('SCRIPT', SEND_MESSAGE_JS)
                output = subprocess.run(['node','-e',code],capture_output=True,text=True,check=True)
                value = json.loads(output.stdout)
                self.assertEqual(value['clicked'], clicks)
                self.assertEqual(value['result']['ok'], bool(clicks))
                if retry is not None:
                    self.assertEqual(value['result']['retryable'], retry)

    def test_service_cooldown_clock_and_expiration(self):
        if not shutil.which('node'):
            self.skipTest('Node.js required')
        cases = [
            ('2026-10-30T14:25:00','3:05\u202fPM',True,15,5),
            ('2026-10-30T15:06:00','3:05 PM',False,None,None),
            ('2026-10-30T23:59:00','12:10 AM',True,0,10),
        ]
        for now, clock, active, hour, minute in cases:
            with self.subTest(now=now,clock=clock):
                fixture = r'''
const NativeDate = Date;
global.Date = class extends NativeDate {constructor(...args) {super(...(args.length ? args : [NOW]));}};
global.location = {hostname:'chatgpt.com'};
global.document = {body:{cloneNode:()=>({querySelectorAll:()=>[],textContent:MESSAGE})}};
const result = SCRIPT;
process.stdout.write(JSON.stringify(result));
'''
                message = "We're doing a quick check to keep ChatGPT reliable. Try again after " + clock + '.'
                code = fixture.replace('NOW',json.dumps(now)).replace('MESSAGE',json.dumps(message)).replace('SCRIPT',_guard_service_limit('({passed:true})'))
                value = json.loads(subprocess.run(['node','-e',code],capture_output=True,text=True,check=True).stdout)
                self.assertEqual(value.get('cooldown',False),active)
                if active:
                    self.assertEqual(value['clock'],f'{hour:02d}:{minute:02d}')
                    self.assertGreater(value['retryAt'],0)
                else:
                    self.assertTrue(value['passed'])

    def test_other_domain_does_not_read_messages(self):
        for script in (PROBE_JS, READ_LATEST_RESPONSE_JS):
            result = self.run_dom(script, [], host='example.com')
            self.assertFalse(result['site'])
            self.assertEqual(result['assistantCount'], 0)


if __name__ == '__main__':
    unittest.main()
