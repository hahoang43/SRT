"""SRT parsing, cue alignment, progress persistence, and JSON validation.
No external dependencies. Times and original subtitles are never passed through a translator.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable

TIME_LINE = re.compile(
    r'^\s*(?P<start>\d{2,}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*'
    r'(?P<end>\d{2,}:\d{2}:\d{2}[,.]\d{1,3})(?P<settings>[^\n]*)\s*$'
)

@dataclass
class Cue:
    number: int
    start: str
    end: str
    settings: str
    source: str
    translation: str = ''

    @property
    def time_range(self) -> str:
        return f'{self.start} --> {self.end}{self.settings}'


def read_text(path: str | Path) -> str:
    raw = Path(path).read_bytes()
    for enc in ('utf-8-sig', 'utf-16', 'gb18030'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError('Không đọc được mã hóa file (UTF-8/UTF-16/GB18030).')


def parse_srt(content: str) -> list[Cue]:
    text = content.replace('\r\n', '\n').replace('\r', '\n').lstrip('\ufeff')
    # Split subtitle entries at blank lines; retain line breaks WITHIN each cue.
    blocks = re.split(r'\n[ \t]*\n+', text.strip()) if text.strip() else []
    cues: list[Cue] = []
    for offset, block in enumerate(blocks, 1):
        lines = block.split('\n')
        timing_at = 1 if len(lines) > 1 and lines[0].strip().isdigit() else 0
        if timing_at >= len(lines):
            raise ValueError(f'Khối {offset} không có mốc thời gian.')
        match = TIME_LINE.match(lines[timing_at])
        if not match:
            raise ValueError(f'Khối {offset} có mốc thời gian SRT không hợp lệ: {lines[timing_at][:90]}')
        original = '\n'.join(lines[timing_at + 1:]).strip()
        # If an entry has no subtitle text, retain an empty cue for exact cue count.
        cues.append(Cue(number=len(cues) + 1, start=match.group('start'),
                        end=match.group('end'), settings=match.group('settings').rstrip(),
                        source=original))
    if not cues:
        raise ValueError('Không tìm thấy phụ đề trong file SRT.')
    return cues


def srt_contents(cues: Iterable[Cue], include_original_for_missing: bool = False) -> str:
    output = []
    for cue in cues:
        subtitle = cue.translation if cue.translation.strip() else (cue.source if include_original_for_missing else '')
        output.append(f'{cue.number}\n{cue.time_range}\n{subtitle}')
    return '\n\n'.join(output) + '\n'


def line_count(text: str) -> int:
    return text.count('\n') + 1 if text else 0


def check_translations(requested: list[Cue], data: object) -> dict[int, str]:
    """Reject missing/extra/duplicated IDs and broken within-cue line count."""
    if not isinstance(data, dict) or not isinstance(data.get('items'), list):
        raise ValueError('JSON phải là {"items":[{"id":1,"vi":"..."}]}')
    expected = {c.number: c for c in requested}
    actual: dict[int, str] = {}
    for row in data['items']:
        if not isinstance(row, dict) or type(row.get('id')) is not int or not isinstance(row.get('vi'), str):
            raise ValueError('Mỗi bản dịch phải có id (số nguyên) và vi (chuỗi).')
        index, translated = row['id'], row['vi'].strip()
        if index not in expected:
            raise ValueError(f'ID ngoài lô: {index}.')
        if index in actual:
            raise ValueError(f'ID bị trùng: {index}.')
        if not translated and expected[index].source:
            raise ValueError(f'ID {index} bị bỏ trống.')
        if line_count(translated) != line_count(expected[index].source):
            raise ValueError(f'ID {index}: số dòng văn bản khác gốc '
                             f'({line_count(expected[index].source)} → {line_count(translated)}).')
        actual[index] = translated
    absent = sorted(set(expected) - set(actual))
    if absent:
        raise ValueError(f'Thiếu ID: {absent[:20]}' + ('…' if len(absent) > 20 else ''))
    return actual


def source_hash(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def progress_path(source_path: str | Path) -> Path:
    path = Path(source_path)
    return path.with_name(path.stem + '.progress.json')


def save_progress(path: str | Path, content: str, cues: list[Cue]) -> None:
    dest = progress_path(path)
    data = {
        'version': 1, 'sha256': source_hash(content),
        'translations': {str(c.number): c.translation for c in cues if c.translation.strip()},
    }
    partial = dest.with_suffix(dest.suffix + '.tmp')
    partial.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    partial.replace(dest)


def restore_progress(path: str | Path, content: str, cues: list[Cue]) -> int:
    src = progress_path(path)
    if not src.exists():
        return 0
    try:
        data = json.loads(src.read_text(encoding='utf-8'))
        if data.get('sha256') != source_hash(content):
            return 0
        restored = 0
        for cue in cues:
            translated = data.get('translations', {}).get(str(cue.number), '')
            if isinstance(translated, str) and translated.strip() and line_count(translated) == line_count(cue.source):
                cue.translation = translated
                restored += 1
        return restored
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return 0


def extract_json(value: str) -> dict:
    """Accept raw JSON, or JSON enclosed by a markdown ```json code fence."""
    value = value.strip()
    fenced = re.match(r'^```(?:json)?\s*\n([\s\S]*?)\n```\s*$', value, flags=re.I)
    if fenced:
        value = fenced.group(1).strip()
    result = json.loads(value)
    if not isinstance(result, dict):
        raise ValueError('Kết quả cần là JSON object.')
    return result


def make_batch_prompt(cues: list[Cue], custom_prompt: str) -> str:
    payload = [{'id': cue.number, 'zh': cue.source} for cue in cues]
    return (
        f'{custom_prompt.strip()}\n\n'
        'NHIỆM VỤ: Dịch chính xác từng phần tử trong dữ liệu JSON từ tiếng Trung sang tiếng Việt. '
        'Bảo toàn nghĩa gốc, không tự thêm bớt chi tiết hay tự ý gộp/tách mục. '
        'Trong từng mục, giữ nguyên số dòng thực tế (số ký tự xuống dòng). '
        'Bảo toàn mọi id; KHÔNG dịch các id. '
        'Chỉ trả về JSON hợp lệ dạng {"items":[{"id":123,"vi":"..."}]}; '
        'không viết thêm giải thích, tiêu đề, markdown.\n\n'
        'DỮ LIỆU JSON:\n' + json.dumps(payload, ensure_ascii=False)
    )

DEFAULT_PROMPT = (
    'Bạn là biên dịch viên phụ đề phim Trung - Việt. Dịch tiếng Việt tự nhiên, '
    'thuần Việt và đúng ngữ cảnh hội thoại, giữ tên riêng nhất quán. '
    'Không tự ý thêm, bỏ, phóng tác hoặc thay đổi ý nghĩa. '
    'Giữ nguyên các dấu xuống dòng của mỗi phụ đề; không tạo thêm chú thích.'
)
