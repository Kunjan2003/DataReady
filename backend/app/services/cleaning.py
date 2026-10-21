import re
from dateutil import parser
import phonenumbers

GST_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
SCHEMA = ["name", "phone", "email", "address", "city", "gst_number", "date", "amount", "product"]

ALIASES = {
 "name": ["name", "customer", "client", "party", "supplier", "vendor", "customer name", "party name"],
 "phone": ["phone", "mobile", "contact", "telephone", "phone number"],
 "email": ["email", "e-mail", "mail"], "address": ["address", "billing address", "location"],
 "city": ["city", "town", "district"], "gst_number": ["gst", "gstin", "gst number", "gst no"],
 "date": ["date", "purchase date", "invoice date", "transaction date"], "amount": ["amount", "price", "total", "invoice amount", "value"],
 "product": ["product", "item", "description", "product name"]}

def valid_gstin(value: str) -> bool:
    if not GST_RE.fullmatch(value): return False
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    total, factor = 0, 2
    for char in reversed(value[:14]):
        product = alphabet.index(char) * factor
        total += product // 36 + product % 36
        factor = 1 if factor == 2 else 2
    return alphabet[(36 - total % 36) % 36] == value[-1]

def suggest_mapping(columns):
    result = {}
    for col in columns:
        key = re.sub(r"[^a-z0-9]+", " ", str(col).lower()).strip()
        found = next((standard for standard, aliases in ALIASES.items() if key in aliases), None)
        if not found:
            found = next((standard for standard, aliases in ALIASES.items() if any(a in key for a in aliases if len(a) > 3)), None)
        if found and found not in result.values(): result[str(col)] = found
    return result

def normalize_phone(value):
    text = str(value or "").strip()
    if not text: return text
    try:
        parsed = phonenumbers.parse(text, "IN")
        if phonenumbers.is_valid_number(parsed): return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException: pass
    digits = re.sub(r"\D", "", text)
    if len(digits) == 10: return "+91" + digits
    if len(digits) == 12 and digits.startswith("91"): return "+" + digits
    return text

def clean_record(raw: dict, mapping: dict):
    data = {key: None for key in SCHEMA}
    for source, target in mapping.items():
        if target in data and source in raw:
            value = raw[source]
            data[target] = None if value is None else str(value).strip()
    changes, flags = [], []
    def set_value(field, new, why):
        old = data[field]
        if new is not None and str(new) != str(old):
            data[field] = new; changes.append((field, old, new, why))
    if data["name"]:
        n = re.sub(r"\s+", " ", data["name"]).strip()
        set_value("name", n.title(), "Trimmed spaces and standardized name capitalization")
    if data["phone"]:
        normalized = normalize_phone(data["phone"])
        if normalized == data["phone"] and not re.fullmatch(r"\+?[0-9]{10,13}", normalized): flags.append("phone needs review")
        set_value("phone", normalized, "Standardized Indian phone number")
    if data["email"]:
        v = data["email"].strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", v): flags.append("invalid email")
        set_value("email", v, "Trimmed and lowercased email")
    if data["gst_number"]:
        v = re.sub(r"\s+", "", data["gst_number"]).upper()
        if not valid_gstin(v): flags.append("invalid GST format or checksum")
        set_value("gst_number", v, "Removed spaces and standardized GST capitalization")
    if data["date"]:
        try:
            dt = parser.parse(data["date"], dayfirst=True, fuzzy=False)
            set_value("date", dt.date().isoformat(), "Standardized date to YYYY-MM-DD")
        except (ValueError, OverflowError): flags.append("invalid date")
    if data["amount"]:
        value = data["amount"].replace(",", "").replace("₹", "").strip()
        try: set_value("amount", f"{float(value):.2f}", "Standardized amount to two decimal places")
        except ValueError: flags.append("invalid amount")
    for field in ("address", "city", "product"):
        if data[field]: set_value(field, re.sub(r"\s+", " ", data[field]).strip(), "Trimmed and normalized spacing")
    return data, changes, flags
