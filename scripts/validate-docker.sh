#!/usr/bin/env bash
# scripts/validate-docker.sh
# 校验 Dockerfile / docker-compose.yml 语法（不实际构建）。
# - 优先使用 hadolint（hadolint/hadolint 容器镜像）做 Dockerfile 静态检查
# - 优先使用 docker compose config 做 compose 配置语法检查
# - 如未安装 docker，将降级为"文件存在性 + 基础结构检查"
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DOCKERFILE="$REPO_ROOT/Dockerfile"
COMPOSE="$REPO_ROOT/docker-compose.yml"
ENV_EXAMPLE="$REPO_ROOT/.env.example"

fail=0

echo "== 文件存在性检查 =="
for f in "$DOCKERFILE" "$COMPOSE" "$ENV_EXAMPLE"; do
  if [ -f "$f" ]; then
    echo "  ✓ $f"
  else
    echo "  ✗ MISSING: $f"
    fail=1
  fi
done
[ $fail -eq 0 ] || exit 1

echo
echo "== Dockerfile 基础结构检查 =="
grep -qE '^FROM .+ AS frontend-builder' "$DOCKERFILE" && echo "  ✓ multi-stage frontend builder" \
  || { echo "  ✗ missing frontend-builder stage"; fail=1; }
grep -qE '^FROM python:3\.12-slim' "$DOCKERFILE" && echo "  ✓ python 3.12-slim base" \
  || { echo "  ✗ missing python:3.12-slim base"; fail=1; }
grep -qE 'apt-get install -y --no-install-recommends' "$DOCKERFILE" && echo "  ✓ ffmpeg 安装" \
  || { echo "  ✗ 未使用 --no-install-recommends 安装 ffmpeg"; fail=1; }
grep -qE '^HEALTHCHECK ' "$DOCKERFILE" && echo "  ✓ HEALTHCHECK 已声明" \
  || { echo "  ✗ missing HEALTHCHECK"; fail=1; }
grep -qE 'EXPOSE 8000' "$DOCKERFILE" && echo "  ✓ EXPOSE 8000" \
  || { echo "  ✗ missing EXPOSE 8000"; fail=1; }
grep -qE 'CMD \["uvicorn"' "$DOCKERFILE" && echo "  ✓ uvicorn 启动命令" \
  || { echo "  ✗ missing uvicorn CMD"; fail=1; }

echo
echo "== docker-compose.yml 基础结构检查 =="
grep -qE '^services:' "$COMPOSE" && echo "  ✓ services 段" \
  || { echo "  ✗ missing services"; fail=1; }
grep -qE 'tubehub:' "$COMPOSE" && echo "  ✓ tubehub 服务" \
  || { echo "  ✗ missing tubehub service"; fail=1; }
grep -qE '8000:8000' "$COMPOSE" && echo "  ✓ 端口映射 8000:8000" \
  || { echo "  ✗ missing 8000:8000 port mapping"; fail=1; }
grep -qE 'healthcheck:' "$COMPOSE" && echo "  ✓ healthcheck 段" \
  || { echo "  ✗ missing healthcheck"; fail=1; }

# 严禁把真实密钥写进文件
if grep -qE 'SECRET_KEY=[A-Za-z0-9]{16,}' "$COMPOSE" "$DOCKERFILE" "$ENV_EXAMPLE" 2>/dev/null; then
  # 仅 .env.example 中允许占位符；其它文件命中则视为风险
  if grep -E 'SECRET_KEY=[A-Za-z0-9]{16,}' "$DOCKERFILE" "$COMPOSE" 2>/dev/null; then
    echo "  ✗ 检测到硬编码的 SECRET_KEY"
    fail=1
  else
    echo "  ✓ 仅 .env.example 含占位符密钥"
  fi
fi

echo
echo "== 工具层校验 =="
if command -v hadolint >/dev/null 2>&1; then
  echo "  • hadolint 静态检查..."
  hadolint "$DOCKERFILE" && echo "  ✓ hadolint PASS" || { echo "  ✗ hadolint FAIL"; fail=1; }
elif command -v docker >/dev/null 2>&1; then
  if docker run --rm -i hadolint/hadolint < "$DOCKERFILE" 2>/dev/null; then
    echo "  ✓ hadolint (docker) PASS"
  else
    echo "  ! hadolint (docker) 不可用或检查失败，跳过"
  fi
else
  echo "  ! 未检测到 hadolint/docker，跳过深度静态检查"
fi

if command -v docker >/dev/null 2>&1; then
  if docker compose -f "$COMPOSE" config >/dev/null 2>&1; then
    echo "  ✓ docker compose config PASS"
  else
    echo "  ! docker compose config 不可用（可能缺少 .env），跳过"
  fi
else
  echo "  ! 未检测到 docker，跳过 compose config 校验"
fi

echo
if [ $fail -eq 0 ]; then
  echo "✅ 全部校验通过"
  exit 0
else
  echo "❌ 校验未通过"
  exit 1
fi
