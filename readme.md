# 🩺 Medical Report Explainer

A multimodal app that reads a **lab report or prescription** and explains it to patients in simple language. It highlights values outside the normal range and lists questions to ask the doctor. **It never gives a diagnosis.**

Built for the Wisework x Imagenext Hackathon.

## Features
- Upload a photo or PDF
- Works with lab reports and prescriptions (printed and handwritten)
- **Check what we read:** the patient reviews and corrects the extracted data next to the original photo before anything is explained
- Color-coded High / Low / Normal status, with abnormal values shown first
- Simple-language explanation of each test or medicine
- Neutral questions to ask the doctor
- Medicine name check, with warnings for unclear or unrecognised names
- Clear "not a diagnosis" disclaimers

## How it works
1. **Vision model (Groq, Qwen)** reads the image and extracts test or medicine rows. Anything unreadable is marked UNCLEAR instead of guessed.
2. **Patient confirms** the data in an editable table.
3. **Rule-based range check (`range_checker.py`)** decides High / Low / Normal. It uses the report's printed range and flags first, and `ranges.json` as a fallback. The AI does not decide this.
4. **Text model (Groq, GPT-OSS)** writes the plain-language summary, explanations and doctor questions.
5. **Safety filter (`safety.py`)** removes any sentence with diagnosis, cause or treatment-advice wording.
6. **Medicine check** fuzzy-matches drug names against `medicines.json` and warns on unknown names.

## Safety design
- No diagnosis, no cause, no treatment or dose advice, enforced in the prompt and again in code
- Status flags come from code, not the AI
- The human confirms the extracted data before any explanation
- Uncertain items are flagged, never silently guessed
- Patient name, ID and doctor name are never extracted

## Tech stack
Python, Streamlit, Groq API (Qwen vision + GPT-OSS text), Pillow, PyMuPDF, pandas

## Run locally
```bash
git https://github.com/gokuldivkr/Medical-Report-Explainer.git
cd Medical-Report-Explainer
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```
Create a `.env` file (get a free key at console.groq.com):
```
GROQ_API_KEY=your_key_here
GROQ_VISION_MODEL=qwen/qwen3.8-27b
GROQ_TEXT_MODEL=openai/gpt-oss-120b
```
Then run:
```bash
streamlit run app.py
```

## Project structure
| File | Purpose |
|---|---|
| `app.py` | Streamlit UI and the confirm-then-explain flow |
| `llm.py` | Groq calls and prompts |
| `range_checker.py` | Rule-based High/Low/Normal logic |
| `safety.py` | Diagnosis-wording filter and medicine check |
| `ranges.json` | Reference ranges for common tests |
| `medicines.json` | Common medicine names |

## Limitations
- AI can misread blurry photos and handwriting, so verification is built in
- Reads page 1 of PDFs only
- Reference ranges are general adult values, and the report's own range is always used first
- Free API tier has rate limits

## Team
- [Name]: UI
- [Name]: LLM integration and prompts
- [Name]: Range logic and testing
- [Name]: Safety, README and demo

> ⚠️ Not medical advice. For information only. Always consult a doctor.