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


def build_address(row):
    parts = [
        (row.get("address_line1") or "").strip(),
        (row.get("address_line2") or "").strip(),
    ]
    return ", ".join([p for p in parts if p])


def fetch_share_details_rows(cursor, cif, account_number):
    cursor.execute(
        """
        SELECT
            g.acct_name,
            g.foracid,
            g.acct_opn_date,
            g.schm_code,
            g.schm_type,
            h.tran_particular,
            h.tran_amt,
            h.tran_id,
            a.orgkey,
            a.address_line1,
            a.address_line2
        FROM tbaadm.gam g
        JOIN tbaadm.htd h
            ON g.acid = h.acid
        LEFT JOIN crmuser.address a
            ON a.orgkey = %s
        WHERE g.foracid = %s
          AND h.tran_particular = 'SHARE FUND DEBITED'
          AND h.part_tran_type = 'D'
        ORDER BY h.tran_id DESC
        """,
        (str(cif).strip(), str(account_number).strip()),
    )
    return cursor.fetchall()


def score_share_row(row):
    score = 0

    if has_value(row.get("acct_name")):
        score += 1
    if has_value(build_address(row)):
        score += 1
    if has_value(row.get("schm_type")):
        score += 1
    if has_value(row.get("schm_code")):
        score += 1
    if has_value(row.get("tran_amt")):
        score += 1
    if has_value(row.get("acct_opn_date")):
        score += 1

    return score


def get_best_share_details(rows):
    if not rows:
        return None

    best_row = None
    best_score = -1

    for row in rows:
        current_score = score_share_row(row)
        if current_score > best_score:
            best_score = current_score
            best_row = row

    return best_row


def execute_fill_missing_share_details():
    records = frappe.db.get_all(
        "Share Application",
        fields=[
            "name",
            "docstatus",
            "cif",
            "account_number",
            "customer_name",
            "address",
            "scheme_type",
            "scheme_code",
            "transaction_amount",
            "account_opening_date",
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
            records, desc="Filling missing Share Application details", unit="record")

        for row in progress:
            record_name = row.get("name")
            docstatus = row.get("docstatus")
            cif = str(row.get("cif")).strip() if row.get(
                "cif") is not None else ""
            account_number = str(row.get("account_number")).strip(
            ) if row.get("account_number") is not None else ""

            progress.set_postfix_str(f"current={record_name}")

            try:
                all_present = all([
                    has_value(row.get("customer_name")),
                    has_value(row.get("address")),
                    has_value(row.get("scheme_type")),
                    has_value(row.get("scheme_code")),
                    has_value(row.get("transaction_amount")),
                ])

                if all_present:
                    skipped_count += 1
                    tqdm.write(
                        f"[SKIPPED] {record_name} -> All required fields already available | docstatus={docstatus}"
                    )
                    continue

                if not cif:
                    skipped_count += 1
                    tqdm.write(
                        f"[SKIPPED] {record_name} -> CIF is empty | docstatus={docstatus}")
                    continue

                if not account_number:
                    skipped_count += 1
                    tqdm.write(
                        f"[SKIPPED] {record_name} -> Account Number is empty | docstatus={docstatus}")
                    continue

                results = fetch_share_details_rows(cursor, cif, account_number)

                if not results:
                    not_found_count += 1
                    tqdm.write(
                        f"[NOT FOUND] {record_name} -> No Finacle record found for CIF: {cif}, Account: {account_number} | docstatus={docstatus}"
                    )
                    continue

                best_result = get_best_share_details(results)

                if not best_result:
                    not_found_count += 1
                    tqdm.write(
                        f"[NOT FOUND] {record_name} -> Matching rows found but no usable data | docstatus={docstatus}"
                    )
                    continue

                fetched_values = {
                    "customer_name": best_result.get("acct_name"),
                    "address": build_address(best_result),
                    "scheme_type": best_result.get("schm_type"),
                    "scheme_code": best_result.get("schm_code"),
                    "transaction_amount": best_result.get("tran_amt"),
                    "account_opening_date": best_result.get("acct_opn_date"),
                }

                update_values = {}

                for fieldname in [
                    "customer_name",
                    "address",
                    "scheme_type",
                    "scheme_code",
                    "transaction_amount",
                    "account_opening_date",
                ]:
                    current_value = row.get(fieldname)
                    new_value = fetched_values.get(fieldname)

                    if not has_value(current_value) and has_value(new_value):
                        update_values[fieldname] = new_value

                if not update_values:
                    skipped_count += 1
                    tqdm.write(
                        f"[SKIPPED] {record_name} -> Best SQL row found but no missing field could be filled | docstatus={docstatus}"
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
                    f"[UPDATED] {record_name} -> docstatus={docstatus} | matched_rows={len(results)} | fields={', '.join(update_values.keys())}"
                )

            except Exception as e:
                frappe.db.rollback()
                error_count += 1
                tqdm.write(f"[ERROR] {record_name} -> {repr(e)}")
                tqdm.write(traceback.format_exc())
                frappe.log_error(
                    frappe.get_traceback(),
                    f"Fill missing Share Application details failed: {record_name}",
                )

        tqdm.write(
            f"Completed. Updated: {updated_count}, Skipped: {skipped_count}, Not Found: {not_found_count}, Errors: {error_count}"
        )

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
