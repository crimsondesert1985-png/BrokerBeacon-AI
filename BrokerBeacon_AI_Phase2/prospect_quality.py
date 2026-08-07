"""Shared quality rules for companies promoted into BrokerBeacon prospects."""
from __future__ import annotations

import re

GENERIC_EXACT = {
    "home", "about", "contact", "company state licenses", "state approval list",
    "find a loan officer", "meet our loan officers", "meet our team", "our team",
    "loan officers", "locations", "apply now", "annual report", "search results",
    "consumer access", "mortgage broker directory", "broker near me",
}
GENERIC_CONTAINS = (
    "best mortgage brokers", "top loan officers", "department of savings",
    "division of banks", "real estate in ", "nmls esb", "cyber fbi",
    "mortgage lenders loan officers", "state licenses", "approval list",
    "find a loan officer", "meet our loan officers", "meet our team",
    "best phoenix", "mortgage brokers in ", "loan officers in ",
    "top mortgage", "directory of ", "list of mortgage",
)
BUSINESS_SIGNALS = (
    "mortgage", "financial", "finance", "lending", "loans", "funding", "capital",
    "bankers", "brokerage", "home loans", "credit", "company", "corporation",
    "services", "solutions", "group", "partners", "associates",
)
LEGAL_SUFFIXES = (" llc", " inc", " corp", " corporation", " ltd", " lp", " plc", " co")


def norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def digits(value: object) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def valid_nmls(value: object) -> bool:
    number = digits(value)
    return 4 <= len(number) <= 12 and int(number or "0") > 0


def is_clean_company_name(name: object, *, trusted_roster: bool = False) -> bool:
    value = norm(name)
    if not value or value in GENERIC_EXACT or any(term in value for term in GENERIC_CONTAINS):
        return False
    if "::" in str(name or "") or len(value) < 3:
        return False
    words = value.split()
    if len(words) == 1 and value in {"home", "licenses", "team", "officers", "approval"}:
        return False
    # Person-shaped two-word names are not companies unless a business signal is present.
    has_business = any(signal in value for signal in BUSINESS_SIGNALS) or any(value.endswith(suffix.strip()) for suffix in LEGAL_SUFFIXES)
    if len(words) == 2 and not has_business and not trusted_roster:
        return False
    return True


def is_publishable_prospect(name: object, nmls: object, source: object = "") -> bool:
    trusted_roster = "official regulator" in norm(source) or "division of finance" in norm(source)
    return is_clean_company_name(name, trusted_roster=trusted_roster) and valid_nmls(nmls)


__all__ = ["norm", "digits", "valid_nmls", "is_clean_company_name", "is_publishable_prospect"]
