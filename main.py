from otel import CustomLogFW
from opentelemetry.trace import Status, StatusCode
import logging

from app import AdventureGame

class Colors:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"

def play(game):
    print(f"{Colors.GREEN}{game.here()}{Colors.RESET}")

    with game.tracer.start_as_current_span(game.adventurer_name, attributes=game.context) as journey_span:
        while game.game_active:
            command = input("> ")
            logging.getLogger('main').info(f"Action by {game.adventurer_name}: " + command)

            # Create a span for each action taken by the player, with location attribute added
            with game.tracer.start_as_current_span(
                f"action: {command}",
                attributes=game.context | {
                    "location": game.current_location  # Adding location attribute to provide more context
                }
            ) as action_span:
                response = game.process_command(command)
                print(f"{response}")
                logging.getLogger('main').info(response)

                # Check if the game has ended, and if so, break out of the loop
                if not game.game_active:
                    journey_span.add_event("Adventure ended")
                    action_span.add_event(f"{game.adventurer_name} completed the adventure.")
                    action_span.set_status(Status(StatusCode.OK))
                    break
        
        # Ask if the user wants to restart after the adventure has ended
    restart_command = input("Would you like to restart the adventure? (yes/no): ").strip().lower()
    if restart_command == "yes":
        game.restart_adventure()
        play(game)
    else:
        print("Thank you for playing!")
        logging.getLogger('main').info(f"{game.adventurer_name}'s adventure has ended.")

if __name__ == "__main__":
    logFW = CustomLogFW(service_name='adventure')
    handler = logFW.setup_logging()
    logging.getLogger('main').addHandler(handler)
    logging.getLogger('main').setLevel(logging.INFO)

    print("Welcome to your text adventure! Type 'quit' to exit.")
    name = input("What is your name, brave adventurer? > ")
    game = AdventureGame(name)
    play(game)