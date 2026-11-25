import io
import re
import fitz  # pymupdf
import pandas as pd
import streamlit as st
from PIL import Image

from llm import explain_data, extract_data
from range_checker import resolve_statuses
from safety import check_medicine

st.set_page_config(page_title="Medical Report Explainer", page_icon="🩺", layout="wide")

DISCLAIMER = (
    "⚠️ **This is not medical advice or a diagnosis.** This tool only explains what is "
    "written on your document in simple language. Only a doctor can tell you what your "
    "results mean for your health."
)

LABELS = {"low": "⬇ Low", "high": "⬆ High", "normal": "✓ Normal", "unknown": "? Not checked"}
COLORS = {"low": "#fff3cd", "high": "#f8d7da", "normal": "#d1e7dd", "unknown": "#e2e3e5"}
ORDER = {"high": 0, "low": 1, "unknown": 2, "normal": 3}


def load_image(file):
    """Open an image, or turn the first page of a PDF into an image."""
    raw = file.getvalue()
    if getattr(file, "name", "").lower().endswith(".pdf"):
        doc = fitz.open(stream=raw, filetype="pdf")
        pix = doc[0].get_pixmap(dpi=200)
        return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return Image.open(io.BytesIO(raw))


def fmt_range(low, high):
    if low is None and high is None:
        return "—"
    if low is None:
        return f"up to {high:g}"
    if high is None:
        return f"{low:g} and above"
    return f"{low:g} – {high:g}"


def s(v):
    """Value to text for the editable table."""
    return "" if v is None else str(v)


def back(v):
    """Edited text back to a value (empty becomes None)."""
    v = str(v).strip()
    return None if v in ("", "None", "nan") else v


def tests_to_df(tests):
    return pd.DataFrame([{
        "Test": s(t["name"]), "Value": s(t["value"]), "Unit": s(t["unit"]),
        "Normal min": s(t["report_min"]), "Normal max": s(t["report_max"]),
    } for t in tests], columns=["Test", "Value", "Unit", "Normal min", "Normal max"])


def meds_to_df(meds):
    return pd.DataFrame([{
        "Medicine": s(m["name"]), "Dosage": s(m["dosage"]),
        "How often": s(m["frequency"]), "Duration": s(m["duration"]),
    } for m in meds], columns=["Medicine", "Dosage", "How often", "Duration"])


def df_to_tests(df, original):
    out = []
    for idx, r in df.iterrows():
        if not back(r["Test"]):
            continue
        value, lo, hi = back(r["Value"]), back(r["Normal min"]), back(r["Normal max"])
        edited = True  # rows added by the patient count as edited
        if isinstance(idx, int) and idx < len(original):
            o = original[idx]
            edited = (value != back(s(o["value"])) or lo != back(s(o["report_min"]))
                      or hi != back(s(o["report_max"])))
        if edited and value:
            value = re.sub(r"\s*[HLhl]\s*$", "", value)  # drop the old printed flag
        out.append({"name": back(r["Test"]), "value": value, "unit": back(r["Unit"]),
                    "report_min": lo, "report_max": hi, "edited": edited})
    return out


def df_to_meds(df):
    out = []
    for _, r in df.iterrows():
        if back(r["Medicine"]):
            out.append({"name": back(r["Medicine"]), "dosage": back(r["Dosage"]),
                        "frequency": back(r["How often"]), "duration": back(r["Duration"])})
    return out


def color_rows(row):
    return [f"background-color: {COLORS[row['_status']]}; color: black"] * len(row)


def reset_state():
    for k in ("extracted", "final"):
        st.session_state.pop(k, None)


# ---------------- UI ----------------
st.title("🩺 Medical Report Explainer")
st.caption("Upload a lab report or prescription (photo or PDF) and get a simple explanation.")
st.warning(DISCLAIMER)

file = st.file_uploader("Upload a photo or PDF", type=["jpg", "jpeg", "png", "webp", "pdf"])

if not file:
    st.stop()

# Reset everything when a new file is chosen
file_key = str(getattr(file, "file_id", None) or f"{getattr(file, 'name', 'camera')}-{file.size}")
if st.session_state.get("file_key") != file_key:
    reset_state()
    st.session_state["file_key"] = file_key

image = load_image(file)

# ---------- Step 1: read ----------
if "extracted" not in st.session_state:
    st.image(image, caption="Your document", width=350)
    if st.button("Read my document", type="primary"):
        with st.spinner("Reading your document..."):
            try:
                st.session_state["extracted"] = extract_data(image)
                st.rerun()
            except Exception as e:
                st.error(f"Something went wrong: {e}. Try a clearer photo or try again in a minute.")
    st.stop()

data = st.session_state["extracted"]
if data["report_type"] == "unknown":
    st.error("This doesn't look like a lab report or prescription. Please upload a clearer photo.")
    st.image(image, width=350)
    st.stop()

# ---------- Step 2: check what we read ----------
st.header("Step 1: Check what we read")
st.info("AI can misread, especially handwriting. Compare with your original and fix anything wrong. "
        "Items marked UNCLEAR could not be read. Fill them in or delete the row.")

left, right = st.columns([1, 2])
with left:
    st.image(image, caption="Your original", use_container_width=True)
with right:
    edited_tests, edited_meds = None, None
    if data["tests"]:
        st.markdown("**Test results**")
        edited_tests = st.data_editor(tests_to_df(data["tests"]), num_rows="dynamic",
                                      use_container_width=True, hide_index=True, key=f"tests_editor_{file_key}")
    if data["medicines"]:
        st.markdown("**Medicines**")
        edited_meds = st.data_editor(meds_to_df(data["medicines"]), num_rows="dynamic",
                                     use_container_width=True, hide_index=True, key=f"meds_editor_{file_key}")

if st.button("✅ Confirm and explain", type="primary"):
    confirmed = {
        "report_type": data["report_type"],
        "tests": df_to_tests(edited_tests, data["tests"]) if edited_tests is not None else [],
        "medicines": df_to_meds(edited_meds) if edited_meds is not None else [],
    }
    with st.spinner("Preparing your explanation..."):
        try:
            info = explain_data(confirmed)
            st.session_state["final"] = {"data": confirmed, "info": info}
        except Exception as e:
            st.error(f"Something went wrong: {e}. Please try again in a minute.")

final = st.session_state.get("final")
if not final:
    st.stop()

# ---------- Step 3: results ----------
data, info = final["data"], final["info"]
explanations = info.get("explanations") or {}

st.divider()
st.header("Step 2: Your explanation")
st.subheader("📝 Summary")
st.write(info.get("summary", ""))

tests = data["tests"]
if tests:
    rows = []
    for t, res in zip(tests, resolve_statuses(tests)):
        rows.append({
            "Test": t["name"],
            "Your value": f"{t['value'] or ''} {t['unit'] or ''}".strip(),
            "Normal range": fmt_range(res["min"], res["max"]),
            "Status": LABELS[res["status"]],
            "What it measures": explanations.get(t["name"], ""),
            "Range source": res["source"],
            "_status": res["status"],
        })
    rows.sort(key=lambda r: ORDER[r["_status"]])
    df = pd.DataFrame(rows)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("⬆ High", int((df["_status"] == "high").sum()))
    c2.metric("⬇ Low", int((df["_status"] == "low").sum()))
    c3.metric("✓ Normal", int((df["_status"] == "normal").sum()))
    c4.metric("? Not checked", int((df["_status"] == "unknown").sum()))

    st.subheader("🔬 Your results")
    st.caption("Values outside the normal range are shown first and highlighted.")
    st.dataframe(df.style.apply(color_rows, axis=1), use_container_width=True,
                 hide_index=True, column_config={"_status": None})

meds = data["medicines"]
if meds:
    st.subheader("💊 Medicines")
    med_rows, warnings = [], 0
    for m in meds:
        check = check_medicine(m["name"], m["dosage"], m["frequency"], m["duration"])
        warnings += check != "ok"
        med_rows.append({
            "Medicine": m["name"], "Dosage": m["dosage"] or "", "How often": m["frequency"] or "",
            "For how long": m["duration"] or "",
            "What it is generally used for": explanations.get(m["name"], ""),
            "Check": "✓ Recognised" if check == "ok" else check,
        })
    st.dataframe(pd.DataFrame(med_rows), use_container_width=True, hide_index=True)
    if warnings:
        st.warning("Some medicine names could not be confirmed. Please check them with your "
                   "doctor or pharmacist before taking anything.")

questions = info.get("questions_for_doctor") or []
if questions:
    st.subheader("❓ Questions to ask your doctor")
    for q in questions:
        st.markdown(f"- {q}")

st.divider()
st.info(DISCLAIMER)