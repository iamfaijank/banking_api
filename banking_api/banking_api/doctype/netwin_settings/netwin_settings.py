# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class NetwinSettings(Document):
	@frappe.whitelist()
	def test_connection(self):
		try:
			import oracledb
		except ImportError:
			frappe.throw(_("`oracledb` is not installed on this server."))

		client_path = self.oracle_client_path
		try:
			if client_path:
				oracledb.init_oracle_client(lib_dir=client_path)
			else:
				oracledb.init_oracle_client()
		except oracledb.ProgrammingError:
			pass  # Already initialized
		except Exception as e:
			frappe.msgprint(_("Warning: Could not initialize Oracle Client for Thick mode. Error: {0}").format(str(e)))

		username = self.username
		password = self.get_password("password")
		host = self.host
		port = self.port
		sid = self.sid

		if not all([username, password, host, port, sid]):
			frappe.throw(_("Please fill all fields before testing the connection."))

		try:
			dsn = oracledb.makedsn(host, port, service_name=sid)
			connection = oracledb.connect(user=username, password=password, dsn=dsn)
			connection.close()
			return {
				"status": "success",
				"message": _("Connection successful."),
			}
		except oracledb.DatabaseError as exc:
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
