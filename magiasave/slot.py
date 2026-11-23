"""head/part 分片协议 + json-shapes-v1 编解码 + preferences 校验。

协议来源（逐条复刻，不做「差不多」的实现）：
  offline/src/profiles.js            —— split()/encodeProfile()/decodeProfile()/validate()
  CNOfflineProfileReader.read()      —— 读取端字段约束
  CNOfflineSlotArchive.validatePreferences()
  CNOfflineSlotLibrary.allowedNamespace()
"""

import codecs
import datetime
import json
import math
import sys

from . import jsjson, protocol
from .errors import FormatError, ValidationError

# ---------------------------------------------------------------- UTF-16 计数

# memoryview.cast("H") 使用本机字节序，显式选择相同字节序的无 BOM 编码。
_NATIVE_UTF16 = "utf-16-le" if sys.byteorder == "little" else "utf-16-be"


def jslen(text):
    """JS 字符串长度（UTF-16 码元数）。profile 的 chars 与分片边界都用这套单位。"""
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def utf16_units(text):
    raw = text.encode("utf-16-le", "surrogatepass")
    units = [0] * (len(raw) // 2)
    for i in range(len(units)):
        units[i] = raw[2 * i] | (raw[2 * i + 1] << 8)
    return units


def units_to_text(units, start, end):
    raw = bytearray()
    for i in range(start, end):
        unit = units[i]
        raw.append(unit & 0xFF)
        raw.append((unit >> 8) & 0xFF)
    return bytes(raw).decode("utf-16-le", "surrogatepass")


# ---------------------------------------------------------------- 分片协议


def part_envelope_bytes(revision, index, data):
    """等价 byteLength(JSON.stringify({revision,part,data}))。"""
    return jsjson.utf8_len(
        jsjson.dumps({"revision": revision, "part": index, "data": data})
    )


def split_parts(serialized, revision, limit=protocol.MAX_PARTS, max_bytes=protocol.PART_BYTES):
    """复刻 profiles.js split()：按 UTF-16 码元切分，envelope 不超过 max_bytes。

    返回 [(revision, index, data)]；片数超过 limit 返回 None（调用方决定报错还是换编码）。
    """
    if not isinstance(serialized, str):
        raise TypeError("serialized must be str")
    units = memoryview(serialized.encode(_NATIVE_UTF16, "surrogatepass")).cast("H")
    total = len(units)
    parts = []
    offset = 0
    while offset < total:
        size = min(max_bytes, total - offset)
        data = None
        while True:
            if size <= 0:
                raise FormatError("profile_chunk_error", code="profile_chunk_error")
            last = units[offset + size - 1]
            nxt = units[offset + size] if offset + size < total else -1
            if 0xD800 <= last <= 0xDBFF and 0xDC00 <= nxt <= 0xDFFF:
                size -= 1
                continue
            candidate = codecs.decode(units[offset:offset + size], _NATIVE_UTF16, "surrogatepass")
            encoded = part_envelope_bytes(revision, len(parts), candidate)
            if encoded <= max_bytes:
                data = candidate
                break
            size = min(size - 1, int(math.floor(size * (max_bytes - 64) / float(encoded))))
        parts.append((revision, len(parts), data))
        offset += size
        if len(parts) > limit:
            return None
    return parts


def parts_to_bytes(parts):
    """head 声明的字节数按 UTF-8 计（CNOfflineProfileReader.bytes）。"""
    return jsjson.utf8_len("".join(data for _, _, data in parts))


# ---------------------------------------------------------------- profile 校验


def parse_profile_text(raw, encoded=False):
    """解析 profile 文本并做 CNOfflineProfileReader 同款结构校验。"""
    try:
        value = json.loads(raw)
    except Exception as exc:
        raise FormatError("invalid_profile_storage: %s" % exc, code="invalid_profile_storage")
    if not isinstance(value, dict):
        raise FormatError("invalid_profile_storage: root not object", code="invalid_profile_storage")
    if value.get("formatVersion") != 1:
        raise FormatError("invalid_profile_storage: formatVersion", code="invalid_profile_storage")
    kind = value.get("kind")
    if kind not in protocol.VALID_KINDS:
        raise FormatError("invalid_profile_storage: kind=%r" % (kind,), code="invalid_profile_storage")
    if not isinstance(value.get("state"), dict):
        raise FormatError("invalid_profile_storage: state", code="invalid_profile_storage")
    return value


def has_cleared_history(profile):
    """profiles.js hasClearedHistory：任一扭蛋回执带 historyDetailsCleared=true。"""
    ledger = profile.get("ordinaryGacha") if isinstance(profile, dict) else None
    if not isinstance(ledger, dict):
        return False
    rows = ledger.get("receipts")
    if not isinstance(rows, list):
        return False
    for row in rows:
        if isinstance(row, dict) and row.get("historyDetailsCleared") is True:
            return True
    return False


def template_matches_kind(template, profile):
    want = protocol.TEMPLATE_KIND.get(template)
    if want is None:
        return False
    return profile.get("kind") == want


# ---------------------------------------------------------------- json-shapes-v1

_CODEC_MAX_CHARS = 64 * 1024 * 1024
_CODEC_MAX_DEPTH = 256


def _codec_error(detail=""):
    return FormatError("invalid_profile_encoding" + ((": " + detail) if detail else ""),
                       code="invalid_profile_encoding")


def _own(mapping, key):
    return isinstance(mapping, dict) and key in mapping


def encode_profile(raw, profile=None):
    """复刻 profiles.js encodeProfile：把规范化 JSON 文本压成 shapes/strings 表。"""
    if jslen(raw) > _CODEC_MAX_CHARS:
        raise _codec_error("profile_encoding_limit")
    value = profile if profile is not None else json.loads(raw)

    counts = {}
    order = []
    strings = []
    string_ids = {}
    shapes = []
    shape_ids = {}

    def count(node, depth):
        if depth > _CODEC_MAX_DEPTH:
            raise _codec_error("depth")
        if isinstance(node, str):
            if node not in counts:
                counts[node] = 0
                order.append(node)
            counts[node] += 1
        elif isinstance(node, (list, tuple)):
            for item in node:
                count(item, depth + 1)
        elif isinstance(node, dict):
            for key in node:
                count(node[key], depth + 1)

    count(value, 0)
    for text in order:
        times = counts[text]
        length = jslen(jsjson.dumps(text))
        if times > 1 and length * times > length + times * 12 + 10:
            string_ids[text] = len(strings)
            strings.append(text)

    def node(value_in, depth):
        if depth > _CODEC_MAX_DEPTH:
            raise _codec_error("depth")
        if isinstance(value_in, str) and value_in in string_ids:
            return [-2, string_ids[value_in]]
        if isinstance(value_in, (list, tuple)):
            return [-1] + [node(item, depth + 1) for item in value_in]
        if isinstance(value_in, dict):
            keys = list(value_in.keys())
            sig = jsjson.dumps(keys)
            if sig not in shape_ids:
                shape_ids[sig] = len(shapes)
                shapes.append(keys)
            return [shape_ids[sig]] + [node(value_in[key], depth + 1) for key in keys]
        if value_in is None or isinstance(value_in, (bool, int, float, str)):
            return value_in
        raise TypeError("unsupported node: %r" % (type(value_in),))

    root = node(value, 0)
    return jsjson.dumps(
        {
            "format": "MagiaProfileShapes",
            "version": 1,
            "chars": jslen(raw),
            "shapes": shapes,
            "strings": strings,
            "root": root,
        }
    )


def decode_profile(packed):
    """复刻 profiles.js decodeProfile：返回 (value, 规范化 raw 文本)。

    packed 必须是 writer-canonical JSON 文本（storageJson(p)===packed）。
    """
    try:
        parsed = json.loads(packed)
    except Exception:
        raise _codec_error("parse")
    if jsjson.dumps(parsed) != packed:
        raise _codec_error("not canonical")
    expected_keys = ["format", "version", "chars", "shapes", "strings", "root"]
    if not isinstance(parsed, dict) or list(parsed.keys()) != expected_keys:
        raise _codec_error("envelope")
    if parsed["format"] != "MagiaProfileShapes" or parsed["version"] != 1:
        raise _codec_error("format")
    chars = parsed["chars"]
    if not isinstance(chars, int) or isinstance(chars, bool) or chars < 0 or chars > _CODEC_MAX_CHARS:
        raise _codec_error("chars")
    shapes = parsed["shapes"]
    strings = parsed["strings"]
    if not isinstance(shapes, list) or not isinstance(strings, list):
        raise _codec_error("tables")

    shape_costs = []
    shape_seen = set()
    for keys in shapes:
        if not isinstance(keys, list):
            raise _codec_error("shape")
        seen = []
        cost = 2 + max(0, len(keys) - 1)
        for key in keys:
            if not isinstance(key, str) or key in seen:
                raise _codec_error("shape key")
            seen.append(key)
            cost += jslen(jsjson.dumps(key)) + 1
        if jsjson.dumps(sorted(seen)) != jsjson.dumps(sorted(keys)) or jsjson.dumps(seen) != jsjson.dumps(keys):
            raise _codec_error("shape order")
        sig = jsjson.dumps(keys)
        if sig in shape_seen:
            raise _codec_error("shape dup")
        shape_seen.add(sig)
        shape_costs.append(cost)

    string_costs = []
    string_seen = set()
    for text in strings:
        if not isinstance(text, str) or text in string_seen:
            raise _codec_error("string dup")
        string_seen.add(text)
        string_costs.append(jslen(jsjson.dumps(text)))

    remaining = chars
    state = {"left": remaining}

    def consume(amount):
        state["left"] -= amount
        if state["left"] < 0:
            raise _codec_error("overrun")

    def node(value, depth):
        if depth > _CODEC_MAX_DEPTH:
            raise _codec_error("depth")
        if not isinstance(value, list):
            if value is not None and not isinstance(value, (str, bool, int, float)):
                raise _codec_error("scalar")
            if isinstance(value, float) and not math.isfinite(value):
                raise _codec_error("scalar")
            consume(jslen(jsjson.dumps(value)))
            return value
        if not value:
            raise _codec_error("empty tag")
        tag = value[0]
        if isinstance(tag, bool) or not isinstance(tag, int):
            raise _codec_error("tag")
        if tag == -2:
            if len(value) != 2 or not isinstance(value[1], int) or not (0 <= value[1] < len(strings)):
                raise _codec_error("string ref")
            consume(string_costs[value[1]])
            return strings[value[1]]
        if tag == -1:
            consume(2 + max(0, len(value) - 2))
            return [node(item, depth + 1) for item in value[1:]]
        if tag < 0 or tag >= len(shapes):
            raise _codec_error("shape ref")
        keys = shapes[tag]
        if len(value) != len(keys) + 1:
            raise _codec_error("shape arity")
        consume(shape_costs[tag])
        out = {}
        for i, key in enumerate(keys):
            out[key] = node(value[i + 1], depth + 1)
        return out

    decoded_value = node(parsed["root"], 0)
    if state["left"] != 0:
        raise _codec_error("underrun")
    raw = jsjson.dumps(decoded_value)
    if jslen(raw) != chars:
        raise _codec_error("chars mismatch")
    return decoded_value, raw


# ---------------------------------------------------------------- head / part


def build_head(bank, revision, parts, raw_bytes, encoding=None):
    head = {
        "formatVersion": 1,
        "bank": bank,
        "revision": revision,
        "parts": len(parts),
        "bytes": raw_bytes,
    }
    if encoding:
        head["encoding"] = encoding
    return head


def parse_head(head):
    """按 CNOfflineProfileReader 的约束验收 head（不合法直接抛错）。"""
    if not isinstance(head, dict):
        raise FormatError("invalid_profile_head: not object", code="invalid_profile_head")
    if head.get("formatVersion") != 1:
        raise FormatError("invalid_profile_head: formatVersion", code="invalid_profile_head")
    encoding = head.get("encoding")
    if "encoding" in head:
        if encoding not in (protocol.PROFILE_ENCODING, protocol.HISTORY_ENCODING):
            raise FormatError("invalid_profile_encoding", code="invalid_profile_encoding")
    bank = head.get("bank")
    if bank not in ("a", "b"):
        raise FormatError("invalid_profile_head: bank", code="invalid_profile_head")
    parts = head.get("parts")
    if not isinstance(parts, int) or isinstance(parts, bool) or not (1 <= parts <= protocol.MAX_PARTS):
        raise FormatError("invalid_profile_head: parts", code="invalid_profile_head")
    revision = head.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or not (1 <= revision <= 2 ** 53 - 1):
        raise FormatError("invalid_profile_head: revision", code="invalid_profile_head")
    length = head.get("bytes")
    if not isinstance(length, int) or isinstance(length, bool) or not (1 <= length <= protocol.STORED_BYTES):
        raise FormatError("invalid_profile_head: bytes", code="invalid_profile_head")
    return head


def assemble_raw(head, part_map, prefix):
    """按 head 声明的 bank/片序拼出原始文本，并校验字节数与 revision 一致性。"""
    raw_parts = []
    for index in range(head["parts"]):
        ns = "%s_%s_%d" % (prefix, head["bank"], index)
        part = part_map.get(ns)
        if part is None:
            raise FormatError("incomplete_profile: missing %s" % ns, code="incomplete_profile")
        if part.get("revision") != head["revision"]:
            raise FormatError("incomplete_profile: revision", code="incomplete_profile")
        if part.get("part") != index:
            raise FormatError("incomplete_profile: part index", code="incomplete_profile")
        data = part.get("data")
        if not isinstance(data, str):
            raise FormatError("incomplete_profile: data", code="incomplete_profile")
        raw_parts.append(data)
    raw = "".join(raw_parts)
    if jsjson.utf8_len(raw) != head["bytes"]:
        raise FormatError("profile_size_mismatch", code="profile_size_mismatch")
    return raw


def decode_stored(raw, encoding):
    """head 带 encoding 时解出 (profile, 规范化 raw)；否则 (profile, raw)。"""
    if not encoding:
        return parse_profile_text(raw), raw
    value, canonical = decode_profile(raw)
    profile = parse_profile_text(canonical)
    if has_cleared_history(profile) != (encoding == protocol.HISTORY_ENCODING):
        raise FormatError("gacha_history_reader_capability_mismatch",
                          code="gacha_history_reader_capability_mismatch")
    return profile, canonical


# ---------------------------------------------------------------- preferences

_GAME_START = datetime.datetime(2017, 8, 22, 0, 0, 0)
_GAME_END = datetime.datetime(2024, 7, 31, 14, 59, 59)
_TS_MIN = int(_GAME_START.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
_TS_MAX = int(_GAME_END.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
_TS_SAFE = 9007199254740991
_DATE_FMT = "%Y/%m/%d %H:%M:%S"


def parse_game_date(text):
    """严格解析 yyyy/MM/dd HH:mm:ss（UTC，非宽松），返回毫秒时间戳。"""
    if not isinstance(text, str) or len(text) != 19:
        raise ValidationError("save_archive_date", code="save_archive_date")
    try:
        moment = datetime.datetime.strptime(text, _DATE_FMT)
    except ValueError:
        raise ValidationError("save_archive_date", code="save_archive_date")
    if moment.strftime(_DATE_FMT) != text:
        raise ValidationError("save_archive_date", code="save_archive_date")
    return int(moment.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)


def format_game_date(ms):
    moment = datetime.datetime.fromtimestamp(ms / 1000.0, tz=datetime.timezone.utc)
    return moment.strftime(_DATE_FMT)


def validate_preferences(value):
    """复刻 CNOfflineSlotArchive.validatePreferences。返回规范化对象。"""
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValidationError("save_archive_preferences_field", code="save_archive_preferences_field")
    for key in value:
        if key not in ("calendar", "draft"):
            raise ValidationError("save_archive_preferences_field", code="save_archive_preferences_field")
    out = {"calendar": None, "draft": None}
    calendar = value.get("calendar")
    if calendar is not None:
        if not isinstance(calendar, dict):
            raise ValidationError("save_archive_calendar", code="save_archive_calendar")
        if set(calendar.keys()) != {"version", "mode", "anchor", "selectedAt"}:
            raise ValidationError("save_archive_calendar", code="save_archive_calendar")
        version = calendar["version"]
        if not isinstance(version, int) or isinstance(version, bool) or version != 1:
            raise ValidationError("save_archive_calendar", code="save_archive_calendar")
        if calendar["mode"] != "historical":
            raise ValidationError("save_archive_calendar", code="save_archive_calendar")
        anchor = calendar["anchor"]
        selected = calendar["selectedAt"]
        if not _is_int(anchor) or not (_TS_MIN <= anchor <= _TS_MAX):
            raise ValidationError("save_archive_calendar", code="save_archive_calendar")
        if not _is_int(selected) or not (0 <= selected <= _TS_SAFE):
            raise ValidationError("save_archive_calendar", code="save_archive_calendar")
        out["calendar"] = {"version": 1, "mode": "historical", "anchor": anchor, "selectedAt": selected}
    draft = value.get("draft")
    if draft is not None:
        if not isinstance(draft, str):
            raise ValidationError("save_archive_draft", code="save_archive_draft")
        stamp = parse_game_date(draft)
        if stamp < _TS_MIN or stamp > _TS_MAX:
            raise ValidationError("save_archive_draft", code="save_archive_draft")
        out["draft"] = draft
    if jsjson.utf8_len(jsjson.dumps(out)) > protocol.MAX_PREFERENCES:
        raise ValidationError("save_archive_preferences_size", code="save_archive_preferences_size")
    return out


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)
