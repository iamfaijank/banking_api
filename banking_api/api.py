import base64

import frappe
from frappe import _


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
        AND :acmastcode IS NOT NULL
        AND s.ac_no = :ac_no
        AND s.acmastcode = :acmastcode
    )
"""


def _encode_blob(value):
	if value is None:
		return None

	if hasattr(value, "read"):
		value = value.read()

	if isinstance(value, str):
		value = value.encode()

	return base64.b64encode(value).decode("utf-8")


@frappe.whitelist()
def fetch_photo_and_signature(gmst_code=None, ac_no=None, acmastcode=None):
	gmst_code = (gmst_code or "").strip()
	ac_no = (ac_no or "").strip()
	acmastcode = (acmastcode or "").strip()

	if not gmst_code and not (ac_no and acmastcode):
		return {
			"status": "error",
			"message": _("Provide either gmst_code or both ac_no and acmastcode."),
		}

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
				"acmastcode": acmastcode or None,
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
