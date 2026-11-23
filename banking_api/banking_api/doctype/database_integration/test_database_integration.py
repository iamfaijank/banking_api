import frappe
from frappe.tests.utils import FrappeTestCase
from banking_api.banking_api.doctype.database_integration.database_integration import DatabaseIntegration


class TestDatabaseIntegration(FrappeTestCase):
	def test_render_query_dynamic_dates(self):
		doc = frappe.new_doc("Database Integration")
		doc.source_query = "SELECT * FROM tbl WHERE created_on >= '{{ days_ago(3) }}' AND created_on <= '{{ today }}'"
		
		rendered = doc.render_query(doc.source_query)
		expected_date_from = frappe.utils.add_days(frappe.utils.today(), -3)
		expected_date_to = frappe.utils.today()

		self.assertIn(expected_date_from, rendered)
		self.assertIn(expected_date_to, rendered)
		self.assertEqual(rendered, f"SELECT * FROM tbl WHERE created_on >= '{expected_date_from}' AND created_on <= '{expected_date_to}'")

	def test_render_query_helpers(self):
		doc = frappe.new_doc("Database Integration")
		query = "SELECT * FROM tbl WHERE d >= '{{ add_days(today, -5) }}'"
		rendered = doc.render_query(query)
		expected_date = frappe.utils.add_days(frappe.utils.today(), -5)
		self.assertEqual(rendered, f"SELECT * FROM tbl WHERE d >= '{expected_date}'")

	def test_render_query_without_templates(self):
		doc = frappe.new_doc("Database Integration")
		query = "SELECT cust_id, pan FROM accounts WHERE active = 1"
		rendered = doc.render_query(query)
		self.assertEqual(rendered, query)

	def test_get_source_query_with_last_n_days_filter(self):
		doc = frappe.new_doc("Database Integration")
		doc.source_query = "SELECT cust_id, pan, created_date FROM netwin_accounts"
		doc.enable_date_filter = 1
		doc.date_filter_column = "created_date"
		doc.date_filter_mode = "Last N Days"
		doc.last_n_days = 3

		query, f_from, f_to = doc.get_source_query_with_filters()
		expected_from = frappe.utils.add_days(frappe.utils.today(), -3)
		self.assertIn(f"WHERE created_date >= '{expected_from}'", query)
		self.assertEqual(f_from, expected_from)

	def test_get_source_query_with_incremental_filter(self):
		doc = frappe.new_doc("Database Integration")
		doc.source_query = "SELECT cust_id, pan, updated_at FROM netwin_accounts"
		doc.enable_date_filter = 1
		doc.date_filter_column = "updated_at"
		doc.date_filter_mode = "Incremental (Sync From)"
		doc.sync_from = "2026-08-20 10:00:00"

		query, f_from, f_to = doc.get_source_query_with_filters()
		self.assertIn("WHERE updated_at > '2026-08-20 10:00:00' ORDER BY updated_at ASC", query)
		self.assertEqual(f_from, "2026-08-20 10:00:00")


