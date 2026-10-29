import json
import tempfile
import unittest
from pathlib import Path
from srt_engine import (
    parse_srt, check_translations, srt_contents, save_progress, restore_progress,
    extract_json, make_batch_prompt,
)

SRC = '''1\n00:00:01,000 --> 00:00:02,000\n你好\n\n2\n00:00:02,300 --> 00:00:05,900 X1:5 X2:9\n别担心\n我帮你\n'''

class EngineTests(unittest.TestCase):
    def test_parse_and_export(self):
        cues = parse_srt(SRC)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[1].number, 2)
        self.assertEqual(cues[1].source, '别担心\n我帮你')
        self.assertTrue(cues[1].time_range.endswith('X1:5 X2:9'))
        translated = {'items': [{'id': 1, 'vi': 'Xin chào'},
                                {'id': 2, 'vi': 'Đừng lo\nTôi giúp bạn'}]}
        mapped = check_translations(cues, translated)
        for c in cues: c.translation = mapped[c.number]
        output = srt_contents(cues)
        self.assertEqual(len(parse_srt(output)), 2)
        self.assertIn('00:00:02,300 --> 00:00:05,900 X1:5 X2:9', output)
        self.assertIn('Đừng lo\nTôi giúp bạn', output)

    def test_missing_duplicate_extra_and_lines(self):
        cues = parse_srt(SRC)
        for bad in (
            {'items': [{'id': 1, 'vi': 'Xin chào'}]},
            {'items': [{'id': 1, 'vi': 'Xin chào'}, {'id': 1, 'vi': 'Xin chào'}]},
            {'items': [{'id': 1, 'vi': 'Xin chào'}, {'id': 2, 'vi': 'Gộp hai dòng'}]},
            {'items': [{'id': 1, 'vi': 'Xin chào'}, {'id': 99, 'vi': 'Thừa'}]},
        ):
            with self.assertRaises(ValueError): check_translations(cues, bad)

    def test_resume_checksum(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'a.srt'
            path.write_text(SRC, encoding='utf-8')
            cues = parse_srt(SRC)
            cues[0].translation = 'Xin chào'
            save_progress(path, SRC, cues)
            blank = parse_srt(SRC)
            self.assertEqual(restore_progress(path, SRC, blank), 1)
            self.assertEqual(blank[0].translation, 'Xin chào')
            self.assertEqual(restore_progress(path, SRC+' ', parse_srt(SRC)), 0)

    def test_json_surrounded_by_prose_and_reject_truncation(self):
        payload = '{"items":[{"id":1,"vi":"Chào"}]}'
        self.assertEqual(extract_json('Kết quả:\n' + payload + '\nHoàn tất.'), json.loads(payload))
        with self.assertRaises(ValueError):
            extract_json(payload[:-2])
        with self.assertRaises(ValueError):
            extract_json(payload + '\n' + payload)

    def test_manual_json_and_prompt(self):
        obj = extract_json('```json\n{"items":[]}\n```')
        self.assertEqual(obj, {'items': []})
        self.assertIn('DỮ LIỆU JSON:', make_batch_prompt(parse_srt(SRC), 'Dịch tự nhiên'))
        with self.assertRaises(ValueError): parse_srt('invalid srt')

if __name__ == '__main__':
    unittest.main()
