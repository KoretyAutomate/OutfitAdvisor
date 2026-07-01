#!/bin/bash
# Run on DGX Spark to install the outfit advisor cron job.
# Usage: bash install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$(which python3)"
LOG="$HOME/.outfit_advisor.log"

echo "=== Outfit Advisor — DGX Spark install ==="
echo "Script: $SCRIPT_DIR/outfit_advisor.py"
echo "Python: $PYTHON"
echo ""

# Write config template if it doesn't exist
if [ ! -f ~/.config/outfit_advisor/config.json ]; then
    echo "Creating config template..."
    $PYTHON "$SCRIPT_DIR/outfit_advisor.py" --init
    echo ""
    echo "STOP: edit ~/.config/outfit_advisor/config.json before continuing."
    echo "  - Set home_lat / home_lon (your home coordinates)"
    echo "  - Set openweather_api_key  (free at openweathermap.org)"
    echo "  - Set telegram_bot_token + telegram_chat_id (reuse from TradingIntel)"
    echo "  - Set ollama_model (default: qwen3:8b — change if needed)"
    exit 0
fi

# Validate config + do a dry run
echo "Running --test to validate config..."
$PYTHON "$SCRIPT_DIR/outfit_advisor.py" --test
echo ""

# Install cron job — fires at 9 PM every day
CRON_LINE="0 21 * * * $PYTHON $SCRIPT_DIR/outfit_advisor.py >> $LOG 2>&1"

if crontab -l 2>/dev/null | grep -qF "outfit_advisor.py"; then
    echo "Cron entry already exists — skipping."
else
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
    echo "Cron job installed: fires daily at 21:00"
fi

echo ""
echo "Done. To check logs: tail -f $LOG"
echo "To run immediately: $PYTHON $SCRIPT_DIR/outfit_advisor.py"
