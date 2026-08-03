"""Copyright Metadata (per-book copyright_meta.json data model and templates).

Path: books/<slug>/edits/copyright_meta.json
Atomic write pattern (tmp + os.replace) matching common/cast_registry.py.
Safe default empty dictionary structure upon read errors.

TODO: When connecting copyright_text to Typst rendering in build_book.py / meta.json,
pick single target language from config.json target_lang (don't render both languages simultaneously).
"""
import os
import json
from typing import Dict, Any, Tuple

DEFAULT_COPYRIGHT_META: Dict[str, Any] = {
    "translator_name": "",
    "original_title": "",
    "original_author": "",
    "original_url": "",
    "original_license": "",
    "generated_text_uk": "",
    "generated_text_en": "",
    "edited_text_uk": None,
    "edited_text_en": None,
}

UK_TEMPLATE = (
    "Переклад і мовну адаптацію цього видання виконано {translator_name}\n"
    "за допомогою сервісу Vydra.\n\n"
    "Цей текст є перекладом та адаптацією документації «{original_title}»,\n"
    "створеної {original_author}, доступної за адресою {original_url}.\n\n"
    "Оригінальний текст поширюється на умовах ліцензії {original_license}.\n"
    "Переклад та адаптація здійснені відповідно до умов цієї ліцензії.\n\n"
    "Переклад згенеровано за допомогою автоматизованого перекладу з\n"
    "подальшим ручним редагуванням і перевіркою людиною-редактором: вибір\n"
    "формулювань, стилістична редакція та контроль якості кожного розділу\n"
    "виконані {translator_name}."
)

EN_TEMPLATE = (
    "Translation and adaptation of this edition by {translator_name},\n"
    "produced with the assistance of the Vydra service.\n\n"
    "This text is a translation and adaptation of the documentation\n"
    '"{original_title}", created by {original_author}, available at\n'
    "{original_url}.\n\n"
    "The original text is distributed under the {original_license} license.\n"
    "This translation and adaptation were made in accordance with the terms\n"
    "of that license.\n\n"
    "The translation was produced through automated translation followed by\n"
    "manual human editing and review: wording choices, stylistic editing,\n"
    "and quality control of each chapter were performed by\n"
    "{translator_name}."
)


def _copyright_meta_path(book_dir: str) -> str:
    return os.path.join(book_dir, "edits", "copyright_meta.json")


def load_copyright_meta(book_dir: str) -> Dict[str, Any]:
    """Load per-book copyright metadata dictionary from books/<slug>/edits/copyright_meta.json.

    Returns safe default dictionary on error or missing file.
    """
    res = dict(DEFAULT_COPYRIGHT_META)
    try:
        path = _copyright_meta_path(book_dir)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                res.update(data)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return res


def save_copyright_meta(book_dir: str, data: Dict[str, Any]) -> None:
    """Save per-book copyright metadata dictionary atomically (tmp + os.replace)."""
    path = _copyright_meta_path(book_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def generate_copyright_text(data: Dict[str, Any]) -> Tuple[str, str]:
    """Generate UK and EN copyright texts by substituting fields into templates."""
    fields = {
        "translator_name": str(data.get("translator_name") or ""),
        "original_title": str(data.get("original_title") or ""),
        "original_author": str(data.get("original_author") or ""),
        "original_url": str(data.get("original_url") or ""),
        "original_license": str(data.get("original_license") or ""),
    }
    uk_text = UK_TEMPLATE.format(**fields)
    en_text = EN_TEMPLATE.format(**fields)
    return uk_text, en_text


def get_effective_copyright_text(data: Dict[str, Any], lang: str = "uk") -> str:
    """Returns edited text if present (non-null), otherwise generated text."""
    if lang == "en":
        edited = data.get("edited_text_en")
        return edited if edited is not None else str(data.get("generated_text_en") or "")
    edited = data.get("edited_text_uk")
    return edited if edited is not None else str(data.get("generated_text_uk") or "")
