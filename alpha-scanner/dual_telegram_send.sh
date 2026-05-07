#!/bin/bash
# dual_telegram_send.sh - Send the same message to two Telegram bots
# Handles messages > 4096 chars by splitting into multiple messages.
#
# Usage: dual_telegram_send.sh "message"
#   or: echo "message" | dual_telegram_send.sh
#   or: dual_telegram_send.sh < file.txt

set -euo pipefail

# Bot 1: Primary (jituihermes_bot) -> Ddong Walks
TOKEN1=$(grep '^TELEGRAM_BOT_TOKEN=' ~/.hermes/.env | cut -d= -f2)
CHAT_ID1="7654897510"

# Bot 2: Secondary (zhx0205hermes_bot) -> Iris Zhu
TOKEN2="8627033259:AAHQMft-iE3CBJw9-xC9-iF1aP1kbELsr6U"
CHAT_ID2="8248490914"

# Read message from argument or stdin
if [ $# -ge 1 ]; then
    MSG="$1"
else
    MSG=$(cat)
fi

# Split message into 4096-char chunks and send each one
# Split at newline boundaries when possible to avoid breaking mid-line
send_long_message() {
    local token="$1"
    local chat_id="$2"
    local label="$3"
    local msg="$4"
    local total_chunks=0
    local ok_count=0
    local fail_count=0

    # Use python3 to split at newline boundaries
    local chunks_json
    chunks_json=$(python3 -c "
import sys
msg = sys.stdin.read()
limit = 4096
if len(msg) <= limit:
    print('[\"' + msg.replace('\\\\', '\\\\\\\\').replace('\"', '\\\\\"').replace('\n', '\\\\n') + '\"]')
else:
    chunks = []
    lines = msg.split('\n')
    current = ''
    for line in lines:
        if len(current) + len(line) + 1 > limit and current:
            chunks.append(current)
            current = line
        else:
            current = current + '\n' + line if current else line
    if current:
        chunks.append(current)
    import json
    print(json.dumps(chunks))
" <<< "$msg")

    # Send each chunk
    local chunk_count
    chunk_count=$(python3 -c "import json,sys; print(len(json.load(sys.stdin)))" <<< "$chunks_json")

    for i in $(seq 0 $((chunk_count - 1))); do
        local chunk
        chunk=$(python3 -c "import json,sys; print(json.load(sys.stdin)[$i])" <<< "$chunks_json")

        local payload
        payload=$(python3 -c "import json,sys; print(json.dumps({'chat_id':'${chat_id}','text':sys.stdin.read()}))" <<< "$chunk")

        local result
        result=$(curl -s --max-time 10 -X POST "https://api.telegram.org/bot${token}/sendMessage" \
            -H "Content-Type: application/json" \
            -d "$payload" 2>&1)

        local ok
        ok=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok',False))" 2>/dev/null || echo "False")

        if [ "$ok" = "True" ]; then
            ok_count=$((ok_count + 1))
        else
            fail_count=$((fail_count + 1))
        fi
        total_chunks=$((total_chunks + 1))

        # Rate limit: small delay between chunks
        if [ $i -lt $((chunk_count - 1)) ]; then
            sleep 0.5
        fi
    done

    echo "${label}:${ok_count}/${total_chunks}ok"
}

# Send to both bots
R1=$(send_long_message "$TOKEN1" "$CHAT_ID1" "Bot1" "$MSG")
R2=$(send_long_message "$TOKEN2" "$CHAT_ID2" "Bot2" "$MSG")

echo "${R1} ${R2}"

# Success if at least one bot delivered something
case "$R1 $R2" in
    *1*ok*|*2*ok*|*3*ok*) exit 0 ;;
    *) exit 1 ;;
esac
