import frappe
import psycopg2
import psycopg2.extras
from frappe import _
from frappe.model.document import Document
from datetime import date, datetime
from decimal import Decimal


class ShareApplicationSettings(Document):
    pass


def db_connection():
    """Connect to external PostgreSQL (Finacle) using Finacle DB Credentials."""
    try:
        creds = frappe.get_single("Finacle DB Credentials")
        port = int(creds.db_port) if creds.db_port else 5432

        conn = psycopg2.connect(
            host=creds.db_host,
            port=port,
            user=creds.db_user,
            password=creds.get_password("db_password"),
            database=creds.db_name
        )
        return conn
    except Exception as e:
        frappe.log_error(frappe.get_traceback(),
                         "PostgreSQL Connection Failed")
        frappe.throw(_("Database Connection Error: {0}").format(str(e)))


def _json_safe(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row):
    return {key: _json_safe(value) for key, value in row.items()}


# @frappe.whitelist()
# def get_loan_account_details():
#     """
#     Fetch all loan account details using the latest query
#     and return response in JSON format.
#     """
#     conn = None
#     cur = None

#     try:
#         conn = db_connection()
#         cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

#         query = """
#             SELECT DISTINCT
#                 g.cif_id,
#                 g.acct_name,
#                 g.foracid AS Ac_No,
#                 g.acct_opn_date,
#                 g.acct_cls_date,
#                 g.acct_cls_flg,
#                 l.payoff_flg AS Preclosed,
#                 c.dpd_cntr AS dpd,
#                 g.schm_code,
#                 g2.schm_desc,
#                 g.sol_id,
#                 s.sol_desc,
#                 g.schm_type,
#                 g.frez_code,
#                 g.sanct_lim AS loan_amt,
#                 l.dis_amt,
#                 l.rep_perd_mths,
#                 g.cum_cr_amt AS Total_Amt_Received,
#                 g.clr_bal_amt AS Outstanding_balance,
#                 ROUND(g.cum_cr_amt / NULLIF(l3.flow_amt, 0), 0) AS "Number of EMIs Paid",
#                 SUM(h.tran_amt) AS Total_Tran_Amt,
#                 l2.lim_exp_date AS loan_end_date,
#                 l3.flow_amt AS EMI,
#                 l.ei_perd_start_date,
#                 l.ei_perd_end_date,
#                 l.prin_dmd_os AS Principal_Overdue,
#                 l.int_dmd_os AS Interest_Overdue,
#                 e.NEXT_INT_RUN_DATE_DR,
#                 (
#                     EXTRACT(YEAR FROM age(current_date, l.ei_perd_start_date)) * 12 +
#                     EXTRACT(MONTH FROM age(current_date, l.ei_perd_start_date))
#                 ) AS EMI_Due_Count,
#                 (
#                     (
#                         EXTRACT(YEAR FROM age(current_date, l.ei_perd_start_date)) * 12 +
#                         EXTRACT(MONTH FROM age(current_date, l.ei_perd_start_date))
#                     ) * l3.flow_amt
#                 ) AS Total_Due_Amount,
#                 (
#                     (
#                         (
#                             EXTRACT(YEAR FROM age(current_date, l.ei_perd_start_date)) * 12 +
#                             EXTRACT(MONTH FROM age(current_date, l.ei_perd_start_date))
#                         ) * l3.flow_amt
#                     ) - g.cum_cr_amt
#                 ) AS Actual_Due_Amount,
#                 s.division_name,
#                 s.region_name,
#                 s.circle_office_name
#             FROM tbaadm.gam g
#             JOIN tbaadm.sol s ON g.sol_id = s.sol_id
#             JOIN tbaadm.gsp g2 ON g.schm_code = g2.schm_code
#             JOIN crmuser.accounts a ON g.cif_id = a.orgkey
#             JOIN tbaadm.lam l ON g.acid = l.acid
#             JOIN tbaadm.lht l2 ON l2.acid = g.acid
#             JOIN tbaadm.eit e ON g.acid = e.entity_id
#             JOIN tbaadm.lrs l3 ON g.acid = l3.acid
#             JOIN tbaadm.htd h ON g.acid = h.acid
#             JOIN tbaadm.gac c ON g.acid = c.acid
#             WHERE g.schm_code IN ('3001','3002','3003','3004','3024','3027','3028','3039','3040','3041','3042','3044','3045')
#               AND g.acct_cls_flg = 'N'
#               AND g.entity_cre_flg = 'Y'
#               AND g.del_flg = 'N'
#               AND h.part_tran_type = 'C'
#               AND COALESCE(l3.flow_amt, 0) <> 0
#             GROUP BY
#                 g.cif_id,
#                 g.foracid,
#                 g.acct_opn_date,
#                 g.acct_cls_date,
#                 g.acct_cls_flg,
#                 l.payoff_flg,
#                 c.dpd_cntr,
#                 g.sol_id,
#                 g.sanct_lim,
#                 s.sol_desc,
#                 g.acct_name,
#                 l.dis_amt,
#                 l.rep_perd_mths,
#                 g.cum_cr_amt,
#                 g.clr_bal_amt,
#                 l2.lim_exp_date,
#                 l3.flow_amt,
#                 l.ei_perd_start_date,
#                 l.ei_perd_end_date,
#                 l.prin_dmd_os,
#                 l.int_dmd_os,
#                 e.NEXT_INT_RUN_DATE_DR,
#                 g.schm_code,
#                 g2.schm_desc,
#                 g.frez_code,
#                 g.schm_type,
#                 g.acct_cls_flg,
#                 s.division_name,
#                 s.region_name,
#                 s.circle_office_name
#         """

#         cur.execute(query)
#         rows = cur.fetchall()
#         data = [_serialize_row(row) for row in rows]

#         return {
#             "status": "success",
#             "count": len(data),
#             "data": data
#         }

#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(),
#                          "Loan Account Details API Error")
#         frappe.throw(
#             _("Unable to fetch loan account details: {0}").format(str(e)))

#     finally:
#         if cur:
#             cur.close()
#         if conn:
#             conn.close()

@frappe.whitelist()
def get_loan_account_details():
    """
    Fetch all loan account details using the latest query
    and return response in JSON format.
    """
    conn = None
    cur = None

    try:
        conn = db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        query = """
            SELECT DISTINCT
                g.cif_id,
                g.acct_name,
                g.foracid AS Ac_No,
                g.acct_opn_date,
                g.acct_cls_date,
                g.acct_cls_flg,
                l.payoff_flg AS Preclosed,
                c.dpd_cntr AS dpd,
                g.schm_code,
                g2.schm_desc,
                g.sol_id,
                s.sol_desc,
                g.schm_type,
                g.frez_code,
                g.sanct_lim AS loan_amt,
                l.dis_amt,
                l.rep_perd_mths,
                g.cum_cr_amt AS Total_Amt_Received,
                g.clr_bal_amt AS Outstanding_balance,
                ROUND(g.cum_cr_amt / NULLIF(l3.flow_amt, 0), 0) AS "Number of EMIs Paid",
                SUM(h.tran_amt) AS Total_Tran_Amt,
                l2.lim_exp_date AS loan_end_date,
                l3.flow_amt AS EMI,
                l.ei_perd_start_date,
                l.ei_perd_end_date,
                l.prin_dmd_os AS Principal_outstanding,
                l.int_dmd_os AS Interest_Outstanding,
                l.prin_dmd_os + l.int_dmd_os + l.bchg_dmd_os + l.ochg_dmd_os AS Total_Overdue_Amount,
                e.NEXT_INT_RUN_DATE_DR,
                (
                    EXTRACT(YEAR FROM age(current_date, l.ei_perd_start_date)) * 12 +
                    EXTRACT(MONTH FROM age(current_date, l.ei_perd_start_date))
                ) AS EMI_Due_Count,
                (
                    (
                        EXTRACT(YEAR FROM age(current_date, l.ei_perd_start_date)) * 12 +
                        EXTRACT(MONTH FROM age(current_date, l.ei_perd_start_date))
                    ) * l3.flow_amt
                ) AS Total_Due_Amount,
                (
                    (
                        (
                            EXTRACT(YEAR FROM age(current_date, l.ei_perd_start_date)) * 12 +
                            EXTRACT(MONTH FROM age(current_date, l.ei_perd_start_date))
                        ) * l3.flow_amt
                    ) - g.cum_cr_amt
                ) AS Actual_Due_Amount,
                s.division_name,
                s.region_name,
                s.circle_office_name
            FROM tbaadm.gam g
            JOIN tbaadm.sol s ON g.sol_id = s.sol_id
            JOIN tbaadm.gsp g2 ON g.schm_code = g2.schm_code
            JOIN crmuser.accounts a ON g.cif_id = a.orgkey
            JOIN tbaadm.lam l ON g.acid = l.acid
            JOIN tbaadm.lht l2 ON l2.acid = g.acid
            JOIN tbaadm.eit e ON g.acid = e.entity_id
            JOIN tbaadm.lrs l3 ON g.acid = l3.acid
            JOIN tbaadm.htd h ON g.acid = h.acid
            JOIN tbaadm.gac c ON g.acid = c.acid
            WHERE g.schm_type = 'LAA'
              AND g.schm_code IN (
                    '3001', '3002', '3003', '3004', '3024', '3027',
                    '3028', '3039', '3040', '3041', '3042', '3044', '3045'
              )
              AND g.acct_cls_flg = 'N'
              AND g.entity_cre_flg = 'Y'
              AND g.del_flg = 'N'
              -- AND h.part_tran_type = 'C'
              AND COALESCE(l3.flow_amt, 0) <> 0
            GROUP BY
                g.cif_id,
                g.foracid,
                g.acct_opn_date,
                g.acct_cls_date,
                g.acct_cls_flg,
                l.payoff_flg,
                c.dpd_cntr,
                g.sol_id,
                g.sanct_lim,
                s.sol_desc,
                g.acct_name,
                l.dis_amt,
                l.rep_perd_mths,
                g.cum_cr_amt,
                g.clr_bal_amt,
                l2.lim_exp_date,
                l3.flow_amt,
                l.ei_perd_start_date,
                l.ei_perd_end_date,
                l.prin_dmd_os,
                l.int_dmd_os,
                l.bchg_dmd_os,
                l.ochg_dmd_os,
                e.NEXT_INT_RUN_DATE_DR,
                g.schm_code,
                g2.schm_desc,
                g.frez_code,
                g.schm_type,
                s.division_name,
                s.region_name,
                s.circle_office_name
        """

        cur.execute(query)
        rows = cur.fetchall()
        data = [_serialize_row(row) for row in rows]

        return {
            "status": "success",
            "count": len(data),
            "data": data
        }

    except Exception as e:
        frappe.log_error(
            frappe.get_traceback(),
            "Loan Account Details API Error"
        )
        frappe.throw(
            _("Unable to fetch loan account details: {0}").format(str(e))
        )

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
