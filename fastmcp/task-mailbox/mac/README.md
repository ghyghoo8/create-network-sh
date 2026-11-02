# Mac 项目协调桥

本目录实现 [事件与钩子方案](../docs/hooks.md) 的本地收件、会话感知和结果补传。VPS 九项工具契约不变；本桥不调用模型、Herdr、任意 shell 或任务携带的回调 URL。

## 可用能力

- 全局事件分页入本机 SQLite，整页和游标同事务提交；稳定事件去重，冲突或满库不推进水位。
- 按原 job 核对任务摘要、精确结果版本及 hash；取消保持请求，UNKNOWN 保持待对账。
- 保存项目目标／路由摘要并明确标为调用方数据；不把目标文字当执行许可。
- Codex 生命周期只记录配置范围内的 session、turn、工具引用与最近观察时间，不读取 transcript，不保存 prompt／末条回复。
- 显式绑定 session/job；结构化结果先暂存，绑定会话的 Stop 才将它放入持久补传队列，重复 Stop 不新增报告。
- `status` 汇总待办、HELD、取消、UNKNOWN、待补传、最近会话信号和连接健康；旧信号不证明进程仍在运行或已停止。

## 独立安装

仅使用本地盘。以下路径均为占位示例，运行时凭据、真实端点和配置不进入仓库：

```bash
python3 -m venv "$HOME/Library/Application Support/TaskMailbox/.venv"
"$HOME/Library/Application Support/TaskMailbox/.venv/bin/python" -m pip install -r mac/requirements.txt
python3 mac/install.py \
  --runtime-dir "$HOME/Library/Application Support/TaskMailbox" \
  --state-dir "$HOME/Library/Application Support/TaskMailbox/state" \
  --endpoint https://mcp.example.com/mailbox/mcp \
  --allowed-root /absolute/path/to/herdr-project \
  --allowed-root /absolute/path/to/mailbox-repository \
  --source-commit FIXED_SOURCE_COMMIT
```

安装器独立复制源码，记录摘要和版本，生成权限 `0600` 的私密配置、Codex hooks.json 及 launchd 单元；保留其它 hook，修改已有 hook 前保存私密备份。它**不授予 hook trust、不启动 launchd、不登录 OAuth**。同一运行目录不允许静默更换源身份或监测范围。

在 Codex 设置的“钩子”或原生 `/hooks` 中审阅新定义并信任精确当前版本。钩子只使用本机 SQLite，超时 3 秒；SessionStart／UserPromptSubmit 的附加上下文只含固定提示、关联 ID／hash 和计数。[官方钩子规则](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks)

## 授权、查询和运行

进入独立复制的 app 目录后：

```bash
../.venv/bin/python bridge.py login
../.venv/bin/python bridge.py status
../.venv/bin/python bridge.py once
../.venv/bin/python bridge.py run
```

`login` 才允许用户浏览器完成本桥自己的 OAuth，不读取 Codex／Kimi 的认证缓存。专用缓存加密保存，目录 `0700`、文件 `0600`；正常运行保留同一 client 的静默 refresh。缺缓存或认证明确拒绝停止该分支，不自动重新登录、DCR、换端点或认证方式。OAuth 路径发现也持久保存，重启不把带前缀 token endpoint 简化为站点根路径。

`run` 使用单进程文件锁，默认每 30 秒一轮、每页 25、最多 4 页／10 RPC／20 秒；单 RPC 10 秒。网络错误退避 60／120／300 秒，SIGTERM 可结束等待。同步、钩子与本地暂存互不等待远端网络。程序收到取消只记录／提示，不宣称下游已停止。

授权后可先人工运行短窗口；决定采用 launchd 时加载安装器生成的用户单元。`KeepAlive=false` 避免认证故障反复重启；授权或配置修好后需显式重新启动。单元没有打开 Mac 公网端口。Mac 睡眠时不能保证持续感知，恢复后沿原游标补读。

## 绑定与报告

只有已经校验并缓存摘要的 job 可以绑定；cwd 须在配置的项目范围内：

```bash
../.venv/bin/python bridge.py bind --session-id ORIGINAL_SESSION --job-id ORIGINAL_JOB --cwd /absolute/project/path
../.venv/bin/python bridge.py stage-report --session-id ORIGINAL_SESSION --turn-id ORIGINAL_TURN \
  --event-id STABLE_REPORT_EVENT --status UNKNOWN --result-file /private/path/result.json
```

报告文件必须是 JSON 对象，规范化后最多 1 MiB。报告与 session/turn/job 匹配后，Stop 入 outbox，成功后把暂存原件移入本机归档，允许下一份报告继续暂存；入队失败保留原件。同事件 ID 上传 ACK 丢失时只补传原报告，不重跑业务。不得悄悄用另一个结果覆盖尚未入队的暂存；变更需沿原事件对账。

## 验证与边界

在服务根运行 `python3 -m unittest discover -s tests -v`。台账／collector fake transport／hook 和安装测试只用标准库、临时目录和本地子进程，不调用外部模型或业务执行器。完整安装的依赖环境与真实 OAuth／工具调用单独验证，当前证据见 [verification.md](../docs/verification.md)。

本机数据库默认 32 MiB、未处理记录／待发报告各 500；VPS 配额保持原值。日志／journal／OAuth 状态／结果暂存另占空间，不自动删历史腾空间。当前无多 Mac claim/fencing、无服务端 stream identity；只允许同一未替换源数据库与单个资源写者。云端插件绑定和 Dot 自动唤醒不由本桥安装推导。
