<div align="center">

# 🌸 Airi Voice

> **输入关键词 → Airi 立刻回你一段可爱语音！**  
> 让聊天瞬间充满灵魂与温度的轻量级语音插件。

[![AstrBot](https://img.shields.io/badge/AstrBot-Plugin-brightgreen?style=for-the-badge&logo=github)](https://github.com/Soulter/AstrBot)
[![Python](https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![Version](https://img.shields.io/badge/Version-2.3-orange?style=for-the-badge)]()

</div>

---

## ✨ 核心亮点

| 特性 | 描述 |
| :--- | :--- |
| 🚀 **零门槛触发** | 直接输入文件名（去后缀）即可触发，无需复杂指令 |
| 🎵 **全格式支持** | 完美支持 `.mp3`, `.wav`, `.ogg`, `.silk`, `.amr` 等主流格式 |
| ⚡ **热加载机制** | 网页上传新语音后自动识别，无需重启机器人 |
| 🛡️ **智能防刷屏** | 内置分页列表命令，再多语音也不怕消息爆炸 |
| 🔐 **权限精细控制** | 支持白名单/管理员模式，防止语音功能被滥用 |
| 🎛️ **多触发模式** | 灵活切换「直接模式」「前缀模式」「LLM 模式」，适应不同场景 |
| 🤖 **LLM 智能联动** | 在 LLM 模式下，由大模型自动选择并发送最合适的语音 |
| 🆕 **引用添加语音** | 聊天中引用语音消息，一条命令即可添加新语音 |

---

## 🎮 使用指南

### 1. 触发语音
配置好语音文件后，只需在聊天框输入对应的**关键词**即可。

> **示例场景：**
> *   你输入：`打卡啦摩托`
> *   Airi 回复：*(发送 `打卡啦摩托.mp3` 的语音)*
>
> *   你输入：`汪大吼`
> *   Airi 回复：*(发送 `汪大吼.wav` 的语音)*

### 2. 查看列表
输入 `/voice.list` 查看所有可用的语音关键词。
*   支持分页查看：`/voice.list 2`
*   自动统计总数与页码，清晰易读。

### 3. 触发模式切换
在插件配置页面可调整触发逻辑，避免日常聊天误触：

| 模式 | 说明 | 适用场景 |
| :--- | :--- | :--- |
| **Direct (直接模式)** 👈 *默认* | 直接发送关键词即可触发 | 亲友群、专用频道 |
| **Prefix (前缀模式)** | 必须发送 `#voice 关键词` 才触发 | 大群、公共频道，防止误触 |
| **LLM 模式** | 仅在需要由大模型自动选择并发送语音时启用，会为当前会话注册 `airi_*` LLM 工具 | 与 Agent 对话、需要“智能选语音”的场景 |

> ⚠️ 未选择 LLM 模式时，插件只作为普通语音关键词插件工作，大模型不会看到 `airi_*` 工具。

### 4. bot追加语音
bot 回复的文本只要包含任意语音关键词，就会自动追加对应语音

---

## 📥 安装方式

### 方法 A：一键安装（推荐）
在 AstrBot 控制面板中：
1. 进入 **插件市场**
2. 搜索 `Airi Voice` 或 `airi_voice`
3. 点击 **安装**

### 方法 B：手动安装
1. 复制仓库地址：`https://github.com/Lidure/astrbot_plugin_airi_voice`
2. 在 AstrBot 后台选择 **手动添加插件**，粘贴链接即可。

---

## 🎤 如何添加新语音

我们提供三种优雅的方式来扩充语音库：

### 🅰️ 方式一：网页上传（推荐 ✨）
*最简单、最安全的方式，支持热更新。*

1. 进入 **AstrBot 网页后台** → **插件管理** → **Airi Voice** → **配置**
2. 找到 **「额外语音文件池」** 区域
3. 直接上传你的 `.mp3` / `.wav` 等音频文件
4. **文件名（不含后缀）** 即为触发关键词
5. 上传成功后，立即生效！

### 🅱️ 方式二：聊天中引用添加（新增 🆕）
*最快捷的方式，聊天中即可完成！*

1. 在聊天中**引用**一条语音消息（可以是别人发的，也可以是机器人发的）
2. 发送命令：`/voice.add 关键词`
3. 完成！立即可用该关键词触发语音

> **示例：**
> 1. 朋友发送了一条语音："早上好"
> 2. 你引用这条语音，发送：`/voice.add 早上好`
> 3. 以后任何人发送 `早上好`，Airi 都会回复同样的语音！

> ⚠️ **注意：** 此命令需要管理员权限

### 🅲 方式三：本地部署
*适合批量导入或服务器运维人员。*

1. 进入插件数据目录：
   ```bash
   # 路径示例 (Windows)
   data/plugin_data/astrbot_plugin_airi_voice/voices/
   
   # 路径示例 (Linux/Docker)
   ./data/plugin_data/astrbot_plugin_airi_voice/voices/
   ```
2. 将音频文件直接拖入该文件夹
3. 在后台执行 `/voice.reload` 命令（管理员权限）刷新列表

---

## 📋 命令速查表

| 命令 | 权限 | 说明 |
| :--- | :---: | :--- |
| `[关键词]` | 全员 | 直接输入关键词发送对应语音 |
| `/随即语音` | 全员 | 随机发送一条语音 |
| `#voice [关键词]` | 全员 | 前缀模式下触发语音 |
| `/voice.list [页码]` | 全员 | 查看可用语音列表（支持分页） |
| `/voice.help` | 全员 | 显示帮助信息与当前模式 |
| `/voice.check` | 全员 | 检查当前用户权限状态 |
| `/voice.add 名字` | 🔒 管理员 | **引用语音消息**添加新语音 🆕 |
| `/voice.delete 名字` | 🔒 管理员 | 删除通过 voice.add 添加的语音 🆕 |
| `/voice.reload` | 🔒 管理员 | 强制重新扫描并加载语音列表 |

---

## 🔐 权限说明

| 权限模式 | 说明 | 配置方式 |
| :--- | :--- | :--- |
| `all` | 所有人可使用管理命令 | 插件配置中设置 `admin_mode: all` |
| `admin` | 仅平台管理员可用 | 插件配置中设置 `admin_mode: admin` |
| `whitelist` 👈 *默认* | 仅白名单用户可用 | 在 `admin_whitelist` 中添加用户 ID 或昵称 |

> 💡 使用 `/voice.check` 可查看当前用户的权限状态

---

## 📁 文件存储说明

| 来源 | 存储位置 | 插件更新后 |
| :--- | :--- | :--- |
| 本地 `voices/` 目录 | `plugins/astrbot_plugin_airi_voice/voices/` | ⚠️ 可能被覆盖 |
| 网页上传 | `data/plugin_data/astrbot_plugin_airi_voice/extra_voices/` | ✅ 持久保存 |
| `/voice.add` 添加 | `data/plugin_data/astrbot_plugin_airi_voice/extra_voices/` | ✅ 持久保存 |

> 💡 推荐使用网页上传或 `/voice.add` 方式，确保语音文件不会因插件更新而丢失

---

<div align="center">

![](https://github.com/user-attachments/assets/a01804f7-7769-4688-9caa-4f7da2796d8d)

*配置简单，响应迅速，让互动更有趣*

</div>

---

## ❤️ 鸣谢与支持

- **框架支持**: 感谢 [AstrBot](https://github.com/Soulter/AstrBot) 提供强大且灵活的插件架构。
- **灵感来源**: 致力于让每一个机器人都拥有独特的声音。

### 🐛 问题反馈
遇到 Bug？有新点子？或者想分享你制作的语音包？
欢迎提交 [Issue](https://github.com/Lidure/astrbot_plugin_airi_voice/issues) 或 [Pull Request](https://github.com/Lidure/astrbot_plugin_airi_voice/pulls)！

---

<div align="center">

**Made with 💕 by [lidure](https://github.com/Lidure)**  
📅 最后更新：2026.03  
📜 遵循 MIT 协议开源

</div>
