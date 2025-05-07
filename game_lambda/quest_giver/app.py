import json
import os
import requests
import boto3
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel
from aws_lambda_powertools import Logger
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
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
import logging

service_name = "quest_giver"

# Initialize logging
logger = Logger()
# Set up OpenTelemetry tracing
resource = Resource.create({"service.name": service_name})
tracer_provider = TracerProvider(resource=resource)
otlp_span_exporter = OTLPSpanExporter()
span_processor = BatchSpanProcessor(otlp_span_exporter)
tracer_provider.add_span_processor(span_processor)
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer(service_name)

class CustomLogFW:
    """
    CustomLogFW sets up logging using OpenTelemetry with a specified service name and instance ID.
    """
    def __init__(self, service_name):
        try:
            # Create an instance of LoggerProvider with a Resource object.
            # Resource is used to include metadata like the service name and instance ID.
            self.logger_provider = LoggerProvider(
                resource=Resource.create(
                    {
                        "service.name": service_name,
                        "service.instance.id": "game-play"
                    }
                )
            )
            # Flag indicating that the logger provider is properly configured.
            self.logger_configured = True
        except Exception as e:
            # In case of error, set the logger provider to None and set the configured flag to False.
            self.logger_provider = None
            self.logger_configured = False
            print(f"Error configuring logging: {e}")

    def setup_logging(self):
        """
        Set up the logging configuration for OpenTelemetry.

        :return: A LoggingHandler instance configured with the logger provider.
        :raises: RuntimeError if the logger provider is not configured properly.
        """
        if not self.logger_configured:
            # If the logger provider wasn't set up correctly, raise an error.
            raise RuntimeError("LoggerProvider not configured correctly. Cannot set up logging.")

        # Set the created LoggerProvider as the global logger provider.
        set_logger_provider(self.logger_provider)

        exporter = OTLPLogExporter()

        # Add a BatchLogRecordProcessor to the logger provider.
        # This processor batches logs before sending them to the backend.
        self.logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(exporter=exporter, max_queue_size=5, max_export_batch_size=1)
        )

        # Create a LoggingHandler that integrates OpenTelemetry logging with the Python logging system.
        # Setting log level to NOTSET to capture all log levels.
        handler = LoggingHandler(level=logging.NOTSET, logger_provider=self.logger_provider)

        # Indicate successful logging configuration.
        print("Logging configured with OpenTelemetry.")

        return handler

logFW = CustomLogFW(service_name=service_name)
handler = logFW.setup_logging()

# Get the logger and add the handler
gamelogs = logging.getLogger("game-play")
gamelogs.addHandler(handler)
gamelogs.setLevel(logging.INFO)

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

class QuestAction(str, Enum):
    ACCEPT_QUEST = "accept_quest"
    CHECK_PROGRESS = "check_progress"

class QuestRequest(BaseModel):
    action: QuestAction
    game_state: GameState

class ActionResponse(BaseModel):
    message: str
    game_state: GameState
    blacksmith_state: Optional[BlacksmithState] = None
    success: bool = True

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
    try:
        # Create a span for this operation
        with tracer.start_as_current_span("get_game_state", kind=SpanKind.CLIENT) as span:
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
                    span.set_attribute("http.status_code", response.status_code)
                    return GameStateResponse(**response.json())
                else:
                    logger.error(f"Failed to get game state: {response.status_code} - {response.text}")
                    span.set_attribute("http.status_code", response.status_code)
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
                "source_function": "quest_giver"
            }
            
            # Invoke Lambda with trace context
            function_name = os.environ.get('GAME_STATE_FUNCTION_NAME', 'GameStateFunction')
            result = invoke_lambda_with_trace(function_name, payload)
            
            if result is None:
                span.set_status(trace.StatusCode.ERROR, "Failed to get game state from Lambda")
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
        logger.exception(f"Error getting game state: {str(e)}")
        # If we're in an active span context, record the exception
        current_span = trace.get_current_span()
        if current_span:
            current_span.record_exception(e)
            current_span.set_status(trace.StatusCode.ERROR, str(e))
        return GameStateResponse(
            success=False,
            message=f"Error getting game state: {str(e)}"
        )

def save_game_state(game_state: GameState, blacksmith_state: Optional[BlacksmithState] = None) -> GameStateResponse:
    """Save game state using the game_state lambda"""
    try:
        # Create a span for this operation
        with tracer.start_as_current_span("save_game_state", kind=SpanKind.CLIENT) as span:
            span.set_attribute("adventurer_name", game_state.adventurer_name)
            
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
                    span.set_attribute("http.status_code", response.status_code)
                    return GameStateResponse(**response.json())
                else:
                    logger.error(f"Failed to save game state: {response.status_code} - {response.text}")
                    span.set_attribute("http.status_code", response.status_code)
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
                "source_function": "quest_giver"
            }
            
            # Invoke Lambda with trace context
            function_name = os.environ.get('GAME_STATE_FUNCTION_NAME', 'GameStateFunction')
            result = invoke_lambda_with_trace(function_name, payload)
            
            if result is None:
                span.set_status(trace.StatusCode.ERROR, "Failed to save game state to Lambda")
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
        logger.exception(f"Error saving game state: {str(e)}")
        # If we're in an active span context, record the exception
        current_span = trace.get_current_span()
        if current_span:
            current_span.record_exception(e)
            current_span.set_status(trace.StatusCode.ERROR, str(e))
        return GameStateResponse(
            success=False,
            message=f"Error saving game state: {str(e)}"
        )

@app.post("/quest-giver")
def handle_quest_giver_action():
    """Handle quest giver actions"""
    # Create a new span for handling quest giver actions
    with tracer.start_as_current_span(
        "handle_quest_giver_action",
        kind=SpanKind.INTERNAL
    ) as span:
        try:
            # Parse request body
            request_data = app.current_event.json_body
            quest_request = QuestRequest(**request_data)
            
            # Add attributes to span
            span.set_attribute("adventurer_name", quest_request.game_state.adventurer_name)
            span.set_attribute("action", quest_request.action.value)
            span.set_attribute("current_location", quest_request.game_state.current_location)
            
            # Load existing state from GameState lambda
            response = get_game_state(quest_request.game_state.adventurer_name)
            
            # Use saved state if it exists, otherwise use request state
            if response.success and response.game_state:
                game_state = response.game_state
            else:
                game_state = quest_request.game_state
            
            # Initialize response
            action_response = ActionResponse(
                message="",
                game_state=game_state,
                blacksmith_state=None
            )
            
            # Process the action
            action_span_name = f"process_{quest_request.action.value}"
            with tracer.start_as_current_span(action_span_name) as action_span:
                if quest_request.action == QuestAction.ACCEPT_QUEST:
                    handle_accept_quest(quest_request, action_response)
                elif quest_request.action == QuestAction.CHECK_PROGRESS:
                    handle_check_progress(quest_request, action_response)
            
            # Save updated state to GameState lambda
            save_response = save_game_state(action_response.game_state)
            if not save_response.success:
                logger.error(f"Failed to save game state: {save_response.message}")
                span.set_status(trace.StatusCode.ERROR, save_response.message)
            
            return action_response.model_dump()
            
        except Exception as e:
            logger.exception("Error processing quest action")
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            return {
                "statusCode": 500,
                "body": json.dumps({"error": str(e)})
            }

def handle_accept_quest(request: QuestRequest, response: ActionResponse):
    """Handle accepting a quest"""
    with tracer.start_as_current_span("handle_accept_quest") as span:
        span.set_attribute("has_sword", response.game_state.has_sword)
        span.set_attribute("sword_type", response.game_state.sword_type)
        span.set_attribute("quest_givers_killed", response.game_state.quest_givers_killed)
        
        # Check if the player has a holy sword and the quest giver was killed
        if response.game_state.sword_type == SwordType.HOLY and response.game_state.quest_givers_killed > 0:
            # Holy sword resurrects the quest giver!
            response.game_state.quest_givers_killed = 0
            response.game_state.quest_accepted = True
            response.message = "As you approach the fallen quest giver, your holy sword begins to glow with an intense radiance. A beam of light extends from the blade to the quest giver's heart. Color returns to his face, and he gasps, drawing breath again! He sits up, looking at you with awe. 'You... you brought me back from death's door! Your sword truly has divine power.' He stands shakily. 'I owe you my life. The quest to defeat the wizard is yours, brave adventurer. That holy blade is exactly what's needed to vanquish the evil that plagues us.'"
            gamelogs.info("MIRACLE: The holy sword has resurrected the quest giver from death!")
            span.set_attribute("quest_giver_resurrected", "true")
            span.set_attribute("result", "quest_giver_resurrected")
            logger.info("The holy sword resurrected the quest giver!")
            return
        elif response.game_state.quest_accepted:
            response.message = "You have already accepted the quest to kill the evil wizard."
            span.set_attribute("result", "already_accepted")
        elif response.game_state.quest_givers_killed > 0:
            response.message = "The quest giver lies motionless on the ground. He can no longer give you any quests."
            span.set_attribute("result", "quest_giver_dead")
        elif response.game_state.sword_type == SwordType.EVIL:
            # Evil sword kills the quest giver but does NOT set quest_accepted
            response.game_state.quest_givers_killed += 1
            response.message = "As you approach the quest giver, you feel a strange sensation in your arm. Your hand tightens on your sword involuntarily. The quest giver suddenly gasps, turns pale, and collapses to the ground. What just happened? You hear a faint whisper but can't make out the words."
            gamelogs.fatal("MURDER: The evil sword has taken control and killed the quest giver without the adventurer's knowledge!")
            span.set_attribute("quest_giver_killed", "true")
            span.set_attribute("result", "quest_giver_killed")
            logger.critical("The evil sword killed the quest giver without the adventurer realizing it!")
            # Ensure quest is not accepted when quest giver is killed
            response.game_state.quest_accepted = False
        elif not response.game_state.has_sword and response.game_state.sword_type == SwordType.NONE:
            # Player doesn't have a sword
            response.message = "The quest giver looks at your empty hands and shakes his head. 'You'll need a sword before you can accept this quest. Visit the blacksmith first.'"
            span.set_attribute("quest_rejected_no_sword", "true")
            span.set_attribute("result", "no_sword")
        elif response.game_state.sword_type == SwordType.HOLY:
            response.game_state.quest_accepted = True
            response.message = "The quest giver's eyes widen at the sight of your holy sword. 'By the gods! That blade... it's perfect!' He excitedly explains your quest to defeat the evil wizard, practically bouncing with enthusiasm. 'With a holy sword like that, the wizard doesn't stand a chance! This is the first time I've ever felt truly confident sending someone to face him. The town will remember your name forever!'"
            gamelogs.info("The quest giver was impressed by the holy sword and confidently gave the quest.")
            span.set_attribute("quest_accepted_holy_sword", "true")
            span.set_attribute("result", "quest_accepted_holy_sword")
        else:
            # Regular sword
            response.game_state.quest_accepted = True
            response.message = "The quest giver looks at your ordinary sword with evident disappointment. He sighs deeply. 'Well... I suppose this sword is better than nothing. The evil wizard is incredibly powerful, you know. I honestly don't think you'll survive with just that, but I'm desperate enough to try.' He reluctantly gives you the quest, not making eye contact. 'Maybe visit the chapel or find someone to enhance that blade before you face him.'"
            span.set_attribute("quest_accepted", "true")
            span.set_attribute("result", "quest_accepted_regular_sword")

def handle_check_progress(request: QuestRequest, response: ActionResponse):
    """Handle checking the progress of a quest"""
    with tracer.start_as_current_span("handle_check_progress") as span:
        span.set_attribute("has_sword", response.game_state.has_sword)
        span.set_attribute("sword_type", response.game_state.sword_type)
        span.set_attribute("quest_accepted", response.game_state.quest_accepted)
        span.set_attribute("quest_givers_killed", response.game_state.quest_givers_killed)
        
        # Check if the player has a holy sword and the quest giver was killed
        if response.game_state.sword_type == SwordType.HOLY and response.game_state.quest_givers_killed > 0:
            # Holy sword gives off a glow near the fallen quest giver
            response.message = "As you approach the fallen quest giver, your holy sword begins to pulse with a soft light. The closer you get to the motionless body, the more intense the glow becomes. Perhaps there's something you can do with your holy sword here?"
            gamelogs.info("The holy sword is reacting to the dead quest giver, indicating resurrection potential.")
            span.set_attribute("holy_sword_reacts_to_dead_quest_giver", "true")
            span.set_attribute("result", "holy_sword_reacts")
            return
        elif response.game_state.quest_givers_killed > 0:
            response.message = "You find the quest giver lying motionless on the ground. Some townsfolk are gathered around, whispering about a mysterious death. One of them looks at your sword with suspicion."
            span.set_attribute("result", "quest_giver_dead")
        elif response.game_state.sword_type == SwordType.EVIL and not response.game_state.quest_accepted:
            # If they have an evil sword but no quest, they must have killed the quest giver with it
            response.game_state.quest_givers_killed += 1
            response.message = "As you approach where the quest giver was standing, you notice he's lying on the ground, motionless. Nearby townsfolk whisper and point at your sword. One covers their mouth in horror. What happened here?"
            gamelogs.error("The player has discovered the quest giver's body. They don't realize their evil sword is responsible for the murder.")
            span.set_attribute("quest_giver_death_discovered", "true")
            span.set_attribute("result", "quest_giver_death_discovered")
        elif not response.game_state.quest_accepted:
            response.message = "You haven't accepted any quests yet."
            span.set_attribute("result", "no_quest_accepted")
        elif response.game_state.sword_type == SwordType.HOLY:
            response.message = "The quest giver beams at your holy sword with reverence. 'You're absolutely ready to face the wizard. That radiant blade will pierce right through his dark magic! I'm already preparing the celebration for your victorious return!'"
            gamelogs.info("The quest giver admires the holy sword and fully supports the adventurer's quest.")
            span.set_attribute("result", "holy_sword_praised")
        elif response.game_state.sword_type == SwordType.EVIL:
            response.message = "The quest giver looks at your sword with an expression you can't quite read. 'That sword... it has a strange aura about it. But perhaps it's powerful enough to defeat the wizard.'"
            gamelogs.warning("The quest giver senses something wrong with the adventurer's evil sword but doesn't recognize its true danger.")
            span.set_attribute("result", "evil_sword_not_recognized")
        elif response.game_state.has_sword:
            response.message = "The quest giver glances at your ordinary sword with the same disappointment as before. 'Still carrying that plain blade, I see. Look, I'm not trying to be rude, but... the wizard has killed dozens of warriors better equipped than you. Please find someone to enhance that sword if you value your life.'"
            span.set_attribute("result", "regular_sword_criticized")
        else:
            response.message = "The quest giver looks shocked. 'What happened to your sword? Did you lose it? The wizard will incinerate you in seconds without a weapon! Start by visiting the blacksmith again.'"
            span.set_attribute("result", "sword_missing")

# Replace Powertools tracer decorator with OpenTelemetry tracing
@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """Main Lambda handler with OpenTelemetry tracing"""
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