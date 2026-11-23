# import frappe
# from frappe import _


# @frappe.whitelist()
# def send_edr_sync_summary():
#     """
#     Fetches first and last successfully synced employee from
#     Finacle EDR Sync Log and sends an email using the
#     'Finacle EDR Sync Summary' Email Template.
#     """
#     first_log = frappe.db.get_value(
#         "Finacle EDR Sync Log",
#         {"status": "Success"},
#         ["employee", "finacle_employee_id", "sync_time"],
#         order_by="sync_time asc",
#     )

#     last_log = frappe.db.get_value(
#         "Finacle EDR Sync Log",
#         {"status": "Success"},
#         ["employee", "finacle_employee_id", "sync_time"],
#         order_by="sync_time desc",
#     )

#     if not first_log and not last_log:
#         frappe.logger().info("EDR Sync Summary: No successful sync logs found.")
#         return

#     first_emp_id = first_log[1] if first_log else "N/A"
#     first_emp_doc = first_log[0] if first_log else None
#     first_emp_name = frappe.db.get_value("Employee", first_emp_doc, "employee_name") if first_emp_doc else "N/A"
#     first_emp_branch = _get_employee_branch(first_emp_doc) if first_emp_doc else "N/A"

#     last_emp_id = last_log[1] if last_log else "N/A"
#     last_emp_doc = last_log[0] if last_log else None
#     last_emp_name = frappe.db.get_value("Employee", last_emp_doc, "employee_name") if last_emp_doc else "N/A"
#     last_emp_branch = _get_employee_branch(last_emp_doc) if last_emp_doc else "N/A"

#     recipients = ["siddharth.t@sahayogmultistate.com"]

#     args = {
#         "first_emp_id": first_emp_id,
#         "first_emp_name": first_emp_name,
#         "first_emp_branch": first_emp_branch,
#         "last_emp_id": last_emp_id,
#         "last_emp_name": last_emp_name,
#         "last_emp_branch": last_emp_branch,
#     }

#     frappe.sendmail(
#         recipients=recipients,
#         template="Finacle EDR Sync Summary",
#         args=args,
#     )

#     frappe.logger().info("EDR Sync Summary email sent to {0}".format(", ".join(recipients)))


# def _get_employee_branch(employee_name):
#     """Return branch name for a given Employee record name."""
#     branch = frappe.db.get_value("Employee", employee_name, "branch")
#     return branch or "N/A"
