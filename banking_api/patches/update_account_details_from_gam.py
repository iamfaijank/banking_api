import traceback

import frappe
import psycopg2
import psycopg2.extras
from frappe import _
from tqdm import tqdm


def db_connection():
    try:
        creds = frappe.get_single("Finacle DB Credentials")
        port = int(creds.db_port) if creds.db_port else 5432

        conn = psycopg2.connect(
            host=creds.db_host,
            port=port,
            user=creds.db_user,
            password=creds.get_password("db_password"),
            database=creds.db_name,
        )
        return conn
    except Exception as e:
        frappe.log_error(frappe.get_traceback(),
                         "PostgreSQL Connection Failed")
        raise Exception(_("Database Connection Error: {0}").format(str(e)))


def has_value(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def fetch_gam_details_rows(cursor, account_number):
    cursor.execute(
        """
        SELECT
            g.foracid,
            g.acct_opn_date,
            g.schm_code,
            g.schm_type
        FROM tbaadm.gam g
        WHERE g.foracid = %s
        """,
        (str(account_number).strip(),),
    )
    return cursor.fetchall()


def score_gam_row(row):
    score = 0

    if has_value(row.get("acct_opn_date")):
        score += 1
    if has_value(row.get("schm_code")):
        score += 1
    if has_value(row.get("schm_type")):
        score += 1

    return score


def get_best_gam_row(rows):
    if not rows:
        return None

    best_row = None
    best_score = -1

    for row in rows:
        current_score = score_gam_row(row)
        if current_score > best_score:
            best_score = current_score
            best_row = row

    return best_row


def execute_patch_account_details_from_gam():
    records = frappe.db.get_all(
        "Share Application",
        fields=[
            "name",
            "docstatus",
            "account_number",
            "account_opening_date",
            "scheme_code",
            "scheme_type",
        ],
        order_by="creation asc",
    )

    total_records = len(records)
    tqdm.write(f"Total Share Application records found: {total_records}")

    if not total_records:
        tqdm.write("No records found. Exiting.")
        return

    conn = None
    cursor = None

    updated_count = 0
    skipped_count = 0
    not_found_count = 0
    error_count = 0

    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        progress = tqdm(
            records,
            desc="Updating account details from GAM",
            unit="record",
        )

        for row in progress:
            record_name = row.get("name")
            docstatus = row.get("docstatus")
            account_number = (
                str(row.get("account_number")).strip()
                if row.get("account_number") is not None
                else ""
            )

            progress.set_postfix_str(f"current={record_name}")

            try:
                all_present = all([
                    has_value(row.get("account_opening_date")),
                    has_value(row.get("scheme_code")),
                    has_value(row.get("scheme_type")),
                ])

                if all_present:
                    skipped_count += 1
                    tqdm.write(
                        f"[SKIPPED] {record_name} -> account_opening_date, scheme_code and scheme_type already available | docstatus={docstatus}"
                    )
                    continue

                if not account_number:
                    skipped_count += 1
                    tqdm.write(
                        f"[SKIPPED] {record_name} -> Account Number is empty | docstatus={docstatus}"
                    )
                    continue

                results = fetch_gam_details_rows(cursor, account_number)

                if not results:
                    not_found_count += 1
                    tqdm.write(
                        f"[NOT FOUND] {record_name} -> No GAM record found for Account Number: {account_number} | docstatus={docstatus}"
                    )
                    continue

                best_result = get_best_gam_row(results)

                if not best_result:
                    not_found_count += 1
                    tqdm.write(
                        f"[NOT FOUND] {record_name} -> Rows found but no usable GAM data for Account Number: {account_number} | docstatus={docstatus}"
                    )
                    continue

                update_values = {}

                if (
                    not has_value(row.get("account_opening_date"))
                    and has_value(best_result.get("acct_opn_date"))
                ):
                    update_values["account_opening_date"] = best_result.get(
                        "acct_opn_date")

                if (
                    not has_value(row.get("scheme_code"))
                    and has_value(best_result.get("schm_code"))
                ):
                    update_values["scheme_code"] = best_result.get("schm_code")

                if (
                    not has_value(row.get("scheme_type"))
                    and has_value(best_result.get("schm_type"))
                ):
                    update_values["scheme_type"] = best_result.get("schm_type")

                if not update_values:
                    skipped_count += 1
                    tqdm.write(
                        f"[SKIPPED] {record_name} -> GAM row found but no missing field could be filled | matched_rows={len(results)} | docstatus={docstatus}"
                    )
                    continue

                frappe.db.set_value(
                    "Share Application",
                    record_name,
                    update_values,
                    update_modified=False,
                )
                frappe.db.commit()

                updated_count += 1
                tqdm.write(
                    f"[UPDATED] {record_name} -> Account Number: {account_number} | matched_rows={len(results)} | fields={', '.join(update_values.keys())} | docstatus={docstatus}"
                )

            except Exception as e:
                frappe.db.rollback()
                error_count += 1
                tqdm.write(f"[ERROR] {record_name} -> {repr(e)}")
                tqdm.write(traceback.format_exc())
                frappe.log_error(
                    frappe.get_traceback(),
                    f"Patch account details from GAM failed: {record_name}",
                )

        tqdm.write(
            f"Completed. Updated: {updated_count}, Skipped: {skipped_count}, Not Found: {not_found_count}, Errors: {error_count}"
        )

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
