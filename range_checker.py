import json
import re
from pathlib import Path

RANGES_PATH = Path(__file__).parent / "ranges.json"

with open(RANGES_PATH, "r", encoding="utf-8") as f:
    RANGES = json.load(f)

ALIAS_MAP = {}
for main_name, info in RANGES.items():
    ALIAS_MAP[main_name.lower()] = main_name
    for alias in info.get("aliases", []):
        ALIAS_MAP[alias.lower()] = main_name


def normalize_name(name: str) -> str:
    name = str(name).lower().strip()
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def find_test(name: str):
    return ALIAS_MAP.get(normalize_name(name))


def to_number(value):
    """Convert '12.5', '134L', '<200' or '1,50,000' to a float. None if it fails."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d[\d,]*\.?\d*", str(value))
    if not match:
        return None
    try:
        return float(match.group().replace(",", ""))
    except ValueError:
        return None


def check_value(name, value, report_min=None, report_max=None):
    """Returns {status, min, max, source}. Uses the report's range first, then ranges.json."""
    num = to_number(value)
    low = to_number(report_min)
    high = to_number(report_max)
    source = "report"

    if low is None and high is None:
        test = find_test(name)
        if test is None:
            return {"status": "unknown", "min": None, "max": None, "source": "none"}
        low = RANGES[test]["min"]
        high = RANGES[test]["max"]
        source = "reference file"

    if num is None:
        return {"status": "unknown", "min": low, "max": high, "source": source}

    if low is not None and num < low:
        status = "low"
    elif high is not None and num > high:
        status = "high"
    else:
        status = "normal"

    return {"status": status, "min": low, "max": high, "source": source}


def printed_flag(value):
    """Reads an H or L printed after the value, like '151H' or '3.0L'."""
    match = re.search(r"([HL])\s*$", str(value).strip(), re.IGNORECASE)
    if not match:
        return None
    return "high" if match.group(1).upper() == "H" else "low"


def resolve_statuses(tests):
    """
    Final status for every test, in the same order as `tests`.
    1. The H/L flag printed on the report wins (most reliable).
    2. Otherwise our own range check is used.
    3. If the report prints flags but our check says abnormal with no printed flag,
       the range was probably misread, so we mark it 'unknown' instead of guessing.
    """
    uses_flags = any(printed_flag(t.get("value")) for t in tests)
    out = []
    for t in tests:
        res = check_value(t.get("name", ""), t.get("value"), t.get("report_min"), t.get("report_max"))
        flag = printed_flag(t.get("value"))
        if flag:
            res["status"], res["source"] = flag, "flag printed on report"
        elif uses_flags and not t.get("edited") and res["status"] in ("low", "high"):
            res["status"], res["source"] = "unknown", "range may be misread, please verify"
        out.append(res)
    return out


if __name__ == "__main__":
    print(check_value("Hb", "10.2"))
    print(check_value("SGPT", 80))
    print(check_value("Glucose", 90, 70, 110))
    print(check_value("Some Rare Test", 5))
    print(printed_flag("151H"), printed_flag("3.0L"), printed_flag("102"))