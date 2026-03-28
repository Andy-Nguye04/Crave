"""
Gemini Live ``Tool`` definitions for Crave function calling.

Declares the three hackathon functions with JSON Schema parameters so the
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
            name="navigate_to_step",
            description=(
                "Navigates the cooking UI to a specific recipe step. Use this "
                "when the user says 'next step', 'go back', 'skip', or similar. "
                "The UI will update and you should then read the new step aloud."
            ),
            parameters_json_schema={
                "type": "object",
                "properties": {
                    "step_number": {
                        "type": "integer",
                        "description": "1-based step number to navigate to.",
                    },
                },
                "required": ["step_number"],
            },
        ),
    ]
    return [types.Tool(function_declarations=declarations)]
