#!/bin/bash
# Finds the ok-know plugin's install path and copies _wip_helpers.py to the target project
# Usage: copy-helpers.sh <target-dir>

TARGET_DIR="${1:-.}"
PLUGINS_JSON="$HOME/.claude/plugins/installed_plugins.json"

if [ ! -f "$PLUGINS_JSON" ]; then
    echo "ERROR: Plugin registry not found at $PLUGINS_JSON"
    exit 1
fi

# Find the ok-know plugin install path (handles ok-know@marketplace-name format)
PLUGIN_PATH=$(python3 -c "
import json
import sys
with open('$PLUGINS_JSON') as f:
    data = json.load(f)
for key, entries in data.get('plugins', {}).items():
    if key.startswith('ok-know@'):
        print(entries[0]['installPath'])
        sys.exit(0)
print('NOT_FOUND')
" 2>/dev/null)

if [ "$PLUGIN_PATH" = "NOT_FOUND" ] || [ -z "$PLUGIN_PATH" ]; then
    echo "ERROR: ok-know plugin not found in registry"
    exit 1
fi

# Convert Windows path to Git Bash path if needed
if [[ "$PLUGIN_PATH" == *":"* ]]; then
    PLUGIN_PATH=$(echo "$PLUGIN_PATH" | sed 's|\\|/|g' | sed 's|^\([A-Za-z]\):|/\L\1|')
fi

SOURCE="$PLUGIN_PATH/scripts/_wip_helpers.py"
DEST="$TARGET_DIR/.claude/knowledge/journey/_wip_helpers.py"

if [ ! -f "$SOURCE" ]; then
    echo "ERROR: Helper script not found at $SOURCE"
    exit 1
fi

mkdir -p "$(dirname "$DEST")"
cp "$SOURCE" "$DEST"
echo "Copied _wip_helpers.py to $DEST"
