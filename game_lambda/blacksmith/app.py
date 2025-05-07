import time
import json
import os
import requests
import boto3
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel
from aws_lambda_powertools import Logger
# Remove Powertools Tracer and import OpenTelemetry tracing
from opentelemetry import trace
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import SpanKind
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
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
                return GameStateResponse(
                    success=False,
                    message=f"Failed to get game state: {response.status_code}"
                )
        
        # For production, use Lambda invocation with trace context
        logger.info("Using direct Lambda invocation with trace context")
        payload = {
            "action": "get",
            "adventurer_name": adventurer_name,
            "source_function": "blacksmith"
        }
        
        # Invoke Lambda with trace context
        function_name = os.environ.get('GAME_STATE_FUNCTION_NAME', 'GameStateFunction')
        result = invoke_lambda_with_trace(function_name, payload)
        
        if result is None:
            return GameStateResponse(
                success=False,
                message="Failed to get game state from Lambda"
            )
        
        # Check for Lambda execution errors
        if 'errorMessage' in result:
            logger.error(f"Lambda execution error: {result}")
            return GameStateResponse(
                success=False,
                message=f"Lambda execution error: {result.get('errorMessage')}"
            )
            
        return GameStateResponse(**result)
            
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
            "source_function": "blacksmith"
        }
        
        # Invoke Lambda with trace context
        function_name = os.environ.get('GAME_STATE_FUNCTION_NAME', 'GameStateFunction')
        result = invoke_lambda_with_trace(function_name, payload)
        
        if result is None:
            return GameStateResponse(
                success=False,
                message="Failed to save game state to Lambda"
            )
        
        # Check for Lambda execution errors
        if 'errorMessage' in result:
            logger.error(f"Lambda execution error: {result}")
            return GameStateResponse(
                success=False,
                message=f"Lambda execution error: {result.get('errorMessage')}"
            )
            
        return GameStateResponse(**result)
            
    except Exception as e:
        logger.exception(f"Error saving game state: {str(e)}")
        return GameStateResponse(
            success=False,
            message=f"Error saving game state: {str(e)}"
        )

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

@app.post("/blacksmith")
def handle_blacksmith_action():
    """Handle blacksmith actions like requesting sword, heating forge, etc."""
    # Create a new span for handling blacksmith actions
    with tracer.start_as_current_span(
        "handle_blacksmith_action",
        kind=SpanKind.INTERNAL
    ) as span:
        try:
            # Parse request body
            request_data = app.current_event.json_body
            blacksmith_request = BlacksmithRequest(**request_data)
            
            # Add attributes to span
            span.set_attribute("adventurer_name", blacksmith_request.game_state.adventurer_name)
            span.set_attribute("action", blacksmith_request.action.value)
            span.set_attribute("current_location", blacksmith_request.game_state.current_location)
            
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
            action_span_name = f"process_{blacksmith_request.action.value}"
            with tracer.start_as_current_span(action_span_name) as action_span:
                if blacksmith_request.action == BlacksmithAction.REQUEST_SWORD:
                    handle_request_sword(blacksmith_request, action_response)
                elif blacksmith_request.action == BlacksmithAction.HEAT_FORGE:
                    handle_heat_forge(blacksmith_request, action_response)
                elif blacksmith_request.action == BlacksmithAction.COOL_FORGE:
                    handle_cool_forge(blacksmith_request, action_response)
                elif blacksmith_request.action == BlacksmithAction.CHECK_SWORD:
                    handle_check_sword(blacksmith_request, action_response)
            
            # Save updated state to GameState lambda
            with tracer.start_as_current_span("save_game_state") as save_span:
                save_response = save_game_state(action_response.game_state, action_response.blacksmith_state)
                if not save_response.success:
                    logger.error(f"Failed to save game state: {save_response.message}")
                    save_span.set_status(trace.StatusCode.ERROR, save_response.message)
            
            return action_response.model_dump()
            
        except Exception as e:
            logger.exception("Error processing blacksmith action")
            span.record_exception(e)
            span.set_status(trace.StatusCode.ERROR, str(e))
            return {
                "statusCode": 500,
                "body": json.dumps({"error": str(e)})
            }

def handle_request_sword(request: BlacksmithRequest, response: ActionResponse):
    """Handle the request sword action"""
    with tracer.start_as_current_span("handle_request_sword") as span:
        span.set_attribute("adventurer_name", request.game_state.adventurer_name)
        
        if response.game_state.has_sword:
            response.message = "You already have a sword. You don't need another one."
            span.set_attribute("already_has_sword", True)
            return
        
        if response.game_state.failed_sword_attempts > 0 and response.game_state.failed_sword_attempts < 3:
            response.blacksmith_state.sword_requested = True
            
            # Check if forge is currently hot before resetting
            was_forge_hot = response.blacksmith_state.is_heating_forge
            
            # Reset forge state
            response.blacksmith_state.is_heating_forge = False
            response.blacksmith_state.heat = 0
            
            span.set_attribute("failed_sword_attempts", response.game_state.failed_sword_attempts)
            span.set_attribute("was_forge_hot", was_forge_hot)
            
            if was_forge_hot:
                logger.warning("Sword requested while forge was still hot")
                response.message = "The blacksmith looks at you with disappointment. He says, 'Fine, but be more careful this time! If the forge gets too hot, the sword will melt.'"
            else:
                response.message = "The blacksmith agrees to try again. 'Let's be more careful with the temperature this time,' he says."
            return
        elif response.game_state.failed_sword_attempts >= 3:
            logger.error("Too many failed sword attempts")
            span.set_attribute("too_many_failures", True)
            span.set_attribute("failed_sword_attempts", response.game_state.failed_sword_attempts)
            response.message = "The blacksmith refuses to forge you another sword. You have wasted too much of his time."
            return
        
        response.blacksmith_state.sword_requested = True
        response.blacksmith_state.heat = 0  # Ensure heat starts at 0
        response.blacksmith_state.is_heating_forge = False  # Ensure heating state starts as false
        response.message = "The blacksmith agrees to forge you a sword. It will take some time and the forge needs to be heated to the correct temperature however."
        span.set_attribute("sword_requested", True)

def handle_heat_forge(request: BlacksmithRequest, response: ActionResponse):
    """Handle heating the forge"""
    with tracer.start_as_current_span("handle_heat_forge") as span:
        span.set_attribute("adventurer_name", request.game_state.adventurer_name)
        
        if response.game_state.blacksmith_burned_down:
            response.message = "The blacksmith has burned down. There's nothing left to heat."
            span.set_attribute("blacksmith_burned_down", True)
            return
            
        if not response.blacksmith_state.sword_requested:
            response.message = "The blacksmith wonders why you want to heat the forge when you haven't requested a sword."
            span.set_attribute("sword_requested", False)
            return
        
        span.set_attribute("sword_requested", True)
        response.blacksmith_state.is_heating_forge = True
        
        # Increase heat immediately (in the original game this would happen over time with a background thread)
        old_heat = response.blacksmith_state.heat
        response.blacksmith_state.heat += 5
        new_heat = response.blacksmith_state.heat
        
        span.set_attribute("forge_heat_before", old_heat)
        span.set_attribute("forge_heat_after", new_heat)
        
        # Update the metrics with the current forge heat through the set_forge_heat method
        logger.info(f"Updating forge heat: {old_heat} -> {new_heat}")
        metrics_instance.set_forge_heat(new_heat)
        
        # Check if the forge gets too hot and burns down the blacksmith (≥ 50)
        if response.blacksmith_state.heat >= 50:
            response.game_state.blacksmith_burned_down = True
            response.blacksmith_state.is_heating_forge = False
            response.message = "Oh no! The forge got too hot and burned down the entire blacksmith shop! You should run back to town."
            logger.error(f"Blacksmith burned down! Heat level: {response.blacksmith_state.heat}")
            span.set_attribute("blacksmith_burned_down", True)
            span.set_status(trace.StatusCode.ERROR, "Blacksmith burned down due to excessive heat")
        else:
            response.message = "You add more coal to the forge. It heats up significantly."
            logger.info(f"Forge heated to {response.blacksmith_state.heat}")

def handle_cool_forge(request: BlacksmithRequest, response: ActionResponse):
    """Handle cooling the forge"""
    with tracer.start_as_current_span("handle_cool_forge") as span:
        span.set_attribute("adventurer_name", request.game_state.adventurer_name)
        
        if response.game_state.blacksmith_burned_down:
            response.message = "The blacksmith has burned down. There's nothing left to cool."
            span.set_attribute("blacksmith_burned_down", True)
            return
        
        old_heat = response.blacksmith_state.heat    
        response.blacksmith_state.heat = 0
        response.blacksmith_state.is_heating_forge = False
        
        span.set_attribute("forge_heat_before", old_heat)
        span.set_attribute("forge_heat_after", 0)
        
        # Update the metrics with the current forge heat through the set_forge_heat method
        logger.info(f"Cooling forge from {old_heat} to 0")
        metrics_instance.set_forge_heat(0)
        
        response.message = "You pour a bucket of water over the forge. The coals sizzle and the forge cools down completely."

def handle_check_sword(request: BlacksmithRequest, response: ActionResponse):
    """Handle checking if the sword is ready"""
    with tracer.start_as_current_span("handle_check_sword") as span:
        span.set_attribute("adventurer_name", request.game_state.adventurer_name)
        
        if not response.blacksmith_state.sword_requested:
            response.message = "You haven't requested a sword from the blacksmith yet."
            span.set_attribute("sword_requested", False)
            return
        
        heat = response.blacksmith_state.heat
        logger.info(f"Checking sword at forge heat: {heat}")
        span.set_attribute("forge_heat", heat)
        span.set_attribute("sword_requested", True)
        
        # Proper heat is exactly 10
        if heat == 10:
            response.blacksmith_state.sword_requested = False
            response.game_state.has_sword = True
            response.game_state.sword_type = SwordType.REGULAR  # Set the sword type to REGULAR
            response.message = "The sword is ready. You take it from the blacksmith."
            logger.info("SUCCESS: Sword forged successfully at perfect temperature!")
            span.set_attribute("sword_forged", True)
            span.set_attribute("sword_type", "regular")
        elif heat > 10:
            # Too hot, sword melts
            response.blacksmith_state.sword_requested = False
            response.game_state.failed_sword_attempts += 1
            response.blacksmith_state.is_heating_forge = False  # Stop heating after failure
            response.message = "The sword has completely melted! The blacksmith looks at you with disappointment."
            logger.warning(f"FAIL: Sword melted due to excessive heat: {heat}")
            span.set_attribute("sword_melted", True)
            span.set_attribute("failed_sword_attempts", response.game_state.failed_sword_attempts)
            span.set_status(trace.StatusCode.ERROR, "Sword melted due to excessive heat")
        else:
            # Not hot enough
            response.message = "The forge is not hot enough yet. The blacksmith tells you to wait."
            logger.info(f"Forge too cold for sword forging: {heat}/10")
            span.set_attribute("forge_too_cold", True) 