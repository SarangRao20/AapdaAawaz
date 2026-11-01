#!/usr/bin/env bash
# Generates claude_desktop_config.json with correct absolute paths
# resolved from wherever this script lives. Run once after cloning.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

# Install deps into local venv if needed
if [ ! -f "$DIR/venv/bin/python" ]; then
  python3 -m venv "$DIR/venv"
  "$DIR/venv/bin/pip" install -q -r "$DIR/requirements.txt"
fi

cat > "$DIR/claude_desktop_config.json" <<EOF
{
  "mcpServers": {
    "aapda-awaaz": {
      "command": "$DIR/venv/bin/python",
      "args": ["$DIR/server.py"],
      "env": {
        "AAPDA_API_URL": "http://localhost:8000"
      }
    }
  }
}
EOF

echo "✓  claude_desktop_config.json written"
echo "   Copy it into:"
echo "     macOS:   ~/Library/Application Support/Claude/claude_desktop_config.json"
echo "     Windows: %APPDATA%\\Claude\\claude_desktop_config.json"
echo "   Then restart Claude Desktop."
