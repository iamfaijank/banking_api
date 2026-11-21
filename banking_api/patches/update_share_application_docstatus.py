import frappe
from tqdm import tqdm


def execute():
    names = frappe.db.get_all("Share Application", pluck="name")

    for name in tqdm(names, desc="Updating Share Application", unit="doc"):
        try:
            doc = frappe.get_doc("Share Application", name)
            original_transaction_id = doc.transaction_id or ""
            trimmed_transaction_id = original_transaction_id.strip()
            changed = False

            if trimmed_transaction_id != original_transaction_id:
                doc.db_set("transaction_id", trimmed_transaction_id,
                           update_modified=False)
                doc.transaction_id = trimmed_transaction_id
                changed = True
                print(f"[TRIMMED] {name} -> '{trimmed_transaction_id}'")

            if trimmed_transaction_id and doc.payment_status == "Success" and doc.docstatus == 0:
                doc.submit()
                changed = True
                print(f"[SUBMITTED] {name}")

            if changed:
                frappe.db.commit()
            else:
                print(f"[SKIPPED] {name}")

        except Exception:
            frappe.db.rollback()
            print(f"[ERROR] {name}")
            frappe.log_error(
                title=f"Update Share Application failed: {name}",
                message=frappe.get_traceback()
            )
