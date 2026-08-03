"""Strict BeaconMatch parser layered over the scenario rescue routes and UI."""
from __future__ import annotations

import re
import scenario_rescue as legacy

DISCLAIMER = legacy.build_analysis("placeholder scenario with enough detail")["disclaimer"]
OUTCOMES = legacy.OUTCOMES


def _number(value: str):
    cleaned = value.replace(",", "")
    return float(cleaned) if "." in cleaned else int(cleaned)


def extract_facts(text: str) -> dict:
    raw = " ".join((text or "").split())
    low = raw.lower()
    facts = {}
    patterns = {
        "fico": [r"(?:fico|credit(?: score)?)\s*(?:of|is|:)?\s*(\d{3})", r"\b(\d{3})\s*fico\b"],
        "purchase_price": [
            r"(?:purchase(?: price)?|sales price|price)\s*(?:of|is|:)?\s*\$?([0-9][0-9,]*)",
            r"\$([0-9][0-9,]*)\s*(?:purchase|sales price|price)\b",
        ],
        "loan_amount": [r"(?:loan(?: amount)?|mortgage)\s*(?:of|is|:)?\s*\$?([0-9][0-9,]*)"],
        "down_payment_percent": [r"(\d+(?:\.\d+)?)\s*%\s*(?:down|down payment)"],
        "dti": [r"(?:dti|debt[- ]to[- ]income)\s*(?:of|is|:)?\s*(\d+(?:\.\d+)?)\s*%?"],
        "reserves_months": [r"(\d+)\s*(?:months?|mos?)\s*(?:of\s*)?reserves?"],
        "employment_years": [
            r"(?:self[- ]employed|in business|employed)\s*(?:for\s*)?(\d+(?:\.\d+)?)\s*(?:years?|yrs?)",
            r"(\d+(?:\.\d+)?)\s*(?:years?|yrs?)\s*(?:self[- ]employed|in business|employment)",
        ],
    }
    for key, variants in patterns.items():
        for pattern in variants:
            match = re.search(pattern, low, re.I)
            if match:
                facts[key] = _number(match.group(1))
                break
    state = re.search(r"\b(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)\b", raw)
    if state:
        facts["state"] = state.group(1)
    facts["transaction"] = "refinance" if re.search(r"\b(refi|refinance|cash[- ]out)\b", low) else "purchase" if "purchase" in low else None
    if any(x in low for x in ["self-employed", "self employed", "business owner"]):
        facts["income_type"] = "self_employed"
    elif any(x in low for x in ["w2", "w-2", "salary", "salaried"]):
        facts["income_type"] = "w2"
    if "primary" in low or "owner occupied" in low:
        facts["occupancy"] = "primary"
    elif "investment" in low or "rental" in low:
        facts["occupancy"] = "investment"
    elif "second home" in low:
        facts["occupancy"] = "second_home"
    if re.search(r"\b(veteran|va loan|va eligible)\b", low):
        facts["va_indicator"] = True
    if "first time" in low or "first-time" in low:
        facts["first_time_buyer"] = True
    if "late" in low:
        facts["recent_late"] = True
    if any(x in low for x in ["bankruptcy", "chapter 7", "chapter 13"]):
        facts["bankruptcy"] = True
    if "foreclosure" in low:
        facts["foreclosure"] = True
    return {key: value for key, value in facts.items() if value is not None}


def missing_information(facts: dict) -> list[str]:
    return legacy.missing_information(facts)


def rank_paths(facts: dict) -> list[dict]:
    return legacy.rank_paths(facts)


def build_analysis(text: str) -> dict:
    facts = extract_facts(text)
    paths = rank_paths(facts)
    missing = missing_information(facts)
    top = paths[0] if paths else {"name": "Human guideline review", "confidence": 30}
    questions = [f"Please confirm: {item}." for item in missing[:5]]
    email = (
        f"This scenario may have a path through {top['name']}, but I need to verify several details before giving direction. "
        + " ".join(questions[:3])
        + " Once those items and the AUS findings are available, I can help structure the next submission."
    )
    return {
        "facts": facts,
        "missing": missing,
        "paths": paths,
        "responses": {
            "email": email,
            "text": f"This may have a path through {top['name']}. Please send the AUS findings plus the missing items listed in BrokerBeacon so I can help structure it.",
            "call": f"I see a possible {top['name']} path. I would first confirm the missing facts, then review AUS findings and lender overlays before recommending structure.",
        },
        "disclaimer": DISCLAIMER,
    }


def install_scenario_rescue(app, db_path):
    legacy.extract_facts = extract_facts
    legacy.build_analysis = build_analysis
    return legacy.install_scenario_rescue(app, db_path)


__all__ = ["install_scenario_rescue", "extract_facts", "missing_information", "rank_paths", "build_analysis"]
