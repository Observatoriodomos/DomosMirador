#!/bin/bash
#
# install-n8n-mcp.sh
# Adds the n8n MCP server (czlonkowski/n8n-mcp) to Claude Desktop config.
# Preserves all existing preferences. Creates a timestamped backup before writing.
# Prompts for the n8n API URL and key — does NOT echo the key.
#
# Run from Terminal:
#   bash ~/Downloads/install-n8n-mcp.sh
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

if ! command -v npx >/dev/null 2>&1; then
    echo "npx not found in PATH. The n8n MCP server runs via npx."
    echo "Install Node.js (>=18) first: https://nodejs.org/"
    exit 1
fi

# --- Prompt for n8n connection details ---------------------------------------
DEFAULT_URL="https://your-n8n-instance.com/api/v1"
read -r -p "n8n API URL [$DEFAULT_URL]: " N8N_API_URL
N8N_API_URL="${N8N_API_URL:-$DEFAULT_URL}"

# Silent prompt for API key — never echoed.
read -r -s -p "n8n API key (input hidden): " N8N_API_KEY
echo
if [ -z "$N8N_API_KEY" ]; then
    echo "API key cannot be empty. Get one in n8n: Settings → API → Create New API Key."
    exit 1
fi

# --- Back up current config --------------------------------------------------
cp "$CONFIG_FILE" "$BACKUP_FILE"
echo "Backed up current config to:"
echo "  $BACKUP_FILE"

# --- Merge in mcpServers.n8n via Python (preinstalled on macOS) --------------
# Pass URL + key via env vars so they never touch the command line.
export N8N_API_URL N8N_API_KEY

python3 <<PYEOF
import json
import os

config_path = "$CONFIG_FILE"

with open(config_path, "r") as f:
    config = json.load(f)

if "mcpServers" not in config:
    config["mcpServers"] = {}

config["mcpServers"]["n8n"] = {
    "command": "npx",
    "args": ["-y", "@czlonkowski/n8n-mcp@latest"],
    "env": {
        "N8N_API_URL": os.environ["N8N_API_URL"],
        "N8N_API_KEY": os.environ["N8N_API_KEY"],
    },
}

with open(config_path, "w") as f:
    json.dump(config, f, indent=2)

print("OK — n8n MCP server added to claude_desktop_config.json")
PYEOF

# Wipe key from this shell's env so a later `env` dump doesn't leak it.
unset N8N_API_KEY

echo ""
echo "Done. Next steps:"
echo "  1. Fully quit Claude Desktop:  Cmd+Q (don't just close the window)"
echo "  2. Reopen Claude Desktop"
echo "  3. Start a new chat and say:  List my n8n workflows"
echo ""
echo "If the n8n MCP fails to connect, common causes:"
echo "  - N8N_API_URL must end in /api/v1 (not just the n8n root URL)"
echo "  - API key needs the relevant scopes (workflow:read, workflow:update at minimum)"
echo "  - n8n instance must be reachable from this machine (test with: curl -H \"X-N8N-API-KEY: <key>\" $N8N_API_URL/workflows)"
echo ""
echo "If anything goes wrong, restore from backup:"
echo "  cp \"$BACKUP_FILE\" \"$CONFIG_FILE\""
