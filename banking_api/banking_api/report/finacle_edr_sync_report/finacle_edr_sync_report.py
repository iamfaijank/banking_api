import frappe
from frappe import _


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "fieldname": "employee",
            "label": _("Employee"),
            "fieldtype": "Link",
            "options": "Employee",
            "width": 120,
        },
        {
            "fieldname": "employee_name",
            "label": _("Employee Name"),
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "finacle_employee_id",
            "label": _("Finacle Employee ID"),
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "fieldname": "branch",
            "label": _("Branch"),
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "fieldname": "status",
            "label": _("Status"),
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "fieldname": "sync_time",
            "label": _("Sync Time"),
            "fieldtype": "Datetime",
            "width": 160,
        },
    ]


def get_data(filters):
    conditions = []

    if filters.get("from_date"):
        conditions.append("log.sync_time >= %(from_date)s")

    if filters.get("to_date"):
        conditions.append("log.sync_time <= %(to_date)s 23:59:59")

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    query = """
        SELECT
            log.employee,
            emp.employee_name,
            log.finacle_employee_id,
            emp.branch,
            log.status,
            log.sync_time
        FROM `tabFinacle EDR Sync Log` log
        LEFT JOIN `tabEmployee` emp ON emp.name = log.employee
        {where_clause}
        ORDER BY log.sync_time ASC
    """.format(where_clause=where_clause)

    data = frappe.db.sql(query, filters, as_dict=True)
    return data
