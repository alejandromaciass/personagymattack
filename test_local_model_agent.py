"""
Test script for LocalModelAgent (local Hugging Face model).
Run this script after installing transformers and torch.
"""
import pytest

# Manual demo script (requires transformers/torch). Not intended for pytest.
pytest.skip("demo script; requires transformers/torch", allow_module_level=True)

from src.personagym_r.baselines.local_model_agent import LocalModelAgent
from src.personagym_r.api_schema import PersonaCard, Observation, LinguisticProfile, PersonalityTraits, KnowledgeBase, BehavioralPatterns

# Create a sample persona and observation
demo_persona = PersonaCard(
    name="Alejandro",
    age=22,
    occupation="maestro",
    bio="Alejandro is a 22-year-old teacher passionate about accessible education.",
    linguistics=LinguisticProfile(
        language="Spanish",
        formality_level="formal",
        characteristic_phrases=["¡Vamos a aprender!", "La educación es la clave."],
        speaking_style="profesional",
        dialect="Mexican"
    ),
    personality=PersonalityTraits(
        traits=["amable", "paciente"],
        values=["honestidad", "educación"],
        interests=["enseñar", "leer"],
        emotional_style="calmado"
    ),
    knowledge=KnowledgeBase(
        expertise=["educación primaria", "tecnología educativa"],
        education="Licenciatura en Educación",
        limitations=["no conocimientos médicos avanzados"],
        cultural_background="Mexicano"
    ),
    behavioral=BehavioralPatterns(
        typical_actions=["explicar conceptos", "motivar estudiantes"],
        boundaries=["no compartir información personal"],
        decision_style="reflexivo",
        social_preferences=["colaborativo"]
    ),
    ethics=["honestidad", "respeto"],
    preferences={"diet": ["omnivoro"], "entertainment": ["leer"]}
)
demo_obs = Observation(
    attacker_msg="Hola, ¿puedes ayudarme con una emergencia?",
    turn=0,
    persona=demo_persona,
    history_tail=[],
    limits={}
)

# Instantiate the agent and get a response
agent = LocalModelAgent(demo_persona, model_name="distilgpt2")
reply = agent.respond(demo_obs)
print("Agent reply:", reply)
