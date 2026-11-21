import base64
import json

import frappe
from frappe import _

HELPER_QUERY = """
SELECT cif_id
FROM tbaadm.gam
WHERE foracid = %s
"""


QUERY = """
SELECT
    s.gmst_code,
    s.gr_id,
    s.acmastcode,
    s.ac_no,
    s.name,
    p.photo_long,
    p.gr_id AS photo_gr_id,
    p.branchcode AS photo_branchcode,
    f.sign_long,
    f.gr_id AS sign_gr_id,
    f.branchcode AS sign_branchcode
FROM signphoto s
JOIN photofl p
    ON s.gmst_code = p.gmst_code
JOIN signfl f
    ON s.gmst_code = f.gmst_code
WHERE
    (
        :gmst_code IS NOT NULL
        AND s.gmst_code = :gmst_code
    )
    OR
    (
        :ac_no IS NOT NULL
        AND s.ac_no = :ac_no
    )
"""

def _fetch_cif_id_from_helper_db(ac_no):
	try:
		import psycopg2
	except ImportError:
		return None, _("`psycopg2` is not installed on this server.")

	settings = frappe.get_single("Finacle DB Credentials")
	host = (settings.db_host or "").strip()
	port = settings.db_port
	user = (settings.db_user or "").strip()
	password = settings.get_password("db_password")
	db_name = (settings.db_name or "").strip()

	if not all([host, port, user, password, db_name]):
		return None, _("Finacle DB Credentials is incomplete.")

	connection = None
	cursor = None

	try:
		connection = psycopg2.connect(
			host=host,
			port=port,
			user=user,
			password=password,
			dbname=db_name,
		)
		cursor = connection.cursor()
		cursor.execute(HELPER_QUERY, (ac_no,))
		row = cursor.fetchone()

		if not row or not row[0]:
			return None, _("No CIF Id found for the provided Ac-no.")

		return str(row[0]).strip(), None
	except psycopg2.Error as exc:
		return None, _("PostgreSQL helper query failed: {0}").format(str(exc))
	finally:
		if cursor:
			cursor.close()
		if connection:
			connection.close()


@frappe.whitelist(allow_guest=True)
def fetch_cif_id(ac_no=None):
	ac_no = (ac_no or "").strip()

	if not ac_no:
		return {
			"status": "error",
			"message": _("Provide ac_no."),
		}

	cif_id, helper_error = _fetch_cif_id_from_helper_db(ac_no)
	if helper_error:
		return {
			"status": "error",
			"message": helper_error,
		}

	return {
		"status": "success",
		"data": {
			"gmst_code": cif_id,
		},
	}


def _encode_blob(value):
	if value is None:
		return None

	if hasattr(value, "read"):
		value = value.read()

	if isinstance(value, str):
		value = value.encode()

	return base64.b64encode(value).decode("utf-8")


@frappe.whitelist(allow_guest=True)
def fetch_photo_and_signature(gmst_code=None, ac_no=None, acmastcode=None):
	gmst_code = (gmst_code or "").strip()
	ac_no = (ac_no or "").strip()

	if not gmst_code and not ac_no:
		return {
			"status": "error",
			"message": _("Provide either gmst_code or ac_no."),
		}

	if ac_no and not gmst_code:
		gmst_code, helper_error = _fetch_cif_id_from_helper_db(ac_no)
		if helper_error:
			return {
				"status": "error",
				"message": helper_error,
			}
		ac_no = ""

	settings = frappe.get_single("Netwin Settings")

	try:
		import oracledb
	except ImportError:
		return {
			"status": "error",
			"message": _("`oracledb` is not installed on this server."),
		}

	try:
		if settings.oracle_client_path:
			oracledb.init_oracle_client(lib_dir=settings.oracle_client_path)
		else:
			oracledb.init_oracle_client()
	except oracledb.ProgrammingError:
		pass  # Already initialized
	except Exception:
		# Fallback to Thin mode if Thick mode initialization fails
		pass

	username = settings.username
	password = settings.get_password("password")
	host = settings.host
	port = settings.port
	sid = settings.sid

	if not all([username, password, host, port, sid]):
		return {
			"status": "error",
			"message": _("Netwin Settings is incomplete."),
		}

	connection = None
	cursor = None

	try:
		dsn = oracledb.makedsn(host, port, service_name=sid)
		connection = oracledb.connect(user=username, password=password, dsn=dsn)
		cursor = connection.cursor()
		cursor.execute(
			QUERY,
			{
				"gmst_code": gmst_code or None,
				"ac_no": ac_no or None,
			},
		)
		row = cursor.fetchone()

		if not row:
			return {
				"status": "error",
				"message": _("No record found for the provided parameters."),
			}

		data = dict(zip([column[0].lower() for column in cursor.description], row))
		data["photo_long"] = _encode_blob(data.get("photo_long"))
		data["sign_long"] = _encode_blob(data.get("sign_long"))

		return {
			"status": "success",
			"data": data,
		}
	except oracledb.DatabaseError as exc:
		error = exc.args[0] if exc.args else exc
		message = getattr(error, "message", str(error))
		return {
			"status": "error",
			"message": _("Oracle connection/query failed: {0}").format(message),
		}
	except Exception as exc:
		return {
			"status": "error",
			"message": _("Unexpected error: {0}").format(str(exc)),
		}
	finally:
		if cursor:
			cursor.close()
		if connection:
			connection.close()


@frappe.whitelist(allow_guest=True)
def fetch_netwin_branch_code():
	# Removed remote proxy logic as it is no longer required.
	# If needed, add local branch code fetching logic here.
	return {
		"status": "success",
		"message": "All",
	}


@frappe.whitelist(allow_guest=True)
def download_netwin_statement(branch_code, ac_code, ac_no, start_date, end_date, export_format="pdf"):
	from banking_api.statement_api import test_db
	return test_db(
		branch_code=branch_code,
		ac_code=ac_code,
		ac_no=ac_no,
		start_date=start_date,
		end_date=end_date,
		export_format=export_format
	)

@frappe.whitelist()
def get_user_context():
	user = frappe.session.user

	emp = frappe.db.get_value(
		"Employee",
		{"user_id": user},
		["name", "netwin_statement", "sol_id"],
		as_dict=True
	)

	branch = None
	if emp and emp.get("sol_id"):
		branch = frappe.db.get_value(
			"Sahayog Branch",
			{"sol_id": emp["sol_id"]},
			"branch_code"
		)

	branches = frappe.db.get_all(
		"Sahayog Branch",
		filters=[
			["branch_code", "is", "set"],   # remove NULL
			["branch_code", "!=", ""]       # remove empty
		],
		fields=["branch_code", "branch"],
		distinct=True
	)

	return {
		"user": user,
		"employee": emp,
		"user_branch": branch,
		"branches": branches
	}
