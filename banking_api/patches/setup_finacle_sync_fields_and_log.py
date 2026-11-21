import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
    # 1. Create Custom Field 'custom_finacle_synced' in Employee DocType
    custom_fields = {
        "Employee": [
            {
                "fieldname": "custom_finacle_synced",
                "label": "Finacle Synced",
                "fieldtype": "Check",
                "insert_after": "status",
                "default": "0",
                "read_only": 1
            }
        ]
    }
    create_custom_fields(custom_fields)
    
    # 2. Update existing employees to have custom_finacle_synced = 1
    frappe.db.sql("UPDATE `tabEmployee` SET custom_finacle_synced = 1 WHERE IFNULL(custom_finacle_synced, 0) = 0")
    
    # 3. Create 'Finacle EDR Sync Log' DocType if it doesn't exist
    if not frappe.db.exists("DocType", "Finacle EDR Sync Log"):
        doc = frappe.get_doc({
            "doctype": "DocType",
            "name": "Finacle EDR Sync Log",
            "module": "Banking API",
            "custom": 1,
            "istable": 0,
            "naming_rule": "Expression",
            "autoname": "format:FIN-SYNC-{YYYY}-{MM}-{####}",
            "fields": [
                {
                    "fieldname": "employee",
                    "label": "Employee",
                    "fieldtype": "Link",
                    "options": "Employee",
                    "in_list_view": 1,
                    "reqd": 1
                },
                {
                    "fieldname": "finacle_employee_id",
                    "label": "Finacle Employee ID",
                    "fieldtype": "Data",
                    "in_list_view": 1
                },
                {
                    "fieldname": "status",
                    "label": "Status",
                    "fieldtype": "Select",
                    "options": "Success\nFailed",
                    "in_list_view": 1,
                    "reqd": 1
                },
                {
                    "fieldname": "sync_time",
                    "label": "Sync Time",
                    "fieldtype": "Datetime",
                    "in_list_view": 1
                },
                {
                    "fieldname": "request_data",
                    "label": "Request Data",
                    "fieldtype": "Code"
                },
                {
                    "fieldname": "response_data",
                    "label": "Response Data",
                    "fieldtype": "Code"
                }
            ],
            "permissions": [
                {
                    "role": "System Manager",
                    "read": 1,
                    "write": 1,
                    "create": 1,
                    "delete": 1
                }
            ]
        })
        doc.insert(ignore_permissions=True)

    # 4. Create or Update Client Script for the DocType List view button
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
    refresh: function(listview) {
        setTimeout(() => {
            if (listview.page.btn_primary) {
                listview.page.btn_primary.html('<span class="hidden-xs">Sync Employees to Finacle</span>');
            }
        }, 10);
    }
};
    """

    script_name = frappe.db.get_value("Client Script", {"dt": "Finacle EDR Sync Log", "view": "List"})
    
    if script_name:
        script_doc = frappe.get_doc("Client Script", script_name)
        script_doc.script = js_code
        script_doc.save(ignore_permissions=True)
    else:
        script_doc = frappe.get_doc({
            "doctype": "Client Script",
            "name": "Finacle EDR Sync Log - List",
            "dt": "Finacle EDR Sync Log",
            "view": "List",
            "script": js_code,
            "module": "Banking API",
            "enabled": 1
        })
        script_doc.insert(ignore_permissions=True)

    frappe.db.commit()
