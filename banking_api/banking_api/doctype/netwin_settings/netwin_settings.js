// Copyright (c) 2026, Talib Sheikh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Netwin Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test Connection"), async () => {
			if (frm.is_dirty()) {
				await frm.save();
			}

			const response = await frm.call("test_connection");
			const result = response.message || {};

			frappe.msgprint({
				title: __("Oracle Connection Test"),
				message: __(result.message || "No response received."),
				indicator: result.status === "success" ? "green" : "red",
			});
		});
	},
});
