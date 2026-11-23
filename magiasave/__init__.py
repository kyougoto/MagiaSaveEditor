"""Magia☆Record 离线存档编辑器（本地私服存档格式支持）。

格式来源：MAGIA-1.6.4-b1713001033-current-source-d566da53.zip
  - magia-native/src/archive_core.cpp
  - patch/src/main/java/io/kamihama/magianative/CNOfflineSlotArchive.java
  - patch/src/main/java/io/kamihama/magianative/CNOfflineSlotLibrary.java
  - patch/src/main/java/io/kamihama/magianative/CNOfflineProfileReader.java
  - offline/src/profiles.js

存档容器：MagiaOfflineSlotArchive/v1（纯数据 zip）
存档内容：head/part 分片协议 off3_<id>_<bank>_<n> + off3_<id>_head
"""

__version__ = "1.0.0"

from .errors import ArchiveError, FormatError, ValidationError  # noqa: F401
from . import jsjson, zipfmt, slot, archive, model, growth, masters, catalog  # noqa: F401
