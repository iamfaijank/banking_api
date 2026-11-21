from collections import defaultdict
import csv
import io
from datetime import datetime

import frappe
from frappe import _


COMMISSION_DOCTYPE = "Commission"


ALLOWED_EXPORT_FIELDS = [
    "name",
    "creation",
    "sol_id",
    "sol_description",
    "agent_code",
    "agent_name",
    "pan_card",
    "pan_status",
    "cif",
    "agent_saving_account",
    "agent_security_account",
    "agent_operative_account",
    "customer_account_number",
    "customer_account_name",
    "collection",
    "eligible_amount",
    "commission_amount",
    "tds",
    "security_deposit",
    "netpay",
    "deduction",
    "final_net_pay",
    "scheme_code",
    "scheme_description",
    "`tabCommission Item`.commission_type",
]


def parse_date(value, field_label):
    if not value:
        frappe.throw(_("{0} is required.").format(field_label))

    try:
        # Parse DD-MM-YYYY format
        return datetime.strptime(value.strip(), "%d-%m-%Y").date()
    except ValueError:
        frappe.throw(
            _("{0} must be in DD-MM-YYYY format.").format(field_label)
        )


def parse_csv_values(value):
    """Convert a comma-separated value string into a distinct cleaned list."""
    if not value:
        return []

    values = []
    seen = set()

    for item in str(value).split(","):
        item = item.strip()

        if item and item not in seen:
            values.append(item)
            seen.add(item)

    return values


def get_report_filters(
    from_date,
    to_date,
    sol_id=None,
    agent_code=None,
    scheme_code=None,
):
    """Build Commission filters using dates and optional multi-select values."""
    from_date = parse_date(from_date, "From Date")
    to_date = parse_date(to_date, "To Date")

    if from_date > to_date:
        frappe.throw(_("From Date cannot be greater than To Date."))

    filters = {
        "creation": ["between", [from_date, to_date]]
    }

    sol_ids = parse_csv_values(sol_id)
    agent_codes = parse_csv_values(agent_code)
    scheme_codes = parse_csv_values(scheme_code)

    if sol_ids:
        filters["sol_id"] = ["in", sol_ids]

    if agent_codes:
        filters["agent_code"] = ["in", agent_codes]

    if scheme_codes:
        filters["scheme_code"] = ["in", scheme_codes]

    return filters


def get_distinct_values(fieldname):
    """Get cleaned, non-empty, distinct values from tabCommission."""
    allowed_fields = {"sol_id", "agent_code", "scheme_code"}

    if fieldname not in allowed_fields:
        frappe.throw(_("Invalid filter field."))

    rows = frappe.db.sql(
        f"""
        SELECT DISTINCT `{fieldname}` AS value
        FROM `tabCommission`
        WHERE IFNULL(TRIM(`{fieldname}`), '') != ''
        ORDER BY `{fieldname}` ASC
        """,
        as_dict=True,
    )

    return [str(row.value).strip() for row in rows if row.value]


@frappe.whitelist()
def get_commission_report_options():
    return {
        "sol_ids": get_distinct_values("sol_id"),
        "agent_codes": get_distinct_values("agent_code"),
        "scheme_codes": get_distinct_values("scheme_code"),
    }


@frappe.whitelist()
def download_commission_report(
    from_date,
    to_date,
    sol_id=None,
    agent_code=None,
    scheme_code=None,
):
    """Generate and download a CSV Commission report."""
    filters = get_report_filters(
        from_date=from_date,
        to_date=to_date,
        sol_id=sol_id,
        agent_code=agent_code,
        scheme_code=scheme_code,
    )

    records = frappe.get_all(
        COMMISSION_DOCTYPE,
        filters=filters,
        fields=ALLOWED_EXPORT_FIELDS,
        group_by="`tabCommission`.name",
        order_by="`tabCommission`.creation asc, `tabCommission`.sol_id asc, `tabCommission`.agent_code asc, `tabCommission`.scheme_code asc",
        limit_page_length=0,
    )

    output = io.StringIO()
    writer = csv.writer(output)

    # CSV column headers
    writer.writerow([
        "SOL ID",
        "SOL Name",
        "Scheme Code",
        "Scheme Description",
        "Commission Type",
        "Agent Code",
        "Agent Name",
        "PAN",
        "PAN Status",
        "CIF",
        "Agent Saving Account",
        "Agent Security Account",
        "Agent Operative Account",
        "Customer Account Number",
        "Customer Account Name",
        "Collection",
        "Eligible Amount",
        "Commission Amount",
        "TDS",
        "Security Deposit",
        "Net Pay",
        "Deduction",
        "Final Net Pay",
    ])

    for row in records:
        writer.writerow([
            row.get("sol_id") or "",
            row.get("sol_description") or "",
            row.get("scheme_code") or "",
            row.get("scheme_description") or "",
            row.get("commission_type") or "",
            row.get("agent_code") or "",
            row.get("agent_name") or "",
            row.get("pan_card") or "",
            row.get("pan_status") or "",
            row.get("cif") or "",
            row.get("agent_saving_account") or "",
            row.get("agent_security_account") or "",
            row.get("agent_operative_account") or "",
            row.get("customer_account_number") or "",
            row.get("customer_account_name") or "",
            row.get("collection") or 0,
            row.get("eligible_amount") or 0,
            row.get("commission_amount") or 0,
            row.get("tds") or 0,
            row.get("security_deposit") or 0,
            row.get("netpay") or 0,
            row.get("deduction") or 0,
            row.get("final_net_pay") or 0,
        ])

    safe_from_date = from_date.replace("-", "")
    safe_to_date = to_date.replace("-", "")

    frappe.local.response.filename = (
        f"commission_report_{safe_from_date}_to_{safe_to_date}.csv"
    )
    frappe.local.response.filecontent = output.getvalue()
    frappe.local.response.type = "download"

    return None


#########################################################################################################################################################


COMMISSION_DOCTYPE = "Commission"
BRANCH_DOCTYPE = "Sahayog Branch"
AGENT_DOCTYPE = "Agent"
EMPLOYEE_DOCTYPE = "Employee"
PRODUCT_DOCTYPE = "Product"


PRODUCT_GROUPS = ["FD", "DAM", "MIS", "RD", "DD", "SMBG"]


def parse_date(value, field_label):
    if not value:
        frappe.throw(_("{0} is required.").format(field_label))

    try:
        return datetime.strptime(value.strip(), "%d-%m-%Y").date()
    except ValueError:
        frappe.throw(
            _("{0} must be in DD-MM-YYYY format.").format(field_label)
        )


def parse_csv_values(value):
    if not value:
        return []

    values = []
    seen = set()

    for item in str(value).split(","):
        item = item.strip()

        if item and item not in seen:
            values.append(item)
            seen.add(item)

    return values


def get_agent_wise_report_filters(
    from_date,
    to_date,
    sol_id=None,
    agent_code=None,
    scheme_code=None,
):
    from_date = parse_date(from_date, "From Date")
    to_date = parse_date(to_date, "To Date")

    if from_date > to_date:
        frappe.throw(_("From Date cannot be greater than To Date."))

    filters = {
        "creation": ["between", [from_date, to_date]]
    }

    sol_ids = parse_csv_values(sol_id)
    agent_codes = parse_csv_values(agent_code)
    scheme_codes = parse_csv_values(scheme_code)

    if sol_ids:
        filters["sol_id"] = ["in", sol_ids]

    if agent_codes:
        filters["agent_code"] = ["in", agent_codes]

    if scheme_codes:
        filters["scheme_code"] = ["in", scheme_codes]

    return filters


def get_branch_lookup(sol_ids):
    """Return {sol_id: {district, region, zone}}"""
    if not sol_ids:
        return {}

    branches = frappe.get_all(
        BRANCH_DOCTYPE,
        filters={"sol_id": ["in", list(sol_ids)]},
        fields=["sol_id", "district", "region", "zone"],
    )

    return {
        branch.sol_id: {
            "district": branch.district or "",
            "region": branch.region or "",
            "zone": branch.zone or "",
        }
        for branch in branches
        if branch.sol_id
    }


def get_agent_lookup(agent_codes):
    """Return {agent_code: {auth_id, employee_name, designation}}"""
    if not agent_codes:
        return {}

    agents = frappe.get_all(
        AGENT_DOCTYPE,
        filters={"agent_code": ["in", list(agent_codes)]},
        fields=["agent_code", "auth_id"],
    )

    auth_ids = [agent.auth_id for agent in agents if agent.auth_id]

    employee_numbers = {
        auth_id.replace("SAH0", "").strip(): auth_id
        for auth_id in auth_ids
        if auth_id
    }

    employees = frappe.get_all(
        EMPLOYEE_DOCTYPE,
        filters={"name": ["in", list(employee_numbers.keys())]},
        fields=["name", "employee_name", "designation"],
    )

    employee_map = {
        employee.name: {
            "employee_name": employee.employee_name or "",
            "designation": employee.designation or "",
        }
        for employee in employees
    }

    return {
        agent.agent_code: {
            "auth_id": agent.auth_id or "",
            "employee_name": employee_map.get(
                agent.auth_id.replace("SAH0", "").strip(), {}
            ).get("employee_name", ""),
            "designation": employee_map.get(
                agent.auth_id.replace("SAH0", "").strip(), {}
            ).get("designation", ""),
        }
        for agent in agents
        if agent.agent_code
    }


def get_product_lookup(scheme_codes):
    """Return {scheme_code: commission_type}"""
    if not scheme_codes:
        return {}

    products = frappe.get_all(
        PRODUCT_DOCTYPE,
        filters={"product_code": ["in", list(scheme_codes)]},
        fields=["product_code", "commission_type"],
    )

    return {
        product.product_code: product.commission_type or ""
        for product in products
        if product.product_code
    }


@frappe.whitelist()
def download_agent_wise_summary(
    from_date,
    to_date,
    sol_id=None,
    agent_code=None,
    scheme_code=None,
):
    """Generate and download Agent Wise Summary as CSV.

    Each row represents one agent_code, aggregated across all matching
    Commission records.
    """
    filters = get_agent_wise_report_filters(
        from_date=from_date,
        to_date=to_date,
        sol_id=sol_id,
        agent_code=agent_code,
        scheme_code=scheme_code,
    )

    records = frappe.get_all(
        COMMISSION_DOCTYPE,
        filters=filters,
        fields=[
            "name",
            "sol_id",
            "sol_description",
            "agent_code",
            "agent_name",
            "pan_card",
            "pan_status",
            "cif",
            "agent_saving_account",
            "agent_security_account",
            "agent_operative_account",
            "scheme_code",
            "scheme_description",
            "group_name",
            "collection",
            "eligible_amount",
            "commission_amount",
            "tds",
            "security_deposit",
            "deduction",
        ],
        order_by="agent_code asc, creation asc",
        limit_page_length=0,
    )

    if not records:
        frappe.throw(
            _("No Commission records found for the selected filters."))

    # Build lookup maps once (avoids N+1 queries)
    sol_ids = {row.sol_id for row in records if row.sol_id}
    agent_codes = {row.agent_code for row in records if row.agent_code}
    scheme_codes = {row.scheme_code for row in records if row.scheme_code}

    branch_map = get_branch_lookup(sol_ids)
    agent_map = get_agent_lookup(agent_codes)
    product_map = get_product_lookup(scheme_codes)

    # Aggregate records by agent_code
    agent_summary = {}

    for row in records:
        agent_code = row.agent_code or ""
        if not agent_code:
            continue

        if agent_code not in agent_summary:
            branch = branch_map.get(row.sol_id, {})
            agent = agent_map.get(agent_code, {})

            agent_summary[agent_code] = {
                "sol_id": row.sol_id or "",
                "sol_description": row.sol_description or "",
                "district": branch.get("district", ""),
                "region": branch.get("region", ""),
                "zone": branch.get("zone", ""),
                "auth_id": agent.get("auth_id", ""),
                "auth_name": agent.get("employee_name", ""),
                "role": agent.get("designation", ""),
                "scheme_code": row.scheme_code or "",
                "scheme_description": row.scheme_description or "",
                "group_name": row.group_name or "",
                "commission_type": product_map.get(row.scheme_code, ""),
                "agent_name": row.agent_name or "",
                "pan_card": row.pan_card or "",
                "pan_status": row.pan_status or "",
                "cif": row.cif or "",
                "agent_saving_account": row.agent_saving_account or "",
                "agent_security_account": row.agent_security_account or "",
                "agent_operative_account": row.agent_operative_account or "",
                "group_totals": defaultdict(lambda: {"collection": 0.0, "eligible": 0.0, "commission": 0.0}),
                "total_tds": 0.0,
                "total_security_deposit": 0.0,
                "mobile_app_deduction": 0.0,
            }

        summary = agent_summary[agent_code]
        group_name = (row.group_name or "").strip().upper()

        if group_name in PRODUCT_GROUPS:
            summary["group_totals"][group_name]["collection"] += float(
                row.collection or 0)
            summary["group_totals"][group_name]["eligible"] += float(
                row.eligible_amount or 0)
            summary["group_totals"][group_name]["commission"] += float(
                row.commission_amount or 0)

        summary["total_tds"] += float(row.tds or 0)
        summary["total_security_deposit"] += float(row.security_deposit or 0)

        deduction = float(row.deduction or 0)
        if deduction > 0:
            summary["mobile_app_deduction"] = max(
                summary["mobile_app_deduction"], deduction
            )

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)

    headers = [
        "SOL ID",
        "SOL Name",
        "Dist",
        "Region",
        "Zone",
        "Auth ID",
        "Auth Name",
        "Role",
        "Scheme Code",
        "Scheme Description",
        "Group Name",
        "Commission Type",
        "Agent Code",
        "Agent Name",
        "PAN",
        "PAN Status",
        "Applicable TDS rate",
        "CIF",
        "Agent Saving Account (text)",
        "Agent Security Account",
        "Agent Operative Account",
    ]

    for group in PRODUCT_GROUPS:
        headers.extend([
            f"{group} Collection",
            f"{group} Eligible Amount",
            f"{group} Commission",
        ])

    headers.extend([
        "Total Collection",
        "Total Eligible Amount",
        "Total Commission",
        "TDS",
        "Security Deposit",
        "Mobile App Deduction",
        "Net Pay",
    ])

    writer.writerow(headers)

    for agent_code, summary in agent_summary.items():
        total_collection = 0.0
        total_eligible = 0.0
        total_commission = 0.0

        row = [
            summary["sol_id"],
            summary["sol_description"],
            summary["district"],
            summary["region"],
            summary["zone"],
            summary["auth_id"],
            summary["auth_name"],
            summary["role"],
            summary["scheme_code"],
            summary["scheme_description"],
            summary["group_name"],
            summary["commission_type"],
            agent_code,
            summary["agent_name"],
            summary["pan_card"],
            summary["pan_status"],
            "2%" if summary["pan_status"] == "Valid and Operative" else "20%",
            summary["cif"],
            summary["agent_saving_account"],
            summary["agent_security_account"],
            summary["agent_operative_account"],
        ]

        for group in PRODUCT_GROUPS:
            group_data = summary["group_totals"].get(
                group, {"collection": 0.0, "eligible": 0.0, "commission": 0.0})
            row.extend([
                group_data["collection"],
                group_data["eligible"],
                group_data["commission"],
            ])
            total_collection += group_data["collection"]
            total_eligible += group_data["eligible"]
            total_commission += group_data["commission"]

        net_pay = (
            total_commission
            - summary["total_tds"]
            - summary["total_security_deposit"]
            - summary["mobile_app_deduction"]
        )

        row.extend([
            total_collection,
            total_eligible,
            total_commission,
            summary["total_tds"],
            summary["total_security_deposit"],
            summary["mobile_app_deduction"],
            net_pay,
        ])

        writer.writerow(row)

    safe_from_date = from_date.replace("-", "")
    safe_to_date = to_date.replace("-", "")

    frappe.local.response.filename = (
        f"agent_wise_summary_{safe_from_date}_to_{safe_to_date}.csv"
    )
    frappe.local.response.filecontent = output.getvalue()
    frappe.local.response.type = "download"

    return None


@frappe.whitelist()
def download_product_wise_summary(
    from_date,
    to_date,
    sol_id=None,
    agent_code=None,
    scheme_code=None,
):
    """Generate and download Product Wise Summary as CSV.

    Each row represents one unique scheme_code, aggregated across all
    matching Commission records.
    """
    filters = get_agent_wise_report_filters(
        from_date=from_date,
        to_date=to_date,
        sol_id=sol_id,
        agent_code=agent_code,
        scheme_code=scheme_code,
    )

    records = frappe.get_all(
        COMMISSION_DOCTYPE,
        filters=filters,
        fields=[
            "scheme_code",
            "scheme_description",
            "group_name",
            "eligible_amount",
            "commission_amount",
            "netpay",
        ],
        order_by="scheme_code asc",
        limit_page_length=0,
    )

    if not records:
        frappe.throw(
            _("No Commission records found for the selected filters."))

    # Aggregate by scheme_code
    product_summary = {}

    for row in records:
        scheme_code = row.scheme_code or ""
        if not scheme_code:
            continue

        if scheme_code not in product_summary:
            product_summary[scheme_code] = {
                "scheme_description": row.scheme_description or "",
                "group_name": row.group_name or "",
                "eligible_amount": 0.0,
                "commission_amount": 0.0,
                "netpay": 0.0,
            }

        product_summary[scheme_code]["eligible_amount"] += float(
            row.eligible_amount or 0)
        product_summary[scheme_code]["commission_amount"] += float(
            row.commission_amount or 0)
        product_summary[scheme_code]["netpay"] += float(row.netpay or 0)

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)

    headers = [
        "Scheme Code",
        "Scheme Description",
        "Group Name",
        "Eligible Amount",
        "Commission Amount",
        "Netpay",
    ]

    writer.writerow(headers)

    for scheme_code, summary in product_summary.items():
        writer.writerow([
            scheme_code,
            summary["scheme_description"],
            summary["group_name"],
            summary["eligible_amount"],
            summary["commission_amount"],
            summary["netpay"],
        ])

    safe_from_date = from_date.replace("-", "")
    safe_to_date = to_date.replace("-", "")

    frappe.local.response.filename = (
        f"product_wise_summary_{safe_from_date}_to_{safe_to_date}.csv"
    )
    frappe.local.response.filecontent = output.getvalue()
    frappe.local.response.type = "download"

    return None
