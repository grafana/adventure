<!--
---
title: Quest World
menuTitle: Quest World
description: A text-based adventure game with an observability twist
weight: 600
killercoda:
  title: Quest World
  description: A text-based adventure game with an observability twist
  details:
      intro:
         foreground: docker-compose-update.sh
  backend:
    backend:
    imageid: ubuntu
---
--->


<!-- INTERACTIVE page intro.md START -->
# Adventure Quest - Serverless Edition

A text-based adventure game built using AWS Lambda and API Gateway. The game maintains its text-based interface while leveraging serverless architecture for game logic and state management.

## Architecture

The game is split into several components:

1. CLI Client (`adventure_client.py`)
   - Handles user interaction
   - Maintains local game state
   - Communicates with backend services via API Gateway

2. Lambda Functions
   - `blacksmith` - Handles sword crafting mechanics
   - `mysterious-man` - Handles evil wizard encounters (TODO)
   - `quest-giver` - Handles quest progression (TODO)
   - `chapel` - Handles holy sword mechanics (TODO)

3. Shared Components
   - `models.py` - Shared data models using Pydantic
   - OpenTelemetry integration for observability

## Project Structure

```
.
├── README.md
├── requirements.txt
├── adventure_client.py
└── lambda/
    ├── shared/
    │   └── models.py
    ├── blacksmith/
    │   └── app.py
    ├── mysterious_man/
    ├── quest_giver/
    └── chapel/
```

## Prerequisites

- Python 3.8+
- AWS CLI configured with appropriate credentials
- AWS SAM CLI (for local testing)

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables:
```bash
export API_URL=<your-api-gateway-url>
```

## Local Development

1. Run the SAM local API:
```bash
sam local start-api
```

2. In a separate terminal, run the client:
```bash
python adventure_client.py
```

## Deployment

1. Package the Lambda functions:
```bash
sam build
```

2. Deploy to AWS:
```bash
sam deploy --guided
```

## Observability

The game integrates with OpenTelemetry to provide:
- Metrics for game actions and states
- Tracing for request flows
- Logging for game events

Metrics, traces, and logs are sent to Grafana Cloud for visualization and monitoring.

## Game Flow

1. Start the game by running the client
2. Enter your adventurer name
3. Navigate through the world using text commands or numbered options
4. Visit the blacksmith to forge a sword
5. Enhance your sword through various encounters
6. Complete quests and defeat the evil wizard

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

<!-- INTERACTIVE ignore START -->

<div align="center">
<img src="https://raw.githubusercontent.com/grafana/adventure/main/img/logo.png" alt="Quest" width="200"/>
</div>

<!-- INTERACTIVE ignore END -->

Quest World is a text-based adventure game with an observability twist. In this game, you'll embark on a journey through a mystical world, interacting with characters, exploring locations, and making choices that shape your destiny. The game is designed to teach you about observability concepts while you embark on an exciting quest.

Checkout our blog post [here](https://grafana.com/blog/2024/11/20/metrics-logs-traces-and-mayhem-introducing-an-observability-adventure-game-powered-by-grafana-alloy-and-otel/) to learn more about the game.

<!-- INTERACTIVE ignore START -->
## Run in a Sandbox Environment

You can play Quest World in a sandbox environment. The online VM is pre-configured with all the necessary components to run the game. Click the button below to launch the VM and start playing.

<div align="center">
  <a href="https://killercoda.com/grafana-labs/course/workshops/adventure">
    <img src="https://raw.githubusercontent.com/grafana/adventure/main/img/launch.png" alt="Quest" width="200"/>
  </a>
</div>

And follow the instructions [here](killercoda-sandbox.md).

## Run with Docker

You can run Quest World on your local machine using Docker. Follow the instructions below to get started. 

1. Clone the repository

   ```bash
   git clone https://github.com/grafana/adventure.git
   ```

2. Navigate to the `adventure` directory

   ```bash
   cd adventure
   ```

3. Spin up the Observability Stack using Docker Compose

   ```bash
   docker compose up -d
   ```

Instead of using a [python virtual environment](#installation-with-python), you can run the game in a Docker container with the following steps.

1. First build the Docker image:

   ```bash
   docker build -t adventure:latest .
   ```
   
   **Note**: Make sure you are in the top level of the `adventure` directory.

1. Run the container:

   ```bash
   docker run -it --network=adventure_adventure --name adventure -e SETUP=docker adventure:latest
   ```

Once up, check the [gameplay instructions](#gameplay-instructions)

Once you **finished playing**, to clean up your environment run:

```bash
docker stop adventure
docker compose down
```

<!-- INTERACTIVE ignore END -->


<!-- INTERACTIVE page intro.md END -->

<!-- INTERACTIVE page step1.md START -->

## Installation with Python

If you prefer to use a python virtual environment, follow the instructions below.

1. Clone the repository

   ```bash
   git clone https://github.com/grafana/adventure.git
   ```

2. Navigate to the `adventure` directory

   ```bash
   cd adventure
   ```

3. Spin up the Observability Stack using Docker Compose

   ```bash
   docker compose up -d
   ```

Quest World runs as a python application our recommended way to install it is to use a virtual environment.

1. Create a virtual environment

   ```bash
   python3.12 -m venv .venv
   ```

2. Activate the virtual environment

   ```bash
   source .venv/bin/activate
   ```

3. Upgrade pip

   ```bash
   pip install --upgrade pip
   ```

4. Install the required dependencies

   ```bash
   pip install -r requirements.txt
   ```

5. Run the application

   ```bash
   python main.py
   ```

<!-- INTERACTIVE page step1.md END -->

<!-- INTERACTIVE page step2.md START -->

## Gameplay Instructions

- Upon starting the game, you will receive a description of your current location and a list of available actions.
- Type the command corresponding to the action you want to take and press **Enter**.
- The game continues based on your inputs and choices.
- This game involves checking Grafana dashboards to progress. You can access the Grafana dashboard at `http://localhost:3000`. Check the dashboard for hints and clues.

### Available Commands

At any point, you can type `list actions` to see the available commands in your current location.

Some universal commands include:

- `quit` or `exit`: End the game.
- `list actions`: Display available actions.

**Sample Actions**:

- **Movement**:
  - `go north`
  - `go south`
  - `go to town`
- **Interactions**:
  - `request sword`
  - `pick herb`
  - `explore`
  - `accept quest`
  - `look at sword`
  - `pray`
- **Special Commands**:
  - `cheat` (to obtain a sword immediately; not recommended).

*Note*: Not all actions are available in every location. Some actions may require certain conditions to be met or prerequisites to be fulfilled.

### Tips for Playing

- **Explore Thoroughly**: Don't hesitate to try different actions to discover hidden elements.
- **Manage Your Items**: Keep track of items like swords and herbs; they can affect your interactions.
- **Interact with Characters**: Talking to NPCs like the blacksmith, wizard, or priest can open new paths.
- **Monitor Forge Heat**: When at the blacksmith, you'll need to manage the forge's heat to get your sword.
- **Beware of Choices**: Some decisions, like accepting the wizard's offer, have consequences.

### Sample Gameplay Flow

1. **Starting Out**:
   - You're at the starting point with the option to `go north` or `cheat`.
   - Typing `go north` takes you to the forest.

2. **In the Forest**:
   - Options include `go north` to the cave, `go south` back to start, `go to town`, or `pick herb`.
   - You might choose to `pick herb` and then `go to town`.

3. **In the Town**:
   - Several locations to explore: `blacksmith`, `mysterious man`, `quest giver`, `chapel`.
   - Visit the `blacksmith` to `request sword`.

4. **At the Blacksmith**:
   - After requesting a sword, you'll need to `heat forge` and `check sword` periodically.
   - Adjust the forge heat using `heat forge` and `cool forge` until the sword is ready.

5. **Getting the Sword**:
   - Once the forge is at the correct temperature, `check sword` will let you obtain it.
   - With the sword, you can interact with other characters differently.

6. **Meeting the Wizard**:
   - Return to town and choose `mysterious man` to meet the wizard (requires having a sword).
   - Decide whether to `accept his offer` or `decline his offer`.

7. **Accepting a Quest**:
   - Visit the `quest giver` to `accept quest`.
   - Your ability to complete the quest may depend on previous choices.

8. **Visiting the Chapel**:
   - Go to the `chapel` and `look at sword` to interact with the priest.
   - The priest can bless your sword, especially if it's been cursed.

<!-- INTERACTIVE page step2.md END -->

<!-- INTERACTIVE page finish.md START -->

Remember, the game is dynamic, and your choices can lead to different outcomes. Enjoy the adventure!

<!-- INTERACTIVE page finish.md END -->
