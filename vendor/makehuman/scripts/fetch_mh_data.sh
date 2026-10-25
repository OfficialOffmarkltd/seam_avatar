#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENDOR_DATA="$SCRIPT_DIR/../data"
CLONE_DIR="/tmp/makehuman-src"
SOURCE_DIR="${MAKEHUMAN_SOURCE_PATH:-}"
CLONED_SOURCE=false

echo "Fetching MakeHuman data assets..."

if [ -n "$SOURCE_DIR" ]; then
    if [ ! -d "$SOURCE_DIR/data" ]; then
        echo "MAKEHUMAN_SOURCE_PATH must point to the MakeHuman source directory containing data/" >&2
        exit 1
    fi
    echo "Using local MakeHuman source at $SOURCE_DIR"
else
    # Clone the MakeHuman repo shallowly when a local checkout is unavailable.
    if [ -d "$CLONE_DIR" ]; then
        echo "Removing existing clone at $CLONE_DIR"
        rm -rf "$CLONE_DIR"
    fi
    git clone --depth=1 https://github.com/makehumancommunity/makehuman.git "$CLONE_DIR"
    SOURCE_DIR="$CLONE_DIR/makehuman"
    CLONED_SOURCE=true
fi

# Create destination directories
mkdir -p "$VENDOR_DATA/targets"
mkdir -p "$VENDOR_DATA/3dobjs"
mkdir -p "$VENDOR_DATA/modifiers"

# Copy the two files we need
cp "$SOURCE_DIR/data/targets.npz" "$VENDOR_DATA/targets/targets.npz"
cp "$SOURCE_DIR/data/3dobjs/base.obj"     "$VENDOR_DATA/3dobjs/base.obj"
cp "$SOURCE_DIR/data/modifiers/modeling_modifiers.json" "$VENDOR_DATA/modifiers/"
cp "$SOURCE_DIR/data/modifiers/measurement_modifiers.json" "$VENDOR_DATA/modifiers/"

# Clean up
if [ "$CLONED_SOURCE" = true ]; then
    rm -rf "$CLONE_DIR"
fi

echo "Done. Files written to $VENDOR_DATA"
