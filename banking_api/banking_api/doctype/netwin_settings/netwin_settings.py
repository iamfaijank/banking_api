# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class NetwinSettings(Document):
	@frappe.whitelist()
	def test_connection(self):
		try:
			import cx_Oracle
		except ImportError:
			frappe.throw(_("`cx_Oracle` is not installed on this server."))

		username = self.username
		password = self.get_password("password")
		host = self.host
		port = self.port
		sid = self.sid

		if not all([username, password, host, port, sid]):
			frappe.throw(_("Please fill all fields before testing the connection."))

		try:
			dsn = cx_Oracle.makedsn(host, port, service_name=sid)
			connection = cx_Oracle.connect(user=username, password=password, dsn=dsn)
			connection.close()
			return {
				"status": "success",
				"message": _("Connection successful."),
			}
		except cx_Oracle.DatabaseError as exc:
			error = exc.args[0] if exc.args else exc
			message = getattr(error, "message", str(error))
			return {
				"status": "error",
				"message": _("Connection failed: {0}").format(message),
			}
		except Exception as exc:
			return {
				"status": "error",
				"message": _("Unexpected error: {0}").format(str(exc)),
			}
