import json
from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.logging import correlation_paths

from shared.models import (
    BlacksmithRequest,
    ActionResponse,
    GameState,
    BlacksmithState,
    BlacksmithAction,
    SwordType
)
from shared.dynamodb import GameStateDB

# Initialize AWS Lambda Powertools
logger = Logger()
tracer = Tracer()
metrics = Metrics()
app = APIGatewayRestResolver()

@app.post("/blacksmith")
@tracer.capture_method
def handle_blacksmith_action():
    """Handle blacksmith actions like requesting sword, heating forge, etc."""
    try:
        # Parse request body
        request_data = app.current_event.json_body
        blacksmith_request = BlacksmithRequest(**request_data)
        
        # Load existing state from DynamoDB
        saved_game_state, saved_blacksmith_state = GameStateDB.load_game_state(blacksmith_request.game_state.adventurer_name)
        
        # Use saved state if it exists, otherwise use request state
        game_state = saved_game_state or blacksmith_request.game_state
        blacksmith_state = saved_blacksmith_state or blacksmith_request.blacksmith_state or BlacksmithState()
        
        # Initialize response
        response = ActionResponse(
            message="",
            game_state=game_state,
            blacksmith_state=blacksmith_state
        )
        
        # Process the action
        if blacksmith_request.action == BlacksmithAction.REQUEST_SWORD:
            handle_request_sword(blacksmith_request, response)
        elif blacksmith_request.action == BlacksmithAction.HEAT_FORGE:
            handle_heat_forge(blacksmith_request, response)
        elif blacksmith_request.action == BlacksmithAction.COOL_FORGE:
            handle_cool_forge(blacksmith_request, response)
        elif blacksmith_request.action == BlacksmithAction.CHECK_SWORD:
            handle_check_sword(blacksmith_request, response)
        
        # Save updated state to DynamoDB
        GameStateDB.save_game_state(response.game_state, response.blacksmith_state)
        
        return response.model_dump()
        
    except Exception as e:
        logger.exception("Error processing blacksmith action")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

def handle_request_sword(request: BlacksmithRequest, response: ActionResponse):
    """Handle the request sword action"""
    if response.game_state.has_sword:
        response.message = "You already have a sword. You don't need another one."
        return
    
    if response.game_state.failed_sword_attempts > 0 and response.game_state.failed_sword_attempts < 3:
        response.blacksmith_state.sword_requested = True
        if response.blacksmith_state.is_heating_forge:
            logger.warning("Sword requested while forge is still hot")
            response.message = "The blacksmith looks at you with disappointment. He says, 'Fine, but be more careful this time! If the forge gets too hot, the sword will melt.'"
        return
    elif response.game_state.failed_sword_attempts >= 3:
        logger.error("Too many failed sword attempts")
        response.message = "The blacksmith refuses to forge you another sword. You have wasted too much of his time."
        return
    
    response.blacksmith_state.sword_requested = True
    response.message = "The blacksmith agrees to forge you a sword. It will take some time and the forge needs to be heated to the correct temperature however."

def handle_heat_forge(request: BlacksmithRequest, response: ActionResponse):
    """Handle the heat forge action"""
    response.blacksmith_state.is_heating_forge = True
    response.blacksmith_state.heat += 5  # Increment heat when heating the forge
    response.message = "You fire up the forge and it begins heating up. You should wait a while before checking on the sword."

def handle_cool_forge(request: BlacksmithRequest, response: ActionResponse):
    """Handle the cool forge action"""
    response.blacksmith_state.heat = 0
    response.blacksmith_state.is_heating_forge = False
    response.message = "You throw a bucket of water over the forge. The coals sizzle and the forge cools down completely."

def handle_check_sword(request: BlacksmithRequest, response: ActionResponse):
    """Handle the check sword action"""
    heat = response.blacksmith_state.heat
    
    if heat >= 10 and heat <= 20:
        response.blacksmith_state.sword_requested = False
        response.game_state.has_sword = True
        response.game_state.sword_type = SwordType.REGULAR
        response.message = "The sword is ready. You take it from the blacksmith."
        tracer.put_annotation("sword_forged", "success")
    elif heat >= 21:
        response.blacksmith_state.sword_requested = False
        response.game_state.failed_sword_attempts += 1
        response.message = "The sword has completely melted! The blacksmith looks at you with disappointment."
        tracer.put_annotation("sword_forged", "failed")
    else:
        response.message = "The forge is not hot enough yet. The blacksmith tells you to wait."
        tracer.put_annotation("sword_forged", "too_cold")

@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """Main Lambda handler"""
    return app.resolve(event, context) 