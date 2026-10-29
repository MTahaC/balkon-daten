#!/usr/bin/env bash
# Install the pipeline toolchain on Ubuntu (WSL2 or GitHub Actions):
#   - system packages needed to build tippecanoe
#   - tippecanoe (built from source, pinned commit)
#   - pmtiles CLI (prebuilt release binary, SHA-256 verified)
#   - a Python venv in pipeline/.venv with requirements.txt (hash-checked)
#
# Usage: pipeline/setup.sh            (tools go to ~/.local/bin)
#        PREFIX=/opt/x pipeline/setup.sh
set -euo pipefail

TIPPECANOE_VERSION="2.79.0"
# Commit of the tag above: tags can be moved, commits can't.
TIPPECANOE_COMMIT="68ab8dcc229f95b8b25877697d5e8d66783af503"
PMTILES_VERSION="1.31.2"
# SHA-256 of go-pmtiles_${PMTILES_VERSION}_Linux_x86_64.tar.gz (GitHub release asset digest).
PMTILES_SHA256="3ed7dbf4ec2e6dfe5e25b6f70d1ffc932729f93c86db353bf514dd71010a312f"
# SHA-256 of the pmtiles binary in that archive: an installed copy is only
# reused if it matches.
PMTILES_BIN_SHA256="a7e9ae10184d109c83f456ccdf6df4f3e2a64ba6cf69d9ed0f9f1840305055c1"
PREFIX="${PREFIX:-$HOME/.local}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$PREFIX/bin"
export PATH="$PREFIX/bin:$PATH"

echo "==> System packages"
sudo apt-get update -qq
sudo apt-get install -y -qq --no-install-recommends \
  build-essential libsqlite3-dev zlib1g-dev git curl ca-certificates \
  python3 python3-venv

echo "==> tippecanoe $TIPPECANOE_VERSION"
if tippecanoe --version 2>&1 | grep -q "v$TIPPECANOE_VERSION"; then
  echo "already installed"
else
  build_dir="$(mktemp -d)"
  git -C "$build_dir" init --quiet
  git -C "$build_dir" fetch --quiet --depth 1 \
    https://github.com/felt/tippecanoe.git "$TIPPECANOE_COMMIT"
  git -C "$build_dir" checkout --quiet FETCH_HEAD
  test "$(git -C "$build_dir" rev-parse HEAD)" = "$TIPPECANOE_COMMIT"
  make -C "$build_dir" -j"$(nproc)" >/dev/null
  make -C "$build_dir" install PREFIX="$PREFIX" >/dev/null
  rm -rf "$build_dir"
fi

echo "==> pmtiles $PMTILES_VERSION"
if [ -x "$PREFIX/bin/pmtiles" ] &&
  echo "$PMTILES_BIN_SHA256  $PREFIX/bin/pmtiles" | sha256sum --check --quiet 2>/dev/null; then
  echo "already installed (checksum verified)"
else
  dl_dir="$(mktemp -d)"
  base="https://github.com/protomaps/go-pmtiles/releases/download/v$PMTILES_VERSION"
  archive="go-pmtiles_${PMTILES_VERSION}_Linux_x86_64.tar.gz"
  curl -fsSL -o "$dl_dir/$archive" "$base/$archive"
  echo "$PMTILES_SHA256  $dl_dir/$archive" | sha256sum --check --quiet
  tar -xzf "$dl_dir/$archive" -C "$dl_dir" pmtiles
  echo "$PMTILES_BIN_SHA256  $dl_dir/pmtiles" | sha256sum --check --quiet
  install -m 0755 "$dl_dir/pmtiles" "$PREFIX/bin/pmtiles"
  rm -rf "$dl_dir"
fi

echo "==> Python venv"
python3 -m venv "$HERE/.venv"
# Every package, including dependencies of dependencies, pinned with hashes
# (requirements.txt is generated from requirements.in, see the command there).
"$HERE/.venv/bin/pip" install --quiet --require-hashes -r "$HERE/requirements.txt"

echo
echo "Done. Make sure $PREFIX/bin is on your PATH, then run:"
echo "  cd pipeline && .venv/bin/python -m lod2pipe"
