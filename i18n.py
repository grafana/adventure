"""
Localization support using GNU gettext.

Set LANGUAGE or LANG (e.g. fr_FR, fr) to choose locale. Uses the 'adventure'
message domain and the locale/ directory next to this package.
"""
import gettext
import os

# Directory containing this file (adventure/)
_this_dir = os.path.dirname(os.path.abspath(__file__))
_locale_dir = os.path.join(_this_dir, "locale")
_domain = "adventure"


def _get_translation():
    languages = os.environ.get("LANGUAGE") or os.environ.get("LANG") or ""
    # LANGUAGE can be "fr_FR:fr:en"; we want a list like ["fr_FR", "fr", "en"]
    if languages:
        languages = [lang.strip() for lang in languages.split(":") if lang.strip()]
    else:
        languages = None  # use default locale
    try:
        t = gettext.translation(
            _domain,
            localedir=_locale_dir,
            languages=languages,
            fallback=True,
        )
        return t.gettext
    except OSError:
        return gettext.gettext


# Use this in application code for translatable strings
_ = _get_translation()
