import frappe
from frappe import _


ACCOUNT_LEDGER_QUERY = """WITH params AS (
    SELECT
        DATE '2025-11-11' AS start_date,   -- <-- Start Date
        DATE '2026-11-12' AS end_date,     -- <-- End Date
        g.acid,
        g.foracid,
        g.acct_name,
        g.acct_opn_date
    FROM tbaadm.gam g
    WHERE g.foracid IN (%s)
      AND g.entity_cre_flg = 'Y'
),
all_txns AS (
    -- 1. Historical Posted Transactions (HTD)
    SELECT
        h.acid,
        h.tran_date,
        h.value_date,
        h.tran_id,
        h.ref_num,
        h.part_tran_srl_num,
        h.instrmnt_num,
        h.tran_particular,
        h.part_tran_type,
        h.tran_amt,
        h.crncy_code,
        h.tran_rmks,
        h.pstd_date,
        h.rcre_time,
        h.acct_balance
    FROM tbaadm.htd h
    JOIN params p ON h.acid = p.acid
    WHERE h.tran_date BETWEEN p.start_date AND p.end_date
      AND h.pstd_flg = 'Y'
      AND h.del_flg = 'N'
    UNION ALL
    -- 2. Today's Live Transactions (DTD)
    SELECT
        d.acid,
        d.tran_date,
        d.value_date,
        d.tran_id,
        d.ref_num,
        d.part_tran_srl_num,
        d.instrmnt_num,
        d.tran_particular,
        d.part_tran_type,
        d.tran_amt,
        d.crncy_code,
        d.tran_rmks,
        d.pstd_date,
        d.rcre_time,
        d.acct_balance
    FROM tbaadm.dtd d
    JOIN params p ON d.acid = p.acid
    WHERE d.tran_date BETWEEN p.start_date AND p.end_date
      AND d.pstd_flg = 'Y'
      AND d.del_flg = 'N'
)
SELECT
    '="' || TRIM(p.foracid) || '"'                              AS "ACCOUNT NUMBER",                                           
    p.acct_name                                                 AS "CUSTOMER NAME",
    TO_CHAR(h.tran_date,'DD-MM-YYYY')                            AS "GL DATE",
    h.tran_particular                                           AS "PARTICULARS",
  --  TRIM(h.tran_id)                                             AS "TRAN ID",
  --  TRIM(h.ref_num)                                             AS "REF NO",
    TRIM(h.instrmnt_num)                                        AS "INSTRUMENT NUMBER",
    h.tran_particular                                           AS "PARTICULARS",
    CASE WHEN h.part_tran_type = 'D' THEN h.tran_amt ELSE 0 END AS "TRANSACTION DEBIT AMOUNT",
    CASE WHEN h.part_tran_type = 'C' THEN h.tran_amt ELSE 0 END AS "TRANSACTION CREDIT AMOUNT",
--   h.crncy_code                                                AS "CRNCY CODE",
    ABS(
        h.acct_balance +
        CASE
            WHEN h.part_tran_type = 'C' THEN h.tran_amt
            WHEN h.part_tran_type = 'D' THEN -h.tran_amt
            ELSE 0
        END
    )                                                           AS "BALANCE"
--   h.tran_rmks                                                 AS "REMARKS"
FROM params p
JOIN all_txns h ON p.acid = h.acid
ORDER BY
    p.foracid ASC,
    h.tran_date ASC,
    h.rcre_time ASC,
    h.tran_id ASC,
    h.part_tran_srl_num ASC"""


def _get_finacle_migration_config_name():
	return frappe.db.get_single_value("Banking API Settings", "finacle_migration")


def _get_finacle_migration_config_doc():
	config_name = _get_finacle_migration_config_name()

	if not config_name:
		frappe.throw(_("Finacle Migration Database Configuration is not set in Banking API Settings."))

	if not frappe.db.exists("Database Configuration", config_name):
		frappe.throw(_("Database Configuration '{0}' not found.").format(config_name))

	return frappe.get_doc("Database Configuration", config_name)


@frappe.whitelist(allow_guest=False)
def check_finacle_migration_connection():
	"""Check connection for the Database Configuration set as Finacle Migration."""
	config_name = _get_finacle_migration_config_name()

	if not config_name:
		return {
			"status": "failed",
			"message": _("Finacle Migration Database Configuration is not set in Banking API Settings."),
		}

	if not frappe.db.exists("Database Configuration", config_name):
		return {
			"status": "failed",
			"message": _("Database Configuration '{0}' not found.").format(config_name),
		}

	try:
		doc = frappe.get_doc("Database Configuration", config_name)
		result = doc.test_connection() or {}
		result["config_name"] = config_name
		return result
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Finacle Passbook: Connection Check Failed")
		return {
			"status": "failed",
			"config_name": config_name,
			"message": _("Unable to test database connection."),
		}


@frappe.whitelist(allow_guest=False)
def get_account_ledger(account_id):
	"""Fetch account ledger data from Finacle Migration DB using the provided account ID."""
	account_id = (account_id or "").strip()
	if not account_id:
		frappe.throw(_("A/c. ID is required."))

	doc = _get_finacle_migration_config_doc()
	conn = None
	cursor = None

	try:
		conn = doc.get_connection(retries=1, timeout=10)
		cursor = conn.cursor()
		cursor.execute(ACCOUNT_LEDGER_QUERY, (account_id,))
		columns = [desc[0] for desc in cursor.description] if cursor.description else []
		rows = cursor.fetchall() or []
		data = [dict(zip(columns, row)) for row in rows]
		return {
			"status": "success",
			"account_id": account_id,
			"columns": columns,
			"data": data,
		}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Finacle Passbook: Get Account Ledger Failed")
		frappe.throw(_("Unable to fetch account ledger data."))
	finally:
		if cursor:
			cursor.close()
		if conn:
			conn.close()
