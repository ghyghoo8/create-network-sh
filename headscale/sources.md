# 来源、版本与证据边界

核验日期：2026-10-29（Asia/Shanghai）。当前方案：Vultr、免费 ngrok 单域名共享、Headscale 自建、官方公共 DERP、无备份。替代域名/DNS/IP 证书方案未采用。

## 固定发布资产

Headscale `releases/latest` 返回 v0.29.6（2026-10-24T10:29:04Z），最低 Tailscale v1.80.0；Caddy 返回 v2.11.7（2026-10-03T05:58:33Z）。以下摘要来自对应官方 GitHub Releases API。重建脚本在 VPS 实际下载时必须再次计算并比对摘要。

| 资产 | SHA-256 |
| --- | --- |
| `headscale_0.29.6_linux_amd64.deb` | `a3b49916a16418c704cef89818d734bc8af0528aac965a2dd5ca4bfa4cef48e2` |
| `headscale_0.29.6_linux_arm64.deb` | `077467b12ba2122086db434335fadfa8deee4dbddacb1f959eecc6d7d10b81d4` |
| `caddy_2.11.7_linux_amd64.tar.gz` | `727b91701a392de6ebc5027509f548bf39979e5216340d0faed8fa5e69c84f8b` |
| `caddy_2.11.7_linux_arm64.tar.gz` | `d8fc6d179a5d283028a472a5618564f6ad8a86fed513e64f032b3b0b7cc45e42` |

[Headscale 发布记录](https://github.com/juanfont/headscale/releases/tag/v0.29.6)、[Caddy 发布记录](https://github.com/caddyserver/caddy/releases/tag/v2.11.7)。执行位置和用户回传证据见文末，助手没有直接操作 VPS。

## 直接来源

| 资料 | 核验用途 |
| --- | --- |
| [Headscale v0.29.6 配置](https://github.com/juanfont/headscale/blob/v0.29.6/config-example.yaml) | SQLite、公共 DERP、TLS 关闭、DNS、私钥和监听字段 |
| [v0.29.6 路由表](https://github.com/juanfont/headscale/blob/v0.29.6/hscontrol/app.go#L544) | Headscale 路径及方法；不将全部 auth/register 路由抢占 |
| [v0.29.6 反代说明](https://github.com/juanfont/headscale/blob/v0.29.6/docs/ref/integration/reverse-proxy.md) | POST 特殊升级与代理要求 |
| [v0.29.6 策略](https://github.com/juanfont/headscale/blob/v0.29.6/docs/ref/policy.md) | Grants、默认全放行与本人节点策略 |
| [v0.29.6 FAQ](https://github.com/juanfont/headscale/blob/v0.29.6/docs/about/faq.md) | 容量不保证、SQLite、同机 tailnet 支持边界 |
| [v0.29.6 systemd](https://github.com/juanfont/headscale/blob/v0.29.6/packaging/systemd/headscale.service) | 用户、数据目录、运行权限 |
| [v0.29.6 configtest](https://github.com/juanfont/headscale/blob/v0.29.6/cmd/headscale/cli/configtest.go)、[初始化](https://github.com/juanfont/headscale/blob/v0.29.6/cmd/headscale/cli/utils.go) | 检查会初始化状态，应停服务后以服务用户运行 |
| [v0.29.6 配置校验](https://github.com/juanfont/headscale/blob/v0.29.6/hscontrol/types/config.go)、[DEB postinst](https://github.com/juanfont/headscale/blob/v0.29.6/packaging/deb/postinst) | base_domain 父域约束与包安装自动启动行为 |
| [接入说明](https://headscale.net/stable/usage/getting-started/)、[注册源码](https://github.com/juanfont/headscale/blob/v0.29.6/cmd/headscale/cli/auth.go) | owner 用户、交互登记及 auth register |
| [Headscale DERP](https://headscale.net/stable/ref/derp/)、[官方公共 map](https://controlplane.tailscale.com/derpmap/default) | 内置关闭后使用公共地区，不能把默认公共 map 称为自建中继 |
| [Tailscale 连接类型](https://tailscale.com/docs/reference/connection-types)、[诊断](https://tailscale.com/docs/reference/troubleshooting/poor-performance-tailnet) | 直连与中继的数据路径、客户端验证 |
| [FastMCP v4.0.11 OAuthProxy](https://github.com/PrefectHQ/fastmcp/blob/v4.0.11/fastmcp_slim/fastmcp/server/auth/oauth_proxy/proxy.py#L2450) | /auth/callback 和 /consent，避免截获现有回调 |
| [MCP SDK v2.3.0 OAuth](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/src/mcp/server/auth/routes.py#L46) | /authorize、/token、根路径 /register、/revoke、元数据 |
| [ngrok 域名](https://ngrok.com/docs/gateway/domains)、[免费限制](https://ngrok.com/docs/pricing-limits/free-plan-limits) | 唯一开发域名、额度与端点限制 |
| [ngrok HTTP](https://ngrok.com/docs/gateway/endpoints/http#hop-by-hop-headers)、[WebSocket](https://ngrok.com/docs/using-ngrok-with/websockets) | HTTPS 在 ngrok 终止；普通 WebSocket 支持不等于特殊 POST 协议已验收 |
| [ngrok 内部端点](https://ngrok.com/docs/gateway/endpoints/internal-endpoints#internal-endpoints-pricing)、[Forward Internal](https://ngrok.com/docs/gateway/traffic-policy/actions/forward-internal) | 内部端点要求 Pay-as-you-go，不适用于已确认免费套餐 |
| [Caddy route](https://caddyserver.com/docs/caddyfile/directives/route)、[reverse_proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy) | 显式顺序、Host 与流式升级转发 |
| [Vultr Firewall](https://docs.vultr.com/products/network/firewall-groups/management/rules) | 原有入站规则归属；当前 ngrok 方案无需新增入站服务端口 |

FastMCP v4.0.11 的框架 wheel 曾在内存读取并核对发布摘要；未安装。实际 VPS 是否使用相同版本、是否有额外路径仍需现场确认。

## 证据边界

- 本地：资料清理、配置与脚本准备、语法/模板/静态路由检查，以及补丁的隔离检查/应用/幂等/精确回退测试。
- 实际 Caddy 运行检查未完成：官方同版本 Mac 测试二进制下载缓慢已中止，未执行不完整资产；VPS 脚本在正式启动新入口前执行 Caddy 配置验证。
- 用户于 2026-10-29 回传：VPS 预检和安装完成；本地新入口 `/health` 200、`/mcp` 401；ngrok 切换前后原 gateway 受控记录一致；Windows 公网 `/health` 返回 pass、`/mcp` 401；第一台 Windows 手动注册后 Headscale 显示 online。助手没有直接执行这些 VPS/Windows 操作。
- 该实例首台客户端的实际注册与在线控制连接已有用户回传证据；不能外推所有 ngrok 边缘或版本均兼容。其他客户端、后续重连、公共 DERP 实际中继、节点间业务及原 MCP/Hysteria 完整业务回归仍为待验收。
- 不创建备份、不恢复旧节点身份、不自动升级 ngrok、改 DNS、收费或回退到另一条接入路径。

## Headplane 可选面板

固定版本：Headplane 0.8.2（2026-10-22），Node 24.22.1。Headplane 0.7 起明确支持 Headscale 0.29 系列；当前实例已收到 HTTP 302 与浏览器对话框截图，完整管理操作和稳态资源仍需分别验收。

| 固定资产 | SHA-256 |
| --- | --- |
| Node `node-v24.22.1-linux-x64.tar.xz` | `6c172a9ab6718f7b801fb5a7bd486af2ee5e32758086a04b84fcce2aa77095e6` |
| 官方镜像 linux/amd64 manifest | `df325c86556b9485104931fad476364922a765f865a4a00e9af847ce45b0f04a` |
| 官方 `/app/build` 层，22674810 字节 | `0a62fd590d4ff0459926f367aa7c5f72550234e99a8abd1e0a1d22e22b1b2545` |
| 官方 `/app/drizzle` 层，2884 字节 | `35c4d8d6af473c41eb9f86daafcd4444166436ce8de27adfbd6daa5c2c259f74` |

来源：[0.8.2 发布说明](https://github.com/tale/headplane/releases/tag/v0.8.2)、[0.7 兼容说明](https://github.com/tale/headplane/releases/tag/v0.7.0)、[Node 校验清单](https://nodejs.org/dist/v24.22.1/SHASUMS256.txt)、[Dockerfile](https://github.com/tale/headplane/blob/v0.8.2/Dockerfile)、[生产 bundle 配置](https://github.com/tale/headplane/blob/v0.8.2/vite.config.ts)。GHCR manifest 和 history 已核对两个 COPY 层与目录的对应关系；仅提取应用内容，不使用镜像内 Node 或可选 agent。

运行与边界：[官方原生运行说明](https://headplane.net/install/native-mode)、[配置示例](https://github.com/tale/headplane/blob/v0.8.2/config.example.yaml)、[只读配置检测](https://github.com/tale/headplane/blob/v0.8.2/app/server/headscale/config-loader.ts#L329)、[原生 proc 集成](https://github.com/tale/headplane/blob/v0.8.2/app/server/config/integration/proc.ts#L32)、[API key 登录](https://github.com/tale/headplane/blob/v0.8.2/app/routes/auth/login/action.ts#L40)、[文件 ACL 只读处理](https://github.com/tale/headplane/blob/v0.8.2/app/routes/acls/acl-loader.ts#L65)。只读配置、独立 UID、关闭 agent 的 API 管理范围已按源码核对；面板不获原服务的信号权限。

官方 release 的上传资产只有文档归档，不提供原生应用包。本项目从固定官方 OCI 层取得 bundle 后以 Node 原生运行，属于本项目的交付封装。不是官方现成安装包，也没有把现有 Headscale 迁移进 Docker。

本地新增脚本语法、帮助与隔离检查通过；官方应用层实际下载在本地 300 秒时限内未完成且已清理。Node 24.22.1 Mac 测试运行时已核验官方摘要并执行版本命令，未取得完整应用进行启动。用户随后回传 VPS 下载、校验与服务创建结果，日志确认 Node 24.22.1；首次启动因禁用的 Kubernetes 块仍缺少必填 `pod_name` 而失败，补齐后返回 HTTP 302，浏览器新增设备对话框可见且 Owner 列表包含 `owner`。这些属于用户回传的实际实例证据；助手未直接操作 VPS、SSH 隧道或浏览器，不能由此宣称所有管理功能、稳态资源和原业务回归均已通过。

## ChatGPT 云端 VPN 核验

[OpenAI 官方云端环境文档](https://learn.chatgpt.com/docs/environments/cloud-environments#private-networking-vpn) 已实际检索并读取：当前 VPN 提供方为 Tailscale，要求 Reusable 与 Ephemeral，保存后需重新发布环境并以新任务测试。文档没有提供 Headscale 自定义控制地址配置。

本机只读实现证据：ChatGPT 26.1023.51421（22530），静态配置模型的 VPN 请求字段为 `draft_id`、`provider`、`auth_method`、`connection_id`、`expected_etag`、`auth_key`、`base_version_id`、`expected_draft_revision`；提供方和认证方式分别固定为 `tailscale`、`auth_key`，没有 `login_server` / `control_url`。未读取用户凭据或提交任何云端设置。

结论仅限当前内置入口：没有可配置到自建 Headscale 的支持路径。实际云端实例、独立客户端或其他网关没有做运行验证。云端接入没有实施；用户随后决定停用自建服务，并回传 Headscale、Headplane 均为 `inactive` / `disabled`。配置、节点数据与共享 Caddy 保留，未据此迁移 Windows 到另一网络。停止与重新启用步骤见 [教程](./安装与管理教程.md#service-lifecycle)；恢复步骤是后续操作参考，尚未执行。
