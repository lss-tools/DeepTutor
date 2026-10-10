"""Russian UI locale integration tests."""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from deeptutor.services.config.launch_settings import (
    _normalize_language as _launch_language,
)
from deeptutor.services.config.settings_spec import _LANGUAGE_CHOICES
from deeptutor.services.prompt.language import language_directive, language_label
from deeptutor.services.settings.interface_settings import _normalize_language

WEB = pathlib.Path(__file__).resolve().parents[2] / "web"


def _catalog(locale: str) -> dict[str, str]:
    return json.loads((WEB / f"locales/{locale}/app.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "raw",
    [
        "ru",
        "RU",
        " ru ",
        "russian",
        "ru-RU",
        "ru_RU",
    ],
)
def test_normalizer_accepts_russian_spellings(raw: str) -> None:
    assert _normalize_language(raw) == "ru"


def test_launch_settings_accept_russian() -> None:
    assert _launch_language("ru-RU") == "ru"
    assert _launch_language("russian") == "ru"


def test_settings_offers_russian() -> None:
    assert "ru" in {code for code, _label, _desc in _LANGUAGE_CHOICES}


def test_language_directive_names_russian() -> None:
    assert language_label("ru") == "Русский"
    assert "Русский" in language_directive("ru")


def test_web_locale_covers_every_english_key() -> None:
    en = _catalog("en")
    ru = _catalog("ru")

    assert set(en) <= set(ru)

    extras = set(ru) - set(en)
    assert all(key.endswith(("_few", "_many")) for key in extras)


def test_web_locale_keeps_interpolation_placeholders() -> None:
    en = _catalog("en")
    ru = _catalog("ru")

    pattern = re.compile(r"\{\{[^}]+\}\}")

    mismatches = [
        key
        for key in set(en) & set(ru)
        if set(pattern.findall(en[key])) != set(pattern.findall(ru[key]))
    ]

    assert mismatches == []


def test_every_locale_can_name_russian() -> None:
    for locale in ("en", "zh", "fr", "de", "uk", "pl", "ru"):
        assert "language.russian" in _catalog(locale)


def test_frontend_registers_russian() -> None:
    languages = (WEB / "i18n/languages.ts").read_text(encoding="utf-8")
    assert '{ code: "ru", labelKey: "language.russian" }' in languages

    init = (WEB / "i18n/init.ts").read_text(encoding="utf-8")
    assert "@/locales/ru/app.json" in init
