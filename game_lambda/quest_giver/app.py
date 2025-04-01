import json
from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.logging import correlation_paths

from shared.models import (
    QuestRequest,
    ActionResponse,
    GameState,
    QuestAction,
    SwordType
)
from shared.dynamodb import GameStateDB

# Initialize AWS Lambda Powertools
logger = Logger()
tracer = Tracer()
metrics = Metrics()
app = APIGatewayRestResolver()

@app.post("/quest-giver")
@tracer.capture_method
def handle_quest_action():
    """Handle quest giver actions"""
    try:
        # Parse request body
        request_data = app.current_event.json_body
        quest_request = QuestRequest(**request_data)
        
        # Load existing state from DynamoDB
        saved_game_state, _ = GameStateDB.load_game_state(quest_request.game_state.adventurer_name)
        
        # Use saved state if it exists, otherwise use request state
        game_state = saved_game_state or quest_request.game_state
        
        # Initialize response
        response = ActionResponse(
            message="",
            game_state=game_state,
            blacksmith_state=None
        )
        
        # Process the action
        if quest_request.action == QuestAction.ACCEPT_QUEST:
            handle_accept_quest(quest_request, response)
        elif quest_request.action == QuestAction.CHECK_PROGRESS:
            handle_check_progress(quest_request, response)
        
        # Save updated state to DynamoDB
        GameStateDB.save_game_state(response.game_state)
        
        return response.dict()
        
    except Exception as e:
        logger.exception("Error processing quest action")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

def handle_accept_quest(request: QuestRequest, response: ActionResponse):
    """Handle accepting the quest"""
    if response.game_state.quest_accepted:
        response.message = "You have already accepted the quest to defeat the evil wizard."
        return
        
    if not response.game_state.has_sword:
        response.message = "You need a sword before you can accept this quest."
        tracer.put_annotation("quest_accepted", "no_sword")
        return
        
    response.game_state.quest_accepted = True
    response.message = "You accept the quest to defeat the evil wizard. Be careful, he is very powerful."
    logger.info(f"{response.game_state.adventurer_name} has accepted the quest")
    tracer.put_annotation("quest_accepted", "success")

def handle_check_progress(request: QuestRequest, response: ActionResponse):
    """Handle checking quest progress"""
    if not response.game_state.quest_accepted:
        response.message = "You haven't accepted any quests yet."
        return
        
    if not response.game_state.has_sword:
        response.message = "You lost your sword! You'll need to get another one from the blacksmith."
        return
        
    if response.game_state.sword_type == SwordType.REGULAR:
        response.message = "Your sword is not powerful enough. Try visiting the chapel or the mysterious man."
    elif response.game_state.sword_type == SwordType.HOLY:
        response.message = "Your holy sword should be powerful enough to defeat the wizard. Good luck!"
    elif response.game_state.sword_type == SwordType.EVIL:
        response.message = "There's something strange about your sword. Are you sure you can trust that mysterious man?"
    
    tracer.put_annotation("quest_progress_checked", "true")

@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """Main Lambda handler"""
    return app.resolve(event, context) 