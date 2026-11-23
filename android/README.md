# 安卓版（Android port）

这是 [MagiaSaveEditor](https://github.com/qwerty-a11y/MagiaSaveEditor) 的 **Android 适配分支**，
上游的存档解析 / 推算 / 编辑逻辑一行未改，只补了「在手机上跑起来」缺的那层壳。

桌面用法完全不变（`python -m magiasave.server` / `launcher.py` / `build_exe.py` 都照旧），
本目录下的内容只对 Android 有用。

---

## 这个构建的定位

**个人使用、朋友之间分享，不发布到任何商店。**

按这个前提，几处取舍是刻意为之，不是遗漏：

| 项 | 决定 | 理由 |
|---|---|---|
| ABI | **只打 `arm64-v8a`** | 2016 年后的手机基本都是 64 位；少打一套 Python 运行时能省 12 MB，也让 APK 更小更好传。遇到 32 位老机再加一行 `abiFilters` 重编即可 |
| 撤销栈 | **保持 25 步，不动** | 上游 `undo_limit = 25` 每步 `copy.deepcopy(profile)`。个人存档一般不大，实测够用；先不为了省内存牺牲撤销深度，真遇到卡顿了再调 |
| 签名 | **debug 签名** | 走 `signingConfigs.debug`，方便直接 `adb install`。个人分享不需要正式 keystore |
| Chaquo 授权 | **免费版够用** | 免费版限非商业用途，个人使用完全落在许可内 |
| 分发方式 | **直接发 APK** | 不发商店就不需要处理 targetSdk 审核、隐私清单这些 |

如果哪天要公开发布，需要重新决定的就这几条：ABI 是否补 32 位、签名换正式 keystore、
Chaquo 是否要商业授权、以及 `undo_limit` 要不要按低端机调。

---

## 为什么能这么轻松搬过来

上游本来就是「**纯标准库 Python 本地 HTTP 服务 + 浏览器 UI**」的结构：

| 部分 | 技术栈 | 安卓上的处理 |
|---|---|---|
| `magiasave/`（14 个 .py，含 4500 行 `model.py`） | `os/json/re/hashlib/zipfile/http.server/threading`，零第三方依赖 | 原样塞进 Chaquo，零改动 |
| `web/`（原生 JS + CSS，无框架） | `fetch` 调本地接口 | 原样塞进 WebView |
| `data/` + `assets/`（约 45 MB） | 静态 JSON / PNG | 首启解包到私有目录 |
| `dialogs.py`（tkinter） | **唯一不通用件** | 换成 Android 系统文件选择器（SAF） |

所以下面的改动都是「接线」，没有重写业务逻辑。

---

## 改了什么

### Python 侧（4 处小改 + 3 个新文件）

| 文件 | 改动 |
|---|---|
| `magiasave/paths.py` | 支持三个环境变量：`MAGIA_BUNDLE_ROOT`（只读资源根）、`MAGIA_APP_DIR`（可写目录）、`MAGIA_ANDROID`；另有 `android()` 判断 |
| `magiasave/masters.py` | 原来把 `_DATA_DIR` 硬编码成源码目录，改成走 `paths.data_dir()`，否则安卓上读不到 `data/*.json` |
| `magiasave/dialogs.py` | 有 Android 桥就走桥，否则退回 tkinter；两者都没有时返回 `None`（前端本来就有手填路径的退路） |
| `magiasave/server.py` | 静态目录改成每个请求重新解析（`import` 时机不受环境变量影响）；`api_save` 末尾把 outbox 文件推回用户选的 Uri |
| **`magiasave/bridge.py`**（新） | 与 Kotlin 的契约层：`pick / commit_save / share / open_external`，不 import 任何 Android 类，桌面 import 也不崩 |
| **`magiasave/android_api.py`**（新） | 挂在 Handler 上的 5 个新接口（见下表） |
| **`magiasave/android_main.py`**（新） | `start_in_thread()`：建服务、起线程、返回端口，给 Chaquo 调用 |

新增 HTTP 接口：

| 接口 | 作用 |
|---|---|
| `GET /api/android` | 告诉前端「是不是安卓 / 有没有桥 / 工作区在哪」 |
| `GET /api/workspace` | 列出工作区里已导入的存档 zip |
| `POST /api/import` | 把系统选择器给的路径拷进工作区（同名自动加序号，绝不覆盖） |
| `POST /api/share` | 转发给 Android 分享面板 |
| `POST /api/open-external` | 用系统默认应用打开 |

### 前端（3 处增量，保持原作者 ES5 风格）

- `index.html`：加一个 `<button id="btnImport">`（默认 `.hidden`）
- `web/app.js`：加 `setupAndroid() / importArchive() / pickFromWorkspace() / offerShare()`，
  并在 `saveAs` 成功后问一句「要分享出去吗」
- `web/style.css`：`.hidden` 与窄屏下的顶栏换行规则

桌面上 `/api/android` 返回 `android: false`，按钮保持隐藏，**行为与上游完全一致**。

### 安卓工程（`android/`，全新）

```
android/
├── settings.gradle / build.gradle / gradle.properties
└── app/
    ├── build.gradle                  ← 关键：stageBundle 把仓库根的 web/data/assets 同步进 APK
    └── src/main/
        ├── AndroidManifest.xml
        ├── java/io/github/magiasaveeditor/android/
        │   ├── MainActivity.kt        进度条 → 解包 → 起 Python → WebView
        │   ├── BundleInstaller.kt     assets/bundle/* → filesDir/bundle（带版本号缓存）
        │   ├── PythonRuntime.kt       Chaquo 启动 + 注入环境变量与桥
        │   ├── AndroidBridge.kt       Python 反射调用的入口
        │   └── SafeFiles.kt           content:// ↔ 真实文件互转
        └── res/                       主题、矢量图标、FileProvider 路径
```

**为什么不复制一份 Python 源码**：`app/build.gradle` 里
`chaquopy.sourceSets.main.srcDirs = [repoRoot]` + `include "magiasave/**/*.py"`，
`stageBundle` 任务把 `web/ data/ assets/` 汇总到 `build/generated/bundle/`。
**仓库根是唯一真相**，改 Python 不用同步两处。

---

## 构建

### 前置

1. **Android Studio**（Ladybug 或更新）与 **JDK 17**
2. **Chaquo Python** 插件（Gradle 会自动从 `https://chaquo.com/maven` 拉）
   - 免费版**仅限非商业用途**；本项目是 GPL-3.0，符合其条款
3. 首次构建要联网下载 Python 运行时（约 20 MB + 各 ABI 的 libpython）

### 步骤

```bash
cd android
# 如果用 Android Studio：直接 File → Open 选这个目录
# 命令行（需要先有 gradle wrapper jar，见下方说明）：
./gradlew assembleDebug
# 产物：android/app/build/outputs/apk/debug/app-debug.apk
```

> **关于 wrapper**：仓库里没有提交 `gradle-wrapper.jar`（二进制文件，体积大且常被误判）。
> 第一次要么用 Android Studio 打开让它自动生成，要么在本机装好 Gradle 8.9 后执行
> `gradle wrapper` 生成，然后就能用 `./gradlew`。

### 预期体积

| 组成 | 约 |
|---|---|
| Python 运行时（arm64-v8a） | 12–15 MB |
| `data/` + `assets/` | 45 MB（不压缩打进 APK） |
| web + Kotlin + 资源 | < 1 MB |
| **合计 APK** | **约 60–70 MB**，装好后首次启动还会在私有目录再占 45 MB |

**本构建只打 `arm64-v8a`**（个人使用分享的刻意选择）。万一朋友的机器是 32 位，
把 `app/build.gradle` 里 `abiFilters` 改成 `"arm64-v8a", "armeabi-v7a"` 重编一次，
APK 大约会大 12 MB。

---

## 用户怎么用（这一版的实际交互）

```
首次启动
  ├─ 解包 45 MB 数据（进度条，2–5 秒）
  ├─ 起 Python 服务（127.0.0.1:随机端口）
  └─ WebView 打开界面

导入存档
  点「导入存档…」→ 系统文件选择器挑 zip → 拷进 app 工作区 → 自动打开

编辑            ← 和桌面完全一样

另存为
  点「另存为…」→ 系统「保存到」对话框选位置 → 写出 → 问「要分享出去吗」
```

**全程走 SAF，因此不需要 `MANAGE_EXTERNAL_STORAGE`，也不需要 `INTERNET` 权限。**
（Python 只绑 `127.0.0.1`，WebView 走 loopback。）

### 关于存档在哪儿

游戏私服的存档一般在 `Android/data/<包名>/files/` 下面，**Android 11+ 第三方 app 读不到这个目录**。
所以流程刻意做成「**导入 → 编辑 → 导出**」：

1. 用户在文件管理器里进到 `Android/data/...`，把存档 zip 复制到「下载」或任意可见目录
2. 在编辑器里点「导入存档…」选它
3. 编辑完「另存为」到可见位置，再手动放回原位

这不是偷懒，是分区存储下的唯一稳妥路径；直接申请「所有文件访问」权限体验差、上架也麻烦。

---

## 已知限制

| 项 | 说明 |
|---|---|
| **撤销占内存** | 上游每步 `copy.deepcopy(profile)` 存 25 步撤销，低端机上可能吃 200–400 MB。**本构建按个人使用的定位保持 25 步不变**；如果实际用起来觉得卡，把 `server.py` 里 `undo_limit` 调到 8–10 即可 |
| **首次启动慢** | 45 MB 解包 + Python 初始化，冷启约 3–8 秒（视闪存速度）。第二次起是瞬时的（`version.txt` 命中） |
| **只测到 arm64** | 模拟器是 x86_64，要先在 `abiFilters` 里加 `"x86_64"` 才能在模拟器上跑 |
| **`targetSdk 34`** | 提到 35 时需要重新验证 SAF 行为 |
| **没有后台保活** | Activity 被系统杀掉后，Python 服务一并结束。重新打开会重新走一遍启动 |
| **Chaquo 免费版限制** | 非商业用途；若要商业分发需购买授权，或改用 [BeeWare / Kivy] 重做壳（工作量明显更大） |

---

## 测试

```bash
# 打包无关的 Python 侧回归（不需要真实存档样本）
python tests/test_android.py          # 桥的降级、导入、路径覆盖、Handler 挂载
python tests/test_android_launch.py   # 模拟安卓启动全链路（起真服务 + 假 Kotlin 桥 + HTTP）
```

`tests/test_android_launch.py` 是这一支最有价值的一个测试：它在桌面上把
「Kotlin 注入环境变量 → `start_in_thread` → 起 HTTP → `/api/pick` 走桥 → `/api/import` →
`/api/share` 转发」整条链跑通，出问题时先看它。

上游原有的 6 个测试仍然可用，但它们硬编码了作者的 Windows 样本路径
（`H:/magia_server/magia-save-chino-*.zip`），需要自己放一份样本才能跑。

---

## 上游同步

这个分支只在上游之上加了文件，冲突极少：

```bash
git remote add upstream https://github.com/qwerty-a11y/MagiaSaveEditor.git
git fetch upstream
git merge upstream/master      # 冲突大概率只出现在 server.py 的导入区与 api_save
```

`server.py` 的改动集中在三处，都是小片段，冲突了照注释手工合一次即可。

---

## 许可

与上游一致：**GPL-3.0**。安卓壳同样是衍生作品，分发时必须一并开源。
游戏素材与主数据的权利仍归原版权方，不在 GPL 覆盖范围内（见 `THIRD-PARTY-NOTICES.md`）。
