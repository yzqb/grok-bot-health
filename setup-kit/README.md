# Grok Bot Health Kit

- GUIDE.md：完整搭建指南，写给负责搭建的 bot 看。
- kit/：脚本。
  - `gh.py`：Google Health API v4 客户端，命令有 auth、identity、daily、sedentary、hourly。
  - `restore.sh`：恢复脚本，盒子重置后重建 venv、恢复凭证；每次唤醒先运行一次。不启动任何后台进程。
  - `install.sh`：安装脚本。
  - `config.example.json`：配置示例。
  - `requirements.txt`：Python 依赖。
  - `pages/`：GitHub Pages 用的首页、隐私政策、使用条款模板。

定时检查（比如久坐提醒）用 bot 自己的 routine 来做，不用后台脚本：盒子闲下来会被平台暂停，后台脚本会跟着停住。

工具包里不含任何人的凭证、密钥或健康数据。
