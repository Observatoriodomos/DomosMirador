#!/bin/bash
#
# install-github-mcp.sh
# Adds the hosted GitHub MCP server to Claude Desktop config
# Preserves all existing preferences. Creates a timestamped backup before writing.
#
# Run from Terminal:
#   bash ~/Downloads/install-github-mcp.sh
# Or from wherever you saved it.
#
# After it succeeds, fully quit Claude Desktop (Cmd+Q) and reopen.

set -euo pipefail

CONFIG_DIR="$HOME/Library/Application Support/Claude"
CONFIG_FILE="$CONFIG_DIR/claude_desktop_config.json"
BACKUP_FILE="$CONFIG_FILE.backup-$(date +%Y%m%d-%H%M%S)"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Config file not found at: $CONFIG_FILE"
    echo "Aborting. Claude Desktop may not be installed or has never been run."
    exit 1
fi

# Backup
cp "$CONFIG_FILE" "$BACKUP_FILE"
echo "Backed up current config to:"
echo "  $BACKUP_FILE"

# Merge in mcpServers.github using Python (preinstalled on macOS)
python3 <<PYEOF
import json
import sys

config_path = "$CONFIG_FILE"

with open(config_path, "r") as f:
    config = json.load(f)

# Ensure mcpServers exists at top level (sibling to preferences)
if "mcpServers" not in config:
    config["mcpServers"] = {}

# Add the hosted GitHub MCP server
config["mcpServers"]["github"] = {
    "url": "https://api.githubcopilot.com/mcp/",
    "transport": "http"
}

with open(config_path, "w") as f:
    json.dump(config, f, indent=2)

print("OK — github MCP server added to claude_desktop_config.json")
PYEOF

echo ""
echo "Done. Next steps:"
echo "  1. Fully quit Claude Desktop:  Cmd+Q (don't just close the window)"
echo "  2. Reopen Claude Desktop"
echo "  3. It will prompt your browser to authorize GitHub — approve for Observatoriodomos"
echo "  4. Start a new chat and say:  Verify GitHub MCP — list my Observatoriodomos repos"
echo ""
echo "If anything goes wrong, restore from backup:"
echo "  cp \"$BACKUP_FILE\" \"$CONFIG_FILE\""
