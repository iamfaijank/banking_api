frappe.ui.form.on("Share Application Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Run Share Application Sync"), function () {
			frappe.call({
				method: "banking_api.banking_api.doctype.share_application_settings.share_application_settings.run_share_application_sync_manual",
				freeze: true,
				freeze_message: __("Running Share Application Sync..."),
				callback: function (r) {
					if (r.message) {
						frappe.msgprint({
							title: __("Sync Result"),
							message: r.message.message || __("Sync completed successfully."),
							indicator: r.message.status === "success" ? "green" : "orange"
						});
						frm.reload_doc();
					}
				}
			});
		}, __("Actions"));

		frm.add_custom_button(__("Run Bulk Share Payment"), function () {
			frappe.confirm(
				__("This will process all Share Application records whose status is not Success. Do you want to continue?"),
				function () {
					frappe.call({
						method: "banking_api.banking_api.doctype.share_application_settings.share_application_settings.run_bulk_share_application_payment",
						freeze: true,
						freeze_message: __("Processing bulk Share Application payments..."),
						callback: function (r) {
							if (r.message) {
								frappe.msgprint({
									title: __("Bulk Payment Result"),
									message: r.message.message || __("Bulk payment completed."),
									indicator: r.message.status === "success" ? "green" : "orange"
								});
								frm.reload_doc();
							}
						}
					});
				}
			);
		}, __("Actions"));
	}
});