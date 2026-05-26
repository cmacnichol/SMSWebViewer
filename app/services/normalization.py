"""Phone number normalization (E.164) and SHA-256 hash utilities."""

import hashlib

import phonenumbers


def normalize_phone(raw: str, country_code: str = "US") -> str:
    """Normalize a phone number to E.164 format.

    Falls back to stripping non-digit characters (preserving leading +)
    when the number cannot be parsed or is invalid.
    """
    if not raw or not raw.strip():
        return raw or ""

    try:
        parsed = phonenumbers.parse(raw, country_code)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.E164
            )
    except phonenumbers.NumberParseException:
        pass

    # Fallback: strip non-numeric except leading +
    cleaned = raw.strip()
    if cleaned.startswith("+"):
        return "+" + "".join(c for c in cleaned[1:] if c.isdigit())
    return "".join(c for c in cleaned if c.isdigit())


def compute_hash(*fields) -> str:
    """Compute SHA-256 hash from composite fields for deduplication.

    Fields are joined with '|' separator before hashing.
    """
    composite = "|".join(str(f) for f in fields)
    return hashlib.sha256(composite.encode("utf-8")).hexdigest()
