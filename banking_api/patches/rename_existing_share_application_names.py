import frappe
from frappe.model.rename_doc import rename_doc
from tqdm import tqdm


def execute():
    if not frappe.db.exists("DocType", "Share Application"):
        return

    records = frappe.get_all(
        "Share Application",
        fields=["name", "sol_id", "cif", "cif_creation_date", "creation"],
        order_by="cif_creation_date asc, cif asc, creation asc"
    )

    sequence = 1
    renamed = 0
    skipped = 0
    failed = 0
    skipped_logs = []
    failed_logs = []

    with tqdm(
        records,
        # desc="Renaming Share Application",
        desc="Renaming ",
        unit="doc",
        ncols=120
    ) as pbar:
        for row in pbar:
            old_name = row.get("name")
            sol_id = str(row.get("sol_id") or "").strip()

            try:
                if not sol_id:
                    skipped += 1
                    skipped_logs.append(f"{old_name}: missing sol_id")
                    pbar.set_postfix(
                        sequence=sequence,
                        renamed=renamed,
                        skipped=skipped,
                        failed=failed
                    )
                    continue

                if not sol_id.isdigit():
                    skipped += 1
                    skipped_logs.append(
                        f"{old_name}: non-numeric sol_id ({sol_id})")
                    pbar.set_postfix(
                        sequence=sequence,
                        renamed=renamed,
                        skipped=skipped,
                        failed=failed
                    )
                    continue

                if len(sol_id) != 4:
                    skipped += 1
                    skipped_logs.append(
                        f"{old_name}: invalid sol_id length ({sol_id})")
                    pbar.set_postfix(
                        sequence=sequence,
                        renamed=renamed,
                        skipped=skipped,
                        failed=failed
                    )
                    continue

                new_name = f"{sol_id}01{sequence:09d}"

                if old_name == new_name:
                    sequence += 1
                    skipped += 1
                    pbar.set_postfix(
                        sequence=sequence,
                        renamed=renamed,
                        skipped=skipped,
                        failed=failed
                    )
                    continue

                if frappe.db.exists("Share Application", new_name):
                    skipped += 1
                    skipped_logs.append(
                        f"{old_name}: target name already exists ({new_name})"
                    )
                    sequence += 1
                    pbar.set_postfix(
                        sequence=sequence,
                        renamed=renamed,
                        skipped=skipped,
                        failed=failed
                    )
                    continue

                rename_doc(
                    "Share Application",
                    old_name,
                    new_name,
                    force=True,
                    merge=False
                )

                frappe.db.commit()

                renamed += 1
                sequence += 1

            except Exception as e:
                frappe.db.rollback()
                failed += 1
                failed_logs.append(f"{old_name}: {str(e)}")

            pbar.set_postfix(
                sequence=sequence,
                renamed=renamed,
                skipped=skipped,
                failed=failed
            )

    if skipped_logs:
        frappe.log_error(
            title="Share Application Rename Patch Skipped Records",
            message="\n".join(skipped_logs)
        )

    if failed_logs:
        frappe.log_error(
            title="Share Application Rename Patch Failed Records",
            message="\n".join(failed_logs)
        )

    frappe.logger().info(
        f"Share Application rename patch completed. "
        f"Renamed: {renamed}, Skipped: {skipped}, Failed: {failed}"
    )
