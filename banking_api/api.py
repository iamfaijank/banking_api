import base64
import hmac

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


def _unauthorized_response():
	frappe.local.response["http_status_code"] = 401
	return {
		"status": "error",
		"message": _("Unauthorized API request."),
	}


def _validate_api_request():
	if frappe.session.user != "Guest":
		return None

	auth_header = (frappe.get_request_header("Authorization") or "").strip()
	if not auth_header.startswith("token "):
		return _unauthorized_response()

	token_value = auth_header[6:].strip()
	if ":" not in token_value:
		return _unauthorized_response()

	provided_key, provided_secret = token_value.split(":", 1)
	provided_key = provided_key.strip()
	provided_secret = provided_secret.strip()

	settings = frappe.get_single("Netwin Settings")
	expected_key = (settings.api_key or "").strip()
	expected_secret = (settings.get_password("api_secret") or "").strip()

	if not expected_key or not expected_secret:
		frappe.local.response["http_status_code"] = 500
		return {
			"status": "error",
			"message": _("API credentials are not configured in Netwin Settings."),
		}

	if not (
		hmac.compare_digest(provided_key, expected_key)
		and hmac.compare_digest(provided_secret, expected_secret)
	):
		return _unauthorized_response()

	return None


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
	auth_error = _validate_api_request()
	if auth_error:
		return auth_error

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
	auth_error = _validate_api_request()
	if auth_error:
		return auth_error

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

	try:
		import cx_Oracle
	except ImportError:
		return {
			"status": "error",
			"message": _("`cx_Oracle` is not installed on this server."),
		}

	settings = frappe.get_single("Netwin Settings")
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
		dsn = cx_Oracle.makedsn(host, port, service_name=sid)
		connection = cx_Oracle.connect(user=username, password=password, dsn=dsn)
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
	except cx_Oracle.DatabaseError as exc:
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
