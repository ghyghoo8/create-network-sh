# 搭建专属网络

* Headscale 部署、客户端接入与 Headplane 管理：[安装与管理教程](./headscale/安装与管理教程.md)
* 方案、固定版本与来源：[Headscale 方案](./headscale/README.md)
* 提交前脱敏结果及历史边界：[敏感信息检查记录](./headscale/fastmcp-security-review.md)

* 参考：https://segmentfault.com/a/1190000047723636

* codex app 配置: `$HOME/.codex/.env`（仅填写在本机，不提交真实凭据）

```
http_proxy=http://127.0.0.1:7897
https_proxy=http://127.0.0.1:7897
all_proxy=socks5://127.0.0.1:7897

```
