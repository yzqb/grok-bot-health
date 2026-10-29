# Grok Bot Health Kit

- GUIDE.md：完整搭建指南，写给负责搭建的 bot 看。
- PROMPT.md：本人发给自己新建的 Grok Bot 的第一条消息。
- kit/：脚本。
  - `gh.py`：Google Health API v4 客户端，命令有 auth、identity、daily、sedentary、hourly。
  - `watch.py`：本地久坐检查守护进程，用法有 once、test。
  - `start_watch.sh`：启动守护进程。
  - `restore.sh`：盒子重置后的恢复脚本。
  - `install.sh`：安装脚本。
  - `set_webhook.py`：保存 webhook 地址和密钥。
  - `config.example.json`：配置示例。
  - `requirements.txt`：Python 依赖。
  - `pages/`：GitHub Pages 用的首页、隐私政策、使用条款模板。

工具包里不含任何人的凭证、密钥或健康数据。
