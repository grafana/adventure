from pydantic import BaseModel
from typing import Optional
from enum import Enum

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
    blacksmith_state: Optional[BlacksmithState]

class MysteriousManAction(str, Enum):
    ACCEPT_OFFER = "accept_offer"
    DECLINE_OFFER = "decline_offer"
    KILL_WIZARD = "kill_wizard"

class MysteriousManRequest(BaseModel):
    action: MysteriousManAction
    game_state: GameState

class ChapelAction(str, Enum):
    LOOK_AT_SWORD = "look_at_sword"
    PRAY = "pray"

class ChapelRequest(BaseModel):
    action: ChapelAction
    game_state: GameState

class QuestAction(str, Enum):
    ACCEPT_QUEST = "accept_quest"
    CHECK_PROGRESS = "check_progress"

class QuestRequest(BaseModel):
    action: QuestAction
    game_state: GameState

class ActionResponse(BaseModel):
    message: str
    game_state: GameState
    blacksmith_state: Optional[BlacksmithState]
    success: bool = True 