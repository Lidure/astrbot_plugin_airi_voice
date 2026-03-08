<div align="center">

# Airi Voice 🌸

**输入关键词 → Airi 立刻回你一段可爱语音！**

一个超级简单的语音包插件，让你的聊天瞬间变有趣～

[![AstrBot](https://img.shields.io/badge/AstrBot-%E6%94%AF%E6%8C%81-brightgreen)](https://github.com/Soulter/AstrBot)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

</div>

## ✨ 功能亮点

- 直接输入文件名（去掉后缀） → 机器人立刻发送对应语音
- 支持 mp3 / wav / ogg / silk / amr 等常见格式
- 自动扫描 `voices/` 文件夹
- 支持 `/voice_list` 查看所有可用关键词

示例：

你：打卡啦摩托  
Airi：（发送 打卡啦摩托.mp3 的语音）

你：/voice_list  
Airi：列出所有可以触发的关键词列表～

## 📦 安装方式

1. 复制该github地址链接手动添加

   
## 🎤 如何添加新语音

1. 把你的语音文件（.mp3 / .wav 等）直接丢进插件目录下的 `voices/` 文件夹

   示例结构：
  astrbot_plugin_airi_voice/
  ├── main.py
  ├── README.md
  └── voices/
    ├── 打卡啦摩托.mp3
    ├── 啊这.wav
    ├── 寄！.ogg
    └── 早安空气.mp3
## 📋 可用命令

| 命令              | 说明                          |
|-------------------|-------------------------------|
| 直接输入关键词     | 发送对应语音（如：打卡啦摩托） |
| `/voice_list`     | 查看所有可用关键词列表         |

## ❤️ 鸣谢 & 联系

- 感谢 [AstrBot](https://github.com/Soulter/AstrBot) 提供这么好用的插件框架
- 有 bug / 想加功能 / 想分享你的语音包？欢迎 issue 或 PR ～
<div align="center">

Made with 💕 by lidure  
最后更新：2026.03

</div>
