import base64
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

import frappe
from frappe import _
from frappe.utils import get_url

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


def _normalize_base_url(value):
	return (value or "").strip().rstrip("/")


def _should_proxy_to_remote(base_url):
	base_url = _normalize_base_url(base_url)
	local_base_url = _normalize_base_url(get_url())

	if not base_url:
		return False

	return urlsplit(base_url) != urlsplit(local_base_url)


def _proxy_photo_and_signature_request(base_url, gmst_code=None, ac_no=None):
	url = "{0}/api/method/banking_api.api.fetch_photo_and_signature?{1}".format(
		_normalize_base_url(base_url),
		urlencode(
			{
				"gmst_code": gmst_code or "",
				"ac_no": ac_no or "",
			}
		),
	)
	request = Request(
		url,
		headers={
			"Accept": "application/json",
			"User-Agent": "banking_api_proxy/1.0",
		},
	)

	try:
		with urlopen(request, timeout=30) as response:
			payload = json.loads(response.read().decode("utf-8"))
	except HTTPError as exc:
		try:
			payload = json.loads(exc.read().decode("utf-8"))
		except Exception:
			return {
				"status": "error",
				"message": _("Remote API request failed with HTTP {0}.").format(exc.code),
			}
	except URLError as exc:
		return {
			"status": "error",
			"message": _("Remote API request failed: {0}").format(str(exc.reason)),
		}
	except Exception as exc:
		return {
			"status": "error",
			"message": _("Remote API request failed: {0}").format(str(exc)),
		}

	return payload.get("message", payload)


def _parse_remote_error_response(exc):
	try:
		body = exc.read()
	except Exception:
		body = b""

	try:
		payload = json.loads(body.decode("utf-8"))
		if isinstance(payload, dict):
			return payload.get("message") or payload.get("exc") or str(payload)
	except Exception:
		pass

	try:
		return body.decode("utf-8") or _("Remote API request failed with HTTP {0}.").format(exc.code)
	except Exception:
		return _("Remote API request failed with HTTP {0}.").format(exc.code)


def _proxy_remote_json_request(base_url, method_path, params=None):
	url = "{0}{1}".format(_normalize_base_url(base_url), method_path)

	if params:
		url = "{0}?{1}".format(url, urlencode(params))

	request = Request(
		url,
		headers={
			"Accept": "application/json",
			"User-Agent": "banking_api_proxy/1.0",
		},
	)

	try:
		with urlopen(request, timeout=30) as response:
			payload = json.loads(response.read().decode("utf-8"))
	except HTTPError as exc:
		return {
			"status": "error",
			"message": _parse_remote_error_response(exc),
		}
	except URLError as exc:
		return {
			"status": "error",
			"message": _("Remote API request failed: {0}").format(str(exc.reason)),
		}
	except Exception as exc:
		return {
			"status": "error",
			"message": _("Remote API request failed: {0}").format(str(exc)),
		}

	return payload.get("message", payload)


def _proxy_remote_statement_download(base_url, payload):
	url = "{0}/api/method/share_holder_management.share_holder_management.share_api.test_db".format(
		_normalize_base_url(base_url)
	)
	request = Request(
		url,
		data=urlencode(payload).encode("utf-8"),
		headers={
			"Accept": "*/*",
			"Content-Type": "application/x-www-form-urlencoded",
			"User-Agent": "banking_api_proxy/1.0",
		},
		method="POST",
	)

	try:
		with urlopen(request, timeout=120) as response:
			filecontent = response.read()
			content_type = response.headers.get("Content-Type", "")
	except HTTPError as exc:
		frappe.throw(_parse_remote_error_response(exc))
	except URLError as exc:
		frappe.throw(_("Remote API request failed: {0}").format(str(exc.reason)))
	except Exception as exc:
		frappe.throw(_("Remote API request failed: {0}").format(str(exc)))

	export_format = (payload.get("export_format") or "pdf").lower()
	filename = "Transaction_Statement_{0}.{1}".format(payload.get("ac_no", ""), export_format)

	frappe.local.response.filename = filename
	frappe.local.response.filecontent = filecontent
	frappe.local.response.type = "download"

	if content_type:
		frappe.local.response.content_type = content_type


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

	if _should_proxy_to_remote(settings.api_base_url):
		return _proxy_photo_and_signature_request(
			settings.api_base_url,
			gmst_code=gmst_code,
			ac_no=ac_no,
		)

	try:
		import cx_Oracle
	except ImportError:
		return {
			"status": "error",
			"message": _("`cx_Oracle` is not installed on this server."),
		}

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


@frappe.whitelist(allow_guest=True)
def fetch_netwin_branch_code():
	settings = frappe.get_single("Netwin Settings")

	if _should_proxy_to_remote(settings.api_base_url):
		return _proxy_remote_json_request(
			settings.api_base_url,
			"/api/method/share_holder_management.share_holder_management.netwin.netwin",
		)

	frappe.throw(_("Remote proxy is not required for the current Netwin Settings base URL."))


@frappe.whitelist(allow_guest=True)
def download_netwin_statement(branch_code, ac_code, ac_no, start_date, end_date, export_format="pdf"):
	settings = frappe.get_single("Netwin Settings")

	if not _should_proxy_to_remote(settings.api_base_url):
		frappe.throw(_("Remote proxy is not required for the current Netwin Settings base URL."))

	_proxy_remote_statement_download(
		settings.api_base_url,
		{
			"branch_code": (branch_code or "").strip(),
			"ac_code": (ac_code or "").strip(),
			"ac_no": (ac_no or "").strip(),
			"start_date": (start_date or "").strip(),
			"end_date": (end_date or "").strip(),
			"export_format": (export_format or "pdf").strip().lower(),
		},
	)
