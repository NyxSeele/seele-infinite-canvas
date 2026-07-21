#!/usr/bin/env bash
# 5090 主站：把新 H800 公网 URL 写入 COMFYUI_NODES 并重启 backend
#
# 用法：
#   bash deploy/h800-register-5090.sh 'https://u1066791-xxxx.westc.seetacloud.com:8443' [vram_gb]
#
#   curl -fsSL 'https://u1066791-81ad-fb224913.bjb2.seetacloud.com:8443/h800-bootstrap/h800-register-5090.sh' | \
#     bash -s -- 'https://u1066791-xxxx.westc.seetacloud.com:8443' 80

set -euo pipefail

H800_URL="${1:-}"
H800_VRAM="${2:-80}"
AISTUDIO="${AISTUDIO_ROOT:-/root/autodl-tmp/AIStudio}"
ENV_FILE="$AISTUDIO/backend/.env"
SUP_DEPLOY="$AISTUDIO/deploy/supervisor-autodl.conf"
SUP_LIVE="/etc/supervisor/conf.d/aistudio.conf"
SUPCTL="/usr/bin/supervisorctl"
SUPCONF="/etc/supervisor/supervisord.conf"

if [[ -z "$H800_URL" ]]; then
  echo "用法: $0 'https://u1066791-xxxx.westc.seetacloud.com:8443' [vram_gb]" >&2
  exit 1
fi
H800_URL="${H800_URL%/}"
if [[ ! "$H800_URL" =~ ^https:// ]]; then
  echo "ERROR: H800 URL 须为 https://…（AutoDL 自定义服务 :6006 → :8443）" >&2
  exit 1
fi

LOCAL_NODES="${LOCAL_COMFYUI_NODES:-http://127.0.0.1:8000|32}"
NEW_NODES="${LOCAL_NODES},${H800_URL}|${H800_VRAM}"

_rebuild_nodes() {
  local current="$1"
  local kept=()
  local part url
  IFS=',' read -ra parts <<<"$current"
  for part in "${parts[@]}"; do
    part="$(echo "$part" | xargs)"
    [[ -z "$part" ]] && continue
    url="${part%%|*}"
    if [[ "$url" == http://127.0.0.1:* ]]; then
      kept+=("$part")
    fi
  done
  if [[ ${#kept[@]} -eq 0 ]]; then
    kept+=("$LOCAL_NODES")
  fi
  kept+=("${H800_URL}|${H800_VRAM}")
  local IFS=','; echo "${kept[*]}"
}

_update_env_line() {
  local file="$1"
  local key="$2"
  local value="$3"
  [[ -f "$file" ]] || return 0
  if grep -q "^${key}=" "$file"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$file"
  else
    echo "${key}=${value}" >>"$file"
  fi
}

_update_supervisor_comfy_nodes() {
  local file="$1"
  local nodes="$2"
  [[ -f "$file" ]] || return 0
  # 只改 aistudio-backend 段的 COMFYUI_NODES=，不动 nginx/cloudflared
  python3 - "$file" "$nodes" <<'PY'
import re, sys
path, nodes = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
pat = re.compile(
    r'(^\[program:aistudio-backend\][\s\S]*?^environment=.*?COMFYUI_NODES=")([^"]*)(")',
    re.MULTILINE,
)
new, n = pat.subn(rf"\g<1>{nodes}\g<3>", text, count=1)
if n != 1:
    raise SystemExit(f"ERROR: 未在 {path} 找到 [program:aistudio-backend] 的 COMFYUI_NODES")
open(path, "w", encoding="utf-8").write(new)
PY
}

echo "==> 注册 H800 节点"
echo "    URL : $H800_URL"
echo "    VRAM: ${H800_VRAM}GB"

CURRENT_NODES="$(grep -E '^COMFYUI_NODES=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || echo "$LOCAL_NODES")"
NEW_NODES="$(_rebuild_nodes "$CURRENT_NODES")"
echo "    COMFYUI_NODES=$NEW_NODES"

_update_env_line "$ENV_FILE" "COMFYUI_NODES" "$NEW_NODES"
_update_supervisor_comfy_nodes "$SUP_DEPLOY" "$NEW_NODES"
if [[ -f "$SUP_LIVE" && "$SUP_LIVE" != "$SUP_DEPLOY" ]]; then
  _update_supervisor_comfy_nodes "$SUP_LIVE" "$NEW_NODES"
fi

echo "==> 探测 H800 公网"
if curl -fsSk --connect-timeout 10 --max-time 30 "${H800_URL}/system_stats" >/dev/null; then
  echo "  OK   ${H800_URL}/system_stats"
else
  echo "  WARN 公网暂不可达（可能 ComfyUI 未起或 URL 填错），仍已写入配置"
fi

if [[ -x "$SUPCTL" && -f "$SUPCONF" ]]; then
  echo "==> 重启 backend"
  "$SUPCTL" -c "$SUPCONF" reread
  "$SUPCTL" -c "$SUPCONF" update
  "$SUPCTL" -c "$SUPCONF" restart aistudio-backend
  sleep 2
  if curl -fsS --connect-timeout 5 --max-time 15 "http://127.0.0.1:7788/api/health" >/dev/null; then
    echo "  OK   backend /api/health"
  else
    echo "  WARN backend health 未立即 200，请: tail $AISTUDIO/../logs/backend.err.log"
  fi
else
  echo "WARN 未找到 supervisorctl，请手动重启 backend 使 COMFYUI_NODES 生效"
fi

echo
echo "完成。当前 COMFYUI_NODES=$NEW_NODES"
