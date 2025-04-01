import os
import time
import boto3
from typing import Optional
from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError

from .models import GameState, BlacksmithState

logger = Logger()
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['GAME_STATE_TABLE'])

class GameStateDB:
    @staticmethod
    def save_game_state(game_state: GameState, blacksmith_state: Optional[BlacksmithState] = None) -> bool:
        """Save game state to DynamoDB"""
        try:
            # Convert states to dict and remove None values
            game_state_dict = {k: v for k, v in game_state.dict().items() if v is not None}
            
            # Add TTL of 24 hours
            game_state_dict['ttl'] = int(time.time()) + (24 * 60 * 60)
            
            # Add blacksmith state if provided
            if blacksmith_state:
                blacksmith_dict = {k: v for k, v in blacksmith_state.dict().items() if v is not None}
                game_state_dict['blacksmith_state'] = blacksmith_dict
            
            # Save to DynamoDB
            table.put_item(Item=game_state_dict)
            logger.info(f"Saved game state for {game_state.adventurer_name}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to save game state: {str(e)}")
            return False
    
    @staticmethod
    def load_game_state(adventurer_name: str) -> tuple[Optional[GameState], Optional[BlacksmithState]]:
        """Load game state from DynamoDB"""
        try:
            response = table.get_item(
                Key={'adventurer_name': adventurer_name}
            )
            
            if 'Item' not in response:
                logger.info(f"No saved game state found for {adventurer_name}")
                return None, None
            
            # Extract blacksmith state if it exists
            item = response['Item']
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
            logger.error(f"Failed to load game state: {str(e)}")
            return None, None
    
    @staticmethod
    def delete_game_state(adventurer_name: str) -> bool:
        """Delete game state from DynamoDB"""
        try:
            table.delete_item(
                Key={'adventurer_name': adventurer_name}
            )
            logger.info(f"Deleted game state for {adventurer_name}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to delete game state: {str(e)}")
            return False 