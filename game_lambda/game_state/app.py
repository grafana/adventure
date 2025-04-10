import json
import os
import time
import boto3
import traceback
from enum import Enum
from typing import Optional, Tuple, Dict, Any, ForwardRef
from pydantic import BaseModel
from aws_lambda_powertools import Logger, Metrics
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.logging import correlation_paths
from botocore.exceptions import ClientError
# Import OpenTelemetry modules for metrics
from opentelemetry.sdk.resources import Resource
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics.export import MetricReader, MetricExporter, MetricsData
from opentelemetry.sdk.metrics import TraceBasedExemplarFilter
from opentelemetry.context import _SUPPRESS_INSTRUMENTATION_KEY, attach, detach, set_value

service_name = "game_state"

# Initialize AWS Lambda Powertools
logger = Logger()
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

class CustomMetrics:
    """
    CustomMetrics sets up metrics collection using OpenTelemetry with a short export interval.
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
            
            # Store the current sword counts as instance variables
            self.regular_sword_count = 0
            self.holy_sword_count = 0
            self.evil_sword_count = 0
            
            # Create gauges for sword types
            self.regular_sword_gauge = self.meter.create_gauge(
                name="swords",
                description="The number of regular swords owned"
            )
            
            self.holy_sword_gauge = self.meter.create_gauge(
                name="holy_sword",
                description="The number of holy swords owned"
            )
            
            self.evil_sword_gauge = self.meter.create_gauge(
                name="evil_sword",
                description="The number of evil swords owned"
            )
            
            logger.info("Metrics configured with very short export interval")
        except Exception as e:
            logger.error(f"Error configuring metrics: {e}")
            self.meter = None
            self.meter_provider = None
            self.reader = None
            self.exporter = None
            self.regular_sword_count = 0
            self.holy_sword_count = 0
            self.evil_sword_count = 0
    
    def get_meter(self):
        return self.meter
    
    def track_sword_state(self, game_state):
        """Track sword state changes with metrics"""
        if not self.meter:
            return
            
        try:
            # Set the counts based on current state
            old_regular = self.regular_sword_count
            old_holy = self.holy_sword_count
            old_evil = self.evil_sword_count
            
            # Reset all values first
            self.regular_sword_count = 0
            self.holy_sword_count = 0
            self.evil_sword_count = 0
            
            # Set the appropriate counter based on current sword type
            if game_state.has_sword and game_state.sword_type == SwordType.REGULAR:
                self.regular_sword_count = 1
            elif game_state.has_sword and game_state.sword_type == SwordType.HOLY:
                self.holy_sword_count = 1
            elif game_state.has_sword and game_state.sword_type == SwordType.EVIL:
                self.evil_sword_count = 1
            
            # Update the gauges with their current values
            self.regular_sword_gauge.set(self.regular_sword_count, {"sword_type": "regular"})
            self.holy_sword_gauge.set(self.holy_sword_count, {"sword_type": "holy"}) 
            self.evil_sword_gauge.set(self.evil_sword_count, {"sword_type": "evil"})
            self.metric_reader.force_flush()
            
            logger.info(f"Sword metrics updated: regular={old_regular}->{self.regular_sword_count}, holy={old_holy}->{self.holy_sword_count}, evil={old_evil}->{self.evil_sword_count}")
        except Exception as e:
            logger.error(f"Error tracking sword metrics: {e}")

# Initialize metrics
otel_metrics = CustomMetrics(service_name=service_name)

# DynamoDB setup
endpoint_url = os.environ.get('DYNAMODB_ENDPOINT', None)
is_local = endpoint_url is not None

if is_local:
    logger.info(f"Using local DynamoDB endpoint: {endpoint_url}")
    dynamodb = boto3.resource('dynamodb', endpoint_url=endpoint_url)
    dynamodb_client = boto3.client('dynamodb', endpoint_url=endpoint_url)
else:
    dynamodb = boto3.resource('dynamodb')
    dynamodb_client = boto3.client('dynamodb')

table_name = os.environ.get('GAME_STATE_TABLE', 'adventure-quest-state')

# Create DynamoDB table if it doesn't exist
def create_table_if_not_exists():
    """Create the DynamoDB table if it doesn't exist (for both local development and production)"""
    try:
        # First, try to access the table to see if it exists
        try:
            table = dynamodb.Table(table_name)
            # Check if table exists by getting its description
            dynamodb_client.describe_table(TableName=table_name)
            logger.info(f"Table {table_name} already exists")
            return table
        except dynamodb_client.exceptions.ResourceNotFoundException:
            logger.info(f"Table {table_name} does not exist, creating it now")
            
            # Table doesn't exist, create it
            table = dynamodb.create_table(
                TableName=table_name,
                KeySchema=[
                    {
                        'AttributeName': 'adventurer_name',
                        'KeyType': 'HASH'
                    }
                ],
                AttributeDefinitions=[
                    {
                        'AttributeName': 'adventurer_name',
                        'AttributeType': 'S'
                    }
                ],
                BillingMode='PAY_PER_REQUEST'
            )
            
            # Wait for table to be created
            logger.info(f"Waiting for table {table_name} to be created...")
            table.meta.client.get_waiter('table_exists').wait(TableName=table_name)
            logger.info(f"Table {table_name} created successfully")
            return table
            
    except Exception as e:
        logger.exception(f"Error creating table: {str(e)}")
        # Even if table creation fails, we'll try to return the table object
        # It might work for subsequent operations
        return dynamodb.Table(table_name)

# Initialize DynamoDB table
table = create_table_if_not_exists()

# DynamoDB operations
def save_game_state(game_state: GameState, blacksmith_state: Optional[BlacksmithState] = None) -> bool:
    """Save game state to DynamoDB"""
    global table
    try:
        # Track sword metrics
        otel_metrics.track_sword_state(game_state)
        
        # Convert states to dict and remove None values
        game_state_dict = {k: v for k, v in game_state.model_dump().items() if v is not None}
        
        # Add TTL of 24 hours
        game_state_dict['ttl'] = int(time.time()) + (24 * 60 * 60)
        
        # Add blacksmith state if provided
        if blacksmith_state:
            blacksmith_dict = {k: v for k, v in blacksmith_state.model_dump().items() if v is not None}
            game_state_dict['blacksmith_state'] = blacksmith_dict
        
        # Save to DynamoDB
        table.put_item(Item=game_state_dict)
        logger.info(f"Saved game state for {game_state.adventurer_name}")
        return True
        
    except ClientError as e:
        if isinstance(e, dynamodb_client.exceptions.ResourceNotFoundException):
            # Table doesn't exist, try to create it and retry
            logger.warning(f"Table {table_name} not found, trying to create it...")
            table = create_table_if_not_exists()
            # Retry save operation
            return save_game_state(game_state, blacksmith_state)
        else:
            logger.error(f"Failed to save game state: {str(e)}")
            return False

def migrate_game_state(item):
    """Migrate an old game state format to the new one"""
    if 'quest_giver_alive' in item:
        # Convert quest_giver_alive (bool) to quest_givers_killed (int)
        quest_giver_alive = item.pop('quest_giver_alive')
        if not quest_giver_alive:
            item['quest_givers_killed'] = 1
        else:
            item['quest_givers_killed'] = 0
        logger.info(f"Migrated quest_giver_alive to quest_givers_killed for {item.get('adventurer_name')}")
    
    # Add any other migrations here

    return item

def load_game_state(adventurer_name: str) -> Tuple[Optional[GameState], Optional[BlacksmithState]]:
    """Load game state from DynamoDB"""
    global table
    try:
        response = table.get_item(
            Key={'adventurer_name': adventurer_name}
        )
        
        if 'Item' not in response:
            logger.info(f"No saved game state found for {adventurer_name}")
            return None, None
        
        # Extract blacksmith state if it exists
        item = response['Item']
        
        # Migrate item if needed
        item = migrate_game_state(item)
        
        blacksmith_state = None
        if 'blacksmith_state' in item:
            blacksmith_data = item.pop('blacksmith_state')
            blacksmith_state = BlacksmithState(**blacksmith_data)
        
        # Remove TTL from game state
        if 'ttl' in item:
            del item['ttl']
        
        # Create GameState object
        game_state = GameState(**item)
        logger.info(f"Loaded game state for {adventurer_name}")
        
        return game_state, blacksmith_state
        
    except ClientError as e:
        if isinstance(e, dynamodb_client.exceptions.ResourceNotFoundException):
            # Table doesn't exist, try to create it
            logger.warning(f"Table {table_name} not found, trying to create it...")
            table = create_table_if_not_exists()
            # For GET operations, we just return None as there's no data yet
            return None, None
        else:
            logger.error(f"Failed to load game state: {str(e)}")
            return None, None

def create_default_game_state(adventurer_name: str) -> Tuple[GameState, BlacksmithState]:
    """Create default game state for a new player"""
    # Initialize default game state
    game_state = GameState(
        adventurer_name=adventurer_name,
        current_location="start",
        has_sword=False,
        sword_type=SwordType.NONE,
        quest_accepted=False,
        priest_alive=True,
        blacksmith_burned_down=False,
        failed_sword_attempts=0,
        has_box=False,
        quest_givers_killed=0
    )
    
    # Initialize default blacksmith state
    blacksmith_state = BlacksmithState(
        heat=0,
        is_heating_forge=False,
        sword_requested=False
    )
    
    # Save the default state to DynamoDB
    success = save_game_state(game_state, blacksmith_state)
    if success:
        logger.info(f"Created and saved default game state for new player: {adventurer_name}")
    else:
        logger.error(f"Failed to save default game state for new player: {adventurer_name}")
    
    return game_state, blacksmith_state

def delete_game_state(adventurer_name: str) -> bool:
    """Delete game state from DynamoDB"""
    global table
    try:
        table.delete_item(
            Key={'adventurer_name': adventurer_name}
        )
        logger.info(f"Deleted game state for {adventurer_name}")
        return True
        
    except ClientError as e:
        if isinstance(e, dynamodb_client.exceptions.ResourceNotFoundException):
            # Table doesn't exist, create it (though there's nothing to delete)
            logger.warning(f"Table {table_name} not found when trying to delete, creating it...")
            table = create_table_if_not_exists()
            return True  # Consider it a success since there was nothing to delete
        else:
            logger.error(f"Failed to delete game state: {str(e)}")
            return False

def process_game_state_action(action, params):
    """Process game state actions (get, save, delete) - used for both direct Lambda invocations and API requests"""
    try:
        if action == 'get':
            adventurer_name = params.get('adventurer_name')
            game_state, blacksmith_state = load_game_state(adventurer_name)
            
            # If no state exists, create a default one for new players
            if not game_state:
                logger.info(f"Creating default state for new player: {adventurer_name}")
                game_state, blacksmith_state = create_default_game_state(adventurer_name)
            
            # Track sword metrics when loading state
            if game_state:
                otel_metrics.track_sword_state(game_state)
                
            return {
                'success': True,
                'message': 'Game state loaded successfully',
                'game_state': game_state.model_dump() if game_state else None,
                'blacksmith_state': blacksmith_state.model_dump() if blacksmith_state else None
            }
        elif action == 'save':
            adventurer_name = params.get('adventurer_name')
            game_state_data = params.get('game_state')
            blacksmith_state_data = params.get('blacksmith_state')
            
            # Create GameState and BlacksmithState objects from the request data
            game_state = GameState(**game_state_data) if game_state_data else None
            blacksmith_state = BlacksmithState(**blacksmith_state_data) if blacksmith_state_data else None
            
            # Save to DynamoDB
            success = save_game_state(game_state, blacksmith_state)
            
            return {
                'success': success,
                'message': 'Game state saved successfully' if success else 'Failed to save game state'
            }
        elif action == 'delete':
            adventurer_name = params.get('adventurer_name')
            success = delete_game_state(adventurer_name)
            
            return {
                'success': success,
                'message': f'Game state deleted for {adventurer_name}' if success else f'Failed to delete game state for {adventurer_name}'
            }
        elif action == 'cheat':
            # Handle cheat action - instantly gives the player a sword
            adventurer_name = params.get('adventurer_name')
            game_state, blacksmith_state = load_game_state(adventurer_name)
            
            if not game_state:
                # Create a new game state if one doesn't exist
                game_state = GameState(
                    adventurer_name=adventurer_name,
                    current_location="start"
                )
            
            # Give the player a sword
            game_state.has_sword = True
            game_state.sword_type = SwordType.REGULAR
            
            # Save the updated state (this will also track the sword metrics)
            success = save_game_state(game_state, blacksmith_state)
            
            return {
                'success': success,
                'message': 'You cheated and got a sword. You feel guilty.',
                'game_state': game_state.model_dump() if game_state else None,
                'blacksmith_state': blacksmith_state.model_dump() if blacksmith_state else None
            }
        else:
            return {
                'success': False,
                'message': f'Unknown action: {action}'
            }
    except Exception as e:
        logger.exception(f"Error processing game state action '{action}': {str(e)}")
        return {
            'success': False,
            'message': f'Error processing request: {str(e)}'
        }

@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    """Main Lambda handler"""
    # Check if this is a direct Lambda invocation (not through API Gateway)
    if 'httpMethod' not in event and 'action' in event:
        logger.info(f"Direct Lambda invocation detected with action: {event['action']}")
        # Add source context to logs if available
        if 'source' in event:
            logger.append_keys(source=event['source'])
        elif 'source_function' in event:
            logger.append_keys(source_function=event['source_function'])
        
        # Process the action
        return process_game_state_action(event.get('action'), event)
    
    # Otherwise, handle as a normal API Gateway request
    return app.resolve(event, context)

def load_all_game_states() -> list:
    """Load all game states from DynamoDB"""
    global table
    try:
        response = table.scan()
        
        if 'Items' not in response or not response['Items']:
            logger.info("No saved game states found")
            return []
        
        game_states = []
        for item in response['Items']:
            # Remove TTL from game state if it exists
            if 'ttl' in item:
                del item['ttl']
                
            # Handle blacksmith state if it exists
            blacksmith_state = None
            if 'blacksmith_state' in item:
                blacksmith_data = item.pop('blacksmith_state')
                blacksmith_state = BlacksmithState(**blacksmith_data)
                
            # Create GameState object and add to list
            game_state = GameState(**item)
            game_states.append({
                'game_state': game_state.model_dump(),
                'blacksmith_state': blacksmith_state.model_dump() if blacksmith_state else None
            })
            
        logger.info(f"Loaded {len(game_states)} game states")
        return game_states
        
    except ClientError as e:
        if isinstance(e, dynamodb_client.exceptions.ResourceNotFoundException):
            # Table doesn't exist, try to create it
            logger.warning(f"Table {table_name} not found, trying to create it...")
            table = create_table_if_not_exists()
            # For scan operations, we just return an empty list
            return []
        else:
            logger.error(f"Failed to load game states: {str(e)}")
            return []

@app.get("/game-state/all")
def get_all_game_states():
    """External API: Get all saved game states"""
    try:
        logger.info("Loading all game states")
        
        # Load all game states from DynamoDB
        game_states = load_all_game_states()
        
        return {
            "game_states": game_states,
            "count": len(game_states),
            "message": "Game states loaded successfully"
        }
        
    except Exception as e:
        logger.exception(f"Error loading all game states: {str(e)}")
        error_trace = traceback.format_exc()
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e), 
                "trace": error_trace
            })
        }

@app.post("/game-state/migrate")
def migrate_all_game_states():
    """Migrate all game states to the latest format"""
    try:
        response = table.scan()
        migrated_count = 0
        
        if 'Items' in response and response['Items']:
            for item in response['Items']:
                original_item = dict(item)
                updated_item = migrate_game_state(item)
                
                if original_item != updated_item:
                    # Save the updated item back to DynamoDB
                    table.put_item(Item=updated_item)
                    migrated_count += 1
        
        return {
            'success': True,
            'message': f'Successfully migrated {migrated_count} game states',
            'count': migrated_count
        }
    except Exception as e:
        logger.exception(f"Error migrating game states: {str(e)}")
        return {
            'success': False,
            'message': f'Error migrating game states: {str(e)}'
        }

@app.get("/game-state/<adventurer_name>")
def get_game_state(adventurer_name: str):
    """External API: Get saved game state for an adventurer"""
    try:
        logger.info(f"Getting game state for {adventurer_name}")
        
        # Load from DynamoDB
        game_state, blacksmith_state = load_game_state(adventurer_name)
        
        # If no state exists, create a default one for new players
        if not game_state:
            logger.info(f"Creating default state for new player: {adventurer_name}")
            game_state, blacksmith_state = create_default_game_state(adventurer_name)
        
        if game_state:
            return {
                "game_state": game_state.model_dump(),
                "blacksmith_state": blacksmith_state.model_dump() if blacksmith_state else None,
                "message": "Game state loaded successfully"
            }
        
        return {
            "message": f"No saved game found for {adventurer_name} and failed to create default state",
            "found": False
        }
        
    except Exception as e:
        logger.exception(f"Error loading game state: {str(e)}")
        error_trace = traceback.format_exc()
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e), 
                "trace": error_trace
            })
        }

@app.post("/game-state")
def save_game_state_handler():
    """External API: Save game state for an adventurer"""
    try:
        request_data = app.current_event.json_body
        logger.info(f"Received data: {request_data}")
        
        if "game_state" not in request_data:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing game_state in request"})
            }
        
        game_state_data = request_data["game_state"]
        blacksmith_state_data = request_data.get("blacksmith_state")
        
        # Create GameState and BlacksmithState objects
        game_state = GameState(**game_state_data)
        blacksmith_state = BlacksmithState(**blacksmith_state_data) if blacksmith_state_data else None
        
        # Save to DynamoDB
        success = save_game_state(game_state, blacksmith_state)
        
        if success:
            return {"message": "Game saved successfully"}
        else:
            return {
                "statusCode": 500,
                "body": json.dumps({"error": "Failed to save game state"})
            }
            
    except Exception as e:
        logger.exception(f"Error saving game state: {str(e)}")
        error_trace = traceback.format_exc()
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e), 
                "trace": error_trace
            })
        }

@app.delete("/game-state/<adventurer_name>")
def delete_game_state_handler(adventurer_name: str):
    """External API: Delete saved game state for an adventurer"""
    try:
        logger.info(f"Deleting game state for {adventurer_name}")
        
        # Delete from DynamoDB
        success = delete_game_state(adventurer_name)
        
        if success:
            return {"message": f"Game state deleted for {adventurer_name}"}
        else:
            return {
                "statusCode": 500,
                "body": json.dumps({"error": f"Failed to delete game state for {adventurer_name}"})
            }
            
    except Exception as e:
        logger.exception(f"Error deleting game state: {str(e)}")
        error_trace = traceback.format_exc()
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e), 
                "trace": error_trace
            })
        }

@app.post("/game-state/internal")
def handle_internal_request():
    """Handle internal requests from other Lambda functions via API Gateway"""
    # Parse request body
    request_data = app.current_event.json_body
    action = request_data.get('action')
    return process_game_state_action(action, request_data) 