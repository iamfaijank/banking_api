frappe.listview_settings["Database Configuration"] = {
	button: {
		show(doc) {
			return true;
		},
		get_label() {
			return __("Test Connection");
		},
		get_description(doc) {
			return __("Test PostgreSQL connection for {0}", [doc.name]);
		},
		action(doc) {
			frappe.call({
				method: "banking_api.banking_api.doctype.database_configuration.database_configuration.test_connection_for_doc",
				args: {
					docname: doc.name
				},
				freeze: true,
				freeze_message: __("Testing Connection..."),
				callback: function(r) {
					if (!r.message) return;

					if (r.message.status === "success") {
						frappe.show_alert({
							message: __("Database connected successfully!"),
							indicator: "green"
						}, 5);

						frappe.msgprint({
							title: __("Connection Successful"),
							indicator: "green",
							message: `
								<div style="display: flex; align-items: center; gap: 14px; margin-bottom: 14px;">
									<div style="width: 42px; height: 42px; border-radius: 50%; background-color: #d1fae5; color: #059669; display: flex; align-items: center; justify-content: center; font-size: 20px; font-weight: bold; flex-shrink: 0;">
										✓
									</div>
									<div>
										<h4 style="margin: 0; font-weight: 600; color: #111827; font-size: 15px;">Connected to '${frappe.utils.escape_html(r.message.database)}'</h4>
										<p style="margin: 2px 0 0; color: #6b7280; font-size: 13px;">PostgreSQL database connection has been established successfully.</p>
									</div>
								</div>
								<div style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px 16px; font-size: 13px;">
									<div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
										<span style="color: #6b7280;">Host & Port:</span>
										<span style="font-weight: 600; font-family: monospace; color: #111827;">${frappe.utils.escape_html(r.message.host)}:${r.message.port || 5432}</span>
									</div>
									<div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
										<span style="color: #6b7280;">Database Name:</span>
										<span style="font-weight: 600; color: #111827;">${frappe.utils.escape_html(r.message.database)}</span>
									</div>
									<div style="display: flex; justify-content: space-between;">
										<span style="color: #6b7280;">Database User:</span>
										<span style="font-weight: 600; color: #111827;">${frappe.utils.escape_html(r.message.user)}</span>
									</div>
								</div>
							`
						});
					} else {
						frappe.msgprint({
							title: __("Connection Failed"),
							indicator: "red",
							message: `
								<div style="display: flex; align-items: flex-start; gap: 14px; margin-bottom: 12px;">
									<div style="width: 42px; height: 42px; border-radius: 50%; background-color: #fee2e2; color: #dc2626; display: flex; align-items: center; justify-content: center; font-size: 20px; font-weight: bold; flex-shrink: 0;">
										✕
									</div>
									<div>
										<h4 style="margin: 0; font-weight: 600; color: #111827; font-size: 15px;">Connection Error</h4>
										<p style="margin: 4px 0 0; color: #374151; font-size: 13px; line-height: 1.5;">${frappe.utils.escape_html(r.message.message)}</p>
									</div>
								</div>
							`
						});
					}
				}
			});
		}
	}
};
