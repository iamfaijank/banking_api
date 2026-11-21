import traceback

import frappe
import psycopg2
import psycopg2.extras
from frappe import _
from tqdm import tqdm


def db_connection():
    """Connect to external PostgreSQL (Finacle) using Finacle DB Credentials."""
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


def get_relationship_opening_date(cursor, cif):
    cursor.execute(
        """
        SELECT orgkey, relationshipopeningdate
        FROM crmuser.accounts
        WHERE orgkey = %s
          AND entity_cre_flag = 'Y'
        ORDER BY relationshipopeningdate DESC
        LIMIT 1
        """,
        (cif,),
    )
    return cursor.fetchone()


def execute():
    records = frappe.db.get_all(
        "Share Application",
        fields=["name", "cif", "cif_creation_date"],
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
            records, desc="Updating CIF Creation Date", unit="record")

        for row in progress:
            record_name = row.get("name")
            raw_cif = row.get("cif")
            cif = str(raw_cif).strip() if raw_cif is not None else ""
            cif_creation_date = row.get("cif_creation_date")

            progress.set_postfix_str(f"current={record_name}")

            try:
                if cif_creation_date:
                    skipped_count += 1
                    tqdm.write(
                        f"[SKIPPED] {record_name} -> cif_creation_date already exists: {cif_creation_date}"
                    )
                    continue

                if not cif:
                    skipped_count += 1
                    tqdm.write(f"[SKIPPED] {record_name} -> CIF is empty")
                    continue

                result = get_relationship_opening_date(cursor, cif)

                if not result:
                    skipped_count += 1
                    tqdm.write(
                        f"[NOT FOUND] {record_name} -> No CRM record found for CIF: {cif}")
                    continue

                relationshipopeningdate = result.get("relationshipopeningdate")

                if not relationshipopeningdate:
                    skipped_count += 1
                    tqdm.write(
                        f"[SKIPPED] {record_name} -> relationshipopeningdate is empty for CIF: {cif}"
                    )
                    continue

                frappe.db.set_value(
                    "Share Application",
                    record_name,
                    "cif_creation_date",
                    relationshipopeningdate,
                    update_modified=False,
                )
                frappe.db.commit()

                updated_count += 1
                tqdm.write(
                    f"[UPDATED] {record_name} -> CIF: {cif} | cif_creation_date: {relationshipopeningdate}"
                )

            except Exception as e:
                frappe.db.rollback()
                error_count += 1
                tqdm.write(f"[ERROR] {record_name} -> {repr(e)}")
                tqdm.write(traceback.format_exc())
                frappe.log_error(
                    frappe.get_traceback(),
                    f"Update CIF Creation Date failed: {record_name}",
                )

        tqdm.write(
            f"Completed. Updated: {updated_count}, Skipped: {skipped_count}, Errors: {error_count}"
        )

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
