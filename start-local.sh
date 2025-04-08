#!/bin/bash


# Start Docker containers
echo "Starting DynamoDB local and admin..."
docker compose up -d

# Wait for DynamoDB to start
echo "Waiting for DynamoDB to start..."
sleep 5

# Set environment variables for local development
export DYNAMODB_ENDPOINT="http://localhost:8000"
export GAME_STATE_TABLE="adventure-quest-state"
export API_URL="http://localhost:3000"

# Start the local API server (using AWS SAM or a custom API server)
echo "Starting local API server..."
echo "Note: Use 'sam local start-api' if you have AWS SAM CLI installed"
echo "You can access the DynamoDB admin panel at http://localhost:8001"

# Display helpful information
echo ""
echo "Local development environment is ready!"
echo "DynamoDB is running at $DYNAMODB_ENDPOINT"
echo "DynamoDB Admin UI is available at http://localhost:8001"
echo "Set up the game state table using the Admin UI if needed"
echo ""
echo "To manually create the table, use AWS CLI:"
echo "aws dynamodb create-table --table-name $GAME_STATE_TABLE \\"
echo "  --attribute-definitions AttributeName=adventurer_name,AttributeType=S \\"
echo "  --key-schema AttributeName=adventurer_name,KeyType=HASH \\"
echo "  --billing-mode PAY_PER_REQUEST \\"
echo "  --endpoint-url $DYNAMODB_ENDPOINT"
echo ""
echo "To run the game client:"
echo "python adventure_client.py"
echo ""
echo "Press Ctrl+C to stop this script and run 'docker-compose down' to stop the Docker containers" 