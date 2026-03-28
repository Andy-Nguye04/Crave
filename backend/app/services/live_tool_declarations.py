"""
Gemini Live ``Tool`` definitions for Crave function calling.

Declares the hackathon Live functions with JSON Schema parameters so the
Live session ``connect`` config can register them. Kept separate from runtime
handlers to keep ``cooking_tools`` free of SDK types.

Use cases:
- Build ``types.Tool(function_declarations=[...])`` when opening a Live session.
- Match names exactly to dispatch in the WebSocket bridge.
"""

from __future__ import annotations

from google.genai import types


def crave_live_tools() -> list[types.Tool]:
    """
    Build the list of Tool objects passed to ``LiveConnectConfig.tools``.

    Returns:
        A singleton list containing one ``types.Tool`` with all declarations.
    """

    declarations = [
        types.FunctionDeclaration(
            name="get_step_details",
            description=(
                "Returns the instruction and visual cues for a specific "
                "recipe step (1-based step_number)."
            ),
            parameters_json_schema={
                "type": "object",
                "properties": {
                    "step_number": {
                        "type": "integer",
                        "description": "1-based index of the cooking step.",
                    },
                },
                "required": ["step_number"],
            },
        ),
        types.FunctionDeclaration(
            name="get_ingredient_info",
            description=(
                "Returns measurements, dietary flags, and substitution hints "
                "for a named ingredient."
            ),
            parameters_json_schema={
                "type": "object",
                "properties": {
                    "item_name": {
                        "type": "string",
                        "description": "Ingredient name or fragment the user asked about.",
                    },
                },
                "required": ["item_name"],
            },
        ),
        types.FunctionDeclaration(
            name="set_kitchen_timer",
            description=(
                "Starts a countdown timer in the cooking UI for the given "
                "duration in seconds."
            ),
            parameters_json_schema={
                "type": "object",
                "properties": {
                    "duration_seconds": {
                        "type": "integer",
                        "description": "Timer length in whole seconds.",
                    },
                },
                "required": ["duration_seconds"],
            },
        ),
        types.FunctionDeclaration(
            name="navigate_recipe_step",
            description=(
                "Advances or goes back one step in the cooking UI. Call when the "
                "user wants the next or previous on-screen step, including implied "
                "forward intent (e.g. 'okay what's next', 'I'm done with this', "
                "'let's continue'). Use 'previous' for go back or the prior step; "
                "if they only want the current step re-read aloud, use "
                "get_step_details instead—do not use previous for that."
            ),
            parameters_json_schema={
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["next", "previous"],
                        "description": (
                            "'next' to advance one step; 'previous' to go back one step."
                        ),
                    },
                },
                "required": ["direction"],
            },
        ),
    ]
    return [types.Tool(function_declarations=declarations)]
