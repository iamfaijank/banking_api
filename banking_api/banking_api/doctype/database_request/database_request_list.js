// Copyright (c) 2026, Talib Sheikh and contributors
// For license information, please see license.txt

frappe.listview_settings["Database Request"] = {
    add_fields: ["status"],

    refresh(listview) {
        // Avoid adding twice on refresh
        if (listview.page.__database_request_actions_added) return;
        listview.page.__database_request_actions_added = true;

        const action_label = __("Actions");

        // PAN Update Report
        listview.page.add_inner_button(__("PAN Update Report"), () => {
            frappe.call({
                method: "banking_api.banking_api.doctype.database_request.database_request.generate_pan_update_report",
                freeze: true,
                freeze_message: __("Generating PAN Update Report..."),
                callback(r) {
                    if (!r.exc && r.message) {
                        const file_url = r.message.file_url;
                        const file_name = r.message.file_name || "pan_update_report.csv";

                        // Trigger download
                        const link = document.createElement("a");
                        link.href = file_url;
                        link.download = file_name;
                        link.click();
                    } else {
                        frappe.msgprint(__("No data found or error while generating report."));
                    }
                },
            });
        }, action_label);
    },
};