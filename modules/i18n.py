"""Simple in-memory language storage for Telegram users."""
from __future__ import annotations

import logging
from typing import Dict

logger = logging.getLogger(__name__)

_DEFAULT_LANG = "ru"
_user_lang: Dict[int, str] = {}


def set_lang(user_id: int, lang: str) -> None:
    """Persist the preferred language for a Telegram user."""
    if not isinstance(user_id, int):
        logger.warning("Attempt to set language for non-integer user_id: %s", user_id)
        return

    if not lang:
        logger.warning("Attempt to set empty language for user %s", user_id)
        return

    _user_lang[user_id] = lang


def get_lang(user_id: int) -> str:
    """Return the stored language or the default one."""
    if not isinstance(user_id, int):
        logger.warning("Attempt to get language for non-integer user_id: %s", user_id)
        return _DEFAULT_LANG

    return _user_lang.get(user_id, _DEFAULT_LANG)


__all__ = ["set_lang", "get_lang"]
