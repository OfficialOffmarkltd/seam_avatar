#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENDOR_DATA="$SCRIPT_DIR/../data"
CLONE_DIR="/tmp/makehuman-src"

echo "Fetching MakeHuman data assets..."

# Clone the MakeHuman repo shallowly (we only need the data directory)
if [ -d "$CLONE_DIR" ]; then
    echo "Removing existing clone at $CLONE_DIR"
    rm -rf "$CLONE_DIR"
fi

git clone --depth=1 https://github.com/makehumancommunity/makehuman.git "$CLONE_DIR"

# Create destination directories
mkdir -p "$VENDOR_DATA/targets"
mkdir -p "$VENDOR_DATA/3dobjs"

# Copy the two files we need
cp "$CLONE_DIR/makehuman/data/targets.npz" "$VENDOR_DATA/targets/targets.npz"
cp "$CLONE_DIR/makehuman/data/3dobjs/base.obj"     "$VENDOR_DATA/3dobjs/base.obj"

# Clean up
rm -rf "$CLONE_DIR"

echo "Done. Files written to $VENDOR_DATA"
