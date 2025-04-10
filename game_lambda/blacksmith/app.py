import time
import json
import os
import requests
import boto3
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.logging import correlation_paths
# Import the Resource class to associate resources such as service name and instance ID with metrics, logs, and traces.
from opentelemetry.sdk.resources import Resource
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics.export import MetricReader, MetricExporter, MetricsData
from opentelemetry.sdk.metrics import TraceBasedExemplarFilter
from opentelemetry.context import _SUPPRESS_INSTRUMENTATION_KEY, attach, detach, set_value

service_name = "blacksmith"
# Initialize AWS Lambda Powertools
logger = Logger()
tracer = Tracer()
app = APIGatewayRestResolver()


class BatchExportingMetricReader(MetricReader):
    def __init__(self, exporter: MetricExporter):
        # Pass the exporter's preferred temporality and aggregation
        super().__init__(
            preferred_temporality=exporter._preferred_temporality,
            preferred_aggregation=exporter._preferred_aggregation,
        )
        self._exporter = exporter

    def _receive_metrics(self, metrics_data: MetricsData, timeout_millis=1000, **kwargs):
        # Export metrics data immediately after receiving it
        # Use the token pattern to suppress instrumentation during export
        token = attach(set_value(_SUPPRESS_INSTRUMENTATION_KEY, True))
        try:
            self._exporter.export(metrics_data, timeout_millis=timeout_millis, **kwargs)
            logger.info(f"Exported metrics: {metrics_data}")
        except Exception as e:
            logger.exception(f"Exception while exporting metrics: {e}")
        finally:
            detach(token)

    def force_flush(self, timeout_millis=10000) -> bool:
        """Forces flush of metrics to the exporter
        
        Args:
            timeout_millis: The maximum amount of time to wait for the flush
                to complete, in milliseconds.
                
        Returns:
            True if the flush was successful, False otherwise.
        """
        # First call the parent's force_flush which will trigger collect()
        super().force_flush(timeout_millis=timeout_millis)
        # Then call force_flush on the exporter
        return self._exporter.force_flush(timeout_millis=timeout_millis)

    def shutdown(self, timeout_millis=1000, **kwargs) -> None:
        """Shuts down the metric reader and exporter.
        
        Args:
            timeout_millis: The maximum amount of time to wait for the exporter
                to shutdown, in milliseconds.
        """
        self._exporter.shutdown(timeout_millis=timeout_millis, **kwargs)

class SimpleMetrics:
    """
    SimpleMetrics sets up metrics collection using OpenTelemetry with a short export interval.
    """
    def __init__(self, service_name):
        try:

            
            # Create the exporter
            self.exporter = OTLPMetricExporter()
            # Create an instance of the custom MetricReader
            self.metric_reader = BatchExportingMetricReader(self.exporter)

            
            # Set up resource information
            resource = Resource.create({
                "service.name": service_name,
                "service.instance.id": "game-play"
            })
            
            # Create MeterProvider with the reader and resource
            self.meter_provider = MeterProvider(
                metric_readers=[self.metric_reader],
                resource=resource,
                exemplar_filter=TraceBasedExemplarFilter()
            )
            
            # Set the global meter provider
            metrics.set_meter_provider(self.meter_provider)
            
            # Create a meter from the provider
            self.meter = metrics.get_meter(__name__)
            
            # Current forge heat value
            self.heat_value = 0
            
            # Create an observable gauge for the forge heat
            self.forge_heat_gauge = self.meter.create_gauge(
                name="forge_heat",
                description="The current heat level of the forge",
            )
            
            logger.info("Metrics configured with very short export interval")
        except Exception as e:
            logger.error(f"Error configuring metrics: {e}")
            self.meter = None
            self.meter_provider = None
            self.reader = None
            self.exporter = None
            self.heat_value = 0
    
    
    def set_forge_heat(self, heat):
        """Set the forge heat value, which will be picked up on the next observation"""
        old_heat = self.heat_value
        self.heat_value = heat
        self.forge_heat_gauge.set(self.heat_value, {"location": "blacksmith"})
        self.metric_reader.force_flush()
        logger.info(f"Forge heat updated: {old_heat} -> {heat}")

# Initialize metrics
metrics_instance = SimpleMetrics(service_name=service_name)



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

class BlacksmithAction(str, Enum):
    REQUEST_SWORD = "request_sword"
    HEAT_FORGE = "heat_forge"
    COOL_FORGE = "cool_forge"
    CHECK_SWORD = "check_sword"

class BlacksmithRequest(BaseModel):
    action: BlacksmithAction
    game_state: GameState
    blacksmith_state: Optional[BlacksmithState] = None

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
            "source_function": "blacksmith"
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
            "source_function": "blacksmith"
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

@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
@tracer.capture_lambda_handler
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """Main Lambda handler"""
    try:
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
        result = app.resolve(event, context)
        
        logger.info("Lambda completing")
            
        return result
    except Exception as e:
        logger.exception(f"Error in lambda handler: {str(e)}")
        raise

@app.post("/blacksmith")
def handle_blacksmith_action():
    """Handle blacksmith actions like requesting sword, heating forge, etc."""
    try:
        # Parse request body
        request_data = app.current_event.json_body
        blacksmith_request = BlacksmithRequest(**request_data)
        
        # Load existing state from GameState lambda
        response = get_game_state(blacksmith_request.game_state.adventurer_name)
        
        # Use saved state if it exists, otherwise use request state
        if response.success and response.game_state:
            game_state = response.game_state
            blacksmith_state = response.blacksmith_state or blacksmith_request.blacksmith_state or BlacksmithState()
        else:
            game_state = blacksmith_request.game_state
            blacksmith_state = blacksmith_request.blacksmith_state or BlacksmithState()
        
        # Initialize response
        action_response = ActionResponse(
            message="",
            game_state=game_state,
            blacksmith_state=blacksmith_state
        )
        
        # Process the action
        if blacksmith_request.action == BlacksmithAction.REQUEST_SWORD:
            handle_request_sword(blacksmith_request, action_response)
        elif blacksmith_request.action == BlacksmithAction.HEAT_FORGE:
            handle_heat_forge(blacksmith_request, action_response)
        elif blacksmith_request.action == BlacksmithAction.COOL_FORGE:
            handle_cool_forge(blacksmith_request, action_response)
        elif blacksmith_request.action == BlacksmithAction.CHECK_SWORD:
            handle_check_sword(blacksmith_request, action_response)
        
        # Save updated state to GameState lambda
        save_response = save_game_state(action_response.game_state, action_response.blacksmith_state)
        if not save_response.success:
            logger.error(f"Failed to save game state: {save_response.message}")
        
        return action_response.model_dump()
        
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
        
        # Check if forge is currently hot before resetting
        was_forge_hot = response.blacksmith_state.is_heating_forge
        
        # Reset forge state
        response.blacksmith_state.is_heating_forge = False
        response.blacksmith_state.heat = 0
        
        if was_forge_hot:
            logger.warning("Sword requested while forge was still hot")
            response.message = "The blacksmith looks at you with disappointment. He says, 'Fine, but be more careful this time! If the forge gets too hot, the sword will melt.'"
        else:
            response.message = "The blacksmith agrees to try again. 'Let's be more careful with the temperature this time,' he says."
        return
    elif response.game_state.failed_sword_attempts >= 3:
        logger.error("Too many failed sword attempts")
        response.message = "The blacksmith refuses to forge you another sword. You have wasted too much of his time."
        return
    
    response.blacksmith_state.sword_requested = True
    response.blacksmith_state.heat = 0  # Ensure heat starts at 0
    response.blacksmith_state.is_heating_forge = False  # Ensure heating state starts as false
    response.message = "The blacksmith agrees to forge you a sword. It will take some time and the forge needs to be heated to the correct temperature however."

def handle_heat_forge(request: BlacksmithRequest, response: ActionResponse):
    """Handle heating the forge"""
    if response.game_state.blacksmith_burned_down:
        response.message = "The blacksmith has burned down. There's nothing left to heat."
        return
        
    if not response.blacksmith_state.sword_requested:
        response.message = "The blacksmith wonders why you want to heat the forge when you haven't requested a sword."
        return
    
    response.blacksmith_state.is_heating_forge = True
    
    # Increase heat immediately (in the original game this would happen over time with a background thread)
    old_heat = response.blacksmith_state.heat
    response.blacksmith_state.heat += 5
    new_heat = response.blacksmith_state.heat
    
    # Update the metrics with the current forge heat through the set_forge_heat method
    logger.info(f"Updating forge heat: {old_heat} -> {new_heat}")
    metrics_instance.set_forge_heat(new_heat)
    
    # Check if the forge gets too hot and burns down the blacksmith (≥ 50)
    if response.blacksmith_state.heat >= 50:
        response.game_state.blacksmith_burned_down = True
        response.blacksmith_state.is_heating_forge = False
        response.message = "Oh no! The forge got too hot and burned down the entire blacksmith shop! You should run back to town."
        logger.error(f"Blacksmith burned down! Heat level: {response.blacksmith_state.heat}")
        tracer.put_annotation("blacksmith_burned_down", "true")
    else:
        response.message = "You add more coal to the forge. It heats up significantly."
        logger.info(f"Forge heated to {response.blacksmith_state.heat}")

def handle_cool_forge(request: BlacksmithRequest, response: ActionResponse):
    """Handle cooling the forge"""
    if response.game_state.blacksmith_burned_down:
        response.message = "The blacksmith has burned down. There's nothing left to cool."
        return
    
    old_heat = response.blacksmith_state.heat    
    response.blacksmith_state.heat = 0
    response.blacksmith_state.is_heating_forge = False
    
    # Update the metrics with the current forge heat through the set_forge_heat method
    logger.info(f"Cooling forge from {old_heat} to 0")
    metrics_instance.set_forge_heat(0)
    
    response.message = "You pour a bucket of water over the forge. The coals sizzle and the forge cools down completely."

def handle_check_sword(request: BlacksmithRequest, response: ActionResponse):
    """Handle checking if the sword is ready"""
    if not response.blacksmith_state.sword_requested:
        response.message = "You haven't requested a sword from the blacksmith yet."
        return
    
    heat = response.blacksmith_state.heat
    logger.info(f"Checking sword at forge heat: {heat}")
    
    # Proper heat is exactly 10
    if heat == 10:
        response.blacksmith_state.sword_requested = False
        response.game_state.has_sword = True
        response.game_state.sword_type = SwordType.REGULAR  # Set the sword type to REGULAR
        response.message = "The sword is ready. You take it from the blacksmith."
        logger.info("SUCCESS: Sword forged successfully at perfect temperature!")
        tracer.put_annotation("sword_forged", "true")
    elif heat > 10:
        # Too hot, sword melts
        response.blacksmith_state.sword_requested = False
        response.game_state.failed_sword_attempts += 1
        response.blacksmith_state.is_heating_forge = False  # Stop heating after failure
        response.message = "The sword has completely melted! The blacksmith looks at you with disappointment."
        logger.warning(f"FAIL: Sword melted due to excessive heat: {heat}")
        tracer.put_annotation("sword_melted", "true")
    else:
        # Not hot enough
        response.message = "The forge is not hot enough yet. The blacksmith tells you to wait."
        logger.info(f"Forge too cold for sword forging: {heat}/10")
        tracer.put_annotation("forge_too_cold", "true") 