
import frappe
from frappe import _
from banking_api.banking_api.doctype.database_configuration.database_configuration import get_db_connection


@frappe.whitelist()
def update_cif_assignment(auth_id: str, cif_id: str, cif_type: str = "Retail") -> dict:
    """
    Assign a Retail or Corporate CIF to the Person ID associated with an Auth ID.

    Retail:
        Updates crmuser.accounts_mod.assignedto using orgkey.

    Corporate:
        Updates crmuser.corporate_mod.assigned_user_id using corp_key.
    """

    if not auth_id or not cif_id:
        frappe.throw(_("Both Auth ID and CIF ID are required."))

    auth_id = str(auth_id).strip()
    cif_id = str(cif_id).strip()
    cif_type = str(cif_type).strip()

    if not auth_id or not cif_id:
        frappe.throw(_("Both Auth ID and CIF ID are required."))

    if cif_type not in ("Retail", "Corporate"):
        frappe.throw(_("Invalid CIF Type. Select Retail or Corporate."))

    conn = None
    cursor = None

    try:
        conn = get_db_connection(database="Finacle Production")
        cursor = conn.cursor()

        # Step 1: Retrieve Person ID for the given Auth ID.
        # This lookup is common to both Retail and Corporate CIFs.
        fetch_query = """
            SELECT personid
            FROM crmuser.users
            WHERE loginid = %s
        """

        cursor.execute(fetch_query, (auth_id,))
        row = cursor.fetchone()

        if not row or not row[0]:
            return {
                "status": "error",
                "message": _("No Person ID found for Auth ID: {0}").format(auth_id)
            }

        person_id = str(row[0]).strip()

        # Step 2: Update the selected CIF type.
        if cif_type == "Retail":
            # Existing Retail query — unchanged.
            update_query = """
                UPDATE crmuser.accounts_mod
                SET assignedto = %s
                WHERE orgkey = %s
            """

        else:
            # Corporate CIF assignment query.
            update_query = """
                UPDATE crmuser.corporate_mod
                SET assigned_user_id = %s
                WHERE corp_key = %s
            """

        cursor.execute(update_query, (person_id, cif_id))
        rows_updated = cursor.rowcount

        conn.commit()

        if rows_updated == 0:
            return {
                "status": "error",
                "message": _(
                    "No {0} CIF record found for CIF ID: {1}. No records were updated."
                ).format(cif_type, cif_id)
            }

        return {
            "status": "success",
            "person_id": person_id,
            "cif_id": cif_id,
            "cif_type": cif_type,
            "rows_updated": rows_updated,
            "message": _(
                "{0} CIF {1} has been successfully assigned to Person ID {2}."
            ).format(cif_type, cif_id, person_id)
        }

    except Exception as exc:
        if conn:
            conn.rollback()

        frappe.log_error(
            title="CIF Assignment Error",
            message=frappe.get_traceback()
        )

        frappe.throw(
            _("Database operation failed: {0}").format(str(exc))
        )

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()
