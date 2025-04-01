import json
from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.logging import correlation_paths

from shared.models import (
    MysteriousManRequest,
    ActionResponse,
    GameState,
    MysteriousManAction,
    SwordType
)
from shared.dynamodb import GameStateDB

# Initialize AWS Lambda Powertools
logger = Logger()
tracer = Tracer()
metrics = Metrics()
app = APIGatewayRestResolver()

@app.post("/mysterious-man")
@tracer.capture_method
def handle_mysterious_man_action():
    """Handle mysterious man (evil wizard) actions"""
    try:
        # Parse request body
        request_data = app.current_event.json_body
        mysterious_request = MysteriousManRequest(**request_data)
        
        # Load existing state from DynamoDB
        saved_game_state, _ = GameStateDB.load_game_state(mysterious_request.game_state.adventurer_name)
        
        # Use saved state if it exists, otherwise use request state
        game_state = saved_game_state or mysterious_request.game_state
        
        # Initialize response
        response = ActionResponse(
            message="",
            game_state=game_state,
            blacksmith_state=None
        )
        
        # Process the action
        if mysterious_request.action == MysteriousManAction.ACCEPT_OFFER:
            handle_accept_offer(mysterious_request, response)
        elif mysterious_request.action == MysteriousManAction.DECLINE_OFFER:
            handle_decline_offer(mysterious_request, response)
        elif mysterious_request.action == MysteriousManAction.KILL_WIZARD:
            handle_kill_wizard(mysterious_request, response)
        
        # Save updated state to DynamoDB
        GameStateDB.save_game_state(response.game_state)
        
        return response.dict()
        
    except Exception as e:
        logger.exception("Error processing mysterious man action")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

def handle_accept_offer(request: MysteriousManRequest, response: ActionResponse):
    """Handle accepting the evil wizard's offer"""
    if not response.game_state.has_sword:
        response.message = "You don't have a sword for the wizard to enchant."
        return
        
    # Update sword state
    response.game_state.sword_type = SwordType.EVIL
    logger.error("The evil wizard has enchanted the sword with dark magic")
    response.message = "You feel funny but powerful. Maybe I should accept a quest."
    tracer.put_annotation("sword_enchanted", "evil")

def handle_decline_offer(request: MysteriousManRequest, response: ActionResponse):
    """Handle declining the evil wizard's offer"""
    response.message = "You will not get another chance. ACCEPT MY OFFER!"
    tracer.put_annotation("offer_declined", "true")

def handle_kill_wizard(request: MysteriousManRequest, response: ActionResponse):
    """Handle attempting to kill the wizard"""
    if not response.game_state.quest_accepted:
        response.message = "You need to accept the quest first!"
        return
        
    if response.game_state.sword_type == SwordType.HOLY:
        response.message = "You strike the wizard down with your holy sword. The town cheers for you. Your adventure has come to an end."
        logger.info(f"{response.game_state.adventurer_name} has successfully defeated the wizard")
        tracer.put_annotation("wizard_defeated", "success")
    elif response.game_state.sword_type == SwordType.EVIL:
        response.message = "The wizard laughs as you strike him down. The sword was cursed. You have failed. The adventure ends here."
        logger.critical("The cursed sword betrayed the adventurer")
        tracer.put_annotation("wizard_defeated", "betrayed")
    else:
        response.message = "You try to strike the wizard down but your sword is not powerful enough."
        logger.warning("Regular sword is not powerful enough to defeat the wizard")
        response.game_state.has_sword = False
        tracer.put_annotation("wizard_defeated", "failed")

@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """Main Lambda handler"""
    return app.resolve(event, context) 