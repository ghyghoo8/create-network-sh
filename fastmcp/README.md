# FastMCP 服务

本目录按服务保存展开源码、部署资料及来源记录。每项服务独立管理运行目录、依赖、认证和数据，不把此目录当成统一进程或公共凭据入口。

| 服务 | 内容与入口 |
| --- | --- |
| [Gitee](gitee/README.md) | 原有脱敏参考资料与导入清单；线上配置不由占位模板覆盖 |
| [Task Mailbox](https://github.com/CF-FE/task-mailbox-mcp) | 唯一维护仓为 `CF-FE/task-mailbox-mcp`；[本目录旧副本](task-mailbox/INTEGRATION.md)仅保留固定来源与部署历史，不承接后续功能或修复 |

公网入口可沿既有 ngrok／Caddy 路径分流，但各服务分别认证和验收；工具发现、持久接收、实际读取与业务执行分开记录。不要用 Headscale 的身份替代 MCP OAuth，也不要将新服务合并到旧 Gitee 进程。

返回[仓库首页](../README.md)。
