import traceback

import frappe
from tqdm import tqdm


def execute_patch_fix_old_cif_creation_date():
    cutoff_date = "2014-11-24"
    new_date = "2014-11-24"

    records = frappe.db.get_all(
        "Share Application",
        filters={
            "cif_creation_date": ["<", cutoff_date]
        },
        fields=["name", "docstatus", "cif_creation_date"],
        order_by="creation asc",
    )

    total_records = len(records)
    tqdm.write(f"Total Share Application records found: {total_records}")

    if not total_records:
        tqdm.write("No matching records found. Exiting.")
        return

    updated_count = 0
    skipped_count = 0
    error_count = 0

    progress = tqdm(
        records,
        desc="Fixing old cif_creation_date values",
        unit="record",
    )

    for row in progress:
        record_name = row.get("name")
        docstatus = row.get("docstatus")
        cif_creation_date = row.get("cif_creation_date")

        progress.set_postfix_str(f"current={record_name}")

        try:
            frappe.db.set_value(
                "Share Application",
                record_name,
                "cif_creation_date",
                new_date,
                update_modified=False,
            )
            frappe.db.commit()

            updated_count += 1
            tqdm.write(
                f"[UPDATED] {record_name} -> cif_creation_date changed from {cif_creation_date} to {new_date} | docstatus={docstatus}"
            )

        except Exception as e:
            frappe.db.rollback()
            error_count += 1
            tqdm.write(f"[ERROR] {record_name} -> {repr(e)}")
            tqdm.write(traceback.format_exc())
            frappe.log_error(
                frappe.get_traceback(),
                f"Patch cif_creation_date failed: {record_name}",
            )

    tqdm.write(
        f"Completed. Updated: {updated_count}, Skipped: {skipped_count}, Errors: {error_count}"
    )
