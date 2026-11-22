# 魔法纪录 离线存档编辑器

面向 `MAGIA-1.6.4`（b1713001033）本地私服存档的读写工具：解析 `MagiaOfflineSlotArchive/v1` 容器，
还原 `off3_*` 分片协议与 `json-shapes-v1` 编码，本地 Web 界面，落盘前用客户端同款规则自检。
**完全自包含**：主数据与素材图都在 `data/` 与 `assets/` 里，运行时不依赖游戏数据包。

## 六条需求的落地状态

| 需求 | 实现 | 证据 |
|---|---|---|
| 1 不支持的部分保持原样 | 未改动时逐字节复用 `stored_raw`；每次事务做路径级 diff，任何白名单外的变化整体回滚；未知枚举值（如历史 `missionStatus`）不被批量覆盖 | `tests/test_features.py` 前四项 PASS |
| 2 魔法少女解析 | 角色行 `userCharaList.userCardId` → 卡片行 `userCardList.id` 关联（此前误用 `userCardId` 作键导致卡片列全空）；属性/学校/卡名/等级/HP/攻防全部在场 | `PASS 角色能关联到卡片 :: 5/5`、`PASS 角色属性有值 :: ['光','木','火','水','光']` |
| 3 数值只读 + 游戏逻辑推算 | `attack/defense/hp` 写入直接拒绝（`stat_readonly`）；改 `level/lbCount/experience` 后按 `growth` 模块重算 | `PASS 等级改动按公式重算数值 :: 存档 {'attack': 2862, 'defense': 3790, 'hp': 10035} / 公式 {...}` |
| 4 游戏素材 + gift 分类 | 图标复制进 `assets/`（32.4 MB），界面缩略图；gift 按官方 ID 段分成 宝玉/书/魔女素材/碎片等组 | `PASS 素材图已复制到编辑器目录`、`PASS 养成素材已分组` |
| 16 角色二级界面 | 一览只显示魔法少女（卡面作头像），点进详情分别编辑卡片养成 / 角色数据 / 只读数值 / 同角色各星级 | `PASS 角色详情含卡片养成字段`、`PASS 详情列出该角色各星级` |
| 17 同角色唯一 | `card.add` 强制「同一 charaId 只能有一张卡」，不同星级也不可并存 | `PASS 同一角色不能再拿第二张卡 :: chara_already_owned` |
| 18 头像来源修正 | `chara_<id>_h.png` 实为命运宝石图标 → 移到 `assets/gem/`；头像改用卡面 `card_<cardId>_s.png` | `PASS 角色头像用卡面而非命运宝石 :: /assets/cards/10012.png / /assets/gem/1001.png` |
| 19 挑战语义 | 目标次数取 APK master 的 challenge.count（1,483 条全部带次数），已达成是累计次数不是开关；文案只用来显示标签 | `PASS 挑战目标次数来自官方文案`、`PASS 按目标补满会写入目标次数` |
| 13 完整剧情 | 数据包提取 8787 个任务 / 2346 个小节（存档只有 727 / 112）；任务页与小节页可切到「含数据包全量」，未收录行标「未收录」并带「补行」按钮 | `PASS 数据包任务数大于存档收录 :: catalog 9077 / stored 727`、`PASS 未收录任务可以补行` |
| 14 名称优先 | 任务显示「第 N 战 · BOSS」，章节/话用官方标题，挑战用条件文案，扭蛋用种类标签；内部 ID 一律降为灰色小字 | `PASS 任务带可读标签 :: ['第 1 战', '第 2 战', '第 1 战']`、`PASS 挑战带可读标签 :: 通关剧情3次` |
| 15 养成素材选项卡 | 105 种素材按 9 类做选项卡切换，不再平铺 | `PASS 养成素材已分组`（9 组）+ 页面顶部分类条 |
| 11 逐条调节 | 小节（可玩 / 已通）、章节（已通）、挑战（达成次数）、扭蛋（总次数 / count）、任务（3 个任务标记 + 通关状态）都能单条切换，不再只有"全部完成/未完成" | `PASS 直接改卡片攻击被拒绝`…（见 test 输出）、逐条 ops 见下 | 
| 12 道具可见性 | 424 种玩家可见道具（图标 / itemType / 商店 / 奖励 / 货币 五类证据），905 种内部道具默认隐藏，可一键切到全部 | `PASS 默认只显示玩家可见道具 :: player 424 / all 1329`、`PASS 可见性判定带证据 :: ['currency','icon','reward','shop']` |
| 7 道具按活动分类 | 三层导航：类型（通用素材 / 每日塔 / 分支活动 / 扭蛋活动 …共 16 类）→ 活动（635 组，296 种带 official eventList 活动名）→ 道具 | `PASS 道具一级分类`、`PASS 二级活动分组`、`PASS 活动组带官方活动名` |
| 8 全量显示 | 道具 1329 种、养成素材 105 种全部列出，未拥有显示 0 | `PASS 道具全量（含未拥有）:: 1329 vs 1329`、`PASS 未拥有道具数量显示为 0` |
| 9 任务 / 小节多级列表 | 部 → 章 → 话 → 任务；章名取 chapterList 官方名（101 → 第1部 章号 N = chapterId 10+N；102 → 第2部 章号 N = 21+N，序章 = 102001..005） | `PASS 主线按部归属`、`PASS 章使用官方章名 :: ['第1章 起始之彩羽', ...]` |
| 10 页内选择器 + 网格 | 添加操作改为页内模态框（搜索 + 卡片网格）；道具/素材/结晶/角色页改为网格布局（每页 200 / 120） | `PASS 分页 offset 生效`，`node --check web/app.js` |
| 5 结晶自由添加 | `piece.add` 从 1042 条已实装结晶里选，数值按公式生成合法行；**同一结晶可重复获取**，每枚独立 id 与等级/突破 | `PASS 结晶添加成功 :: 1563`、`PASS 同一结晶可重复获取（多枚独立行）` |
| 6 翻页按钮 | 前端改为「渲染完成后统一绑定」，事件绑定时机确定 | `PASS 分页 offset 生效`，`node --check web/app.js` 通过 |

## 数值推算：用游戏逻辑，不猜

逻辑来源是私服自身实现 `offline/src/growth.js`（注释说明它来自客户端 `CardUtil` 公式证据）：

* 卡片：`MAX=[0,40,50,60,80,100]`、`CURVE=[0,200,220,240,260,300]`、`TYPES` 成长系数，
  `coefficient = floor((level-1)*CURVE[rank]/(MAX[rank]-1))/100`，`stat = floor(base + base*coefficient*growth)`
* 结晶：`PIECE_CURVES[rank-1][level]` 整数百分比表，`pieceMaxLevel = [10,15,20,30][rank-1] + lbCount*5`
* 经验表：`CARD_EXP` / `PIECE_EXP`

基础数值（`rank`/`growthType`/`attack`/`defense`/`hp`）由 `tools/build_masters.py` 从数据包内嵌的
官方 card/piece 定义聚合：**445 张卡 / 915 枚结晶**（`data/cards.json`、`data/pieces.json`）。

验证：对 chino 存档逐项比对，存档内数值与推算值 **卡片 15/15、结晶 35/35 完全一致**
（缺基础值的 2 张卡 + 1 枚结晶在界面里禁用等级输入，不做推测）。

## 分类与层级

**道具（三层导航）**：`tools/build_item_groups.py` 解析官方 `itemCode` 得到 (族, 活动号)，再用
`eventList.json` 的官方活动名做组名：

组内**默认按 itemCode 排序**（另可选按名称 / 按数量），数量为零的条目不会被打散。

```
类型（16 类）        例：通用 / 系统 193 种 · 每日塔 443 种 · 分支活动 82 种 · 扭蛋活动 211 种
  └─ 活动组（635）  例：三日月别墅的Merry Christmas · 每日塔（4 种）
       └─ 道具      例：EVENT_DAILYTOWER_1010_EXCHANGE_1
```

**任务 / 小节（四级）**：
```
部 → 章 → 话 → 任务
第1部 → 第1章 起始之彩羽 → 小丘比（新西中央车站） → 10110151 / 10110152 …
第2部 → 第1章 前言和脚步声一同 → 两条前行之路 → …
```
部的判定依据：101 段的章 7/8/9 与 chapterList 的 `NORMALSECTIONID=101718/101881/101972` 对齐，
章号 N → chapterId = 10+N；102 段章号 0 的 5 个小节对应 chapterList 21「序章」，章号 N → 21+N。
103/104 段没有官方章号序列，标签标明部段编号后用「第N章 · 该章首个话的标题」，不编造篇名。

## 记忆结晶与队伍

结晶页支持按**星级**与**类型**（能力 / 技能）筛选，筛选项直接来自存档里实际拥有的值；点卡片进入详情。
添加弹窗同样带这两个筛选，数据源是 `pieceList` 全量（1,042 条）。

**结晶详情**显示：稀有度、类型、种类、属性、只读数值（HP / 攻 / 防）、等级与突破编辑、中文描述、
技能（名称 + 效果说明）、以及**被编成到的队伍**（队伍名 / 第几位 / 槽几，可能同时出现在多个队伍）。

数据来源：

| 内容 | 来源 |
|---|---|
| 描述 | `libs/pieceList.json`（中文），回退 master |
| 技能名 / 说明 | `libs/pieceSkillMap.json`（2,109 条中文） |
| 种类 / 技能 id | MCATBIN1 `tables.piece` |

`tools/export_pieces_detail.py` 生成 `data/pieces-detail.json`（1,041 条）。

**队伍页**（新 tab）：每个编成一块，显示 4 个成员位与各自的结晶槽。点角色跳到角色详情，点结晶跳到结晶详情。
队伍第 1–4 位可编辑（换人 / 移除 / 加结晶 / 卸结晶），**支援位由好友填充，不能放自己的角色**，
界面上单独标注阵型位置（`questPositionHelper`），`deckType >= 20` 的其他编成只读。

约束：同一张卡不能在一个队伍里重复上阵；同一枚结晶不能同时装在两处（`piece_already_equipped`）。
换人时会清空该位置的结晶槽。

```
deck.member        { deckType, slot(1-4), userCardId }
deck.removeMember  { deckType, slot }
deck.piece         { deckType, member(1-4), slot(1-5), pieceInstanceId }
deck.removePiece   { deckType, member, slot }
```
## 角色剧情 / 衣装剧情 / 衣装获取状态

角色详情页里新增两个面板，数据全部来自安装包：

| 面板 | 数据来源 | 规模 |
|---|---|---|
| 剧情（角色 / 衣装） | `catalog` 的 `tables.section`（charaId / genericId / questType） + `tables.questBattle`（section → 任务） + `libs/sectionList.json`（中文标题与简介） | 2,397 段（角色 907 / 衣装 87） |
| 衣装 | `libs/live2dList.json`（live2dId / 中文名 / 语音前缀） | 230 角色 888 件 |

`tools/export_stories.py` 生成 `data/stories.json` 与 `data/costumes.json`。

归属规则照客户端 `CharaQuest.js`：**角色剧情用 `section.genericId` 匹配角色**（不是 charaId），**衣装剧情用 `section.charaId`**，衣装 id 取 `genericId` 末两位。
所以环彩羽（1001）只有 310011–310014 四段 —— 313/314/315 那些 charaId 也是 1001 但 genericId 是 1301/1401/1501 的段，属于另一个形态，不进入这个角色的页面。

**首通奖励**按种类翻中文：道具查 itemList、结晶查 pieceList、魔女化身查 doppelList、衣装用「角色名的衣装【衣装名】」（衣装表）、命运宝石直接写中文。全库 1,398 条奖励（道具 782 / 衣装 164 / 结晶 229 / 魔女化身 217 / 宝石 6）没有一条剩日文。

面板顶部有提示：**这里只改存档里的通关状态，不会发放首通奖励**（道具 / 衣装 / 结晶 / 魔女化身 / 命运宝石都不会进仓库），也不会解锁关卡。

**剧情面板**：角色剧情与衣装剧情各一张表，列出段号、标题、AP、首通奖励、段内任务进度、通关状态。
「通关 / 回退」调用 `story.set`：一次性写 `userSectionList.cleared` 与段内所有 `userQuestBattleList`，
缺的段/任务行自动补出；原本是 `NONE`（该任务没有这条条件）的标记保持不动。

**魔力（Magia）面板**另带一个魔女化身（Doppel）开关：显示名称、称号、doppelId 与解锁状态，「解锁 / 取消解锁」写 `userDoppelList`（`{userId, doppelId, createdAt}`，照 settlement.js）。角色→doppel 的映射来自 `tables.card[].doppel`（默认卡与进化链），中文名取 `libs/doppelList.json`（217 条）。

**衣装面板**：每件衣装显示名称、live2dId、是否已获取、是否当前穿着。三个操作：

| 操作 | 写入 | 规则 |
|---|---|---|
| 获取 | `userLive2dList` 追加一行 | 必须在官方衣装表里 |
| 取消获取 | 删除该行 | **默认服装（live2dId 00）拒绝**，正在穿着的也拒绝（先换掉） |
| 设为当前 | `userCharaList.live2dId` | 必须已拥有（默认服装除外） |

默认服装在界面上标「默认服装 · 不可取消」，后端是 `costume_default_locked` —— 战斗与剧情都依赖这身，
取消它会让客户端取不到服装而崩溃。
## 精神强化 / 属性强化 / 觉醒

三套数据都来自 APK 里的真 master：assets/magia/offline/catalog.json（57 MB）不是 JSON，
而是紧凑容器 MCATBIN1（格式见 patch/src/.../CNCompactCatalog.java）：

    magic "MCATBIN1"(8B) | count i32 | root i32 | length i32 | 节点池
    type 0 null / 1 false / 2 true / 3 double(BE) / 4 string(u32+utf8) /
         5 array(u32 n + n*u32) / 6 object(u32 n + n*(keyId,valueId))
    子节点 id 必须小于父节点（forward reference 校验）

解出 743,567 个节点后由 tools/export_advanced.py 导出：

| 文件 | 内容 | 数量 |
|---|---|---|
| data/spirit.json | 精神树节点（类型 / 效果 / 前置 / 碎片 / 坐标 / 连线 / 情感技能） | 23,248 节点 · 230 组 · 230 角色 · 3,058 技能 |
| data/attribute.json | 属性强化格（6 属性 × 3 项 × 4 段）与消耗材料名 | 72 格 · 221 角色 |
| data/awakening.json | 突破规则、卡片定制槽、觉醒链、卡片基础值 | 230 角色 · 525 卡 |

**精神树**按 pointX/pointY 原样绘成 SVG（前端 spiritTreeSvg），节点内嵌游戏原图 icon_hp|atk|def|accele|blast|charge|skill|ability，连线取 connectedCellIdList，
根节点落在 (2048, 2048) 六向辐射，100 个节点的组与游戏界面同构。类型分色：
类型由图标区分；圆框按状态着色：已开启紫、可开启绿虚线、选中金、起点金圈。
开启节点写入 userCharaEnhancementCellList，并按 mental-enhancement.js 的 summary() 重算
addendHp / addendAttack / addendDefense / addendAccelBonus / addendBlastBonus / addendChargeBonus
与 emotionSkillList / emotionSkillIds；SKILL 节点写入完整 emotionSkill 对象（客户端 battleState
会逐字段比对，只写 id 会报 spirit_skill_definition_mismatch）。needOpenedCellId 前置链在开启时
自动补齐，关闭时若有节点依赖则拒绝。

**属性强化**写 userCharaAtbEnhancementCellList（{userId,charaId,atbEnhancementCellId,createdAt}），
状态值累加到 userStatusList[statusId].point（statusId 就是 FIRE_HP 这类格子类型），总战力按
effectValue × 同属性已拥有角色数 累加 —— 与 attribute-enhancement.js 的 forces = deltas[k] * count 一致。
开启门槛是该卡 revision ≥ openingConditions 的段号。

**觉醒与突破**：突破写 card.revision（0→3），每级 +500 总战力；需求命运宝石按初始稀有度
（RANK_1/2 = 10、RANK_3 = 3、RANK_4/5 = 1）与 costByRevision=[5000,10000,50000]。
觉醒槽位写 customized1..6，每槽 +200 总战力；可以单格填充，也可以全部填充，填充本身不触发升星，
升星仍按游戏流程（满级 + 全部槽位）。

名称全部取官方中文 libs（files/magica/js/libs）：素材名用 giftList.json / itemList.json，情感技能名与说明用 emotionSkillMap.json（3,058 条，已并入 data/catalog.json 的 emotionSkills），日文只作 master fallback。

**材料只展示，不消耗**：这三套操作不写 userGiftList、userItemList、gameUser.riche，
界面只标「需要 / 持有」，缺料标红。精神树的碎片与 CC、属性强化的 COMPOSE_ITEM_*、
突破的命运宝石与 LIMIT_BREAK_ALL、觉醒的 gift 都按这条处理。

## 素材本地化

`tools/fetch_assets.py` 把需要的图复制进 `assets/`：

| 分组 | 复制 / 应有 | 体积 |
|---|---|---|
| gifts（`item_gift_<id>.png`） | 105 / 105 | 0.5 MB |
| chara（`chara_<id>_h.png`） | 230 / 231 | 6.6 MB |
| cards（`card_<id>_s.png`） | 525 / 530 | 10.1 MB |
| pieces（`memoria_<id>_s.png`） | 1042 / 1042 | 13.5 MB |
| items（`<itemCode>.png`） | 213 / 1329 | 1.7 MB |
| spirit（`image_web/page/chara/tree/icon_*.png`） | 15 | 68 KB |

官方没提供的道具图标不伪造，前端显示占位。重跑：
`python tools/fetch_assets.py --data-root "H:/magia_server/io.kamihama.totentanz/files"`。

## 存档格式（从源码还原）

证据：`CNOfflineSlotArchive.java`、`CNOfflineSlotLibrary.java`、`CNOfflineProfileReader.java`、
`CNProfileJSON.java`、`magia-native/src/archive_core.cpp`、`offline/src/profiles.js`。

```
manifest.json      {"schema":"MagiaOfflineSlotArchive/v1","version":1,"template":"new|progress|full",
                    "label":"≤80","entries":[{"path","bytes","sha256"}, ...]}
preferences.json   {"calendar":{...}|null,"draft":"yyyy/MM/dd HH:mm:ss"|null}
state/off3_<id>_head.json        {"formatVersion":1,"bank":"a|b","revision":N,"parts":N,"bytes":N[,"encoding"]}
state/off3_<id>_<bank>_<n>.json  {"revision":N,"part":n,"data":"..."}
state/off3_selected.json         {"id":"<template>"}
native/entryQuest.json           {"schema":"MagiaNativeEntry/v1","present":bool}
```

* `head.bytes` = 拼接文本 UTF-8 字节数；每片 `JSON.stringify({revision,part,data})` ≤ 512 KiB
* 片内 `revision`/`part` 与 head 严格一致；保存时 bank 交替、revision +1
* 未覆盖的那个 bank 原样保留（客户端用它做回滚副本），本次保存不改动它的任何字节
* zip 必须落在客户端 `inspect()` 的窄子集：无 ZIP64/加密/注释/未知 extra，路径仅 ASCII 白名单，数据区无 gap

## 目录

```
magia_save_editor/
├─ magiasave/
│  ├─ protocol.py  协议常量与路径白名单
│  ├─ zipfmt.py    严格 ZIP 读写（复刻 CNOfflineSlotArchive.inspect）
│  ├─ slot.py      head/part 分片、json-shapes-v1 编解码、preferences 校验
│  ├─ archive.py   SlotArchive：解包 / 重打包 / 无损复用
│  ├─ growth.py    游戏数值推算（移植 growth.js）
│  ├─ masters.py   卡片与结晶基础数值表
│  ├─ catalog.py   ID → 官方中文名称
│  ├─ model.py     视图 + 编辑事务 + 只读保护
│  └─ server.py    本地 Web 服务（127.0.0.1）
├─ web/            index.html / app.js / style.css
├─ tools/
│  ├─ build_catalog.py   主数据索引
│  ├─ build_masters.py   成长基础值聚合
│  ├─ fetch_assets.py    素材图复制
│  ├─ parse_compact_catalog.py  APK 的 MCATBIN1 master 解析器
│  ├─ export_advanced.py        导出精神树 / 属性强化 / 觉醒 master
│  └─ VerifyArchive.java 独立的 Java 校验器
├─ tests/          test_roundtrip.py / test_server.py / test_features.py / test_advanced.py / test_story.py / test_piece_deck.py
├─ data/           catalog.json / cards.json / pieces.json / item-groups.json
│                 item-visibility.json / quests.json / challenges.json
│                 spirit.json / attribute.json / awakening.json
│                 stories.json / costumes.json / doppels.json
└─ assets/         gifts / chara / cards / pieces / items
```

正式使用只跑 exe（`dist/MagiaSaveEditor.exe`）；源码方式仅作开发调试，两者共用同一套 `data/` / `web/` / `assets/`。

## 启动

```bash
cd H:/magia_server/magia_save_editor
python -m magiasave.server --archive "H:/magia_server/magia-save-chino-1794718180238.zip" --port 8765
# http://127.0.0.1:8765/

# 或：自动挑端口 + 自动开浏览器（与 exe 行为一致）
python launcher.py --archive "H:/magia_server/magia-save-chino-1794718180238.zip"
```

改动先落内存（可撤销 25 步），点「另存为…」才产出新 zip；原存档绝不覆盖。

## 打包成单文件 exe

```bash
cd H:/magia_server/magia_save_editor
python build_exe.py
# 产物：dist/MagiaSaveEditor.exe
```

PyInstaller onefile：data / web / assets 全部打进 exe，双击即跑：

| 环节 | 行为 |
|---|---|
| 启动 | 自动挑空闲端口（`--port 0`）并打开默认浏览器 |
| 选存档 | 页面里点「浏览…」弹原生文件对话框（服务端 tkinter） |
| 另存为 | 同样走原生「另存为」对话框，取消则退回手填路径 |
| 写盘 | 永远写你选的路径，不写临时解包目录 |
| 退出 | 关掉控制台窗口 |

源码运行与 exe 共用同一套路径解析（`magiasave/paths.py`）：打包后读 `sys._MEIPASS`，可写目录始终取 exe 所在目录。

**阵型与支援位**：每个编成的 `formationSheetId` 可换（只能选已获取的，即 `userFormationSheetList` 里的），顺带把 4 名成员与支援位按新阵型的格子重排（`questPositionId1..4` + `questPositionHelper`）。支援位可单独换到阵型里的空格，占用中的格子会拒绝（`deck_position_taken`）。

「阵型管理」弹窗列出全部 20 个阵型（中文名 + 格子 + 说明 + 哪些队伍在用），可获取 / 取消获取；正在被队伍使用的阵型不能取消（`formation_in_use`）。

```
formation.add / formation.remove   { formationSheetId }
deck.formation                     { deckType, formationSheetId }
deck.helper                        { deckType, position(1-9) }
```

阵型数据来自 MCATBIN1 `tables.formationSheet`（每个格子的 placeSkill）+ `libs/formationSheetList.json`（26 条中文名），由 `tools/export_formations.py` 生成 `data/formations.json`（20 个阵型）。

## 页面路径（浏览器前进 / 后退）

所有跳转都写进 URL 的 hash，浏览器退回就能回上一页：

| 页面 | 地址 |
|---|---|
| 概览 | `#/overview` |
| 角色一览 | `#/charas` |
| 角色详情 | `#/charas/<userCardId>` |
| 角色子面板 | `#/charas/<userCardId>/spirit`（story / costume / awake / attribute …） |
| 结晶列表 | `#/pieces` |
| 结晶详情 | `#/pieces/<pieceInstanceId>` |
| 队伍 | `#/decks` |

点队伍里的角色 / 结晶也是走同一套，所以「队伍 → 角色 → 精神强化」三层都可以逐级后退。

## 编辑操作

```
money.set / item.set / item.add / item.delete / gift.set
status.set                     AP/BP/CP/RP 及各自上限
user.set                       玩家非身份字段
card.set                       level / experience / magiaLevel / displayCardId / enabled（数值只读）
card.setAllLevels
chara.set                      lbItemNum / bondsTotalPt / live2dId
piece.set                      level / lbCount / experience / protect / archive（数值只读）
piece.setAllLevels / piece.add / piece.delete   # 可重复添加同一 pieceId（多枚独立行）
quest.set / quest.bulk / quest.mission   任务通关状态与 3 个任务标记（逐条）
quest.ensure / section.ensure            为数据包里未收录的剧情补出合法行
section.set / section.bulk              小节可玩 / 已通（逐条 + 批量）
chapter.set / chapter.bulk              章节已通（逐条 + 批量）
challenge.set / challenge.clear          挑战达成次数（逐条 + 批量）
spirit.open / spirit.close               精神树节点开关（自动补前置链 / all=true 清空）
attribute.open / attribute.close         属性强化格开关（all=true 开当前突破可用格）
awake.limit / awake.set                 界限突破 +1..3 / 直接设 revision（含降级）
awake.slot                              觉醒槽位单格或全部填充 customized1..6
story.set                               整段剧情通关 / 回退（连带段内任务）
costume.add / costume.remove / costume.equip   衣装获取状态与当前穿着
doppel.set                              魔女化身解锁 / 取消解锁（写 userDoppelList）
gacha.set / capacity.set
raw.set / raw.delete           任意路径，但类型必须与原值一致
```

路径语法：`state.gameUser.riche`、`state.userItemList[itemId=YELL].quantity`、
`state.userQuestBattleList[questBattleId=10110151].cleared`。

身份字段（`state.user.id` 等）默认拒绝；白名单外的字段一律不允许变化。

## 验证

```bash
python tests/test_roundtrip.py   # 容器/分片/编码不变量
python tests/test_server.py      # Web API 端到端 + 落盘
python tests/test_features.py    # 六条需求回归
python tests/test_advanced.py    # 精神树 / 属性强化 / 觉醒
python tests/test_story.py       # 剧情 / 衣装
python tests/test_piece_deck.py  # 结晶筛选 / 详情 / 队伍
node --check web/app.js
java tools/VerifyArchive.java _work/untouched.zip    # 未改动存档：11 条目、逐字节复用
java tools/VerifyArchive.java _work/server-out.zip   # 编辑后存档
```

## 已知边界

* 角色、卡片、结晶只改已有行或按官方基础值新增结晶；新增角色/卡片（涉及卡链与队伍约束）未实现。
* 升星（evolve）不直接换卡：编辑器负责把 6 个槽位与等级备好，换卡走「星级切换」面板（card.swap）。
* 礼物盒领取、商店流水、结算回执等流程状态未建模，需要时走 `raw.set`。
* 道具图标官方仅提供 213/1329，其余显示占位；卡片/结晶/角色图标覆盖率见上表。
* 分片落点比客户端略保守（同构线性收缩的过冲差异，均在 512 KiB 内，读取端不要求片内贪心）。
* Web 服务仅绑定 127.0.0.1，无鉴权——本机工具，不要暴露到局域网。
