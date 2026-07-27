#!/bin/bash
set -Eeuo pipefail

export DEBIAN_FRONTEND=noninteractive
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

apt-get update
apt-get upgrade -y

apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  gnupg \
  unzip \
  jq \
  nginx

usermod -a -G docker ubuntu || true

systemctl enable nginx
systemctl start nginx

install_aws_cli() {
  echo "Checking for existing AWS CLI installation..."

  if command -v aws >/dev/null 2>&1; then
    echo "AWS CLI already installed: $(aws --version)"
    return 0
  fi

  local arch
  arch="$(uname -m)"
  local aws_arch

  case "$arch" in
    x86_64)
      aws_arch="x86_64"
      ;;
    aarch64|arm64)
      aws_arch="aarch64"
      ;;
    *)
      echo "Unsupported architecture for AWS CLI installation: $arch" >&2
      return 1
      ;;
  esac

  echo "Detected architecture: $arch (AWS CLI arch: $aws_arch)"

  local tmp_dir
  tmp_dir="$(mktemp -d)"

  curl --fail --silent --show-error --location \
    "https://awscli.amazonaws.com/awscli-exe-linux-${aws_arch}.zip" \
    --output "${tmp_dir}/awscliv2.zip"

  unzip -q "${tmp_dir}/awscliv2.zip" -d "$tmp_dir"
  "${tmp_dir}/aws/install" --install-dir /usr/local/aws-cli --bin-dir /usr/local/bin

  rm -rf "$tmp_dir"

  echo "AWS CLI installed: $(aws --version)"
}

install_docker() {
  if command -v docker >/dev/null 2>&1; then
    echo "Docker already installed: $(docker --version)"
    systemctl enable docker
    systemctl start docker
    return 0
  fi

  echo "Installing Docker Engine from the official Docker APT repository..."

  install -m 0755 -d /etc/apt/keyrings

  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg

  chmod a+r /etc/apt/keyrings/docker.gpg

  . /etc/os-release

  local docker_arch
  docker_arch="$(dpkg --print-architecture)"

  echo \
    "deb [arch=${docker_arch} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    | tee /etc/apt/sources.list.d/docker.list >/dev/null

  apt-get update

  apt-get install -y --no-install-recommends \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin

  systemctl enable docker
  systemctl start docker

  echo "Docker installed: $(docker --version)"
}

install_aws_cli
install_docker
