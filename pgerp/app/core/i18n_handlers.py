"""PyGo ERP V2.0 — i18n handlers."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app"))

from core.i18n import SUPPORTED_LANGS, DEFAULT_LANG, get_lang, set_lang, t, translate, get_all_translations
from core.registry import register


@register("core.i18n.langs")
def i18n_langs(**kwargs):
    """Get supported languages."""
    return {"languages": SUPPORTED_LANGS, "default": DEFAULT_LANG, "current": get_lang()}


@register("core.i18n.translate")
def i18n_translate(text=None, target=None, **kwargs):
    """Translate text."""
    if not text:
        return {"error": "text required"}
    return {"translated": translate(text, target_lang=target or get_lang()), "lang": target or get_lang()}


@register("core.i18n.all")
def i18n_all(lang=None, **kwargs):
    """Get all translations for a language."""
    return get_all_translations(lang)


@register("core.i18n.set")
def i18n_set(lang=None, **kwargs):
    """Set current language."""
    if not lang or lang not in SUPPORTED_LANGS:
        return {"error": f"language must be one of {SUPPORTED_LANGS}"}
    set_lang(lang)
    return {"language": lang}
