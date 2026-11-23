"""存档协议常量与路径白名单。

逐条对齐：
  CNOfflineSlotLibrary.allowedNamespace / nativeFile / archiveLeaf
  CNOfflineSlotArchive.limit / SCHEMA / MAX_*
"""

import re

SCHEMA = "MagiaOfflineSlotArchive/v1"
SCHEMA_VERSION = 1

MAX_ARCHIVE = 160 * 1024 * 1024        # CNOfflineSlotArchive.MAX_ARCHIVE
MAX_TOTAL = 128 * 1024 * 1024          # CNOfflineSlotArchive.MAX_TOTAL
MAX_ENTRIES = 256                      # MAX_ENTRIES
MAX_MANIFEST = 128 * 1024              # MAX_MANIFEST
MAX_PREFERENCES = 16384                # MAX_PREFERENCES
PART_BYTES = 512 * 1024                # CNOfflineSlotLibrary.PART / profiles.js MAX_BYTES
MAX_PARTS = 32                         # profiles.js MAX_PARTS
LEGACY_PARTS = 8                       # profiles.js LEGACY_PARTS
STORED_BYTES = MAX_PARTS * PART_BYTES  # CNOfflineProfileReader.STORED_BYTES

PROFILE_ENCODING = "json-shapes-v1"
HISTORY_ENCODING = PROFILE_ENCODING + "+gacha-history-details-cleared-v1"

BUILTIN_TEMPLATES = ("new", "progress", "full")
PROFILE_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,11}$")
TEMPLATE_KIND = {
    "new": "new",
    "progress": "imported-progress",
    "full": "full-unlock",
}
VALID_KINDS = ("new", "imported-progress", "halfway", "full-unlock")

_NATIVE_FILE_RE = re.compile(
    r"^(?:start\.json|send\.json|replay\.bin|record\.json|storyData\.json|data[0-9]{1,24}\.bin|entryQuest\.json)$"
)


def native_file(name):
    """CNOfflineSlotLibrary.nativeFile：只有这些叶子文件可以进入存档。"""
    return bool(_NATIVE_FILE_RE.match(name or ""))


def allowed_namespace(preset, ns):
    """CNOfflineSlotLibrary.allowedNamespace：state/ 下的命名空间白名单。"""
    if preset not in BUILTIN_TEMPLATES:
        return False
    if not ns or len(ns) > 48:
        return False
    if ns == "off3_selected":
        return True
    pattern = (
        r"^off3_(?:bak_)?" + re.escape(preset) + r"_(?:head|[ab]_(?:[0-9]|[12][0-9]|3[01]))$"
    )
    if re.match(pattern, ns):
        return True
    if ns == "off3_diag_" + preset:
        return True
    return bool(re.match(r"^off3_(?:replay|activity)_" + re.escape(preset) + r"(?:_[a-z0-9]{1,10})?$", ns))


def archive_leaf(preset, path):
    """CNOfflineSlotLibrary.archiveLeaf：manifest 里允许出现的条目路径。"""
    if not path:
        return False
    if path.startswith("state/") and path.endswith(".json"):
        return allowed_namespace(preset, path[6:-5])
    return path.startswith("native/") and native_file(path[7:])


def envelope_path(path):
    """CNOfflineSlotArchive.envelopePath：zip 条目路径必须是可识别的存档成员。"""
    if path in ("manifest.json", "preferences.json"):
        return True
    for preset in BUILTIN_TEMPLATES:
        if archive_leaf(preset, path):
            return True
    return False


def path_limit(path):
    """CNOfflineSlotArchive.limit：每个条目的解压后字节上限。"""
    if path == "manifest.json":
        return MAX_MANIFEST
    if path == "preferences.json":
        return MAX_PREFERENCES
    if path.startswith("state/"):
        return PART_BYTES
    if path == "native/entryQuest.json":
        return 16384
    if path.startswith("native/"):
        return 32 * 1024 * 1024
    raise ValueError("save_archive_path: %s" % path)


HEAD_RE_TMPL = r"^off3_%s_head$"
