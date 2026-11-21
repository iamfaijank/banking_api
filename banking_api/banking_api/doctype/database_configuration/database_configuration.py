import time
import psycopg2
import frappe
from frappe import _
from frappe.model.document import Document


class DatabaseConfiguration(Document):
	def get_connection(self, retries=1, retry_delay=2, timeout=10):
		"""
		Establishes a connection to the PostgreSQL database using DocType configuration fields.
		"""
		if self.name and frappe.db.exists("Database Configuration", self.name):
			db_doc = frappe.get_doc("Database Configuration", self.name)
			host = self.host or db_doc.host
			port = self.port or db_doc.port
			user = self.user or db_doc.user
			database_name = self.database_name or db_doc.database_name
		else:
			host = self.host
			port = self.port
			user = self.user
			database_name = self.database_name

		if not host or not user:
			frappe.throw(_("Database configuration is incomplete. Host and User are required."))

		password = ""
		if not self.is_new():
			password = self.get_password(fieldname="password", raise_exception=False) or ""

		if not password and self.password and not set(self.password) == {"*"}:
			password = self.password

		connection_params = {
			"host": host,
			"port": int(port) if port else 5432,
			"user": user,
			"password": password,
			"database": database_name or "postgres",
			"connect_timeout": timeout,
		}


		last_error = None
		for attempt in range(retries):
			try:
				return psycopg2.connect(**connection_params)
			except psycopg2.Error as e:
				last_error = e
				if attempt < retries - 1:
					time.sleep(retry_delay)

		raise last_error

	@frappe.whitelist()
	def test_connection(self):
		"""
		Whitelisted method called from 'Test Connection' form button.
		"""
		target_db = self.database_name or "postgres"

		try:
			conn = self.get_connection(retries=2, retry_delay=1, timeout=10)
			conn.close()
			return {
				"status": "success",
				"host": self.host,
				"port": int(self.port) if self.port else 5432,
				"user": self.user,
				"database": target_db,
				"message": _("Database connection established successfully.")
			}
		except Exception as e:
			err_str = str(e)

			if "does not exist" in err_str.lower() and target_db != "postgres":
				return {
					"status": "failed",
					"message": _("Credentials are valid for user '{0}', but database '{1}' does not exist on server {2}.").format(
						self.user, target_db, self.host
					)
				}

			return {
				"status": "failed",
				"message": _("PostgreSQL database connection failed: {0}").format(err_str)
			}


@frappe.whitelist()
def test_connection_for_doc(docname):
	"""Whitelisted function to test connection for a specific document name from List View."""
	if not docname or not frappe.db.exists("Database Configuration", docname):
		return {
			"status": "failed",
			"message": _("Invalid Database Configuration record.")
		}

	doc = frappe.get_doc("Database Configuration", docname)
	return doc.test_connection()


def get_db_connection(name=None, database=None, database_name=None, **kwargs):
	"""
	Helper function to easily get a PostgreSQL connection anywhere in the codebase.
	Usage:
		from banking_api.banking_api.doctype.database_configuration.database_configuration import get_db_connection
		conn = get_db_connection("DC-00001") # or get_db_connection(database="CBS")
	"""
	filters = {}
	if name:
		filters["name"] = name
	elif database_name:
		filters["database_name"] = database_name
	elif database:
		filters["database"] = database

	docname = frappe.db.get_value("Database Configuration", filters, "name") if filters else None
	if not docname:
		frappe.throw(_("Database Configuration not found for: {0}").format(filters or name or database))

	doc = frappe.get_doc("Database Configuration", docname)
	return doc.get_connection(**kwargs)









