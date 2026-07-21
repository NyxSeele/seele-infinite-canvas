#!/usr/bin/env bash
# H800 新实例一键恢复（挂好同一块 autodl-fs 后执行）
#
# 会做：
#   1. 检查文件存储 + 数据盘
#   2. （可选）FS 缺权重时 seed
#   3. 数据目录迁到 /root/autodl-tmp、extra_model_paths、MagCache、启动 ComfyUI :6006
#   4. 验收 system_stats / clip_vision / 数据盘路径
#   5. 打印在 5090 主站注册本节点的命令
#
# 用法（推荐，控制台先挂载文件存储）：
#   curl -fsSL 'https://u1066791-81ad-fb224913.bjb2.seetacloud.com:8443/h800-bootstrap/h800-new-instance.sh' | bash -s --
#
#   # 带上公网 URL（控制台 → 自定义服务 → :6006 的 https://…:8443），方便复制 5090 注册命令：
#   H800_PUBLIC_URL='https://u1066791-xxxx.westc.seetacloud.com:8443' \
#     curl -fsSL '…/h800-new-instance.sh' | bash -s --
#
# 本地：
#   bash deploy/h800-new-instance.sh
#   bash deploy/h800-new-instance.sh --seed
#   bash deploy/h800-new-instance.sh --public-url 'https://…:8443'

set -euo pipefail

FS="${AUTODL_FS:-/root/autodl-fs}"
DATA_ROOT="${AUTODL_DATA:-/root/autodl-tmp}"
COMFY_ROOT="${COMFY_ROOT:-/root/ComfyUI}"
MODELS="$FS/models"
BOOTSTRAP_BASE="${BOOTSTRAP_BASE:-https://u1066791-81ad-fb224913.bjb2.seetacloud.com:8443/h800-bootstrap}"
H800_VRAM_GB="${H800_VRAM_GB:-80}"
H800_PUBLIC_URL="${H800_PUBLIC_URL:-}"
DO_SEED=0
DO_START=1
SKIP_CHECKS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed) DO_SEED=1 ;;
    --no-start) DO_START=0 ;;
    --skip-checks) SKIP_CHECKS=1 ;;
    --public-url)
      H800_PUBLIC_URL="${2:-}"
      shift
      ;;
    --help|-h)
      sed -n '1,22p' "$0"
      exit 0
      ;;
    *)
      echo "未知参数: $1（可用 --seed --public-url URL --no-start --skip-checks）" >&2
      exit 1
      ;;
  esac
  shift
done

_resolve_script_dir() {
  if [[ -n "${BASH_SOURCE[0]:-}" && "${BASH_SOURCE[0]}" != "-" ]]; then
    (cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
    return 0
  fi
  for cand in \
    "/root/autodl-fs/bin" \
    "/root/autodl-tmp/AIStudio/deploy" \
    "/root/autodl-tmp/share/h800-bootstrap/public"
  do
    if [[ -f "$cand/h800-new-instance.sh" || -f "$cand/h800-restore-env.sh" ]]; then
      echo "$cand"
      return 0
    fi
  done
  echo "/root/autodl-fs/bin"
}
SCRIPT_DIR="$(_resolve_script_dir)"

_fetch_deploy_script() {
  local name="$1"
  local dest="$2"
  if [[ -f "$SCRIPT_DIR/$name" ]]; then
    cp -f "$SCRIPT_DIR/$name" "$dest"
    return 0
  fi
  if curl -fsSL "${BOOTSTRAP_BASE}/${name}" -o "$dest" 2>/dev/null; then
    return 0
  fi
  return 1
}

_sync_scripts_to_fs() {
  mkdir -p "$FS/bin"
  for name in \
    h800-new-instance.sh \
    h800-restore-env.sh \
    h800-seed-fs.sh \
    extra_model_paths.h800-fs.yaml
  do
    if _fetch_deploy_script "$name" "$FS/bin/$name" 2>/dev/null; then
      chmod +x "$FS/bin/$name" 2>/dev/null || true
    fi
  done
}

_need_weights=(
  "text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors"
  "text_encoders/byt5_small_glyphxl_fp16.safetensors"
  "clip_vision/sigclip_vision_patch14_384.safetensors"
)

_count_missing_weights() {
  local miss=0
  local rel
  for rel in "${_need_weights[@]}"; do
    [[ -f "$MODELS/$rel" ]] || miss=$((miss + 1))
  done
  echo "$miss"
}

_print_banner() {
  echo "=============================================="
  echo " H800 新实例一键恢复"
  echo " $(date -Is 2>/dev/null || date)"
  echo "=============================================="
}

_preflight() {
  echo "==> [0] 前置检查"
  if [[ ! -d "$FS" ]]; then
    echo "ERROR: $FS 未挂载。"
    echo "  AutoDL 控制台 → 实例 → 文件存储 → 挂载到本实例后重试。"
    exit 1
  fi
  echo "  OK   FS mounted: $FS"
  df -h "$FS" | tail -1

  if [[ ! -d "$DATA_ROOT" ]]; then
    echo "ERROR: 数据盘 $DATA_ROOT 不存在。"
    exit 1
  fi
  echo "  OK   DATA disk: $DATA_ROOT"
  df -h "$DATA_ROOT" | tail -1

  if [[ ! -d "$COMFY_ROOT" ]]; then
    echo "ERROR: $COMFY_ROOT 不存在（请使用带 ComfyUI 的镜像）。"
    exit 1
  fi
  echo "  OK   ComfyUI: $COMFY_ROOT"
}

_maybe_seed() {
  local miss
  miss="$(_count_missing_weights)"
  if [[ "$miss" -eq 0 ]]; then
    echo "==> [seed] 跳过（FS 权重齐全）"
    return 0
  fi
  echo "==> [seed] FS 缺 $miss 个 SigCLIP/共享 TE 权重"
  if [[ "$DO_SEED" -eq 1 ]]; then
    local seed_sh="$FS/bin/h800-seed-fs.sh"
    _fetch_deploy_script h800-seed-fs.sh "$seed_sh" || {
      echo "ERROR: 找不到 h800-seed-fs.sh"
      exit 1
    }
    chmod +x "$seed_sh"
    bash "$seed_sh"
    return 0
  fi
  echo "  WARN 未加 --seed，跳过下载。可执行："
  echo "    bash $FS/bin/h800-seed-fs.sh"
  echo "  或："
  echo "    curl -fsSL '${BOOTSTRAP_BASE}/h800-seed-fs.sh' | bash"
}

_run_restore() {
  local restore_sh="$FS/bin/h800-restore-env.sh"
  _fetch_deploy_script h800-restore-env.sh "$restore_sh" || {
    echo "ERROR: 找不到 h800-restore-env.sh"
    exit 1
  }
  chmod +x "$restore_sh"
  if [[ "$DO_START" -eq 1 ]]; then
    bash "$restore_sh" --start
  else
    bash "$restore_sh"
  fi
}

_verify() {
  if [[ "$SKIP_CHECKS" -eq 1 || "$DO_START" -eq 0 ]]; then
    return 0
  fi
  echo "==> [验收] ComfyUI :6006"
  local ok=1

  if curl -fsS --connect-timeout 5 --max-time 20 "http://127.0.0.1:6006/system_stats" >/dev/null; then
    echo "  OK   system_stats"
  else
    echo "  FAIL system_stats"
    ok=0
  fi

  local argv_json
  argv_json="$(curl -fsS "http://127.0.0.1:6006/system_stats" 2>/dev/null \
    | python3 -c "import sys,json;print(json.dumps(json.load(sys.stdin).get('system',{}).get('argv',[])))" \
    2>/dev/null || echo '[]')"
  if [[ "$argv_json" == *autodl-tmp/ComfyUI/output* ]]; then
    echo "  OK   output 在数据盘"
  else
    echo "  WARN argv 未指向数据盘 output: $argv_json"
    ok=0
  fi

  local clip
  clip="$(curl -fsS "http://127.0.0.1:6006/models/clip_vision" 2>/dev/null || echo '[]')"
  if [[ "$clip" == *sigclip_vision_patch14_384* ]]; then
    echo "  OK   clip_vision: sigclip"
  else
    echo "  WARN clip_vision: $clip"
  fi

  echo "  --- 数据目录 ---"
  ls -la "$COMFY_ROOT"/{output,input,user,temp} 2>/dev/null || true

  if [[ "$ok" -eq 0 ]]; then
    echo "验收未完全通过，请查看: tail -n 80 $DATA_ROOT/logs/comfyui-h800.out.log"
    return 1
  fi
  echo "  OK   验收通过"
  return 0
}

_guess_public_url() {
  if [[ -n "$H800_PUBLIC_URL" ]]; then
    echo "${H800_PUBLIC_URL%/}"
    return 0
  fi
  # AutoDL 部分镜像会在配置里写代理地址（不保证存在）
  for f in /etc/autodl.conf /root/autodl-tmp/.autodl/config.conf; do
    if [[ -f "$f" ]]; then
      local u
      u="$(grep -Eo 'https://[^[:space:]]+seetacloud\.com:8443' "$f" 2>/dev/null | head -1 || true)"
      if [[ -n "$u" ]]; then
        echo "$u"
        return 0
      fi
    fi
  done
  return 1
}

_print_5090_steps() {
  local pub="${1:-}"
  echo
  echo "=============================================="
  echo " 下一步：在 5090 主站注册此 H800 节点"
  echo "=============================================="
  echo "1. 控制台 → 自定义服务 → 复制 :6006 的公网 https 地址（:8443）"
  if [[ -z "$pub" ]]; then
    echo "2. 在 5090 执行（把 URL 换成你的）："
    echo "   bash /root/autodl-tmp/AIStudio/deploy/h800-register-5090.sh \\"
    echo "     'https://u1066791-XXXX.westc.seetacloud.com:8443' ${H800_VRAM_GB}"
    echo
    echo "   或 curl："
    echo "   curl -fsSL '${BOOTSTRAP_BASE}/h800-register-5090.sh' | bash -s -- \\"
    echo "     'https://u1066791-XXXX.westc.seetacloud.com:8443' ${H800_VRAM_GB}"
  else
    echo "2. 检测到公网 URL: $pub"
    echo "   在 5090 执行："
    echo "   bash /root/autodl-tmp/AIStudio/deploy/h800-register-5090.sh '$pub' ${H800_VRAM_GB}"
    echo
    echo "   或 curl："
    echo "   curl -fsSL '${BOOTSTRAP_BASE}/h800-register-5090.sh' | bash -s -- '$pub' ${H800_VRAM_GB}"
  fi
  echo
  echo "3. 验证：在 5090 上 curl 公网 system_stats 应返回 200"
  if [[ -n "$pub" ]]; then
    echo "   curl -sk '$pub/system_stats' | head -c 200"
  fi
  echo
  echo "本机日常重启 ComfyUI："
  echo "   bash $FS/bin/start-comfyui-h800.sh"
  echo "=============================================="
}

_write_bootstrap_record() {
  local pub="${1:-}"
  mkdir -p "$FS/bin"
  python3 - "$FS/bin/h800-last-bootstrap.json" "$pub" <<'PY' 2>/dev/null || true
import json, sys, datetime
out, pub = sys.argv[1], sys.argv[2]
rec = {
    "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "public_url": pub or None,
    "data_root": "/root/autodl-tmp",
    "comfy_port": 6006,
}
with open(out, "w", encoding="utf-8") as f:
    json.dump(rec, f, ensure_ascii=False, indent=2)
PY
}

# ── main ──
_print_banner
_preflight
_sync_scripts_to_fs
_maybe_seed
_run_restore
_verify || true
pub=""
pub="$(_guess_public_url 2>/dev/null || true)"
_write_bootstrap_record "$pub"
_print_5090_steps "$pub"
echo
echo "H800 本机恢复完成。"
