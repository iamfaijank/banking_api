import time
import frappe
from frappe.model.document import Document
from custom_report.db_connection import get_dr_connection
from psycopg2.extras import RealDictCursor


class CIFMerge(Document):
	def validate(self):
		if not self.aadhar:
			frappe.throw(_("Please enter Aadhaar number."))

		# Agar user ne child table me already data edit/add kiya hai, to use overwrite mat karo
		if not self.cif_details and self.aadhar:
			records = get_cif_records(aadhar=self.aadhar)
			if records:
				for r in records:
					self.append("cif_details", {
						"cif_id": r.get("cif_id"),
						"first_name": r.get("first_name"),
						"middle_name": r.get("middle_name"),
						"last_name": r.get("last_name"),
						"cif_creation": r.get("cif_creation"),
						"date_of_birth": r.get("date_of_birth"),
						"pan": r.get("pan"),
						"mobile": r.get("mobile"),
						"phone_local_code": r.get("phone_local_code"),
						"sol_id": r.get("sol_id"),
						"address_line_1": r.get("address_line_1"),
						"address_line_2": r.get("address_line_2"),
						"address_line_3": r.get("address_line_3"),
						"pin_code": r.get("pin_code") or "",
						"active_accounts_count": r.get("active_accounts_count", 0),
						"active_account_numbers": r.get("active_account_numbers", "") or "",
						"primary": r.get("primary", 0),
						"merge": r.get("merge", 0),
						"re_kyc": r.get("re_kyc", 0)
					})

		if self.cif_details:
			self.total_cif_count = len(self.cif_details)
			# Agar koi bhi active cif ya active account hai to Active, warna Inactive
			has_active = any(
				(getattr(r, "cif_status", "") == "ACTIVE" or (getattr(r, "active_accounts_count", 0) or 0) > 0)
				for r in self.cif_details
			)
			self.status = "Active" if has_active else "Inactive"
		else:
			self.total_cif_count = 0
			self.status = "Inactive"

		if not self.cif_status:
			self.cif_status = "Draft"



ACTIVE_CIF_QUERY = """
WITH aadhaar_cif_count AS (
    SELECT
        referencenumber AS aadhaar_no,
        COUNT(DISTINCT orgkey) AS total_cif_count
    FROM crmuser.entitydocument
    WHERE UPPER(docdescr) LIKE 'AADHAAR%'
      AND doccode = '2'
      AND referencenumber IS NOT NULL
      AND TRIM(referencenumber) != ''
    GROUP BY referencenumber
)
SELECT
    ed.referencenumber                      AS "AADHAAR NUMBER",
    ed.docdescr                             AS "DOC DESCRIPTION",
    ed.orgkey                               AS "CIF ID",
    STRING_AGG(DISTINCT TRIM(pan.referencenumber), ', ') AS "PAN NUMBER",
    a.cust_first_name                       AS "FIRST NAME",
    a.cust_middle_name                      AS "MIDDLE NAME",
    a.cust_last_name                        AS "LAST NAME",
    TRIM(
        CONCAT_WS(' ',
            NULLIF(TRIM(a.cust_first_name), ''),
            NULLIF(TRIM(a.cust_middle_name), ''),
            NULLIF(TRIM(a.cust_last_name), '')
        )
    )                                       AS "CUSTOMER NAME",
    a.primary_sol_id                        AS "SOL ID",
    a.relationshipopeningdate               AS "CIF OPENING DATE",
    TO_CHAR(a.cust_dob, 'YYYY-MM-DD')       AS "CUST DOB",
    COUNT(DISTINCT g.foracid)               AS "ACTIVE ACCOUNTS COUNT",
    STRING_AGG(DISTINCT g.foracid, ', ')   AS "ACTIVE ACCOUNT NUMBERS",
    'ACTIVE'                                AS "CIF STATUS",
    cp.phone_type                           AS "PHONE TYPE",   
    cp.phonenolocalcode                     AS "PHONE LOCAL CODE",
    cp.phoneno                              AS "PHONE NUMBER",
    ad.addresscategory                      AS "ADDRESS CATEGORY",
    ad.address_line1                        AS "ADDRESS LINE 1",
    ad.address_line2                        AS "ADDRESS LINE 2",
    ad.address_line3                        AS "ADDRESS LINE 3",
    ad.zip                                  AS "PIN CODE",       
    ac.total_cif_count                      AS "TOTAL CIF COUNT"
FROM crmuser.entitydocument ed
JOIN aadhaar_cif_count ac
    ON ed.referencenumber = ac.aadhaar_no
LEFT JOIN crmuser.entitydocument pan
    ON ed.orgkey = pan.orgkey
   AND pan.doccode = 'PAN'
   AND UPPER(pan.docdescr) LIKE 'PAN%'    
LEFT JOIN crmuser.accounts a
    ON ed.orgkey = a.orgkey
LEFT JOIN crmuser.address ad
    ON ed.orgkey = ad.orgkey
   AND UPPER(ad.addresscategory) = 'MAILING'
LEFT JOIN crmuser.cphone cp
    ON ed.orgkey = cp.phone_b2kid
   AND UPPER(cp.phone_type) = 'CELLPH'
JOIN tbaadm.gam g
    ON a.orgkey = g.cif_id
   AND g.acct_cls_flg = 'N'
   AND g.entity_cre_flg = 'Y'
   AND g.del_flg = 'N'                                       
WHERE UPPER(ed.docdescr) LIKE 'AADHAAR%'  
  AND ed.doccode = '2'
  AND LENGTH(TRIM(ed.referencenumber)) = 12
  AND {filter_clause}
GROUP BY
    ed.referencenumber,
    ed.docdescr,
    ed.orgkey,
    a.cust_first_name,
    a.cust_middle_name,
    a.cust_last_name,
    cp.phone_type,
    cp.phonenolocalcode,
    cp.phoneno,        
    ad.addresscategory,
    ad.address_line1,
    ad.address_line2,
    ad.address_line3,
    ad.zip,
    a.primary_sol_id,
    a.relationshipopeningdate,
    a.cust_dob,
    ac.total_cif_count
HAVING COUNT(DISTINCT g.foracid) > 0
ORDER BY
    ac.total_cif_count DESC,
    ed.referencenumber,
    ed.orgkey
"""

INACTIVE_CIF_QUERY = """
WITH aadhaar_cif_count AS (
    SELECT
        referencenumber AS aadhaar_no,
        COUNT(DISTINCT orgkey) AS total_cif_count
    FROM crmuser.entitydocument
    WHERE UPPER(docdescr) LIKE 'AADHAAR%'
      AND doccode = '2'
      AND referencenumber IS NOT NULL
      AND TRIM(referencenumber) != ''
    GROUP BY referencenumber
)
SELECT
    ed.referencenumber            AS "AADHAAR NUMBER",
    ed.docdescr                   AS "DOC DESCRIPTION",
    ed.orgkey                     AS "CIF ID",
    STRING_AGG(DISTINCT TRIM(pan.referencenumber), ', ') AS "PAN NUMBER",
    a.cust_first_name             AS "FIRST NAME",
    a.cust_middle_name            AS "MIDDLE NAME",
    a.cust_last_name              AS "LAST NAME",
    TRIM(
        CONCAT_WS(' ',
            NULLIF(TRIM(a.cust_first_name), ''),
            NULLIF(TRIM(a.cust_middle_name), ''),
            NULLIF(TRIM(a.cust_last_name), '')
        )
    )                             AS "CUSTOMER NAME",
    a.primary_sol_id              AS "SOL ID",
    a.relationshipopeningdate     AS "CIF OPENING DATE",
    TO_CHAR(a.cust_dob, 'YYYY-MM-DD') AS "CUST DOB",
    COUNT(DISTINCT g.foracid)     AS "ACTIVE ACCOUNTS COUNT",
    COALESCE(STRING_AGG(DISTINCT g.foracid, ', '), 'NO ACTIVE ACCOUNT') AS "ACTIVE ACCOUNT NUMBERS",
    'INACTIVE'                    AS "CIF STATUS",
    cp.phone_type                 AS "PHONE TYPE",   
    cp.phonenolocalcode           AS "PHONE LOCAL CODE",
    cp.phoneno                    AS "PHONE NUMBER",
    ad.addresscategory            AS "ADDRESS CATEGORY",
    ad.address_line1              AS "ADDRESS LINE 1",
    ad.address_line2              AS "ADDRESS LINE 2",
    ad.address_line3              AS "ADDRESS LINE 3",
    ad.zip                        AS "PIN CODE",       
    ac.total_cif_count            AS "TOTAL CIF COUNT"
FROM crmuser.entitydocument ed
JOIN aadhaar_cif_count ac
    ON ed.referencenumber = ac.aadhaar_no
LEFT JOIN crmuser.entitydocument pan
    ON ed.orgkey = pan.orgkey
   AND pan.doccode = 'PAN'
   AND UPPER(pan.docdescr) LIKE 'PAN%'    
LEFT JOIN crmuser.accounts a
    ON ed.orgkey = a.orgkey
LEFT JOIN crmuser.address ad
    ON ed.orgkey = ad.orgkey
   AND UPPER(ad.addresscategory) = 'MAILING'
LEFT JOIN crmuser.cphone cp
    ON ed.orgkey = cp.phone_b2kid
   AND UPPER(cp.phone_type) = 'CELLPH'    
LEFT JOIN tbaadm.gam g
    ON a.orgkey = g.cif_id
   AND g.acct_cls_flg = 'N'
   AND g.entity_cre_flg = 'Y'
   AND g.del_flg = 'N'                                       
WHERE UPPER(ed.docdescr) LIKE 'AADHAAR%'
  AND ed.doccode = '2'
  AND LENGTH(TRIM(ed.referencenumber)) = 12
  AND {filter_clause}
GROUP BY
    ed.referencenumber,
    ed.docdescr,
    ed.orgkey,
    a.cust_first_name,
    a.cust_middle_name,
    a.cust_last_name,
    cp.phone_type,
    cp.phonenolocalcode,
    cp.phoneno,
    ad.addresscategory,
    ad.address_line1,
    ad.address_line2,
    ad.address_line3,
    ad.zip,     
    a.primary_sol_id,
    a.relationshipopeningdate,
    a.cust_dob,
    ac.total_cif_count
HAVING COUNT(DISTINCT g.foracid) = 0
ORDER BY
    ac.total_cif_count DESC,
    ed.referencenumber,
    ed.orgkey
"""


@frappe.whitelist()
def get_cif_records(aadhar=None, pan=None):
	if not aadhar and not pan:
		return []

	# Filter clause prepare
	params = {}
	if aadhar:
		filter_clause = "ed.referencenumber = %(search_val)s"
		params["search_val"] = str(aadhar).strip()
	else:
		filter_clause = "pan.referencenumber = %(search_val)s"
		params["search_val"] = str(pan).strip().upper()

	active_sql = ACTIVE_CIF_QUERY.format(filter_clause=filter_clause)
	inactive_sql = INACTIVE_CIF_QUERY.format(filter_clause=filter_clause)

	records = []
	conn = None
	try:
		conn = get_dr_connection()
		with conn.cursor(cursor_factory=RealDictCursor) as cur:
			# 1. Run Active query
			cur.execute(active_sql, params)
			active_rows = cur.fetchall() or []

			# 2. Run Inactive query
			cur.execute(inactive_sql, params)
			inactive_rows = cur.fetchall() or []

		raw_rows = active_rows + inactive_rows

		for r in raw_rows:
			records.append({
				"cif_id": r.get("CIF ID"),
				"first_name": r.get("FIRST NAME") or (r.get("CUSTOMER NAME", "").split(" ")[0] if r.get("CUSTOMER NAME") else ""),
				"middle_name": r.get("MIDDLE NAME") or "",
				"last_name": r.get("LAST NAME") or "",
				"cif_creation": str(r.get("CIF OPENING DATE")) if r.get("CIF OPENING DATE") else "",
				"date_of_birth": str(r.get("CUST DOB")) if r.get("CUST DOB") else "",
				"pan": r.get("PAN NUMBER") or "",
				"mobile": r.get("PHONE NUMBER") or "",
				"phone_local_code": r.get("PHONE LOCAL CODE") or "",
				"sol_id": r.get("SOL ID") or "",
				"address_line_1": r.get("ADDRESS LINE 1") or "",
				"address_line_2": r.get("ADDRESS LINE 2") or "",
				"address_line_3": r.get("ADDRESS LINE 3") or "",
				"pin_code": r.get("PIN CODE") or "",
				"cif_status": r.get("CIF STATUS") or "ACTIVE",
				"active_accounts_count": r.get("ACTIVE ACCOUNTS COUNT") or 0,
				"active_account_numbers": r.get("ACTIVE ACCOUNT NUMBERS") or "",
				"total_cif_count": r.get("TOTAL CIF COUNT") or len(raw_rows),
				"aadhar": r.get("AADHAAR NUMBER") or aadhar,
				"primary": 0,
				"merge": 0,
				"re_kyc": 0
			})

	except Exception as e:
		frappe.log_error(message=frappe.get_traceback(), title="CIF Records Fetch Failed")
		frappe.throw(f"Error fetching CIF records from DB: {str(e)}")
	finally:
		if conn:
			try:
				conn.close()
			except Exception:
				pass

	return records


@frappe.whitelist()
def get_status_summary():
	"""Returns counts of Active, Inactive, and Total records in CIF Merge."""
	counts = frappe.db.sql("""
		SELECT 
			COALESCE(NULLIF(status, ''), 'Inactive') as status_val,
			COUNT(*) as count
		FROM `tabCIF Merge`
		GROUP BY status_val
	""", as_dict=True)

	summary = {"Active": 0, "Inactive": 0, "Total": 0}
	for r in counts:
		val = r.status_val
		summary[val] = r.count
		summary["Total"] += r.count
	return summary


@frappe.whitelist()
def get_top_cif_counts():
	"""Returns all distinct total_cif_count values (from 1 upwards) with their record counts."""
	return frappe.db.sql("""
		SELECT total_cif_count, COUNT(*) as doc_count
		FROM `tabCIF Merge`
		WHERE total_cif_count > 0
		GROUP BY total_cif_count
		ORDER BY total_cif_count ASC
	""", as_dict=True)


@frappe.whitelist()
def trigger_sync_all():
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only System Manager can trigger sync."))
	frappe.enqueue(
		"banking_api.banking_api.doctype.cif_merge.cif_merge.sync_all_cif_merge_records",
		queue="long",
		timeout=3600
	)
	return {"status": "queued", "message": _("Bulk CIF Sync has started in the background.")}


@frappe.whitelist()
def sync_all_cif_merge_records(batch_size=10000):
	"""
	Bulk synchronizes duplicate CIF records from Finacle DR DB into 'CIF Merge' doctype
	using high-performance direct SQL bulk inserts.
	Command to execute:
		bench execute banking_api.banking_api.doctype.cif_merge.cif_merge.sync_all_cif_merge_records
	"""
	batch_size = int(batch_size)
	print(f"--- Starting Superfast Bulk CIF Merge Sync (Batch size: {batch_size}) ---")

	queries = [
		("ACTIVE", ACTIVE_CIF_QUERY.format(filter_clause="1=1")),
		("INACTIVE", INACTIVE_CIF_QUERY.format(filter_clause="1=1")),
	]

	total_processed = 0

	for label, sql in queries:
		print(f"\n[INFO] Processing {label} CIF Records...")
		batch_count = 0
		attempt = 0
		retry_count = 0
		while True:
			conn = None
			try:
				conn = get_dr_connection()
				with conn.cursor() as setup_cur:
					try:
						setup_cur.execute("SET statement_timeout = 0;")
						setup_cur.execute("SET idle_in_transaction_session_timeout = 0;")
					except Exception:
						pass

				cursor_name = f"cif_stream_{label.lower()}_{attempt}"
				with conn.cursor(name=cursor_name, cursor_factory=RealDictCursor) as cur:
					cur.itersize = batch_size
					cur.execute(sql)

					if batch_count > 0:
						print(f"[RECOVERY] Skipping {batch_count} already processed rows...")
						cur.scroll(batch_count, mode='absolute')

					while True:
						rows = cur.fetchmany(batch_size)
						if not rows:
							break

						# Group rows by Aadhaar number
						grouped = {}
						for r in rows:
							aadhaar = (r.get("AADHAAR NUMBER") or "").strip()
							if not aadhaar:
								continue
							if aadhaar not in grouped:
								grouped[aadhaar] = []
							grouped[aadhaar].append(r)

						_bulk_upsert_cif_records(grouped, status="Active" if label == "ACTIVE" else "Inactive")

						frappe.db.commit()
						batch_count += len(rows)
						total_processed += len(rows)
						print(f"[PROGRESS] {label}: {batch_count} records synced...")
						retry_count = 0

				break

			except Exception as e:
				frappe.db.rollback()
				attempt += 1
				retry_count += 1
				err_msg = str(e).strip()
				print(f"\n[WARNING] Disconnected at {batch_count} rows. Error: {err_msg}")
				wait_sec = min(retry_count * 5, 30)
				print(f"[RETRY attempt #{attempt}] Reconnecting in {wait_sec}s and resuming from row {batch_count}...")
				time.sleep(wait_sec)
			finally:
				if conn:
					try:
						conn.close()
					except Exception:
						pass

	print(f"\n--- Superfast CIF Merge Sync Completed! Total processed: {total_processed} ---")


@frappe.whitelist()
def update_existing_cif_merge_status():
	"""
	One-minute superfast batch update to set status (Active/Inactive) for all already-synced CIF Merge records.
	Command:
		bench execute banking_api.banking_api.doctype.cif_merge.cif_merge.update_existing_cif_merge_status
	"""
	print("--- Updating Status for already synced CIF Merge records ---")
	# 1. Jo Aadhar ke pass active CIF/accounts hain unhe Active set karo
	frappe.db.sql("""
		UPDATE `tabCIF Merge` cm
		SET cm.status = 'Active'
		WHERE cm.name IN (
			SELECT DISTINCT parent FROM `tabCIF Details`
			WHERE active_accounts_count > 0 OR cif_status = 'ACTIVE'
		)
	""")

	# 2. Baaki sabko Inactive set karo jinka status set nahi hua
	frappe.db.sql("""
		UPDATE `tabCIF Merge`
		SET status = 'Inactive'
		WHERE status IS NULL OR status = ''
	""")

	frappe.db.commit()
	print("--- Status update completed successfully! ---")


def _bulk_upsert_cif_records(grouped, status="Active"):
	"""Direct SQL bulk insert for CIF Merge and CIF Details to maximize ingestion speed."""
	now = frappe.utils.now()
	user = frappe.session.user or "Administrator"

	parent_records = []
	for aadhar, items in grouped.items():
		parent_records.append({
			"name": aadhar,
			"creation": now,
			"modified": now,
			"modified_by": user,
			"owner": user,
			"aadhar": aadhar,
			"total_cif_count": len(set(r.get("CIF ID") for r in items if r.get("CIF ID"))),
			"status": status,
			"cif_status": "Pending"
		})

	# 1. Bulk insert parent table `tabCIF Merge`
	frappe.db.bulk_insert(
		"CIF Merge",
		fields=["name", "creation", "modified", "modified_by", "owner", "aadhar", "total_cif_count", "status", "cif_status"],
		values=[list(d.values()) for d in parent_records],
		ignore_duplicates=True
	)

	# Existing records ka status bhi update karein
	aadhars = list(grouped.keys())
	if aadhars:
		format_strings = ','.join(['%s'] * len(aadhars))
		frappe.db.sql(
			f"UPDATE `tabCIF Merge` SET status = %s WHERE name IN ({format_strings}) AND (status IS NULL OR status != %s)",
			tuple([status] + aadhars + [status])
		)

	# 2. Fetch existing child cif_ids to avoid duplicates
	aadhars = list(grouped.keys())
	existing_cifs = set()
	if aadhars:
		format_strings = ','.join(['%s'] * len(aadhars))
		existing_rows = frappe.db.sql(
			f"SELECT parent, cif_id FROM `tabCIF Details` WHERE parent IN ({format_strings})",
			tuple(aadhars),
			as_dict=True
		)
		existing_cifs = {(row.parent, row.cif_id) for row in existing_rows}

	# 3. Prepare child rows for bulk insert
	child_records = []
	for aadhar, items in grouped.items():
		for idx, r in enumerate(items, 1):
			cif_id = r.get("CIF ID")
			if not cif_id or (aadhar, cif_id) in existing_cifs:
				continue

			child_name = frappe.generate_hash(length=10)
			first_name = r.get("FIRST NAME") or (r.get("CUSTOMER NAME", "").split(" ")[0] if r.get("CUSTOMER NAME") else "")
			cif_creation = str(r.get("CIF OPENING DATE")) if r.get("CIF OPENING DATE") else None
			dob = str(r.get("CUST DOB")) if r.get("CUST DOB") else None

			child_records.append([
				child_name, now, now, user, user,
				aadhar, "CIF Merge", "cif_details", idx,
				cif_id, first_name, r.get("MIDDLE NAME") or "", r.get("LAST NAME") or "",
				cif_creation, dob, r.get("PAN NUMBER") or "", r.get("PHONE NUMBER") or "",
				r.get("PHONE LOCAL CODE") or "", r.get("SOL ID") or "",
				r.get("ADDRESS LINE 1") or "", r.get("ADDRESS LINE 2") or "", r.get("ADDRESS LINE 3") or "",
				r.get("PIN CODE") or "",
				r.get("ACTIVE ACCOUNTS COUNT") or 0,
				r.get("ACTIVE ACCOUNT NUMBERS") or "",
				0, 0, 0
			])
			existing_cifs.add((aadhar, cif_id))

	if child_records:
		child_fields = [
			"name", "creation", "modified", "modified_by", "owner",
			"parent", "parenttype", "parentfield", "idx",
			"cif_id", "first_name", "middle_name", "last_name",
			"cif_creation", "date_of_birth", "pan", "mobile",
			"phone_local_code", "sol_id",
			"address_line_1", "address_line_2", "address_line_3",
			"pin_code",
			"active_accounts_count",
			"active_account_numbers",
			"primary", "merge", "re_kyc"
		]
		frappe.db.bulk_insert(
			"CIF Details",
			fields=child_fields,
			values=child_records,
			ignore_duplicates=True
		)



@frappe.whitelist()
def update_workflow_status(docname, action):
	"""
	Workflow transitions for CIF Merge:
	- Maker: 'send_to_checker' -> Pending Verification
	- Checker: 'approve' -> Approved
	- Checker: 'send_to_maker' -> Draft
	- Checker: 'reject' -> Rejected
	"""
	doc = frappe.get_doc("CIF Merge", docname)
	user_roles = frappe.get_roles(frappe.session.user)
	is_maker = "CIF Maker" in user_roles or "System Manager" in user_roles or frappe.session.user == "Administrator"
	is_checker = "CIF Checker" in user_roles or "System Manager" in user_roles or frappe.session.user == "Administrator"

	if action == "send_to_checker":
		if not is_maker:
			frappe.throw("Only CIF Maker can send records to checker.")
		has_primary = any(int(getattr(r, "primary", 0) or 0) == 1 for r in (doc.cif_details or []))
		if not has_primary:
			frappe.throw(_("Please select at least one Primary CIF."))
		doc.cif_status = "Pending Verification"
		doc.save()
		return {"status": doc.cif_status, "message": "Sent to Checker for verification."}

	elif action == "approve":
		if not is_checker:
			frappe.throw("Only CIF Checker can approve records.")
		doc.cif_status = "Approved"
		doc.save()
		return {"status": doc.cif_status, "message": "CIF Merge record approved successfully."}

	elif action == "send_to_maker":
		if not is_checker:
			frappe.throw("Only CIF Checker can send records back to maker.")
		doc.cif_status = "Draft"
		doc.save()
		return {"status": doc.cif_status, "message": "Record sent back to Maker for changes."}

	elif action == "reject":
		if not is_checker:
			frappe.throw("Only CIF Checker can reject records.")
		doc.cif_status = "Rejected"
		doc.save()
		return {"status": doc.cif_status, "message": "CIF Merge record rejected."}

	elif action == "no_action_needed":
		# Both Maker and Checker can mark No Action Needed
		if not (is_maker or is_checker):
			frappe.throw("Only CIF Maker or Checker can take this action.")
		doc.cif_status = "No Action Needed"
		doc.save()
		return {"status": doc.cif_status, "message": "Record marked as No Action Needed."}

	else:
		frappe.throw(f"Invalid action: {action}")


@frappe.whitelist()
def update_accounts_and_pincode_batch(batch_size=10000):
	"""
	Command to execute on server terminal:
	bench --site <site_name> execute banking_api.banking_api.doctype.cif_merge.cif_merge.update_accounts_and_pincode_batch
	"""
	print("\n[START] Fetching total rows to update...")
	total = frappe.db.sql("""
		SELECT COUNT(*) FROM `tabCIF Details`
		WHERE (active_account_numbers IS NULL OR active_account_numbers = '')
	""")[0][0]

	print(f"[INFO] Total {total} rows need accounts/pincode update.")
	if total == 0:
		print("[DONE] All records are already updated.")
		return

	offset = 0
	updated_count = 0

	while offset < total:
		# 1. Fetch batch of cif_ids from MariaDB
		rows = frappe.db.sql(f"""
			SELECT name, cif_id FROM `tabCIF Details`
			WHERE (active_account_numbers IS NULL OR active_account_numbers = '')
			LIMIT {batch_size}
		""", as_dict=True)

		if not rows:
			break

		cif_ids = [r.cif_id for r in rows if r.cif_id]
		if not cif_ids:
			break

		# 2. Query DR DB for accounts & zip for this batch
		conn = None
		cif_info = {}
		try:
			conn = get_dr_connection()
			with conn.cursor(cursor_factory=RealDictCursor) as cur:
				# Fetch active accounts
				cur.execute("""
					SELECT 
						cif_id,
						COUNT(DISTINCT foracid) as acc_count,
						STRING_AGG(DISTINCT foracid, ', ') as acc_numbers
					FROM tbaadm.gam
					WHERE cif_id = ANY(%s)
					  AND acct_cls_flg = 'N'
					  AND entity_cre_flg = 'Y'
					  AND del_flg = 'N'
					GROUP BY cif_id
				""", (cif_ids,))
				for ar in cur.fetchall() or []:
					cif_info[ar["cif_id"]] = {
						"acc_count": ar["acc_count"] or 0,
						"acc_numbers": ar["acc_numbers"] or ""
					}

				# Fetch mailing zip
				cur.execute("""
					SELECT orgkey, zip
					FROM crmuser.address
					WHERE orgkey = ANY(%s)
					  AND UPPER(addresscategory) = 'MAILING'
				""", (cif_ids,))
				for zr in cur.fetchall() or []:
					cid = zr["orgkey"]
					if cid not in cif_info:
						cif_info[cid] = {"acc_count": 0, "acc_numbers": ""}
					cif_info[cid]["zip"] = zr["zip"] or ""

		except Exception as e:
			print(f"[ERROR] DR DB query failed: {str(e)}")
			break
		finally:
			if conn:
				try:
					conn.close()
				except Exception:
					pass

		# 3. Update MariaDB in bulk using CASE statements
		update_cases_count = []
		update_cases_numbers = []
		update_cases_zip = []
		matched_names = []

		for r in rows:
			cid = r.cif_id
			info = cif_info.get(cid, {"acc_count": 0, "acc_numbers": "NO ACTIVE ACCOUNT", "zip": ""})
			acc_cnt = info.get("acc_count", 0)
			acc_num = info.get("acc_numbers") or "NO ACTIVE ACCOUNT"
			zip_code = info.get("zip", "")

			row_name = frappe.db.escape(r.name)
			update_cases_count.append(f"WHEN name = {row_name} THEN {acc_cnt}")
			update_cases_numbers.append(f"WHEN name = {row_name} THEN {frappe.db.escape(acc_num)}")
			if zip_code:
				update_cases_zip.append(f"WHEN name = {row_name} THEN {frappe.db.escape(zip_code)}")
			matched_names.append(row_name)

		if matched_names:
			names_in = ",".join(matched_names)
			zip_clause = f", pin_code = CASE {' '.join(update_cases_zip)} ELSE pin_code END" if update_cases_zip else ""
			update_sql = f"""
				UPDATE `tabCIF Details`
				SET 
					active_accounts_count = CASE {' '.join(update_cases_count)} ELSE 0 END,
					active_account_numbers = CASE {' '.join(update_cases_numbers)} ELSE 'NO ACTIVE ACCOUNT' END
					{zip_clause}
				WHERE name IN ({names_in})
			"""
			frappe.db.sql(update_sql)
			frappe.db.commit()

		updated_count += len(rows)
		print(f"[PROGRESS] Updated {updated_count}/{total} records...")

	print(f"\n[DONE] Successfully updated {updated_count} records.")


@frappe.whitelist()
def fix_cif_counts_and_pans():
	"""
	Command to execute on server terminal to correct total_cif_count and update multiple PANs:
	bench --site <site_name> execute banking_api.banking_api.doctype.cif_merge.cif_merge.fix_cif_counts_and_pans
	"""
	print("\n[1/2] Updating total_cif_count to exact distinct CIF IDs...")
	frappe.db.sql("""
		UPDATE `tabCIF Merge` cm 
		SET cm.total_cif_count = (
			SELECT COUNT(DISTINCT cif_id) 
			FROM `tabCIF Details` cd 
			WHERE cd.parent = cm.name
		)
	""")
	frappe.db.commit()
	print("[DONE] total_cif_count updated accurately.")

	print("\n[2/2] Fetching and aggregating multiple PANs from DR DB...")
	conn = None
	try:
		conn = get_dr_connection()
		with conn.cursor(cursor_factory=RealDictCursor) as cur:
			cur.execute("""
				SELECT 
					TRIM(orgkey) as cif_id,
					STRING_AGG(DISTINCT TRIM(referencenumber), ', ') as pan_numbers
				FROM crmuser.entitydocument
				WHERE doccode = 'PAN'
				  AND UPPER(docdescr) LIKE 'PAN%'
				  AND referencenumber IS NOT NULL
				  AND TRIM(referencenumber) != ''
				GROUP BY TRIM(orgkey)
			""")
			pan_rows = cur.fetchall() or []
	except Exception as e:
		print(f"[ERROR] Failed fetching PANs from DR DB: {str(e)}")
		pan_rows = []
	finally:
		if conn:
			try:
				conn.close()
			except Exception:
				pass

	if pan_rows:
		print(f"[INFO] Updating {len(pan_rows)} CIF PAN mappings into MariaDB...")
		batch_size = 5000
		for i in range(0, len(pan_rows), batch_size):
			chunk = pan_rows[i:i + batch_size]
			cases = []
			cifs = []
			for r in chunk:
				cid = frappe.db.escape(r["cif_id"])
				p_num = frappe.db.escape(r["pan_numbers"])
				cases.append(f"WHEN cif_id = {cid} THEN {p_num}")
				cifs.append(cid)
			
			if cifs:
				frappe.db.sql(f"""
					UPDATE `tabCIF Details`
					SET pan = CASE {' '.join(cases)} ELSE pan END
					WHERE cif_id IN ({','.join(cifs)})
				""")
				frappe.db.commit()
			print(f"[PROGRESS] Updated PANs for {min(i + batch_size, len(pan_rows))}/{len(pan_rows)}...")

	print("\n[COMPLETED] fix_cif_counts_and_pans executed successfully!")


@frappe.whitelist()
def get_full_cif_details(parent):
	"""Returns all child rows of cif_details for a given parent document without pagination limit."""
	return frappe.db.get_all(
		"CIF Details",
		filters={"parent": parent},
		fields=[
			"name", "cif_id", "first_name", "middle_name", "last_name",
			"date_of_birth", "mobile", "pan", "sol_id", "cif_creation",
			"active_accounts_count", "active_account_numbers", "pin_code",
			"address_line_1", "address_line_2", "address_line_3",
			"primary", "merge", "re_kyc"
		],
		order_by="primary desc, merge desc, idx asc",
		limit_page_length=0
	)
