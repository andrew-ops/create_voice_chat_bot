#!/usr/bin/env bash
# notify_restart.sh
WEBHOOK_URL="https://discord.com/api/webhooks/…/…"
HOSTNAME=$(hostname)
TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

# Discord용 JSON payload
read -r -d '' PAYLOAD <<EOF
{
"content": "",
"embeds": [
    {
    "title": "🤖 Discord Bot Restarted",
    "color": 3066993,
    "fields": [
        { "name": "Host", "value": "$HOSTNAME", "inline": true },
        { "name": "Time", "value": "$TIMESTAMP", "inline": true }
    ]
    }
]
}
EOF

# curl로 POST
curl -X POST -H "Content-Type: application/json" \
    -d "$PAYLOAD" \
    "$WEBHOOK_URL"
