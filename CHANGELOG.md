# 版本记录

每次云构建产出的 APK 都放在 `dist/`，文件名带版本号，方便回退。

| 版本 | APK | 做了什么 |
|---|---|---|
| **v1.5** | `Pic2Speech-v1.5-player-debug.apk` | **内置播放器**：暂停/继续、拖动进度条定位、倍速 0.5x~2.0x、前后跳 5 秒、一键交给系统默认播放器；倍速会被记住，重开 App 仍可播放上次音频。`versionCode=5 / versionName=1.5` |
| v1.4 | `Pic2Speech-v1.4-i18n-debug.apk` | 修「非拉丁文字偶发失败」：翻译改为最多 3 次重试 + 强指令；37 语言实测通过 |
| v1.3 | （已删） | 修两类**静默失败**：音色与文字系统不匹配时产出空音频/乱念；视觉模型不服从"翻译"指令 → 改成「视觉只 OCR + 文本模型翻译」 |
| v1.2 | （已删） | 修法语"翻译朗读失败" |
| v1.1 | （已删） | 内置智谱 API Key（构建时从仓库 Secret 注入），装完即用 |
| v1.0 | （已删） | 首个可安装版本（Chaquopy + edge-tts + GLM-4V） |

## v1.5 改动清单

| 文件 | 改动 |
|---|---|
| `MainActivity.kt` | 新增播放器面板逻辑：`MediaPlayer` + 主线程节拍器刷新进度、`setPlaybackParams` 变速（`pitch=1.0` 变速不变调）、暂停用**自己维护的 `paused` 标志位**判定（不靠 `isPlaying()` 现算，避免个别机型上"点播放被自己按成暂停"）、解码失败兜底 |
| `res/layout/activity_main.xml` | 新增播放器面板（`playerBox`）：时间文字 + 进度条 + 跳转/系统播放器按钮 + 倍速条 |
| `res/drawable/bg_player.xml` | 面板卡片底（新增） |
| `res/values/strings.xml` | 新增 7 条文案 |
| `app/build.gradle.kts` | `versionCode 1→5`、`versionName 1.0→1.5` |

## 回退方法

把 `dist/` 里旧版本的 APK 直接装回手机即可（`versionCode` 更小的包需要先卸载新版）。
