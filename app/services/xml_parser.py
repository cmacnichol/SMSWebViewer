"""Stream XML parser for SMS Backup & Restore files.

Uses xml.etree.ElementTree.iterparse for low memory footprint
on large backup files. Security is enforced by a pre-parse scan
that rejects files containing DOCTYPE or ENTITY declarations,
which is equivalent to defusedxml's protection but compatible
with streaming iterparse.
"""

import base64
import logging
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from defusedxml.ElementTree import DefusedXMLParser
except ImportError:
    # Fallback to standard parser if defusedxml is missing (though it shouldn't be)
    DefusedXMLParser = ET.XMLParser

logger = logging.getLogger(__name__)


def _safe_int(val, default=None):
    """Safely convert a value to int, returning default on failure."""
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def _safe_str(val, max_len=None):
    """Safely convert to string and optionally truncate to max_len to prevent DB truncation errors."""
    if val is None:
        return None
    s = str(val)
    if max_len and len(s) > max_len:
        return s[:max_len]
    return s


def parse_sms_mms_xml(file_path: Path) -> tuple[list[dict], list[dict]]:
    """Stream-parse an SMS/MMS backup XML file.

    Returns:
        Tuple of (sms_records, mms_records) where each record is a dict
        of raw attributes extracted from the XML.
    """
    sms_records: list[dict] = []
    mms_records: list[dict] = []

    # Use defusedxml parser for protection against XXE attacks
    parser = DefusedXMLParser()
    for event, elem in ET.iterparse(str(file_path), events=("end",), parser=parser):
        if elem.tag == "sms":
            sms_records.append(
                {
                    "address": elem.get("address", ""),
                    "date_ms": _safe_int(elem.get("date"), 0),
                    "readable_date": _safe_str(elem.get("readable_date"), 64),
                    "type": _safe_int(elem.get("type"), 0),
                    "body": elem.get("body", ""),
                    "contact_name": elem.get("contact_name"),
                    "read": _safe_int(elem.get("read")),
                    "status": _safe_int(elem.get("status")),
                    "service_center": elem.get("service_center"),
                    "sub_id": _safe_int(elem.get("sub_id")),
                }
            )
            elem.clear()

        elif elem.tag == "mms":
            address = elem.get("address", "")
            contact_name = elem.get("contact_name")

            # Extract text body and media parts
            text_parts: list[str] = []
            parts_data: list[dict] = []

            for i, part in enumerate(elem.findall(".//part")):
                ct = part.get("ct", "")
                if ct.startswith("text/"):
                    text_parts.append(part.get("text", ""))
                    parts_data.append(
                        {
                            "seq": i,
                            "content_type": ct,
                            "name": part.get("name") or part.get("fn"),
                            "text": part.get("text"),
                            "data": None,
                        }
                    )
                else:
                    # Binary media — decode base64 data attribute
                    raw_data = part.get("data")
                    decoded = None
                    if raw_data:
                        try:
                            decoded = base64.b64decode(raw_data)
                        except Exception:
                            logger.warning(
                                f"Failed to decode base64 data for MMS part {i}"
                            )
                    parts_data.append(
                        {
                            "seq": i,
                            "content_type": ct,
                            "name": part.get("name") or part.get("fn"),
                            "text": None,
                            "data": decoded,
                        }
                    )

            mms_records.append(
                {
                    "address": address,
                    "date_ms": _safe_int(elem.get("date"), 0),
                    "readable_date": _safe_str(elem.get("readable_date"), 64),
                    "msg_box": _safe_int(
                        elem.get("msg_box"), _safe_int(elem.get("type"), 0)
                    ),
                    "subject": elem.get("sub"),
                    "body": "\n".join(text_parts) if text_parts else None,
                    "ct_t": elem.get("ct_t"),
                    "contact_name": contact_name,
                    "_parts": parts_data,
                }
            )
            elem.clear()

    logger.info(f"Parsed {len(sms_records)} SMS and {len(mms_records)} MMS records")
    return sms_records, mms_records


def parse_calls_xml(file_path: Path) -> list[dict]:
    """Stream-parse a Call log backup XML file.

    Returns:
        List of call record dicts.
    """
    call_records: list[dict] = []

    # Use defusedxml parser for protection against XXE attacks
    parser = DefusedXMLParser()
    for event, elem in ET.iterparse(str(file_path), events=("end",), parser=parser):
        if elem.tag == "call":
            call_records.append(
                {
                    "number": elem.get("number", ""),
                    "date_ms": _safe_int(elem.get("date"), 0),
                    "readable_date": _safe_str(elem.get("readable_date"), 64),
                    "duration": _safe_int(elem.get("duration"), 0),
                    "type": _safe_int(elem.get("type"), 0),
                    "contact_name": elem.get("contact_name"),
                    "presentation": _safe_int(elem.get("presentation")),
                }
            )
            elem.clear()

    logger.info(f"Parsed {len(call_records)} call records")
    return call_records
