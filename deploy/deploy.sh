#!/usr/bin/env bash
# AI Studio — Docker 一键部署（Linux / macOS 服务器）
# 用法：在项目根目录执行  bash deploy/deploy.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

info()  { echo "[deploy] $*"; }
warn()  { echo "[deploy] 警告: $*" >&2; }
abort() { echo "[deploy] 错误: $*" >&2; exit 1; }

random_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 24
  else
    python3 -c "import secrets; print(secrets.token_hex(24))"
  fi
}

need_replace() {
  local val="$1"
  [[ -z "$val" || "$val" == *"change-me"* ]]
}

ensure_docker() {
  command -v docker >/dev/null 2>&1 || abort "未安装 Docker，请先安装: https://docs.docker.com/engine/install/"
  docker compose version >/dev/null 2>&1 || abort "未找到 docker compose，请安装 Docker Compose v2"
}

ensure_root_env() {
  if [[ ! -f .env ]]; then
    info "创建 .env（从 .env.example 复制）"
    cp .env.example .env
  fi
  # shellcheck disable=SC1091
  source .env

  local changed=0
  if need_replace "${POSTGRES_PASSWORD:-}"; then
    POSTGRES_PASSWORD="$(random_secret)"
    echo "POSTGRES_PASSWORD=$POSTGRES_PASSWORD" >> .env
    changed=1
    info "已自动生成 POSTGRES_PASSWORD"
  fi
  if need_replace "${REDIS_PASSWORD:-}"; then
    REDIS_PASSWORD="$(random_secret)"
    echo "REDIS_PASSWORD=$REDIS_PASSWORD" >> .env
    changed=1
    info "已自动生成 REDIS_PASSWORD"
  fi
  if [[ "$changed" -eq 1 ]]; then
    warn "请妥善保存 .env 中的数据库与 Redis 密码"
  fi
}

ensure_backend_env() {
  if [[ ! -f backend/.env ]]; then
    info "创建 backend/.env（从 backend/.env.example 复制）"
    cp backend/.env.example backend/.env
  fi

  if grep -q '^JWT_SECRET=change-me' backend/.env 2>/dev/null \
     || grep -q '^JWT_SECRET=$' backend/.env 2>/dev/null; then
    local jwt
    jwt="$(random_secret)$(random_secret)"
    if grep -q '^JWT_SECRET=' backend/.env; then
      sed -i.bak "s|^JWT_SECRET=.*|JWT_SECRET=$jwt|" backend/.env && rm -f backend/.env.bak
    else
      echo "JWT_SECRET=$jwt" >> backend/.env
    fi
    info "已自动生成 JWT_SECRET"
  fi

  if ! grep -q '^APP_ENV=production' backend/.env; then
    if grep -q '^APP_ENV=' backend/.env; then
      sed -i.bak 's|^APP_ENV=.*|APP_ENV=production|' backend/.env && rm -f backend/.env.bak
    else
      echo "APP_ENV=production" >> backend/.env
    fi
  fi

  if grep -q '^COMFYUI_URL=http://127.0.0.1' backend/.env; then
    warn "COMFYUI_URL 仍为本地地址，请在 backend/.env 改为服务器可访问的内网 ComfyUI 地址"
  fi
  if grep -q '^DASHSCOPE_API_KEY=$' backend/.env || ! grep -q '^DASHSCOPE_API_KEY=' backend/.env; then
    warn "请在 backend/.env 填写 DASHSCOPE_API_KEY（文本生成需要）"
  fi
}

main() {
  info "AI Studio Docker 一键部署"
  ensure_docker
  ensure_root_env
  ensure_backend_env

  info "构建并启动容器（postgres + redis + backend + web）..."
  docker compose up -d --build

  local port="${HTTP_PORT:-80}"
  info "等待服务就绪..."
  sleep 5

  if curl -fsS "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
    info "健康检查通过"
  else
    warn "健康检查暂未通过，可稍后执行: curl http://127.0.0.1:${port}/health"
    warn "查看日志: docker compose logs -f backend"
  fi

  echo ""
  info "部署完成"
  echo "  访问地址: http://<服务器IP>:${port}"
  echo "  健康检查: http://<服务器IP>:${port}/health"
  echo "  查看状态: docker compose ps"
  echo "  查看日志: docker compose logs -f"
  echo ""
  warn "ComfyUI 未包含在 Compose 中，需单独部署并在 backend/.env 配置 COMFYUI_URL"
}

main "$@"
