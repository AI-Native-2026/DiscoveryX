#!/usr/bin/env bash
# DiscoveryX — Ubuntu bootstrap (idempotent)
# Installs: base tooling, uv + Python 3.11, Docker, Node 20, CJK fonts,
#           CN mirrors, 8G swap, project directories.
set -uo pipefail

LOG_PREFIX="[bootstrap]"
log() { echo "$LOG_PREFIX $*"; }
have() { command -v "$1" >/dev/null 2>&1; }

if ! sudo -n true 2>/dev/null; then
  log "ERROR: passwordless sudo not available"; exit 1
fi

export DEBIAN_FRONTEND=noninteractive

# ---------------------------------------------------------------- 1. base pkgs
log "apt update + base packages"
sudo apt-get update -y -qq
sudo apt-get install -y -qq \
  ca-certificates curl wget git unzip zip jq gnupg lsb-release \
  build-essential pkg-config software-properties-common \
  libgl1 libxrender1 libxext6 libsm6 libgomp1 \
  fonts-noto-cjk fontconfig \
  rsync htop tree tmux

# ---------------------------------------------------------------- 2. swap 8G
CUR_SWAP=$(free -m | awk '/Swap:/{print $2}')
if [ "${CUR_SWAP:-0}" -lt 7000 ]; then
  log "enlarging swap to 8G (current ${CUR_SWAP}MB)"
  sudo swapoff /swapfile 2>/dev/null || true
  sudo fallocate -l 8G /swapfile 2>/dev/null || sudo dd if=/dev/zero of=/swapfile bs=1M count=8192 status=none
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null
  sudo swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  sudo sysctl -w vm.swappiness=10 >/dev/null
else
  log "swap already >= 7G, skipping"
fi

# ---------------------------------------------------------------- 3. uv + py3.11
if ! have uv; then
  log "installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
if have uv; then
  log "uv $(uv --version)"
  # make uv available on the default PATH (persistent)
  sudo ln -sf "$HOME/.local/bin/uv" /usr/local/bin/uv
  sudo ln -sf "$HOME/.local/bin/uvx" /usr/local/bin/uvx
  grep -q '.local/bin' "$HOME/.bashrc" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
  grep -q '.local/bin' "$HOME/.profile" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.profile"
  log "installing Python 3.11 via uv"
  uv python install 3.11 || log "WARN: uv python install 3.11 failed (will retry later)"
fi

# ---------------------------------------------------------------- 4. docker
if ! have docker; then
  log "installing Docker Engine"
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER" || true
else
  log "docker already installed: $(docker --version 2>/dev/null || echo '?')"
fi
sudo systemctl enable --now docker >/dev/null 2>&1 || true
# docker compose plugin check
sudo docker compose version >/dev/null 2>&1 && log "docker compose OK" || log "WARN: docker compose missing"

# ---------------------------------------------------------------- 5. node 20
if ! have node || [ "$(node -v 2>/dev/null | sed 's/v\([0-9]*\).*/\1/')" -lt 20 ] 2>/dev/null; then
  log "installing Node.js 20 LTS"
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - >/dev/null
  sudo apt-get install -y -qq nodejs
else
  log "node already installed: $(node -v)"
fi
have pnpm || { log "installing pnpm"; sudo npm install -g pnpm >/dev/null 2>&1 || true; }

# ---------------------------------------------------------------- 6. mirrors
log "configuring CN mirrors"
# pip
mkdir -p "$HOME/.pip"
cat > "$HOME/.pip/pip.conf" <<'EOF'
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
trusted-host = pypi.tuna.tsinghua.edu.cn
timeout = 60
EOF
# uv
mkdir -p "$HOME/.config/uv"
cat > "$HOME/.config/uv/uv.toml" <<'EOF'
[[index]]
url = "https://pypi.tuna.tsinghua.edu.cn/simple"
default = true
EOF
# npm
npm config set registry https://registry.npmmirror.com >/dev/null 2>&1 || true
# docker registry mirror (best-effort)
if [ ! -f /etc/docker/daemon.json ]; then
  echo '{"registry-mirrors":["https://docker.m.daocloud.io"]}' | sudo tee /etc/docker/daemon.json >/dev/null
  sudo systemctl restart docker >/dev/null 2>&1 || true
fi

# ---------------------------------------------------------------- 7. dirs
log "creating project directories"
mkdir -p "$HOME/discoveryx" "$HOME/data" "$HOME/models" "$HOME/reports" "$HOME/.config/discoveryx"
chmod 700 "$HOME/.config/discoveryx"

# ---------------------------------------------------------------- 8. summary
echo
log "================ SUMMARY ================"
printf '  os      : %s\n' "$(lsb_release -ds 2>/dev/null || echo '?')"
printf '  cpus    : %s\n' "$(nproc)"
printf '  mem     : %s\n' "$(free -h | awk '/Mem:/{print $2}')"
printf '  swap    : %s\n' "$(free -h | awk '/Swap:/{print $2}')"
printf '  disk    : %s free\n' "$(df -h / | awk 'NR==2{print $4}')"
printf '  python  : %s\n' "$(python3 --version 2>&1)"
printf '  uv      : %s\n' "$(have uv && uv --version || echo 'MISSING')"
printf '  node    : %s\n' "$(have node && node -v || echo 'MISSING')"
printf '  pnpm    : %s\n' "$(have pnpm && pnpm -v || echo 'MISSING')"
printf '  docker  : %s\n' "$(have docker && docker --version || echo 'MISSING')"
printf '  fonts   : %s\n' "$(fc-list :lang=zh 2>/dev/null | wc -l) CJK faces"
log "========================================="
log "NOTE: docker group requires a new login to take effect."
