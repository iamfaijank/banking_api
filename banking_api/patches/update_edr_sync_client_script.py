import frappe


def execute():
    """Update Client Script to add Retry Failed button for Finacle EDR Sync Log."""

    js_code = """
frappe.listview_settings['Finacle EDR Sync Log'] = {
    primary_action: function() {
        frappe.confirm(
            __('Are you sure you want to sync new employees to Finacle?'),
            function() {
                frappe.call({
                    method: "banking_api.finacle_sync.sync_employees_to_finacle",
                    freeze: true,
                    freeze_message: __('Syncing new employees to Finacle...'),
                    callback: function(r) {
                        frappe.msgprint(__('Sync process completed.'));
                        cur_list.refresh();
                    }
                });
            }
        );
    },
    onload: function(listview) {
        frappe.call({
            method: "frappe.client.get_count",
            args: {
                doctype: "Finacle EDR Sync Log",
                filters: { status: "Failed" }
            },
            callback: function(r) {
                if (r.message && r.message > 0) {
                    listview.page.add_button(__("Retry Failed (" + r.message + ")"), function() {
                        frappe.confirm(
                            __('Are you sure you want to retry ' + r.message + ' failed records?'),
                            function() {
                                frappe.call({
                                    method: "banking_api.finacle_sync.retry_failed_finacle_sync",
                                    freeze: true,
                                    freeze_message: __('Retrying failed employees...'),
                                    callback: function(r) {
                                        frappe.msgprint(__('Retry process completed.'));
                                        cur_list.refresh();
                                    }
                                });
                            }
                        );
                    }).addClass("btn-danger");
                }
            }
        });
    },
    refresh: function(listview) {
        setTimeout(() => {
            if (listview.page.btn_primary) {
                listview.page.btn_primary.html('<span class="hidden-xs">Sync Employees to Finacle</span>');
            }
        }, 10);
    }
};
    """

    script_name = frappe.db.get_value(
        "Client Script", {"dt": "Finacle EDR Sync Log", "view": "List"}
    )

    if script_name:
        frappe.db.set_value("Client Script", script_name, "script", js_code)
        frappe.db.commit()
