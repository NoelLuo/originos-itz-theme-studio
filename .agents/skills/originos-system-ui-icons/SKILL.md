---
name: originos-system-ui-icons
description: 修改 OriginOS 7 控制中心 Wi-Fi、移动数据和蓝牙的开关图标，或音量面板媒体、铃声、通知、闹钟的字形与系统配色。
---

# OriginOS 7 控制中心与音量面板

## 控制中心

- 从目标主题的 `com.vivo.systemuiplugin` 及实际使用的 `com.android.systemui` 资源确认 `vivo_super_qs_*` 路径、状态和别名。亚津子方案采用 `144×144` 透明底图，关闭态沿用原图，开启态加彩色兜帽角色。Wi-Fi 信号和蓝牙符号应可识别。已确认的移动数据开启稿省略箭头。
- 静态位图在已测系统路径上可能被 `SRC_IN` 染成单色，透明底决定其剪影。需要全彩时，本项目用真正含动画帧的 WebP 测试，并按目标查找键写入 `.png` 条目。先核对 WebP 载荷、Alpha、帧和资源别名，保留关闭态原 PNG。沿用当前主题实际映射的 Wi-Fi 强度、`run` 与移动数据 `cellular` 等变体。
- 已有设备解码测试得到 `AnimatedImageDrawable`，且在探针调用 `setTint(WHITE)` 后保留颜色。该结果只验证解码和探针染色。控制中心是否保色要实际套用测试包后，在展开和折叠面板里切换三组状态确认。

## 音量面板

- 复用 `itz_engine.py` 的 `make_volume_glyph_icon()` 和颜色写入逻辑。更新目标包实际读取的 `vivo_volume_ic_audio_*_new` 与对应深色状态，保留媒体静音辨识。媒体、铃声、通知、闹钟分别可用扬声器、铃铛、消息气泡和双铃表盘。
- 同时检查位图和 `theme_values.xml` 的 `vivo_volume_whole_theme_icon_color_light/dark`，验证最终染色及实际轨道背景。蓝色进度条用莓紫可以形成明度区分，项目样例浅色为 `#54253E`、深色为 `#9C6480`。按目标轨道颜色在浅、深两种 UI 的已填充和未填充段检查辨识度。
- 核对两个输出包里的资源和颜色配置。报告实际套用、静态预览、解码探针分别覆盖了哪一层。
