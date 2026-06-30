"""Event registry — scheduled activities (HOA + manual) + reminder firing.

Sources:
* ``hoa`` — auto-extracted from the El Dorado Ranch weekly PDF
* ``manual`` — created via POST /api/events

Reminders are fired by the scheduler in ``scheduler.py``; the actual
"say it out loud" action goes to the local TTS service via ``tts.py``.
"""

from .store import EventStore
from .scheduler import run_reminder_scheduler

__all__ = ["EventStore", "run_reminder_scheduler"]
