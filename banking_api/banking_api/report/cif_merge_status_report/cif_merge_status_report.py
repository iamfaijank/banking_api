# Copyright (c) 2026, Antigravity and contributors
# For license information, please see license.txt

import frappe
from frappe import _
import io
import csv

def _has_report_access(user):
  allowed_roles = {"System Manager", "CIF Checker", "CIF Maker", "Employee"}
  user_roles = set(frappe.get_roles(user))
  return bool(allowed_roles.intersection(user_roles))

def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart(data)
	report_summary = get_report_summary(data)
	return columns, data, None, chart, report_summary


def get_columns():
	return [
		{
			"label": _("Date"),
			"fieldname": "action_date",
			"fieldtype": "Date",
			"width": 110
		},
		{
			"label": _("Aadhaar Number"),
			"fieldname": "aadhar",
			"fieldtype": "Link",
			"options": "CIF Merge",
			"width": 140
		},
		{
			"label": _("Doc Status"),
			"fieldname": "cif_status",
			"fieldtype": "Data",
			"width": 140
		},
		{
			"label": _("CIF ID"),
			"fieldname": "cif_id",
			"fieldtype": "Data",
			"width": 120
		},
		{
			"label": _("CIF Type"),
			"fieldname": "cif_type",
			"fieldtype": "Data",
			"width": 110
		},
		{
			"label": _("First Name"),
			"fieldname": "first_name",
			"fieldtype": "Data",
			"width": 130
		},
		{
			"label": _("Middle Name"),
			"fieldname": "middle_name",
			"fieldtype": "Data",
			"width": 120
		},
		{
			"label": _("Last Name"),
			"fieldname": "last_name",
			"fieldtype": "Data",
			"width": 130
		},
		{
			"label": _("Date of Birth"),
			"fieldname": "date_of_birth",
			"fieldtype": "Date",
			"width": 110
		},
		{
			"label": _("Mobile"),
			"fieldname": "mobile",
			"fieldtype": "Data",
			"width": 110
		},
		{
			"label": _("PAN"),
			"fieldname": "pan",
			"fieldtype": "Data",
			"width": 120
		},
		{
			"label": _("Sol ID"),
			"fieldname": "sol_id",
			"fieldtype": "Data",
			"width": 80
		},
		{
			"label": _("Creation Date"),
			"fieldname": "cif_creation",
			"fieldtype": "Date",
			"width": 110
		},
		{
			"label": _("Active Accounts Count"),
			"fieldname": "active_accounts_count",
			"fieldtype": "Int",
			"width": 110
		},
		{
			"label": _("Active Account Numbers"),
			"fieldname": "active_account_numbers",
			"fieldtype": "Data",
			"width": 200
		},
		{
			"label": _("Pin Code"),
			"fieldname": "pin_code",
			"fieldtype": "Data",
			"width": 90
		},
		{
			"label": _("Address"),
			"fieldname": "address",
			"fieldtype": "Data",
			"width": 220
		},
		{
			"label": _("Action Taken By"),
			"fieldname": "modified_by",
			"fieldtype": "Data",
			"width": 180
		}
	]


def get_data(filters):
	conditions = ["1=1"]
	values = {}

	if filters.get("from_date"):
		conditions.append("DATE(m.modified) >= %(from_date)s")
		values["from_date"] = filters.get("from_date")

	if filters.get("to_date"):
		conditions.append("DATE(m.modified) <= %(to_date)s")
		values["to_date"] = filters.get("to_date")

	if filters.get("cif_status"):
		conditions.append("m.cif_status = %(cif_status)s")
		values["cif_status"] = filters.get("cif_status")

	where_clause = " AND ".join(conditions)

	sql = f"""
		SELECT
			DATE(m.modified) as action_date,
			m.aadhar,
			m.cif_status,
			m.modified_by,
			d.cif_id,
			CASE 
				WHEN d.primary = 1 THEN 'Primary'
				WHEN d.merge = 1 THEN 'Merge'
				WHEN d.re_kyc = 1 THEN 'Re-KYC'
				ELSE '-'
			END as cif_type,
			d.first_name,
			d.middle_name,
			d.last_name,
			d.date_of_birth,
			d.mobile,
			d.pan,
			d.sol_id,
			d.cif_creation,
			COALESCE(d.active_accounts_count, 0) as active_accounts_count,
			COALESCE(d.active_account_numbers, '-') as active_account_numbers,
			d.pin_code,
			TRIM(CONCAT_WS(', ', 
				NULLIF(TRIM(d.address_line_1), ''),
				NULLIF(TRIM(d.address_line_2), ''),
				NULLIF(TRIM(d.address_line_3), '')
			)) as address
		FROM `tabCIF Merge` m
		INNER JOIN `tabCIF Details` d ON d.parent = m.name
		WHERE {where_clause}
		ORDER BY DATE(m.modified) DESC, m.name, d.primary DESC, d.merge DESC, d.idx ASC
	"""

	return frappe.db.sql(sql, values, as_dict=True)


def get_report_summary(data):
	# Unique documents count
	unique_docs = {}
	for r in data:
		unique_docs[r.get("aadhar")] = r.get("cif_status")

	draft = sum(1 for st in unique_docs.values() if st == "Draft")
	pending = sum(1 for st in unique_docs.values() if st == "Pending Verification")
	approved = sum(1 for st in unique_docs.values() if st == "Approved")
	rejected = sum(1 for st in unique_docs.values() if st == "Rejected")
	no_action = sum(1 for st in unique_docs.values() if st == "No Action Needed")

	summary = []
	if draft > 0:
		summary.append({
			"value": draft,
			"label": _("Draft Aadhaars"),
			"datatype": "Int",
			"indicator": "Gray"
		})
	if pending > 0:
		summary.append({
			"value": pending,
			"label": _("Pending Verification"),
			"datatype": "Int",
			"indicator": "Orange"
		})

	summary.extend([
		{
			"value": approved,
			"label": _("Approved Aadhaars"),
			"datatype": "Int",
			"indicator": "Green"
		},
		{
			"value": rejected,
			"label": _("Rejected Aadhaars"),
			"datatype": "Int",
			"indicator": "Red"
		},
		{
			"value": no_action,
			"label": _("No Action Needed"),
			"datatype": "Int",
			"indicator": "Blue"
		},
		{
			"value": len(unique_docs),
			"label": _("Total Aadhaars"),
			"datatype": "Int",
			"indicator": "Gray"
		},
		{
			"value": len(data),
			"label": _("Total CIF Rows"),
			"datatype": "Int",
			"indicator": "Purple"
		}
	])
	return summary


def get_chart(data):
	if not data:
		return None

	unique_docs = {}
	for r in data:
		k = (str(r.get("action_date")), r.get("aadhar"))
		unique_docs[k] = r.get("cif_status")

	date_status_map = {}
	for (d_str, aadhar), st in unique_docs.items():
		if d_str not in date_status_map:
			date_status_map[d_str] = {"Approved": 0, "Rejected": 0, "No Action Needed": 0, "Draft": 0, "Pending Verification": 0}
		if st in date_status_map[d_str]:
			date_status_map[d_str][st] += 1

	labels = sorted(list(date_status_map.keys()))[-10:]
	draft_data = [date_status_map[d]["Draft"] for d in labels]
	pending_data = [date_status_map[d]["Pending Verification"] for d in labels]
	approved_data = [date_status_map[d]["Approved"] for d in labels]
	rejected_data = [date_status_map[d]["Rejected"] for d in labels]
	no_action_data = [date_status_map[d]["No Action Needed"] for d in labels]

	datasets = []
	colors = []
	if any(draft_data):
		datasets.append({"name": _("Draft"), "values": draft_data})
		colors.append("#6b7280")
	if any(pending_data):
		datasets.append({"name": _("Pending Verification"), "values": pending_data})
		colors.append("#f59e0b")

	datasets.extend([
		{"name": _("Approved"), "values": approved_data},
		{"name": _("Rejected"), "values": rejected_data},
		{"name": _("No Action Needed"), "values": no_action_data}
	])
	colors.extend(["#16a34a", "#dc2626", "#2563eb"])

	return {
		"data": {
			"labels": labels,
			"datasets": datasets
		},
		"type": "bar",
		"colors": colors
	}

@frappe.whitelist()
def download_csv(filters=None):
	if not _has_report_access(frappe.session.user):
		frappe.throw(_("You don't have permission to get a report on: Employee"))

	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	data = get_data(filters)
	columns = [c["fieldname"] for c in get_columns()]
	headers = [c["label"] for c in get_columns()]

	output = io.StringIO()
	writer = csv.writer(output)
	writer.writerow(headers)
	for row in data:
		writer.writerow([row.get(col, "") for col in columns])

	return output.getvalue()