import difflib
import json
import re
from pathlib import Path

MEDICINES = json.loads((Path(__file__).parent / "medicines.json").read_text(encoding="utf-8"))

# Wording that sounds like a diagnosis, a cause, or treatment advice
BANNED = [
    r"\byou have\b", r"\byou are suffering\b", r"\byou might have\b", r"\byou may have\b",
    r"\bdiagnos", r"\bindicates?\b", r"\bsuggests? that\b", r"\bsuggests? (a|an|you)\b",
    r"\bcaus(e|es|ed|ing)\b", r"\bdue to\b", r"\bsign of\b", r"\bsymptom of\b",
    r"\bcould be (a |an )?(disease|disorder|infection|condition)", r"\bsuffering\b",
    r"\byou should (take|stop|start|avoid|eat|drink|increase|reduce|use)\b",
    r"\bstop taking\b", r"\bstart taking\b", r"\bi recommend\b", r"\bwe recommend\b",
    r"\byou need to (take|stop|start)\b", r"\b(increase|reduce|skip) (your|the) (dose|medicine|medication)\b",
]
BANNED_RE = re.compile("|".join(BANNED), re.IGNORECASE)

DEFAULT_QUESTIONS = [
    "Can you explain my results in simple words?",
    "Which of these results should I pay the most attention to?",
    "Do any of these tests need to be repeated?",
    "Is there anything I should ask or tell you about my health history?",
    "When should I come back for a follow-up?",
]
DEFAULT_SUMMARY = (
    "This document lists test results or medicines. "
    "Please read the table below and discuss it with your doctor."
)


def is_unsafe(text: str) -> bool:
    return bool(BANNED_RE.search(text or ""))


def clean_sentences(text: str, fallback: str = "") -> str:
    """Remove any sentence with diagnosis or treatment wording."""
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    kept = [p for p in parts if p and not is_unsafe(p)]
    return " ".join(kept) if kept else fallback


def clean_info(info: dict) -> dict:
    """Filter the AI's summary, explanations and doctor questions."""
    cleaned = {
        "summary": clean_sentences(info.get("summary", ""), DEFAULT_SUMMARY),
        "explanations": {
            k: clean_sentences(v, "") for k, v in (info.get("explanations") or {}).items()
        },
    }
    questions = [q for q in (info.get("questions_for_doctor") or []) if q and not is_unsafe(q)]
    for q in DEFAULT_QUESTIONS:
        if len(questions) >= 5:
            break
        if q not in questions:
            questions.append(q)
    cleaned["questions_for_doctor"] = questions[:8]
    return cleaned


def _normalize_med(name: str) -> str:
    name = re.sub(r"\d+(\.\d+)?\s*(mg|mcg|g|ml|iu)?", " ", str(name).lower())
    name = re.sub(r"\b(tab|tablet|cap|capsule|syp|syrup|inj|injection|oint|drops?)\b\.?", " ", name)
    name = re.sub(r"[^a-z ]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def check_medicine(name, dosage=None, frequency=None, duration=None) -> str:
    """Returns 'ok' or a short warning text."""
    joined = f"{name} {dosage} {frequency} {duration}".lower()
    if "unclear" in joined or "?" in joined:
        return "⚠ Hard to read. Please verify with your doctor or pharmacist"
    norm = _normalize_med(name)
    if not norm:
        return "⚠ Name missing. Please verify"
    words = norm.split()
    for candidate in [norm] + words:
        if difflib.get_close_matches(candidate, MEDICINES, n=1, cutoff=0.8):
            return "ok"
    return "⚠ Name not recognised. It may be misread. Please verify"