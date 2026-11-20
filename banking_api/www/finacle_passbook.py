import frappe
from frappe import _


def _get_finacle_migration_config_name():
	return frappe.db.get_single_value("Banking API Settings", "finacle_migration")


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
