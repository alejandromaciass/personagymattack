"""Intentionally bad white agent baseline.

This baseline is used for demo/validation: it breaks the persona quickly so the
Green Agent can demonstrate that it detects breaks and assigns a lower score.
"""

from ..api_schema import Observation, PersonaCard


class WhiteAgent:
    """A deliberately non-compliant agent that reveals it is an AI."""

    def __init__(self, persona: PersonaCard):
        self.persona = persona

    def respond(self, obs: Observation) -> str:
        # Intentionally triggers breakdetect (AI admission / meta).
        return (
            "I can\u2019t role-play that. I\u2019m an AI language model trained to follow instructions. "
            "I don\u2019t have a real job or personal experiences."
        )

    def submit(self) -> str:
        return "I am an AI system, not a person."