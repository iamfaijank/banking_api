# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

# import frappe

import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class ShareProceedingLog(Document):
    def validate(self):
        # Set document name = date (YYYY-MM-DD)
        if self.date:
            date_str = getdate(self.date).strftime("%Y-%m-%d")
            self.name = date_str
