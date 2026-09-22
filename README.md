# 图片转语音 · 安卓版（Chaquopy + 云构建）

上传 1~8 张图片 → 智谱 GLM-4V 理解画面与文字 → edge-tts 合成 MP3（含 SRT 字幕），
**142 种语言语言 / 322 个音色**任选，支持"任意语言图片 → 任意语言语音"。

本工程的最大特点是：**本机不需要安装 JDK、Android SDK、Android Studio**，
代码推到 GitHub 后由云端编译，你只下载编译好的 APK。

---

## 一、三步拿到 APK

### 第 1 步：把工程推到 GitHub

在 GitHub 上新建一个仓库（公开或私有都行），然后在本机执行：

```bash
cd "D:\workbuddy-space\办公\图片转语音工具-Android"
git init
git add .
git commit -m "图片转语音安卓版"
git branch -M main
git remote add origin https://github.com/你的用户名/Pic2Speech.git
git push -u origin main
```

> 本工程**故意不含 gradle wrapper 文件**（生成它需要本机装 Gradle）。
> 云端用 `gradle/actions/setup-gradle` 提供 Gradle，正好符合"本机零工具链"的初衷。

### 第 2 步：等云端编译

推送后打开仓库的 **Actions** 页，会看到一个名为 **Build APK** 的任务在跑。
首次约 **8~15 分钟**（要下载 Python 运行时和安卓版依赖 wheel），之后就快很多。

### 第 3 步：下载并安装

任务变绿后，点进该次运行，在页面底部 **Artifacts** 区域下载
`pic2speech-debug-apk` → 解压得到 `app-debug.apk` → 传到手机点击安装
（需在系统设置里允许"安装未知来源应用"）。

想重新编译：Actions 页右上角 **Run workflow** 手动触发即可。

---

## 二、首次使用

1. **先填你自己的智谱 API Key**：打开 App 顶部会有一条黄色提示条，
   往下滚到「智谱 API Key」，粘贴后点"保存"（只需一次）
   - 免费申请：https://open.bigmodel.cn （模型 `glm-4v-flash` 免费不限量）
   - 智谱的 Key 是**无前缀的 40~50 位字符串**，不是 `sk-` 开头
   - **本 App 不内置任何 Key**：所以这个 APK 给谁装都可以，你的额度不会被别人用掉
   - Key 只存在手机本机的 App 私有存储里，调用时由手机**直连智谱**，不经过任何中间服务器
2. 点 **① 选择图片**（可多选，最多 8 张）
3. 选 **目标语言** 与 **音色**
4. 点 **③ 生成音频**（约 5~60 秒）
5. 完成后下方会弹出**播放器面板**：可**暂停/继续**、**拖动进度条**定位、**调倍速**（0.5x~2.0x）、**前后跳 5 秒**，
   也可以点「系统播放器」把 MP3 交给手机自带的播放器（可后台播放）
6. 可直接编辑识别出的文字稿后点 **仅重新合成**；点 **分享** 可把 MP3 发给微信/QQ 等

> 播放器说明：进度条按真实时长显示 `已播 / 总长`（如 `00:12 / 01:30`），倍速用 `pitch=1.0` 变速不变调，
> 调好的倍速会被记住；关闭 App 再打开，上一次生成的音频仍可直接播放。

| 模式 | 作用 |
|---|---|
| 看图解说 | 理解画面 + 图中文字，用目标语言写解说词（默认） |
| 朗读图中文字 | 原样读出图中文字，音色自动匹配原文语言 |
| 翻译朗读 | 把图中文字翻译成目标语言再朗读 |

---

## 三、常见问题

| 现象 | 原因与处理 |
|---|---|
| **API Key 无效（HTTP 401）** | Key 复制不全或已过期，去智谱后台重新生成 |
| **语音服务拒绝请求（403）** | **最常见**：手机系统时间不准导致 edge-tts 令牌校验失败。到「设置 → 日期和时间」开启**自动设置时间**后重试 |
| 无法连接语音服务 | 手机网络问题；部分公司/校园网会封 `speech.platform.bing.com` |
| 提示"图片读取失败" | 重新选择图片；个别云盘返回的图片流无法解码，先存到本地相册 |
| 生成内容偏短 | 免费模型输出上限 1024 token（约 800 字），一次少传几张图；或改用 `glm-4v-plus`（需账户额度） |
| 构建失败 | 看 Actions 日志。最常见是 SDK 许可证或网络下载超时，重新 Run workflow 一般即可 |

**APK 偏大（约 40~60 MB）属正常**：内置了 Python 解释器和两个架构的原生库。
只想给自己手机用的话，可以在 `app/build.gradle.kts` 里把 `abiFilters` 的
`"x86_64"` 去掉（那是模拟器用的），能再小一截。

---

## 四、目录结构

```
图片转语音工具-Android/
├── .github/workflows/build-apk.yml     ★ 云构建配置
├── settings.gradle.kts / build.gradle.kts / gradle.properties
├── app/
│   ├── build.gradle.kts                ★ Chaquopy + pip 配置
│   └── src/main/
│       ├── AndroidManifest.xml
│       ├── python/pic2speech/
│       │   ├── api.py                  Kotlin 调用入口（统一返回 JSON）
│       │   ├── vision.py               图片理解（urllib 直连智谱）
│       │   ├── tts.py                  语音合成（edge-tts → MP3 + SRT）
│       │   └── voices.json             142 语言 / 322 音色（离线）
│       ├── java/com/pic2speech/app/
│       │   ├── MainActivity.kt         界面与交互（含内置播放器：进度/倍速/暂停）
│       │   ├── PyBridge.kt             Kotlin ↔ Python 桥接
│       │   └── ImageUtil.kt            图片压缩（最长边 1568）
│       └── res/                        布局、主题、图标
└── tools/                              辅助脚本（电脑上运行）
    ├── gen_voices.py                   联网刷新音色表
    ├── make_icons.py                   生成启动图标
    ├── smoke_test.py                   Python 侧冒烟测试
    ├── check_resources.py              资源引用一致性校验
    └── verify_no_key.py                ★ 安全闸门：确认 APK 内不含 API Key
```

---

## 四之二、为什么这个包里没有你的 Key（安全设计）

APK **本质是 zip**，Chaquopy 的 `assets/chaquopy/app.imy` 也是 zip，
两层双击即可进入。早先版本把 Key 注入成 `pic2speech/_secret.py`，
那是个**明文 Python 源码文件** —— 也就是说，任何拿到 APK 的人，
在电脑上这样操作就能看到它（不需要安卓手机，也不需要反编译工具）：

```bash
unzip Pic2Speech.apk assets/chaquopy/app.imy
unzip assets/chaquopy/app.imy pic2speech/_secret.py
cat pic2speech/_secret.py          # ← Key 就在眼前
```

**只要 Key 进了包，就等于公开。** 混淆、加密、藏进 native 库都只是提高门槛：
解密的逻辑必须也在客户端里，最终总要在运行时还原成明文。

所以本工程从 **v1.6** 起改为**不内置任何 Key**：

| 环节 | 做法 |
|---|---|
| 构建 | CI **不再注入** Key，改为校验源码树里不存在 `_secret.py` |
| 产物 | 构建后用 `tools/verify_no_key.py` 拆包扫描，**只要翻出 Key 形态的字符串就让这次构建失败** |
| 运行 | Key 由用户自己粘贴，保存在手机本机（App 私有存储），直连智谱 |
| 善后 | 曾经内置过 Key 的旧包请弃用；那把 Key 应去智谱后台**吊销并重建** |

> 顺带一个好处：现在这个 APK 可以放心地发给任何人 —— 你的额度不会被别人用掉。

---

## 五、技术要点（为什么这么设计）

| 决策 | 原因 |
|---|---|
| **不用 `openai` SDK**，改用标准库 `urllib` | SDK 依赖 `pydantic-core`（Rust 编写），安卓上几乎装不上；REST 调用本身很简单 |
| **图片压缩放 Kotlin**，Python 不用 Pillow | 少一个 C 扩展依赖，整条依赖链只剩 `edge-tts` 一族 |
| **edge-tts 保留** | 其原生依赖在 Chaquopy 仓库里都有 cp313 安卓预编译包：`aiohttp 3.10.10` + `multidict 6.1.0` + `frozenlist 1.4.1` + `yarl 1.16.0`，无需自己交叉编译 |
| Python 版本必须选 **3.13**（不是 3.10） | 实测 Chaquopy 仓库：**cp310 下 `yarl` 最高只有 1.4.2，不满足 `aiohttp 3.10.10` 要求的 `yarl>=1.12`，依赖解析会失败**；cp313 下四个包齐全且互相满足。这组轮子编译目标是 `android_24`，与本工程 `minSdk = 24` 正好对应。顺带满足 Google Play 的 16 KB 页对齐要求 |
| `max_tokens = 1024` | GLM-4V-Flash 的硬上限，超过会报 400/1210 |
| 界面只用**系统原生控件**（除 FileProvider） | 不引入 UI 框架，减少编译期风险，APK 更小 |
| 跨语言全部走**字符串 / JSON** | 避开二进制数组跨 JNI 传递的兼容问题，出错只返回中文消息，不崩溃 |
| **不内置 API Key**，改由用户自己在界面填写 | APK 与 `.imy` 都是 zip，内置的凭据零门槛可提取（详见"四之二"）；不内置后，这个包给谁装都不会消耗你的额度 |

---

## 六、可选：本地构建（需要 Android Studio）

如果你以后装了 Android Studio，也可以直接打开本工程构建：
Android Studio 会提示补全 gradle wrapper，同意即可；随后 `Build → Build APK(s)`。
需要 JDK 17 与 Android SDK 34，Chaquopy 插件会自动处理 Python 运行时。
