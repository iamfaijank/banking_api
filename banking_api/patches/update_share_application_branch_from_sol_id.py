import frappe
from tqdm import tqdm


def execute():
    """
    Update Share Application.branch from Sahayog Branch.branch.

    For every Share Application:
    1. Read Share Application.sol_id
    2. Find Sahayog Branch where Sahayog Branch.name == sol_id
    3. Copy Sahayog Branch.branch to Share Application.branch
    4. Commit after every individual record
    """

    share_applications = frappe.get_all(
        "Share Application",
        fields=["name", "sol_id", "branch"],
        order_by="name asc"
    )

    total_records = len(share_applications)

    updated_count = 0
    skipped_no_sol_id = 0
    skipped_branch_not_found = 0
    skipped_empty_branch = 0
    already_correct_count = 0
    failed_count = 0

    # Cache branch lookup by sol_id so repeated sol_id values
    # do not query Sahayog Branch repeatedly.
    branch_cache = {}

    for share_application in tqdm(
        share_applications,
        total=total_records,
        desc="Updating Share Application branches",
        unit="record"
    ):
        share_application_name = share_application.get("name")
        sol_id = (share_application.get("sol_id") or "").strip()

        try:
            # No sol_id means there is nothing to match.
            if not sol_id:
                skipped_no_sol_id += 1
                frappe.db.commit()
                continue

            # Fetch branch once per unique sol_id.
            if sol_id not in branch_cache:
                branch_cache[sol_id] = frappe.db.get_value(
                    "Sahayog Branch",
                    sol_id,          # Name must match Share Application.sol_id
                    "branch"
                )

            sahayog_branch_value = branch_cache[sol_id]

            # No Sahayog Branch exists where name = sol_id.
            if sahayog_branch_value is None:
                skipped_branch_not_found += 1
                frappe.db.commit()
                continue

            sahayog_branch_value = str(sahayog_branch_value).strip()

            # Matching Sahayog Branch exists, but branch field is blank.
            if not sahayog_branch_value:
                skipped_empty_branch += 1
                frappe.db.commit()
                continue

            current_branch = (share_application.get("branch") or "").strip()

            # Avoid an unnecessary DB write when the value is already correct.
            if current_branch == sahayog_branch_value:
                already_correct_count += 1
                frappe.db.commit()
                continue

            frappe.db.set_value(
                "Share Application",
                share_application_name,
                "branch",
                sahayog_branch_value,
                update_modified=False
            )

            # Required: commit after each individual record.
            frappe.db.commit()

            updated_count += 1

        except Exception:
            # Roll back only the current record's work, then continue.
            frappe.db.rollback()
            failed_count += 1

            frappe.log_error(
                frappe.get_traceback(),
                title=(
                    "Share Application Branch Update Failed: "
                    f"{share_application_name}"
                )
            )

    frappe.logger().info(
        "Share Application branch update completed. "
        f"Total={total_records}, "
        f"Updated={updated_count}, "
        f"Already Correct={already_correct_count}, "
        f"No SOL ID={skipped_no_sol_id}, "
        f"Sahayog Branch Not Found={skipped_branch_not_found}, "
        f"Empty Sahayog Branch Value={skipped_empty_branch}, "
        f"Failed={failed_count}"
    )

    print(
        "\nShare Application branch update completed:\n"
        f"  Total records: {total_records}\n"
        f"  Updated: {updated_count}\n"
        f"  Already correct: {already_correct_count}\n"
        f"  Skipped - empty sol_id: {skipped_no_sol_id}\n"
        f"  Skipped - Sahayog Branch not found: {skipped_branch_not_found}\n"
        f"  Skipped - Sahayog Branch.branch empty: {skipped_empty_branch}\n"
        f"  Failed: {failed_count}\n"
    )
