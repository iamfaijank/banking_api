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


def fetch_share_details(cursor, cif, account_number):
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
        CROSS JOIN (
            SELECT orgkey, address_line1, address_line2
            FROM crmuser.address
            WHERE orgkey = %s
            LIMIT 1
        ) a
        WHERE g.foracid = %s
          AND h.tran_particular = 'SHARE FUND DEBITED'
          AND h.part_tran_type = 'D'
        ORDER BY h.tran_id DESC
        LIMIT 1
        """,
        (str(cif).strip(), str(account_number).strip()),
    )
    return cursor.fetchone()


def build_address(row):
    parts = [
        (row.get("address_line1") or "").strip(),
        (row.get("address_line2") or "").strip(),
    ]
    return ", ".join([p for p in parts if p])


def execute():
    records = frappe.db.get_all(
        "Share Application",
        fields=["name", "cif", "account_number"],
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
    error_count = 0

    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        progress = tqdm(
            records, desc="Updating Share Application details", unit="record")

        for row in progress:
            record_name = row.get("name")
            cif = str(row.get("cif")).strip() if row.get(
                "cif") is not None else ""
            account_number = str(row.get("account_number")).strip(
            ) if row.get("account_number") is not None else ""

            progress.set_postfix_str(f"current={record_name}")

            try:
                if not cif:
                    skipped_count += 1
                    tqdm.write(f"[SKIPPED] {record_name} -> CIF is empty")
                    continue

                if not account_number:
                    skipped_count += 1
                    tqdm.write(
                        f"[SKIPPED] {record_name} -> Account Number is empty")
                    continue

                result = fetch_share_details(cursor, cif, account_number)

                if not result:
                    skipped_count += 1
                    tqdm.write(
                        f"[NOT FOUND] {record_name} -> No Finacle record found for CIF: {cif}, Account: {account_number}"
                    )
                    continue

                frappe.db.set_value(
                    "Share Application",
                    record_name,
                    {
                        "customer_name": result.get("acct_name"),
                        "address": build_address(result),
                        "scheme_type": result.get("schm_type"),
                        "scheme_code": result.get("schm_code"),
                        "transaction_amount": result.get("tran_amt"),
                        "account_opening_date": result.get("acct_opn_date"),
                    },
                    update_modified=False,
                )

                frappe.db.commit()

                updated_count += 1
                tqdm.write(
                    f"[UPDATED] {record_name} -> CIF: {cif} | Account: {account_number} | Customer: {result.get('acct_name')}"
                )

            except Exception as e:
                frappe.db.rollback()
                error_count += 1
                tqdm.write(f"[ERROR] {record_name} -> {repr(e)}")
                tqdm.write(traceback.format_exc())
                frappe.log_error(
                    frappe.get_traceback(),
                    f"Update Share Application details failed: {record_name}",
                )

        tqdm.write(
            f"Completed. Updated: {updated_count}, Skipped: {skipped_count}, Errors: {error_count}"
        )

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
