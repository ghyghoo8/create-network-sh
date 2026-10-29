# Gitee MCP 网关

G8 Gitee 网关提供仓库、文件、分支、提交、PR、issues 和 hooks 等 MCP 工具，通过 GitHub OAuth 验证访问身份。源码及原部署资料保存在 [完整部署](完整部署/00_归档索引.md) 中，保留原目录布局。

本目录是脱敏后的参考资料；未包含 `SKILL.md` 或 Codex plugin 清单，也不是已部署服务的配置目录。

## 来源与完整性

- 来源：历史资料包 `gitee_20261020.zip`，记录的导入日期为 2026-10-20；私有会话链接已移除。
- 原导入记录包含 18 个文件，外层 `gitee/` 对应本目录。2026-10-29 按公子要求脱敏账号与域名，并删除三个 ZIP，当前文件不再声称与原包逐字节相同。
- 原始 `gitee/.token` 被导入记录列为排除项，本目录没有该凭证文件。
- [import-manifest.json](import-manifest.json) 保留来源包信息，并记录脱敏后剩余导入文件的当前大小、SHA-256、原路径和权限，以及已删除的交付包。它不是 Codex 安装配置。
- 当前仅维护展开的代码与文档，不再提供 ZIP；此清理未连接或修改线上服务。

## 配置占位说明

| 占位值 | 需要替换的位置 |
| --- | --- |
| `your-github-login` | `01_代码与脚本/auth_policy.py` 的 `ALLOWED_LOGIN`，以及部署示例和历史测试中的账号断言；常量须使用小写，与现有 `casefold()` 比较一致 |
| `mcp.example.com` | `gateway_server.py` 的 `BASE_URL` 和 `allowed_hosts`、`start.sh` 的 `NGROK_URL`，以及 GitHub OAuth App 的 Homepage/Callback 和 MCP 客户端入口；主机名必须一致 |
| 空凭据字段 | `.env.example` 的 `GITHUB_CLIENT_ID`、`GITHUB_CLIENT_SECRET`、`GITEE_ACCESS_TOKEN`；真实值只在目标服务器的私有 `.env` 填写 |

`mcp.example.com` 是示例域名，不是可使用的隧道入口；账号占位符也不是实际授权账号。账号和域名目前由源码常量配置，不会自动从 `.env` 读取。首次部署前需一起替换，不能用 `*` 放宽身份、Host 或 Origin 校验。现有线上配置不要被本目录的占位模板覆盖。

## 文件入口

| 目录或文档 | 内容 |
| --- | --- |
| [01_代码与脚本](完整部署/01_代码与脚本/) | 网关、仓库工具、认证策略、启停脚本和配置示例 |
| [部署指南](完整部署/02_部署文档/部署指南.md) | 已替换账号和域名的部署参考 |
| [服务启停说明](完整部署/02_部署文档/服务启停说明.md) | 后台进程、日志和停止方式 |
| [03_诊断与验收](完整部署/03_诊断与验收/) | 扩展网关测试、诊断程序及旧项目迁移清单工具 |
| [05_历史资料](完整部署/05_历史资料/) | 历史配置示例与旧版测试 |

## 运行前提

原资料记录的运行环境为 Python 3.14.4、FastMCP/fastmcp-slim 4.0.11、MCP 2.3.0。源码会检查这三个 Python 包的准确版本，还引用 `httpx2`、`mcp_types`、`jsonschema` 等模块。原包未提供独立依赖锁文件，本次没有新增或猜测依赖版本。

原启动流程面向 Linux，依赖 Bash、GNU coreutils、util-linux 和已配置的 ngrok。网关使用 HTTP 传输，监听 `127.0.0.1:8765`，MCP 路径为 `/mcp`。

服务固定读取 `/opt/gitee-mcp-gateway/gateway/.env`，要求它是权限为 `600` 的普通文件。所需配置名称：

| 配置 | 用途 |
| --- | --- |
| `GITHUB_CLIENT_ID`、`GITHUB_CLIENT_SECRET` | GitHub OAuth App |
| `GITEE_ACCESS_TOKEN` | 上游 Gitee 访问凭证 |
| `GITEE_MODE` | `READ` 或 `WRITE` 模式 |

外部目的地包括 GitHub OAuth/API、Gitee MCP/API 及待配置的 ngrok 域名。授权账号和入口域名已替换为占位值，默认路径仍保留，因此归档成功并不代表它可以直接启动。

## 原部署与测试方式

分类目录用于保存源资料。原部署指南要求将代码与诊断文件平铺到 `/opt/gitee-mcp-gateway/gateway/`，而非直接从当前分类目录执行测试：`test_gateway_tools.py` 会在自身同目录查找网关源码。

在原部署前提均满足后，从该部署目录执行：

```bash
/opt/gitee-mcp-gateway/.venv/bin/python test_gateway_tools.py
bash start.sh
# 停止由该脚本管理的服务
bash stop.sh
```

代表性就绪检查为未认证的 `/mcp` 请求返回 `401`，随后还需经过 OAuth 连接、列工具和只读请求验证；`401` 本身不能证明完整功能可用。具体步骤见原部署指南。本次没有执行上述部署、服务启动或外部请求。

`migration_manifest.py` 针对另一个项目的原八文件快照；它不是本次导入的验收工具。原文中的历史测试结果也不作为当前环境的测试结果。

## 验证范围

导入时检查 ZIP CRC、18 个文件的逐字节内容与 SHA-256、Python 源码解析、Shell 语法、仓库结构及仓库检查工具的测试。FastMCP、`httpx2` 和 `mcp_types` 当前未安装，原网关的离线功能测试、真实 OAuth/Gitee 连接及隧道启动尚未运行。

本次清理另做原账号/域名残留检查、ZIP 与 Finder 元数据检查、Python 语法解析、Shell 语法及当前清单哈希核对。未运行原网关或隧道，未安装依赖，未测试生产 OAuth/Gitee 连接。

返回 [仓库首页](../../README.md)。检查与清理记录见 [敏感信息检查](../../headscale/fastmcp-security-review.md)。
