"""MagiaOfflineSlotArchive/v1 容器读写。

职责：
  * 严格解析/校验存档 zip（对齐 CNOfflineSlotArchive.inspect + readArchive）
  * 拼装 head/part 得到 profile，识别 json-shapes-v1 编码
  * 重新分片并写出新的存档 zip（bank 交替、revision+1、manifest 重算 sha256）
"""

import hashlib
import json
import os

from . import jsjson, protocol, slot, zipfmt
from .errors import ArchiveError, FormatError, ValidationError


def _sha256(blob):
    return hashlib.sha256(blob).hexdigest()


class SlotArchive:
    """一个存档包（.zip）的内存模型。"""

    def __init__(self, path=None):
        self.path = path
        self.manifest = None
        self.preferences = {"calendar": None, "draft": None}
        self.native = {}          # 'native/xxx' -> bytes
        self.state_raw = {}       # ns -> raw json text
        self.state = {}           # ns -> parsed object
        self.head = None
        self.head_ns = None
        self.stored_raw = ""      # head 声明 bank 的拼接原文（可能是编码文本）
        self.profile = None
        self.profile_text = ""    # 规范化后的 profile JSON 文本（未编码）
        self.entries = {}         # 原始 zip 条目 -> bytes
        self.digests = {}         # name -> sha256（载入时校验通过的值）

    # ------------------------------------------------------------ 载入

    @classmethod
    def load(cls, path):
        if not os.path.isfile(path):
            raise ArchiveError("存档不存在: %s" % path, code="save_archive_missing")
        with open(path, "rb") as handle:
            blob = handle.read()
        if len(blob) > protocol.MAX_ARCHIVE:
            raise ArchiveError("save_archive_zip_size", code="save_archive_zip_size")
        entries, _records = zipfmt.read_entries(blob)
        archive = cls(path)
        archive.entries = entries
        archive._parse(entries)
        return archive

    def _parse(self, entries):
        # manifest.json
        try:
            manifest = json.loads(entries["manifest.json"].decode("utf-8"))
        except Exception as exc:
            raise FormatError("save_archive_json: %s" % exc, code="save_archive_json")
        if not isinstance(manifest, dict) or set(manifest.keys()) != {"schema", "version", "template", "label", "entries"}:
            raise FormatError("save_archive_fields", code="save_archive_fields")
        if manifest["schema"] != protocol.SCHEMA or manifest["version"] != 1:
            raise FormatError("save_archive_schema", code="save_archive_schema")
        template = manifest["template"]
        if template not in protocol.BUILTIN_TEMPLATES:
            raise FormatError("save_archive_metadata", code="save_archive_metadata")
        label = manifest["label"]
        if not isinstance(label, str) or not label.strip() or len(label) > 80 or "\0" in label:
            raise FormatError("save_archive_metadata", code="save_archive_metadata")
        self.manifest = manifest

        expected = {}
        for row in manifest["entries"]:
            if not isinstance(row, dict) or set(row.keys()) != {"path", "bytes", "sha256"}:
                raise FormatError("save_archive_manifest_entries", code="save_archive_manifest_entries")
            path = row["path"]
            if path != "preferences.json" and not protocol.archive_leaf(template, path):
                raise FormatError("save_archive_namespace: %s" % path, code="save_archive_namespace")
            if path in expected:
                raise FormatError("save_archive_manifest_entries", code="save_archive_manifest_entries")
            expected[path] = row
        if "preferences.json" not in expected:
            raise FormatError("save_archive_preferences_missing", code="save_archive_preferences_missing")
        if len(expected) != len(entries) - 1:
            raise FormatError("save_archive_manifest_entries", code="save_archive_manifest_entries")

        for path, row in expected.items():
            blob = entries.get(path)
            if blob is None:
                raise FormatError("save_archive_manifest_entries: %s" % path, code="save_archive_manifest_entries")
            if len(blob) != row["bytes"] or _sha256(blob) != row["sha256"]:
                raise FormatError("save_archive_sha256: %s" % path, code="save_archive_sha256")
            self.digests[path] = row["sha256"]

        # preferences.json
        try:
            prefs = json.loads(entries["preferences.json"].decode("utf-8"))
        except Exception as exc:
            raise FormatError("save_archive_json: %s" % exc, code="save_archive_json")
        self.preferences = slot.validate_preferences(prefs)

        # state / native
        for path, blob in entries.items():
            if path.startswith("state/"):
                ns = path[6:-5]
                text = blob.decode("utf-8")
                try:
                    self.state_raw[ns] = text
                    self.state[ns] = json.loads(text)
                except Exception as exc:
                    raise FormatError("save_archive_json: %s (%s)" % (ns, exc), code="save_archive_json")
            elif path.startswith("native/"):
                self.native[path] = blob

        self._load_profile(template)
        self._check_selected(template)

    def _load_profile(self, template):
        head_ns = "off3_%s_head" % template
        head = self.state.get(head_ns)
        if head is None:
            for bank in ("a", "b"):
                for index in range(protocol.MAX_PARTS):
                    if "off3_%s_%s_%d" % (template, bank, index) in self.state:
                        raise FormatError("profile_head_missing_parts_preserved",
                                          code="profile_head_missing_parts_preserved")
            raise FormatError("存档内没有已提交的 profile（缺少 %s）" % head_ns,
                              code="save_slot_backup_empty")
        slot.parse_head(head)
        raw = slot.assemble_raw(head, self.state, "off3_" + template)
        self.head = head
        self.head_ns = head_ns
        self.stored_raw = raw
        encoding = head.get("encoding")
        profile, canonical = slot.decode_stored(raw, encoding)
        if not slot.template_matches_kind(template, profile):
            raise ValidationError(
                "profile.kind=%r 与模板 %r 不匹配" % (profile.get("kind"), template),
                code="save_slot_template_mismatch",
            )
        self.profile = profile
        self.profile_text = canonical

    def _check_selected(self, template):
        selected = self.state.get("off3_selected")
        if selected is not None:
            if not isinstance(selected, dict) or set(selected.keys()) != {"id"}:
                raise ValidationError("off3_selected 字段非法", code="save_archive_selected")
            if selected["id"] != template:
                raise ValidationError("off3_selected.id != template", code="save_archive_selected")

    # ------------------------------------------------------------ 摘要

    @property
    def template(self):
        return self.manifest["template"]

    @property
    def label(self):
        return self.manifest["label"]

    @property
    def revision(self):
        return self.head["revision"]

    @property
    def encoding(self):
        return self.head.get("encoding")

    def summary(self):
        return {
            "path": self.path,
            "label": self.label,
            "template": self.template,
            "revision": self.revision,
            "bank": self.head["bank"],
            "parts": self.head["parts"],
            "bytes": self.head["bytes"],
            "encoding": self.encoding,
            "storedBytes": jsjson.utf8_len(self.stored_raw),
            "profileBytes": jsjson.utf8_len(self.profile_text),
            "kind": self.profile.get("kind"),
            "entries": len(self.entries),
            "native": sorted(self.native),
            "stateNamespaces": sorted(self.state),
            "preferences": self.preferences,
        }

    # ------------------------------------------------------------ 写出

    def serialize_state(self, exclude_bank=None):
        """当前 state 命名空间 -> 原始文本。

        head 由调用方重写；只有即将被覆盖的那个 bank 的分片被替换，
        另一个 bank（客户端用它做回滚副本）原样保留。
        """
        out = {}
        for ns, value in self.state.items():
            if ns == self.head_ns:
                continue
            if exclude_bank and ns.startswith("off3_%s_%s_" % (self.template, exclude_bank)):
                continue
            original = self.state_raw.get(ns)
            text = jsjson.dumps(value) if original is None else original
            out[ns] = text
        return out

    def build_entries(self, profile=None, preferences=None, label=None, revision=None, bank=None):
        """生成新的 zip 条目（含 head/part 重分片）与 manifest 行。"""
        profile = self.profile if profile is None else profile
        preferences = self.preferences if preferences is None else preferences
        label = self.label if label is None else label
        validation = slot.validate_preferences(preferences)
        if not isinstance(label, str) or not label.strip() or len(label) > 80 or "\0" in label:
            raise ValidationError("save_archive_metadata: label", code="save_archive_metadata")
        kind = profile.get("kind")
        if kind not in protocol.VALID_KINDS:
            raise ValidationError("invalid_profile: kind=%r" % (kind,), code="invalid_profile")
        if not isinstance(profile.get("state"), dict) or profile.get("formatVersion") != 1:
            raise ValidationError("invalid_profile", code="invalid_profile")
        if not slot.template_matches_kind(self.template, profile):
            raise ValidationError("save_slot_template_mismatch", code="save_slot_template_mismatch")

        new_revision = self.revision + 1 if revision is None else int(revision)
        if not (1 <= new_revision <= 2 ** 53 - 1):
            raise ValidationError("invalid_profile_head: revision", code="invalid_profile_head")
        new_bank = bank or ("b" if self.head["bank"] == "a" else "a")
        if new_bank not in ("a", "b"):
            raise ValidationError("invalid_profile_head: bank", code="invalid_profile_head")

        raw = jsjson.dumps(profile)
        # 未改动时直接复用磁盘上的原始存储文本：不重新序列化、不重排、不改编码。
        if raw == jsjson.dumps(self.profile):
            stored = self.stored_raw
            encoding = self.head.get("encoding")
            parts = slot.split_parts(stored, new_revision, limit=protocol.MAX_PARTS)
            if parts is None:
                raise ValidationError("profile_capacity_exceeded", code="profile_capacity_exceeded")
            parts = [(new_revision, index, data) for index, (_r, _i, data) in enumerate(parts)]
            head = slot.build_head(new_bank, new_revision, parts, jsjson.utf8_len(stored), encoding)
            return self._emit(head, parts, stored, label, validation)

        history = slot.has_cleared_history(profile)
        parts = None
        encoding = None
        stored = None
        if history:
            packed = slot.encode_profile(raw, profile)
            parts = slot.split_parts(packed, 1, limit=protocol.MAX_PARTS)
            if parts is None:
                raise ValidationError("profile_capacity_exceeded", code="profile_capacity_exceeded")
            encoding = protocol.HISTORY_ENCODING
            stored = packed
        else:
            candidate = slot.split_parts(raw, 1, limit=protocol.LEGACY_PARTS)
            if candidate is not None:
                parts = candidate
                stored = raw
            else:
                packed = slot.encode_profile(raw, profile)
                if jsjson.utf8_len(packed) < jsjson.utf8_len(raw):
                    parts = slot.split_parts(packed, 1, limit=protocol.MAX_PARTS)
                    if parts is not None:
                        encoding = protocol.PROFILE_ENCODING
                        stored = packed
                if parts is None:
                    parts = slot.split_parts(raw, 1, limit=protocol.MAX_PARTS)
                    stored = raw
                    if parts is None:
                        raise ValidationError("profile_capacity_exceeded", code="profile_capacity_exceeded")

        parts = [(new_revision, index, data) for index, (_rev, _idx, data) in enumerate(parts)]
        # 片内 revision 必须等于 head 的 revision
        head = slot.build_head(new_bank, new_revision, parts, jsjson.utf8_len(stored), encoding)
        return self._emit(head, parts, stored, label, validation)

    def _emit(self, head, parts, stored, label, validation):
        new_bank = head["bank"]
        body = self.serialize_state(new_bank)
        # 丢掉将被覆盖的 bank 里的同 bank 旧片，保留另一 bank 作为回滚副本
        for ns in list(body):
            if ns.startswith("off3_%s_%s_" % (self.template, new_bank)):
                del body[ns]
        body[self.head_ns] = jsjson.dumps(head)
        for revision_of_part, index, data in parts:
            body["off3_%s_%s_%d" % (self.template, new_bank, index)] = jsjson.dumps(
                {"revision": revision_of_part, "part": index, "data": data}
            )
        body["off3_selected"] = jsjson.dumps({"id": self.template})

        blobs = {}
        for ns, text in body.items():
            blobs["state/%s.json" % ns] = text.encode("utf-8")
        for path, blob in self.native.items():
            blobs[path] = blob
        blobs["preferences.json"] = jsjson.dumps(validation).encode("utf-8")

        total = sum(len(blob) for blob in blobs.values())
        if total > protocol.MAX_TOTAL:
            raise ValidationError("save_archive_total_size", code="save_archive_total_size")
        rows = []
        ordered = {}
        for path in sorted(blobs):
            blob = blobs[path]
            try:
                cap = protocol.path_limit(path)
            except ValueError:
                raise ValidationError("save_archive_path: %s" % path, code="save_archive_path")
            if len(blob) > cap:
                raise ValidationError("save_archive_declared_size: %s" % path, code="save_archive_declared_size")
            ordered[path] = blob
            rows.append({"path": path, "bytes": len(blob), "sha256": _sha256(blob)})
        manifest = {
            "schema": protocol.SCHEMA,
            "version": 1,
            "template": self.template,
            "label": label,
            "entries": rows,
        }
        manifest_blob = jsjson.dumps(manifest).encode("utf-8")
        if len(manifest_blob) > protocol.MAX_MANIFEST or total + len(manifest_blob) > protocol.MAX_TOTAL:
            raise ValidationError("save_archive_manifest_size", code="save_archive_manifest_size")
        entries = [("manifest.json", manifest_blob)]
        for path in sorted(ordered):
            entries.append((path, ordered[path]))
        if len(entries) > protocol.MAX_ENTRIES:
            raise ValidationError("save_archive_entry_count", code="save_archive_entry_count")
        return entries, manifest, head, stored

    def save(self, out_path, profile=None, preferences=None, label=None):
        """写出新的存档 zip，返回写出后的摘要。不覆盖原文件除非显式指定。"""
        entries, manifest, head, stored = self.build_entries(profile, preferences, label)
        blob = zipfmt.build_zip(entries)
        out_path = os.path.abspath(out_path)
        if self.path and os.path.abspath(self.path) == out_path:
            raise ValidationError("拒绝覆盖原存档，请另存为新文件", code="save_archive_overwrite")
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        tmp = out_path + ".tmp"
        with open(tmp, "wb") as handle:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, out_path)
        # 写出后立刻回读，确保客户端同款解析器能接受
        check = SlotArchive.load(out_path)
        self.manifest = manifest
        self.head = head
        self.stored_raw = stored
        return {"path": out_path, "size": len(blob), "revision": check.revision,
                "parts": check.head["parts"], "encoding": check.encoding,
                "label": check.label, "bytes": check.head["bytes"]}
