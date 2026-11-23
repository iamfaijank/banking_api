import frappe


def _build_conditions(filters):
    """filters: list of [fieldname, operator, value]"""
    conditions = []
    values = {}
    for i, f in enumerate(filters or []):
        fieldname, operator, value = f[0], f[1], f[2]
        key = f"val{i}"
        if operator.lower() == "like":
            conditions.append(f"`{fieldname}` LIKE %({key})s")
            values[key] = f"%{value}%"
        else:
            conditions.append(f"`{fieldname}` = %({key})s")
            values[key] = value
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    return where_clause, values


@frappe.whitelist()
def get_commission_grouped(filters=None, limit_start=0, limit_page_length=10):
    """Returns one consolidated row per agent_code, with SUM'd amount fields."""
    filters = frappe.parse_json(filters) if filters else []
    limit_start = int(limit_start)
    limit_page_length = int(limit_page_length)

    where_clause, values = _build_conditions(filters)

    rows = frappe.db.sql(
        f"""
            SELECT
                agent_code,
                MAX(agent_name) AS agent_name,
                MAX(sol_id) AS sol_id,
                MAX(sol_description) AS sol_description,
                MAX(scheme_code) AS scheme_code,
                MAX(scheme_description) AS scheme_description,
                MAX(pan_card) AS pan_card,
                MAX(pan_status) AS pan_status,
                MAX(cif) AS cif,
                MAX(agent_saving_account) AS agent_saving_account,
                MAX(agent_security_account) AS security_account,
                MAX(agent_operative_account) AS operative_account,
                COALESCE(SUM(CAST(NULLIF(TRIM(collection), '') AS DECIMAL(18,2))), 0) AS collection,
                COALESCE(SUM(CAST(NULLIF(TRIM(eligible_amount), '') AS DECIMAL(18,2))), 0) AS eligible_amount,
                COALESCE(SUM(CAST(NULLIF(TRIM(commission_amount), '') AS DECIMAL(18,2))), 0) AS commission_amount,
                COALESCE(SUM(CAST(NULLIF(TRIM(tds), '') AS DECIMAL(18,2))), 0) AS tds,
                COALESCE(SUM(CAST(NULLIF(TRIM(security_deposit), '') AS DECIMAL(18,2))), 0) AS security_deposit,
                COALESCE(SUM(CAST(NULLIF(TRIM(netpay), '') AS DECIMAL(18,2))), 0) AS netpay
            FROM `tabCommission`
            WHERE {where_clause}
            GROUP BY agent_code
            ORDER BY agent_code ASC
            LIMIT %(limit_page_length)s OFFSET %(limit_start)s
        """,
        {**values, "limit_start": limit_start,
            "limit_page_length": limit_page_length},
        as_dict=True,
    )
    return rows


@frappe.whitelist()
def get_commission_grouped_count(filters=None):
    """Count of distinct agent_code groups matching the filters."""
    filters = frappe.parse_json(filters) if filters else []
    where_clause, values = _build_conditions(filters)

    row = frappe.db.sql(
        f"""
        SELECT COUNT(DISTINCT agent_code) AS total
        FROM `tabCommission`
        WHERE {where_clause}
        """,
        values,
        as_dict=True,
    )
    return row[0].get("total") or 0 if row else 0


# @frappe.whitelist()
# def get_commission_summary(filters=None):
#     """Overall totals across ALL matching rows (not just current page) — used for stat cards."""
#     filters = frappe.parse_json(filters) if filters else []
#     where_clause, values = _build_conditions(filters)

#     row = frappe.db.sql(
#         f"""
#         SELECT
#             COUNT(DISTINCT agent_code) AS total_records,
#             COALESCE(SUM(CAST(NULLIF(TRIM(eligible_amount), '') AS DECIMAL(18,2))), 0) AS total_eligible,
#             COALESCE(SUM(CAST(NULLIF(TRIM(commission_amount), '') AS DECIMAL(18,2))), 0) AS total_commission,
#             COALESCE(SUM(CAST(NULLIF(TRIM(netpay), '') AS DECIMAL(18,2))), 0) AS total_netpay,
#             COALESCE(SUM(CAST(NULLIF(TRIM(security_deposit), '') AS DECIMAL(18,2))), 0) AS total_security_deposit
#         FROM `tabCommission`
#         WHERE {where_clause}
#         """,
#         values,
#         as_dict=True,
#     )

#     result = row[0] if row else {}
#     return {
#         "total_records": result.get("total_records") or 0,
#         "total_eligible": float(result.get("total_eligible") or 0),
#         "total_commission": float(result.get("total_commission") or 0),
#         "total_netpay": float(result.get("total_netpay") or 0),
#         "total_security_deposit": float(result.get("total_security_deposit") or 0),
#     }


@frappe.whitelist()
def get_commission_summary(filters=None):
    """Overall totals across ALL matching rows, used for dashboard stat cards."""
    filters = frappe.parse_json(filters) if isinstance(
        filters, str) else (filters or [])
    where_clause, values = _build_conditions(filters)

    row = frappe.db.sql(
        f"""
        SELECT
            COUNT(DISTINCT c.agent_code) AS total_records,

            COALESCE(SUM(
                CASE WHEN c.group_name IN ('FD', 'DAM', 'MIS', 'RD', 'DD', 'SMBG')
                THEN COALESCE(CAST(NULLIF(TRIM(c.collection), '') AS DECIMAL(18,2)), 0)
                ELSE 0 END
            ), 0) AS total_collection,

            COALESCE(SUM(
                COALESCE(CAST(NULLIF(TRIM(c.eligible_amount), '') AS DECIMAL(18,2)), 0)
            ), 0) AS total_eligible,

            COALESCE(SUM(
                CASE WHEN c.group_name IN ('FD', 'DAM', 'MIS', 'RD', 'DD', 'SMBG')
                THEN COALESCE(CAST(NULLIF(TRIM(c.commission_amount), '') AS DECIMAL(18,2)), 0)
                ELSE 0 END
            ), 0) AS total_commission,

            COALESCE(SUM(
                COALESCE(CAST(NULLIF(TRIM(c.tds), '') AS DECIMAL(18,2)), 0)
            ), 0) AS total_tds,

            COALESCE(SUM(
                COALESCE(CAST(NULLIF(TRIM(c.security_deposit), '') AS DECIMAL(18,2)), 0)
            ), 0) AS total_security_deposit,

            GREATEST(
                COALESCE(MAX(
                    COALESCE(CAST(NULLIF(TRIM(c.deduction), '') AS DECIMAL(18,2)), 0)
                ), 0),
                0
            ) AS total_mobile_deduction,

            COALESCE(SUM(
                CASE WHEN c.group_name IN ('FD', 'DAM', 'MIS', 'RD', 'DD', 'SMBG')
                THEN COALESCE(CAST(NULLIF(TRIM(c.commission_amount), '') AS DECIMAL(18,2)), 0)
                ELSE 0 END
            ), 0)

            - COALESCE(SUM(
                COALESCE(CAST(NULLIF(TRIM(c.tds), '') AS DECIMAL(18,2)), 0)
            ), 0)

            - COALESCE(SUM(
                COALESCE(CAST(NULLIF(TRIM(c.security_deposit), '') AS DECIMAL(18,2)), 0)
            ), 0)

            - GREATEST(
                COALESCE(MAX(
                    COALESCE(CAST(NULLIF(TRIM(c.deduction), '') AS DECIMAL(18,2)), 0)
                ), 0),
                0
            ) AS total_netpay

        FROM `tabCommission` c
        WHERE {where_clause}
        """,
        values,
        as_dict=True,
    )

    result = row[0] if row else {}

    return {
        "total_records": result.get("total_records") or 0,
        "total_collection": float(result.get("total_collection") or 0),
        "total_eligible": float(result.get("total_eligible") or 0),
        "total_commission": float(result.get("total_commission") or 0),
        "total_tds": float(result.get("total_tds") or 0),
        "total_security_deposit": float(result.get("total_security_deposit") or 0),
        "total_netpay": float(result.get("total_netpay") or 0),
    }


@frappe.whitelist()
def get_commission_filter_options():
    sol = frappe.db.get_list(
        "Commission",
        fields=["sol_id", "sol_description"],
        group_by="sol_id",
        order_by="sol_id",
    )
    scheme = frappe.db.get_list(
        "Commission",
        fields=["scheme_code"],
        group_by="scheme_code",
        order_by="scheme_code",
        pluck="scheme_code",
    )
    agent = frappe.db.get_list(
        "Commission",
        fields=["agent_code"],
        group_by="agent_code",
        order_by="agent_code",
        pluck="agent_code",
    )

    return {
        "sol_list": [
            {
                "value": r.sol_id,
                "label": f"{r.sol_id} - {r.sol_description}" if r.sol_description else str(r.sol_id),
            }
            for r in sol
            if r.sol_id
        ],
        "scheme_list": [s for s in scheme if s],
        "agent_list": [a for a in agent if a],
    }


@frappe.whitelist(methods=["POST"])
def run_commission_payment(agent_codes=None, filters=None):
    agent_codes = frappe.parse_json(agent_codes) if isinstance(
        agent_codes, str) else (agent_codes or [])
    filters = frappe.parse_json(filters) if isinstance(
        filters, str) else (filters or [])

    if not agent_codes:
        frappe.throw("No agent codes provided for payment run.")

    # Exclude unselected agents: combine the incoming filters with an explicit
    # "agent_code IN (...)" restriction so payment only runs for selected agents.
    where_clause, values = _build_conditions(filters)

    placeholders = ", ".join(
        [f"%(agent_{i})s" for i in range(len(agent_codes))])
    for i, code in enumerate(agent_codes):
        values[f"agent_{i}"] = code

    # TODO: Replace this SELECT with your actual payment execution logic —
    # e.g. creating Payment Entry records, calling a bank disbursal API,
    # updating a "payment_status" field on Commission rows, etc.
    rows = frappe.db.sql(
        f"""
        SELECT agent_code,
               COALESCE(SUM(CAST(NULLIF(TRIM(netpay), '') AS DECIMAL(18,2))), 0) AS netpay
        FROM `tabCommission`
        WHERE {where_clause} AND agent_code IN ({placeholders})
        GROUP BY agent_code
        """,
        values,
        as_dict=True,
    )

    # frappe.db.commit() if you make DB changes above

    return {
        "status": "success",
        "paid_agents": [r.agent_code for r in rows],
        "total_paid": sum(float(r.netpay or 0) for r in rows),
    }


COMMISSION_GROUPS = ("FD", "DAM", "MIS", "RD", "DD", "SMBG")


def _commission_amount(field, group=None):
    """
    MariaDB-safe numeric expression for Commission fields.
    If group is provided, value is included only for that group_name.
    """
    amount = f"""
        COALESCE(
            CAST(NULLIF(TRIM(c.`{field}`), '') AS DECIMAL(18,2)),
            0
        )
    """

    if group:
        return f"""
            CASE WHEN c.group_name = '{group}'
            THEN {amount}
            ELSE 0 END
        """

    return amount


def _commission_group_columns():
    """Builds FD/DAM/MIS/RD/DD/SMBG collection, eligible and commission columns."""
    columns = []

    for group in COMMISSION_GROUPS:
        prefix = group.lower()

        columns.extend([
            f"COALESCE(SUM({_commission_amount('collection', group)}), 0) AS {prefix}_collection",
            f"COALESCE(SUM({_commission_amount('eligible_amount', group)}), 0) AS {prefix}_eligible_amount",
            f"COALESCE(SUM({_commission_amount('commission_amount', group)}), 0) AS {prefix}_commission",
        ])

    return ",\n\n".join(columns)


# @frappe.whitelist()
# def get_commission_detailed_report(filters=None, limit_start=0, limit_page_length=10):
#     """
#     Returns one detailed consolidated row per agent_code.

#     Adds Branch, Agent, Employee and Product details to the existing
#     agent-wise commission totals.
#     """
#     filters = frappe.parse_json(filters) if isinstance(
#         filters, str) else (filters or [])
#     limit_start = int(limit_start or 0)
#     limit_page_length = int(limit_page_length or 10)

#     where_clause, values = _build_conditions(filters)

#     values.update({
#         "limit_start": limit_start,
#         "limit_page_length": limit_page_length,
#     })

#     group_columns = _commission_group_columns()

#     rows = frappe.db.sql(
#         f"""
#         SELECT
#             c.agent_code,

#             MAX(c.sol_id) AS sol_id,
#             MAX(c.sol_description) AS sol_name,
#             MAX(b.district) AS dist,
#             MAX(b.region) AS region,
#             MAX(b.zone) AS zone,

#             MAX(a.auth_id) AS auth_id,
#             MAX(e.employee_name) AS auth_name,
#             MAX(e.designation) AS role,

#             MAX(c.scheme_code) AS scheme_code,
#             MAX(c.scheme_description) AS scheme_description,
#             MAX(c.group_name) AS group_name,
#             MAX(p.commission_type) AS commission_type,

#             MAX(c.agent_name) AS agent_name,
#             MAX(c.pan_card) AS pan,
#             MAX(c.pan_status) AS pan_status,

#             CASE
#                 WHEN MAX(c.pan_status) = 'Valid and Operative' THEN 2
#                 ELSE 20
#             END AS applicable_tds_rate,

#             MAX(c.cif) AS cif,
#             MAX(c.agent_saving_account) AS agent_saving_account,
#             MAX(c.agent_security_account) AS agent_security_account,
#             MAX(c.agent_operative_account) AS agent_operative_account,

#             {group_columns},

#             COALESCE(SUM(
#                 CASE WHEN c.group_name IN ('FD', 'DAM', 'MIS', 'RD', 'DD', 'SMBG')
#                 THEN {_commission_amount('collection')}
#                 ELSE 0 END
#             ), 0) AS total_collection,

#             COALESCE(SUM(
#                 CASE WHEN c.group_name IN ('FD', 'DAM', 'MIS', 'RD', 'DD', 'SMBG')
#                 THEN {_commission_amount('eligible_amount')}
#                 ELSE 0 END
#             ), 0) AS total_eligible_amount,

#             COALESCE(SUM(
#                 CASE WHEN c.group_name IN ('FD', 'DAM', 'MIS', 'RD', 'DD', 'SMBG')
#                 THEN {_commission_amount('commission_amount')}
#                 ELSE 0 END
#             ), 0) AS total_commission,

#             COALESCE(SUM({_commission_amount('tds')}), 0) AS tds,

#             COALESCE(SUM({_commission_amount('security_deposit')}), 0) AS security_deposit,

#             GREATEST(
#                 COALESCE(MAX({_commission_amount('deduction')}), 0),
#                 0
#             ) AS mobile_app_deduction,

#             COALESCE(SUM(
#                 CASE WHEN c.group_name IN ('FD', 'DAM', 'MIS', 'RD', 'DD', 'SMBG')
#                 THEN {_commission_amount('commission_amount')}
#                 ELSE 0 END
#             ), 0)

#             - COALESCE(SUM({_commission_amount('tds')}), 0)

#             - COALESCE(SUM({_commission_amount('security_deposit')}), 0)

#             - GREATEST(
#                 COALESCE(MAX({_commission_amount('deduction')}), 0),
#                 0
#             ) AS net_pay

#         FROM `tabCommission` c

#         LEFT JOIN `tabSahayog Branch` b
#             ON b.sol_id = c.sol_id

#         LEFT JOIN `tabAgent` a
#             ON a.agent_code = c.agent_code

#         LEFT JOIN `tabEmployee` e
#             ON e.name = REGEXP_REPLACE(a.auth_id, '^SAH0+', '')

#         LEFT JOIN `tabProduct` p
#             ON p.product_code = c.scheme_code

#         WHERE {where_clause}

#         GROUP BY c.agent_code

#         ORDER BY c.agent_code ASC

#         LIMIT %(limit_page_length)s OFFSET %(limit_start)s
#         """,
#         values,
#         as_dict=True,
#     )

#     return rows


@frappe.whitelist()
def get_commission_detailed_report(filters=None, limit_start=0, limit_page_length=10):
    """
    Fast agent-wise detailed commission report.

    Step 1: Aggregate Commission rows by agent_code.
    Step 2: Join Branch, Agent, Employee and Product only once per agent.
    """
    filters = frappe.parse_json(filters) if isinstance(
        filters, str) else (filters or [])
    limit_start = int(limit_start or 0)
    limit_page_length = int(limit_page_length or 10)

    where_clause, values = _build_conditions(filters)

    values.update({
        "limit_start": limit_start,
        "limit_page_length": limit_page_length,
    })

    rows = frappe.db.sql(
        f"""
        SELECT
            agg.agent_code,
            agg.sol_id,
            agg.sol_name,
            b.district AS dist,
            b.region AS region,
            b.zone AS zone,

            a.auth_id,
            e.employee_name AS auth_name,
            e.designation AS role,

            agg.scheme_code,
            agg.scheme_description,
            agg.group_name,
            p.commission_type,

            agg.agent_name,
            agg.pan,
            agg.pan_status,

            CASE
                WHEN agg.pan_status = 'Valid and Operative' THEN 2
                ELSE 20
            END AS applicable_tds_rate,

            agg.cif,
            agg.agent_saving_account,
            agg.agent_security_account,
            agg.agent_operative_account,

            agg.fd_collection,
            agg.fd_eligible_amount,
            agg.fd_commission,

            agg.dam_collection,
            agg.dam_eligible_amount,
            agg.dam_commission,

            agg.mis_collection,
            agg.mis_eligible_amount,
            agg.mis_commission,

            agg.rd_collection,
            agg.rd_eligible_amount,
            agg.rd_commission,

            agg.dd_collection,
            agg.dd_eligible_amount,
            agg.dd_commission,

            agg.smbg_collection,
            agg.smbg_eligible_amount,
            agg.smbg_commission,

            agg.total_collection,
            agg.total_eligible_amount,
            agg.total_commission,
            agg.tds,
            agg.security_deposit,
            agg.mobile_app_deduction,
            agg.net_pay

        FROM (

            SELECT
                c.agent_code,

                MAX(c.sol_id) AS sol_id,
                MAX(c.sol_description) AS sol_name,
                MAX(c.scheme_code) AS scheme_code,
                MAX(c.scheme_description) AS scheme_description,
                MAX(c.group_name) AS group_name,
                MAX(c.agent_name) AS agent_name,
                MAX(c.pan_card) AS pan,
                MAX(c.pan_status) AS pan_status,
                MAX(c.cif) AS cif,
                MAX(c.agent_saving_account) AS agent_saving_account,
                MAX(c.agent_security_account) AS agent_security_account,
                MAX(c.agent_operative_account) AS agent_operative_account,

                COALESCE(SUM(CASE WHEN c.group_name = 'FD'
                    THEN COALESCE(CAST(NULLIF(TRIM(c.collection), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0) AS fd_collection,

                COALESCE(SUM(CASE WHEN c.group_name = 'FD'
                    THEN COALESCE(CAST(NULLIF(TRIM(c.eligible_amount), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0) AS fd_eligible_amount,

                COALESCE(SUM(CASE WHEN c.group_name = 'FD'
                    THEN COALESCE(CAST(NULLIF(TRIM(c.commission_amount), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0) AS fd_commission,

                COALESCE(SUM(CASE WHEN c.group_name = 'DAM'
                    THEN COALESCE(CAST(NULLIF(TRIM(c.collection), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0) AS dam_collection,

                COALESCE(SUM(CASE WHEN c.group_name = 'DAM'
                    THEN COALESCE(CAST(NULLIF(TRIM(c.eligible_amount), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0) AS dam_eligible_amount,

                COALESCE(SUM(CASE WHEN c.group_name = 'DAM'
                    THEN COALESCE(CAST(NULLIF(TRIM(c.commission_amount), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0) AS dam_commission,

                COALESCE(SUM(CASE WHEN c.group_name = 'MIS'
                    THEN COALESCE(CAST(NULLIF(TRIM(c.collection), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0) AS mis_collection,

                COALESCE(SUM(CASE WHEN c.group_name = 'MIS'
                    THEN COALESCE(CAST(NULLIF(TRIM(c.eligible_amount), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0) AS mis_eligible_amount,

                COALESCE(SUM(CASE WHEN c.group_name = 'MIS'
                    THEN COALESCE(CAST(NULLIF(TRIM(c.commission_amount), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0) AS mis_commission,

                COALESCE(SUM(CASE WHEN c.group_name = 'RD'
                    THEN COALESCE(CAST(NULLIF(TRIM(c.collection), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0) AS rd_collection,

                COALESCE(SUM(CASE WHEN c.group_name = 'RD'
                    THEN COALESCE(CAST(NULLIF(TRIM(c.eligible_amount), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0) AS rd_eligible_amount,

                COALESCE(SUM(CASE WHEN c.group_name = 'RD'
                    THEN COALESCE(CAST(NULLIF(TRIM(c.commission_amount), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0) AS rd_commission,

                COALESCE(SUM(CASE WHEN c.group_name = 'DD'
                    THEN COALESCE(CAST(NULLIF(TRIM(c.collection), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0) AS dd_collection,

                COALESCE(SUM(CASE WHEN c.group_name = 'DD'
                    THEN COALESCE(CAST(NULLIF(TRIM(c.eligible_amount), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0) AS dd_eligible_amount,

                COALESCE(SUM(CASE WHEN c.group_name = 'DD'
                    THEN COALESCE(CAST(NULLIF(TRIM(c.commission_amount), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0) AS dd_commission,

                COALESCE(SUM(CASE WHEN c.group_name = 'SMBG'
                    THEN COALESCE(CAST(NULLIF(TRIM(c.collection), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0) AS smbg_collection,

                COALESCE(SUM(CASE WHEN c.group_name = 'SMBG'
                    THEN COALESCE(CAST(NULLIF(TRIM(c.eligible_amount), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0) AS smbg_eligible_amount,

                COALESCE(SUM(CASE WHEN c.group_name = 'SMBG'
                    THEN COALESCE(CAST(NULLIF(TRIM(c.commission_amount), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0) AS smbg_commission,

                COALESCE(SUM(CASE WHEN c.group_name IN ('FD', 'DAM', 'MIS', 'RD', 'DD', 'SMBG')
                    THEN COALESCE(CAST(NULLIF(TRIM(c.collection), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0) AS total_collection,

                COALESCE(SUM(CASE WHEN c.group_name IN ('FD', 'DAM', 'MIS', 'RD', 'DD', 'SMBG')
                    THEN COALESCE(CAST(NULLIF(TRIM(c.eligible_amount), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0) AS total_eligible_amount,

                COALESCE(SUM(CASE WHEN c.group_name IN ('FD', 'DAM', 'MIS', 'RD', 'DD', 'SMBG')
                    THEN COALESCE(CAST(NULLIF(TRIM(c.commission_amount), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0) AS total_commission,

                COALESCE(SUM(COALESCE(CAST(NULLIF(TRIM(c.tds), '') AS DECIMAL(18,2)), 0)), 0) AS tds,

                COALESCE(SUM(COALESCE(CAST(NULLIF(TRIM(c.security_deposit), '') AS DECIMAL(18,2)), 0)), 0) AS security_deposit,

                GREATEST(
                    COALESCE(MAX(COALESCE(CAST(NULLIF(TRIM(c.deduction), '') AS DECIMAL(18,2)), 0)), 0),
                    0
                ) AS mobile_app_deduction,

                COALESCE(SUM(CASE WHEN c.group_name IN ('FD', 'DAM', 'MIS', 'RD', 'DD', 'SMBG')
                    THEN COALESCE(CAST(NULLIF(TRIM(c.commission_amount), '') AS DECIMAL(18,2)), 0)
                    ELSE 0 END), 0)

                - COALESCE(SUM(COALESCE(CAST(NULLIF(TRIM(c.tds), '') AS DECIMAL(18,2)), 0)), 0)

                - COALESCE(SUM(COALESCE(CAST(NULLIF(TRIM(c.security_deposit), '') AS DECIMAL(18,2)), 0)), 0)

                - GREATEST(
                    COALESCE(MAX(COALESCE(CAST(NULLIF(TRIM(c.deduction), '') AS DECIMAL(18,2)), 0)), 0),
                    0
                ) AS net_pay

            FROM `tabCommission` c
            WHERE {where_clause}
            GROUP BY c.agent_code

            ORDER BY c.agent_code ASC
            LIMIT %(limit_page_length)s OFFSET %(limit_start)s

        ) agg

        LEFT JOIN `tabSahayog Branch` b
            ON b.sol_id = agg.sol_id

        LEFT JOIN `tabAgent` a
            ON a.agent_code = agg.agent_code

        LEFT JOIN `tabEmployee` e
            ON e.name = REGEXP_REPLACE(a.auth_id, '^SAH0+', '')

        LEFT JOIN `tabProduct` p
            ON p.product_code = agg.scheme_code

        ORDER BY agg.agent_code ASC
        """,
        values,
        as_dict=True,
    )

    return rows


@frappe.whitelist()
def get_commission_detailed_report_count(filters=None):
    """
    Returns the number of distinct agent_code groups matching the filters.
    Used for pagination of the detailed commission report.
    """
    filters = frappe.parse_json(filters) if isinstance(
        filters, str) else (filters or [])
    where_clause, values = _build_conditions(filters)

    row = frappe.db.sql(
        f"""
        SELECT COUNT(DISTINCT c.agent_code) AS total
        FROM `tabCommission` c
        WHERE {where_clause}
        """,
        values,
        as_dict=True,
    )

    return row[0]["total"] if row else 0
