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
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
import logging

service_name = "chapel"

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

class ChapelAction(str, Enum):
    LOOK_AT_SWORD = "look_at_sword"
    PRAY = "pray"

class ChapelRequest(BaseModel):
    action: ChapelAction
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
            "source_function": "chapel"
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
            "source_function": "chapel"
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

@app.post("/chapel")
@tracer.capture_method
def handle_chapel_action():
    """Handle chapel actions"""
    try:
        # Parse request body
        request_data = app.current_event.json_body
        chapel_request = ChapelRequest(**request_data)
        
        # Load existing state from GameState lambda
        response = get_game_state(chapel_request.game_state.adventurer_name)
        
        # Use saved state if it exists, otherwise use request state
        if response.success and response.game_state:
            game_state = response.game_state
            logger.info(f"Loaded existing game state for {game_state.adventurer_name}: has_sword={game_state.has_sword}, sword_type={game_state.sword_type}")
        else:
            game_state = chapel_request.game_state
            logger.info(f"Using request game state for {game_state.adventurer_name}: has_sword={game_state.has_sword}, sword_type={game_state.sword_type}")
        
        # Initialize response
        action_response = ActionResponse(
            message="",
            game_state=game_state,
            blacksmith_state=None
        )
        
        # Process the action
        if chapel_request.action == ChapelAction.LOOK_AT_SWORD:
            handle_look_at_sword(chapel_request, action_response)
        elif chapel_request.action == ChapelAction.PRAY:
            handle_pray(chapel_request, action_response)
            logger.info(f"After prayer: has_sword={action_response.game_state.has_sword}, sword_type={action_response.game_state.sword_type}")
        
        # Save updated state to GameState lambda
        save_response = save_game_state(action_response.game_state)
        if save_response.success:
            logger.info(f"Successfully saved game state with sword_type={action_response.game_state.sword_type}")
        else:
            logger.error(f"Failed to save game state: {save_response.message}")
        
        return action_response.model_dump()
        
    except Exception as e:
        logger.exception("Error processing chapel action")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

def handle_look_at_sword(request: ChapelRequest, response: ActionResponse):
    """Handle looking at the sword in the chapel"""
    if not response.game_state.has_sword and response.game_state.sword_type == SwordType.NONE:
        response.message = "You don't have a sword to look at."
    elif response.game_state.sword_type == SwordType.HOLY:
        response.message = "Your sword glows with a holy light. It feels powerful and righteous in your hand."
        gamelogs.info("Adventurer examines their holy sword in the chapel, strengthening its connection to the divine.")
    elif response.game_state.sword_type == SwordType.EVIL:
        response.message = "Your sword feels strange in the chapel. The metal seems darker than you remember, and it feels uncomfortably cold to the touch. The priest studies it with a concerned expression."
        gamelogs.warning("An evil sword was brought into the chapel. The priest has noticed its dark aura.")
    else:
        response.message = "It's just a regular sword. Nothing special about it."

def handle_pray(request: ChapelRequest, response: ActionResponse):
    """Handle praying in the chapel"""
    if not response.game_state.priest_alive:
        response.message = "The chapel is empty. The priest is no longer here, having sacrificed himself to purify your sword."
        return

    if not response.game_state.has_sword and response.game_state.sword_type == SwordType.NONE:
        response.message = "You pray for guidance on your adventure."
    elif response.game_state.sword_type == SwordType.EVIL:
        # Priest sacrifices himself to remove the curse
        response.game_state.priest_alive = False
        response.game_state.sword_type = SwordType.HOLY
        # Ensure has_sword is true even though we're converting from evil to holy
        response.game_state.has_sword = True
        response.message = "The priest looks at your sword with alarm. 'There is something wrong with this blade,' he whispers. He takes the sword from your hands and begins to pray over it. Suddenly, he gasps in pain as the metal begins to glow. 'I will... take this burden...' he manages to say. The priest collapses to the ground, his life force draining away. When you take back the sword, it feels different - lighter, warmer, and it now emits a soft, golden light."
        gamelogs.critical("The priest sacrificed his life to transform the evil sword into a holy one!")
        tracer.put_annotation("sword_blessed", "true")
        tracer.put_annotation("priest_died", "true")
    elif response.game_state.has_sword:
        response.game_state.sword_type = SwordType.HOLY
        response.message = "The priest blesses your sword. It now glows with a holy light."
        gamelogs.info("The priest blessed a regular sword, transforming it into a holy sword.")
        tracer.put_annotation("sword_blessed", "true")
    else:
        response.message = "You pray for guidance on your adventure."

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