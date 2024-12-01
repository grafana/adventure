#!/bin/bash

export PLAYER="Demo User2"

# Generate a new adventurer name!
ENDPOINT=http://localhost:3001/api/adventurer
response=$(curl --silent $ENDPOINT)

player_name=$(echo $response | jq -r '.name')
export PLAYER=$player_name

./interact.sh 'look around'
./interact.sh 'go to town'
./interact.sh 'blacksmith'
./interact.sh 'request sword'
./interact.sh 'heat forge'

echo "Thus temporarily ends the adventures of $player_name"