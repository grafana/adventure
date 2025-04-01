import json
from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.logging import correlation_paths

from shared.models import (
    ChapelRequest,
    ActionResponse,
    GameState,
    ChapelAction,
    SwordType
)
from shared.dynamodb import GameStateDB

# Initialize AWS Lambda Powertools
logger = Logger()
tracer = Tracer()
metrics = Metrics()
app = APIGatewayRestResolver()

@app.post("/chapel")
@tracer.capture_method
def handle_chapel_action():
    """Handle chapel actions like blessing swords"""
    try:
        # Parse request body
        request_data = app.current_event.json_body
        chapel_request = ChapelRequest(**request_data)
        
        # Load existing state from DynamoDB
        saved_game_state, _ = GameStateDB.load_game_state(chapel_request.game_state.adventurer_name)
        
        # Use saved state if it exists, otherwise use request state
        game_state = saved_game_state or chapel_request.game_state
        
        # Initialize response
        response = ActionResponse(
            message="",
            game_state=game_state,
            blacksmith_state=None
        )
        
        # Process the action
        if chapel_request.action == ChapelAction.LOOK_AT_SWORD:
            handle_look_at_sword(chapel_request, response)
        elif chapel_request.action == ChapelAction.PRAY:
            handle_pray(chapel_request, response)
        
        # Save updated state to DynamoDB
        GameStateDB.save_game_state(response.game_state)
        
        return response.dict()
        
    except Exception as e:
        logger.exception("Error processing chapel action")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

def handle_look_at_sword(request: ChapelRequest, response: ActionResponse):
    """Handle the priest looking at the sword"""
    if response.game_state.sword_type == SwordType.HOLY:
        response.message = "I have already blessed your sword child, go now and use it well."
        return
        
    if response.game_state.sword_type == SwordType.REGULAR:
        response.game_state.sword_type = SwordType.HOLY
        response.message = "The priest blesses your sword. You feel a warm glow."
        tracer.put_annotation("sword_blessed", "success")
        return
        
    if response.game_state.sword_type == SwordType.EVIL:
        response.game_state.sword_type = SwordType.HOLY
        response.game_state.priest_alive = False
        logger.warning("The priest transfers the curse from the sword to himself")
        response.message = "The priest looks at your sword with fear. My child, this sword is cursed. I will transfer the curse to me."
        tracer.put_annotation("curse_transferred", "true")
        return
        
    response.message = "The priest looks at your empty hands. You feel a little embarrassed."
    tracer.put_annotation("sword_blessed", "no_sword")

def handle_pray(request: ChapelRequest, response: ActionResponse):
    """Handle praying at the chapel"""
    response.message = "You pray for guidance."
    tracer.put_annotation("prayer_offered", "true")

@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """Main Lambda handler"""
    return app.resolve(event, context) 