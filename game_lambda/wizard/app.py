import json
import os
import requests
import boto3
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel
from aws_lambda_powertools import Logger, Metrics
from opentelemetry import trace
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import SpanKind
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.logging import correlation_paths
from opentelemetry.sdk.resources import Resource

service_name = "wizard"

# Initialize logging
logger = Logger()
metrics = Metrics()
# Set up OpenTelemetry tracing
resource = Resource.create({"service.name": service_name})
tracer_provider = TracerProvider(resource=resource)
otlp_span_exporter = OTLPSpanExporter()
span_processor = BatchSpanProcessor(otlp_span_exporter)
tracer_provider.add_span_processor(span_processor)
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer(service_name)

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

# Helper method to propagate trace context to downstream Lambda functions
def invoke_lambda_with_trace(function_name: str, payload: dict) -> dict:
    """Invoke a Lambda function with trace context propagation"""
    logger.info(f"Invoking Lambda function: {function_name}")
    
    # Create a copy of the payload to avoid modifying the original
    trace_payload = payload.copy()
    
    # Inject the current trace context into the payload
    inject(carrier=trace_payload)
    
    # Invoke the Lambda function with the trace context
    client = boto3.client('lambda')
    response = client.invoke(
        FunctionName=function_name,
        InvocationType='RequestResponse',
        Payload=json.dumps(trace_payload)
    )
    
    # Process the response
    if response.get('StatusCode') != 200:
        logger.error(f"Lambda invocation failed with status: {response.get('StatusCode')}")
        return None
    
    # Parse the response payload
    payload_str = response['Payload'].read().decode('utf-8')
    try:
        return json.loads(payload_str)
    except json.JSONDecodeError:
        logger.error(f"Failed to decode payload as JSON: {payload_str}")
        return None

# Game state API client
def get_game_state(adventurer_name: str) -> GameStateResponse:
    """Get game state from the game_state lambda"""
    with tracer.start_as_current_span("get_game_state") as span:
        try:
            span.set_attribute("adventurer_name", adventurer_name)
            
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
                
                # Create headers dict to inject trace context
                headers = {"Content-Type": "application/json"}
                inject(headers)
                
                response = requests.post(
                    f"{local_url}/game-state/internal",
                    json=request.model_dump(),
                    headers=headers
                )
                
                if response.status_code == 200:
                    return GameStateResponse(**response.json())
                else:
                    logger.error(f"Failed to get game state: {response.status_code} - {response.text}")
                    span.set_status(trace.StatusCode.ERROR, f"Failed to get game state: {response.status_code}")
                    return GameStateResponse(
                        success=False,
                        message=f"Failed to get game state: {response.status_code}"
                    )
            
            # For production, use Lambda invocation with trace context
            logger.info("Using direct Lambda invocation with trace context")
            payload = {
                "action": "get",
                "adventurer_name": adventurer_name,
                "source_function": "wizard"
            }
            
            # Invoke Lambda with trace context
            function_name = os.environ.get('GAME_STATE_FUNCTION_NAME', 'GameStateFunction')
            result = invoke_lambda_with_trace(function_name, payload)
            
            if result is None:
                span.set_status(trace.StatusCode.ERROR, "Failed to get response from Lambda")
                return GameStateResponse(
                    success=False,
                    message="Failed to get game state from Lambda"
                )
            
            # Check for Lambda execution errors
            if 'errorMessage' in result:
                logger.error(f"Lambda execution error: {result}")
                span.set_status(trace.StatusCode.ERROR, f"Lambda execution error: {result.get('errorMessage')}")
                return GameStateResponse(
                    success=False,
                    message=f"Lambda execution error: {result.get('errorMessage')}"
                )
                
            return GameStateResponse(**result)
                
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            logger.exception(f"Error getting game state: {str(e)}")
            return GameStateResponse(
                success=False,
                message=f"Error getting game state: {str(e)}"
            )

def save_game_state(game_state: GameState, blacksmith_state: Optional[BlacksmithState] = None) -> GameStateResponse:
    """Save game state using the game_state lambda"""
    with tracer.start_as_current_span("save_game_state") as span:
        try:
            span.set_attribute("adventurer_name", game_state.adventurer_name)
            span.set_attribute("has_sword", game_state.has_sword)
            span.set_attribute("sword_type", game_state.sword_type.value)
            
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
                
                # Create headers dict to inject trace context
                headers = {"Content-Type": "application/json"}
                inject(headers)
                
                response = requests.post(
                    f"{local_url}/game-state/internal",
                    json=request.model_dump(),
                    headers=headers
                )
                
                if response.status_code == 200:
                    return GameStateResponse(**response.json())
                else:
                    logger.error(f"Failed to save game state: {response.status_code} - {response.text}")
                    span.set_status(trace.StatusCode.ERROR, f"Failed to save game state: {response.status_code}")
                    return GameStateResponse(
                        success=False,
                        message=f"Failed to save game state: {response.status_code}"
                    )
            
            # For production, use Lambda invocation with trace context
            logger.info("Using direct Lambda invocation with trace context")
            payload = {
                "action": "save",
                "adventurer_name": game_state.adventurer_name,
                "game_state": game_state.model_dump() if game_state else None,
                "blacksmith_state": blacksmith_state.model_dump() if blacksmith_state else None,
                "source_function": "wizard"
            }
            
            # Invoke Lambda with trace context
            function_name = os.environ.get('GAME_STATE_FUNCTION_NAME', 'GameStateFunction')
            result = invoke_lambda_with_trace(function_name, payload)
            
            if result is None:
                span.set_status(trace.StatusCode.ERROR, "Failed to get response from Lambda")
                return GameStateResponse(
                    success=False,
                    message="Failed to save game state to Lambda"
                )
            
            # Check for Lambda execution errors
            if 'errorMessage' in result:
                logger.error(f"Lambda execution error: {result}")
                span.set_status(trace.StatusCode.ERROR, f"Lambda execution error: {result.get('errorMessage')}")
                return GameStateResponse(
                    success=False,
                    message=f"Lambda execution error: {result.get('errorMessage')}"
                )
                
            return GameStateResponse(**result)
                
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            logger.exception(f"Error saving game state: {str(e)}")
            return GameStateResponse(
                success=False,
                message=f"Error saving game state: {str(e)}"
            )

def cheat_get_sword(adventurer_name: str) -> GameStateResponse:
    """Cheat to get a sword instantly"""
    with tracer.start_as_current_span("cheat_get_sword") as span:
        try:
            span.set_attribute("adventurer_name", adventurer_name)
            span.set_attribute("action", "cheat")
            
            # Check if we're running locally with SAM
            is_local = os.environ.get('AWS_SAM_LOCAL') == 'true'
            
            if is_local:
                # For local SAM testing, use localhost URL
                logger.info("Running in SAM Local mode, using localhost URL")
                
                # Create headers dict to inject trace context
                headers = {"Content-Type": "application/json"}
                inject(headers)
                
                response = requests.post(
                    f"http://localhost:3000/game-state/internal",
                    json={"action": "cheat", "adventurer_name": adventurer_name},
                    headers=headers
                )
                
                if response.status_code == 200:
                    return GameStateResponse(**response.json())
                else:
                    logger.error(f"Failed to apply cheat: {response.status_code} - {response.text}")
                    span.set_status(trace.StatusCode.ERROR, f"Failed to apply cheat: {response.status_code}")
                    return GameStateResponse(
                        success=False,
                        message=f"Failed to apply cheat: {response.status_code}"
                    )
            
            # For production, use Lambda invocation with trace context
            logger.info("Using direct Lambda invocation with trace context")
            payload = {
                "action": "cheat",
                "adventurer_name": adventurer_name,
                "source_function": "wizard"
            }
            
            # Invoke Lambda with trace context
            function_name = os.environ.get('GAME_STATE_FUNCTION_NAME', 'GameStateFunction')
            result = invoke_lambda_with_trace(function_name, payload)
            
            if result is None:
                span.set_status(trace.StatusCode.ERROR, "Failed to get response from Lambda")
                return GameStateResponse(
                    success=False,
                    message="Failed to apply cheat"
                )
            
            # Check for Lambda execution errors
            if 'errorMessage' in result:
                logger.error(f"Lambda execution error: {result}")
                span.set_status(trace.StatusCode.ERROR, f"Lambda execution error: {result.get('errorMessage')}")
                return GameStateResponse(
                    success=False,
                    message=f"Lambda execution error: {result.get('errorMessage')}"
                )
            
            span.set_attribute("cheat_success", True)    
            return GameStateResponse(**result)
                
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            logger.exception(f"Error applying cheat: {str(e)}")
            return GameStateResponse(
                success=False,
                message=f"Error applying cheat: {str(e)}"
            )

@app.post("/wizard")
def handle_wizard_action():
    """Handle wizard actions"""
    with tracer.start_as_current_span("handle_wizard_action", kind=SpanKind.INTERNAL) as span:
        try:
            # Parse request body
            request_data = app.current_event.json_body
            wizard_request = WizardRequest(**request_data)
            
            # Add attributes to span
            span.set_attribute("adventurer_name", wizard_request.game_state.adventurer_name)
            span.set_attribute("action", wizard_request.action.value)
            span.set_attribute("current_location", wizard_request.game_state.current_location)
            span.set_attribute("has_sword", wizard_request.game_state.has_sword)
            span.set_attribute("sword_type", wizard_request.game_state.sword_type.value)
            
            # Load existing state from GameState lambda
            response = get_game_state(wizard_request.game_state.adventurer_name)
            
            # Use saved state if it exists, otherwise use request state
            if response.success and response.game_state:
                game_state = response.game_state
                blacksmith_state = response.blacksmith_state
                span.set_attribute("loaded_state", True)
            else:
                game_state = wizard_request.game_state
                blacksmith_state = None
                span.set_attribute("loaded_state", False)
            
            # Initialize response
            action_response = ActionResponse(
                message="",
                game_state=game_state,
                blacksmith_state=blacksmith_state
            )
            
            # Process the action
            action_span_name = f"process_{wizard_request.action.value}"
            with tracer.start_as_current_span(action_span_name) as action_span:
                if wizard_request.action == WizardAction.KILL_WIZARD:
                    handle_kill_wizard(wizard_request, action_response)
                    action_span.set_attribute("game_over", action_response.game_over)
                    action_span.set_attribute("current_location_after", action_response.game_state.current_location)
                elif wizard_request.action == WizardAction.TALK_TO_WIZARD:
                    handle_talk_to_wizard(wizard_request, action_response)
                elif wizard_request.action == WizardAction.CHEAT:
                    # Use the cheat function to give the player a sword
                    cheat_response = cheat_get_sword(wizard_request.game_state.adventurer_name)
                    if cheat_response.success:
                        action_response.game_state = cheat_response.game_state
                        action_response.blacksmith_state = cheat_response.blacksmith_state
                        action_response.message = "The wizard chuckles and waves his hand. A sword materializes before you. 'Don't tell anyone I did that,' he winks."
                        action_span.set_attribute("cheat_success", True)
                    else:
                        action_response.message = "The wizard's spell fizzles. 'Sorry, I can't seem to conjure a sword right now.'"
                        action_span.set_attribute("cheat_success", False)
            
            # Save updated state to GameState lambda
            if wizard_request.action != WizardAction.CHEAT:  # Skip save if we already saved in the cheat function
                with tracer.start_as_current_span("save_game_state_after_action") as save_span:
                    save_response = save_game_state(action_response.game_state, action_response.blacksmith_state)
                    if not save_response.success:
                        logger.error(f"Failed to save game state: {save_response.message}")
                        save_span.set_status(trace.StatusCode.ERROR, save_response.message)
                        span.set_attribute("save_success", False)
                    else:
                        span.set_attribute("save_success", True)
            
            return action_response.model_dump()
            
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            logger.exception("Error processing wizard action")
            return {
                "statusCode": 500,
                "body": json.dumps({"error": str(e)})
            }

def handle_kill_wizard(request: WizardRequest, response: ActionResponse):
    """Handle the kill wizard action"""
    with tracer.start_as_current_span("handle_kill_wizard") as span:
        span.set_attribute("adventurer_name", request.game_state.adventurer_name)
        span.set_attribute("has_sword", response.game_state.has_sword)
        span.set_attribute("sword_type", response.game_state.sword_type.value)
        span.set_attribute("quest_accepted", response.game_state.quest_accepted)
        
        if not response.game_state.quest_accepted:
            response.message = "You don't have a quest to kill the wizard. The wizard looks at you with amusement. 'Did someone send you to kill me? Or did you just wander in here on your own?'"
            span.set_attribute("scenario", "no_quest")
            return
            
        if not response.game_state.has_sword and response.game_state.sword_type == SwordType.NONE:
            response.message = "You try to attack the wizard with your bare hands. He laughs and waves his hand, sending you flying back out the door. 'Come back when you have a weapon at least!'"
            response.game_state.current_location = "town"
            span.set_attribute("scenario", "no_sword")
            span.set_attribute("location_changed", True)
            return
            
        if response.game_state.sword_type == SwordType.HOLY:
            response.message = "You strike the wizard down with your holy sword. It glows with righteous power as it pierces through his dark defenses. The wizard screams as he dissolves into shadow. The town cheers for you when you return with news of your victory. Your adventure has come to an end."
            response.game_state.current_location = "town"
            response.game_state.quest_accepted = False
            response.game_over = True
            span.set_attribute("scenario", "victory_holy_sword")
            span.set_attribute("wizard_defeated", True)
            span.set_attribute("game_over", True)
        elif response.game_state.sword_type == SwordType.EVIL:
            response.message = "As you raise your sword to strike, something strange happens. Your arm freezes mid-swing. The wizard's laughter echoes in the chamber as your vision begins to blur. 'Did you truly believe you could defeat me with that?' he asks, his voice suddenly seeming to come from inside your own head. You feel a cold sensation spreading through your body from your hand still gripping the sword. The world fades to darkness. Months later, villagers whisper of a new figure seen at the wizard's side, wearing your face but with eyes devoid of recognition. The adventure ends, but not in the way you had hoped."
            response.game_state.current_location = "wizard"
            response.game_over = True
            span.set_attribute("scenario", "evil_sword_possession")
            span.set_attribute("player_corrupted", True)
            span.set_attribute("game_over", True)
            logger.critical("The adventurer was consumed by the evil sword's power without understanding what was happening.")
        else:
            # Regular sword
            response.message = "You charge at the wizard with your ordinary sword. With a contemptuous flick of his wrist, he shatters your blade with magical force. The metal fragments turn to dust before they hit the ground. 'Pathetic,' the wizard sneers. 'Did you really think common steel could harm me?' You retreat hastily, knowing you'll need a more powerful weapon."
            response.game_state.current_location = "town"
            response.game_state.has_sword = False
            response.game_state.sword_type = SwordType.NONE
            span.set_attribute("scenario", "sword_broken")
            span.set_attribute("sword_broken", True)

def handle_talk_to_wizard(request: WizardRequest, response: ActionResponse):
    """Handle talking to the wizard"""
    with tracer.start_as_current_span("handle_talk_to_wizard") as span:
        span.set_attribute("adventurer_name", request.game_state.adventurer_name)
        span.set_attribute("has_box", response.game_state.has_box)
        
        if response.game_state.has_box:
            response.message = "The wizard notices the box in your pocket. 'Ah, you found my puzzle box! I've been looking for that. But it seems you haven't opened it yet.'"
            span.set_attribute("scenario", "has_box")
        else:
            response.message = "The wizard eyes you suspiciously. 'What do you want? I'm very busy with my evil... err, important research.'"
            span.set_attribute("scenario", "no_box")

@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """Lambda handler for wizard operations with OpenTelemetry tracing"""
    # Extract trace context from event headers for API Gateway requests
    headers = event.get('headers', {}) or {}
    
    # Check for API Gateway vs direct Lambda invocation
    if 'httpMethod' in event:
        # For API Gateway requests, extract context from headers
        extracted_context = extract(headers)
    else:
        # For direct Lambda invocations, extract context from the event payload itself
        # This handles cases where one Lambda invokes another and injects context into the payload
        extracted_context = extract(event)
    
    # Start a new span for the lambda handler with the extracted context
    with tracer.start_as_current_span(
        "lambda_handler", 
        context=extracted_context,
        kind=SpanKind.SERVER
    ) as span:
        try:
            # Add event information as span attributes
            span.set_attribute("service.name", service_name)
            span.set_attribute("function.name", context.function_name)
            span.set_attribute("cold_start", context.invoked_function_arn is not None)
            
            # Check for API Gateway vs direct Lambda invocation
            if 'httpMethod' in event:
                span.set_attribute("invocation.type", "api_gateway")
                span.set_attribute("http.method", event.get('httpMethod', ''))
                span.set_attribute("http.path", event.get('path', ''))
                if 'requestContext' in event and 'identity' in event.get('requestContext', {}):
                    span.set_attribute("client.ip", event.get('requestContext', {}).get('identity', {}).get('sourceIp', ''))
                
                # Handle API Gateway request
                result = app.resolve(event, context)
                logger.info("Lambda completing - API Gateway request")
                return result
            else:
                # Direct Lambda invocation
                logger.info("Direct Lambda invocation detected")
                span.set_attribute("invocation.type", "direct")
                
                # Handle direct invocation if needed
                # Extract source function if provided for better tracing
                if 'source_function' in event:
                    span.set_attribute("source_function", event.get('source_function'))
                
                try:
                    # Currently this lambda doesn't need to handle direct invocations
                    return {
                        'success': False,
                        'message': 'Direct invocation not supported by this Lambda function'
                    }
                except Exception as e:
                    logger.exception(f"Error handling direct Lambda invocation: {str(e)}")
                    span.record_exception(e)
                    span.set_status(trace.StatusCode.ERROR, str(e))
                    return {
                        'success': False,
                        'message': f'Error handling request: {str(e)}'
                    }
        except Exception as e:
            logger.exception(f"Error in lambda handler: {str(e)}")
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            raise 