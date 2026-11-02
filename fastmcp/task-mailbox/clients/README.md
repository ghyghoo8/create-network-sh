# 客户端接入

这些文件是占位模板，不是已登记插件或运行配置。先完成宿主 OAuth／HTTPS 验证，再替换 `mcp.example.com` 为实际服务域名。保持各客户端同一 `/mailbox/mcp` 端点，不携带服务器端 GitHub client secret。

## Codex

在实际使用的客户端执行，或将 [TOML 条目](codex.config.example.toml) 合并至其现有配置：

```bash
codex mcp add task-mailbox --url https://mcp.example.com/mailbox/mcp
codex mcp login task-mailbox
```

本轮 Mac CLI 0.166.0-alpha.5.1 已原生登记该端点并回读配置；首次登录收到了本地回调，但令牌交换返回 `Request failed`。没有自动重登、更换认证或读取令牌缓存。桌面、CLI 与其他机器的有效配置、工具发现及身份须分别回读，不能互相推定。

原生 OAuth 的 `127.0.0.1:<临时端口>/callback` 是运行登录流程的 Mac 客户端接收地址；它不同于 GitHub OAuth App 中服务器的 `/mailbox/auth/callback`，也不同于云端插件自己的回调。不要因看到 loopback 回调就改写服务器配置。参见 [OpenAI MCP 文档](https://learn.chatgpt.com/docs/extend/mcp#oauth-client-registration-and-callbacks)。

Codex App 的“钩子”可用于会话查信、结果入本地待发队列等生命周期适配；它不替代持续收件桥，当前没有安装或启用，见[设计与限制](../docs/hooks.md#codex-app-原生钩子适配)。

## Kimi Code

将 [JSON 条目](kimi.mcp.example.json) 合并至实际版本使用的 MCP 配置，保留既有条目。当前官方 kimi-code 文档使用 `~/.kimi-code/mcp.json` 或项目内 `.kimi-code/mcp.json`，交互命令为 `/mcp-config`、`/mcp-config login task-mailbox`，通过 `/mcp` 回读。旧 kimi-cli 的 `kimi mcp add` 不应套用到不提供该子命令的新版 CLI。

配置与登录行为依据 [Kimi Code 官方 MCP 文档](https://github.com/MoonshotAI/kimi-code/blob/main/docs/en/customization/mcp.md)。当前机器 Kimi Code 2.4.1 不提供 `mcp add` 子命令；委托执行侧已将端点原子写入其用户级 MCP 配置并核对保留既有条目；主执行侧另行回读端点匹配与文件权限 `0600`。尚未启动 Kimi 新会话、登录或回读工具。

## ChatGPT 云端／Dot

[cloud-plugin](cloud-plugin/) 仅保存 portable plugin 的源模板。实际端点验证后，将 `.example` 文件复制为 `plugin.json` 和 `mcp.json`，填入真实 HTTPS 端点，校验并打包到临时产物目录，再通过获准的插件连接流程登记、安装并完成 OAuth。不要上传带占位端点的包来试探登记；不要把认证密钥打进包中。

插件元数据有严格长度／格式要求，修改后需重新验证。本轮已从此模板创建账号下的私有插件 `0.1.0` 并回读登记元数据，公子回报已连接。实际地址和插件标识只留私密交付；仓库模板继续使用占位值。当前执行会话尚未发现信箱工具，因此不能将上传、用户连接回报代替 Dot 的原生工具调用或结果读取。云端认证与注册依据 [OpenAI MCP 接入说明](https://developers.openai.com/api/docs/mcp#handle-authentication)。

## 双向验收

Dot 提交一个新的固定 job ID 与随机片段，本地客户端按游标读取并发布变换结果；Dot 读取完整结果，核版本／摘要并确认。随后交换方向再做一次。记录各侧真实调用证据，不能用回环模拟客户端替代真实 Dot 或 Mac 客户端。信箱不负责自动唤醒、后台轮询或执行 Herdr。
