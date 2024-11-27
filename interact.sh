#!/bin/bash

# Simple script to prevent me having to retype the curl command. 
# Use me like this:  ./interact.sh "go north" and you'll continuously play the game
# You must put everything in quotes.

ENDPOINT=http://localhost:3000/api/adventure
PLAYER=moxious

JSON=$(cat <<EOF
{"user":"$PLAYER", "command":"$1"}
EOF
)
# echo $JSON
# echo $ENDPOINT
curl -XPOST $ENDPOINT -H 'Content-Type: application/json' -d "$JSON"

echo