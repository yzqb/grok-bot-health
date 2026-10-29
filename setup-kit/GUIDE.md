# 健康管家搭建指南（Grok Bot Health Kit）

这份指南是写给负责搭建的 Grok Bot 看的。目标是用**本人自己的** Google 账号和 GitHub 账号，搭一个健康管家：能通过 Google Health API v4 长期、稳定地读取本人的 Fitbit 数据（`gh.py`），这是唯一的必做目标。读到数据之后用来做什么（问答、日报、提醒等）由本人决定，不要预设。第 5 步的久坐提醒只是一个可选示例：只有本人想要主动提醒时才做。

**分工**：本人只做两件事：登录账号、点同意授权。其余全部由 bot 自己完成。密码和验证码绝不能发在聊天里。

**统一命名**：下文的 `APP` 默认是 `Grok Bot Health`，Google 项目、OAuth 应用、OAuth 客户端都用这个名字；GitHub 仓库默认叫 `grok-bot-health`。本人想换名字的话，所有地方一起换。

---

## 前提（开工前先问本人确认）
1. 手环数据已经同步到 Google Health：手机上装好了 **Google Health app**，用要授权的那个 Google 账号登录，并完成了 Fitbit 账号迁移，app 里能看到今天的步数。旧的 Fitbit Web API 将在 2026-11-02 关闭，只能走 Google Health 这条路。
2. 本人已经有 Google 账号和 GitHub 账号。
3. 时区不要问本人：直接用你自己已知的本人时区（你的系统提示/Time 部分给出的 IANA 时区，如 `America/New_York`；盒子的 `date +%Z` 或 `/etc/timezone` 也可参考）。稍后写进 `config.json`。

## 第 0 步：在你自己的浏览器里让本人登录
1. **Google**：用 computerUse 浏览器打开 `https://accounts.google.com/`，然后调用 `request_box_help` 把屏幕交给本人。本人自己输入账号、密码和两步验证，并勾选“保持登录”。登录后，在同一个浏览器里打开 `https://console.cloud.google.com/`，确认已经是登录状态。如果弹出服务条款，请本人勾选同意，国家选自己所在地。**不需要绑定结算账户。**
2. **GitHub**：优先运行 `gh auth login --hostname github.com --git-protocol https --web`。把终端打印出的 8 位一次性代码发给本人，请他在任意设备上打开 `https://github.com/login/device`，输入代码并点授权。代码 15 分钟内有效，过期了就重新运行这条命令。完成后用 `gh auth status` 确认已登录。如果 `gh` 用不了，就在浏览器里打开 `https://github.com/login`，再用 `request_box_help` 请本人自己登录。
3. **登录时常见的情况**：
   - Google 提示“此浏览器或应用可能不安全”：停止自动操作，改用 `request_box_help`，请本人亲手登录。如果还是被拦，换盒子上的另一个浏览器再试（Chrome 和 Firefox 互换）。
   - 要求在手机上确认“是我本人”、输入短信验证码，或者做人机验证：都交给本人在交出去的屏幕上完成，你只需要等他做完。
   - 登录后又被要求重新验证：这是正常的，同样交给本人。

## 第 1 步：放好工具包
```bash
cd /home/box && unzip -o <kit压缩包路径> -d /home/box/health-kit-src
bash /home/box/health-kit-src/kit/install.sh      # 安装到 /home/box/health 并建好 venv；已有的凭证不会被覆盖
```
然后编辑 `/home/box/health/config.json`：`timezone` 填第 0 步确定的本人 IANA 时区（示例里是 UTC，换成本人的时区）。

## 第 2 步：GitHub Pages（OAuth 同意屏幕需要应用首页和隐私政策页）
```bash
U=$(gh api user -q .login); R=grok-bot-health; cd /home/box && rm -rf $R && mkdir $R && cd $R
cp /home/box/health/pages/*.html .
sed -i "s/{{APP_NAME}}/Grok Bot Health/g; s/{{CONTACT_EMAIL}}/<本人邮箱>/g; s/{{DATE}}/$(date +%F)/g" *.html
git init -q -b main && git add . && git -c user.name="$U" -c user.email="$U@users.noreply.github.com" commit -qm "pages"
gh repo create "$U/$R" --public --source=. --push      # 免费账号的 Pages 只能用公开仓库；仓库里只有说明页，没有任何健康数据
gh api -X POST "repos/$U/$R/pages" -f "source[branch]=main" -f "source[path]=/"
```
等 1–3 分钟，再运行 `curl -sI https://$U.github.io/$R/privacy.html`，返回 200 就说明页面已经上线。**禁止**把 token、client_secret、任何密钥或健康数据放进这个仓库。

## 第 3 步：Google Cloud（全部在你自己的浏览器里操作）
1. **建项目**：打开 `https://console.cloud.google.com/projectcreate`，项目名称填 `APP`，点“创建”。之后每一页都要先确认顶部选中的是这个项目。
2. **启用 API**：打开 `https://console.cloud.google.com/apis/library/health.googleapis.com`，点“启用”（Enable）。
3. **OAuth 同意屏幕**：打开 `https://console.cloud.google.com/auth/overview`，点“开始”（Get started）：
   - 应用名称填 `APP`，用户支持邮箱选本人的邮箱；
   - 受众（Audience）选“外部”（External）；
   - 联系信息填本人的邮箱；
   - 勾选同意政策，点“创建”。
4. **品牌（Branding）**：打开 `https://console.cloud.google.com/auth/branding`，填写：
   - 应用首页：`https://<U>.github.io/grok-bot-health/`
   - 隐私政策：`.../privacy.html`
   - 服务条款：`.../terms.html`
   - 已获授权的网域：添加 `<U>.github.io`

   然后点“保存”。
5. **数据访问（Data Access）**：打开 `https://console.cloud.google.com/auth/scopes`，点“添加或移除范围”，搜索 `Google Health API`，勾选下面 5 个范围，点“更新”，再点“保存”：
   `googlehealth.activity_and_fitness.readonly`、`googlehealth.health_metrics_and_measurements.readonly`、`googlehealth.sleep.readonly`、`googlehealth.profile.readonly`、`googlehealth.settings.readonly`
6. **客户端（Clients）**：打开 `https://console.cloud.google.com/auth/clients`，点“创建客户端”，应用类型**必须选“桌面应用”（Desktop app）**，名称填 `APP`，点“创建”，再点“下载 JSON”。下载的文件一般在 `/home/box/Downloads/client_secret_*.json`，把它移到 `/home/box/health/client_secret.json`，然后运行 `chmod 600`。如果选成了 Web 应用，授权时会报 `redirect_uri_mismatch`。
7. **发布为正式版（关键）**：打开 `https://console.cloud.google.com/auth/audience`，点“发布应用”（Publish app），再点“确认”，状态要变成 **“正式版”（In production）**。
   - 停在“测试”（Testing）状态的话，授权 **7 天后就会失效**。
   - 页面提示“需要验证”时**不用提交验证**。只给本人自己用完全没问题，未验证的应用最多可以给 100 个用户用。
   - 一定要先发布，再做第 4 步的授权。在发布之前拿到的授权，有效期仍然只有 7 天。

## 第 4 步：授权（本人只需点同意）
```bash
cd /home/box/health && pkill -f "gh.py auth"; setsid nohup .venv/bin/python gh.py auth > auth.log 2>&1 &
sleep 3; cat auth.log      # 里面是授权链接，不含密钥，可以查看
```
1. 用**你自己的浏览器**（第 0 步本人已经登录 Google 的那个）打开 `auth.log` 里的链接，然后用 `request_box_help` 把屏幕交给本人，请他：
   - 选择自己的账号；
   - 如果看到“Google 尚未验证此应用”，点“高级”，再点“转至 Grok Bot Health（不安全）”；
   - 在权限页面**勾选全部复选框**，再点“继续”。
2. 浏览器跳转到 `localhost:8765` 并显示“Authorized”，同时 `auth.log` 里出现 `token saved`，授权就成功了。
3. 授权必须在盒子的浏览器里完成。本人如果在自己的手机或电脑上打开链接，最后跳转到的 localhost 页面会打不开。遇到这种情况，改用 `gh.py auth --manual`：请本人把那个打不开的页面的**完整地址**发给你，你再把它粘贴进去。
4. 验证：
   ```bash
   .venv/bin/python gh.py identity     # 应返回 {"linked": true}
   .venv/bin/python gh.py daily --days 2
   .venv/bin/python gh.py sedentary
   ```
   能看到步数、心率和睡眠数据，才算真正成功。

## 第 5 步（可选）：主动提醒，以久坐提醒为例
只有本人想要主动提醒时才做，否则跳过本步，直接做第 6 步。做完第 4 步后，告诉本人数据已经能读了，并简单说明可以用来做什么（比如问今天的数据、每天总结、久坐提醒），由他决定，不要自己替他加。

**定时的事只能用你自己的 routine 来做。** 盒子（云电脑）没有 bot 在干活、也没人在用 app 的时候，几分钟后就会被平台暂停，后台进程不算活动，会跟着一起停住。所以不要用 `nohup` 后台脚本、本地循环，或者“脚本发 webhook 叫醒 bot”来做定时检查，那样到点了也不会运行。routine 到点会自己唤醒盒子。代价是每次运行都会消耗 Grok Bot 用量。

**一个 routine 只做一件事**：久坐提醒、每日总结等不同任务分别建不同的 routine，不要合并。

久坐提醒的做法（其他主动提醒照这个模式写）：
1. 先读 routines skill，然后用 `UpdateRoutine` 新建一个 routine，名字叫 `久坐提醒`，触发方式用 cron 定时，时区设为本人的时区。提醒时段默认 9:00–22:00（除非本人说了别的），每 30 分钟一次，例如 `0,30 9-21 * * *`，再加一条 `0 22 * * *`。
2. prompt 写：
   > 先在 Shell 运行 `/home/box/health/restore.sh --quiet`。然后运行 `cd /home/box/health && .venv/bin/python gh.py sedentary`（默认看最近 60 分钟、少于 250 步算久坐；数据超过 30 分钟没同步时 `data_stale` 为 true，`sedentary` 不会为 true）。状态记在 `/home/box/health/reminder_state.json`（last_reminded 是 Unix 时间，error_sent 是 true/false；文件不存在就当作空）。
   > - 退出码是 3 或命令失败：如果 error_sent 不是 true，就告诉本人读取手环数据失败、可能需要重新授权（`gh.py auth`），附上简短原因，然后把 error_sent 设为 true；已经提醒过就不再发。
   > - 命令成功：把 error_sent 设为 false。只有 `sedentary` 为 true，并且距离 last_reminded 超过 55 分钟时，才给本人发一条简短友好的起身提醒：写上过去 window_minutes 分钟走了 steps_last_window 步，建议站起来走几分钟、喝口水，每次换个说法；发完更新 last_reminded。
   > - 其他情况什么都不发，也不要回复“没有需要提醒的”。结果只发给本人，就在这个聊天里。
3. 验证：手动运行一次 `gh.py sedentary`，确认能返回 JSON；再确认 routine 已经保存，时区和时间都对。

## 第 6 步：防中断（盒子重置、更新或暂停之后）
盒子重置或更新后，正在运行的进程、系统里装的软件和 /tmp 都会被清掉，只有 /home/box 下的文件会保留下来。盒子闲下来还会被暂停。所以工具包不依赖任何常驻进程：
- 即使跳过了第 5 步也要做本步，保证随时能读数据。
- 代码、venv 和凭证都放在 `/home/box/health`，凭证另外在 `/home/box/.health-backup` 存一份备份。gh.py 刷新 token 时会自动更新这份备份。
- `restore.sh` 可以反复运行，结果都一样：venv 坏了就重建，凭证丢了就从备份恢复。它不启动任何后台进程。
- **用 `UpdateMemory` 写一条长期规则**：
  > 每次被唤醒（不管是聊天消息还是 routine），做任何事之前，先在 Shell 安静地运行 `/home/box/health/restore.sh --quiet`。没有输出就说明一切正常，不用告诉本人。有输出的话自己修好，只有需要本人重新授权时才找他。定时的事一律用自己的 routine（一个 routine 只做一件事），不用后台脚本或 webhook。

## 故障排查
| 现象 | 原因和处理办法 |
|---|---|
| 授权 7 天后失效（gh.py 报 `auth_expired_or_revoked` 或 `invalid_grant`） | 应用还停在“测试”状态，或者是在发布之前授权的。按第 3 步第 7 条发布为正式版，再重做第 4 步。另外，授权连续约 6 个月没用过，或者本人在 Google 账号里撤销了授权，也会失效。 |
| 报 `redirect_uri_mismatch`，或 gh.py 提示不是“桌面应用”客户端 | 第 3 步第 6 条建成了 Web 客户端。重新建一个“桌面应用”客户端，下载新的 JSON。 |
| `Error 403: access_denied`（提示“尚未完成 Google 验证流程”） | 应用还在“测试”状态，而且本人不在测试用户名单里。发布为正式版，或者在 Audience 页把本人加为测试用户。 |
| 显示“Google 尚未验证此应用” | 正常现象。点“高级”，再点“转至…（不安全）”。 |
| 403 `SERVICE_DISABLED`，或提示 “has not been used in project” | 漏了第 3 步第 2 条，或者在别的项目里启用了。在正确的项目里启用 API，等几分钟再试。 |
| 403 `insufficient scopes`，或者某一类数据报错 | 授权时有复选框没勾上，或者第 3 步第 5 条少加了范围。把范围补全，重做第 4 步，这次全部勾选。 |
| `gh.py identity` 返回 `ACCOUNT_NOT_LINKED` | 这个 Google 账号还没在 Google Health app 里登录，或者 Fitbit 迁移还没完成。请本人在手机上完成后再试。 |
| 授权最后跳转到的 localhost 页面打不开 | 不是在盒子的浏览器里授权的。改用盒子的浏览器重做，或者用 `gh.py auth --manual`。 |
| 报 `Address already in use`（8765 端口被占用） | 上一次的 `gh.py auth` 还在运行。先运行 `pkill -f "gh.py auth"`。 |
| 数据为空、显示 `data_stale: true`，或者一直不提醒 | 手环没同步。超过 30 分钟没有新数据时，routine 会故意不提醒。请本人打开 Google Health app 下拉刷新，并确认手环的蓝牙连着。刚开始戴的手环，第一天的数据可能很少。 |
| GitHub Pages 返回 404 | 刚开通时要等几分钟。确认仓库是公开的，并在仓库的 Settings → Pages 里确认来源是 main 分支的 /(root)。 |
| Google 控制台的品牌页保存不了（网域报错） | 已获授权的网域只填 `<U>.github.io`，前面不加 https，后面不带路径。 |
| 不再提醒 | 确认 routine 还在、时区和时间正确，prompt 第一步是运行 `restore.sh --quiet`，并且第 6 步的长期规则已经写进记忆。 |
| `pip install` 失败 | 一般是网络临时出问题。过一会儿重新运行 `restore.sh`，它会自动重建 venv。 |

## 安全底线
- 绝不打印、上传或提交 `client_secret.json` 和 `token.json`。
- 健康数据只存在本人自己的盒子上，不公开，不用任何第三方服务，只申请只读权限。
