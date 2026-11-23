# 第三方组件与素材声明（THIRD-PARTY NOTICES）

本项目是**离线存档编辑器**，不包含、也不分发游戏 APK、游戏引擎或原生下载组件。
下面按实际随本项目分发/嵌入的内容登记归属与许可。

## 1. 游戏素材与主数据（非开源授权）

`assets/`（角色头像、卡面、结晶、礼物、道具图标、属性图标、精神树图标）与 `data/`（从安装包
MCATBIN1 与前端 libs 导出的主数据：名称、章节、剧情、结晶描述、觉醒链等）来自游戏
**マギアレコード 魔法少女まどか☆マギカ外伝**（Magia Record）。

- 权利归原版权方（Aniplex / f4samurai 及各自权利人）所有，**不在 GPL-3.0 覆盖范围内**；
- 本项目仅在本地做存档分析与编辑时读取这些数据，不主张任何再许可；
- 再分发素材属于再分发者的责任范围，请自行确认所在法域与用途。

## 2. 移植的玩法逻辑（GPL-3.0）

`magiasave/growth.py`、`magiasave/catalog.py` 的成长/强化/编成推算，以及存档容器
（`MagiaOfflineSlotArchive/v1` 分片、`json-shapes-v1`、`+gacha-history-details-cleared-v1`）
的编解码语义，移植自 MAGIA 复刻工程（`offline/` 部分的 `src/growth.js`、
`src/mental-enhancement.js`、`src/attribute-enhancement.js`、`src/deckFormation` 等）。

- 上游以 **GPL-3.0-only** 发布（文件头带 `SPDX-License-Identifier: GPL-3.0-only`）；
- 本项目因此整体以 GPL-3.0 发布，见 [LICENSE](LICENSE)；
- 上游工程自身的第三方声明（其 APK 产物里的 aria2 / GnuTLS / 字体等）见该工程根目录的
  `THIRD-PARTY-NOTICES.md`，**那些二进制本项目并不包含**，故不在此重复登记。

## 3. 运行时与打包

| 组件 | 版本 | 许可 | 用途 |
|---|---|---|---|
| Python | 3.10（本机构建） | PSF License 2.0 | 运行时，被 PyInstaller 一并打包 |
| PyInstaller | 6.x | GPL-2.0 **with bootloader exception** | 生成 `MagiaSaveEditor.exe`；引导程序例外允许以任意许可分发打包产物 |

前端（`web/`）为原生 JavaScript + CSS，无第三方框架或 CDN 依赖；后端只使用 Python 标准库
（`http.server`、`zipfile`、`tkinter` 等），不依赖任何 pip 包。

## 4. 不含的组件

为免误解，本项目**不包含**以下上游 APK 里的第三方二进制：aria2 / OpenSSL / GnuTLS /
nettle / GMP / libxml2 / sqlite3 / libssh2、以及任何字体文件与汉化补丁。
