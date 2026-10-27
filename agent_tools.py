"""Step 5: register two sequential tools. See lab.md for the full contract."""
from pydantic_ai import Agent, RunContext
from action_model import Action
from room_tools import RoomSession, GoalReached


def register_tools(agent: Agent):
    # TODO: observe_room(ctx) -> ctx.deps.observe()
    # TODO: perform_action(ctx, action: Action) -> ctx.deps.perform(action.model_dump())
    # Both must be sequential with retries=0. After a successful action,
    # raise GoalReached if ctx.deps.goal_reached; the final result is already logged.
    raise NotImplementedError("Step 5: register the two room tools in agent_tools.py")
