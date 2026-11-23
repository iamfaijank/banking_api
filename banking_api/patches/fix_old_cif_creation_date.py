import traceback

import frappe
from frappe.utils import getdate
from tqdm import tqdm


def execute_patch_fix_old_cif_creation_date():
    records = frappe.db.get_all(
        "Share Application",
        fields=["name", "docstatus", "cif_creation_date"],
        order_by="creation asc",
    )

    total_records = len(records)
    tqdm.write(f"Total Share Application records found: {total_records}")

    if not total_records:
        tqdm.write("No records found. Exiting.")
        return

    updated_count = 0
    skipped_count = 0
    error_count = 0

    cutoff_date = getdate("2014-11-23")
    new_date = "2014-11-24"

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
            if not cif_creation_date:
                skipped_count += 1
                tqdm.write(
                    f"[SKIPPED] {record_name} -> cif_creation_date is empty | docstatus={docstatus}"
                )
                continue

            current_date = getdate(cif_creation_date)

            if current_date <= cutoff_date:
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
                    f"[UPDATED] {record_name} -> cif_creation_date changed from {current_date} to {new_date} | docstatus={docstatus}"
                )
            else:
                skipped_count += 1
                tqdm.write(
                    f"[SKIPPED] {record_name} -> cif_creation_date is after 2014-11-23 | current={current_date} | docstatus={docstatus}"
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
