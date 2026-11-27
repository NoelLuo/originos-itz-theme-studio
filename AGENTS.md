# AGENTS.md

本仓库为 **OriginOS .itz Theme Studio**——面向 vivo / iQOO（OriginOS 6 / 7，Android 17）的 `.itz` 主题可视化制作、真机模拟预览与一键打包工作台。

## 1. 技术栈与仓库结构

- **运行环境**：Python 3.10+，仅依赖 `Pillow>=10.0.0`（见 `requirements.txt`）；Web 服务端基于 Python 标准库 `http.server`，前端为原生单页 `static/index.html`，保持零第三方 Web 框架依赖。
- **公开跟踪文件**：
  - `server.py`：本地 Web GUI 服务端（默认 `http://127.0.0.1:18765/`）与 ADB 联动接口。
  - `itz_engine.py`：`.itz` 读写解析、OriginOS 7 资源生成（源 `.9.png`、开关、音量配色、SuperCard 混淆名写入、锁屏组件）与自动化替换包合并核心。
  - `apk_icon_extractor.py`：通过 ADB 批量提取手机已安装应用的原版图标与索引清单。
  - `supercard_obf_map.json`：OriginOS 7 `SuperCard.apk` 的 AAPT2 混淆名与原始尺寸映射表（49 组 / 141 枚资源）。
  - `static/index.html`：可视化工作台与真机模拟预览前端。
  - `start.bat`：Windows 启动入口。
  - `.agents/skills/`：按模块拆分的主题制作与打包技能。
- **本地私有资产（`.gitignore` 排除，严禁提交到 Git）**：
  - 各类 `.itz` 主题包与历史导出包、`.apk`、`.zip`、预览图（`*_preview.png`）、本地美术素材目录、个人批处理构建脚本（如 `build_atsuko_*.py` 等）以及本地维护交接笔记。
  - 若工作区存在用户私有的**原始基础替换底包**，必须视为**只读模板**，禁止原地修改或覆盖。

## 2. 常用命令与验证

```bash
# 安装唯一第三方依赖
pip install -r requirements.txt

# 启动本地 Web 工作台（默认监听 127.0.0.1:18765）
python server.py

# Python 语法检查（修改核心脚本后建议运行）
python -m py_compile server.py itz_engine.py apk_icon_extractor.py

# 校验源主题包（仅使用 Python 标准库）
python .agents/skills/originos-itz-theme/scripts/verify_itz.py path/to/theme.itz

# 校验合并后的直用替换包
python .agents/skills/originos-itz-theme/scripts/verify_itz.py path/to/replacement_pack.itz --replacement-pack
```

- 改动导出/打包逻辑时，需执行最小往返校验或运行 `verify_itz.py` 核对关键不变量。
- 改动服务端资源预览接口（如 `/api/asset`）时，需验证普通 PNG、WebP 与以 `.png` 命名保存的动图 WebP（`RIFF....WEBP`）均可正确识别并返回对应 MIME 类型。

## 3. OriginOS 7 实机硬性红线

以下规则基于 OriginOS 7 实机逆向与测试总结，涉及主题生成、引擎改动或资源替换时必须遵守：

1. **绝不使用二进制 `npTc` 点九图**：所有 `.9.png`（卸载弹窗 `vigour_dialog_full_light.9.png`、短信卡片 `sms_card_view_bg.9.png`、开关滑块 `vigour_bool_btn_hand_normal_light.9.png`、聊天气泡等）必须采用 **1px 透明外框 + 1px 纯黑 `#000000` 拉伸/内容线** 的源 `.9.png`（32-bit RGBA PNG，`binary_npTc_count == 0`），否则会导致 OriginOS 7 全局主题应用失败。
2. **主主题包默认不包含 `fonts/`**：除非用户明确要求内嵌字体，否则不要在主 `.itz` 中打入字体文件；字体应通过 `ThemeProject.export_font_itz()` 单独导出。
3. **超级卡包 (`com.vivo.card`) 必须同步写混淆名**：`SuperCard.apk` 不走常规明文优化映射，替换卡面必须通过 `write_supercard_assets()` 或读取 `supercard_obf_map.json`，同时写入明文名与 141 枚 AAPT2 混淆名资源。
4. **音量面板展开态 4 条进度条配色**：仅改进度色会回退默认蓝色，必须通过 `ThemeProject.set_systemui_colors()` 同步写入 `<bool name="new_style">true</bool>`、`<bool name="is_color_style">true</bool>`、`vigour_color_track_gradient_startcolor` 及 `vivo_volume_seekbar_bg_color_for_expand_dialog_row_*_new`。
5. **控制中心与音量图标防染白规则**：系统会对静态单色 PNG 执行 `SRC_IN` 染白，因此静态单色图标必须透明底并使用清晰负空间镂空；若为控制中心开启态提供全彩动图 WebP（`RIFF....WEBP` 且含 `ANIM` 块，以 `.png` 路径写入），需在真机套用后目视确认渲染效果。
6. **替换包合并与真机推送**：通过 `build_replacement_pack()` 或 Studio 导出/直推生成替换包，不得手改只读底包；测试包使用明确版本号命名，未获指令不删除设备内既有主题包。

## 4. 专题 Skill 与参考文档索引

开展具体模块任务前，优先查阅对应技能与参考文档：

| 任务范围 | 技能路径 |
| --- | --- |
| `.itz` 整包组装、SuperCard、替换包与跨模块排查 | `.agents/skills/originos-itz-theme/SKILL.md` |
| 资源尺寸规范 & OriginOS 7 架构记录 | `.agents/skills/originos-itz-theme/references/asset-specs.md`<br>`.agents/skills/originos-itz-theme/references/originos7-architecture.md` |
| 桌面应用图标设计、包名映射与批量预览 | `.agents/skills/originos-launcher-icons/SKILL.md` |
| 短信卡片、按压态与卸载底部弹窗点九图 | `.agents/skills/originos-theme-nine-patch/SKILL.md` |
| 设置页与超级卡包 `VMoveBoolButton` 头像开关 | `.agents/skills/originos-settings-switches/SKILL.md` |
| 控制中心 Wi-Fi / 数据 / 蓝牙与音量面板图标 | `.agents/skills/originos-system-ui-icons/SKILL.md` |

## 5. 协作与发布守则

- **区分验证状态**：汇报主题打包或真机任务时，明确区分「脚本校验通过」「已推送至设备」与「已真机套用并目视验收」，不将未实测项写成已生效。
- **不扩大依赖面**：优先使用 Python 标准库与现有 `Pillow` 能力，不随意引入新第三方包或构建工具链。
- **保持开源仓库干净**：提交前检查 `git status` 与 `git diff`，严禁将 `.itz`、`.apk`、`.zip`、受版权保护的美术/字体素材、私人构建脚本或个人设备序列号等隐私信息写入受跟踪文件。
