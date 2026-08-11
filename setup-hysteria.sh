#!/bin/bash
set -e

# 注意，要赋予此脚本执行权限：chmod +x setup-hysteria.sh
# 然后在执行：./setup-hysteria.sh

# ==================== 配置变量（按需修改） ====================
PASSWORD="your password"
LISTEN_PORT="443"
MASQUERADE_URL="https://www.bing.com"
CERT_DAYS="365"
HY_VERSION="v2.12.1"
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   Hysteria ${HY_VERSION} VPN 服务器安装   ${NC}"
echo -e "${GREEN}          Ubuntu 22.04 专用           ${NC}"
echo -e "${GREEN}========================================${NC}"

if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}错误：请使用 root 用户执行此脚本 (sudo ./script.sh)${NC}"
    exit 1
fi

echo -e "${YELLOW}[1/7] 更新系统并安装依赖...${NC}"
apt update -qq
apt install -y -qq wget curl openssl ufw

echo -e "${YELLOW}[2/7] 创建目录结构...${NC}"
mkdir -p /etc/hysteria /etc/ssl/hysteria

echo -e "${YELLOW}[3/7] 生成 SSL 证书（有效期${CERT_DAYS}天）...${NC}"
openssl req -x509 -newkey rsa:4096 -nodes \
    -keyout /etc/ssl/hysteria/key.pem \
    -out /etc/ssl/hysteria/cert.pem \
    -days ${CERT_DAYS} \
    -subj "/CN=www.bing.com"

chmod 644 /etc/ssl/hysteria/key.pem
chmod 644 /etc/ssl/hysteria/cert.pem
echo -e "${GREEN}✓ 证书权限已设置为 644${NC}"

echo -e "${YELLOW}[4/7] 创建配置文件 /etc/hysteria/config.yaml ...${NC}"
cat > /etc/hysteria/config.yaml << YAML
listen: :${LISTEN_PORT}

tls:
  cert: /etc/ssl/hysteria/cert.pem
  key: /etc/ssl/hysteria/key.pem

auth:
  type: password
  password: ${PASSWORD}

masquerade:
  type: proxy
  proxy:
    url: ${MASQUERADE_URL}
    rewriteHost: true

quic:
  initStreamReceiveWindow: 8388608
  maxStreamReceiveWindow: 8388608
  initConnReceiveWindow: 20971520
  maxConnReceiveWindow: 20971520
YAML

echo -e "${YELLOW}[5/7] 使用官方脚本安装 Hysteria ${HY_VERSION} ...${NC}"
bash <(curl -fsSL https://get.hy2.sh/) --version ${HY_VERSION}

echo -e "${YELLOW}[6/7] 配置防火墙 (ufw)...${NC}"
ufw allow ${LISTEN_PORT}/udp
echo -e "${GREEN}已允许 UDP ${LISTEN_PORT} 端口${NC}"

echo -e "${YELLOW}[7/7] 重启 Hysteria 服务并应用配置...${NC}"
systemctl stop hysteria-server || true
systemctl start hysteria-server
systemctl enable hysteria-server
sleep 3

if systemctl is-active --quiet hysteria-server; then
    SERVER_IP=$(curl -s ifconfig.me)
    echo -e "\n${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ Hysteria 部署成功！${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo -e "${YELLOW}服务状态：${NC}$(systemctl status hysteria-server --no-pager | grep "Active:")"
    echo -e "${YELLOW}端口监听：${NC}"
    ss -tulnp | grep ":${LISTEN_PORT}" | grep -v grep || echo "  等待端口监听..."
    echo ""
    echo -e "${GREEN}客户端连接信息：${NC}"
    echo -e "  服务器地址：${SERVER_IP}:${LISTEN_PORT}"
    echo -e "  密码：${PASSWORD}"
    echo -e "  协议：Hysteria ${HY_VERSION}"
    echo ""
    echo -e "${YELLOW}常用管理命令：${NC}"
    echo -e "  查看状态: systemctl status hysteria-server"
    echo -e "  查看日志: journalctl -u hysteria-server -f"
    echo -e "  重启服务: systemctl restart hysteria-server"
    echo -e "  停止服务: systemctl stop hysteria-server"
else
    echo -e "${RED}服务启动失败！查看错误日志：${NC}"
    journalctl -u hysteria-server -n 20 --no-pager
    exit 1
fi
