import base64
import io
import json
import os
import re

from dotenv import load_dotenv
from groq import Groq
from PIL import Image

from range_checker import resolve_statuses
from safety import clean_info

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "openai/gpt-oss-120b")

EXTRACT_PROMPT = """You read a photo of a lab report or a prescription (printed or handwritten) and extract the data. Do not explain anything.

Rules:
- Copy values exactly as printed or written, including any H or L letter. Never guess.
- If any part is hard to read, write "UNCLEAR" for that part. A wrong medicine name is dangerous, so prefer "UNCLEAR" over a guess.
- Read each row left to right, one row at a time. Name, value, unit and range must all come from the SAME row.
- If a row has no printed range, use null for lo and hi. Never reuse another row's range or unit.
- Do NOT extract patient name, ID, age or doctor name.
- If the image is not a lab report or prescription, use report_type "unknown".
- Output ONE line of compact JSON. No line breaks, no markdown.

Format:
{"report_type":"lab_report","tests":[{"n":"NAME","v":"value","u":"unit","lo":null,"hi":null}],"medicines":[{"n":"NAME","d":"dosage","f":"frequency","t":"duration"}]}
For lab reports leave "medicines" empty. For prescriptions leave "tests" empty."""

EXPLAIN_PROMPT = """You explain medical report contents to patients in very simple words.

STRICT RULES:
- NEVER diagnose any disease or condition.
- NEVER recommend, change, start or stop any treatment, medicine or dose.
- NEVER say what a result means for the patient's health or what might be causing it. Only describe what a test measures, or what a medicine is generally used for, in general terms.
- Use short, simple words.
- If an item contains UNCLEAR, do not explain it. Use the text "Could not be read clearly".
- Questions for the doctor must be neutral, such as "Can you explain my X result?" or "Should this test be repeated?". Never suggest a cause or a condition.

You get a list of items from the patient's document, each with a status in brackets. Return ONLY valid JSON:
{"summary":"2-3 sentence plain overview of what the document contains",
 "explanations":{"<item name exactly as given>":"one short sentence of what it measures or what the medicine is generally used for"},
 "questions_for_doctor":["5 to 8 neutral questions the patient can ask their doctor, mentioning specific out-of-range items when there are any"]}"""


def prepare_image(image: Image.Image, max_side: int = 2000) -> str:
    image = image.convert("RGB")
    image.thumbnail((max_side, max_side))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def clean_text(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
    text = text.replace("```json", "").replace("```", "").strip()
    start = text.find("{")
    return text[start:] if start != -1 else text


def extract_json(text: str) -> dict:
    text = clean_text(text)
    end = text.rfind("}")
    if end == -1:
        raise ValueError("No JSON found in model response")
    return json.loads(text[:end + 1])


def repair_json(text: str) -> dict:
    """Parse JSON; if the output was cut off, keep the complete rows."""
    text = clean_text(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    closers = ["", "]", "}", "]}", "}]", "}]}", "]}]}", "}],\"medicines\":[]}", "]}],\"medicines\":[]}"]
    for cut in range(len(text) - 1, 0, -1):
        if text[cut] not in "}]":
            continue
        for closing in closers:
            try:
                return json.loads(text[:cut + 1] + closing)
            except json.JSONDecodeError:
                continue
    raise ValueError("Could not read the model's response")


def chat(kwargs, reasoning_effort):
    """Call Groq with a reasoning setting; retry without it if the model rejects it."""
    try:
        return client.chat.completions.create(reasoning_effort=reasoning_effort, **kwargs)
    except Exception as e:
        if "reasoning" not in str(e).lower():
            raise
        return client.chat.completions.create(**kwargs)


def extract_data(image: Image.Image) -> dict:
    """Step 1: the vision model reads the image (short output)."""
    kwargs = dict(
        model=VISION_MODEL,
        messages=[
            {"role": "system", "content": EXTRACT_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": "Extract the data and return the JSON."},
                {"type": "image_url", "image_url": {"url": prepare_image(image)}},
            ]},
        ],
        temperature=0.1,
        max_tokens=950,
    )
    response = chat(kwargs, "none")
    raw = repair_json(response.choices[0].message.content)

    tests = [
        {"name": r.get("n"), "value": r.get("v"), "unit": r.get("u"),
         "report_min": r.get("lo"), "report_max": r.get("hi")}
        for r in (raw.get("tests") or []) if isinstance(r, dict) and r.get("n")
    ]
    medicines = [
        {"name": r.get("n"), "dosage": r.get("d"), "frequency": r.get("f"), "duration": r.get("t")}
        for r in (raw.get("medicines") or []) if isinstance(r, dict) and r.get("n")
    ]
    report_type = raw.get("report_type", "unknown")
    if not tests and not medicines:
        report_type = "unknown"
    return {"report_type": report_type, "tests": tests, "medicines": medicines}


def explain_data(data: dict) -> dict:
    """Step 2: the text model writes the plain-language parts. Uses the patient-confirmed data."""
    lines = []
    tests = data.get("tests") or []
    for t, res in zip(tests, resolve_statuses(tests)):
        lines.append(f"{t.get('name')}: {t.get('value')} {t.get('unit') or ''} [{res['status']}]")
    for m in data.get("medicines") or []:
        lines.append(f"{m.get('name')}: {m.get('dosage')} {m.get('frequency')} {m.get('duration')}")

    kwargs = dict(
        model=TEXT_MODEL,
        messages=[
            {"role": "system", "content": EXPLAIN_PROMPT},
            {"role": "user", "content": f"Document type: {data.get('report_type')}\nItems:\n" + "\n".join(lines)},
        ],
        temperature=0.3,
        max_tokens=3000,
    )
    response = chat(kwargs, "low")
    return clean_info(extract_json(response.choices[0].message.content))


if __name__ == "__main__":
    img = Image.open("sample_report.jpg")
    d = extract_data(img)
    print(json.dumps(explain_data(d), indent=2))