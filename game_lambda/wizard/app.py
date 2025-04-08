import json
import os
import requests
import boto3
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel
from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.logging import correlation_paths

# Initialize AWS Lambda Powertools
logger = Logger()
tracer = Tracer()
metrics = Metrics()
app = APIGatewayRestResolver()

# Model definitions
class SwordType(str, Enum):
    NONE = "none"
    REGULAR = "regular"
    HOLY = "holy"
    EVIL = "evil"

class GameState(BaseModel):
    adventurer_name: str
    current_location: str
    has_sword: bool = False
    sword_type: SwordType = SwordType.NONE
    quest_accepted: bool = False
    priest_alive: bool = True
    blacksmith_burned_down: bool = False
    failed_sword_attempts: int = 0
    has_box: bool = False
    quest_givers_killed: int = 0

class BlacksmithState(BaseModel):
    heat: int = 0
    is_heating_forge: bool = False
    sword_requested: bool = False

class WizardAction(str, Enum):
    KILL_WIZARD = "kill_wizard"
    TALK_TO_WIZARD = "talk_to_wizard"
    CHEAT = "cheat"

class WizardRequest(BaseModel):
    action: WizardAction
    game_state: GameState

class ActionResponse(BaseModel):
    message: str
    game_state: GameState
    blacksmith_state: Optional[BlacksmithState] = None
    success: bool = True
    game_over: bool = False

class GameStateAction(str, Enum):
    GET = "get"
    SAVE = "save"
    DELETE = "delete"

class GameStateRequest(BaseModel):
    action: GameStateAction
    adventurer_name: str
    game_state: Optional[GameState] = None
    blacksmith_state: Optional[BlacksmithState] = None

class GameStateResponse(BaseModel):
    success: bool
    message: str
    game_state: Optional[GameState] = None
    blacksmith_state: Optional[BlacksmithState] = None

# Game state API client
def get_game_state(adventurer_name: str) -> GameStateResponse:
    """Get game state from the game_state lambda"""
    try:
        # Check if we're running locally with SAM
        is_local = os.environ.get('AWS_SAM_LOCAL') == 'true'
        
        if is_local:
            # For local SAM testing, use localhost URL
            logger.info("Running in SAM Local mode, using localhost URL")
            local_url = "http://localhost:3000"
            request = GameStateRequest(
                action=GameStateAction.GET,
                adventurer_name=adventurer_name
            )
            
            response = requests.post(
                f"{local_url}/game-state/internal",
                json=request.model_dump()
            )
            
            if response.status_code == 200:
                return GameStateResponse(**response.json())
            else:
                logger.error(f"Failed to get game state: {response.status_code} - {response.text}")
                return GameStateResponse(
                    success=False,
                    message=f"Failed to get game state: {response.status_code}"
                )
        
        # For production, always use direct Lambda invocation
        logger.info("Using direct Lambda invocation")
        client = boto3.client('lambda')
        payload = json.dumps({
            "action": "get",
            "adventurer_name": adventurer_name,
            "source_function": "wizard"
        })
        
        response = client.invoke(
            FunctionName=os.environ.get('GAME_STATE_FUNCTION_NAME', 'GameStateFunction'),
            InvocationType='RequestResponse',
            Payload=payload
        )
        
        # Check for successful invocation
        if response.get('StatusCode') != 200:
            logger.error(f"Lambda invocation failed with status: {response.get('StatusCode')}")
            return GameStateResponse(
                success=False,
                message=f"Lambda invocation failed with status: {response.get('StatusCode')}"
            )
            
        payload_str = response['Payload'].read().decode('utf-8')
        logger.info(f"Received payload: {payload_str}")
        
        # Parse the payload
        try:
            payload = json.loads(payload_str)
            
            # Check for Lambda execution errors
            if 'errorMessage' in payload:
                logger.error(f"Lambda execution error: {payload}")
                return GameStateResponse(
                    success=False,
                    message=f"Lambda execution error: {payload.get('errorMessage')}"
                )
                
            return GameStateResponse(**payload)
        except json.JSONDecodeError:
            logger.error(f"Failed to decode payload as JSON: {payload_str}")
            return GameStateResponse(
                success=False,
                message=f"Failed to decode payload as JSON: {payload_str}"
            )
            
    except Exception as e:
        logger.exception(f"Error getting game state: {str(e)}")
        return GameStateResponse(
            success=False,
            message=f"Error getting game state: {str(e)}"
        )

def save_game_state(game_state: GameState, blacksmith_state: Optional[BlacksmithState] = None) -> GameStateResponse:
    """Save game state using the game_state lambda"""
    try:
        # Check if we're running locally with SAM
        is_local = os.environ.get('AWS_SAM_LOCAL') == 'true'
        
        if is_local:
            # For local SAM testing, use localhost URL
            logger.info("Running in SAM Local mode, using localhost URL")
            local_url = "http://localhost:3000"
            request = GameStateRequest(
                action=GameStateAction.SAVE,
                adventurer_name=game_state.adventurer_name,
                game_state=game_state,
                blacksmith_state=blacksmith_state
            )
            
            response = requests.post(
                f"{local_url}/game-state/internal",
                json=request.model_dump()
            )
            
            if response.status_code == 200:
                return GameStateResponse(**response.json())
            else:
                logger.error(f"Failed to save game state: {response.status_code} - {response.text}")
                return GameStateResponse(
                    success=False,
                    message=f"Failed to save game state: {response.status_code}"
                )
        
        # For production, always use direct Lambda invocation
        logger.info("Using direct Lambda invocation")
        client = boto3.client('lambda')
        payload = json.dumps({
            "action": "save",
            "adventurer_name": game_state.adventurer_name,
            "game_state": game_state.model_dump() if game_state else None,
            "blacksmith_state": blacksmith_state.model_dump() if blacksmith_state else None,
            "source_function": "wizard"
        })
        
        response = client.invoke(
            FunctionName=os.environ.get('GAME_STATE_FUNCTION_NAME', 'GameStateFunction'),
            InvocationType='RequestResponse',
            Payload=payload
        )
        
        # Check for successful invocation
        if response.get('StatusCode') != 200:
            logger.error(f"Lambda invocation failed with status: {response.get('StatusCode')}")
            return GameStateResponse(
                success=False,
                message=f"Lambda invocation failed with status: {response.get('StatusCode')}"
            )
            
        payload_str = response['Payload'].read().decode('utf-8')
        logger.info(f"Received payload: {payload_str}")
        
        # Parse the payload
        try:
            payload = json.loads(payload_str)
            
            # Check for Lambda execution errors
            if 'errorMessage' in payload:
                logger.error(f"Lambda execution error: {payload}")
                return GameStateResponse(
                    success=False,
                    message=f"Lambda execution error: {payload.get('errorMessage')}"
                )
                
            return GameStateResponse(**payload)
        except json.JSONDecodeError:
            logger.error(f"Failed to decode payload as JSON: {payload_str}")
            return GameStateResponse(
                success=False,
                message=f"Failed to decode payload as JSON: {payload_str}"
            )
            
    except Exception as e:
        logger.exception(f"Error saving game state: {str(e)}")
        return GameStateResponse(
            success=False,
            message=f"Error saving game state: {str(e)}"
        )

def cheat_get_sword(adventurer_name: str) -> GameStateResponse:
    """Cheat to get a sword instantly"""
    try:
        # Check if we're running locally with SAM
        is_local = os.environ.get('AWS_SAM_LOCAL') == 'true'
        
        if is_local:
            # For local SAM testing, use localhost URL
            logger.info("Running in SAM Local mode, using localhost URL")
            local_url = "http://localhost:3000"
            request = GameStateRequest(
                action=GameStateAction.SAVE,  # Use save as proxy for cheat
                adventurer_name=adventurer_name
            )
            
            response = requests.post(
                f"{local_url}/game-state/internal",
                json={"action": "cheat", "adventurer_name": adventurer_name}
            )
            
            if response.status_code == 200:
                return GameStateResponse(**response.json())
            else:
                logger.error(f"Failed to apply cheat: {response.status_code} - {response.text}")
                return GameStateResponse(
                    success=False,
                    message=f"Failed to apply cheat: {response.status_code}"
                )
        
        # For production, always use direct Lambda invocation
        logger.info("Using direct Lambda invocation")
        client = boto3.client('lambda')
        payload = json.dumps({
            "action": "cheat",
            "adventurer_name": adventurer_name,
            "source_function": "wizard"
        })
        
        response = client.invoke(
            FunctionName=os.environ.get('GAME_STATE_FUNCTION_NAME', 'GameStateFunction'),
            InvocationType='RequestResponse',
            Payload=payload
        )
        
        # Check for successful invocation
        if response.get('StatusCode') != 200:
            logger.error(f"Lambda invocation failed with status: {response.get('StatusCode')}")
            return GameStateResponse(
                success=False,
                message=f"Lambda invocation failed with status: {response.get('StatusCode')}"
            )
            
        payload_str = response['Payload'].read().decode('utf-8')
        logger.info(f"Received payload: {payload_str}")
        
        # Parse the payload
        try:
            payload = json.loads(payload_str)
            
            # Check for Lambda execution errors
            if 'errorMessage' in payload:
                logger.error(f"Lambda execution error: {payload}")
                return GameStateResponse(
                    success=False,
                    message=f"Lambda execution error: {payload.get('errorMessage')}"
                )
                
            return GameStateResponse(**payload)
        except json.JSONDecodeError:
            logger.error(f"Failed to decode payload as JSON: {payload_str}")
            return GameStateResponse(
                success=False,
                message=f"Failed to decode payload as JSON: {payload_str}"
            )
            
    except Exception as e:
        logger.exception(f"Error applying cheat: {str(e)}")
        return GameStateResponse(
            success=False,
            message=f"Error applying cheat: {str(e)}"
        )

@app.post("/wizard")
def handle_wizard_action():
    """Handle wizard actions"""
    try:
        # Parse request body
        request_data = app.current_event.json_body
        wizard_request = WizardRequest(**request_data)
        
        # Load existing state from GameState lambda
        response = get_game_state(wizard_request.game_state.adventurer_name)
        
        # Use saved state if it exists, otherwise use request state
        if response.success and response.game_state:
            game_state = response.game_state
            blacksmith_state = response.blacksmith_state
        else:
            game_state = wizard_request.game_state
            blacksmith_state = None
        
        # Initialize response
        action_response = ActionResponse(
            message="",
            game_state=game_state,
            blacksmith_state=blacksmith_state
        )
        
        # Process the action
        if wizard_request.action == WizardAction.KILL_WIZARD:
            handle_kill_wizard(wizard_request, action_response)
        elif wizard_request.action == WizardAction.TALK_TO_WIZARD:
            handle_talk_to_wizard(wizard_request, action_response)
        elif wizard_request.action == WizardAction.CHEAT:
            # Use the cheat function to give the player a sword
            cheat_response = cheat_get_sword(wizard_request.game_state.adventurer_name)
            if cheat_response.success:
                action_response.game_state = cheat_response.game_state
                action_response.blacksmith_state = cheat_response.blacksmith_state
                action_response.message = "The wizard chuckles and waves his hand. A sword materializes before you. 'Don't tell anyone I did that,' he winks."
            else:
                action_response.message = "The wizard's spell fizzles. 'Sorry, I can't seem to conjure a sword right now.'"
        
        # Save updated state to GameState lambda
        if wizard_request.action != WizardAction.CHEAT:  # Skip save if we already saved in the cheat function
            save_response = save_game_state(action_response.game_state, action_response.blacksmith_state)
            if not save_response.success:
                logger.error(f"Failed to save game state: {save_response.message}")
        
        return action_response.model_dump()
        
    except Exception as e:
        logger.exception("Error processing wizard action")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

def handle_kill_wizard(request: WizardRequest, response: ActionResponse):
    """Handle the kill wizard action"""
    if not response.game_state.quest_accepted:
        response.message = "You don't have a quest to kill the wizard. The wizard looks at you with amusement. 'Did someone send you to kill me? Or did you just wander in here on your own?'"
        return
        
    if not response.game_state.has_sword and response.game_state.sword_type == SwordType.NONE:
        response.message = "You try to attack the wizard with your bare hands. He laughs and waves his hand, sending you flying back out the door. 'Come back when you have a weapon at least!'"
        response.game_state.current_location = "town"
        return
        
    if response.game_state.sword_type == SwordType.HOLY:
        response.message = "You strike the wizard down with your holy sword. It glows with righteous power as it pierces through his dark defenses. The wizard screams as he dissolves into shadow. The town cheers for you when you return with news of your victory. Your adventure has come to an end."
        response.game_state.current_location = "town"
        response.game_state.quest_accepted = False
        response.game_over = True
        tracer.put_annotation("wizard_defeated", "true")
    elif response.game_state.sword_type == SwordType.EVIL:
        response.message = "As you raise your sword to strike, something strange happens. Your arm freezes mid-swing. The wizard's laughter echoes in the chamber as your vision begins to blur. 'Did you truly believe you could defeat me with that?' he asks, his voice suddenly seeming to come from inside your own head. You feel a cold sensation spreading through your body from your hand still gripping the sword. The world fades to darkness. Months later, villagers whisper of a new figure seen at the wizard's side, wearing your face but with eyes devoid of recognition. The adventure ends, but not in the way you had hoped."
        response.game_state.current_location = "wizard"
        response.game_over = True
        tracer.put_annotation("player_becomes_evil_minion", "true")
        logger.critical("The adventurer was consumed by the evil sword's power without understanding what was happening.")
    else:
        # Regular sword
        response.message = "You charge at the wizard with your ordinary sword. With a contemptuous flick of his wrist, he shatters your blade with magical force. The metal fragments turn to dust before they hit the ground. 'Pathetic,' the wizard sneers. 'Did you really think common steel could harm me?' You retreat hastily, knowing you'll need a more powerful weapon."
        response.game_state.current_location = "town"
        response.game_state.has_sword = False
        response.game_state.sword_type = SwordType.NONE
        tracer.put_annotation("sword_broken", "true")

def handle_talk_to_wizard(request: WizardRequest, response: ActionResponse):
    """Handle talking to the wizard"""
    if response.game_state.has_box:
        response.message = "The wizard notices the box in your pocket. 'Ah, you found my puzzle box! I've been looking for that. But it seems you haven't opened it yet.'"
    else:
        response.message = "The wizard eyes you suspiciously. 'What do you want? I'm very busy with my evil... err, important research.'"

@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
@tracer.capture_lambda_handler
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """Main Lambda handler"""
    # Check for API Gateway vs direct Lambda invocation
    if 'httpMethod' not in event:
        logger.info("Direct Lambda invocation detected")
        try:
            # Handle direct invocation if needed
            # Currently this lambda doesn't need to handle direct invocations
            return {
                'success': False,
                'message': 'Direct invocation not supported by this Lambda function'
            }
        except Exception as e:
            logger.exception(f"Error handling direct Lambda invocation: {str(e)}")
            return {
                'success': False,
                'message': f'Error handling request: {str(e)}'
            }
    
    # Otherwise handle as API Gateway request
    return app.resolve(event, context) 