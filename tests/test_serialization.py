"""序列化和分片与已发布的游戏存档保持一致；不依赖外部存档。"""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from magiasave import jsjson, slot


class SerializationTests(unittest.TestCase):
    def test_quote(self):
        self.assertEqual(jsjson.quote('中🌙\ud83c\udf19\udfff🚀\ud800'),
                         '"中🌙\\ud83c\\udf19\\udfff🚀\\ud800"')
        self.assertEqual(jsjson.quote('\x00\x1f\b\t\n\f\r"\\/\x7f\u2028\u2029'),
                         '"\\u0000\\u001f\\b\\t\\n\\f\\r\\"\\\\/\x7f\u2028\u2029"')
        for s in ['', 'ascii', ' "\\\n\t神浜🎵' * 1024]:
            self.assertEqual(jsjson.quote(s), json.dumps(s, ensure_ascii=False))

    @staticmethod
    def reference(text, revision, limit, cap):
        # Reference the former code-unit representation and serializer for chunk sizing.
        import math
        units = slot.utf16_units(text)
        parts, at = [], 0
        while at < len(units):
            size = min(cap, len(units) - at)
            while size:
                end = at + size
                if (end < len(units) and 0xd800 <= units[end - 1] <= 0xdbff
                        and 0xdc00 <= units[end] <= 0xdfff):
                    size -= 1
                    continue
                chunk = slot.units_to_text(units, at, end)
                count = slot.part_envelope_bytes(revision, len(parts), chunk)
                if count <= cap:
                    break
                size = min(size - 1, math.floor(size * (cap - 64) / count))
            if not size:
                raise AssertionError("invalid fixture capacity")
            parts.append((revision, len(parts), chunk))
            if len(parts) > limit:
                return None
            at += size
        return parts

    def test_split_matches_previous_boundaries(self):
        cap = 145
        for text in ['', 'a' * (cap-1) + '🌙' + 'b' * cap,
                     ('🌙中"\\\n\udfffZ\ud800Z' * 125), '活動🎵' * 1000]:
            for limit in (1, 1000):
                with self.subTest(chars=len(text), limit=limit):
                    expected = self.reference(text, 99, limit, cap)
                    self.assertEqual(slot.split_parts(text, 99, limit, cap), expected)


if __name__ == '__main__':
    unittest.main()
