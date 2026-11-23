# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CommissionSettings(Document):
	def before_validate(self):
		val = (
			getattr(self, "eligible_amount_setting", None)
			or getattr(self, "eligible_amount_rule", None)
			or getattr(self, "eligible_amount_basis", None)
		)
		if val:
			if "max" in str(val).lower():
				self.eligible_amount_setting = "Whichever is maximum demand or collection"
			else:
				self.eligible_amount_setting = "Whichever is minimum demand or collection"

	def on_update(self):
		if hasattr(self, "eligible_amount_setting") and self.eligible_amount_setting:
			frappe.db.set_single_value(
				"Commission Settings",
				"eligible_amount_rule",
				self.eligible_amount_setting,
			)

	@property
	def eligible_amount_rule(self):
		return getattr(self, "eligible_amount_setting", None)

	@eligible_amount_rule.setter
	def eligible_amount_rule(self, value):
		self.eligible_amount_setting = value

	@property
	def eligible_amount_basis(self):
		return getattr(self, "eligible_amount_setting", None)

	@eligible_amount_basis.setter
	def eligible_amount_basis(self, value):
		self.eligible_amount_setting = value

