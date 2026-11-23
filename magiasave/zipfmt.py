"""与客户端逐字段一致的 ZIP 写入/校验。

客户端 (CNOfflineSlotArchive.inspect) 在把 zip 交给 JDK 解压器之前手工解析
中央目录与本地头，只接受一个很窄的 v1 子集：
  - 单卷、非 ZIP64、无注释、无加密、无未知 extra
  - 可选单个 0x5455 扩展时间戳（仅 mtime），本地头与中央目录必须一致
  - 方法 0 或 8；文件名只能是 ASCII 32..126 且必须命中存档路径白名单
  - 条目数据区首尾相接，无 gap；必须同时存在 manifest.json 与 preferences.json
这里把同一套规则实现成 Python 校验器，用于「写完之后先自检，再交给客户端」。
"""

import io
import struct
import zipfile

from . import protocol
from .errors import FormatError

_U16 = struct.Struct("<H")
_U32 = struct.Struct("<I")


class Record:
    __slots__ = ("name", "size", "compressed", "crc", "offset", "end", "mtime", "flags", "method")

    def __init__(self):
        self.name = ""
        self.size = 0
        self.compressed = 0
        self.crc = 0
        self.offset = 0
        self.end = 0
        self.mtime = -1
        self.flags = 0
        self.method = 0

    def __repr__(self):
        return "<Record %s size=%d crc=%08x>" % (self.name, self.size, self.crc)


def _bad(reason):
    return FormatError("save_archive_" + reason, code="save_archive_" + reason)


def _u16(data, pos):
    return _U16.unpack_from(data, pos)[0]


def _u32(data, pos):
    return _U32.unpack_from(data, pos)[0]


def _extra_mtime(data, pos, length):
    """只接受 9 字节、tag=0x5455、len=5、flags=1（仅 mtime）的扩展时间戳。"""
    if length == 0:
        return -1
    if length != 9 or _u16(data, pos) != 0x5455 or _u16(data, pos + 2) != 5 or data[pos + 4] != 1:
        raise _bad("zip_extra")
    return _u32(data, pos + 5)


def inspect(data):
    """复刻 CNOfflineSlotArchive.inspect。返回 {name: Record}。"""
    size = len(data)
    if size < 22 or size > protocol.MAX_ARCHIVE:
        raise _bad("zip_size")
    end_pos = size - 22
    if _u32(data, end_pos) != 0x06054B50:
        raise _bad("zip_signature")
    if _u16(data, end_pos + 4) != 0 or _u16(data, end_pos + 6) != 0:
        raise _bad("zip_disk")
    on_disk = _u16(data, end_pos + 8)
    count = _u16(data, end_pos + 10)
    central_size = _u32(data, end_pos + 12)
    central = _u32(data, end_pos + 16)
    if _u16(data, end_pos + 20) != 0 or on_disk != count or count < 2 or count > protocol.MAX_ENTRIES:
        raise _bad("zip_directory")
    if central + central_size != end_pos:
        raise _bad("zip_directory")

    records = {}
    pos = central
    total = 0
    for _ in range(count):
        if pos + 46 > end_pos:
            raise _bad("zip_directory")
        if _u32(data, pos) != 0x02014B50:
            raise _bad("zip_signature")
        rec = Record()
        rec.flags = _u16(data, pos + 8)
        rec.method = _u16(data, pos + 10)
        rec.crc = _u32(data, pos + 16)
        rec.compressed = _u32(data, pos + 20)
        rec.size = _u32(data, pos + 24)
        name_len = _u16(data, pos + 28)
        extra_len = _u16(data, pos + 30)
        comment_len = _u16(data, pos + 32)
        disk = _u16(data, pos + 34)
        attrs = _u32(data, pos + 38)
        rec.offset = _u32(data, pos + 42)
        needed = _u16(data, pos + 6)
        mode = (attrs >> 16) & 0o170000
        if (
            needed > 20
            or (rec.flags & ~0x808) != 0
            or rec.method not in (0, 8)
            or comment_len != 0
            or disk != 0
            or mode not in (0, 0o100000)
            or (attrs & 16) != 0
            or rec.compressed == 0xFFFFFFFF
            or rec.size == 0xFFFFFFFF
            or rec.offset >= central
        ):
            raise _bad("zip_attributes")
        raw_name = data[pos + 46: pos + 46 + name_len]
        if name_len < 1 or name_len > 96:
            raise _bad("zip_name")
        for byte in raw_name:
            if byte < 32 or byte > 126:
                raise _bad("zip_name")
        name = raw_name.decode("ascii")
        if not protocol.envelope_path(name):
            raise _bad("zip_path")
        rec.name = name
        rec.mtime = _extra_mtime(data, pos + 46 + name_len, extra_len)
        if name in records:
            raise _bad("duplicate")
        records[name] = rec
        try:
            cap = protocol.path_limit(name)
        except ValueError:
            raise _bad("path")
        if rec.size > cap or rec.compressed > protocol.MAX_ARCHIVE:
            raise _bad("declared_size")
        total += rec.size
        if total > protocol.MAX_TOTAL:
            raise _bad("total_size")
        pos += 46 + name_len + extra_len + comment_len

    if pos != central + central_size:
        raise _bad("zip_directory")
    if "manifest.json" not in records or "preferences.json" not in records:
        raise _bad("zip_directory")

    ordered = sorted(records.values(), key=lambda r: r.offset)
    nxt = 0
    for rec in ordered:
        if rec.offset != nxt or rec.offset + 30 > central:
            raise _bad("zip_offset")
        pos = rec.offset
        if _u32(data, pos) != 0x04034B50:
            raise _bad("zip_signature")
        needed = _u16(data, pos + 4)
        if needed > 20 or _u16(data, pos + 6) != rec.flags or _u16(data, pos + 8) != rec.method:
            raise _bad("zip_header")
        crc = _u32(data, pos + 14)
        compressed = _u32(data, pos + 18)
        plain = _u32(data, pos + 22)
        name_len = _u16(data, pos + 26)
        extra_len = _u16(data, pos + 28)
        start = pos + 30
        raw_name = data[start: start + name_len]
        if name_len < 1 or name_len > 96:
            raise _bad("zip_name")
        for byte in raw_name:
            if byte < 32 or byte > 126:
                raise _bad("zip_name")
        if raw_name.decode("ascii") != rec.name:
            raise _bad("zip_header")
        if _extra_mtime(data, start + name_len, extra_len) != rec.mtime:
            raise _bad("zip_extra_conflict")
        if (rec.flags & 8) == 0:
            if crc != rec.crc or compressed != rec.compressed or plain != rec.size:
                raise _bad("zip_header")
        else:
            if (crc and crc != rec.crc) or (compressed and compressed != rec.compressed) or (plain and plain != rec.size):
                raise _bad("zip_header")
        nxt = start + name_len + extra_len + rec.compressed
        if nxt > central:
            raise _bad("zip_offset")
        if rec.flags & 8:
            if _u32(data, nxt) == 0x08074B50:
                nxt += 4
            if _u32(data, nxt) != rec.crc:
                raise _bad("zip_descriptor")
            if _u32(data, nxt + 4) != rec.compressed or _u32(data, nxt + 8) != rec.size:
                raise _bad("zip_descriptor")
            nxt += 12
        if nxt > central:
            raise _bad("zip_offset")
        rec.end = nxt
    if nxt != central:
        raise _bad("zip_gap")
    return records


def read_entries(data):
    """严格校验后解出全部条目内容：{name: bytes}。"""
    records = inspect(data)
    out = {}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        if names != set(records):
            raise _bad("zip_entry")
        for name in sorted(records):
            rec = records[name]
            got = zf.read(name)
            if len(got) != rec.size:
                raise _bad("crc")
            if (_u32_crc(got) & 0xFFFFFFFF) != rec.crc:
                raise _bad("crc")
            out[name] = got
    return out, records


def _u32_crc(data):
    import zlib

    return zlib.crc32(data)


def build_zip(entries):
    """按客户端可接受的子集写 zip。entries: [(path, bytes)]，manifest.json 必须在首位。

    写出后立刻用 inspect() 自检，任何不合规都会在这里抛错，而不是等到客户端导入。
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=False) as zf:
        for path, blob in entries:
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0
            info.external_attr = 0
            info.internal_attr = 0
            info.extra = b""
            info.comment = b""
            zf.writestr(info, blob)
    data = buf.getvalue()
    inspect(data)  # 自检：不通过就抛 FormatError
    return data
