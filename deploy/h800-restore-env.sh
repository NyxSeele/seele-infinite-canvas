#!/usr/bin/env bash
# H800：从 autodl-fs 一键恢复环境（新实例每次跑这个，不重新下大模型）
#
# 前置：
#   1. AutoDL 把「同一块」文件存储挂到 /root/autodl-fs
#   2. 曾经在任一台 H800 上跑过一次 h800-seed-fs.sh（或已有 Wan 权重在 FS）
#
# 本脚本会做：
#   - ComfyUI 输出/输入/user/temp/缓存/日志 → /root/autodl-tmp（数据盘）
#   - MagCache：FS → custom_nodes 软链
#   - extra_model_paths → 指向 autodl-fs
#   - （可选）启动 ComfyUI :6006
#
# 用法：
#   bash deploy/h800-restore-env.sh
#   bash deploy/h800-restore-env.sh --start
#   curl -fsSL …/h800-bootstrap/h800-restore-env.sh | bash -s -- --start
#
# 新实例推荐直接用：deploy/h800-new-instance.sh（含验收 + 5090 注册说明）

set -euo pipefail

FS="${AUTODL_FS:-/root/autodl-fs}"
DATA_ROOT="${AUTODL_DATA:-/root/autodl-tmp}"
COMFY_ROOT="${COMFY_ROOT:-/root/ComfyUI}"
COMFY_DATA="$DATA_ROOT/ComfyUI"
PLUGINS="$FS/comfy-plugins"
MODELS="$FS/models"
START=0
for arg in "$@"; do
  case "$arg" in
    --start) START=1 ;;
  esac
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
    if [[ -f "$cand/h800-restore-env.sh" ]]; then
      echo "$cand"
      return 0
    fi
  done
  echo "/root/autodl-fs/bin"
}
SCRIPT_DIR="$(_resolve_script_dir)"

_write_start_script() {
  local start_script="$FS/bin/start-comfyui-h800.sh"
  cat >"$start_script" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

FS="${AUTODL_FS:-/root/autodl-fs}"
DATA_ROOT="${AUTODL_DATA:-/root/autodl-tmp}"
COMFY_ROOT="${COMFY_ROOT:-/root/ComfyUI}"
COMFY_DATA="$DATA_ROOT/ComfyUI"
COMFY_DB="$COMFY_DATA/user/comfyui_h800.db"
COMFY_LOG="$DATA_ROOT/logs/comfyui-h800.out.log"

comfy_db_url() {
  # 绝对路径：sqlite:////root/...（4 个斜杠）
  printf 'sqlite:////%s' "${1#/}"
}

mkdir -p "$DATA_ROOT/logs" "$COMFY_DATA"/{output,input,user,temp} \
  "$DATA_ROOT/.cache/huggingface/hub" "$DATA_ROOT/.cache/torch" "$DATA_ROOT/.cache/tmp"

PYTHON=""
for cand in \
  "$COMFY_ROOT/.venv/bin/python" \
  "/root/autodl-tmp/AIStudio/backend/.venv/bin/python" \
  "$(command -v python3 2>/dev/null || true)" \
  "$(command -v python 2>/dev/null || true)"
do
  [[ -n "$cand" && -x "$cand" ]] && PYTHON="$cand" && break
done
if [[ -z "$PYTHON" ]]; then
  echo "ERROR: 找不到 python"
  exit 1
fi

stop_comfy() {
  pkill -f '[m]ain.py --listen 0.0.0.0 --port 6006' 2>/dev/null || true
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if command -v ss >/dev/null 2>&1; then
      ss -ltn 2>/dev/null | grep -q ':6006 ' || return 0
    else
      sleep 1
      return 0
    fi
    sleep 1
  done
  command -v fuser >/dev/null 2>&1 && fuser -k 6006/tcp 2>/dev/null || true
  sleep 1
}

wait_comfy() {
  for _ in $(seq 1 45); do
    if curl -fsS --connect-timeout 2 --max-time 5 "http://127.0.0.1:6006/system_stats" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

stop_comfy
cd "$COMFY_ROOT"

export HF_HOME="$DATA_ROOT/.cache/huggingface"
export HF_HUB_CACHE="$DATA_ROOT/.cache/huggingface/hub"
export TRANSFORMERS_CACHE="$DATA_ROOT/.cache/huggingface"
export TORCH_HOME="$DATA_ROOT/.cache/torch"
export XDG_CACHE_HOME="$DATA_ROOT/.cache"
export TMPDIR="$DATA_ROOT/.cache/tmp"

DB_URL="$(comfy_db_url "$COMFY_DB")"
: >"$COMFY_LOG"

echo "==> 启动 ComfyUI :6006"
echo "    python=$PYTHON"
echo "    db=$DB_URL"
echo "    output=$COMFY_DATA/output"

if command -v setsid >/dev/null 2>&1; then
  setsid "$PYTHON" -u main.py --listen 0.0.0.0 --port 6006 \
    --output-directory "$COMFY_DATA/output" \
    --input-directory "$COMFY_DATA/input" \
    --user-directory "$COMFY_DATA/user" \
    --temp-directory "$COMFY_DATA/temp" \
    --database-url "$DB_URL" \
    >>"$COMFY_LOG" 2>&1 < /dev/null &
else
  nohup "$PYTHON" -u main.py --listen 0.0.0.0 --port 6006 \
    --output-directory "$COMFY_DATA/output" \
    --input-directory "$COMFY_DATA/input" \
    --user-directory "$COMFY_DATA/user" \
    --temp-directory "$COMFY_DATA/temp" \
    --database-url "$DB_URL" \
    >>"$COMFY_LOG" 2>&1 < /dev/null &
fi

COMFY_PID=$!
echo "PID $COMFY_PID  log=$COMFY_LOG"

if wait_comfy; then
  curl -sS "http://127.0.0.1:6006/system_stats" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print('argv:',d.get('system',{}).get('argv',[]))"
  exit 0
fi

if kill -0 "$COMFY_PID" 2>/dev/null; then
  echo "WARN ComfyUI 进程仍在但 HTTP 未就绪，请 tail -f $COMFY_LOG"
  exit 1
fi

echo "ERROR ComfyUI 启动失败（PID $COMFY_PID 已退出）。最近日志："
tail -n 40 "$COMFY_LOG" || true
exit 1
EOF
  chmod +x "$start_script"
  echo "OK wrote $start_script"
}

if [[ ! -d "$FS" ]]; then
  echo "ERROR: $FS 未挂载。控制台 → 实例 → 文件存储 → 挂载到本实例后再跑。"
  exit 1
fi
if [[ ! -d "$COMFY_ROOT" ]]; then
  echo "ERROR: $COMFY_ROOT 不存在（请用带 ComfyUI 的镜像）。"
  exit 1
fi
if [[ ! -d "$DATA_ROOT" ]]; then
  echo "ERROR: 数据盘 $DATA_ROOT 不存在。请在控制台扩容/挂载数据盘后再跑。"
  exit 1
fi

echo "==> FS: $FS"
df -h "$FS" | tail -1
echo "==> DATA: $DATA_ROOT"
df -h "$DATA_ROOT" | tail -1

_migrate_comfy_subdir() {
  local name="$1"
  local src="$COMFY_ROOT/$name"
  local dst="$COMFY_DATA/$name"

  mkdir -p "$dst"

  if [[ -L "$src" ]]; then
    local target
    target="$(readlink -f "$src" 2>/dev/null || readlink "$src")"
    if [[ "$target" == "$dst" || "$target" == "$dst/"* ]]; then
      echo "  OK   $src → data disk"
      return 0
    fi
    echo "  RELINK $src (was $target)"
    rm -f "$src"
  elif [[ -d "$src" ]]; then
    if [[ -n "$(ls -A "$src" 2>/dev/null || true)" ]]; then
      echo "  MOVE $src/* → $dst/"
      if command -v rsync >/dev/null 2>&1; then
        rsync -a "$src/" "$dst/"
      else
        cp -a "$src/." "$dst/"
      fi
    fi
    rm -rf "$src"
  fi

  ln -sfn "$dst" "$src"
  echo "  OK   $src → $dst"
}

echo "==> [1/4] ComfyUI 数据目录 → 数据盘 ($COMFY_DATA)"
mkdir -p \
  "$DATA_ROOT/logs" \
  "$DATA_ROOT/.cache/huggingface/hub" \
  "$DATA_ROOT/.cache/torch" \
  "$DATA_ROOT/.cache/tmp" \
  "$COMFY_DATA"/{output,input,user,temp}

for sub in output input user temp; do
  _migrate_comfy_subdir "$sub"
done

LOCAL_MODELS="$COMFY_ROOT/models"
if [[ -d "$MODELS" ]]; then
  if [[ -L "$LOCAL_MODELS" ]]; then
    echo "  OK   models → $(readlink -f "$LOCAL_MODELS")"
  elif [[ ! -e "$LOCAL_MODELS" ]] || [[ -z "$(ls -A "$LOCAL_MODELS" 2>/dev/null || true)" ]]; then
    rm -rf "$LOCAL_MODELS" 2>/dev/null || true
    ln -sfn "$MODELS" "$LOCAL_MODELS"
    echo "  OK   models → $MODELS"
  else
    echo "  WARN models 目录有本地文件，未整体替换；大权重仍走 extra_model_paths → $MODELS"
    if [[ -f "$MODELS/clip_vision/sigclip_vision_patch14_384.safetensors" ]]; then
      mkdir -p "$LOCAL_MODELS/clip_vision"
      ln -sfn "$MODELS/clip_vision/sigclip_vision_patch14_384.safetensors" \
        "$LOCAL_MODELS/clip_vision/sigclip_vision_patch14_384.safetensors"
      echo "  OK   clip_vision/sigclip → FS"
    fi
  fi
fi

echo "==> [2/4] MagCache symlink"
MAG_SRC="$PLUGINS/ComfyUI-MagCache"
MAG_DST="$COMFY_ROOT/custom_nodes/ComfyUI-MagCache"
mkdir -p "$COMFY_ROOT/custom_nodes"
if [[ -f "$MAG_SRC/nodes.py" ]]; then
  rm -rf "$MAG_DST"
  ln -sfn "$MAG_SRC" "$MAG_DST"
  echo "OK $MAG_DST → $MAG_SRC"
elif [[ -f "$MAG_DST/nodes.py" ]]; then
  echo "OK MagCache 已在本机 $MAG_DST（FS 无副本，保留本地）"
else
  echo "WARN MagCache 不在 FS（$MAG_SRC）。可先跑 h800-seed-fs.sh，或暂时依赖 EasyCache。"
fi

echo "==> [3/4] extra_model_paths.yaml → autodl-fs"
YAML_SRC=""
for cand in \
  "$SCRIPT_DIR/extra_model_paths.h800-fs.yaml" \
  "$FS/bin/extra_model_paths.h800-fs.yaml" \
  "$COMFY_ROOT/../autodl-tmp/AIStudio/deploy/extra_model_paths.h800-fs.yaml"
do
  if [[ -f "$cand" ]]; then
    YAML_SRC="$cand"
    break
  fi
done
if [[ -z "$YAML_SRC" ]]; then
  cat > "$COMFY_ROOT/extra_model_paths.yaml" <<'YAML'
autodl_fs:
    base_path: /root/autodl-fs/models/
    checkpoints: checkpoints/
    diffusion_models: diffusion_models/
    vae: vae/
    text_encoders: text_encoders/
    loras: loras/
    clip: clip/
    clip_vision: clip_vision/
    unet: unet/
    SEEDVR2: SEEDVR2/
YAML
  echo "OK wrote embedded extra_model_paths.yaml"
else
  cp -f "$YAML_SRC" "$COMFY_ROOT/extra_model_paths.yaml"
  echo "OK cp $YAML_SRC"
fi

echo "==> [4/4] 快速核对权重（缺的只提示，不自动下）"
need=(
  "text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors"
  "text_encoders/byt5_small_glyphxl_fp16.safetensors"
  "clip_vision/sigclip_vision_patch14_384.safetensors"
)
missing=0
for rel in "${need[@]}"; do
  if [[ -f "$MODELS/$rel" ]]; then
    echo "  OK   $rel"
  else
    echo "  MISS $rel"
    missing=1
  fi
done
if [[ "$missing" -eq 1 ]]; then
  echo
  echo "部分权重缺失。若这是第一次用这块 FS，请跑："
  echo "  bash $SCRIPT_DIR/h800-seed-fs.sh"
  echo "（Wan 等其它权重仍用你们现有的 restore/pull 脚本种进 FS）"
fi

mkdir -p "$FS/bin"
cp -f "$0" "$FS/bin/h800-restore-env.sh" 2>/dev/null || true
chmod +x "$FS/bin/h800-restore-env.sh" 2>/dev/null || true
if [[ -f "$SCRIPT_DIR/h800-seed-fs.sh" ]]; then
  cp -f "$SCRIPT_DIR/h800-seed-fs.sh" "$FS/bin/h800-seed-fs.sh"
  chmod +x "$FS/bin/h800-seed-fs.sh"
fi
if [[ -f "$SCRIPT_DIR/extra_model_paths.h800-fs.yaml" ]]; then
  cp -f "$SCRIPT_DIR/extra_model_paths.h800-fs.yaml" "$FS/bin/"
fi

COMFY_DB="$COMFY_DATA/user/comfyui_h800.db"
COMFY_LOG="$DATA_ROOT/logs/comfyui-h800.out.log"

_write_start_script

if [[ "$START" -eq 1 ]]; then
  echo "==> 启动 ComfyUI :6006（数据盘 output/input/user/temp + cache）"
  if bash "$FS/bin/start-comfyui-h800.sh"; then
    echo "OK ComfyUI 已用数据盘目录启动"
  else
    echo "启动失败。可查看: tail -n 60 $COMFY_LOG"
    echo "手动重试: bash $FS/bin/start-comfyui-h800.sh"
    exit 1
  fi
else
  echo
  echo "RESTORE DONE（未自动启动）。启动："
  echo "  bash $FS/bin/start-comfyui-h800.sh"
  echo "  # 或："
  echo "  bash $FS/bin/h800-restore-env.sh --start"
fi
