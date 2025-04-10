import os
import json
import requests
from typing import Optional, Dict, Any, Tuple
from otel import CustomTracer



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
        self.service_name = "adventure-client"  
        ct = CustomTracer(service_name=self.service_name)
        self.trace = ct.get_trace()
        self.tracer = self.trace.get_tracer(self.service_name)
        
        self.setup_game()

        
    def check_for_saved_game(self, adventurer_name: str) -> Tuple[Optional[Dict], Optional[Dict]]:
        """Check if there's a saved game for this adventurer"""
        try:
            # Make API call to check for saved game
            response = requests.get(
                f"{self.api_url}/game-state/{adventurer_name}"
            )
            
            if response.status_code == 200:
                data = response.json()
                # Check if a pre-existing saved game exists (not a default one just created)
                if data.get("game_state") and not (
                    data.get("game_state").get("current_location") == "start" and
                    not data.get("game_state").get("has_sword") and
                    data.get("game_state").get("sword_type") == "none" and
                    not data.get("game_state").get("quest_accepted") and 
                    data.get("game_state").get("priest_alive") and
                    not data.get("game_state").get("blacksmith_burned_down") and
                    data.get("game_state").get("failed_sword_attempts") == 0 and
                    not data.get("game_state").get("has_box") and
                    data.get("game_state").get("quest_givers_killed", 0) == 0
                ):
                    return data.get("game_state"), data.get("blacksmith_state")
            return None, None
            
        except Exception as e:
            print(f"{Colors.RED}Error checking for saved game: {str(e)}{Colors.RESET}")
            return None, None
        
    def setup_game(self):
        """Initialize the game state"""
        self.adventurer_name = input("Enter your name, brave adventurer: ")
        
        # Check for saved game

        saved_game, saved_blacksmith = self.check_for_saved_game(self.adventurer_name)
        
        if saved_game:
            load_save = input(f"Welcome back, {self.adventurer_name}! Would you like to continue your previous adventure? (yes/no): ").lower()
            if load_save == "yes":
                self.game_state = saved_game
                self.blacksmith_state = saved_blacksmith
                print(f"\nWelcome back to your adventure, {self.adventurer_name}! Type 'quit' to exit or 'save' to save your progress.")
                return
        
        # Create a new game state
        self.game_state = {
            "adventurer_name": self.adventurer_name,
            "current_location": "start",
            "has_sword": False,
            "sword_type": "none",
            "quest_accepted": False,
            "priest_alive": True,
            "blacksmith_burned_down": False,
            "failed_sword_attempts": 0,
            "has_box": False,
            "quest_givers_killed": 0
        }
        
        # Initialize default blacksmith state
        self.blacksmith_state = {
            "heat": 0,
            "is_heating_forge": False,
            "sword_requested": False
        }
        
        # Immediately save the initial state to DynamoDB to ensure it's properly initialized
        save_success = self.save_game()
        if save_success:
            print(f"\nWelcome to your text adventure, {self.adventurer_name}! Your game has been automatically saved. Type 'quit' to exit or 'save' to save your progress.")
        else:
            print(f"\nWelcome to your text adventure, {self.adventurer_name}! Type 'quit' to exit or 'save' to save your progress.")
    
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
            "wizard": "You meet a wizard. He yells 'Are you here to kill me?!'",
            "forest": "You are in a dark forest. The trees are tall and the air is thick, you can make out a faint trail heading further east.",
            "cave": "You enter a dark cave at the end of the trail. The air is cold and damp. You see a faint light at the end of the cave.",
            "treasure": "You find a treasure chest at the end of the cave. Inside is a small decorative wooden box with no visible way of opening it."
        }
        return locations.get(self.game_state["current_location"], "You are in an unknown location.")
    
    def get_available_actions(self) -> list:
        """Get available actions for the current location"""
        actions = {
            "start": ["go to town", "go to forest", "cheat"],
            "town": ["blacksmith", "mysterious man", "quest giver", "chapel", "wizard"],
            "blacksmith": ["request sword", "heat forge", "cool forge", "check sword", "go to town"],
            "mysterious_man": ["accept offer", "decline offer", "go to town"],
            "chapel": ["look at sword", "pray", "go to town"],
            "quest_giver": ["accept quest", "check progress", "go to town"],
            "wizard": ["kill wizard", "talk to wizard", "cheat", "go to town"],
            "forest": ["go back", "go east"],
            "cave": ["go back", "go towards light"],
            "treasure": []
        }
        
        # Add treasure room actions based on state
        if self.game_state["current_location"] == "treasure":
            if not self.game_state.get("has_box", False):
                actions["treasure"].append("take the box")
            actions["treasure"].append("exit the cave")
        
        return actions.get(self.game_state["current_location"], ["look around"])
    
    def handle_blacksmith_action(self, action: str) -> Optional[str]:
        """Handle actions in the blacksmith location"""
        try:
            action_map = {
                "request sword": "request_sword",
                "heat forge": "heat_forge",
                "cool forge": "cool_forge",
                "check sword": "check_sword"
            }
            
            if action not in action_map:
                return None
                
            # Make sure the current location is set correctly before sending
            self.game_state["current_location"] = "blacksmith"
                
            request = {
                "action": action_map[action],
                "game_state": self.game_state,
                "blacksmith_state": self.blacksmith_state
            }
            
            response = requests.post(
                f"{self.api_url}/blacksmith",
                json=request
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Update game state but preserve our current location
                current_location = self.game_state["current_location"]
                self.game_state = result["game_state"]
                self.game_state["current_location"] = current_location
                
                # Update blacksmith state
                self.blacksmith_state = result.get("blacksmith_state")
                
                # Save the updated state to make sure it persists
                self.save_game()
                
                # Get the message from the response - no temperature info
                message = result.get("message", "")
                
                return message
            else:
                return f"Error: {response.status_code} - {response.text}"
                
        except Exception as e:
            return f"Error processing action: {str(e)}"
    
    def handle_mysterious_man_action(self, action: str) -> Optional[str]:
        """Handle actions with the mysterious man"""
        try:
            action_map = {
                "accept offer": "accept_offer",
                "decline offer": "decline_offer"
            }
            
            if action not in action_map:
                return None
                
            # Make sure the current location is set correctly before sending
            self.game_state["current_location"] = "mysterious_man"
                
            request = {
                "action": action_map[action],
                "game_state": self.game_state
            }
            
            response = requests.post(
                f"{self.api_url}/mysterious-man",
                json=request
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Update game state but preserve our current location
                current_location = self.game_state["current_location"]
                self.game_state = result["game_state"]
                self.game_state["current_location"] = current_location
                
                # Save the updated state to make sure it persists
                self.save_game()
                
                return result.get("message", "")
            else:
                return f"Error: {response.status_code} - {response.text}"
                
        except Exception as e:
            return f"Error processing action: {str(e)}"
    
    def handle_wizard_action(self, action: str) -> Optional[str]:
        """Handle actions with the wizard"""
        try:
            action_map = {
                "kill wizard": "kill_wizard",
                "talk to wizard": "talk_to_wizard",
                "cheat": "cheat"
            }
            
            if action not in action_map:
                return None
                
            # Make sure the current location is set correctly before sending
            self.game_state["current_location"] = "wizard"
                
            request = {
                "action": action_map[action],
                "game_state": self.game_state
            }
            
            response = requests.post(
                f"{self.api_url}/wizard",
                json=request
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Special handling for kill_wizard which intentionally changes location
                if action_map[action] == "kill_wizard":
                    # Just use the state as returned by the lambda
                    self.game_state = result["game_state"]
                else:
                    # For other actions, preserve our current location
                    current_location = self.game_state["current_location"]
                    self.game_state = result["game_state"]
                    self.game_state["current_location"] = current_location
                
                # Also update blacksmith state if provided
                if result.get("blacksmith_state"):
                    self.blacksmith_state = result.get("blacksmith_state")
                    
                # Check for game over
                game_over = result.get("game_over", False)
                
                if game_over:
                    print(f"\n{Colors.GREEN}{result.get('message', '')}{Colors.RESET}")
                    print("\nYour adventure has come to an end.")
                    return "quit"
                
                # Save the updated state unless it's game over
                if not game_over:
                    self.save_game()
                
                return result.get("message", "")
            else:
                return f"Error: {response.status_code} - {response.text}"
                
        except Exception as e:
            return f"Error processing action: {str(e)}"
    
    def handle_chapel_action(self, action: str) -> Optional[str]:
        """Handle actions in the chapel"""
        try:
            action_map = {
                "look at sword": "look_at_sword",
                "pray": "pray"
            }
            
            if action not in action_map:
                return None
                
            # Make sure the current location is set correctly before sending
            self.game_state["current_location"] = "chapel"
                
            request = {
                "action": action_map[action],
                "game_state": self.game_state
            }
            
            response = requests.post(
                f"{self.api_url}/chapel",
                json=request
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Update game state but preserve our current location
                current_location = self.game_state["current_location"]
                self.game_state = result["game_state"]
                self.game_state["current_location"] = current_location
                
                # Save the updated state to make sure it persists
                self.save_game()
                
                return result.get("message", "")
            else:
                return f"Error: {response.status_code} - {response.text}"
                
        except Exception as e:
            return f"Error processing action: {str(e)}"
    
    def handle_quest_giver_action(self, action: str) -> Optional[str]:
        """Handle actions with the quest giver"""
        try:
            action_map = {
                "accept quest": "accept_quest",
                "check progress": "check_progress"
            }
            
            if action not in action_map:
                return None
                
            # Make sure the current location is set correctly before sending
            self.game_state["current_location"] = "quest_giver"
                
            request = {
                "action": action_map[action],
                "game_state": self.game_state
            }
            
            response = requests.post(
                f"{self.api_url}/quest-giver",
                json=request
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Update game state but preserve our current location
                current_location = self.game_state["current_location"]
                self.game_state = result["game_state"]
                self.game_state["current_location"] = current_location
                
                # Save the updated state to make sure it persists
                self.save_game()
                
                return result.get("message", "")
            else:
                return f"Error: {response.status_code} - {response.text}"
                
        except Exception as e:
            return f"Error processing action: {str(e)}"
    
    def handle_cheat(self) -> str:
        """Handle the cheat action"""
        try:
            # Save current location before sending request
            current_location = self.game_state["current_location"]
            
            request = {
                "action": "cheat",
                "game_state": self.game_state
            }
            
            response = requests.post(
                f"{self.api_url}/wizard",
                json=request
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Update game state
                if result.get("game_state"):
                    self.game_state = result["game_state"]
                    # Restore location after update
                    self.game_state["current_location"] = current_location
                    
                # Also update blacksmith state if provided
                if result.get("blacksmith_state"):
                    self.blacksmith_state = result.get("blacksmith_state")
                    
                # Save the updated state to ensure it persists
                self.save_game()
                    
                return result.get("message", "You cheated and got a sword. You feel guilty.")
            else:
                return f"Error: {response.status_code} - {response.text}"
                
        except Exception as e:
            return f"Error processing cheat: {str(e)}"
    
    def save_game(self) -> bool:
        """Save the current game state"""
        try:
            # Make API call to save game
            response = requests.post(
                f"{self.api_url}/game-state",
                json={
                    "game_state": self.game_state,
                    "blacksmith_state": self.blacksmith_state
                }
            )
            
            if response.status_code == 200:
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
        
        # Handle cheat command
        if command.lower() == "cheat":
            result = self.handle_cheat()
            print(f"\n{Colors.GREEN}{result}{Colors.RESET}")
            self.display_current_location()
            return True
            
        # Handle box collection
        if command.lower() == "take the box" and self.game_state["current_location"] == "treasure":
            if not self.game_state.get("has_box", False):
                self.game_state["has_box"] = True
                print(f"\n{Colors.GREEN}You take the box and place it in your pocket. You hear a slight hum coming from the box as you touch it.{Colors.RESET}")
                # Save the game state after taking the box
                self.save_game()
                self.display_current_location()
            else:
                print(f"\n{Colors.GREEN}You already have the box.{Colors.RESET}")
            return True
            
        location_changes = {
            "go to town": "town",
            "go to forest": "forest",
            "go back": "start" if self.game_state["current_location"] == "forest" else "forest",
            "go east": "cave",
            "go towards light": "treasure",
            "exit the cave": "start",
            "blacksmith": "blacksmith",
            "mysterious man": "mysterious_man",
            "chapel": "chapel",
            "quest giver": "quest_giver",
            "wizard": "wizard"
        }
        
        if command in location_changes:
            # Update location in local state
            self.game_state["current_location"] = location_changes[command]
            # Save the updated state to the database
            self.save_game()
            self.display_current_location()
            return True
            
        # Handle location-specific actions
        result = None
        if self.game_state["current_location"] == "blacksmith":
            result = self.handle_blacksmith_action(command)
        elif self.game_state["current_location"] == "mysterious_man":
            result = self.handle_mysterious_man_action(command)
        elif self.game_state["current_location"] == "chapel":
            result = self.handle_chapel_action(command)
        elif self.game_state["current_location"] == "quest_giver":
            result = self.handle_quest_giver_action(command)
        elif self.game_state["current_location"] == "wizard":
            result = self.handle_wizard_action(command)
            if result == "quit":
                return False
            
        if result:
            print(f"\n{Colors.GREEN}{result}{Colors.RESET}")
            self.display_current_location()
            return True
                
        print(f"\n{Colors.RED}I don't understand that command.{Colors.RESET}")
        return True
    
    def restart_adventure(self):
        """Reset the game state for a new adventure"""
        # Ask for a new adventurer name
        adventurer_name = input("Enter your name for this new adventure: ")
        
        # Create a new game state
        self.game_state = {
            "adventurer_name": adventurer_name,
            "current_location": "start",
            "has_sword": False,
            "sword_type": "none",
            "quest_accepted": False,
            "priest_alive": True,
            "blacksmith_burned_down": False,
            "failed_sword_attempts": 0,
            "has_box": False,
            "quest_givers_killed": 0
        }
        
        # Reset blacksmith state
        self.blacksmith_state = {
            "heat": 0,
            "is_heating_forge": False,
            "sword_requested": False
        }
        
        # Immediately save the initial state
        save_success = self.save_game()
        if save_success:
            print(f"\nWelcome to your new adventure, {adventurer_name}! Your game has been automatically saved. Type 'quit' to exit or 'save' to save your progress.")
        else:
            print(f"\nWelcome to your new adventure, {adventurer_name}! Type 'quit' to exit or 'save' to save your progress.")
    
    def play(self):
        """Main game loop"""
        self.display_current_location()
        with self.tracer.start_as_current_span(self.adventurer_name, attributes={"adventurer": self.adventurer_name}) as journey_span:
            while True:
                command = input("> ").strip().lower()
                with self.tracer.start_as_current_span(
                    f"action: {command}",
                    attributes={
                        "adventurer": self.adventurer_name,
                        "location": self.game_state["current_location"]  # Adding location attribute to provide more context
                    }
                ) as action_span:
                    if not self.process_command(command):
                        break
            
            # Ask if the user wants to start a new adventure
            restart = input("\nWould you like to start a new adventure? (yes/no): ").strip().lower()
            if restart == "yes":
                self.restart_adventure()
                self.display_current_location()
                self.play()  # Recursively start a new game
            else:
                print("\nThank you for playing!")

if __name__ == "__main__":
    game = AdventureClient()
    game.play() 