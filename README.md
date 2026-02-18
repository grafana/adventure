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
# Quest World

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

### Localization (GNU gettext)

The game uses GNU gettext for translations. User-visible strings are in `main.py` wrapped with `_()`. Locale data lives under `locale/`.

- **Run in another language**: set `LANGUAGE` or `LANG` (e.g. `LANGUAGE=fr python main.py`).
- **Extract strings** (after adding or changing text): `make extract` — updates `locale/adventure.pot`.
- **Add a new language** (e.g. French): `make init-fr` creates `locale/fr/LC_MESSAGES/adventure.po`. Edit the `msgstr` entries, then run `make compile`.
- **Update existing .po files** from the template: `make update` then `make compile`.

Requires the gettext tools (e.g. `brew install gettext` on macOS). In-game commands (e.g. `go to town`, `quit`) stay in English so parsing remains consistent across locales.

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
