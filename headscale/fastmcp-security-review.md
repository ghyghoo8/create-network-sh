# 提交前敏感信息检查与清理

日期：2026-10-29（Asia/Shanghai）。本次提交前复核覆盖整个仓库的当前 Git 候选文件，以及本地可见的 1 个历史提交；下文同时保留此前 `fastmcp/` 导入清理记录。本次检查与本地脱敏未连接或修改线上服务，没有运行网关/隧道，没有轮换凭据、暂存、提交或改写 Git 历史。

## 本次提交前复核结果

- 当前 Git 候选范围共 34 个文本文件：原有根目录资料、`fastmcp/`、`headscale/` 及新增忽略规则。未发现真实生产令牌、私钥、API key、cookie、完整登记 ID、实际 VPS 公网地址或实际 ngrok 域名。
- 清理 2 个文件中的 3 处个人本机路径：根 README 改用 `$HOME`，Headscale 上传命令改为从仓库根目录使用相对路径，保留配置和操作说明。
- FastMCP 的两个 `.env.example` 凭据项为空；测试 token、测试邮箱和保留域名属于离线测试夹具。公开软件 SHA-256、官方源地址、回环地址和示例网段均保留。
- 当前候选文件没有 ZIP、数据库、私钥、运行日志或生成二进制；此前要求删除的三个 ZIP 未重新出现。浏览器截图位于用户提供的附件临时位置，不在仓库候选范围；含真实入口的截图不应复制入提交材料。
- 新增根 `.gitignore` 和 `headscale/.gitignore`，覆盖真实 `.env`、cookie secret、私钥、SQLite 状态、日志/缓存、VPS 配置回拷和下载产物，同时保留 `.env.example`、`config.env.example` 与全部脚本和文档。
- `fastmcp/gitee/import-manifest.json` 的 15 条当前文件大小、SHA-256、权限均匹配。

历史边界：原始提交 `94dec20` 的 `README.md` 第 5 行仍含旧的本机用户路径。当前工作树已脱敏，后续普通提交不会清除旧提交里的内容。本次未发现历史中的真实凭据，也没有重写历史；如要连同这项个人路径一起从历史彻底移除，需要单独处理。

检查方法：完整文件清点、隐藏文件和 Git 忽略规则检查、常见密钥/认证格式扫描、域名/IP/个人路径分类、两份独立目录复核及历史文本检查。没有联网验证任何 token，没有读取 VPS 的真实 `.env` 或运行期密钥；这份结论针对当前文件和可见历史，不代表对未收录运行数据的检查。

提交前检查：10 个 Python 文件完成语法解析，5 个 Shell 脚本通过 Bash 语法检查，本地 Markdown 文件链接目标检查及 `git diff --check` 通过；17 个私密/运行路径的忽略行为与 7 个应保留示例/交付文件的可提交行为已验证。没有为本次文档和忽略规则调整安装依赖或运行服务。

## 此前 FastMCP 导入清理结果

- 真实授权账号统一替换为小写 `your-github-login`，覆盖认证常量、文档、索引与历史测试。
- 实际公网服务域名统一替换为 `mcp.example.com`，同步覆盖 OAuth base URL、Host/Origin 关联配置、ngrok 入口与部署示例。
- 按公子最新要求直接删除三个 ZIP，不重新打包、不保留备份。
- 删除 `fastmcp/.DS_Store` 和 `fastmcp/gitee/.DS_Store`，增加忽略规则，空 `.env.example` 继续保留。
- 移除私有会话链接；保留来源包名称、原始摘要及历史排除项说明。
- 更新归档索引、部署入口和清单，避免已删除 ZIP 的下载/部署说明及脱敏前哈希被误认为当前文件证据。

配置占位说明见 [Gitee 网关 README](../fastmcp/gitee/README.md#配置占位说明)。本地资料现在是配置模板，不能直接覆盖线上真实配置；GitHub 白名单、Host/Origin 防护和令牌隔离逻辑未放宽。

## 检查依据

清理前检查了 18 个 UTF-8 文本（2679 行），包括所有隐藏模板；两个 Finder 元数据文件；三个 ZIP 中全部 18 个文本条目（解压后共 222617 字节）。未运行其中代码或联网验证任何凭据。

本次未发现高置信的生产令牌、私钥、带凭据数据库 URI 或已填写的真实 `.env`。两份 `.env.example` 的凭据项为空。`test_gateway_tools.py` 的 PAT、前端 token 和 webhook secret 用于 MockTransport、假响应与脱敏断言，保留为测试 fixture，未将其认定为生产泄露。

静态检查不能覆盖无特征、混淆或运行时注入的秘密，也不覆盖 VPS 的真实 `.env`、进程环境和日志。资料曾在其他位置发布与否不在本次证据范围内。

## 已删除内容

| 路径（相对 `fastmcp/`） | 处理 |
| --- | --- |
| `.DS_Store` | 删除 |
| `gitee/.DS_Store` | 删除 |
| `gitee/完整部署/04_交付包/gitee_gateway_complete_20261009.zip` | 删除，不保留备份 |
| `gitee/完整部署/04_交付包/gitee_gateway_tools_upgrade.zip` | 删除，不保留备份 |
| `gitee/完整部署/04_交付包/gitee_service_scripts.zip` | 删除，不保留备份 |

## 保留的运行边界

归档代码监听 `127.0.0.1:8765`，FastMCP HTTP 路径为 `/mcp`，通过 ngrok 出站隧道暴露；资料中没有本地 Nginx/Caddy 配置。GitHub OAuth、账号白名单和上游 Gitee PAT 是独立应用边界，Headscale 不替代它们。

入口域名需要在 `gateway_server.py` 的 `BASE_URL`/`allowed_hosts`、`start.sh` 的 `NGROK_URL`、GitHub OAuth App 及客户端入口中保持一致；账号常量须为小写。这里只替换本地资料，未把占位配置应用到 VPS。

`G8_GATEWAY_PORT` 仍只影响脚本探测和 ngrok 目标，Python 服务固定 8765；OAuth 仍使用启动时随机签名密钥与内存状态。没有为本次清理改变这些行为，也没有重启网关。

另一个项目的 `migration_manifest.py` 八文件基线未修改。当前展开导入文件的大小与 SHA-256 见 [import-manifest.json](../fastmcp/gitee/import-manifest.json)。

## 验证范围

已核对原账号/域名在剩余本地资料中无明文残留，指定 ZIP 和 Finder 元数据均已删除，凭据模板仍为空。完成后另检查 Python 语法、Shell 语法、占位认证行为及清单摘要一致性；这些均属于本地证据，不是线上业务验收。
