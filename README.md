<div align="center">

# Airi Voice 🌸

**输入关键词 → Airi 立刻回你一段可爱语音！**

一个超级简单的语音包插件，让你的聊天瞬间变有趣～

[![AstrBot](https://img.shields.io/badge/AstrBot-%E6%94%AF%E6%8C%81-brightgreen)](https://github.com/Soulter/AstrBot)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

</div>

## 更新

voice_list更新了翻页，防止过多记录导致的刷屏

新增配置项，可以在配置中修改音频


## ✨ 功能亮点

- **零门槛触发**：直接输入文件名（去掉后缀）就能让 Airi 回你语音  
- **格式全家桶**：支持 .mp3 / .wav / .ogg / .silk / .amr 等常见音频格式  
- **自动扫描**：插件启动/重载时自动扫描 `voices/` 文件夹  
- **网页上传支持**：在 AstrBot 插件配置页面直接上传新语音，文件名即关键词  
- **防刷屏列表**：`/voice_list` 支持翻页显示，再多关键词也不怕炸屏  
- **刷新即生效**：上传新语音后发 `/voice_reload` 立即可用，无需重启 bot

示例：

你：打卡啦摩托  
Airi：（发送 打卡啦摩托.mp3 的语音）

你：/voice_list  
Airi：列出所有可以触发的关键词列表～

目前，voices中有：打卡啦摩托、汪大吼、airi自我介绍、生辰快乐、MMJ!（歌曲）
## 📦 安装方式

1. 复制该github地址链接手动添加

   
## 🎤 如何添加新语音

方式1：本地添加（不推荐）

打开插件目录下的 voices/ 文件夹
（路径示例：data/plugins/astrbot_plugin_airi_voice/voices/）
把你的语音文件直接拖进去

方式2：网页上传（优雅推荐）

进入 AstrBot 网页后台 → 插件管理 → Airi Voice → 配置
在「额外语音文件池」区域上传你的 .mp3 / .wav 等文件
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
