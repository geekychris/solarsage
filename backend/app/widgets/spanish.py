"""Spanish widget — phrase of the day + on-demand translate.

Rotates a phrase from a category-tagged library based on day-of-year so
you get something different every day. Speak buttons hit the local TTS
service. The actual translate feature is implemented as REST endpoints
in ``main.py`` (POST /api/translations); this widget just exposes the
config + rendering hints.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from .base import Widget


PHRASES: list[dict[str, str]] = [
    # travel
    {"category": "travel", "es": "¿Dónde está la gasolinera más cercana?",
     "en": "Where is the nearest gas station?"},
    {"category": "travel", "es": "Necesito ir al banco.",
     "en": "I need to go to the bank."},
    {"category": "travel", "es": "¿Cuánto cuesta el peaje?",
     "en": "How much is the toll?"},
    # food
    {"category": "food", "es": "La cuenta, por favor.",
     "en": "The check, please."},
    {"category": "food", "es": "Sin cilantro, por favor.",
     "en": "No cilantro, please."},
    {"category": "food", "es": "¿Está muy picante?",
     "en": "Is it very spicy?"},
    {"category": "food", "es": "Un café con leche, por favor.",
     "en": "A coffee with milk, please."},
    # HOA / community
    {"category": "hoa", "es": "¿A qué hora abre la piscina?",
     "en": "What time does the pool open?"},
    {"category": "hoa", "es": "Estoy buscando al director de actividades.",
     "en": "I'm looking for the activities director."},
    # emergencies / medical
    {"category": "medical", "es": "Necesito una farmacia.",
     "en": "I need a pharmacy."},
    {"category": "medical", "es": "¿Puede llamar a una ambulancia?",
     "en": "Can you call an ambulance?"},
    {"category": "medical", "es": "Me siento mal.",
     "en": "I feel unwell."},
    # utilities / home
    {"category": "home", "es": "El agua no está saliendo.",
     "en": "The water isn't coming out."},
    {"category": "home", "es": "Necesitamos gas para la casa.",
     "en": "We need propane for the house."},
    {"category": "home", "es": "Se fue la luz.",
     "en": "The power went out."},
    # greetings / small talk
    {"category": "greetings", "es": "Buenos días, ¿cómo está usted?",
     "en": "Good morning, how are you?"},
    {"category": "greetings", "es": "Mucho gusto en conocerte.",
     "en": "Nice to meet you."},
    {"category": "greetings", "es": "Que tengas un buen día.",
     "en": "Have a good day."},
    # money
    {"category": "money", "es": "¿Aceptan dólares?",
     "en": "Do you accept dollars?"},
    {"category": "money", "es": "¿Puede hacer un descuento?",
     "en": "Can you give a discount?"},
]


class SpanishWidget(Widget):
    id = "spanish"
    kind = "spanish"
    name = "Spanish practice"
    description = (
        "Phrase of the day (rotates by category), a speak button that "
        "sends any text to the pi5 speaker, and a translate box. Every "
        "translation is saved so you can build up a personal phrase book."
    )
    refresh_seconds = 6 * 3600
    default_tab = "Community"
    default_position = 210

    config_schema = {
        "type": "object",
        "properties": {
            "categories": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Whitelist of phrase categories to rotate through — "
                    "empty means all. Categories: travel, food, hoa, "
                    "medical, home, greetings, money."
                ),
            },
            "custom_phrases": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "es": {"type": "string"},
                        "en": {"type": "string"},
                    },
                },
            },
        },
    }
    default_config = {"categories": [], "custom_phrases": []}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        cats = set(config.get("categories") or [])
        custom = list(config.get("custom_phrases") or [])
        pool = list(PHRASES) + [
            {"category": "custom", "es": p.get("es", ""), "en": p.get("en", "")}
            for p in custom if p.get("es") and p.get("en")
        ]
        if cats:
            pool = [p for p in pool if p["category"] in cats]
        if not pool:
            pool = PHRASES

        today = date.today()
        idx = today.toordinal() % len(pool)
        phrase = pool[idx]
        # A rotating small sampler around today for the "practice list"
        window = 5
        practice = [
            pool[(idx + off) % len(pool)]
            for off in range(1, window + 1)
        ]

        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "phrase_of_the_day": phrase,
            "practice_set": practice,
            "categories_available": sorted({p["category"] for p in pool}),
            "hint": (
                "POST /api/translations to translate anything; log lives "
                "at GET /api/translations."
            ),
        }
