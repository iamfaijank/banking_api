import frappe
from tqdm import tqdm


def execute():
    cif_list = [
        400157050,
        400156904,
        400156963,
        400156870,
        400156994,
    ]

    existing_records = frappe.get_all(
        "Share Application",
        filters={"cif": ["in", cif_list]},
        fields=["name", "cif", "payment_status", "docstatus"],
    )

    records_by_cif = {}
    for row in existing_records:
        records_by_cif.setdefault(str(row.cif), []).append(row)

    not_available_cif = []

    with tqdm(total=len(cif_list), desc="Processing CIFs", ncols=100, leave=True) as pbar:
        for cif in cif_list:
            cif_key = str(cif)
            matched_rows = records_by_cif.get(cif_key, [])

            if not matched_rows:
                not_available_cif.append(cif)
                pbar.update(1)
                continue

            for row in matched_rows:
                if row.payment_status == "Success":
                    continue

                if row.payment_status == "Failed":
                    try:
                        doc = frappe.get_doc("Share Application", row.name)

                        doc.db_set("transaction_id", "Default",
                                   update_modified=False)
                        doc.db_set(
                            "error_log", "Success But Fund Not Debited", update_modified=False)
                        doc.db_set("payment_status", "Success",
                                   update_modified=False)
                        doc.db_set("insufficient_balance",
                                   0, update_modified=False)
                        doc.db_set("account_closed", 0, update_modified=False)
                        doc.db_set("account_frozen", 0, update_modified=False)
                        doc.db_set("account_not_found", 0,
                                   update_modified=False)
                        doc.db_set("success_but_fund_not_debited",
                                   1, update_modified=False)

                        if cint_safe(doc.docstatus) != 1:
                            doc.db_set("docstatus", 1, update_modified=False)

                        frappe.db.commit()

                    except Exception:
                        frappe.log_error(
                            title=f"Share Application Patch Failed for CIF {cif}",
                            message=frappe.get_traceback()
                        )
                        frappe.db.rollback()
                        continue

            pbar.update(1)

    print(
        f'cif not available in share application doctype {not_available_cif}')


def cint_safe(value):
    try:
        return int(value or 0)
    except Exception:
        return 0
