# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

import json
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class DatabaseRequest(Document):
    pass


# @frappe.whitelist()
# def generate_pan_update_report():
#     """
#     Generate a consolidated PAN Update CSV from all Database Request records.
#     De-duplicate by (pan, account_number).
#     Returns: dict with file_url and file_name.
#     """

#     # Fetch all Database Request docs (add filters if needed later)
#     db_requests = frappe.get_all(
#         "Database Request",
#         fields=["name", "synced_payload"],
#         order_by="creation asc",
#     )

#     seen_keys = set()
#     rows = []

#     # Header row
#     headers = [
#         "sr_no",
#         "cif_id",
#         "field_name",
#         "application_id",
#         "pan",
#         "account_number",
#         "account_open_date",
#         "aadhaar_number",
#         "agent_code",
#         "source_doc",
#     ]

#     for db_req in db_requests:
#         payload_raw = db_req.get("synced_payload")
#         if not payload_raw:
#             continue

#         try:
#             payload = json.loads(payload_raw) if isinstance(
#                 payload_raw, str) else payload_raw
#         except Exception:
#             # Skip malformed JSON
#             continue

#         if not isinstance(payload, list):
#             continue

#         for item in payload:
#             values = item.get("values") or {}
#             sr_no = item.get("sr_no")

#             pan = values.get("pan")
#             account_number = values.get("account_number")

#             # Skip if PAN or account_number missing (optional; adjust if you want to keep them)
#             if not pan or not account_number:
#                 continue

#             key = (str(pan).strip(), str(account_number).strip())
#             if key in seen_keys:
#                 continue

#             seen_keys.add(key)

#             row = {
#                 "sr_no": sr_no,
#                 "cif_id": values.get("orgkey"),
#                 "field_name": values.get("field_name"),
#                 "application_id": values.get("application_id"),
#                 "pan": pan,
#                 "account_number": account_number,
#                 "account_open_date": values.get("account_open_date"),
#                 "aadhaar_number": values.get("aadhaar_number"),
#                 "agent_code": values.get("agent_code"),
#                 "source_doc": db_req.name,
#             }
#             rows.append(row)

#     if not rows:
#         return None

#     # Build CSV content
#     import csv
#     import io

#     output = io.StringIO()
#     writer = csv.DictWriter(output, fieldnames=headers)
#     writer.writeheader()
#     writer.writerows(rows)
#     csv_content = output.getvalue()

#     # Save as a File in Frappe
#     file_name = f"pan_update_report_{frappe.utils.now_datetime().strftime('%Y%m%d_%H%M%S')}.csv"
#     file_doc = frappe.get_doc(
#         {
#             "doctype": "File",
#             "file_name": file_name,
#             "content": csv_content.encode("utf-8"),
#             "attached_to_doctype": "Database Request",
#             "attached_to_name": "Bulk",
#             "is_private": 0,  # set 1 if you want private files
#         }
#     )
#     file_doc.save(ignore_permissions=True)

#     return {
#         "file_url": file_doc.file_url,
#         "file_name": file_doc.file_name,
#     }


@frappe.whitelist()
def generate_pan_update_report():
    """
    Generate a consolidated PAN Update CSV from all Database Request records.
    De-duplicate by (pan, account_number).
    Returns: dict with file_url and file_name.
    """
    import json
    import csv
    import io

    import frappe
    from frappe.utils import now_datetime

    db_requests = frappe.get_all(
        "Database Request",
        fields=["name", "synced_payload"],
        order_by="creation asc",
    )

    seen_keys = set()
    unique_rows = []

    for db_req in db_requests:
        payload_raw = db_req.get("synced_payload")
        if not payload_raw:
            continue

        try:
            payload = json.loads(payload_raw) if isinstance(
                payload_raw, str) else payload_raw
        except Exception:
            continue

        if not isinstance(payload, list):
            continue

        for item in payload:
            values = item.get("values") or {}

            pan = values.get("pan")
            account_number = values.get("account_number")

            if not pan or not account_number:
                continue

            key = (str(pan).strip(), str(account_number).strip())
            if key in seen_keys:
                continue

            seen_keys.add(key)

            # Store base row
            unique_rows.append({
                # keep reading 'orgkey' from payload, but label as cif_id
                "cif_id": values.get("orgkey"),
                "field_name": values.get("field_name"),
                "application_id": values.get("application_id"),
                "pan": pan,
                "account_number": account_number,
                "account_open_date": values.get("account_open_date"),
                "aadhaar_number": values.get("aadhaar_number"),
                "agent_code": values.get("agent_code"),
                "source_doc": db_req.name,
            })

    if not unique_rows:
        return None

    # Add incremental sr_no per record in final report
    rows = []
    for idx, row in enumerate(unique_rows, start=1):
        rows.append({
            "sr_no": idx,
            "cif_id": row["cif_id"],
            "field_name": row["field_name"],
            "application_id": row["application_id"],
            "pan": row["pan"],
            "account_number": row["account_number"],
            "account_open_date": row["account_open_date"],
            "aadhaar_number": row["aadhaar_number"],
            "agent_code": row["agent_code"],
            "source_doc": row["source_doc"],
        })

    headers = [
        "sr_no",
        "cif_id",
        "field_name",
        "application_id",
        "pan",
        "account_number",
        "account_open_date",
        "aadhaar_number",
        "agent_code",
        "source_doc",
    ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    csv_content = output.getvalue()

    file_name = f"pan_update_report_{frappe.utils.now_datetime().strftime('%Y%m%d_%H%M%S')}.csv"
    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": file_name,
            "content": csv_content.encode("utf-8"),
            "attached_to_doctype": "Database Request",
            "attached_to_name": "Bulk",
            "is_private": 0,
        }
    )
    file_doc.save(ignore_permissions=True)

    return {
        "file_url": file_doc.file_url,
        "file_name": file_doc.file_name,
    }
