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


def build_address_from_address_row(row):
    parts = [
        (row.get("address_line1") or "").strip(),
        (row.get("address_line2") or "").strip(),
    ]
    return ", ".join([p for p in parts if p])


def fetch_address_details_rows(cursor, cif):
    cursor.execute(
        """
        SELECT
            a.orgkey,
            a.name,
            a.address_line1,
            a.address_line2
        FROM crmuser.address a
        WHERE a.orgkey = %s
        """,
        (str(cif).strip(),),
    )
    return cursor.fetchall()


def score_address_row(row):
    score = 0

    if has_value(row.get("name")):
        score += 1
    if has_value(row.get("address_line1")):
        score += 1
    if has_value(row.get("address_line2")):
        score += 1
    if has_value(build_address_from_address_row(row)):
        score += 1

    return score


def get_best_address_row(rows):
    if not rows:
        return None

    best_row = None
    best_score = -1

    for row in rows:
        current_score = score_address_row(row)
        if current_score > best_score:
            best_score = current_score
            best_row = row

    return best_row


def execute_patch_customer_name_and_address_from_cif():
    records = frappe.db.get_all(
        "Share Application",
        fields=[
            "name",
            "docstatus",
            "cif",
            "customer_name",
            "address",
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
            desc="Updating customer_name and address from CIF",
            unit="record",
        )

        for row in progress:
            record_name = row.get("name")
            docstatus = row.get("docstatus")
            cif = str(row.get("cif")).strip() if row.get(
                "cif") is not None else ""

            progress.set_postfix_str(f"current={record_name}")

            try:
                if has_value(row.get("customer_name")) and has_value(row.get("address")):
                    skipped_count += 1
                    tqdm.write(
                        f"[SKIPPED] {record_name} -> customer_name and address already available | docstatus={docstatus}"
                    )
                    continue

                if not cif:
                    skipped_count += 1
                    tqdm.write(
                        f"[SKIPPED] {record_name} -> CIF is empty | docstatus={docstatus}")
                    continue

                results = fetch_address_details_rows(cursor, cif)

                if not results:
                    not_found_count += 1
                    tqdm.write(
                        f"[NOT FOUND] {record_name} -> No address record found for CIF: {cif} | docstatus={docstatus}"
                    )
                    continue

                best_result = get_best_address_row(results)

                if not best_result:
                    not_found_count += 1
                    tqdm.write(
                        f"[NOT FOUND] {record_name} -> Rows found but no usable customer/address data for CIF: {cif} | docstatus={docstatus}"
                    )
                    continue

                fetched_customer_name = best_result.get("name")
                fetched_address = build_address_from_address_row(best_result)

                update_values = {}

                if not has_value(row.get("customer_name")) and has_value(fetched_customer_name):
                    update_values["customer_name"] = fetched_customer_name

                if not has_value(row.get("address")) and has_value(fetched_address):
                    update_values["address"] = fetched_address

                if not update_values:
                    skipped_count += 1
                    tqdm.write(
                        f"[SKIPPED] {record_name} -> Best CIF row found but no missing field could be filled | matched_rows={len(results)} | docstatus={docstatus}"
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
                    f"[UPDATED] {record_name} -> CIF: {cif} | matched_rows={len(results)} | fields={', '.join(update_values.keys())} | docstatus={docstatus}"
                )

            except Exception as e:
                frappe.db.rollback()
                error_count += 1
                tqdm.write(f"[ERROR] {record_name} -> {repr(e)}")
                tqdm.write(traceback.format_exc())
                frappe.log_error(
                    frappe.get_traceback(),
                    f"Patch customer_name/address from CIF failed: {record_name}",
                )

        tqdm.write(
            f"Completed. Updated: {updated_count}, Skipped: {skipped_count}, Not Found: {not_found_count}, Errors: {error_count}"
        )

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
