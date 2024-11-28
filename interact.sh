#!/bin/bash

# Simple script to prevent me having to retype the curl command. 
# Use me like this:  ./interact.sh "go north" and you'll continuously play the game
# You must put everything in quotes.

ENDPOINT=http://localhost:3001/api/adventure
#ENDPOINT=https://adventure-93209135917.us-east4.run.app/api/adventure
PLAYER=Moxious

JSON=$(cat <<EOF
{"user":"$PLAYER", "command":"$1"}
EOF
)
# echo $JSON
# echo $ENDPOINT
response=$(curl -XPOST $ENDPOINT -H 'Content-Type: application/json' -d "$JSON")

echo $response | jq -r '.response'
echo
