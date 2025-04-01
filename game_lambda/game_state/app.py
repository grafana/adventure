import json
from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.logging import correlation_paths

from shared.models import GameState, BlacksmithState
from shared.dynamodb import GameStateDB

# Initialize AWS Lambda Powertools
logger = Logger()
tracer = Tracer()
metrics = Metrics()
app = APIGatewayRestResolver()

@app.get("/game-state/<adventurer_name>")
@tracer.capture_method
def get_game_state(adventurer_name: str):
    """Get saved game state for an adventurer"""
    try:
        game_state, blacksmith_state = GameStateDB.load_game_state(adventurer_name)
        
        if not game_state:
            return {
                "statusCode": 404,
                "body": json.dumps({"message": "No saved game found"})
            }
        
        return {
            "game_state": game_state.dict(),
            "blacksmith_state": blacksmith_state.dict() if blacksmith_state else None
        }
        
    except Exception as e:
        logger.exception("Error loading game state")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

@app.post("/game-state")
@tracer.capture_method
def save_game_state():
    """Save game state for an adventurer"""
    try:
        request_data = app.current_event.json_body
        game_state = GameState(**request_data["game_state"])
        blacksmith_state = BlacksmithState(**request_data["blacksmith_state"]) if request_data.get("blacksmith_state") else None
        
        success = GameStateDB.save_game_state(game_state, blacksmith_state)
        
        if success:
            return {"message": "Game state saved successfully"}
        else:
            return {
                "statusCode": 500,
                "body": json.dumps({"error": "Failed to save game state"})
            }
            
    except Exception as e:
        logger.exception("Error saving game state")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

@app.delete("/game-state/<adventurer_name>")
@tracer.capture_method
def delete_game_state(adventurer_name: str):
    """Delete saved game state for an adventurer"""
    try:
        success = GameStateDB.delete_game_state(adventurer_name)
        
        if success:
            return {"message": "Game state deleted successfully"}
        else:
            return {
                "statusCode": 500,
                "body": json.dumps({"error": "Failed to delete game state"})
            }
            
    except Exception as e:
        logger.exception("Error deleting game state")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """Main Lambda handler"""
    return app.resolve(event, context) 