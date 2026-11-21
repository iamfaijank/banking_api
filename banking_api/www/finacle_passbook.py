import frappe
from frappe import _
from frappe.utils.pdf import get_pdf


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
    h.tran_date DESC,
    h.rcre_time DESC,
    h.tran_id DESC,
    h.part_tran_srl_num DESC"""


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


ACCOUNT_SUMMARY_QUERY = """
SELECT
	g.foracid,
	g.acct_name,
	g.crncy_code,
	g.acct_opn_date,
	g.gl_sub_head_code,
	g.acct_cls_flg,
	g.acct_cls_date,
	g.active_status,
	g.frez_code,
	g.last_frez_date,
	g.last_unfrez_date,
	g.schm_type,
	g.schm_code,
	g.acct_ownership,
	g.clr_bal_amt,
	g.un_clr_bal_amt,
	g.drwng_power,
	g.lien_amt,
	g.system_reserved_amt,
	g.future_bal_amt,
	g.sol_id
FROM tbaadm.gam g
WHERE g.foracid = %s
  AND g.entity_cre_flg = 'Y'
LIMIT 1
"""

OPENING_BALANCE_QUERY = """
WITH params AS (
	SELECT
		DATE '2025-11-11' AS start_date,
		g.acid
	FROM tbaadm.gam g
	WHERE g.foracid = %s
	  AND g.entity_cre_flg = 'Y'
),
all_txns AS (
	SELECT
		h.acid,
		h.tran_date,
		h.tran_id,
		h.part_tran_srl_num,
		h.part_tran_type,
		h.tran_amt,
		h.rcre_time,
		h.acct_balance
	FROM tbaadm.htd h
	JOIN params p ON h.acid = p.acid
	WHERE h.tran_date < p.start_date
	  AND h.pstd_flg = 'Y'
	  AND h.del_flg = 'N'
	UNION ALL
	SELECT
		d.acid,
		d.tran_date,
		d.tran_id,
		d.part_tran_srl_num,
		d.part_tran_type,
		d.tran_amt,
		d.rcre_time,
		d.acct_balance
	FROM tbaadm.dtd d
	JOIN params p ON d.acid = p.acid
	WHERE d.tran_date < p.start_date
	  AND d.pstd_flg = 'Y'
	  AND d.del_flg = 'N'
)
SELECT
	ABS(
		h.acct_balance +
		CASE
			WHEN h.part_tran_type = 'C' THEN h.tran_amt
			WHEN h.part_tran_type = 'D' THEN -h.tran_amt
			ELSE 0
		END
	) AS opening_balance
FROM all_txns h
ORDER BY
	h.tran_date DESC,
	h.rcre_time DESC,
	h.tran_id DESC,
	h.part_tran_srl_num DESC
LIMIT 1
"""


def _format_date_display(val):
	if not val:
		return ""
	try:
		if hasattr(val, "strftime"):
			return val.strftime("%d-%m-%Y")
	except Exception:
		pass
	s = str(val).strip()
	if len(s) >= 10 and s[4] == "-" and s[7] == "-":
		# YYYY-MM-DD...
		return f"{s[8:10]}-{s[5:7]}-{s[0:4]}"
	if len(s) == 10 and s[2] == "-" and s[5] == "-":
		return s
	return s


def _format_money(val, currency="INR", cr_dr=None):
	if val is None or val == "":
		return ""
	try:
		num = float(val)
	except Exception:
		return str(val)
	amt = "{:,.2f}".format(abs(num))
	prefix = f"{currency} " if currency else ""
	if cr_dr == "CR":
		return f"{prefix}{amt} CR."
	if cr_dr == "DR":
		return f"{prefix}{amt} DR."
	if num < 0:
		return f"{prefix}{amt} DR."
	return f"{prefix}{amt} CR."


def _derive_account_status(row):
	cls_flg = (row.get("acct_cls_flg") or "").strip()
	active_status = (row.get("active_status") or "").strip()
	frez_code = (row.get("frez_code") or "").strip()
	if cls_flg == "Y":
		return "CLOSED"
	if frez_code and frez_code.upper() not in ("N", "NONE"):
		return "FROZEN"
	if active_status == "I":
		return "INACTIVE"
	return "ACTIVE"


def _derive_account_status_date(row, status):
	if status == "CLOSED":
		return row.get("acct_cls_date")
	if status == "FROZEN":
		return row.get("last_frez_date") or row.get("acct_opn_date")
	return row.get("last_unfrez_date") or row.get("acct_opn_date")


def _derive_account_type(row):
	ownership = (row.get("acct_ownership") or "").strip().upper()
	schm_type = (row.get("schm_type") or "").strip()
	schm_code = (row.get("schm_code") or "").strip()
	if ownership == "C":
		return "CUSTOMER ACCOUNT"
	if ownership == "O":
		return "OFFICE ACCOUNT"
	parts = [p for p in [schm_type, schm_code] if p]
	return " ".join(parts) if parts else ""


def _fetch_account_summary(cursor, account_id, ledger_data):
	summary = {
		"ac_id": _clean_acct(account_id),
		"ac_status": "",
		"ac_open_date": "",
		"gl_subhead": "",
		"opening_bal": "",
		"closing_bal": "",
		"funds_in_clg": "",
		"ac_status_date": "",
		"ac_close_date": "",
		"ac_type": "",
		"available_amt": "",
		"effective_available_amt": "",
		"float_bal": "",
	}

	cursor.execute(ACCOUNT_SUMMARY_QUERY, (account_id,))
	row = cursor.fetchone()
	if not row:
		# fallback minimal summary from ledger data
		if ledger_data:
			first = ledger_data[0]
			summary["ac_id"] = _clean_acct(first.get("ACCOUNT NUMBER") or account_id)
			latest = ledger_data[0]
			summary["closing_bal"] = _format_money(latest.get("BALANCE"), "INR", "CR")
		return summary

	cols = [d[0] for d in cursor.description]
	g = dict(zip(cols, row))
	ccy = (g.get("crncy_code") or "INR").strip() or "INR"

	status = _derive_account_status(g)
	status_date = _derive_account_status_date(g, status)
	ac_id = _clean_acct(g.get("foracid") or account_id)
	acct_name = (g.get("acct_name") or "").strip()
	if acct_name:
		ac_id = f"{ac_id} {ccy} {acct_name}"

	summary["ac_id"] = ac_id.strip()
	summary["ac_status"] = status
	summary["ac_open_date"] = _format_date_display(g.get("acct_opn_date"))
	summary["gl_subhead"] = (g.get("gl_sub_head_code") or "").strip()
	summary["ac_status_date"] = _format_date_display(status_date)
	summary["ac_close_date"] = _format_date_display(g.get("acct_cls_date"))
	summary["ac_type"] = _derive_account_type(g)

	funds_in_clg = float(g.get("un_clr_bal_amt") or 0)
	summary["funds_in_clg"] = _format_money(funds_in_clg, ccy, "CR")
	summary["float_bal"] = _format_money(funds_in_clg, ccy, "CR")

	clr_bal = float(g.get("clr_bal_amt") or 0)
	lien_amt = float(g.get("lien_amt") or 0)
	sys_reserved = float(g.get("system_reserved_amt") or 0)
	available = clr_bal - lien_amt - sys_reserved
	drwng_power = g.get("drwng_power")
	eff_available = available
	if drwng_power is not None:
		try:
			dp = float(drwng_power)
			# use drawing power as effective available when it differs meaningfully
			if dp != 0:
				eff_available = dp
		except Exception:
			pass
	summary["available_amt"] = _format_money(available, ccy, "CR" if available >= 0 else "DR")
	summary["effective_available_amt"] = _format_money(eff_available, ccy, "CR" if eff_available >= 0 else "DR")

	# Opening balance: balance before statement start date, else 0
	opening = 0.0
	try:
		cursor.execute(OPENING_BALANCE_QUERY, (account_id,))
		ob = cursor.fetchone()
		if ob and ob[0] is not None:
			opening = float(ob[0])
	except Exception:
		opening = 0.0
	summary["opening_bal"] = _format_money(opening, ccy, "CR")

	# Closing balance: latest txn balance in fetched period, else current clear balance
	if ledger_data:
		latest = ledger_data[0]
		summary["closing_bal"] = _format_money(latest.get("BALANCE"), ccy, "CR")
	else:
		summary["closing_bal"] = _format_money(clr_bal, ccy, "CR" if clr_bal >= 0 else "DR")

	return summary


def _fetch_account_ledger_data(account_id):
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

		account_summary = {}
		try:
			account_summary = _fetch_account_summary(cursor, account_id, data)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Finacle Passbook: Get Account Summary Failed")
			account_summary = {}

		return {
			"status": "success",
			"account_id": account_id,
			"columns": columns,
			"data": data,
			"account_summary": account_summary,
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Finacle Passbook: Get Account Ledger Failed")
		message = _("Unable to fetch account ledger data.")
		err = str(e).strip()
		if err:
			message = _("{0} ({1})").format(message, err.splitlines()[0])
		frappe.throw(message)
	finally:
		if cursor:
			cursor.close()
		if conn:
			conn.close()


@frappe.whitelist(allow_guest=False)
def get_account_ledger(account_id):
	"""Fetch account ledger data from Finacle Migration DB using the provided account ID."""
	return _fetch_account_ledger_data(account_id)


def _fmt_amount(val):
	if val is None or val == "":
		return ""
	try:
		num = float(val)
		if num == 0:
			return "0.00"
		return "{:,.2f}".format(num)
	except Exception:
		return str(val)


def _fmt_balance(val):
	if val is None or val == "":
		return ""
	try:
		num = float(val)
		if abs(num) < 0.005:
			return "0.00"
		return "{:,.2f}Cr".format(abs(num))
	except Exception:
		return str(val)


def _fmt_date_ddmmyy(val):
	if not val:
		return ""
	s = str(val).strip()
	# Expected from query: DD-MM-YYYY
	if len(s) == 10 and s[2] == "-" and s[5] == "-":
		return s[:6] + s[8:]
	return s


def _clean_acct(val):
	if val is None:
		return ""
	return str(val).replace('="', "").replace('"', "").strip()


def _build_ledger_pdf_html(result):
	rows = result.get("data") or []
	account_id = _clean_acct((rows[0].get("ACCOUNT NUMBER") if rows else "") or result.get("account_id") or "")

	# Build transaction rows similar to HPBP extracted format
	body_rows = []
	for row in rows:
		date = _fmt_date_ddmmyy(row.get("GL DATE"))
		particular = (row.get("PARTICULARS") or "").replace("\n", " ").strip()
		cheque = (row.get("INSTRUMENT NUMBER") or "").strip()
		debit_amt = row.get("TRANSACTION DEBIT AMOUNT")
		credit_amt = row.get("TRANSACTION CREDIT AMOUNT")
		balance = row.get("BALANCE")

		try:
			dr = float(debit_amt or 0)
		except Exception:
			dr = 0.0
		try:
			cr = float(credit_amt or 0)
		except Exception:
			cr = 0.0

		debit = _fmt_amount(debit_amt) if dr else ""
		credit = _fmt_amount(credit_amt) if cr else ""
		# In extracted PDF, credit amounts often shown like 5,000.00 (and Cr in balance), keep simple/close
		bal = _fmt_balance(balance)

		body_rows.append(
			"<tr>"
			f"<td class='date'>{frappe.utils.escape_html(date)}</td>"
			f"<td class='part'>{frappe.utils.escape_html(particular)}</td>"
			f"<td class='chq'>{frappe.utils.escape_html(cheque)}</td>"
			f"<td class='amt'>{frappe.utils.escape_html(debit)}</td>"
			f"<td class='amt'>{frappe.utils.escape_html(credit)}</td>"
			f"<td class='amt'>{frappe.utils.escape_html(bal)}</td>"
			"</tr>"
		)

	rows_html = "".join(body_rows)

	html = f"""<!DOCTYPE html>
<html>
<head>
	<meta charset="utf-8">
	<style>
		@page {{
			size: A4;
			margin: 12mm 10mm;
		}}
		body {{
			font-family: Arial, Helvetica, sans-serif;
			font-size: 11px;
			color: #000;
			margin: 0;
		}}
		table {{
			width: 100%;
			border-collapse: collapse;
		}}
		th, td {{
			padding: 2px 4px;
			vertical-align: top;
		}}
		th {{
			text-align: left;
			font-weight: bold;
			border-bottom: 1px solid #000;
		}}
		td.date {{ width: 12%; white-space: nowrap; }}
		td.part {{ width: 40%; }}
		td.chq  {{ width: 14%; }}
		td.amt  {{ width: 11%; text-align: right; white-space: nowrap; }}
		th.amt  {{ text-align: right; }}
	</style>
</head>
<body>
	<table>
		<thead>
			<tr>
				<th class="date">Date</th>
				<th class="part">Particular</th>
				<th class="chq">Cheque No.</th>
				<th class="amt">Debit</th>
				<th class="amt">Credit</th>
				<th class="amt">Balance</th>
			</tr>
		</thead>
		<tbody>
			{rows_html}
		</tbody>
	</table>
</body>
</html>"""
	return html


CLOSURE_VOUCHER_QUERY = """
SELECT 
    h.tran_id           AS "TRAN ID",
    g.foracid           AS "ACCOUNT NUMBER",
    g.acct_name         AS "ACCOUNT NAME",
    h.part_tran_type    AS "DR_CR",
    h.tran_amt          AS "AMOUNT",
    h.tran_particular   AS "PARTICULARS"
FROM tbaadm.gam g_rd
-- RD ka Closing Debit Leg (Using 'Closure proceeds')
JOIN tbaadm.htd h_rd 
    ON g_rd.acid = h_rd.acid 
   AND h_rd.part_tran_type = 'D'
   AND h_rd.tran_particular LIKE '%Closure proceeds%'
-- Usi voucher ke baaki saare Legs
JOIN tbaadm.htd h 
    ON h_rd.tran_id = h.tran_id 
   AND h_rd.tran_date = h.tran_date
JOIN tbaadm.gam g 
    ON h.acid = g.acid
WHERE g_rd.foracid = %s   -- <-- Apna Closed RD Account Number dalein
ORDER BY h.part_tran_srl_num
"""


def _safe_fetchone_dict(cursor, query, params):
	try:
		cursor.execute(query, params)
		row = cursor.fetchone()
		if not row:
			return {}
		cols = [d[0] for d in cursor.description]
		return dict(zip(cols, row))
	except Exception:
		return {}


def _safe_fetchall_dicts(cursor, query, params):
	try:
		cursor.execute(query, params)
		rows = cursor.fetchall() or []
		cols = [d[0] for d in cursor.description]
		return [dict(zip(cols, r)) for r in rows]
	except Exception:
		return []


@frappe.whitelist(allow_guest=False)
def get_statement_download_data(account_id):
	"""Return enriched account details for statement PDF front page (download only)."""
	account_id = (account_id or "").strip()
	if not account_id:
		frappe.throw(_("A/c. ID is required."))

	base = _fetch_account_ledger_data(account_id)
	doc = _get_finacle_migration_config_doc()
	conn = None
	cursor = None
	front_page = {}

	try:
		conn = doc.get_connection(retries=1, timeout=10)
		cursor = conn.cursor()

		gam = _safe_fetchone_dict(cursor, """
			SELECT
				g.foracid, g.acct_name, g.cust_id, g.cif_id, g.sol_id,
				g.acct_opn_date, g.acct_cls_date, g.acct_cls_flg, g.frez_code,
				g.mode_of_oper_code, g.nom_available_flg, g.schm_code, g.schm_type,
				g.acct_ownership, g.gl_sub_head_code, g.crncy_code, g.schm_sub_type
			FROM tbaadm.gam g
			WHERE g.foracid = %s AND g.entity_cre_flg = 'Y'
			LIMIT 1
		""", (account_id,))

		sol = {}
		sol_id = (gam.get("sol_id") or "").strip() if gam else ""
		if sol_id:
			sol = _safe_fetchone_dict(cursor, """
				SELECT sol_id, sol_desc, br_code, addr_1, addr_2, addr_3, city_code, state_code, pin_code, cntry_code
				FROM tbaadm.sol
				WHERE sol_id = %s
				LIMIT 1
			""", (sol_id,))

		nominee = {}
		if gam.get("acid") is None:
			# get acid for nominee lookup
			acid_row = _safe_fetchone_dict(cursor, "SELECT acid FROM tbaadm.gam WHERE foracid=%s AND entity_cre_flg='Y' LIMIT 1", (account_id,))
			gam_acid = acid_row.get("acid")
		else:
			gam_acid = gam.get("acid")
		if gam_acid:
			nominee = _safe_fetchone_dict(cursor, """
				SELECT nom_name, nom_reg_num, nom_reltn_code
				FROM tbaadm.ant
				WHERE acid = %s AND del_flg = 'N'
				ORDER BY nom_srl_num
				LIMIT 1
			""", (gam_acid,))

		cif_id = (gam.get("cif_id") or gam.get("cust_id") or "").strip()
		address = {}
		mobile = ""
		if cif_id:
			address = _safe_fetchone_dict(cursor, """
				SELECT address_line1, address_line2, address_line3, city, state, zip, country
				FROM crmuser.address
				WHERE (orgkey = %s OR orgid = %s OR personid = %s)
				ORDER BY preferredaddress DESC NULLS LAST, addressid DESC
				LIMIT 1
			""", (cif_id, cif_id, cif_id))
			phone = _safe_fetchone_dict(cursor, """
				SELECT phoneno1, phoneno1localcode, phoneno1citycode, phoneno1countrycode,
				       phoneno2, phoneno2localcode, phoneno2citycode, phoneno2countrycode
				FROM crmuser.address
				WHERE (orgkey = %s OR orgid = %s OR personid = %s)
				ORDER BY preferredaddress DESC NULLS LAST, addressid DESC
				LIMIT 1
			""", (cif_id, cif_id, cif_id))
			for k in ["phoneno1localcode", "phoneno1", "phoneno2localcode", "phoneno2"]:
				v = (phone.get(k) or "").strip()
				if v and v not in ("0",):
					mobile = v
					break
			if not mobile:
				acct_phone = _safe_fetchone_dict(cursor, """
					SELECT phone_cell, smsbankingmobilenumber, phone_home, preferredphone
					FROM crmuser.accounts
					WHERE orgkey = %s OR otuoldcifid = %s
					LIMIT 1
				""", (cif_id, cif_id))
				for k in ["smsbankingmobilenumber", "phone_cell", "preferredphone", "phone_home"]:
					v = (acct_phone.get(k) or "").strip()
					if v and v not in ("0",):
						mobile = v
						break

		closure_voucher = _safe_fetchall_dicts(cursor, CLOSURE_VOUCHER_QUERY, (account_id,))

		# derive values
		def fmt_dt(v):
			return _format_date_display(v)

		nom_available = (gam.get("nom_available_flg") or "").strip().upper() == "Y" or bool(nominee.get("nom_name"))
		mop = (gam.get("mode_of_oper_code") or "").strip()
		joint = "Y" if (gam.get("acct_ownership") or "").strip().upper() == "J" else ("Y" if mop and mop.upper() not in ("SELF", "1") else "N")

		sol_addr_parts = [p.strip() for p in [sol.get("addr_1"), sol.get("addr_2"), sol.get("addr_3")] if (p or "").strip()]
		sol_city = " ".join([p.strip() for p in [sol.get("city_code"), sol.get("state_code"), sol.get("pin_code")] if (p or "").strip()])
		branch_addr_lines = list(sol_addr_parts)
		if sol_city and sol_city not in branch_addr_lines:
			branch_addr_lines.append(sol_city)
		while len(branch_addr_lines) < 3:
			branch_addr_lines.append("")

		cust_addr_lines = [p.strip() for p in [address.get("address_line1"), address.get("address_line2"), address.get("address_line3")] if (p or "").strip()]
		cust_city = " ".join([p.strip() for p in [address.get("city"), address.get("state"), address.get("zip")] if (p or "").strip()])
		if cust_city and cust_city not in cust_addr_lines:
			cust_addr_lines.append(cust_city)
		while len(cust_addr_lines) < 3:
			cust_addr_lines.append("")

		front_page = {
			"bank_name": "SAHAYOG MULTISTATE CREDIT CO.OPERATIVE SOCIETY LTD",
			"branch_name": (sol.get("sol_desc") or "").strip(),
			"branch_code": (sol.get("br_code") or sol.get("sol_id") or "").strip(),
			"branch_address_1": branch_addr_lines[0],
			"branch_address_2": branch_addr_lines[1],
			"branch_address_3": branch_addr_lines[2],
			"phone_no": "",
			"nature_of_account": (gam.get("schm_type") or gam.get("schm_code") or base.get("account_summary", {}).get("ac_type") or "").strip(),
			"customer_name": (gam.get("acct_name") or "").strip(),
			"account_number": _clean_acct(gam.get("foracid") or account_id),
			"customer_id": (gam.get("cust_id") or gam.get("cif_id") or "").strip(),
			"nominee_reg": "Y" if nom_available else "N",
			"nominee_name": (nominee.get("nom_name") or "").strip(),
			"joint_account": joint,
			"customer_address_1": cust_addr_lines[0],
			"customer_address_2": cust_addr_lines[1],
			"customer_address_3": cust_addr_lines[2],
			"ac_open_date": fmt_dt(gam.get("acct_opn_date")),
			"mobile_no": mobile,
			"maturity_date": fmt_dt(gam.get("acct_cls_date")),
			"mop": mop,
			"ifsc_code": "ICIC0000104",
			"e_transaction_no": f"SAHG{_clean_acct(gam.get('foracid') or account_id)}",
			"agent_code": "",
			"agent_name": "",
			"closure_voucher": closure_voucher,
		}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Finacle Passbook: Get Statement Download Data Failed")
	finally:
		if cursor:
			cursor.close()
		if conn:
			conn.close()

	base["front_page"] = front_page
	return base


@frappe.whitelist(allow_guest=False)
def download_account_ledger_pdf(account_id):
	"""Generate and download account ledger PDF (HPBP-style) for the given account ID."""
	result = _fetch_account_ledger_data(account_id)
	html = _build_ledger_pdf_html(result)
	pdf = get_pdf(html)

	account_id = _clean_acct(result.get("account_id") or account_id)
	filename = f"{account_id} HPBP.pdf" if account_id else "account_ledger_HPBP.pdf"

	frappe.local.response.filename = filename
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "download"
