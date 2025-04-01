import os
import json
import time
import boto3
import requests
from typing import Optional, Tuple
from game_lambda.shared.models import (
    GameState, BlacksmithState, BlacksmithAction, BlacksmithRequest,
    MysteriousManAction, MysteriousManRequest,
    ChapelAction, ChapelRequest,
    QuestAction, QuestRequest,
    ActionResponse, SwordType
)

class Colors:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"

class AdventureClient:
    def __init__(self):
        self.api_url = os.getenv("API_URL", "http://localhost:3000")
        self.game_state = None
        self.blacksmith_state = None
        self.current_actions = []
        
        self.setup_game()
        
    def check_for_saved_game(self, adventurer_name: str) -> Tuple[Optional[GameState], Optional[BlacksmithState]]:
        """Check if there's a saved game for this adventurer"""
        try:
            # Make API call to check for saved game
            response = requests.get(
                f"{self.api_url}/game-state/{adventurer_name}"
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("game_state"):
                    return (
                        GameState(**data["game_state"]),
                        BlacksmithState(**data["blacksmith_state"]) if data.get("blacksmith_state") else None
                    )
            return None, None
            
        except Exception as e:
            print(f"{Colors.RED}Error checking for saved game: {str(e)}{Colors.RESET}")
            return None, None
        
    def setup_game(self):
        """Initialize the game state"""
        adventurer_name = input("Enter your name, brave adventurer: ")
        
        # Check for saved game
        saved_game, saved_blacksmith = self.check_for_saved_game(adventurer_name)
        
        if saved_game:
            load_save = input(f"Welcome back, {adventurer_name}! Would you like to continue your previous adventure? (yes/no): ").lower()
            if load_save == "yes":
                self.game_state = saved_game
                self.blacksmith_state = saved_blacksmith
                print(f"\nWelcome back to your adventure, {adventurer_name}! Type 'quit' to exit or 'save' to save your progress.")
                return
        
        self.game_state = GameState(
            adventurer_name=adventurer_name,
            current_location="start"
        )
        print(f"\nWelcome to your text adventure, {adventurer_name}! Type 'quit' to exit or 'save' to save your progress.")
    
    def display_current_location(self):
        """Display the current location and available actions"""
        description = self.get_location_description()
        actions = self.get_available_actions()
        
        print(f"\n{Colors.GREEN}{description}{Colors.RESET}")
        print("\nAvailable actions:")
        self.current_actions = actions
        for i, action in enumerate(actions, 1):
            print(f"{Colors.MAGENTA}{i}. {action}{Colors.RESET}")
    
    def get_location_description(self) -> str:
        """Get the description for the current location"""
        locations = {
            "start": "You are at the beginning of your adventure. There's a path leading north towards a town, and another path leading east towards a forest.",
            "town": "You are in a bustling town. People are going about their business. You see a blacksmith, a mysterious man wandering the streets, a quest giver, and a chapel.",
            "blacksmith": "You are at the blacksmith's forge. The blacksmith is busy working.",
            "mysterious_man": "You meet a mysterious man. He offers to enhance your sword with magic.",
            "chapel": "You enter the chapel. The priest greets you warmly.",
            "quest_giver": "You meet a quest giver. He offers you a quest to defeat the evil wizard.",
            "wizard": "You meet a wizard. He yells 'Are you here to kill me?!'"
        }
        return locations.get(self.game_state.current_location, "You are in an unknown location.")
    
    def get_available_actions(self) -> list:
        """Get available actions for the current location"""
        actions = {
            "start": ["go to town", "go to forest"],
            "town": ["blacksmith", "mysterious man", "quest giver", "chapel"],
            "blacksmith": ["request sword", "heat forge", "cool forge", "check sword", "go to town"],
            "mysterious_man": ["accept offer", "decline offer", "kill wizard", "go to town"],
            "chapel": ["look at sword", "pray", "go to town"],
            "quest_giver": ["accept quest", "check progress", "go to town"],
            "wizard": ["kill wizard", "go to town"]
        }
        return actions.get(self.game_state.current_location, ["look around"])
    
    def handle_blacksmith_action(self, action: str) -> Optional[str]:
        """Handle actions in the blacksmith location"""
        try:
            action_map = {
                "request sword": BlacksmithAction.REQUEST_SWORD,
                "heat forge": BlacksmithAction.HEAT_FORGE,
                "cool forge": BlacksmithAction.COOL_FORGE,
                "check sword": BlacksmithAction.CHECK_SWORD
            }
            
            if action not in action_map:
                return None
                
            request = BlacksmithRequest(
                action=action_map[action],
                game_state=self.game_state,
                blacksmith_state=self.blacksmith_state
            )
            
            response = requests.post(
                f"{self.api_url}/blacksmith",
                json=request.model_dump()
            )
            
            if response.status_code == 200:
                result = ActionResponse(**response.json())
                self.game_state = result.game_state
                self.blacksmith_state = result.blacksmith_state
                return result.message
            else:
                return f"Error: {response.status_code} - {response.text}"
                
        except Exception as e:
            return f"Error processing action: {str(e)}"
    
    def handle_mysterious_man_action(self, action: str) -> Optional[str]:
        """Handle actions with the mysterious man"""
        try:
            action_map = {
                "accept offer": MysteriousManAction.ACCEPT_OFFER,
                "decline offer": MysteriousManAction.DECLINE_OFFER,
                "kill wizard": MysteriousManAction.KILL_WIZARD
            }
            
            if action not in action_map:
                return None
                
            request = MysteriousManRequest(
                action=action_map[action],
                game_state=self.game_state
            )
            
            response = requests.post(
                f"{self.api_url}/mysterious-man",
                json=request.model_dump()
            )
            
            if response.status_code == 200:
                result = ActionResponse(**response.json())
                self.game_state = result.game_state
                return result.message
            else:
                return f"Error: {response.status_code} - {response.text}"
                
        except Exception as e:
            return f"Error processing action: {str(e)}"
    
    def handle_chapel_action(self, action: str) -> Optional[str]:
        """Handle actions in the chapel"""
        try:
            action_map = {
                "look at sword": ChapelAction.LOOK_AT_SWORD,
                "pray": ChapelAction.PRAY
            }
            
            if action not in action_map:
                return None
                
            request = ChapelRequest(
                action=action_map[action],
                game_state=self.game_state
            )
            
            response = requests.post(
                f"{self.api_url}/chapel",
                json=request.model_dump()
            )
            
            if response.status_code == 200:
                result = ActionResponse(**response.json())
                self.game_state = result.game_state
                return result.message
            else:
                return f"Error: {response.status_code} - {response.text}"
                
        except Exception as e:
            return f"Error processing action: {str(e)}"
    
    def handle_quest_giver_action(self, action: str) -> Optional[str]:
        """Handle actions with the quest giver"""
        try:
            action_map = {
                "accept quest": QuestAction.ACCEPT_QUEST,
                "check progress": QuestAction.CHECK_PROGRESS
            }
            
            if action not in action_map:
                return None
                
            request = QuestRequest(
                action=action_map[action],
                game_state=self.game_state
            )
            
            response = requests.post(
                f"{self.api_url}/quest-giver",
                json=request.model_dump()
            )
            
            if response.status_code == 200:
                result = ActionResponse(**response.json())
                self.game_state = result.game_state
                return result.message
            else:
                return f"Error: {response.status_code} - {response.text}"
                
        except Exception as e:
            return f"Error processing action: {str(e)}"
    
    def save_game(self) -> bool:
        """Save the current game state"""
        try:
            # Make API call to save game
            response = requests.post(
                f"{self.api_url}/game-state",
                json={
                    "game_state": self.game_state.model_dump(),
                    "blacksmith_state": self.blacksmith_state.model_dump() if self.blacksmith_state else None
                }
            )
            
            if response.status_code == 200:
                print(f"{Colors.GREEN}Game saved successfully!{Colors.RESET}")
                return True
            else:
                print(f"{Colors.RED}Failed to save game: {response.text}{Colors.RESET}")
                return False
                
        except Exception as e:
            print(f"{Colors.RED}Error saving game: {str(e)}{Colors.RESET}")
            return False
    
    def process_command(self, command: str) -> bool:
        """Process a command from the user"""
        if command.lower() in ["quit", "exit"]:
            # Ask to save before quitting
            save_game = input("Would you like to save your progress before quitting? (yes/no): ").lower()
            if save_game == "yes":
                self.save_game()
            return False
            
        if command.lower() == "save":
            self.save_game()
            return True
            
        try:
            action_index = int(command) - 1
            if 0 <= action_index < len(self.current_actions):
                command = self.current_actions[action_index]
        except ValueError:
            pass
            
        location_changes = {
            "go to town": "town",
            "go to forest": "forest",
            "blacksmith": "blacksmith",
            "mysterious man": "mysterious_man",
            "chapel": "chapel",
            "quest giver": "quest_giver",
            "wizard": "wizard"
        }
        
        if command in location_changes:
            self.game_state.current_location = location_changes[command]
            self.display_current_location()
            return True
            
        # Handle location-specific actions
        result = None
        if self.game_state.current_location == "blacksmith":
            result = self.handle_blacksmith_action(command)
        elif self.game_state.current_location == "mysterious_man":
            result = self.handle_mysterious_man_action(command)
        elif self.game_state.current_location == "chapel":
            result = self.handle_chapel_action(command)
        elif self.game_state.current_location == "quest_giver":
            result = self.handle_quest_giver_action(command)
            
        if result:
            print(f"\n{Colors.GREEN}{result}{Colors.RESET}")
            if "go to town" in command:
                self.display_current_location()
            return True
                
        print(f"\n{Colors.RED}I don't understand that command.{Colors.RESET}")
        return True
    
    def play(self):
        """Main game loop"""
        self.display_current_location()
        
        while True:
            command = input("> ").strip().lower()
            if not self.process_command(command):
                break
                
        print("\nThank you for playing!")

if __name__ == "__main__":
    game = AdventureClient()
    game.play() 