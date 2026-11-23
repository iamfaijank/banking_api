# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

from tqdm import tqdm

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, cint, flt, getdate, now_datetime

import psycopg2
from psycopg2.extras import RealDictCursor

from decimal import (
    Decimal,
    ROUND_HALF_UP,
)

from datetime import date, datetime
from dateutil.relativedelta import relativedelta


class Commission(Document):
    pass


def db_connection():
    """Connect to external PostgreSQL using Finacle DB Credentials."""
    try:
        creds = frappe.get_single("Finacle DB Credentials")

        port = int(creds.db_port) if creds.db_port else 5432

        return psycopg2.connect(
            host=creds.db_host,
            port=port,
            user=creds.db_user,
            password=creds.get_password("db_password"),
            database=creds.db_name,
        )

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "PostgreSQL Connection Failed",
        )
        frappe.throw(_("Database Connection Error"))


def get_commission_query_dates(from_date=None, to_date=None):
    """
    Return dynamic reporting dates based on provided dates or T-1 (yesterday) for current month.
    """
    if from_date and to_date:
        start_dt = frappe.utils.getdate(from_date)
        end_dt = frappe.utils.getdate(to_date)
        current_month_start = start_dt
        report_date = end_dt
        current_month_end = end_dt
        previous_month_start = start_dt - relativedelta(months=1)
        previous_month_end = start_dt - relativedelta(days=1)
    else:
        today = date.today()
        # T-1: yesterday's date
        report_date = today - relativedelta(days=1)

        # Current month start based on report_date (T-1)
        current_month_start = report_date.replace(day=1)

        # Current month end
        current_month_end = (
            current_month_start
            + relativedelta(months=1)
            - relativedelta(days=1)
        )

        # Previous month start and end
        previous_month_start = current_month_start - relativedelta(months=1)
        previous_month_end = current_month_start - relativedelta(days=1)

    return {
        "present_date": report_date.isoformat(),           # T-1 or custom end_date
        "current_month_start": current_month_start.isoformat(),
        "current_month_end": current_month_end.isoformat(),
        "previous_month_start": previous_month_start.isoformat(),
        "previous_month_end": previous_month_end.isoformat(),
    }


# QUERY_1 = """
# WITH account_data AS (
#     SELECT
#         d.rm_id,
#         g2.emp_name AS rm_name,
#         d2.operacc,
#         g.cif_id,
#         g.acct_opn_date,
#         a2.relationshipopeningdate AS cif_id_opening_date,
#         g.foracid,
#         g.sol_id,
#         sol.sol_desc,
#         g.schm_code AS scheme_code,
#         gsp.schm_desc,
#         tam.deposit_period_days,
#         tam.deposit_period_mths,
#         tam.deposit_amount,
#         /* ADDED - ACCOUNT NAME FROM GAM */
#         g.acct_name
#     FROM custom.dsamap d
#     INNER JOIN tbaadm.gam g
#         ON g.foracid = d.account_number
#         AND g.schm_code IN ('2004','2005','2006','2010','2011','2012','2013','2014','2015')
#     LEFT JOIN tbaadm.tam tam
#         ON tam.acid = g.acid
#     LEFT JOIN crmuser.accounts a2
#         ON g.cif_id = a2.orgkey
#     LEFT JOIN tbaadm.sol sol
#         ON g.sol_id = sol.sol_id
#     LEFT JOIN tbaadm.gsp gsp
#         ON g.schm_code = gsp.schm_code
#     LEFT JOIN custom.dsaauth d2
#         ON d.rm_id = d2.user_id
#     LEFT JOIN tbaadm.get g2
#         ON d2.user_id = g2.emp_id
# ),
# flow_data AS (
#     SELECT
#         d.rm_id,
#         g.foracid,
#         g.schm_code,
#         SUM(tdt.flow_amt) AS total_flow_amount
#     FROM custom.dsamap d
#     INNER JOIN tbaadm.gam g
#         ON g.foracid = d.account_number
#         AND g.schm_code IN ('2004','2005','2006','2010','2011','2012','2013','2014','2015')
#     INNER JOIN tbaadm.tdt tdt
#         ON tdt.acid = g.acid
#         AND tdt.flow_code = 'NI'
#     WHERE
#         tdt.flow_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31'    // curr start date and present date
#     GROUP BY d.rm_id, g.foracid, g.schm_code
#     HAVING SUM(tdt.flow_amt) > 0
# ),
# tran_data AS (
#     SELECT
#         d.rm_id,
#         g.foracid,
#         g.schm_code,
#         SUM(dtt.tran_amt) AS total_tran_amt
#     FROM custom.dsamap d
#     INNER JOIN tbaadm.gam g
#         ON g.foracid = d.account_number
#         AND g.schm_code IN ('2004','2005','2006','2010','2011','2012','2013','2014','2015')
#     INNER JOIN tbaadm.dtt dtt
#         ON dtt.acid = g.acid
#         AND dtt.flow_code = 'NI'
#     WHERE
#         (
#             (dtt.tran_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31'    // curr start date and present date
#              AND dtt.value_date > DATE '2026-07-31')     // previous month end date
#             OR
#             (dtt.tran_date > DATE '2026-08-31'
#              AND dtt.value_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31')    // curr start date and present date
#             OR
#             (dtt.value_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31'    // curr start date and present date
#              AND dtt.tran_date > DATE '2026-08-31')      // current month end date
#         )
#     GROUP BY d.rm_id, g.foracid, g.schm_code
#     HAVING SUM(dtt.tran_amt) > 0
# ),
# reference_data AS (
#     SELECT
#         ed.referencenumber,
#         da.user_id AS rm_id
#     FROM crmuser.entitydocument ed
#     INNER JOIN tbaadm.gam g
#         ON ed.orgkey = g.cif_id
#     INNER JOIN custom.dsaauth da
#         ON g.foracid = da.operacc
#     WHERE ed.doccode = 'PAN'
# )
# SELECT
#     ad.rm_id,
#     ad.rm_name,
#     ad.operacc,
#     ad.cif_id,
#     ad.acct_opn_date,
#     ad.acct_opn_date,
#     ad.cif_id_opening_date,
#     ad.foracid,
#     /* ADDED - ACCOUNT NAME */
#     ad.acct_name,
#     ad.deposit_amount,
#     COALESCE(fd.total_flow_amount,0) AS total_flow_amount,
#     /* CHANGED - SCHEME 2004 KA FLOW AMT SAME RAHEGA
#        SCHEME 2005-2015 KA * 3 HOGA */
#     CASE
#         WHEN ad.scheme_code = '2004'
#             THEN COALESCE(fd.total_flow_amount,0)
#         WHEN ad.scheme_code IN ('2005','2006','2010','2011','2012','2013','2014','2015')
#             THEN COALESCE(fd.total_flow_amount,0) * 3
#         ELSE COALESCE(fd.total_flow_amount,0)
#     END AS adjusted_flow_amount,
#     COALESCE(td.total_tran_amt,0) AS total_tran_amt,
#     LEAST(
#         COALESCE(fd.total_flow_amount,0),
#         COALESCE(td.total_tran_amt,0)
#     ) AS commission_amount,
#     CASE
#         WHEN ad.acct_opn_date + INTERVAL '1 year' >= DATE '2026-08-31' THEN 'YES'     // current month end date
#         ELSE 'NO'
#     END AS one_year_completed,
#     ad.deposit_period_days,
#     ad.deposit_period_mths,
#     COALESCE(rd.referencenumber,'N/A') AS referencenumber,
#     ad.scheme_code,
#     ad.schm_desc,
#     ad.sol_id,
#     ad.sol_desc
# FROM account_data ad
# LEFT JOIN flow_data fd
#     ON ad.rm_id = fd.rm_id
#     AND ad.foracid = fd.foracid
#     AND ad.scheme_code = fd.schm_code
# LEFT JOIN tran_data td
#     ON ad.rm_id = td.rm_id
#     AND ad.foracid = td.foracid
#     AND ad.scheme_code = td.schm_code
# LEFT JOIN reference_data rd
#     ON ad.rm_id = rd.rm_id
# WHERE
#     COALESCE(td.total_tran_amt,0) > 0
#     -- ADDED: SIRF RDDSA AUR DDDSA PREFIX WALE RM_ID
# AND (
#     UPPER(ad.rm_id) LIKE 'RDDSA%'
#     OR UPPER(ad.rm_id) LIKE 'DDDSA%'
# )
# ORDER BY
#     ad.foracid,
#     ad.rm_id,
#     ad.scheme_code;

# """
# QUERY_2 = """
# --COMMITION QUERY 2 -- COUNT 6,563

# WITH account_data AS (
# SELECT
# ds.rm_id,
# g2.emp_name AS rm_name,
# d2.operacc,
# g.foracid,
# g.acct_name,                    /* ADDED - ACCOUNT NAME FROM GAM */
# g.acct_opn_date,
# tam.deposit_amount,
# tam.deposit_period_mths,
# tam.deposit_period_days,
# COUNT(DISTINCT g.acid) AS count_acid_gam,
# SUM(dtt.tran_amt) AS total_tran_amt_dtt,
# SUM(tdt.flow_amt) AS total_flow_amt_tdt,
# g.sol_id,
# sol.sol_desc,
# g.schm_code AS scheme_code,
# gsp.schm_desc
# FROM custom.dsamap AS ds
# LEFT JOIN tbaadm.gam AS g
# ON g.foracid = ds.account_number
# AND g.schm_code IN (
# '2001','2002','2003',
# '2018','2019','2020','2021','2022','2023','2024','2025','2026','2027','2028','2029','2030','2031','2032','2033','2034','2035',
# '2101','2102','2103','2104','2105','2106',
# '2201','2202','2203',
# '9001','9002'
# )
# AND g.acct_opn_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31'    // curr month start date and present date
# AND g.acct_cls_flg = 'N'
# LEFT JOIN tbaadm.tam AS tam
# ON tam.acid = g.acid
# LEFT JOIN tbaadm.dtt AS dtt
# ON dtt.acid = g.acid
# AND dtt.flow_code = 'PI'
# AND dtt.tran_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31'       // curr month start date and present date
# AND NOT (
# dtt.value_date >= DATE '2026-07-01'    // prev month start date
# AND dtt.value_date < DATE '2026-08-01'    // curr month start date
# )
# LEFT JOIN tbaadm.tdt AS tdt
# ON tdt.acid = g.acid
# AND tdt.flow_code = 'PI'
# AND tdt.flow_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31'       // curr month start date and present date
# LEFT JOIN custom.dsaauth AS d2
# ON UPPER(ds.rm_id) = UPPER(d2.user_id)
# LEFT JOIN tbaadm.get AS g2
# ON d2.user_id = g2.emp_id
# LEFT JOIN tbaadm.sol AS sol
# ON g.sol_id = sol.sol_id
# LEFT JOIN tbaadm.gsp AS gsp
# ON gsp.schm_code = g.schm_code
# GROUP BY
# ds.rm_id,
# g2.emp_name,
# d2.operacc,
# g.foracid,
# g.acct_name,                    /* ADDED */
# g.acct_opn_date,
# tam.deposit_amount,
# tam.deposit_period_mths,
# tam.deposit_period_days,
# g.sol_id,
# sol.sol_desc,
# g.schm_code,
# gsp.schm_desc
# ),
# reference_data AS (
# SELECT
# ed.referencenumber,
# da.user_id AS rm_id
# FROM crmuser.entitydocument AS ed
# JOIN tbaadm.gam AS g
# ON ed.orgkey = g.cif_id
# JOIN custom.dsaauth AS da
# ON g.foracid = da.operacc
# WHERE ed.doccode = 'PAN'
# )
# SELECT
# ad.rm_id,
# ad.rm_name,
# ad.operacc,
# ad.foracid,
# ad.acct_name,                   /* ADDED - ACCOUNT NAME */
# ad.acct_opn_date,
# ad.deposit_amount,
# ad.deposit_period_mths,
# ad.deposit_period_days,
# ad.sol_id,
# ad.sol_desc,
# ad.scheme_code,
# ad.schm_desc,
# SUM(ad.total_tran_amt_dtt)      AS total_tran_amt_dtt,
# SUM(ad.total_flow_amt_tdt)      AS total_flow_amt_tdt,
# SUM(ad.total_flow_amt_tdt)      AS adjusted_flow_amount,
# LEAST(
# COALESCE(SUM(ad.total_tran_amt_dtt),0),
# COALESCE(SUM(ad.total_flow_amt_tdt),0)
# ) AS commission_amount,
# CASE
# WHEN ad.acct_opn_date + INTERVAL '1 year' <= DATE '2026-08-31' THEN 'YES'    // curr month end date
# ELSE 'NO'
# END AS one_year_completed,
# MAX(COALESCE(rd.referencenumber,'N/A')) AS referencenumber
# FROM account_data AS ad
# LEFT JOIN reference_data AS rd
# ON UPPER(ad.rm_id) = UPPER(rd.rm_id)
# WHERE ad.total_tran_amt_dtt > 0
# -- ADDED: SIRF RDDSA AUR DDDSA PREFIX WALE RM_ID
# AND (
#     UPPER(ad.rm_id) LIKE 'RDDSA%'
#     OR UPPER(ad.rm_id) LIKE 'DDDSA%'
# )
# GROUP BY
# ad.rm_id,
# ad.rm_name,
# ad.operacc,
# ad.foracid,
# ad.acct_name,                   /* ADDED */
# ad.acct_opn_date,
# ad.deposit_amount,
# ad.deposit_period_mths,
# ad.deposit_period_days,
# ad.sol_id,
# ad.sol_desc,
# ad.scheme_code,
# ad.schm_desc
# ORDER BY
# ad.sol_id,
# ad.rm_id,
# ad.scheme_code,
# ad.deposit_period_mths;


# """


def get_query_1(from_date=None, to_date=None):
    dates = get_commission_query_dates(from_date=from_date, to_date=to_date)

    return f"""
WITH account_data AS (
    SELECT
        d.rm_id,
        g2.emp_name AS rm_name,
        d2.operacc,
        g.cif_id,
        g.acct_opn_date,
        g.acct_cls_date,
        a2.relationshipopeningdate AS cif_id_opening_date,
        g.foracid,
        g.sol_id,
        sol.sol_desc,
        g.schm_code AS scheme_code,
        gsp.schm_desc,
        tam.deposit_period_days,
        tam.deposit_period_mths,
        tam.deposit_amount,
        g.acct_name
    FROM custom.dsamap d
    INNER JOIN tbaadm.gam g
        ON g.foracid = d.account_number
        AND g.schm_code IN (
            '2004','2005','2006','2010','2011',
            '2012','2013','2014','2015'
        )
        -- Same month me open aur close hone wale accounts exclude karne ke liye:
        AND (
            g.acct_cls_date IS NULL
            OR TO_CHAR(g.acct_opn_date, 'YYYYMM') <> TO_CHAR(g.acct_cls_date, 'YYYYMM')
        )
    LEFT JOIN tbaadm.tam tam
        ON tam.acid = g.acid
    LEFT JOIN crmuser.accounts a2
        ON g.cif_id = a2.orgkey
    LEFT JOIN tbaadm.sol sol
        ON g.sol_id = sol.sol_id
    LEFT JOIN tbaadm.gsp gsp
        ON g.schm_code = gsp.schm_code
    LEFT JOIN custom.dsaauth d2
        ON d.rm_id = d2.user_id
    LEFT JOIN tbaadm.get g2
        ON d2.user_id = g2.emp_id
),
flow_data AS (
    SELECT
        d.rm_id,
        g.foracid,
        g.schm_code,
        SUM(tdt.flow_amt) AS total_flow_amount
    FROM custom.dsamap d
    INNER JOIN tbaadm.gam g
        ON g.foracid = d.account_number
        AND g.schm_code IN (
            '2004','2005','2006','2010','2011',
            '2012','2013','2014','2015'
        )
        -- Flow data me bhi same month open-close filter
        AND (
            g.acct_cls_date IS NULL
            OR TO_CHAR(g.acct_opn_date, 'YYYYMM') <> TO_CHAR(g.acct_cls_date, 'YYYYMM')
        )
    INNER JOIN tbaadm.tdt tdt
        ON tdt.acid = g.acid
        AND tdt.flow_code = 'NI'
    WHERE tdt.flow_date BETWEEN
        -- Dynamic reporting dates (Current month start to T-1)
        DATE '{dates['current_month_start']}'
        AND DATE '{dates['present_date']}'
    GROUP BY
        d.rm_id,
        g.foracid,
        g.schm_code
    HAVING SUM(tdt.flow_amt) > 0
),
tran_data AS (
    SELECT
        d.rm_id,
        g.foracid,
        g.schm_code,
        SUM(dtt.tran_amt) AS total_tran_amt
    FROM custom.dsamap d
    INNER JOIN tbaadm.gam g
        ON g.foracid = d.account_number
        AND g.schm_code IN (
            '2004','2005','2006','2010','2011',
            '2012','2013','2014','2015'
        )
        -- Tran data me bhi same month open-close filter
        AND (
            g.acct_cls_date IS NULL
            OR TO_CHAR(g.acct_opn_date, 'YYYYMM') <> TO_CHAR(g.acct_cls_date, 'YYYYMM')
        )
    INNER JOIN tbaadm.dtt dtt
        ON dtt.acid = g.acid
        AND dtt.flow_code = 'NI'
    WHERE
        (
            (
                dtt.tran_date BETWEEN
                    DATE '{dates['current_month_start']}'
                    AND DATE '{dates['present_date']}'
                AND dtt.value_date >
                    DATE '{dates['previous_month_end']}'
            )
            OR
            (
                dtt.tran_date >
                    DATE '{dates['present_date']}'
                AND dtt.value_date BETWEEN
                    DATE '{dates['current_month_start']}'
                    AND DATE '{dates['present_date']}'
            )
            OR
            (
                dtt.value_date BETWEEN
                    DATE '{dates['current_month_start']}'
                    AND DATE '{dates['present_date']}'
                AND dtt.tran_date >
                    DATE '{dates['present_date']}'
            )
        )
    GROUP BY
        d.rm_id,
        g.foracid,
        g.schm_code
    HAVING SUM(dtt.tran_amt) > 0
),
reference_data AS (
    SELECT
        ed.referencenumber,
        da.user_id AS rm_id
    FROM crmuser.entitydocument ed
    INNER JOIN tbaadm.gam g
        ON ed.orgkey = g.cif_id
    INNER JOIN custom.dsaauth da
        ON g.foracid = da.operacc
    WHERE ed.doccode = 'PAN'
)
SELECT
    ad.rm_id,
    ad.rm_name,
    ad.operacc,
    ad.cif_id,
    ad.acct_opn_date,
    ad.acct_cls_date,                     -- (Optional: verification ke liye add kiya hai)
    ad.cif_id_opening_date,
    ad.foracid,
    ad.acct_name,
    ad.deposit_amount,
    COALESCE(fd.total_flow_amount, 0)
        AS total_flow_amount,
    CASE
        WHEN ad.scheme_code = '2004'
            THEN COALESCE(fd.total_flow_amount, 0)
        WHEN ad.scheme_code IN (
            '2005','2006','2010','2011',
            '2012','2013','2014','2015'
        )
            THEN COALESCE(fd.total_flow_amount, 0) * 3
        ELSE COALESCE(fd.total_flow_amount, 0)
    END AS adjusted_flow_amount,
    COALESCE(td.total_tran_amt, 0)
        AS total_tran_amt,
    LEAST(
        COALESCE(fd.total_flow_amount, 0),
        COALESCE(td.total_tran_amt, 0)
    ) AS commission_amount,
    CASE
        WHEN ad.acct_opn_date + INTERVAL '1 year' >=
            DATE '{dates['present_date']}'
            THEN 'YES'
        ELSE 'NO'
    END AS one_year_completed,
    ad.deposit_period_days,
    ad.deposit_period_mths,
    COALESCE(rd.referencenumber, 'N/A')
        AS referencenumber,
    ad.scheme_code,
    ad.schm_desc,
    ad.sol_id,
    ad.sol_desc
FROM account_data ad
LEFT JOIN flow_data fd
    ON ad.rm_id = fd.rm_id
    AND ad.foracid = fd.foracid
    AND ad.scheme_code = fd.schm_code
LEFT JOIN tran_data td
    ON ad.rm_id = td.rm_id
    AND ad.foracid = td.foracid
    AND ad.scheme_code = td.schm_code
LEFT JOIN reference_data rd
    ON ad.rm_id = rd.rm_id
WHERE COALESCE(td.total_tran_amt, 0) > 0
AND (
    UPPER(ad.rm_id) LIKE 'RDDSA%'
    OR UPPER(ad.rm_id) LIKE 'DDDSA%'
)
ORDER BY
    ad.foracid,
    ad.rm_id,
    ad.scheme_code;
"""


def get_query_2(from_date=None, to_date=None):
    dates = get_commission_query_dates(from_date=from_date, to_date=to_date)

    return f"""
WITH account_data AS (
    SELECT
        ds.rm_id,
        g2.emp_name AS rm_name,
        d2.operacc,
        g.foracid,
        g.acct_name,
        g.acct_opn_date,
        tam.deposit_amount,
        tam.deposit_period_mths,
        tam.deposit_period_days,
        COUNT(DISTINCT g.acid) AS count_acid_gam,
        SUM(dtt.tran_amt) AS total_tran_amt_dtt,
        SUM(tdt.flow_amt) AS total_flow_amt_tdt,
        g.sol_id,
        sol.sol_desc,
        g.schm_code AS scheme_code,
        gsp.schm_desc
    FROM custom.dsamap AS ds
    LEFT JOIN tbaadm.gam AS g
        ON g.foracid = ds.account_number
        AND g.schm_code IN (
            '2001','2002','2003',
            '2018','2019','2020','2021','2022',
            '2023','2024','2025','2026','2027',
            '2028','2029','2030','2031','2032',
            '2033','2034','2035',
            '2101','2102','2103','2104','2105','2106',
            '2201','2202','2203',
            '9001','9002'
        )
        AND g.acct_opn_date BETWEEN
            -- Dynamic reporting dates (Current month start to T-1)
            DATE '{dates['current_month_start']}'
            AND DATE '{dates['present_date']}'
        AND g.acct_cls_flg = 'N'
    LEFT JOIN tbaadm.tam AS tam
        ON tam.acid = g.acid
    LEFT JOIN tbaadm.dtt AS dtt
        ON dtt.acid = g.acid
        AND dtt.flow_code = 'PI'
        AND dtt.tran_date BETWEEN
            DATE '{dates['current_month_start']}'
            AND DATE '{dates['present_date']}'
        AND NOT (
            dtt.value_date >=
                DATE '{dates['previous_month_start']}'
            AND dtt.value_date <
                DATE '{dates['current_month_start']}'
        )
    LEFT JOIN tbaadm.tdt AS tdt
        ON tdt.acid = g.acid
        AND tdt.flow_code = 'PI'
        AND tdt.flow_date BETWEEN
            DATE '{dates['current_month_start']}'
            AND DATE '{dates['present_date']}'
    LEFT JOIN custom.dsaauth AS d2
        ON UPPER(ds.rm_id) = UPPER(d2.user_id)
    LEFT JOIN tbaadm.get AS g2
        ON d2.user_id = g2.emp_id
    LEFT JOIN tbaadm.sol AS sol
        ON g.sol_id = sol.sol_id
    LEFT JOIN tbaadm.gsp AS gsp
        ON gsp.schm_code = g.schm_code
    GROUP BY
        ds.rm_id,
        g2.emp_name,
        d2.operacc,
        g.foracid,
        g.acct_name,
        g.acct_opn_date,
        tam.deposit_amount,
        tam.deposit_period_mths,
        tam.deposit_period_days,
        g.sol_id,
        sol.sol_desc,
        g.schm_code,
        gsp.schm_desc
),
reference_data AS (
    SELECT
        ed.referencenumber,
        da.user_id AS rm_id
    FROM crmuser.entitydocument AS ed
    JOIN tbaadm.gam AS g
        ON ed.orgkey = g.cif_id
    JOIN custom.dsaauth AS da
        ON g.foracid = da.operacc
    WHERE ed.doccode = 'PAN'
)
SELECT
    ad.rm_id,
    ad.rm_name,
    ad.operacc,
    ad.foracid,
    ad.acct_name,
    ad.acct_opn_date,
    ad.deposit_amount,
    ad.deposit_period_mths,
    ad.deposit_period_days,
    ad.sol_id,
    ad.sol_desc,
    ad.scheme_code,
    ad.schm_desc,
    SUM(ad.total_tran_amt_dtt)
        AS total_tran_amt_dtt,
    SUM(ad.total_flow_amt_tdt)
        AS total_flow_amt_tdt,
    SUM(ad.total_flow_amt_tdt)
        AS adjusted_flow_amount,
    LEAST(
        COALESCE(SUM(ad.total_tran_amt_dtt), 0),
        COALESCE(SUM(ad.total_flow_amt_tdt), 0)
    ) AS commission_amount,
    CASE
        WHEN ad.acct_opn_date + INTERVAL '1 year' <=
            DATE '{dates['present_date']}'
            THEN 'YES'
        ELSE 'NO'
    END AS one_year_completed,
    MAX(
        COALESCE(rd.referencenumber, 'N/A')
    ) AS referencenumber
FROM account_data AS ad
LEFT JOIN reference_data AS rd
    ON UPPER(ad.rm_id) = UPPER(rd.rm_id)
WHERE ad.total_tran_amt_dtt > 0
AND (
    UPPER(ad.rm_id) LIKE 'RDDSA%'
    OR UPPER(ad.rm_id) LIKE 'DDDSA%'
)
GROUP BY
    ad.rm_id,
    ad.rm_name,
    ad.operacc,
    ad.foracid,
    ad.acct_name,
    ad.acct_opn_date,
    ad.deposit_amount,
    ad.deposit_period_mths,
    ad.deposit_period_days,
    ad.sol_id,
    ad.sol_desc,
    ad.scheme_code,
    ad.schm_desc
ORDER BY
    ad.sol_id,
    ad.rm_id,
    ad.scheme_code,
    ad.deposit_period_mths
"""


def _safe_int(value):
    if value in (None, "", "N/A"):
        return None

    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return None


def _safe_str(value):
    if value is None:
        return None

    return str(value).strip()


def _get_demand_settings():
    """
    Get demand multiplier and selected scheme codes from Commission Settings.
    """
    try:
        settings = frappe.get_single("Commission Settings")
        multiplier = getattr(settings, "demand_multiplier", None)
        multiplier = float(multiplier) if multiplier not in (None, "") else 3.0
        raw_schemes = getattr(
            settings, "demand_multiplier_scheme_codes", None) or ""
        schemes = {
            s.strip()
            for line in str(raw_schemes).splitlines()
            for s in line.split(",")
            if s.strip()
        }
        return multiplier, schemes
    except Exception:
        return 3.0, set()


def _calculate_demand(total_flow_amount, scheme_code):
    """
    Calculate demand with multiplier applied if scheme_code matches selected schemes in Commission Settings.
    """
    demand = _safe_int(total_flow_amount)
    if demand is None:
        return None

    multiplier, schemes = _get_demand_settings()
    curr_scheme = str(scheme_code).strip() if scheme_code is not None else ""

    if schemes and curr_scheme in schemes:
        return int(round(demand * multiplier))

    return demand


def _get_eligible_amount_from_setting(demand, collection, eligible_setting=None):
    """
    Return eligible_amount based on the 'Eligible Amount Setting'
    configured in Commission Settings.

    Options:
        Whichever is minimum demand or collection  -> min(demand, collection)
        Whichever is maximum demand or collection  -> max(demand, collection)

    If either value is None the other is returned as-is.
    If both are None, None is returned.
    """
    if eligible_setting is None:
        try:
            settings = frappe.get_single("Commission Settings")
            setting = (
                getattr(settings, "eligible_amount_setting", None)
                or "Whichever is minimum demand or collection"
            )
        except Exception:
            setting = "Whichever is minimum demand or collection"
    else:
        setting = eligible_setting

    demand_int = _safe_int(demand)
    collection_int = _safe_int(collection)

    if demand_int is None and collection_int is None:
        return None

    if demand_int is None:
        return collection_int

    if collection_int is None:
        return demand_int

    if setting == "Whichever is maximum demand or collection":
        return max(demand_int, collection_int)

    # Default: minimum
    return min(demand_int, collection_int)


COMMISSION_BULK_FIELDS = [
    "name",
    "creation",
    "modified",
    "modified_by",
    "owner",
    "docstatus",
    "idx",
    "date",
    "agent_code",
    "agent_name",
    "customer_account_number",
    "customer_account_name",
    "deposit_amount",
    "tenure_months",
    "tenure_days",
    "demand",
    "collection",
    "eligible_amount",
    "account_opening_date",
    "remarks",
    "pan_card",
    "scheme_code",
    "scheme_description",
    "sol_id",
    "sol_description",
]


def _sync_agent_fetch_from_fields():
    """
    Simulate Frappe ORM fetch_from across all inserted Commission records
    via single lightning-fast bulk UPDATE JOINs.
    """
    frappe.db.sql("""
        UPDATE `tabCommission` c
        INNER JOIN `tabAgent` a ON c.agent_code = a.name
        SET
            c.agent_operative_account = COALESCE(a.agent_operative_account, '0'),
            c.agent_saving_account    = COALESCE(a.agent_saving_account, '0'),
            c.agent_security_account  = COALESCE(a.agent_security_account, '0'),
            c.cif                     = COALESCE(a.cif, '0'),
            c.pan_status              = COALESCE(a.pan_status, '0')
        WHERE
            c.agent_code IS NOT NULL
            AND (
                c.agent_operative_account IS NULL
                OR c.cif IS NULL
                OR c.pan_status IS NULL
                OR c.agent_saving_account IS NULL
                OR c.agent_security_account IS NULL
            )
    """)

    frappe.db.sql("""
        UPDATE `tabCommission` c
        INNER JOIN `tabProduct` p ON c.scheme_code = p.product_code
        SET
            c.group_name = p.group_name
        WHERE
            c.scheme_code IS NOT NULL
            AND (c.group_name IS NULL OR c.group_name = '')
    """)
    frappe.db.commit()


def _get_existing_commission_map(from_date=None):
    """
    Get mapping of (customer_account_number_scheme_code) -> name created in the targeted period.
    Allows lightning-fast O(1) distinction between INSERT and UPDATE.
    """
    if from_date:
        start_date = frappe.utils.getdate(from_date).strftime('%Y-%m-01')
    else:
        start_date = None

    if start_date:
        rows = frappe.db.sql("""
            SELECT name, CONCAT(COALESCE(customer_account_number, ''), '_', COALESCE(scheme_code, '')) as `key`
            FROM `tabCommission`
            WHERE creation >= %(start_date)s
        """, {"start_date": start_date}, as_dict=True)
    else:
        rows = frappe.db.sql("""
            SELECT name, CONCAT(COALESCE(customer_account_number, ''), '_', COALESCE(scheme_code, '')) as `key`
            FROM `tabCommission`
            WHERE creation >= DATE_FORMAT(NOW(), '%%Y-%%m-01')
        """, as_dict=True)
    return {r["key"]: r["name"] for r in rows if r.get("key")}


def _build_commission_tuple(row, is_query_2, now_ts, doc_name=None, eligible_setting=None, sync_date=None):
    collection_val = row.get(
        "total_tran_amt_dtt") if is_query_2 else row.get("total_tran_amt")

    demand_val = _safe_int(row.get("adjusted_flow_amount")) or 0
    collection_int = _safe_int(collection_val) or 0

    eligible_amount = _get_eligible_amount_from_setting(
        demand_val,
        collection_int,
        eligible_setting=eligible_setting,
    )

    return (
        doc_name or frappe.generate_hash(length=10),
        now_ts,
        now_ts,
        "Administrator",
        "Administrator",
        0,
        0,
        sync_date,
        _safe_str(row.get("rm_id")),
        _safe_str(row.get("rm_name")),
        _safe_str(row.get("foracid")),
        _safe_str(row.get("acct_name")),
        _safe_int(row.get("deposit_amount")) or 0,
        _safe_int(row.get("deposit_period_mths")) or 0,
        _safe_int(row.get("deposit_period_days")) or 0,
        demand_val,
        collection_int,
        eligible_amount,
        row.get("acct_opn_date"),
        _safe_str(row.get("one_year_completed")),
        _safe_str(row.get("referencenumber")),
        _safe_int(row.get("scheme_code")) or 0,
        _safe_str(row.get("schm_desc")),
        _safe_int(row.get("sol_id")) or 0,
        _safe_str(row.get("sol_desc")),
    )


def _bulk_update_commissions(update_tuples, chunk_size=2000):
    """
    Direct batch update of existing Commission records using cursor.executemany without any temporary tables.
    """
    if not update_tuples:
        return

    update_sql = """
        UPDATE `tabCommission`
        SET
            modified = %s,
            `date` = %s,
            agent_code = %s,
            agent_name = %s,
            customer_account_number = %s,
            customer_account_name = %s,
            deposit_amount = %s,
            tenure_months = %s,
            tenure_days = %s,
            demand = %s,
            collection = %s,
            eligible_amount = %s,
            account_opening_date = %s,
            remarks = %s,
            pan_card = %s,
            scheme_code = %s,
            scheme_description = %s,
            sol_id = %s,
            sol_description = %s
        WHERE name = %s
    """

    cursor = frappe.db._cursor
    for i in range(0, len(update_tuples), chunk_size):
        chunk = update_tuples[i:i + chunk_size]
        params = [
            (
                t[2],   # modified
                t[7],   # date
                t[8],   # agent_code
                t[9],   # agent_name
                t[10],  # customer_account_number
                t[11],  # customer_account_name
                t[12],  # deposit_amount
                t[13],  # tenure_months
                t[14],  # tenure_days
                t[15],  # demand
                t[16],  # collection
                t[17],  # eligible_amount
                t[18],  # account_opening_date
                t[19],  # remarks
                t[20],  # pan_card
                t[21],  # scheme_code
                t[22],  # scheme_description
                t[23],  # sol_id
                t[24],  # sol_description
                t[0],   # name (WHERE clause)
            )
            for t in chunk
        ]
        cursor.executemany(update_sql, params)
        frappe.db.commit()


def _create_commission_from_query_1(row, commit=True, sync_date=None):
    agent_code = _safe_str(row.get("rm_id")) or "0"

    doc = frappe.get_doc({
        "doctype": "Commission",
        "date": sync_date,
        "agent_code": agent_code,
        "agent_name": _safe_str(row.get("rm_name")) or "0",

        "customer_account_number": (
            _safe_str(row.get("foracid")) or "0"
        ),
        "customer_account_name": (
            _safe_str(row.get("acct_name")) or "0"
        ),
        "deposit_amount": _safe_int(
            row.get("deposit_amount")
        ),

        "tenure_months": _safe_int(
            row.get("deposit_period_mths")
        ),
        "tenure_days": _safe_int(
            row.get("deposit_period_days")
        ),

        "demand": _calculate_demand(
            row.get("total_flow_amount"),
            row.get("scheme_code"),
        ),
        "collection": _safe_int(
            row.get("total_tran_amt")
        ),

        "eligible_amount": _get_eligible_amount_from_setting(
            _calculate_demand(
                row.get("total_flow_amount"),
                row.get("scheme_code"),
            ),
            _safe_int(row.get("total_tran_amt")),
        ),
        "account_opening_date": row.get(
            "acct_opn_date"
        ),
        "remarks": (
            _safe_str(row.get("one_year_completed"))
            or "0"
        ),

        "pan_card": (
            _safe_str(row.get("referencenumber"))
            or "0"
        ),
        "scheme_code": (
            _safe_str(row.get("scheme_code"))
            or "0"
        ),
        "scheme_description": (
            _safe_str(row.get("schm_desc"))
            or "0"
        ),
        "sol_id": (
            _safe_str(row.get("sol_id"))
            or "0"
        ),
        "sol_description": (
            _safe_str(row.get("sol_desc"))
            or "0"
        ),
    })

    doc.insert(ignore_permissions=True)
    if commit:
        frappe.db.commit()

    return doc.name


def _create_commission_from_query_2(row, commit=True, sync_date=None):
    agent_code = _safe_str(row.get("rm_id")) or "0"

    doc = frappe.get_doc({
        "doctype": "Commission",
        "date": sync_date,
        "agent_code": agent_code,
        "agent_name": _safe_str(row.get("rm_name")) or "0",

        "customer_account_number": (
            _safe_str(row.get("foracid")) or "0"
        ),
        "customer_account_name": (
            _safe_str(row.get("acct_name")) or "0"
        ),
        "deposit_amount": _safe_int(
            row.get("deposit_amount")
        ),

        "tenure_months": _safe_int(
            row.get("deposit_period_mths")
        ),
        "tenure_days": _safe_int(
            row.get("deposit_period_days")
        ),

        "demand": _calculate_demand(
            row.get("total_flow_amount"),
            row.get("scheme_code"),
        ),
        "collection": _safe_int(
            row.get("total_tran_amt_dtt")
        ),

        "eligible_amount": _get_eligible_amount_from_setting(
            _calculate_demand(
                row.get("total_flow_amount"),
                row.get("scheme_code"),
            ),
            _safe_int(row.get("total_tran_amt_dtt")),
        ),
        "account_opening_date": row.get(
            "acct_opn_date"
        ),
        "remarks": (
            _safe_str(row.get("one_year_completed"))
            or "0"
        ),

        "pan_card": (
            _safe_str(row.get("referencenumber"))
            or "0"
        ),
        "scheme_code": (
            _safe_str(row.get("scheme_code"))
            or "0"
        ),
        "scheme_description": (
            _safe_str(row.get("schm_desc"))
            or "0"
        ),
        "sol_id": (
            _safe_str(row.get("sol_id"))
            or "0"
        ),
        "sol_description": (
            _safe_str(row.get("sol_desc"))
            or "0"
        ),
    })

    doc.insert(ignore_permissions=True)
    if commit:
        frappe.db.commit()

    return doc.name


def _run_query(connection, query):
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(query)
        return cursor.fetchall()


@frappe.whitelist()
def fetch_and_create_commission(from_date=None, to_date=None):
    """
    Execute Query 2 first, then Query 1.
    Uses bulk_insert for lightning-fast performance across 80,000+ records.
    Filters existing accounts created in the current month to prevent duplicates on daily runs.
    """
    if not frappe.flags.in_scheduler and not frappe.flags.in_test:
        frappe.only_for(("System Manager",))

    if to_date:
        max_allowed_date = frappe.utils.add_days(frappe.utils.today(), -1)
        if str(to_date) > str(max_allowed_date):
            frappe.throw(
                _("To Date cannot be today or a future date. Maximum allowed date is {0} (T-1).").format(max_allowed_date)
            )
        if from_date and str(from_date) > str(to_date):
            frappe.throw(_("From Date cannot be after To Date."))

    conn = None
    errors = []

    try:
        conn = db_connection()

        now_ts = now_datetime()
        existing_map = _get_existing_commission_map(from_date=from_date)
        processed_keys = set()

        try:
            settings_doc = frappe.get_single("Commission Settings")
            eligible_setting = (
                getattr(settings_doc, "eligible_amount_setting", None)
                or "Whichever is minimum demand or collection"
            )
        except Exception:
            eligible_setting = "Whichever is minimum demand or collection"

        # Fetch rows from external Postgres immediately while connection is fresh
        query_2_rows = _run_query(
            conn,
            get_query_2(from_date=from_date, to_date=to_date),
        )

        query_1_rows = _run_query(
            conn,
            get_query_1(from_date=from_date, to_date=to_date),
        )

        # Close Postgres connection early to avoid holding standby slots
        conn.close()
        conn = None

        insert_tuples = []
        update_tuples = []

        # Determine effective sync date (custom to_date, or T-1 report_date)
        query_dates = get_commission_query_dates(from_date=from_date, to_date=to_date)
        sync_date = query_dates.get("present_date")

        # Process Query 2
        for row in query_2_rows:
            key = f"{row.get('foracid') or ''}_{row.get('scheme_code') or ''}"
            if key in processed_keys:
                continue
            processed_keys.add(key)

            existing_name = existing_map.get(key)
            if existing_name:
                update_tuples.append(_build_commission_tuple(
                    row, True, now_ts, doc_name=existing_name, eligible_setting=eligible_setting, sync_date=sync_date))
            else:
                insert_tuples.append(
                    _build_commission_tuple(row, True, now_ts, eligible_setting=eligible_setting, sync_date=sync_date))

        # Process Query 1
        for row in query_1_rows:
            key = f"{row.get('foracid') or ''}_{row.get('scheme_code') or ''}"
            if key in processed_keys:
                continue
            processed_keys.add(key)

            existing_name = existing_map.get(key)
            if existing_name:
                update_tuples.append(_build_commission_tuple(
                    row, False, now_ts, doc_name=existing_name, eligible_setting=eligible_setting, sync_date=sync_date))
            else:
                insert_tuples.append(
                    _build_commission_tuple(row, False, now_ts, eligible_setting=eligible_setting, sync_date=sync_date))

        # Execute Bulk Inserts
        if insert_tuples:
            frappe.db.bulk_insert(
                "Commission", COMMISSION_BULK_FIELDS, insert_tuples, chunk_size=5000)
            frappe.db.commit()

        # Execute Bulk Updates
        if update_tuples:
            _bulk_update_commissions(update_tuples, chunk_size=5000)

        total_processed = len(insert_tuples) + len(update_tuples)
        if total_processed > 0:
            _sync_agent_fetch_from_fields()

        return {
            "status": "completed",
            "query_1_fetched": len(query_1_rows),
            "query_2_fetched": len(query_2_rows),
            "inserted_count": len(insert_tuples),
            "updated_count": len(update_tuples),
            "total_processed": total_processed,
            "error_count": 0,
            "errors": [],
        }

    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            frappe.get_traceback(),
            "Commission Import Failed",
        )
        raise

    finally:
        if conn:
            conn.close()


@frappe.whitelist()
def run_fetch_and_create_commission_with_progress(limit=None, from_date=None, to_date=None):
    """
    Execute Query 1 and Query 2 with terminal progress using high-speed bulk batches.
    """
    frappe.only_for(("System Manager",))

    conn = None
    try:
        if limit is not None and str(limit).strip():
            limit = int(limit)
            if limit <= 0:
                frappe.throw(_("Limit must be greater than 0"))
        else:
            limit = None

        conn = db_connection()

        query_1_rows = _run_query(conn, get_query_1(from_date=from_date, to_date=to_date))
        query_2_rows = _run_query(conn, get_query_2(from_date=from_date, to_date=to_date))

        if limit:
            if len(query_2_rows) >= limit:
                query_2_rows = query_2_rows[:limit]
                query_1_rows = []
            else:
                rem = limit - len(query_2_rows)
                query_1_rows = query_1_rows[:rem]

        now_ts = now_datetime()
        existing_map = _get_existing_commission_map(from_date=from_date)
        processed_keys = set()

        total_to_process = len(query_2_rows) + len(query_1_rows)
        progress = tqdm(total=total_to_process,
                        desc="Upserting Commission Docs", unit="doc")

        insert_tuples = []
        update_tuples = []

        query_dates = get_commission_query_dates(from_date=from_date, to_date=to_date)
        sync_date = query_dates.get("present_date")

        try:
            # Process Query 2
            for row in query_2_rows:
                key = f"{row.get('foracid') or ''}_{row.get('scheme_code') or ''}"
                if key in processed_keys:
                    progress.update(1)
                    continue
                processed_keys.add(key)

                existing_name = existing_map.get(key)
                if existing_name:
                    update_tuples.append(_build_commission_tuple(
                        row, True, now_ts, doc_name=existing_name, sync_date=sync_date))
                else:
                    insert_tuples.append(
                        _build_commission_tuple(row, True, now_ts, sync_date=sync_date))
                progress.update(1)

            # Process Query 1
            for row in query_1_rows:
                key = f"{row.get('foracid') or ''}_{row.get('scheme_code') or ''}"
                if key in processed_keys:
                    progress.update(1)
                    continue
                processed_keys.add(key)

                existing_name = existing_map.get(key)
                if existing_name:
                    update_tuples.append(_build_commission_tuple(
                        row, False, now_ts, doc_name=existing_name, sync_date=sync_date))
                else:
                    insert_tuples.append(
                        _build_commission_tuple(row, False, now_ts, sync_date=sync_date))
                progress.update(1)

            if insert_tuples:
                frappe.db.bulk_insert(
                    "Commission", COMMISSION_BULK_FIELDS, insert_tuples, chunk_size=5000)
                frappe.db.commit()

            if update_tuples:
                _bulk_update_commissions(update_tuples, chunk_size=5000)

            _sync_agent_fetch_from_fields()

        finally:
            progress.close()

        if total_to_process > 0:
            _sync_agent_fetch_from_fields()

        print("\nCommission Fetch Completed")
        print(f"Query 1 Docs Created: {len(query_1_rows)}")
        print(f"Query 2 Docs Created: {len(query_2_rows)}")
        print(f"Total Docs Created: {total_to_process}")

        return {
            "status": "completed",
            "limit": limit,
            "query_1_fetched": len(query_1_rows),
            "query_2_fetched": len(query_2_rows),
            "query_1_created": len(query_1_rows),
            "query_2_created": len(query_2_rows),
            "inserted_count": total_to_process,
            "error_count": 0,
            "errors": [],
        }

    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Commission Import Failed")
        raise

    finally:
        if conn:
            conn.close()


@frappe.whitelist()
def debug_fetch_commission_data():
    frappe.only_for(("System Manager",))

    conn = None

    try:
        conn = db_connection()

        query_1_rows = _run_query(
            conn,
            get_query_1(),
        )
        query_2_rows = _run_query(
            conn,
            get_query_2(),
        )

        print("\n===== COMMISSION DEBUG FETCH =====")
        print(f"QUERY 1 ROW COUNT: {len(query_1_rows)}")
        print(f"QUERY 2 ROW COUNT: {len(query_2_rows)}")

        if query_1_rows:
            print("QUERY 1 FIRST ROW:")
            print(query_1_rows[0])
        else:
            print("QUERY 1 returned no rows")

        if query_2_rows:
            print("QUERY 2 FIRST ROW:")
            print(query_2_rows[0])
        else:
            print("QUERY 2 returned no rows")

        return {
            "query_1_count": len(query_1_rows),
            "query_2_count": len(query_2_rows),
            "query_1_first_row": query_1_rows[0] if query_1_rows else None,
            "query_2_first_row": query_2_rows[0] if query_2_rows else None,
        }

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "Commission Debug Fetch Failed",
        )
        raise

    finally:
        if conn:
            conn.close()


@frappe.whitelist()
def debug_create_one_commission():
    frappe.only_for(("System Manager",))

    conn = None

    try:
        conn = db_connection()
        query_1_rows = _run_query(
            conn,
            get_query_1(),
        )

        if not query_1_rows:
            return {"status": "no_data"}

        row = query_1_rows[0]
        docname = _create_commission_from_query_1(row)

        return {
            "status": "success",
            "docname": docname,
            "sample_row": row,
        }

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "Commission Debug Create One Failed",
        )
        raise

    finally:
        if conn:
            conn.close()


@frappe.whitelist()
def truncate_commission_and_payments(clear_commission=1, clear_payments=1):
    """
    Clear Commission (including items) and/or Commission Payment records based on selection.
    Restricted to System Manager.
    """
    frappe.only_for(("System Manager",))

    cleared = []
    clear_commission = cint(clear_commission)
    clear_payments = cint(clear_payments)

    if clear_commission:
        frappe.db.sql("TRUNCATE TABLE `tabCommission Item`")
        frappe.db.sql("TRUNCATE TABLE `tabCommission`")
        cleared.append("Commission & Items")

    if clear_payments:
        frappe.db.sql("TRUNCATE TABLE `tabCommission Payment`")
        cleared.append("Commission Payment")

    frappe.db.commit()

    if not cleared:
        return {"status": "none", "message": _("No tables were selected to clear.")}

    return {"status": "success", "message": _("Successfully cleared: {0}").format(", ".join(cleared))}


def _get_deferred_product(product_name):
    """
    Load Product including its deferred child table.
    frappe.db.get_value does not provide the child rows,
    so Deferred needs the full Product document.
    """
    product_doc = frappe.get_doc("Product", product_name)

    if product_doc.commission_type != "Deferred":
        frappe.throw(
            _("Product {0} is not configured for Deferred commission").format(
                product_name
            )
        )

    if not product_doc.deferred_commission_schedule:
        frappe.throw(
            _("Deferred Commission Schedule is missing in Product: {0}").format(
                product_name
            )
        )

    return product_doc


def _get_valid_deferred_schedule_rows(product_doc):
    """
    Read, validate, and sort enabled Product deferred schedule rows.
    """
    schedule_rows = []
    used_years = set()

    for row in product_doc.deferred_commission_schedule:
        if not row.enabled:
            continue

        year_no = cint(row.year_no)
        rate = flt(row.commission_rate)

        if year_no <= 0:
            frappe.throw(
                _("Deferred Year No must be greater than 0 in Product: {0}").format(
                    product_doc.name
                )
            )

        if year_no in used_years:
            frappe.throw(
                _("Duplicate Deferred Year No {0} in Product: {1}").format(
                    year_no,
                    product_doc.name
                )
            )

        if rate < 0:
            frappe.throw(
                _("Deferred commission rate cannot be negative for Year {0}").format(
                    year_no
                )
            )

        used_years.add(year_no)

        schedule_rows.append({
            "year_no": year_no,
            "rate": rate,
            "remarks": _safe_str(row.remarks),
        })

    if not schedule_rows:
        frappe.throw(
            _("No enabled deferred commission rows found in Product: {0}").format(
                product_doc.name
            )
        )

    return sorted(schedule_rows, key=lambda item: item["year_no"])


# def _create_deferred_commission_schedule(commission_doc, product_doc, eligible_amount):
#     """
#     Create deferred payout schedule rows in the current Commission document.

#     Example:
#     Commission document created on 2026-08-19:
#     Year 1 due: 2026-09-01
#     Year 2 due: 2027-09-01
#     Year 3 due: 2028-09-01
#     """
#     commission_meta = frappe.get_meta("Commission")

#     if not commission_meta.has_field("deferred_commission_details"):
#         frappe.throw(
#             _("Commission child table field 'deferred_commission_details' is missing")
#         )

#     if commission_doc.deferred_commission_details:
#         frappe.throw(
#             _("Deferred schedule already exists for Commission record: {0}").format(
#                 commission_doc.name
#             )
#         )

#     schedule_rows = _get_valid_deferred_schedule_rows(product_doc)

#     source_date = getdate(commission_doc.creation)

#     # First day of the next calendar month.
#     first_due_date = add_to_date(
#         source_date.replace(day=1),
#         months=1,
#         as_string=True,
#     )

#     total_commission = 0
#     total_rate = 0

#     for schedule in schedule_rows:
#         year_no = schedule["year_no"]
#         rate = schedule["rate"]

#         # gross_commission = (eligible_amount * rate) / 100
#         # tds = gross_commission * 0.02
#         # security_deposit = gross_commission * 0.10
#         # netpay = gross_commission - (tds + security_deposit)

#         gross_commission = (
#             eligible_amount * rate
#         ) / 100

#         financial_values = (
#             _calculate_commission_financial_values(
#                 commission_amount=gross_commission,
#                 eligible_amount=eligible_amount,
#                 pan_status=commission_doc.pan_status,
#             )
#         )

#         gross_commission = flt(
#             financial_values["commission_amount"]
#         )

#         tds = flt(
#             financial_values["tds"]
#         )

#         security_deposit = flt(
#             financial_values["security_deposit"]
#         )

#         netpay = flt(
#             financial_values["netpay"]
#         )

#         due_date = add_to_date(
#             first_due_date,
#             years=year_no - 1,
#             as_string=True,
#         )

#         commission_doc.append(
#             "deferred_commission_details",
#             {
#                 "year_no": year_no,
#                 "commission_rate": rate,
#                 "eligible_amount": eligible_amount,
#                 "gross_commission": gross_commission,
#                 "due_date": due_date,
#                 "status": "Pending",
#                 "tds": tds,
#                 "security_deposit": security_deposit,
#                 "netpay": netpay,
#                 "remarks": schedule["remarks"],
#             },
#         )

#         total_commission += gross_commission
#         total_rate += rate

#     return {
#         "total_commission": total_commission,
#         "total_rate": total_rate,
#         "first_due_date": first_due_date,
#         "schedule_count": len(schedule_rows),
#     }


def _create_deferred_commission_schedule(
    commission_doc,
    product_doc,
    eligible_amount,
):
    """
    Create deferred payout schedule rows in Commission Item.

    Example:
    Commission created on 2026-08-19:
    Year 1 due: 2026-09-01
    Year 2 due: 2027-09-01
    Year 3 due: 2028-09-01
    """
    commission_meta = frappe.get_meta("Commission")

    if not commission_meta.has_field("commission_items"):
        frappe.throw(
            _("Commission child table field 'commission_items' is missing")
        )

    if commission_doc.commission_items:
        frappe.throw(
            _("Commission Item rows already exist for Commission record: {0}").format(
                commission_doc.name
            )
        )

    schedule_rows = _get_valid_deferred_schedule_rows(product_doc)

    source_date = getdate(commission_doc.creation)

    first_due_date = add_to_date(
        source_date.replace(day=1),
        months=1,
        as_string=True,
    )

    total_commission = 0
    total_rate = 0

    for schedule in schedule_rows:
        year_no = schedule["year_no"]
        rate = schedule["rate"]

        gross_commission = (
            eligible_amount * rate
        ) / 100

        financial_values = (
            _calculate_commission_financial_values(
                commission_amount=gross_commission,
                eligible_amount=eligible_amount,
                pan_status=commission_doc.pan_status,
            )
        )

        gross_commission = flt(
            financial_values["commission_amount"]
        )

        tds = flt(
            financial_values["tds"]
        )

        security_deposit = flt(
            financial_values["security_deposit"]
        )

        netpay = flt(
            financial_values["netpay"]
        )

        due_date = add_to_date(
            first_due_date,
            years=year_no - 1,
            as_string=True,
        )

        commission_doc.append(
            "commission_items",
            {
                "commission_type": "Deferred",
                "year_no": year_no,
                "commission_rate": rate,
                "eligible_amount": eligible_amount,
                "gross_commission": gross_commission,
                "due_date": due_date,
                "status": "Pending",
                "tds": tds,
                "security_deposit": security_deposit,
                "netpay": netpay,
                "remarks": schedule["remarks"],
            },
        )

        total_commission += gross_commission
        total_rate += rate

    return {
        "total_commission": total_commission,
        "total_rate": total_rate,
        "first_due_date": first_due_date,
        "schedule_count": len(schedule_rows),
    }


def _create_normal_commission_item(
    commission_doc,
    commission_type,
    rate,
    eligible_amount,
    commission_amount,
    tds,
    security_deposit,
    netpay,
):
    """
    Create one Commission Item row for non-Deferred commission types.

    This stores the same calculated parent values in the child table.
    It does not create an additional Commission Payment.
    """
    commission_meta = frappe.get_meta("Commission")

    if not commission_meta.has_field("commission_items"):
        frappe.throw(
            _("Commission child table field 'commission_items' is missing")
        )

    commission_doc.append(
        "commission_items",
        {
            "commission_type": "Normal",
            "year_no": 1,
            "commission_rate": flt(rate),
            "eligible_amount": flt(eligible_amount),
            "gross_commission": flt(commission_amount),
            "due_date": getdate(commission_doc.creation),
            "status": "Pending",
            "tds": flt(tds),
            "security_deposit": flt(security_deposit),
            "netpay": flt(netpay),
            "remarks": commission_type,
        },
    )


# def _update_agent_deduction_and_final_net_pay(agent_code):
#     """
#     Update deduction and final_net_pay in all Commission records
#     belonging to the same agent.

#     Rule:
#     - agent_total_netpay = sum of all active Commission.netpay values
#     - if agent_total_netpay > 1000:
#         deduction = 150
#         final_net_pay = agent_total_netpay - 150
#     - otherwise:
#         deduction = 0
#         final_net_pay = agent_total_netpay
#     """

#     if not agent_code:
#         return {
#             "agent_code": None,
#             "agent_total_netpay": 0,
#             "deduction": 0,
#             "final_net_pay": 0,
#         }

#     agent_code = str(agent_code).strip()

#     result = frappe.db.sql(
#         """
#         SELECT
#             COALESCE(
#                 SUM(
#                     CAST(NULLIF(TRIM(netpay), '') AS DECIMAL(18, 2))
#                 ),
#                 0
#             ) AS agent_total_netpay
#         FROM `tabCommission`
#         WHERE agent_code = %s
#         AND docstatus < 2
#         """,
#         (agent_code,),
#         as_dict=True,
#     )

#     agent_total_netpay = (
#         flt(result[0].agent_total_netpay)
#         if result and result[0].agent_total_netpay is not None
#         else 0
#     )

#     deduction = 150 if agent_total_netpay > 1000 else 0
#     final_net_pay = agent_total_netpay - deduction

#     frappe.db.sql(
#         """
#         UPDATE `tabCommission`
#         SET
#             deduction = %s,
#             final_net_pay = %s
#         WHERE agent_code = %s
#         AND docstatus < 2
#         """,
#         (
#             deduction,
#             final_net_pay,
#             agent_code,
#         ),
#     )

#     return {
#         "agent_code": agent_code,
#         "agent_total_netpay": agent_total_netpay,
#         "deduction": deduction,
#         "final_net_pay": final_net_pay,
#     }


def _calculate_agent_deduction(
    agent_total_netpay,
    calculation_settings,
):
    """
    Calculate agent deduction from Commission Settings.

    Supported types:
        Amount Above Limit
        Percentage Above Limit
        Fixed Amount
        Percentage Of Total
    """
    if not calculation_settings[
        "enable_agent_deduction"
    ]:
        return Decimal("0"), _decimal_amount(
            agent_total_netpay
        )

    total_netpay = _decimal_amount(
        agent_total_netpay
    )

    deduction_type = calculation_settings[
        "agent_deduction_type"
    ]

    deduction_limit = _decimal_amount(
        calculation_settings[
            "agent_deduction_limit"
        ]
    )

    deduction_amount = _decimal_amount(
        calculation_settings[
            "agent_deduction_amount"
        ]
    )

    deduction_percentage = _decimal_amount(
        calculation_settings[
            "agent_deduction_percentage"
        ]
    )

    if deduction_type == "Fixed Amount":
        deduction = deduction_amount

    elif deduction_type == "Percentage Of Total":
        deduction = (
            total_netpay
            * deduction_percentage
            / Decimal("100")
        )

    elif deduction_type == "Percentage Above Limit":
        excess = max(
            total_netpay - deduction_limit,
            Decimal("0"),
        )

        deduction = (
            excess
            * deduction_percentage
            / Decimal("100")
        )

    else:
        # Amount Above Limit
        deduction = (
            deduction_amount
            if total_netpay > deduction_limit
            else Decimal("0")
        )

    maximum_deduction = calculation_settings[
        "agent_deduction_maximum"
    ]

    if maximum_deduction is not None:
        deduction = min(
            deduction,
            _decimal_amount(maximum_deduction),
        )

    deduction = _round_calculation_amount(
        deduction,
        calculation_settings,
    )

    if calculation_settings[
        "agent_deduction_operation"
    ] == "Add":
        final_netpay = (
            total_netpay + deduction
        )
    else:
        final_netpay = (
            total_netpay - deduction
        )

    final_netpay = _round_calculation_amount(
        final_netpay,
        calculation_settings,
    )

    return deduction, final_netpay


def _update_agent_deduction_and_final_net_pay(
    agent_code,
):
    """
    Update deduction and final_net_pay on all active Commission
    documents belonging to the same agent.

    The calculation remains agent-level and is not changed.
    Only the hardcoded calculation values are now read from
    Commission Settings.
    """
    if not agent_code:
        return {
            "agent_code": None,
            "agent_total_netpay": 0,
            "deduction": 0,
            "final_net_pay": 0,
        }

    agent_code = str(agent_code).strip()

    result = frappe.db.sql(
        """
        SELECT
            COALESCE(
                SUM(
                    CAST(
                        NULLIF(TRIM(netpay), '')
                        AS DECIMAL(18, 2)
                    )
                ),
                0
            ) AS agent_total_netpay
        FROM `tabCommission`
        WHERE agent_code = %s
        AND docstatus < 2
        """,
        (agent_code,),
        as_dict=True,
    )

    agent_total_netpay = (
        flt(result[0].agent_total_netpay)
        if result
        and result[0].agent_total_netpay is not None
        else 0
    )

    calculation_settings = (
        _get_commission_calculation_settings()
    )

    deduction, final_net_pay = (
        _calculate_agent_deduction(
            agent_total_netpay=agent_total_netpay,
            calculation_settings=calculation_settings,
        )
    )

    frappe.db.sql(
        """
        UPDATE `tabCommission`
        SET
            deduction = %s,
            final_net_pay = %s
        WHERE agent_code = %s
        AND docstatus < 2
        """,
        (
            flt(deduction),
            flt(final_net_pay),
            agent_code,
        ),
    )

    return {
        "agent_code": agent_code,
        "agent_total_netpay": agent_total_netpay,
        "deduction": flt(deduction),
        "final_net_pay": flt(final_net_pay),
    }


def _get_product_commission_type(scheme_code):
    """
    Return Commission Type configured in Product.

    Product name equals Product.product_code because Product uses:
    autoname = field:product_code
    """
    if not scheme_code:
        frappe.throw(_("Scheme Code is required to create Commission Payment"))

    product_name = str(scheme_code).strip()

    commission_type = frappe.db.get_value(
        "Product",
        product_name,
        "commission_type",
    )

    if not commission_type:
        frappe.throw(
            _("Commission Type is not configured in Product: {0}").format(
                product_name
            )
        )

    return commission_type


def _commission_payment_exists(commission_name, payment_type, payment_year):
    """
    Check whether a Commission Payment already exists.

    Duplicate key:
    Commission + Payment Type + Payment Year.
    """
    return frappe.db.exists(
        "Commission Payment",
        {
            "commission": commission_name,
            "payment_type": payment_type,
            "payment_year": payment_year,
            "docstatus": ("<", 2),
        },
    )


def _create_commission_payment_if_missing(payment_data):
    """
    Insert a Commission Payment only if the same schedule/payment
    record does not already exist.
    """
    existing_payment = _commission_payment_exists(
        payment_data.get("commission"),
        payment_data.get("payment_type"),
        payment_data.get("payment_year"),
    )

    if existing_payment:
        return {
            "created": False,
            "name": existing_payment,
        }

    payment_doc = frappe.get_doc({
        "doctype": "Commission Payment",
        **payment_data,
    })

    payment_doc.insert(ignore_permissions=True)

    return {
        "created": True,
        "name": payment_doc.name,
    }


def create_commission_payment_records(commission_doc):
    """
    Create payment records after Commission calculation.

    Normal type:
    - One consolidated payment record for the agent.

    Deferred type:
    - One payment record per yearly deferred schedule row.
    """
    commission_type = frappe.db.get_value(
        "Product",
        str(commission_doc.scheme_code).strip(),
        "commission_type",
    )

    if not commission_type:
        frappe.throw(
            _("Commission Type is missing for Scheme Code: {0}").format(
                commission_doc.scheme_code
            )
        )

    if commission_type == "Deferred":
        return {
            "commission_type": "Deferred",
            "deferred_result": _create_deferred_payment_records(
                commission_doc
            ),
        }

    return {
        "commission_type": commission_type,
        "normal_result": _create_normal_agent_payment_if_missing(
            commission_doc.agent_code
        ),
    }


def _round_payment_amounts(payment_data):
    """
    Round all Commission Payment monetary values to whole numbers
    when round_calculated_amounts is enabled.
    """
    calculation_settings = (
        _get_commission_calculation_settings()
    )

    amount_fields = (
        "gross_commission",
        "tds_amount",
        "security_deposit_amount",
        "netpay_amount",
        "deduction_amount",
        "final_netpay",
    )

    for fieldname in amount_fields:
        if fieldname in payment_data:
            payment_data[fieldname] = flt(
                _round_calculation_amount(
                    payment_data[fieldname],
                    calculation_settings,
                )
            )

    return payment_data


def _get_deferred_product_codes():
    """
    Return Product document names configured with Deferred commission type.

    Product.name equals Product.product_code because Product uses:
    autoname = field:product_code
    """
    return frappe.get_all(
        "Product",
        filters={"commission_type": "Deferred"},
        pluck="name",
    )


def _create_normal_agent_payment_if_missing(agent_code, due_date=None):
    """
    Create one consolidated Commission Payment record for one agent.

    Includes only Commission records whose Product commission type
    is NOT Deferred.
    """
    if not agent_code:
        frappe.throw(_("Agent Code is required"))

    agent_code = str(agent_code).strip()
    due_date = due_date or frappe.utils.today()

    deferred_product_codes = _get_deferred_product_codes()

    deferred_condition = ""
    values = {"agent_code": agent_code}

    if deferred_product_codes:
        placeholders = ", ".join(
            [f"%(deferred_scheme_{i})s" for i in range(
                len(deferred_product_codes))]
        )

        deferred_condition = f"""
            AND c.scheme_code NOT IN ({placeholders})
        """

        for i, scheme_code in enumerate(deferred_product_codes):
            values[f"deferred_scheme_{i}"] = scheme_code

    # totals = frappe.db.sql(
    #     f"""
    #     SELECT
    #         COALESCE(
    #             SUM(CAST(NULLIF(TRIM(c.commission_amount), '') AS DECIMAL(18,2))),
    #             0
    #         ) AS gross_commission,

    #         COALESCE(
    #             SUM(CAST(NULLIF(TRIM(c.tds), '') AS DECIMAL(18,2))),
    #             0
    #         ) AS tds_amount,

    #         COALESCE(
    #             SUM(CAST(NULLIF(TRIM(c.security_deposit), '') AS DECIMAL(18,2))),
    #             0
    #         ) AS security_deposit_amount,

    #         COALESCE(
    #             SUM(CAST(NULLIF(TRIM(c.netpay), '') AS DECIMAL(18,2))),
    #             0
    #         ) AS netpay_amount,

    #         MAX(CAST(NULLIF(TRIM(c.deduction), '') AS DECIMAL(18,2))) AS deduction_amount,

    #         MAX(CAST(NULLIF(TRIM(c.final_net_pay), '') AS DECIMAL(18,2))) AS final_netpay

    #     FROM `tabCommission` c
    #     WHERE c.agent_code = %(agent_code)s
    #     AND c.docstatus < 2
    #     {deferred_condition}
    #     """,
    #     values,
    #     as_dict=True,
    # )
#################################################################################################
    # totals = frappe.db.sql(
    #     f"""
    # SELECT
    #     MAX(NULLIF(TRIM(c.agent_operative_account), '')) AS agent_operative_account,
    #     MAX(NULLIF(TRIM(c.agent_saving_account), '')) AS agent_saving_account,

    #     COALESCE(
    #         SUM(CAST(NULLIF(TRIM(c.commission_amount), '') AS DECIMAL(18,2))),
    #         0
    #     ) AS gross_commission,

    #     COALESCE(
    #         SUM(CAST(NULLIF(TRIM(c.tds), '') AS DECIMAL(18,2))),
    #         0
    #     ) AS tds_amount,

    #     COALESCE(
    #         SUM(CAST(NULLIF(TRIM(c.security_deposit), '') AS DECIMAL(18,2))),
    #         0
    #     ) AS security_deposit_amount,

    #     COALESCE(
    #         SUM(CAST(NULLIF(TRIM(c.netpay), '') AS DECIMAL(18,2))),
    #         0
    #     ) AS netpay_amount,

    #     MAX(CAST(NULLIF(TRIM(c.deduction), '') AS DECIMAL(18,2))) AS deduction_amount,

    #     MAX(CAST(NULLIF(TRIM(c.final_net_pay), '') AS DECIMAL(18,2))) AS finalnetpay

    # FROM `tabCommission` c
    # WHERE c.agent_code = %(agent_code)s
    # AND c.docstatus < 2
    # {deferred_condition}
    # """,
    #     values,
    #     as_dict=True,
    # )

    totals = frappe.db.sql(
        f"""
    SELECT
        MAX(NULLIF(TRIM(c.agent_operative_account), ''))
            AS agent_operative_account,

        MAX(NULLIF(TRIM(c.agent_saving_account), ''))
            AS agent_saving_account,

        COALESCE(
            SUM(
                CAST(
                    NULLIF(TRIM(c.commission_amount), '')
                    AS DECIMAL(18,2)
                )
            ),
            0
        ) AS gross_commission,

        COALESCE(
            SUM(
                CAST(
                    NULLIF(TRIM(c.tds), '')
                    AS DECIMAL(18,2)
                )
            ),
            0
        ) AS tds_amount,

        COALESCE(
            SUM(
                CAST(
                    NULLIF(TRIM(c.security_deposit), '')
                    AS DECIMAL(18,2)
                )
            ),
            0
        ) AS security_deposit_amount,

        COALESCE(
            SUM(
                CAST(
                    NULLIF(TRIM(c.netpay), '')
                    AS DECIMAL(18,2)
                )
            ),
            0
        ) AS netpay_amount,

        MAX(
            CAST(
                NULLIF(TRIM(c.deduction), '')
                AS DECIMAL(18,2)
            )
        ) AS deduction_amount,

        MAX(
            CAST(
                NULLIF(TRIM(c.final_net_pay), '')
                AS DECIMAL(18,2)
            )
        ) AS finalnetpay

    FROM `tabCommission` c
    WHERE c.agent_code = %(agent_code)s
    AND c.docstatus < 2
    {deferred_condition}
    """,
        values,
        as_dict=True,
    )
    totals = totals[0] if totals else {}
    # agent_operative_account = _safe_str(
    #     totals.get("agent_operative_account")
    # )
    # agent_saving_account = _safe_str(
    #     totals.get("agent_saving_account")
    # )

    agent_operative_account = (
        _safe_str(
            totals.get("agent_operative_account")
        )
        or "0"
    )

    agent_saving_account = (
        _safe_str(
            totals.get("agent_saving_account")
        )
        or "0"
    )

    if not agent_operative_account:
        frappe.throw(
            _("Agent Operative Account not found for Agent: {0}").format(
                agent_code
            )
        )
    if not agent_saving_account:
        frappe.throw(
            _("Agent Saving Account not found for Agent: {0}").format(
                agent_code
            )
        )

    gross_commission = flt(totals.get("gross_commission"))
    tds_amount = flt(totals.get("tds_amount"))
    security_deposit_amount = flt(totals.get("security_deposit_amount"))
    netpay_amount = flt(totals.get("netpay_amount"))
    deduction_amount = flt(totals.get("deduction_amount"))
    final_netpay = flt(totals.get("final_netpay"))

    if gross_commission <= 0 and netpay_amount <= 0:
        return {
            "created": False,
            "reason": "No normal Commission amount available for this agent",
            "name": None,
        }

    existing_payment = frappe.db.exists(
        "Commission Payment",
        {
            "agent_code": agent_code,
            "payment_type": "Normal",
            "due_date": due_date,
            "docstatus": ("<", 2),
        },
    )

    if existing_payment:
        payment_doc = frappe.get_doc("Commission Payment", existing_payment)

        # Do not alter a payment that is currently processing or already paid.
        if payment_doc.payment_status in ("Processing", "Paid"):
            return {
                "created": False,
                "updated": False,
                "name": payment_doc.name,
                "reason": "Payment is already Processing or Paid",
            }

        # old code
        # payment_doc.agent_operative_account = agent_operative_account
        # payment_doc.agent_saving_account = agent_saving_account

        # new code
        # payment_doc.agent_operative_account = (
        #     agent_operative_account
        # )

        # payment_doc.agent_saving_account = (
        #     agent_saving_account
        # )
        # payment_doc.gross_commission = gross_commission
        # payment_doc.tds_amount = tds_amount
        # payment_doc.security_deposit_amount = security_deposit_amount
        # payment_doc.netpay_amount = netpay_amount
        # payment_doc.deduction_amount = deduction_amount
        # payment_doc.final_netpay = final_netpay
        # payment_doc.payment_status = "Pending"

        payment_data = _round_payment_amounts({
            "gross_commission": gross_commission,
            "tds_amount": tds_amount,
            "security_deposit_amount": (
                security_deposit_amount
            ),
            "netpay_amount": netpay_amount,
            "deduction_amount": deduction_amount,
            "final_netpay": final_netpay,
        })

        payment_doc.agent_operative_account = (
            agent_operative_account
        )

        payment_doc.agent_saving_account = (
            agent_saving_account
        )

        payment_doc.gross_commission = (
            payment_data["gross_commission"]
        )

        payment_doc.tds_amount = (
            payment_data["tds_amount"]
        )

        payment_doc.security_deposit_amount = (
            payment_data[
                "security_deposit_amount"
            ]
        )

        payment_doc.netpay_amount = (
            payment_data["netpay_amount"]
        )

        payment_doc.deduction_amount = (
            payment_data["deduction_amount"]
        )

        payment_doc.final_netpay = (
            payment_data["final_netpay"]
        )

        payment_doc.payment_status = "Pending"
        payment_doc.save(ignore_permissions=True)

        _link_commission_items_to_payment(
            payment_name=payment_doc.name,
            agent_code=agent_code,
            due_date=due_date,
        )

        return {
            "created": False,
            "updated": True,
            "name": payment_doc.name,
        }

    # payment_doc = frappe.get_doc({
    #     "doctype": "Commission Payment",
    #     "agent_code": agent_code,
    #     # "agent_operative_account": agent_operative_account,
    #     # "agent_saving_account": agent_saving_account,
    #     "agent_operative_account": (
    #         agent_operative_account
    #     ),

    #     "agent_saving_account": (
    #         agent_saving_account
    #     ),
    #     "payment_type": "Normal",
    #     "payment_year": 1,
    #     "due_date": due_date,
    #     "gross_commission": gross_commission,
    #     "tds_amount": tds_amount,
    #     "security_deposit_amount": security_deposit_amount,
    #     "netpay_amount": netpay_amount,
    #     "deduction_amount": deduction_amount,
    #     "final_netpay": final_netpay,
    #     "payment_status": "Pending",
    # })

    payment_data = {
        "doctype": "Commission Payment",
        "agent_code": agent_code,
        "agent_operative_account": (
            agent_operative_account
        ),
        "agent_saving_account": (
            agent_saving_account
        ),
        "payment_type": "Normal",
        "payment_year": 1,
        "due_date": due_date,
        "gross_commission": gross_commission,
        "tds_amount": tds_amount,
        "security_deposit_amount": (
            security_deposit_amount
        ),
        "netpay_amount": netpay_amount,
        "deduction_amount": deduction_amount,
        "final_netpay": final_netpay,
        "payment_status": "Pending",
    }

    payment_data = _round_payment_amounts(
        payment_data
    )

    payment_doc = frappe.get_doc(
        payment_data
    )

    payment_doc.insert(ignore_permissions=True)

    _link_commission_items_to_payment(
        payment_name=payment_doc.name,
        agent_code=agent_code,
        due_date=due_date,
    )

    return {
        "created": True,
        "updated": False,
        "name": payment_doc.name,
    }


def _link_commission_items_to_payment(payment_name, agent_code, due_date=None):
    """
    Link Commission Payment reference to Commission Item child table rows
    for the agent and month of due_date, preventing duplicate payments.
    """
    if not payment_name or not agent_code:
        return

    due_date = due_date or frappe.utils.today()
    dt = frappe.utils.getdate(due_date)

    frappe.db.sql(
        """
        UPDATE `tabCommission Item` ci
        INNER JOIN `tabCommission` c ON c.name = ci.parent
        SET ci.payment_reference = %(payment_name)s
        WHERE c.agent_code = %(agent_code)s
          AND YEAR(c.creation) = %(year)s
          AND MONTH(c.creation) = %(month)s
          AND (ci.payment_reference IS NULL OR ci.payment_reference = '' OR ci.payment_reference = %(payment_name)s)
          AND ci.status IN ('Pending', 'Due')
          AND c.docstatus < 2
        """,
        {
            "payment_name": payment_name,
            "agent_code": agent_code,
            "year": dt.year,
            "month": dt.month,
        },
    )


def _get_commission_calculation_settings():
    """
    Load all calculation settings from Commission Settings.

    Defaults preserve the original calculation:
        TDS = 2% of Commission Amount
        Security Deposit = 10% of Commission Amount
        Net Pay = Commission Amount - TDS - Security Deposit
        Agent deduction = 150 when total net pay > 1000
        No rounding
    """
    settings = frappe.get_single(
        "Commission Settings"
    )

    # decimal_places = cint(
    #     getattr(
    #         settings,
    #         "calculation_decimal_places",
    #         2,
    #     )
    #     or 2
    # )

    # if decimal_places < 0:
    #     decimal_places = 0

    return {
        "round_calculated_amounts": cint(
            getattr(
                settings,
                "round_calculated_amounts",
                0,
            )
        ),

        # "calculation_decimal_places": decimal_places,

        # # "calculation_rounding_method": (
        # #     getattr(
        # #         settings,
        # #         "calculation_rounding_method",
        # #         None,
        # #     )
        # #     or "Half Up"
        # # ),
        # "calculation_rounding_method": (
        #     getattr(
        #         settings,
        #         "calculation_rounding_method",
        #         None,
        #     )
        #     or "Nearest"
        # ),

        "enable_tds": cint(
            getattr(
                settings,
                "enable_tds",
                1,
            )
        ),

        "tds_operation": (
            getattr(
                settings,
                "tds_operation",
                None,
            )
            or "Percentage"
        ),

        "tds_percentage": flt(
            getattr(
                settings,
                "tds_percentage",
                2,
            )
            if getattr(
                settings,
                "tds_percentage",
                None,
            )
            not in (None, "")
            else 2
        ),

        "tds_percentage_without_valid_pan": flt(
            getattr(
                settings,
                "tds_percentage_without_valid_pan",
                20,
            )
            if getattr(
                settings,
                "tds_percentage_without_valid_pan",
                None,
            )
            not in (None, "")
            else 20
        ),

        "tds_fixed_amount": flt(
            getattr(
                settings,
                "tds_fixed_amount",
                0,
            )
            or 0
        ),

        "tds_base": (
            getattr(
                settings,
                "tds_base",
                None,
            )
            or "Commission Amount"
        ),

        "tds_maximum_amount": (
            flt(settings.tds_maximum_amount)
            if getattr(
                settings,
                "tds_maximum_amount",
                None,
            )
            not in (None, "")
            else None
        ),

        "enable_security_deposit": cint(
            getattr(
                settings,
                "enable_security_deposit",
                1,
            )
        ),

        "security_deposit_operation": (
            getattr(
                settings,
                "security_deposit_operation",
                None,
            )
            or "Percentage"
        ),

        "security_deposit_percentage": flt(
            getattr(
                settings,
                "security_deposit_percentage",
                10,
            )
            if getattr(
                settings,
                "security_deposit_percentage",
                None,
            )
            not in (None, "")
            else 10
        ),

        "security_deposit_fixed_amount": flt(
            getattr(
                settings,
                "security_deposit_fixed_amount",
                0,
            )
            or 0
        ),

        "security_deposit_base": (
            getattr(
                settings,
                "security_deposit_base",
                None,
            )
            or "Commission Amount"
        ),

        "security_deposit_maximum_amount": (
            flt(settings.security_deposit_maximum_amount)
            if getattr(
                settings,
                "security_deposit_maximum_amount",
                None,
            )
            not in (None, "")
            else None
        ),

        "net_pay_operation": (
            getattr(
                settings,
                "net_pay_operation",
                None,
            )
            or "Commission Amount - TDS - Security Deposit"
        ),

        "net_pay_fixed_adjustment": flt(
            getattr(
                settings,
                "net_pay_fixed_adjustment",
                0,
            )
            or 0
        ),

        "net_pay_minimum_amount": (
            flt(settings.net_pay_minimum_amount)
            if getattr(
                settings,
                "net_pay_minimum_amount",
                None,
            )
            not in (None, "")
            else None
        ),

        "net_pay_maximum_amount": (
            flt(settings.net_pay_maximum_amount)
            if getattr(
                settings,
                "net_pay_maximum_amount",
                None,
            )
            not in (None, "")
            else None
        ),

        "enable_agent_deduction": cint(
            getattr(
                settings,
                "enable_agent_deduction",
                1,
            )
        ),

        "agent_deduction_type": (
            getattr(
                settings,
                "agent_deduction_type",
                None,
            )
            or "Amount Above Limit"
        ),

        "agent_deduction_limit": flt(
            getattr(
                settings,
                "agent_deduction_limit",
                1000,
            )
            or 1000
        ),

        "agent_deduction_amount": flt(
            getattr(
                settings,
                "agent_deduction_amount",
                150,
            )
            or 150
        ),

        "agent_deduction_percentage": flt(
            getattr(
                settings,
                "agent_deduction_percentage",
                0,
            )
            or 0
        ),

        "agent_deduction_maximum": (
            flt(settings.agent_deduction_maximum)
            if getattr(
                settings,
                "agent_deduction_maximum",
                None,
            )
            not in (None, "")
            else None
        ),

        "agent_deduction_operation": (
            getattr(
                settings,
                "agent_deduction_operation",
                None,
            )
            or "Subtract"
        ),
    }


def _decimal_amount(value):
    return Decimal(
        str(
            0
            if value in (None, "")
            else value
        )
    )


# def _round_calculation_amount(
#     value,
#     calculation_settings,
# ):
#     """
#     Round only when Round Calculated Amounts is enabled.
#     """
#     amount = _decimal_amount(value)

#     if not calculation_settings[
#         "round_calculated_amounts"
#     ]:
#         return amount

#     rounding_map = {
#         "Half Up": ROUND_HALF_UP,
#         "Half Down": ROUND_HALF_DOWN,
#         "Down": ROUND_DOWN,
#         "Up": ROUND_UP,
#         "Ceiling": ROUND_CEILING,
#         "Floor": ROUND_FLOOR,
#     }

#     rounding_mode = rounding_map.get(
#         calculation_settings[
#             "calculation_rounding_method"
#         ],
#         ROUND_HALF_UP,
#     )

#     decimal_places = calculation_settings[
#         "calculation_decimal_places"
#     ]

#     quantizer = Decimal("1").scaleb(
#         -decimal_places
#     )

#     return amount.quantize(
#         quantizer,
#         rounding=rounding_mode,
#     )


# def _round_calculation_amount(
#     value,
#     calculation_settings,
# ):
#     """
#     Round using one rule only:

#     Decimal part < 0.5:
#         round down

#     Decimal part >= 0.5:
#         round up

#     Examples:
#         10.49 -> 10
#         10.50 -> 11
#         10.99 -> 11
#     """
#     amount = _decimal_amount(value)

#     if not calculation_settings[
#         "round_calculated_amounts"
#     ]:
#         return amount

#     decimal_places = calculation_settings[
#         "calculation_decimal_places"
#     ]

#     quantizer = Decimal("1").scaleb(
#         -decimal_places
#     )

#     return amount.quantize(
#         quantizer,
#         rounding=ROUND_HALF_UP,
#     )


def _round_calculation_amount(
    value,
    calculation_settings,
):
    """
    Round calculated amounts to the nearest whole number.

    When disabled:
        Keep the original decimal value.

    When enabled:
        Decimal part below 0.50 -> round down.
        Decimal part 0.50 or above -> round up.

    Examples:
        10.01 -> 10
        10.30 -> 10
        10.40 -> 10
        10.49 -> 10
        10.50 -> 11
        10.60 -> 11
        10.78 -> 11
        10.90 -> 11
    """
    amount = _decimal_amount(value)

    if not calculation_settings[
        "round_calculated_amounts"
    ]:
        return amount

    return amount.quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )


def _apply_amount_limit(
    amount,
    maximum_amount,
):
    amount = _decimal_amount(amount)

    if maximum_amount is None:
        return amount

    return min(
        amount,
        _decimal_amount(maximum_amount),
    )


def _get_calculation_base(
    base_name,
    commission_amount,
    eligible_amount,
    tds=Decimal("0"),
    security_deposit=Decimal("0"),
):
    """
    Return the configured base amount.

    Supported bases are the values in Commission Settings.
    """
    if base_name == "Eligible Amount":
        return _decimal_amount(
            eligible_amount
        )

    if base_name == "Net Pay Before TDS":
        return (
            _decimal_amount(commission_amount)
            - _decimal_amount(security_deposit)
        )

    if base_name == "Net Pay Before Security Deposit":
        return (
            _decimal_amount(commission_amount)
            - _decimal_amount(tds)
        )

    return _decimal_amount(
        commission_amount
    )


def _calculate_base_percentage(
    base_amount,
    percentage,
):
    return (
        _decimal_amount(base_amount)
        * _decimal_amount(percentage)
        / Decimal("100")
    )


def _has_valid_pan_status(pan_status):
    """
    Return True only for valid/active PAN status values.
    """
    normalized_status = str(
        pan_status or ""
    ).strip().casefold()

    return normalized_status in {
        "valid and operative".casefold(),
        "active".casefold(),
    }


# def _calculate_tds(
#     commission_amount,
#     eligible_amount,
#     calculation_settings,
#     security_deposit=Decimal("0"),
#     pan_status=None,
# ):
#     """
#     Calculate TDS dynamically.

#     Supported operations:
#         Percentage
#         Fixed Amount
#         Percentage Plus Security Deposit
#         Percentage Minus Security Deposit
#     """
#     if not calculation_settings["enable_tds"]:
#         return Decimal("0")

#     base_amount = _get_calculation_base(
#         base_name=calculation_settings["tds_base"],
#         commission_amount=commission_amount,
#         eligible_amount=eligible_amount,
#         security_deposit=security_deposit,
#     )

#     operation = calculation_settings[
#         "tds_operation"
#     ]

#     # percentage_amount = _calculate_base_percentage(
#     #     base_amount,
#     #     calculation_settings["tds_percentage"],
#     # )

#     if _has_valid_pan_status(pan_status):
#         applicable_tds_percentage = (
#             calculation_settings["tds_percentage"]
#         )
#     else:
#         applicable_tds_percentage = (
#             calculation_settings[
#                 "tds_percentage_without_valid_pan"
#             ]
#         )

#     percentage_amount = _calculate_base_percentage(
#         base_amount,
#         applicable_tds_percentage,
#     )

#     if operation == "Fixed Amount":
#         tds = _decimal_amount(
#             calculation_settings["tds_fixed_amount"]
#         )

#     elif operation == "Percentage Plus Security Deposit":
#         tds = (
#             percentage_amount
#             + _decimal_amount(security_deposit)
#         )

#     elif operation == "Percentage Minus Security Deposit":
#         tds = (
#             percentage_amount
#             - _decimal_amount(security_deposit)
#         )

#     else:
#         tds = percentage_amount

#     if tds < 0:
#         tds = Decimal("0")

#     tds = _apply_amount_limit(
#         tds,
#         calculation_settings[
#             "tds_maximum_amount"
#         ],
#     )

#     return _round_calculation_amount(
#         tds,
#         calculation_settings,
#     )


def _calculate_tds(
    commission_amount,
    eligible_amount,
    calculation_settings,
    security_deposit=Decimal("0"),
    pan_status=None,
):
    """
    Calculate TDS dynamically.

    Valid PAN status:
        Uses tds_percentage.

    Missing/invalid PAN status:
        Uses tds_percentage_without_valid_pan.

    The selected tds_operation logic remains unchanged.
    """
    if not calculation_settings["enable_tds"]:
        return Decimal("0")

    base_amount = _get_calculation_base(
        base_name=calculation_settings["tds_base"],
        commission_amount=commission_amount,
        eligible_amount=eligible_amount,
        security_deposit=security_deposit,
    )

    if _has_valid_pan_status(pan_status):
        applicable_tds_percentage = (
            calculation_settings["tds_percentage"]
        )
    else:
        applicable_tds_percentage = (
            calculation_settings[
                "tds_percentage_without_valid_pan"
            ]
        )

    percentage_amount = _calculate_base_percentage(
        base_amount,
        applicable_tds_percentage,
    )

    operation = calculation_settings[
        "tds_operation"
    ]

    if operation == "Fixed Amount":
        tds = _decimal_amount(
            calculation_settings["tds_fixed_amount"]
        )

    elif operation == "Percentage Plus Security Deposit":
        tds = (
            percentage_amount
            + _decimal_amount(security_deposit)
        )

    elif operation == "Percentage Minus Security Deposit":
        tds = (
            percentage_amount
            - _decimal_amount(security_deposit)
        )

    else:
        tds = percentage_amount

    if tds < 0:
        tds = Decimal("0")

    tds = _apply_amount_limit(
        tds,
        calculation_settings["tds_maximum_amount"],
    )

    return _round_calculation_amount(
        tds,
        calculation_settings,
    )


def _calculate_security_deposit(
    commission_amount,
    eligible_amount,
    tds,
    calculation_settings,
):
    """
    Calculate Security Deposit dynamically.

    Supported operations:
        Percentage
        Fixed Amount
        Percentage Plus TDS
        Percentage Minus TDS
    """
    if not calculation_settings[
        "enable_security_deposit"
    ]:
        return Decimal("0")

    base_amount = _get_calculation_base(
        base_name=calculation_settings[
            "security_deposit_base"
        ],
        commission_amount=commission_amount,
        eligible_amount=eligible_amount,
        tds=tds,
    )

    operation = calculation_settings[
        "security_deposit_operation"
    ]

    percentage_amount = _calculate_base_percentage(
        base_amount,
        calculation_settings[
            "security_deposit_percentage"
        ],
    )

    if operation == "Fixed Amount":
        security_deposit = _decimal_amount(
            calculation_settings[
                "security_deposit_fixed_amount"
            ]
        )

    elif operation == "Percentage Plus TDS":
        security_deposit = (
            percentage_amount
            + _decimal_amount(tds)
        )

    elif operation == "Percentage Minus TDS":
        security_deposit = (
            percentage_amount
            - _decimal_amount(tds)
        )

    else:
        security_deposit = percentage_amount

    if security_deposit < 0:
        security_deposit = Decimal("0")

    security_deposit = _apply_amount_limit(
        security_deposit,
        calculation_settings[
            "security_deposit_maximum_amount"
        ],
    )

    return _round_calculation_amount(
        security_deposit,
        calculation_settings,
    )


def _calculate_netpay(
    commission_amount,
    tds,
    security_deposit,
    calculation_settings,
):
    """
    Calculate Net Pay dynamically from Net Pay Operation.
    """
    commission_amount = _decimal_amount(
        commission_amount
    )
    tds = _decimal_amount(tds)
    security_deposit = _decimal_amount(
        security_deposit
    )

    operation = calculation_settings[
        "net_pay_operation"
    ]

    if operation == "Commission Amount - TDS":
        netpay = commission_amount - tds

    elif operation == "Commission Amount - Security Deposit":
        netpay = (
            commission_amount
            - security_deposit
        )

    elif operation == (
        "Commission Amount + TDS - Security Deposit"
    ):
        netpay = (
            commission_amount
            + tds
            - security_deposit
        )

    elif operation == (
        "Commission Amount - TDS + Security Deposit"
    ):
        netpay = (
            commission_amount
            - tds
            + security_deposit
        )

    elif operation == (
        "Commission Amount + TDS + Security Deposit"
    ):
        netpay = (
            commission_amount
            + tds
            + security_deposit
        )

    elif operation == "Commission Amount + Security Deposit":
        netpay = (
            commission_amount
            + security_deposit
        )

    elif operation == "Commission Amount":
        netpay = commission_amount

    elif operation == "Custom Fixed Adjustment":
        netpay = (
            commission_amount
            + _decimal_amount(
                calculation_settings[
                    "net_pay_fixed_adjustment"
                ]
            )
        )

    else:
        netpay = (
            commission_amount
            - tds
            - security_deposit
        )

    minimum_amount = calculation_settings[
        "net_pay_minimum_amount"
    ]

    maximum_amount = calculation_settings[
        "net_pay_maximum_amount"
    ]

    if minimum_amount is not None:
        netpay = max(
            netpay,
            _decimal_amount(minimum_amount),
        )

    if maximum_amount is not None:
        netpay = min(
            netpay,
            _decimal_amount(maximum_amount),
        )

    return _round_calculation_amount(
        netpay,
        calculation_settings,
    )


# def _calculate_commission_financial_values(
#     commission_amount,
#     eligible_amount,
#     pan_status=None,
# ):
#     """
#     Central financial calculation engine.

#     The TDS/Security Deposit dependency is resolved in this order:
#         1. Calculate preliminary TDS.
#         2. Calculate Security Deposit.
#         3. Recalculate TDS if it depends on Security Deposit.
#         4. Calculate Net Pay.
#     """
#     calculation_settings = (
#         _get_commission_calculation_settings()
#     )

#     commission_amount = _round_calculation_amount(
#         commission_amount,
#         calculation_settings,
#     )

#     tds_operation = calculation_settings[
#         "tds_operation"
#     ]

#     # First pass: calculate TDS without security deposit.
#     preliminary_tds = _calculate_tds(
#         commission_amount=commission_amount,
#         eligible_amount=eligible_amount,
#         calculation_settings=calculation_settings,
#         security_deposit=Decimal("0"),
#         pan_status=pan_status,
#     )

#     security_deposit = _calculate_security_deposit(
#         commission_amount=commission_amount,
#         eligible_amount=eligible_amount,
#         tds=preliminary_tds,
#         calculation_settings=calculation_settings,
#     )

#     # Second pass: TDS operations involving Security Deposit.
#     if tds_operation in (
#         "Percentage Plus Security Deposit",
#         "Percentage Minus Security Deposit",
#     ):
#         tds = _calculate_tds(
#             commission_amount=commission_amount,
#             eligible_amount=eligible_amount,
#             calculation_settings=calculation_settings,
#             security_deposit=security_deposit,
#             pan_status=pan_status,
#         )
#     else:
#         tds = preliminary_tds

#     netpay = _calculate_netpay(
#         commission_amount=commission_amount,
#         tds=tds,
#         security_deposit=security_deposit,
#         calculation_settings=calculation_settings,
#     )

#     return {
#         "commission_amount": commission_amount,
#         "tds": tds,
#         "security_deposit": security_deposit,
#         "netpay": netpay,
#         "calculation_settings": calculation_settings,
#     }

def _calculate_commission_financial_values(
    commission_amount,
    eligible_amount,
    pan_status=None,
):
    """
    Central financial calculation engine.

    TDS percentage is selected using Commission.pan_status:

    Valid and Operative / Active:
        Commission Settings.tds_percentage

    Missing or other PAN status:
        Commission Settings.tds_percentage_without_valid_pan
    """
    calculation_settings = (
        _get_commission_calculation_settings()
    )

    commission_amount = _round_calculation_amount(
        commission_amount,
        calculation_settings,
    )

    tds_operation = calculation_settings[
        "tds_operation"
    ]

    preliminary_tds = _calculate_tds(
        commission_amount=commission_amount,
        eligible_amount=eligible_amount,
        calculation_settings=calculation_settings,
        security_deposit=Decimal("0"),
        pan_status=pan_status,
    )

    security_deposit = _calculate_security_deposit(
        commission_amount=commission_amount,
        eligible_amount=eligible_amount,
        tds=preliminary_tds,
        calculation_settings=calculation_settings,
    )

    if tds_operation in (
        "Percentage Plus Security Deposit",
        "Percentage Minus Security Deposit",
    ):
        tds = _calculate_tds(
            commission_amount=commission_amount,
            eligible_amount=eligible_amount,
            calculation_settings=calculation_settings,
            security_deposit=security_deposit,
            pan_status=pan_status,
        )
    else:
        tds = preliminary_tds

    netpay = _calculate_netpay(
        commission_amount=commission_amount,
        tds=tds,
        security_deposit=security_deposit,
        calculation_settings=calculation_settings,
    )

    return {
        "commission_amount": commission_amount,
        "tds": tds,
        "security_deposit": security_deposit,
        "netpay": netpay,
        "calculation_settings": calculation_settings,
        "pan_status": pan_status,
        "tds_percentage_used": (
            calculation_settings["tds_percentage"]
            if _has_valid_pan_status(pan_status)
            else calculation_settings[
                "tds_percentage_without_valid_pan"
            ]
        ),
    }


def _get_eligible_amount_scheme_groups():
    """
    Read scheme groups from Commission Settings.

    Format:
        2014
        2015,2016,2017,2018
        2019,2020

    Returns:
        {
            "2014": ("2014",),
            "2015": ("2015", "2016", "2017", "2018"),
            "2016": ("2015", "2016", "2017", "2018"),
            ...
        }
    """
    settings = frappe.get_single(
        "Commission Settings"
    )

    raw_groups = (
        getattr(
            settings,
            "eligible_amount_scheme_groups",
            None,
        )
        or ""
    )

    scheme_groups = {}
    used_schemes = set()

    for raw_line in str(raw_groups).splitlines():
        line = raw_line.strip()

        if not line:
            continue

        scheme_codes = [
            scheme.strip()
            for scheme in line.split(",")
            if scheme.strip()
        ]

        if not scheme_codes:
            continue

        # Remove duplicates within a group while
        # preserving the entered order.
        group = tuple(
            dict.fromkeys(scheme_codes)
        )

        for scheme_code in group:
            if scheme_code in scheme_groups:
                frappe.throw(
                    _(
                        "Scheme Code {0} is configured in "
                        "more than one Eligible Amount Scheme Group."
                    ).format(scheme_code)
                )

            scheme_groups[scheme_code] = group
            used_schemes.add(scheme_code)

    return scheme_groups


def _get_eligible_amount_scheme_group(
    scheme_code,
):
    """
    Return the configured group for one scheme.

    If the scheme is not configured in a group, it becomes
    its own group.
    """
    scheme_code = str(
        scheme_code or ""
    ).strip()

    if not scheme_code:
        frappe.throw(
            _("Scheme Code is required.")
        )

    scheme_groups = (
        _get_eligible_amount_scheme_groups()
    )

    return scheme_groups.get(
        scheme_code,
        (scheme_code,),
    )


def _validate_commission_calculation_enabled():
    """
    Stop commission calculation unless enabled in Commission Settings.
    """
    settings = frappe.get_single(
        "Commission Settings"
    )

    if not cint(
        getattr(
            settings,
            "calculate_commission",
            0,
        )
    ):
        frappe.throw(
            _(
                "Commission calculation is disabled. "
                "Enable 'Calculate Commission' in Commission Settings "
                "before calculating commission."
            )
        )

    return settings


@frappe.whitelist()
def calculate_commission_amount(docname):
    """
    Calculate Commission.commission_amount based on Product commission type.

    Supported Product commission types:
    1. Fixed Rate
    2. Age Based
    3. Eligible Amount Based
    4. Deferred

    After each calculation:
    - TDS = 2% of commission amount.
    - Security Deposit = 10% of commission amount.
    - Net Pay = commission amount - TDS - Security Deposit.
    - Agent-level deduction/final_net_pay is updated for every record
      with the same agent_code.
    """

    _validate_commission_calculation_enabled()

    if not docname:
        frappe.throw(_("Commission document name is required"))

    commission_doc = frappe.get_doc("Commission", docname)

    if not commission_doc.scheme_code:
        frappe.throw(_("Scheme Code is required in Commission document"))

    if commission_doc.eligible_amount in (None, ""):
        frappe.throw(_("Eligible Amount is required in Commission document"))

    if not commission_doc.agent_code:
        frappe.throw(_("Agent Code is required in Commission document"))

    product_name = str(commission_doc.scheme_code).strip()

    product = frappe.db.get_value(
        "Product",
        product_name,
        [
            "commission_type",
            "commission_rate",
            "commission_rate_upto_one_year",
            "commission_rate_above_one_year",
            "slab_1_limit",
            "slab_1_rate",
            "slab_2_limit",
            "slab_2_rate",
            "slab_3_rate",
        ],
        as_dict=True,
    )

    if not product:
        frappe.throw(
            _("No Product found with Product Code: {0}").format(
                product_name
            )
        )

    if not product.commission_type:
        frappe.throw(
            _("Commission Type is not configured in Product: {0}").format(
                product_name
            )
        )

    commission_type = product.commission_type
    eligible_amount = flt(commission_doc.eligible_amount)

    if eligible_amount < 0:
        frappe.throw(_("Eligible Amount cannot be negative"))

    rate = None
    is_deferred = False
    deferred_result = None

    # ==========================================================
    # PRODUCT TYPE 1: FIXED RATE
    # ==========================================================
    if commission_type == "Fixed Rate":
        if product.commission_rate in (None, ""):
            frappe.throw(
                _("Commission Rate is required for Product: {0}").format(
                    product_name
                )
            )

        rate = flt(product.commission_rate)

    # ==========================================================
    # PRODUCT TYPE 2: AGE BASED
    # ==========================================================
    elif commission_type == "Age Based":
        remarks = _safe_str(commission_doc.remarks).upper()

        if remarks == "YES":
            if product.commission_rate_upto_one_year in (None, ""):
                frappe.throw(
                    _(
                        "Commission Rate Upto One Year is required "
                        "for Product: {0}"
                    ).format(product_name)
                )

            rate = flt(product.commission_rate_upto_one_year)

        elif remarks == "NO":
            if product.commission_rate_above_one_year in (None, ""):
                frappe.throw(
                    _(
                        "Commission Rate Above One Year is required "
                        "for Product: {0}"
                    ).format(product_name)
                )

            rate = flt(product.commission_rate_above_one_year)

        else:
            frappe.throw(
                _(
                    "Remarks must be YES or NO for Age Based Product: {0}"
                ).format(product_name)
            )

    # ==========================================================
    # PRODUCT TYPE 3: ELIGIBLE AMOUNT BASED
    # ==========================================================
    elif commission_type == "Eligible Amount Based":
        required_fields = {
            "Slab 1 Limit": product.slab_1_limit,
            "Slab 1 Rate": product.slab_1_rate,
            "Slab 2 Limit": product.slab_2_limit,
            "Slab 2 Rate": product.slab_2_rate,
            "Slab 3 Rate": product.slab_3_rate,
        }

        for field_label, field_value in required_fields.items():
            if field_value in (None, ""):
                frappe.throw(
                    _("{0} is required for Product: {1}").format(
                        field_label,
                        product_name,
                    )
                )

        slab_1_limit = flt(product.slab_1_limit)
        slab_2_limit = flt(product.slab_2_limit)

        if slab_1_limit < 0:
            frappe.throw(_("Slab 1 Limit cannot be negative"))

        if slab_2_limit <= slab_1_limit:
            frappe.throw(
                _(
                    "Slab 2 Limit must be greater than "
                    "Slab 1 Limit for Product: {0}"
                ).format(product_name)
            )

        # agent_code = str(commission_doc.agent_code).strip()

        # eligible_products = frappe.get_all(
        #     "Product",
        #     filters={"commission_type": "Eligible Amount Based"},
        #     pluck="name",
        # )

        # if not eligible_products:
        #     frappe.throw(
        #         _(
        #             "No Product found with commission_type = "
        #             "'Eligible Amount Based'"
        #         )
        #     )

        # in_clause = ", ".join(["%s"] * len(eligible_products))
        # in_params = tuple(eligible_products)

        # result = frappe.db.sql(
        #     """
        #     SELECT
        #         COALESCE(SUM(c.eligible_amount), 0) AS total
        #     FROM `tabCommission` c
        #     WHERE c.agent_code = %s
        #     AND c.docstatus < 2
        #     AND c.scheme_code IN ({0})
        #     """.format(in_clause),
        #     tuple([agent_code] + list(in_params)),
        #     as_dict=True,
        # )

        # agent_total = (
        #     flt(result[0].total)
        #     if result and result[0].total is not None
        #     else 0
        # )

        # if agent_total <= 0:
        #     frappe.throw(
        #         _(
        #             "Total eligible amount for Agent {0} "
        #             "(Eligible Amount Based products) is zero or invalid"
        #         ).format(agent_code)
        #     )

        # frappe.db.sql(
        #     """
        #     UPDATE `tabCommission`
        #     SET agent_total_eligible_collection = %s
        #     WHERE agent_code = %s
        #     AND docstatus < 2
        #     AND scheme_code IN ({0})
        #     """.format(in_clause),
        #     tuple([agent_total, agent_code] + list(in_params)),
        # )

        # commission_doc.agent_total_eligible_collection = agent_total

        agent_code = str(
            commission_doc.agent_code
        ).strip()

        current_scheme_code = str(
            commission_doc.scheme_code
        ).strip()

        eligible_scheme_group = (
            _get_eligible_amount_scheme_group(
                current_scheme_code
            )
        )

        group_placeholders = ", ".join(
            ["%s"] * len(eligible_scheme_group)
        )

        group_values = (
            [agent_code]
            + list(eligible_scheme_group)
        )

        result = frappe.db.sql(
            f"""
            SELECT
                COALESCE(
                    SUM(c.eligible_amount),
                    0
                ) AS total
            FROM `tabCommission` c
            INNER JOIN `tabProduct` p
                ON p.name = c.scheme_code
            WHERE c.agent_code = %s
            AND c.docstatus < 2
            AND p.commission_type = 'Eligible Amount Based'
            AND c.scheme_code IN ({group_placeholders})
            """,
            tuple(group_values),
            as_dict=True,
        )

        agent_total = (
            flt(result[0].total)
            if result
            and result[0].total is not None
            else 0
        )

        calculation_settings = (
            _get_commission_calculation_settings()
        )

        agent_total = flt(
            _round_calculation_amount(
                agent_total,
                calculation_settings,
            )
        )

        if agent_total <= 0:
            frappe.throw(
                _(
                    "Total eligible amount for Agent {0} "
                    "and Scheme Group {1} is zero or invalid."
                ).format(
                    agent_code,
                    ", ".join(eligible_scheme_group),
                )
            )

        frappe.db.sql(
            f"""
            UPDATE `tabCommission` c
            INNER JOIN `tabProduct` p
                ON p.name = c.scheme_code
            SET c.agent_total_eligible_collection = %s
            WHERE c.agent_code = %s
            AND c.docstatus < 2
            AND p.commission_type = 'Eligible Amount Based'
            AND c.scheme_code IN ({group_placeholders})
            """,
            tuple(
                [agent_total, agent_code]
                + list(eligible_scheme_group)
            ),
        )

        commission_doc.agent_total_eligible_collection = (
            agent_total
        )

        if agent_total <= slab_1_limit:
            rate = flt(product.slab_1_rate)
        elif agent_total <= slab_2_limit:
            rate = flt(product.slab_2_rate)
        else:
            rate = flt(product.slab_3_rate)

    # ==========================================================
    # PRODUCT TYPE 4: DEFERRED
    # ==========================================================
    elif commission_type == "Deferred":
        is_deferred = True

        product_doc = _get_deferred_product(product_name)

        deferred_result = _create_deferred_commission_schedule(
            commission_doc=commission_doc,
            product_doc=product_doc,
            eligible_amount=eligible_amount,
        )

        # Parent values are the total of all deferred schedule years.
        commission_amount = flt(deferred_result["total_commission"])
        rate = flt(deferred_result["total_rate"])

    # ==========================================================
    # INVALID COMMISSION TYPE
    # ==========================================================
    else:
        frappe.throw(
            _(
                "Invalid Commission Type '{0}' in Product: {1}. "
                "Allowed values are Fixed Rate, Age Based, "
                "Eligible Amount Based, and Deferred."
            ).format(
                commission_type,
                product_name,
            )
        )

    if rate is None:
        frappe.throw(
            _("Unable to determine commission rate for Product: {0}").format(
                product_name
            )
        )

    if rate < 0:
        frappe.throw(_("Commission rate cannot be negative"))

    # ==========================================================
    # COMMON FINANCIAL CALCULATION
    # ==========================================================
    if not is_deferred:
        commission_amount = (eligible_amount * rate) / 100

    # tds = commission_amount * 0.02
    # security_deposit = commission_amount * 0.10
    # netpay = commission_amount - (tds + security_deposit)

    # financial_values = (
    #     _calculate_commission_financial_values(
    #         commission_amount=commission_amount,
    #         eligible_amount=eligible_amount,
    #         pan_status=commission_doc.pan_status,
    #     )
    # )

    # commission_amount = flt(
    #     financial_values["commission_amount"]
    # )

    # tds = flt(
    #     financial_values["tds"]
    # )

    # security_deposit = flt(
    #     financial_values["security_deposit"]
    # )

    # netpay = flt(
    #     financial_values["netpay"]
    # )

    financial_values = (
        _calculate_commission_financial_values(
            commission_amount=commission_amount,
            eligible_amount=eligible_amount,
            pan_status=commission_doc.pan_status,
        )
    )

    commission_amount = flt(
        financial_values["commission_amount"]
    )

    tds = flt(
        financial_values["tds"]
    )

    security_deposit = flt(
        financial_values["security_deposit"]
    )

    netpay = flt(
        financial_values["netpay"]
    )

    calculation_settings = (
        _get_commission_calculation_settings()
    )

    commission_amount = flt(
        _round_calculation_amount(
            commission_amount,
            calculation_settings,
        )
    )

    commission_doc.eligible_amount = flt(
        _round_calculation_amount(
            commission_doc.eligible_amount,
            calculation_settings,
        )
    )

    tds = flt(
        _round_calculation_amount(
            tds,
            calculation_settings,
        )
    )

    security_deposit = flt(
        _round_calculation_amount(
            security_deposit,
            calculation_settings,
        )
    )

    netpay = flt(
        _round_calculation_amount(
            netpay,
            calculation_settings,
        )
    )

    commission_doc.commission_amount = commission_amount
    commission_doc.tds = tds
    commission_doc.security_deposit = security_deposit
    commission_doc.netpay = netpay

    if not is_deferred:
        _create_normal_commission_item(
            commission_doc=commission_doc,
            commission_type=commission_type,
            rate=rate,
            eligible_amount=eligible_amount,
            commission_amount=commission_amount,
            tds=tds,
            security_deposit=security_deposit,
            netpay=netpay,
        )

    if frappe.get_meta("Commission").has_field("applied_commission_rate"):
        commission_doc.applied_commission_rate = rate

    if frappe.get_meta("Commission").has_field("commission_type_applied"):
        commission_doc.commission_type_applied = commission_type

    commission_doc.save(ignore_permissions=True)

    # ==========================================================
    # AGENT-WISE DEDUCTION / FINAL NET PAY
    # ==========================================================
    agent_summary = _update_agent_deduction_and_final_net_pay(
        commission_doc.agent_code
    )

    commission_doc.reload()

    payment_result = create_commission_payment_records(
        commission_doc
    )

    frappe.db.commit()

    response = {
        "status": "success",
        "docname": commission_doc.name,
        "product_code": product_name,
        "commission_type": commission_type,
        "remarks": commission_doc.remarks,
        "eligible_amount": eligible_amount,
        "agent_total_eligible_collection": (
            flt(commission_doc.agent_total_eligible_collection)
            if commission_type == "Eligible Amount Based"
            else None
        ),
        "agent_total_netpay": agent_summary["agent_total_netpay"],
        "deduction": agent_summary["deduction"],
        "final_net_pay": agent_summary["final_net_pay"],
        "applied_rate": rate,
        "commission_amount": commission_amount,
        "tds": tds,
        "security_deposit": security_deposit,
        "netpay": netpay,
        "commission_payment": payment_result,
    }

    if is_deferred:
        response.update({
            "deferred_schedule_count": deferred_result["schedule_count"],
            "first_deferred_due_date": deferred_result["first_due_date"],
            "message": _("Deferred commission schedule created successfully"),
        })

    return response


def _round_amount_with_settings(value, calculation_settings):
    """
    Same rounding rule as _round_calculation_amount(),
    but accepts preloaded calculation settings.
    """
    amount = _decimal_amount(value)

    if not calculation_settings["round_calculated_amounts"]:
        return amount

    return amount.quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )


def _calculate_tds_with_settings(
    commission_amount,
    eligible_amount,
    calculation_settings,
    security_deposit=Decimal("0"),
    pan_status=None,
):
    """
    Same TDS logic as _calculate_tds(),
    but uses preloaded calculation settings.
    """
    if not calculation_settings["enable_tds"]:
        return Decimal("0")

    base_amount = _get_calculation_base(
        base_name=calculation_settings["tds_base"],
        commission_amount=commission_amount,
        eligible_amount=eligible_amount,
        security_deposit=security_deposit,
    )

    if _has_valid_pan_status(pan_status):
        applicable_tds_percentage = calculation_settings[
            "tds_percentage"
        ]
    else:
        applicable_tds_percentage = calculation_settings[
            "tds_percentage_without_valid_pan"
        ]

    percentage_amount = _calculate_base_percentage(
        base_amount,
        applicable_tds_percentage,
    )

    operation = calculation_settings["tds_operation"]

    if operation == "Fixed Amount":
        tds = _decimal_amount(
            calculation_settings["tds_fixed_amount"]
        )

    elif operation == "Percentage Plus Security Deposit":
        tds = (
            percentage_amount
            + _decimal_amount(security_deposit)
        )

    elif operation == "Percentage Minus Security Deposit":
        tds = (
            percentage_amount
            - _decimal_amount(security_deposit)
        )

    else:
        tds = percentage_amount

    if tds < 0:
        tds = Decimal("0")

    tds = _apply_amount_limit(
        tds,
        calculation_settings["tds_maximum_amount"],
    )

    return _round_amount_with_settings(
        tds,
        calculation_settings,
    )


def _calculate_security_deposit_with_settings(
    commission_amount,
    eligible_amount,
    tds,
    calculation_settings,
):
    """
    Same Security Deposit logic as _calculate_security_deposit(),
    but uses preloaded calculation settings.
    """
    if not calculation_settings["enable_security_deposit"]:
        return Decimal("0")

    base_amount = _get_calculation_base(
        base_name=calculation_settings["security_deposit_base"],
        commission_amount=commission_amount,
        eligible_amount=eligible_amount,
        tds=tds,
    )

    operation = calculation_settings[
        "security_deposit_operation"
    ]

    percentage_amount = _calculate_base_percentage(
        base_amount,
        calculation_settings[
            "security_deposit_percentage"
        ],
    )

    if operation == "Fixed Amount":
        security_deposit = _decimal_amount(
            calculation_settings[
                "security_deposit_fixed_amount"
            ]
        )

    elif operation == "Percentage Plus TDS":
        security_deposit = (
            percentage_amount
            + _decimal_amount(tds)
        )

    elif operation == "Percentage Minus TDS":
        security_deposit = (
            percentage_amount
            - _decimal_amount(tds)
        )

    else:
        security_deposit = percentage_amount

    if security_deposit < 0:
        security_deposit = Decimal("0")

    security_deposit = _apply_amount_limit(
        security_deposit,
        calculation_settings[
            "security_deposit_maximum_amount"
        ],
    )

    return _round_amount_with_settings(
        security_deposit,
        calculation_settings,
    )


def _calculate_netpay_with_settings(
    commission_amount,
    tds,
    security_deposit,
    calculation_settings,
):
    """
    Same Net Pay logic as _calculate_netpay(),
    but uses preloaded calculation settings.
    """
    commission_amount = _decimal_amount(
        commission_amount
    )
    tds = _decimal_amount(tds)
    security_deposit = _decimal_amount(
        security_deposit
    )

    operation = calculation_settings[
        "net_pay_operation"
    ]

    if operation == "Commission Amount - TDS":
        netpay = commission_amount - tds

    elif operation == "Commission Amount - Security Deposit":
        netpay = (
            commission_amount
            - security_deposit
        )

    elif operation == (
        "Commission Amount + TDS - Security Deposit"
    ):
        netpay = (
            commission_amount
            + tds
            - security_deposit
        )

    elif operation == (
        "Commission Amount - TDS + Security Deposit"
    ):
        netpay = (
            commission_amount
            - tds
            + security_deposit
        )

    elif operation == (
        "Commission Amount + TDS + Security Deposit"
    ):
        netpay = (
            commission_amount
            + tds
            + security_deposit
        )

    elif operation == "Commission Amount + Security Deposit":
        netpay = (
            commission_amount
            + security_deposit
        )

    elif operation == "Commission Amount":
        netpay = commission_amount

    elif operation == "Custom Fixed Adjustment":
        netpay = (
            commission_amount
            + _decimal_amount(
                calculation_settings[
                    "net_pay_fixed_adjustment"
                ]
            )
        )

    else:
        netpay = (
            commission_amount
            - tds
            - security_deposit
        )

    minimum_amount = calculation_settings[
        "net_pay_minimum_amount"
    ]

    maximum_amount = calculation_settings[
        "net_pay_maximum_amount"
    ]

    if minimum_amount is not None:
        netpay = max(
            netpay,
            _decimal_amount(minimum_amount),
        )

    if maximum_amount is not None:
        netpay = min(
            netpay,
            _decimal_amount(maximum_amount),
        )

    return _round_amount_with_settings(
        netpay,
        calculation_settings,
    )


def _calculate_financial_values_with_settings(
    commission_amount,
    eligible_amount,
    pan_status,
    calculation_settings,
):
    """
    Same result as _calculate_commission_financial_values(),
    but accepts preloaded calculation settings.
    """
    commission_amount = _round_amount_with_settings(
        commission_amount,
        calculation_settings,
    )

    tds_operation = calculation_settings[
        "tds_operation"
    ]

    preliminary_tds = _calculate_tds_with_settings(
        commission_amount=commission_amount,
        eligible_amount=eligible_amount,
        calculation_settings=calculation_settings,
        security_deposit=Decimal("0"),
        pan_status=pan_status,
    )

    security_deposit = (
        _calculate_security_deposit_with_settings(
            commission_amount=commission_amount,
            eligible_amount=eligible_amount,
            tds=preliminary_tds,
            calculation_settings=calculation_settings,
        )
    )

    if tds_operation in (
        "Percentage Plus Security Deposit",
        "Percentage Minus Security Deposit",
    ):
        tds = _calculate_tds_with_settings(
            commission_amount=commission_amount,
            eligible_amount=eligible_amount,
            calculation_settings=calculation_settings,
            security_deposit=security_deposit,
            pan_status=pan_status,
        )
    else:
        tds = preliminary_tds

    netpay = _calculate_netpay_with_settings(
        commission_amount=commission_amount,
        tds=tds,
        security_deposit=security_deposit,
        calculation_settings=calculation_settings,
    )

    return {
        "commission_amount": commission_amount,
        "tds": tds,
        "security_deposit": security_deposit,
        "netpay": netpay,
    }


def _preload_bulk_commission_data():
    """
    Load all static configuration once for the complete bulk run.
    """
    calculation_settings = (
        _get_commission_calculation_settings()
    )

    products = frappe.get_all(
        "Product",
        fields=[
            "name",
            "commission_type",
            "commission_rate",
            "commission_rate_upto_one_year",
            "commission_rate_above_one_year",
            "slab_1_limit",
            "slab_1_rate",
            "slab_2_limit",
            "slab_2_rate",
            "slab_3_rate",
        ],
    )

    product_map = {
        product.name: product
        for product in products
    }

    deferred_product_codes = {
        product.name
        for product in products
        if product.commission_type == "Deferred"
    }

    deferred_product_docs = {}

    for product_name in deferred_product_codes:
        deferred_product_docs[product_name] = (
            frappe.get_doc(
                "Product",
                product_name,
            )
        )

    scheme_groups = (
        _get_eligible_amount_scheme_groups()
    )

    commission_meta = frappe.get_meta("Commission")

    return {
        "calculation_settings": calculation_settings,
        "product_map": product_map,
        "deferred_product_codes": deferred_product_codes,
        "deferred_product_docs": deferred_product_docs,
        "scheme_groups": scheme_groups,
        "has_applied_rate_field": commission_meta.has_field(
            "applied_commission_rate"
        ),
        "has_commission_type_field": commission_meta.has_field(
            "commission_type_applied"
        ),
    }


def _get_bulk_commission_fields():
    return [
        "name",
        "agent_code",
        "agent_name",
        "scheme_code",
        "eligible_amount",
        "remarks",
        "pan_status",
        "creation",
        "docstatus",
    ]


def _bulk_update_commission_calculated_fields(
    update_rows,
    chunk_size=2000,
):
    """
    Bulk update calculated Commission parent fields.
    """
    if not update_rows:
        return

    update_sql = """
        UPDATE `tabCommission`
        SET
            modified = %s,
            modified_by = %s,
            eligible_amount = %s,
            commission_amount = %s,
            tds = %s,
            security_deposit = %s,
            netpay = %s,
            applied_commission_rate = %s,
            commission_type_applied = %s,
            agent_total_eligible_collection = %s
        WHERE name = %s
    """

    cursor = frappe.db._cursor

    for i in range(
        0,
        len(update_rows),
        chunk_size,
    ):
        chunk = update_rows[
            i:i + chunk_size
        ]

        cursor.executemany(
            update_sql,
            chunk,
        )

    frappe.db.commit()


def _bulk_insert_commission_items(
    item_rows,
    chunk_size=5000,
):
    """
    Bulk insert Commission Item child rows.
    """
    if not item_rows:
        return

    fields = [
        "name",
        "creation",
        "modified",
        "modified_by",
        "owner",
        "docstatus",
        "idx",
        "parent",
        "parentfield",
        "parenttype",
        "commission_type",
        "year_no",
        "commission_rate",
        "eligible_amount",
        "gross_commission",
        "due_date",
        "status",
        "tds",
        "security_deposit",
        "netpay",
        "remarks",
    ]

    frappe.db.bulk_insert(
        "Commission Item",
        fields,
        item_rows,
        chunk_size=chunk_size,
    )

    frappe.db.commit()


def _bulk_update_agent_deduction(
    agent_deduction_rows,
    chunk_size=1000,
):
    """
    Update deduction and final_net_pay once per agent.
    """
    if not agent_deduction_rows:
        return

    update_sql = """
        UPDATE `tabCommission`
        SET
            deduction = %s,
            final_net_pay = %s
        WHERE agent_code = %s
        AND docstatus < 2
    """

    cursor = frappe.db._cursor

    for i in range(
        0,
        len(agent_deduction_rows),
        chunk_size,
    ):
        chunk = agent_deduction_rows[
            i:i + chunk_size
        ]

        cursor.executemany(
            update_sql,
            chunk,
        )

    frappe.db.commit()


# @frappe.whitelist()
# def calculate_commission_for_all_optimized(
#     batch_size=5000,
# ):
#     """
#     Optimized bulk commission calculation.

#     Preserves the same calculation logic as
#     calculate_commission_amount(docname), including:

#     - Fixed Rate
#     - Age Based
#     - Eligible Amount Based slab selection
#     - Deferred yearly schedule
#     - PAN-based TDS
#     - Security Deposit
#     - Net Pay
#     - Agent-level deduction and final net pay
#     - Commission Item rows
#     - Normal and Deferred Commission Payment creation

#     Differences from the existing method:
#     - Reads settings and Product data once
#     - Calculates values in memory
#     - Updates Commission parent records in batches
#     - Inserts Commission Item rows in bulk
#     - Updates agent deduction once per agent
#     - Creates Normal Commission Payment once per agent
#     - Commits in batches instead of after every record
#     """
#     frappe.only_for(("System Manager",))

#     _validate_commission_calculation_enabled()

#     batch_size = cint(batch_size) or 5000

#     if batch_size < 100:
#         batch_size = 100

#     preloaded = _preload_bulk_commission_data()

#     calculation_settings = preloaded[
#         "calculation_settings"
#     ]

#     product_map = preloaded["product_map"]
#     scheme_groups = preloaded["scheme_groups"]
#     deferred_product_codes = preloaded[
#         "deferred_product_codes"
#     ]
#     deferred_product_docs = preloaded[
#         "deferred_product_docs"
#     ]

#     fields = _get_bulk_commission_fields()

#     total_count = frappe.db.count(
#         "Commission",
#         {
#             "docstatus": ("<", 2),
#         },
#     )

#     if not total_count:
#         return {
#             "status": "completed",
#             "total_processed": 0,
#             "success_count": 0,
#             "error_count": 0,
#             "errors": [],
#         }

#     processed_count = 0
#     success_count = 0
#     error_count = 0
#     errors = []

#     normal_agent_codes = set()
#     deferred_item_rows = []
#     processed_deferred_keys = set()

#     offset = 0

#     while offset < total_count:
#         commission_rows = frappe.db.sql(
#             f"""
#             SELECT
#                 {", ".join(fields)}
#             FROM `tabCommission`
#             WHERE docstatus < 2
#             ORDER BY creation ASC, name ASC
#             LIMIT %s OFFSET %s
#             """,
#             (
#                 batch_size,
#                 offset,
#             ),
#             as_dict=True,
#         )

#         if not commission_rows:
#             break

#         offset += len(commission_rows)

#         parent_update_rows = []
#         commission_item_rows = []

#         now_ts = now_datetime()
#         current_user = frappe.session.user

#         for row in commission_rows:
#             try:
#                 commission_name = row.name
#                 scheme_code = str(
#                     row.scheme_code or ""
#                 ).strip()

#                 if not scheme_code:
#                     raise frappe.ValidationError(
#                         _(
#                             "Scheme Code is required in "
#                             "Commission document"
#                         )
#                     )

#                 if row.eligible_amount in (None, ""):
#                     raise frappe.ValidationError(
#                         _(
#                             "Eligible Amount is required in "
#                             "Commission document"
#                         )
#                     )

#                 if not row.agent_code:
#                     raise frappe.ValidationError(
#                         _(
#                             "Agent Code is required in "
#                             "Commission document"
#                         )
#                     )

#                 product = product_map.get(scheme_code)

#                 if not product:
#                     raise frappe.ValidationError(
#                         _(
#                             "No Product found with Product Code: {0}"
#                         ).format(scheme_code)
#                     )

#                 commission_type = product.commission_type

#                 if not commission_type:
#                     raise frappe.ValidationError(
#                         _(
#                             "Commission Type is not configured "
#                             "in Product: {0}"
#                         ).format(scheme_code)
#                     )

#                 eligible_amount = flt(
#                     row.eligible_amount
#                 )

#                 if eligible_amount < 0:
#                     raise frappe.ValidationError(
#                         _(
#                             "Eligible Amount cannot be negative"
#                         )
#                     )

#                 rate = None
#                 is_deferred = False
#                 commission_amount = 0
#                 agent_total = None

#                 if commission_type == "Fixed Rate":
#                     if product.commission_rate in (None, ""):
#                         raise frappe.ValidationError(
#                             _(
#                                 "Commission Rate is required for "
#                                 "Product: {0}"
#                             ).format(scheme_code)
#                         )

#                     rate = flt(
#                         product.commission_rate
#                     )

#                 elif commission_type == "Age Based":
#                     remarks = str(
#                         row.remarks or ""
#                     ).strip().upper()

#                     if remarks == "YES":
#                         if product.commission_rate_upto_one_year in (
#                             None,
#                             "",
#                         ):
#                             raise frappe.ValidationError(
#                                 _(
#                                     "Commission Rate Upto One Year is "
#                                     "required for Product: {0}"
#                                 ).format(scheme_code)
#                             )

#                         rate = flt(
#                             product.commission_rate_upto_one_year
#                         )

#                     elif remarks == "NO":
#                         if product.commission_rate_above_one_year in (
#                             None,
#                             "",
#                         ):
#                             raise frappe.ValidationError(
#                                 _(
#                                     "Commission Rate Above One Year is "
#                                     "required for Product: {0}"
#                                 ).format(scheme_code)
#                             )

#                         rate = flt(
#                             product.commission_rate_above_one_year
#                         )

#                     else:
#                         raise frappe.ValidationError(
#                             _(
#                                 "Remarks must be YES or NO for "
#                                 "Age Based Product: {0}"
#                             ).format(scheme_code)
#                         )

#                 elif commission_type == "Eligible Amount Based":
#                     required_fields = {
#                         "Slab 1 Limit": product.slab_1_limit,
#                         "Slab 1 Rate": product.slab_1_rate,
#                         "Slab 2 Limit": product.slab_2_limit,
#                         "Slab 2 Rate": product.slab_2_rate,
#                         "Slab 3 Rate": product.slab_3_rate,
#                     }

#                     for field_label, field_value in required_fields.items():
#                         if field_value in (None, ""):
#                             raise frappe.ValidationError(
#                                 _(
#                                     "{0} is required for Product: {1}"
#                                 ).format(
#                                     field_label,
#                                     scheme_code,
#                                 )
#                             )

#                     slab_1_limit = flt(
#                         product.slab_1_limit
#                     )
#                     slab_2_limit = flt(
#                         product.slab_2_limit
#                     )

#                     if slab_1_limit < 0:
#                         raise frappe.ValidationError(
#                             _(
#                                 "Slab 1 Limit cannot be negative"
#                             )
#                         )

#                     if slab_2_limit <= slab_1_limit:
#                         raise frappe.ValidationError(
#                             _(
#                                 "Slab 2 Limit must be greater than "
#                                 "Slab 1 Limit for Product: {0}"
#                             ).format(scheme_code)
#                         )

#                     agent_code = str(
#                         row.agent_code
#                     ).strip()

#                     eligible_scheme_group = (
#                         scheme_groups.get(
#                             scheme_code,
#                             (scheme_code,),
#                         )
#                     )

#                     group_values = [
#                         agent_code
#                     ] + list(eligible_scheme_group)

#                     placeholders = ", ".join(
#                         ["%s"] * len(
#                             eligible_scheme_group
#                         )
#                     )

#                     result = frappe.db.sql(
#                         f"""
#                         SELECT
#                             COALESCE(
#                                 SUM(
#                                     CAST(
#                                         NULLIF(
#                                             TRIM(c.eligible_amount),
#                                             ''
#                                         ) AS DECIMAL(18, 2)
#                                     )
#                                 ),
#                                 0
#                             ) AS total
#                         FROM `tabCommission` c
#                         INNER JOIN `tabProduct` p
#                             ON p.name = c.scheme_code
#                         WHERE c.agent_code = %s
#                         AND c.docstatus < 2
#                         AND p.commission_type = 'Eligible Amount Based'
#                         AND c.scheme_code IN ({placeholders})
#                         """,
#                         tuple(group_values),
#                         as_dict=True,
#                     )

#                     agent_total = flt(
#                         result[0].total
#                         if result
#                         and result[0].total is not None
#                         else 0
#                     )

#                     agent_total = flt(
#                         _round_amount_with_settings(
#                             agent_total,
#                             calculation_settings,
#                         )
#                     )

#                     if agent_total <= 0:
#                         raise frappe.ValidationError(
#                             _(
#                                 "Total eligible amount for Agent {0} "
#                                 "and Scheme Group {1} is zero or invalid."
#                             ).format(
#                                 agent_code,
#                                 ", ".join(
#                                     eligible_scheme_group
#                                 ),
#                             )
#                         )

#                     if agent_total <= slab_1_limit:
#                         rate = flt(
#                             product.slab_1_rate
#                         )

#                     elif agent_total <= slab_2_limit:
#                         rate = flt(
#                             product.slab_2_rate
#                         )

#                     else:
#                         rate = flt(
#                             product.slab_3_rate
#                         )

#                 elif commission_type == "Deferred":
#                     is_deferred = True

#                     product_doc = deferred_product_docs.get(
#                         scheme_code
#                     )

#                     if not product_doc:
#                         raise frappe.ValidationError(
#                             _(
#                                 "Deferred Product configuration is "
#                                 "missing for Product: {0}"
#                             ).format(scheme_code)
#                         )

#                     schedule_rows = (
#                         _get_valid_deferred_schedule_rows(
#                             product_doc
#                         )
#                     )

#                     source_date = getdate(
#                         row.creation
#                     )

#                     first_due_date = add_to_date(
#                         source_date.replace(day=1),
#                         months=1,
#                         as_string=True,
#                     )

#                     total_deferred_commission = 0
#                     total_deferred_rate = 0

#                     for schedule in schedule_rows:
#                         year_no = schedule["year_no"]
#                         schedule_rate = schedule["rate"]

#                         item_gross = (
#                             eligible_amount
#                             * schedule_rate
#                         ) / 100

#                         item_financial = (
#                             _calculate_financial_values_with_settings(
#                                 commission_amount=item_gross,
#                                 eligible_amount=eligible_amount,
#                                 pan_status=row.pan_status,
#                                 calculation_settings=calculation_settings,
#                             )
#                         )

#                         item_gross = flt(
#                             item_financial[
#                                 "commission_amount"
#                             ]
#                         )

#                         item_tds = flt(
#                             item_financial["tds"]
#                         )

#                         item_security_deposit = flt(
#                             item_financial[
#                                 "security_deposit"
#                             ]
#                         )

#                         item_netpay = flt(
#                             item_financial["netpay"]
#                         )

#                         due_date = add_to_date(
#                             first_due_date,
#                             years=year_no - 1,
#                             as_string=True,
#                         )

#                         deferred_item_rows.append(
#                             (
#                                 frappe.generate_hash(length=10),
#                                 now_ts,
#                                 now_ts,
#                                 current_user,
#                                 current_user,
#                                 0,
#                                 len(deferred_item_rows) + 1,
#                                 commission_name,
#                                 "commission_items",
#                                 "Commission",
#                                 "Deferred",
#                                 year_no,
#                                 schedule_rate,
#                                 eligible_amount,
#                                 item_gross,
#                                 due_date,
#                                 "Pending",
#                                 item_tds,
#                                 item_security_deposit,
#                                 item_netpay,
#                                 schedule["remarks"],
#                             )
#                         )

#                         total_deferred_commission += item_gross
#                         total_deferred_rate += schedule_rate

#                     commission_amount = (
#                         total_deferred_commission
#                     )
#                     rate = total_deferred_rate

#                 else:
#                     raise frappe.ValidationError(
#                         _(
#                             "Invalid Commission Type '{0}' in Product: {1}. "
#                             "Allowed values are Fixed Rate, Age Based, "
#                             "Eligible Amount Based, and Deferred."
#                         ).format(
#                             commission_type,
#                             scheme_code,
#                         )
#                     )

#                 if rate is None:
#                     raise frappe.ValidationError(
#                         _(
#                             "Unable to determine commission rate "
#                             "for Product: {0}"
#                         ).format(scheme_code)
#                     )

#                 if rate < 0:
#                     raise frappe.ValidationError(
#                         _(
#                             "Commission rate cannot be negative"
#                         )
#                     )

#                 if not is_deferred:
#                     commission_amount = (
#                         eligible_amount * rate
#                     ) / 100

#                 financial_values = (
#                     _calculate_financial_values_with_settings(
#                         commission_amount=commission_amount,
#                         eligible_amount=eligible_amount,
#                         pan_status=row.pan_status,
#                         calculation_settings=calculation_settings,
#                     )
#                 )

#                 final_commission_amount = flt(
#                     financial_values["commission_amount"]
#                 )

#                 final_tds = flt(
#                     financial_values["tds"]
#                 )

#                 final_security_deposit = flt(
#                     financial_values["security_deposit"]
#                 )

#                 final_netpay = flt(
#                     financial_values["netpay"]
#                 )

#                 final_eligible_amount = flt(
#                     _round_amount_with_settings(
#                         eligible_amount,
#                         calculation_settings,
#                     )
#                 )

#                 final_commission_amount = flt(
#                     _round_amount_with_settings(
#                         final_commission_amount,
#                         calculation_settings,
#                     )
#                 )

#                 final_tds = flt(
#                     _round_amount_with_settings(
#                         final_tds,
#                         calculation_settings,
#                     )
#                 )

#                 final_security_deposit = flt(
#                     _round_amount_with_settings(
#                         final_security_deposit,
#                         calculation_settings,
#                     )
#                 )

#                 final_netpay = flt(
#                     _round_amount_with_settings(
#                         final_netpay,
#                         calculation_settings,
#                     )
#                 )

#                 if not is_deferred:
#                     commission_item_rows.append(
#                         (
#                             frappe.generate_hash(length=10),
#                             now_ts,
#                             now_ts,
#                             current_user,
#                             current_user,
#                             0,
#                             1,
#                             commission_name,
#                             "commission_items",
#                             "Commission",
#                             "Normal",
#                             1,
#                             flt(rate),
#                             final_eligible_amount,
#                             final_commission_amount,
#                             getdate(row.creation),
#                             "Pending",
#                             final_tds,
#                             final_security_deposit,
#                             final_netpay,
#                             commission_type,
#                         )
#                     )

#                     normal_agent_codes.add(
#                         str(row.agent_code).strip()
#                     )

#                 parent_update_rows.append(
#                     (
#                         now_ts,
#                         current_user,
#                         final_eligible_amount,
#                         final_commission_amount,
#                         final_tds,
#                         final_security_deposit,
#                         final_netpay,
#                         flt(rate)
#                         if preloaded[
#                             "has_applied_rate_field"
#                         ]
#                         else None,
#                         commission_type
#                         if preloaded[
#                             "has_commission_type_field"
#                         ]
#                         else None,
#                         agent_total,
#                         commission_name,
#                     )
#                 )

#                 success_count += 1

#             except Exception:
#                 error_count += 1

#                 error_traceback = frappe.get_traceback()

#                 errors.append({
#                     "docname": row.get("name"),
#                     "error": error_traceback,
#                 })

#                 frappe.log_error(
#                     error_traceback,
#                     (
#                         "Optimized Commission Calculation Error - "
#                         f"{row.get('name')}"
#                     ),
#                 )

#         _bulk_update_commission_calculated_fields(
#             parent_update_rows
#         )

#         _bulk_insert_commission_items(
#             commission_item_rows
#         )

#         processed_count += len(commission_rows)

#     if deferred_item_rows:
#         _bulk_insert_commission_items(
#             deferred_item_rows
#         )

#     _update_agent_deduction_for_all_agents_optimized()

#     for agent_code in sorted(normal_agent_codes):
#         try:
#             _create_normal_agent_payment_if_missing(
#                 agent_code
#             )

#         except Exception:
#             error_count += 1

#             error_traceback = frappe.get_traceback()

#             errors.append({
#                 "agent_code": agent_code,
#                 "error": error_traceback,
#             })

#             frappe.log_error(
#                 error_traceback,
#                 (
#                     "Optimized Normal Commission Payment Error - "
#                     f"{agent_code}"
#                 ),
#             )

#     _create_missing_deferred_payments_optimized()

#     frappe.db.commit()

#     return {
#         "status": "completed",
#         "total_processed": processed_count,
#         "success_count": success_count,
#         "error_count": error_count,
#         "errors": errors,
#     }


@frappe.whitelist()
def calculate_commission_for_all_optimized(
    batch_size=5000,
    show_progress=False,
):
    """
    Optimized bulk commission calculation.

    - Non-Deferred records are calculated in batches.
    - Deferred records use the existing calculate_commission_amount()
      method to preserve deferred schedule and payment behavior.
    - show_progress=True displays a terminal progress bar.
    """
    frappe.only_for(("System Manager",))

    _validate_commission_calculation_enabled()

    batch_size = cint(batch_size) or 5000
    show_progress = cint(show_progress)

    commission_names = frappe.get_all(
        "Commission",
        filters={
            "docstatus": ("<", 2),
        },
        pluck="name",
        order_by="creation asc",
    )

    total_records = len(commission_names)

    if not total_records:
        return {
            "status": "completed",
            "total_processed": 0,
            "success_count": 0,
            "error_count": 0,
            "errors": [],
        }

    success_count = 0
    error_count = 0
    errors = []

    progress = None

    if show_progress:
        from tqdm import tqdm

        progress = tqdm(
            total=total_records,
            desc="Calculating Commission",
            unit="record",
            dynamic_ncols=True,
            leave=True,
        )

    try:
        for start in range(0, total_records, batch_size):
            batch_names = commission_names[
                start:start + batch_size
            ]

            batch_result = (
                _calculate_commission_batch(
                    commission_names=batch_names,
                )
            )

            success_count += batch_result[
                "success_count"
            ]

            error_count += batch_result[
                "error_count"
            ]

            errors.extend(
                batch_result["errors"]
            )

            if progress:
                progress.update(len(batch_names))
                progress.set_postfix(
                    success=success_count,
                    errors=error_count,
                )

            frappe.db.commit()

    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            frappe.get_traceback(),
            "Optimized Commission Calculation Failed",
        )
        raise

    finally:
        if progress:
            progress.close()

    result = {
        "status": "completed",
        "total_processed": total_records,
        "success_count": success_count,
        "error_count": error_count,
        "errors": errors,
    }

    if show_progress:
        print("\n\n========== Commission Calculation Result ==========")
        print(f"Status          : {result['status'].upper()}")
        print(f"Total Processed : {total_records}")
        print(f"Success Count   : {success_count}")
        print(f"Error Count     : {error_count}")
        print("===================================================")

    return result


def _calculate_commission_batch(commission_names):
    """
    Calculate one batch of Commission records.

    Deferred records are processed using the existing method.
    Non-Deferred records are calculated and updated in bulk.
    """
    success_count = 0
    error_count = 0
    errors = []

    rows = frappe.db.sql(
        """
        SELECT
            name,
            agent_code,
            scheme_code,
            eligible_amount,
            remarks,
            pan_status,
            creation
        FROM `tabCommission`
        WHERE name IN %s
        AND docstatus < 2
        """,
        (tuple(commission_names),),
        as_dict=True,
    )

    rows_by_name = {
        row.name: row for row in rows
    }

    deferred_names = []
    normal_names = []

    product_cache = (
        _get_product_calculation_cache()
    )

    for docname in commission_names:
        row = rows_by_name.get(docname)

        if not row:
            error_count += 1
            errors.append({
                "docname": docname,
                "error": "Commission record not found",
            })
            continue

        scheme_code = str(
            row.scheme_code or ""
        ).strip()

        product = product_cache.get(scheme_code)

        if not product:
            error_count += 1
            errors.append({
                "docname": docname,
                "error": (
                    f"No Product found with Product Code: "
                    f"{scheme_code}"
                ),
            })
            continue

        if product.commission_type == "Deferred":
            deferred_names.append(docname)
        else:
            normal_names.append(docname)

    # Deferred records must use the existing full method
    # because they create yearly schedule and payment records.
    for docname in deferred_names:
        try:
            calculate_commission_amount(docname)
            success_count += 1

        except Exception:
            error_count += 1
            traceback = frappe.get_traceback()

            errors.append({
                "docname": docname,
                "error": traceback,
            })

            frappe.log_error(
                traceback,
                f"Commission Calculation Error - {docname}",
            )

    # Non-Deferred records are calculated in bulk.
    normal_result = (
        _calculate_non_deferred_commission_batch(
            commission_names=normal_names,
            rows_by_name=rows_by_name,
            product_cache=product_cache,
            normal_names=normal_names,
        )
    )

    success_count += normal_result[
        "success_count"
    ]

    error_count += normal_result[
        "error_count"
    ]

    errors.extend(
        normal_result["errors"]
    )

    return {
        "success_count": success_count,
        "error_count": error_count,
        "errors": errors,
    }


def _get_product_calculation_cache():
    """
    Load all Product calculation fields once.
    """
    products = frappe.get_all(
        "Product",
        fields=[
            "name",
            "commission_type",
            "commission_rate",
            "commission_rate_upto_one_year",
            "commission_rate_above_one_year",
            "slab_1_limit",
            "slab_1_rate",
            "slab_2_limit",
            "slab_2_rate",
            "slab_3_rate",
        ],
    )

    return {
        product.name: product
        for product in products
    }


def _calculate_non_deferred_commission_batch(
    commission_names,
    rows_by_name,
    product_cache,
    normal_names,
):
    """
    Calculate Fixed Rate, Age Based, and Eligible Amount Based
    Commission records in bulk without changing calculation logic.
    """
    success_count = 0
    error_count = 0
    errors = []

    calculation_settings = (
        _get_commission_calculation_settings()
    )

    scheme_groups = (
        _get_eligible_amount_scheme_groups()
    )

    update_values = []
    commission_items = []

    eligible_group_rows = []

    now_ts = now_datetime()

    for docname in commission_names:
        row = rows_by_name[docname]

        try:
            scheme_code = str(
                row.scheme_code or ""
            ).strip()

            product = product_cache[scheme_code]

            commission_type = (
                product.commission_type
            )

            eligible_amount = flt(
                row.eligible_amount
            )

            if eligible_amount < 0:
                raise Exception(
                    "Eligible Amount cannot be negative"
                )

            rate = None

            if commission_type == "Fixed Rate":
                if product.commission_rate in (None, ""):
                    raise Exception(
                        f"Commission Rate is required for Product: {scheme_code}"
                    )

                rate = flt(
                    product.commission_rate
                )

            elif commission_type == "Age Based":
                remarks = str(
                    row.remarks or ""
                ).strip().upper()

                if remarks == "YES":
                    if product.commission_rate_upto_one_year in (None, ""):
                        raise Exception(
                            f"Commission Rate Upto One Year is required for Product: {scheme_code}"
                        )

                    rate = flt(
                        product.commission_rate_upto_one_year
                    )

                elif remarks == "NO":
                    if product.commission_rate_above_one_year in (None, ""):
                        raise Exception(
                            f"Commission Rate Above One Year is required for Product: {scheme_code}"
                        )

                    rate = flt(
                        product.commission_rate_above_one_year
                    )

                else:
                    raise Exception(
                        f"Remarks must be YES or NO for Age Based Product: {scheme_code}"
                    )

            elif commission_type == "Eligible Amount Based":
                required_fields = {
                    "Slab 1 Limit": product.slab_1_limit,
                    "Slab 1 Rate": product.slab_1_rate,
                    "Slab 2 Limit": product.slab_2_limit,
                    "Slab 2 Rate": product.slab_2_rate,
                    "Slab 3 Rate": product.slab_3_rate,
                }

                for label, value in required_fields.items():
                    if value in (None, ""):
                        raise Exception(
                            f"{label} is required for Product: {scheme_code}"
                        )

                eligible_group_rows.append({
                    "docname": docname,
                    "agent_code": str(
                        row.agent_code or ""
                    ).strip(),
                    "scheme_code": scheme_code,
                    "eligible_amount": eligible_amount,
                    "product": product,
                })

                # Actual rate is calculated after agent-group totals.
                update_values.append(None)
                commission_items.append(None)
                success_count += 1
                continue

            else:
                raise Exception(
                    f"Invalid Commission Type '{commission_type}' in Product: {scheme_code}"
                )

            if rate is None:
                raise Exception(
                    f"Unable to determine commission rate for Product: {scheme_code}"
                )

            if rate < 0:
                raise Exception(
                    "Commission rate cannot be negative"
                )

            commission_amount = (
                eligible_amount * rate
            ) / 100

            financial_values = (
                _calculate_commission_financial_values(
                    commission_amount=commission_amount,
                    eligible_amount=eligible_amount,
                    pan_status=row.pan_status,
                )
            )

            commission_amount = flt(
                financial_values["commission_amount"]
            )

            tds = flt(
                financial_values["tds"]
            )

            security_deposit = flt(
                financial_values["security_deposit"]
            )

            netpay = flt(
                financial_values["netpay"]
            )

            commission_amount = flt(
                _round_calculation_amount(
                    commission_amount,
                    calculation_settings,
                )
            )

            eligible_amount = flt(
                _round_calculation_amount(
                    eligible_amount,
                    calculation_settings,
                )
            )

            tds = flt(
                _round_calculation_amount(
                    tds,
                    calculation_settings,
                )
            )

            security_deposit = flt(
                _round_calculation_amount(
                    security_deposit,
                    calculation_settings,
                )
            )

            netpay = flt(
                _round_calculation_amount(
                    netpay,
                    calculation_settings,
                )
            )

            # update_values.append((
            #     commission_amount,
            #     tds,
            #     security_deposit,
            #     netpay,
            #     rate,
            #     commission_type,
            #     eligible_amount,
            #     docname,
            # ))
            update_values.append((
                commission_amount,
                tds,
                security_deposit,
                netpay,
                eligible_amount,
                docname,
            ))

            commission_items.append((
                frappe.generate_hash(length=10),
                now_ts,
                now_ts,
                "Administrator",
                "Administrator",
                docname,
                "Commission",
                "commission_items",
                0,
                1,
                "Normal",
                1,
                rate,
                eligible_amount,
                commission_amount,
                getdate(row.creation),
                "Pending",
                tds,
                security_deposit,
                netpay,
                commission_type,
            ))

            success_count += 1

        except Exception:
            error_count += 1
            traceback = frappe.get_traceback()

            errors.append({
                "docname": docname,
                "error": traceback,
            })

            frappe.log_error(
                traceback,
                f"Commission Calculation Error - {docname}",
            )

    # Calculate Eligible Amount Based records using
    # agent + scheme-group totals.
    eligible_result = (
        _calculate_eligible_amount_based_batch(
            eligible_group_rows=eligible_group_rows,
            calculation_settings=calculation_settings,
            scheme_groups=scheme_groups,
            now_ts=now_ts,
        )
    )

    update_values.extend(
        eligible_result["update_values"]
    )

    commission_items.extend(
        eligible_result["commission_items"]
    )

    success_count = (
        success_count
        - len(eligible_group_rows)
        + eligible_result["success_count"]
    )

    error_count += eligible_result[
        "error_count"
    ]

    errors.extend(
        eligible_result["errors"]
    )

    # Remove old non-deferred Commission Item rows
    # before inserting fresh rows for this batch.
    if normal_names:
        frappe.db.sql(
            """
            DELETE FROM `tabCommission Item`
            WHERE parenttype = 'Commission'
            AND parentfield = 'commission_items'
            AND commission_type = 'Normal'
            AND parent IN %s
            """,
            (tuple(normal_names),),
        )

    # Bulk update parent Commission fields.
    if update_values:
        update_values = [
            value for value in update_values
            if value is not None
        ]

        # update_sql = """
        #     UPDATE `tabCommission`
        #     SET
        #         commission_amount = %s,
        #         tds = %s,
        #         security_deposit = %s,
        #         netpay = %s,
        #         applied_commission_rate = %s,
        #         commission_type_applied = %s,
        #         eligible_amount = %s
        #     WHERE name = %s
        # """

        update_sql = """
            UPDATE `tabCommission`
            SET
                commission_amount = %s,
                tds = %s,
                security_deposit = %s,
                netpay = %s,
                eligible_amount = %s
            WHERE name = %s
        """

        cursor = frappe.db._cursor

        for i in range(
            0,
            len(update_values),
            2000,
        ):
            cursor.executemany(
                update_sql,
                update_values[
                    i:i + 2000
                ],
            )

    # Bulk insert Commission Item rows.
    item_values = [
        value for value in commission_items
        if value is not None
    ]

    if item_values:
        frappe.db.bulk_insert(
            "Commission Item",
            [
                "name",
                "creation",
                "modified",
                "owner",
                "modified_by",
                "parent",
                "parenttype",
                "parentfield",
                "docstatus",
                "idx",
                "commission_type",
                "year_no",
                "commission_rate",
                "eligible_amount",
                "gross_commission",
                "due_date",
                "status",
                "tds",
                "security_deposit",
                "netpay",
                "remarks",
            ],
            item_values,
            chunk_size=5000,
        )

    # Update agent deduction and final net pay
    # once per affected agent.
    affected_agents = {
        str(
            rows_by_name[docname].agent_code or ""
        ).strip()
        for docname in commission_names
        if rows_by_name.get(docname)
        and rows_by_name[docname].agent_code
    }

    for agent_code in affected_agents:
        _update_agent_deduction_and_final_net_pay(
            agent_code
        )

    # Create or update Normal Commission Payment
    # once per affected agent.
    for agent_code in affected_agents:
        try:
            _create_normal_agent_payment_if_missing(
                agent_code
            )

        except Exception:
            traceback = frappe.get_traceback()

            errors.append({
                "docname": agent_code,
                "error": traceback,
            })

            frappe.log_error(
                traceback,
                f"Normal Commission Payment Error - {agent_code}",
            )

    return {
        "success_count": success_count,
        "error_count": error_count,
        "errors": errors,
    }


def _calculate_eligible_amount_based_batch(
    eligible_group_rows,
    calculation_settings,
    scheme_groups,
    now_ts,
):
    """
    Calculate Eligible Amount Based records using one
    agent + scheme-group total per group.
    """
    success_count = 0
    error_count = 0
    errors = []

    update_values = []
    commission_items = []

    if not eligible_group_rows:
        return {
            "success_count": 0,
            "error_count": 0,
            "errors": [],
            "update_values": update_values,
            "commission_items": commission_items,
        }

    # Fetch agent-group totals once.
    group_totals = {}

    grouped = {}

    for row in eligible_group_rows:
        group = scheme_groups.get(
            row["scheme_code"],
            (row["scheme_code"],),
        )

        key = (
            row["agent_code"],
            group,
        )

        grouped.setdefault(
            key,
            [],
        ).append(row)

    for (
        agent_code,
        group,
    ), rows in grouped.items():

        placeholders = ", ".join(
            ["%s"] * len(group)
        )

        result = frappe.db.sql(
            f"""
            SELECT
                COALESCE(
                    SUM(c.eligible_amount),
                    0
                ) AS total
            FROM `tabCommission` c
            INNER JOIN `tabProduct` p
                ON p.name = c.scheme_code
            WHERE c.agent_code = %s
            AND c.docstatus < 2
            AND p.commission_type = 'Eligible Amount Based'
            AND c.scheme_code IN ({placeholders})
            """,
            tuple(
                [agent_code]
                + list(group)
            ),
            as_dict=True,
        )

        agent_total = flt(
            result[0].total
            if result
            else 0
        )

        agent_total = flt(
            _round_calculation_amount(
                agent_total,
                calculation_settings,
            )
        )

        group_totals[
            (agent_code, group)
        ] = agent_total

    for (
        agent_code,
        group,
    ), rows in grouped.items():

        agent_total = group_totals[
            (agent_code, group)
        ]

        if agent_total <= 0:
            for row in rows:
                error_count += 1
                errors.append({
                    "docname": row["docname"],
                    "error": (
                        f"Total eligible amount for Agent {agent_code} "
                        f"and Scheme Group {', '.join(group)} is zero or invalid."
                    ),
                })

            continue

        # Update agent total once per group.
        placeholders = ", ".join(
            ["%s"] * len(group)
        )

        frappe.db.sql(
            f"""
            UPDATE `tabCommission` c
            INNER JOIN `tabProduct` p
                ON p.name = c.scheme_code
            SET c.agent_total_eligible_collection = %s
            WHERE c.agent_code = %s
            AND c.docstatus < 2
            AND p.commission_type = 'Eligible Amount Based'
            AND c.scheme_code IN ({placeholders})
            """,
            tuple(
                [agent_total, agent_code]
                + list(group)
            ),
        )

        for row in rows:
            try:
                product = row["product"]

                slab_1_limit = flt(
                    product.slab_1_limit
                )

                slab_2_limit = flt(
                    product.slab_2_limit
                )

                if agent_total <= slab_1_limit:
                    rate = flt(
                        product.slab_1_rate
                    )

                elif agent_total <= slab_2_limit:
                    rate = flt(
                        product.slab_2_rate
                    )

                else:
                    rate = flt(
                        product.slab_3_rate
                    )

                eligible_amount = row[
                    "eligible_amount"
                ]

                commission_amount = (
                    eligible_amount * rate
                ) / 100

                financial_values = (
                    _calculate_commission_financial_values(
                        commission_amount=commission_amount,
                        eligible_amount=eligible_amount,
                        pan_status=None,
                    )
                )

                commission_amount = flt(
                    financial_values["commission_amount"]
                )

                tds = flt(
                    financial_values["tds"]
                )

                security_deposit = flt(
                    financial_values[
                        "security_deposit"
                    ]
                )

                netpay = flt(
                    financial_values["netpay"]
                )

                commission_amount = flt(
                    _round_calculation_amount(
                        commission_amount,
                        calculation_settings,
                    )
                )

                eligible_amount = flt(
                    _round_calculation_amount(
                        eligible_amount,
                        calculation_settings,
                    )
                )

                tds = flt(
                    _round_calculation_amount(
                        tds,
                        calculation_settings,
                    )
                )

                security_deposit = flt(
                    _round_calculation_amount(
                        security_deposit,
                        calculation_settings,
                    )
                )

                netpay = flt(
                    _round_calculation_amount(
                        netpay,
                        calculation_settings,
                    )
                )

                # update_values.append((
                #     commission_amount,
                #     tds,
                #     security_deposit,
                #     netpay,
                #     rate,
                #     "Eligible Amount Based",
                #     eligible_amount,
                #     row["docname"],
                # ))
                update_values.append((
                    commission_amount,
                    tds,
                    security_deposit,
                    netpay,
                    eligible_amount,
                    row["docname"],
                ))

                commission_items.append((
                    frappe.generate_hash(length=10),
                    now_ts,
                    now_ts,
                    "Administrator",
                    "Administrator",
                    row["docname"],
                    "Commission",
                    "commission_items",
                    0,
                    1,
                    "Normal",
                    1,
                    rate,
                    eligible_amount,
                    commission_amount,
                    getdate(
                        frappe.db.get_value(
                            "Commission",
                            row["docname"],
                            "creation",
                        )
                    ),
                    "Pending",
                    tds,
                    security_deposit,
                    netpay,
                    "Eligible Amount Based",
                ))

                success_count += 1

            except Exception:
                error_count += 1
                traceback = frappe.get_traceback()

                errors.append({
                    "docname": row["docname"],
                    "error": traceback,
                })

                frappe.log_error(
                    traceback,
                    f"Eligible Amount Commission Error - {row['docname']}",
                )

    return {
        "success_count": success_count,
        "error_count": error_count,
        "errors": errors,
        "update_values": update_values,
        "commission_items": commission_items,
    }


def _update_agent_deduction_for_all_agents_optimized():
    """
    Calculate agent-level deduction and final_net_pay once per agent.

    This produces the same final values as updating the agent after
    every individual Commission calculation.
    """
    agent_totals = frappe.db.sql(
        """
        SELECT
            agent_code,
            COALESCE(
                SUM(
                    CAST(
                        NULLIF(TRIM(netpay), '')
                        AS DECIMAL(18, 2)
                    )
                ),
                0
            ) AS agent_total_netpay
        FROM `tabCommission`
        WHERE agent_code IS NOT NULL
        AND agent_code != ''
        AND docstatus < 2
        GROUP BY agent_code
        """,
        as_dict=True,
    )

    calculation_settings = (
        _get_commission_calculation_settings()
    )

    agent_deduction_rows = []

    for agent_total in agent_totals:
        agent_code = str(
            agent_total.agent_code
        ).strip()

        total_netpay = flt(
            agent_total.agent_total_netpay
        )

        deduction, final_net_pay = (
            _calculate_agent_deduction(
                agent_total_netpay=total_netpay,
                calculation_settings=calculation_settings,
            )
        )

        agent_deduction_rows.append(
            (
                flt(deduction),
                flt(final_net_pay),
                agent_code,
            )
        )

    _bulk_update_agent_deduction(
        agent_deduction_rows
    )


def _create_missing_deferred_payments_optimized():
    """
    Create missing Deferred Commission Payment records from
    Commission Item rows.

    Existing Deferred payments are not changed.
    """
    deferred_items = frappe.db.sql(
        """
        SELECT
            ci.name AS item_name,
            ci.parent AS commission_name,
            ci.year_no,
            ci.due_date,
            ci.gross_commission,
            ci.tds,
            ci.security_deposit,
            ci.netpay,
            ci.status,
            c.agent_code,
            c.agent_operative_account,
            c.agent_saving_account
        FROM `tabCommission Item` ci
        INNER JOIN `tabCommission` c
            ON c.name = ci.parent
        WHERE ci.parenttype = 'Commission'
        AND ci.parentfield = 'commission_items'
        AND ci.commission_type = 'Deferred'
        AND c.docstatus < 2
        """,
        as_dict=True,
    )

    if not deferred_items:
        return

    existing_payments = frappe.get_all(
        "Commission Payment",
        filters={
            "payment_type": "Deferred",
            "docstatus": ("<", 2),
        },
        fields=[
            "name",
            "commission",
            "payment_year",
        ],
    )

    existing_keys = {
        (
            payment.commission,
            cint(payment.payment_year),
        )
        for payment in existing_payments
    }

    calculation_settings = (
        _get_commission_calculation_settings()
    )

    for item in deferred_items:
        payment_year = cint(item.year_no)

        if payment_year <= 0:
            continue

        key = (
            item.commission_name,
            payment_year,
        )

        if key in existing_keys:
            continue

        payment_data = {
            "doctype": "Commission Payment",
            "commission": item.commission_name,
            "agent_code": item.agent_code,
            "agent_operative_account": (
                item.agent_operative_account
            ),
            "agent_saving_account": (
                item.agent_saving_account
            ),
            "payment_type": "Deferred",
            "payment_year": payment_year,
            "due_date": item.due_date,
            "source_deferred_detail": item.item_name,
            "gross_commission": flt(
                item.gross_commission
            ),
            "tds_amount": flt(item.tds),
            "security_deposit_amount": flt(
                item.security_deposit
            ),
            "netpay_amount": flt(item.netpay),
            "deduction_amount": 0,
            "final_netpay": flt(item.netpay),
            "payment_status": (
                "Due"
                if item.status == "Due"
                else "Pending"
            ),
        }

        payment_data = _round_payment_amounts(
            payment_data
        )

        payment_doc = frappe.get_doc(
            payment_data
        )

        payment_doc.insert(
            ignore_permissions=True
        )

        existing_keys.add(key)

    frappe.db.commit()


# def _create_deferred_payment_records(commission_doc):
#     """
#     Create one Commission Payment document for each row in
#     Commission.deferred_commission_details.

#     Each Deferred payment remains linked to its individual Commission record,
#     because every annual installment has its own source record, year, and due date.
#     """
#     if not commission_doc.deferred_commission_details:
#         return {
#             "created_count": 0,
#             "existing_count": 0,
#             "payments": [],
#         }

#     payment_results = []

#     for deferred_row in commission_doc.deferred_commission_details:
#         payment_year = int(deferred_row.year_no or 0)

#         if payment_year <= 0:
#             frappe.throw(
#                 _("Invalid Deferred Year No in Commission: {0}").format(
#                     commission_doc.name
#                 )
#             )

#         if not deferred_row.due_date:
#             frappe.throw(
#                 _("Due Date is required for Deferred Year {0}").format(
#                     payment_year
#                 )
#             )

#         existing_payment = frappe.db.exists(
#             "Commission Payment",
#             {
#                 "commission": commission_doc.name,
#                 "payment_type": "Deferred",
#                 "payment_year": payment_year,
#                 "docstatus": ("<", 2),
#             },
#         )

#         if existing_payment:
#             payment_results.append({
#                 "created": False,
#                 "name": existing_payment,
#             })
#             continue

#         # payment_doc = frappe.get_doc({
#         #     "doctype": "Commission Payment",
#         #     "commission": commission_doc.name,
#         #     "agent_code": commission_doc.agent_code,
#         #     "agent_operative_account": commission_doc.agent_operative_account,
#         #     "agent_saving_account": commission_doc.agent_saving_account,
#         #     "payment_type": "Deferred",
#         #     "payment_year": payment_year,
#         #     "due_date": deferred_row.due_date,
#         #     "source_deferred_detail": deferred_row.name,
#         #     "gross_commission": flt(deferred_row.gross_commission),
#         #     "tds_amount": flt(deferred_row.tds),
#         #     "security_deposit_amount": flt(
#         #         deferred_row.security_deposit
#         #     ),
#         #     "netpay_amount": flt(deferred_row.netpay),
#         #     "deduction_amount": 0,
#         #     "final_netpay": flt(deferred_row.netpay),
#         #     "payment_status": (
#         #         "Due"
#         #         if deferred_row.status == "Due"
#         #         else "Pending"
#         #     ),
#         # })

#         payment_data = {
#             "doctype": "Commission Payment",
#             "commission": commission_doc.name,
#             "agent_code": commission_doc.agent_code,
#             "agent_operative_account": (
#                 commission_doc.agent_operative_account
#             ),
#             "agent_saving_account": (
#                 commission_doc.agent_saving_account
#             ),
#             "payment_type": "Deferred",
#             "payment_year": payment_year,
#             "due_date": deferred_row.due_date,
#             "source_deferred_detail": deferred_row.name,
#             "gross_commission": flt(
#                 deferred_row.gross_commission
#             ),
#             "tds_amount": flt(
#                 deferred_row.tds
#             ),
#             "security_deposit_amount": flt(
#                 deferred_row.security_deposit
#             ),
#             "netpay_amount": flt(
#                 deferred_row.netpay
#             ),
#             "deduction_amount": 0,
#             "final_netpay": flt(
#                 deferred_row.netpay
#             ),
#             "payment_status": (
#                 "Due"
#                 if deferred_row.status == "Due"
#                 else "Pending"
#             ),
#         }

#         payment_data = _round_payment_amounts(
#             payment_data
#         )

#         payment_doc = frappe.get_doc(
#             payment_data
#         )

#         payment_doc.insert(ignore_permissions=True)

#         payment_results.append({
#             "created": True,
#             "name": payment_doc.name,
#         })

#     return {
#         "created_count": sum(
#             1 for payment in payment_results if payment["created"]
#         ),
#         "existing_count": sum(
#             1 for payment in payment_results if not payment["created"]
#         ),
#         "payments": payment_results,
#     }


def _create_deferred_payment_records(commission_doc):
    """
    Create one Commission Payment document for each Deferred row in
    Commission.commission_items.
    """
    if not commission_doc.commission_items:
        return {
            "created_count": 0,
            "existing_count": 0,
            "payments": [],
        }

    payment_results = []

    for deferred_row in commission_doc.commission_items:
        if deferred_row.commission_type != "Deferred":
            continue

        payment_year = int(deferred_row.year_no or 0)

        if payment_year <= 0:
            frappe.throw(
                _("Invalid Deferred Year No in Commission: {0}").format(
                    commission_doc.name
                )
            )

        if not deferred_row.due_date:
            frappe.throw(
                _("Due Date is required for Deferred Year {0}").format(
                    payment_year
                )
            )

        existing_payment = frappe.db.exists(
            "Commission Payment",
            {
                "commission": commission_doc.name,
                "payment_type": "Deferred",
                "payment_year": payment_year,
                "docstatus": ("<", 2),
            },
        )

        if existing_payment:
            payment_results.append({
                "created": False,
                "name": existing_payment,
            })
            continue

        payment_data = {
            "doctype": "Commission Payment",
            "commission": commission_doc.name,
            "agent_code": commission_doc.agent_code,
            "agent_operative_account": (
                commission_doc.agent_operative_account
            ),
            "agent_saving_account": (
                commission_doc.agent_saving_account
            ),
            "payment_type": "Deferred",
            "payment_year": payment_year,
            "due_date": deferred_row.due_date,
            "source_deferred_detail": deferred_row.name,
            "gross_commission": flt(
                deferred_row.gross_commission
            ),
            "tds_amount": flt(
                deferred_row.tds
            ),
            "security_deposit_amount": flt(
                deferred_row.security_deposit
            ),
            "netpay_amount": flt(
                deferred_row.netpay
            ),
            "deduction_amount": 0,
            "final_netpay": flt(
                deferred_row.netpay
            ),
            "payment_status": (
                "Due"
                if deferred_row.status == "Due"
                else "Pending"
            ),
        }

        payment_data = _round_payment_amounts(
            payment_data
        )

        payment_doc = frappe.get_doc(
            payment_data
        )

        payment_doc.insert(ignore_permissions=True)

        payment_results.append({
            "created": True,
            "name": payment_doc.name,
        })

    return {
        "created_count": sum(
            1 for payment in payment_results if payment["created"]
        ),
        "existing_count": sum(
            1 for payment in payment_results if not payment["created"]
        ),
        "payments": payment_results,
    }


def _get_product_with_deferred_schedule(product_name):
    """
    Load complete Product document because deferred schedule is a child table.
    """
    product_doc = frappe.get_doc("Product", product_name)

    if product_doc.commission_type != "Deferred":
        frappe.throw(
            _("Product {0} is not configured as Deferred").format(
                product_name
            )
        )

    if not product_doc.deferred_commission_schedule:
        frappe.throw(
            _("Deferred Commission Schedule is missing in Product: {0}").format(
                product_name
            )
        )

    return product_doc


def _validate_deferred_schedule(product_doc):
    """
    Validate enabled Product deferred commission schedule rows.
    Returns schedule rows sorted by year_no.
    """
    enabled_rows = []
    used_years = set()

    for row in product_doc.deferred_commission_schedule:
        if not row.enabled:
            continue

        year_no = cint(row.year_no)
        commission_rate = flt(row.commission_rate)

        if year_no <= 0:
            frappe.throw(
                _("Deferred Year No must be greater than zero in Product: {0}").format(
                    product_doc.name
                )
            )

        if year_no in used_years:
            frappe.throw(
                _("Duplicate Deferred Year No {0} in Product: {1}").format(
                    year_no,
                    product_doc.name
                )
            )

        if commission_rate < 0:
            frappe.throw(
                _("Deferred Commission Rate cannot be negative for Year {0}").format(
                    year_no
                )
            )

        used_years.add(year_no)
        enabled_rows.append({
            "year_no": year_no,
            "commission_rate": commission_rate,
            "remarks": _safe_str(row.remarks),
        })

    if not enabled_rows:
        frappe.throw(
            _("No enabled Deferred Commission Schedule rows found in Product: {0}").format(
                product_doc.name
            )
        )

    return sorted(enabled_rows, key=lambda row: row["year_no"])


def _generate_deferred_commission_schedule(commission_doc, product_doc, eligible_amount):
    """
    Generate the full annual deferred payout schedule in the Commission child table.

    Due-date rule:
    - Year 1: first day of next calendar month after Commission record creation.
    - Year 2: one year after Year 1 due date.
    - Year N: Year 1 due date plus N-1 years.

    Example:
    Commission created on 2026-08-19:
    - Year 1 due: 2026-09-01
    - Year 2 due: 2027-09-01
    """
    commission_meta = frappe.get_meta("Commission")

    if not commission_meta.has_field("deferred_commission_details"):
        frappe.throw(
            _("Commission field 'deferred_commission_details' does not exist")
        )

    if commission_doc.deferred_commission_details:
        frappe.throw(
            _("Deferred commission schedule already exists for Commission: {0}").format(
                commission_doc.name
            )
        )

    schedule_rows = _validate_deferred_schedule(product_doc)

    # Commission document creation date controls the deferred due cycle.
    source_date = getdate(commission_doc.creation)

    # First day of next month.
    first_due_date = add_to_date(
        source_date.replace(day=1),
        months=1,
        as_string=True,
    )

    total_deferred_amount = 0
    total_deferred_rate = 0

    for schedule in schedule_rows:
        year_no = schedule["year_no"]
        rate = schedule["commission_rate"]

        # gross_commission = (eligible_amount * rate) / 100
        # tds = gross_commission * 0.02
        # security_deposit = gross_commission * 0.10
        # netpay = gross_commission - (tds + security_deposit)

        gross_commission = (
            eligible_amount * rate
        ) / 100

        financial_values = (
            _calculate_commission_financial_values(
                commission_amount=gross_commission,
                eligible_amount=eligible_amount,
                pan_status=commission_doc.pan_status,
            )
        )

        gross_commission = flt(
            financial_values["commission_amount"]
        )

        tds = flt(
            financial_values["tds"]
        )

        security_deposit = flt(
            financial_values["security_deposit"]
        )

        netpay = flt(
            financial_values["netpay"]
        )

        due_date = add_to_date(
            first_due_date,
            years=year_no - 1,
            as_string=True,
        )

        commission_doc.append(
            "deferred_commission_details",
            {
                "year_no": year_no,
                "commission_rate": rate,
                "eligible_amount": eligible_amount,
                "gross_commission": gross_commission,
                "due_date": due_date,
                "status": "Pending",
                "tds": tds,
                "security_deposit": security_deposit,
                "netpay": netpay,
                "remarks": schedule["remarks"],
            },
        )

        total_deferred_amount += gross_commission
        total_deferred_rate += rate

    return {
        "total_deferred_amount": total_deferred_amount,
        "total_deferred_rate": total_deferred_rate,
        "first_due_date": first_due_date,
        "schedule_count": len(schedule_rows),
    }


# @frappe.whitelist()
# def calculate_commission_for_all():
#     """
#     Calculate commission on ALL Commission documents.
#     Calls calculate_commission_amount(docname) for each document.
#     """
#     frappe.only_for(("System Manager",))
#     _validate_commission_calculation_enabled()

#     # Get all Commission names
#     commission_names = frappe.get_all(
#         "Commission",
#         filters={"docstatus": ("<", 2)},  # ignore cancelled if any
#         pluck="name",
#     )

#     if not commission_names:
#         return {
#             "status": "completed",
#             "total_processed": 0,
#             "success_count": 0,
#             "error_count": 0,
#             "errors": [],
#         }

#     success_count = 0
#     error_count = 0
#     errors = []

#     for docname in commission_names:
#         try:
#             # Call existing method
#             calculate_commission_amount(docname)
#             success_count += 1
#         except Exception:
#             error_count += 1
#             errors.append(
#                 f"{docname}: {frappe.get_traceback()}"
#             )
#             # Optionally log
#             frappe.log_error(
#                 frappe.get_traceback(),
#                 f"Commission Calculation Error - {docname}",
#             )

#     return {
#         "status": "completed",
#         "total_processed": len(commission_names),
#         "success_count": success_count,
#         "error_count": error_count,
#         "errors": errors,
#     }


# @frappe.whitelist()
# def calculate_commission_for_all_with_progress_bar():
#     """
#     Calculate commission on all Commission documents with a terminal
#     progress bar using tqdm.

#     Displays progress, successful calculations, errors, and final status.
#     """
#     from tqdm import tqdm

#     frappe.only_for(("System Manager",))
#     _validate_commission_calculation_enabled()

#     commission_names = frappe.get_all(
#         "Commission",
#         filters={"docstatus": ("<", 2)},
#         pluck="name",
#     )

#     total_records = len(commission_names)
#     success_count = 0
#     error_count = 0
#     errors = []

#     if not commission_names:
#         result = {
#             "status": "completed",
#             "total_processed": 0,
#             "success_count": 0,
#             "error_count": 0,
#             "errors": [],
#         }
#         print("\nCommission Calculation Result")
#         print("Status: Completed")
#         print("Total Processed: 0")
#         print("Success Count: 0")
#         print("Error Count: 0")
#         return result

#     with tqdm(
#         total=total_records,
#         desc="Calculating Commission",
#         unit="record",
#         dynamic_ncols=True,
#         leave=True,
#     ) as progress:

#         for docname in commission_names:
#             try:
#                 calculate_commission_amount(docname)
#                 success_count += 1

#             except Exception:
#                 error_count += 1
#                 error_traceback = frappe.get_traceback()

#                 errors.append({
#                     "docname": docname,
#                     "error": error_traceback,
#                 })

#                 frappe.log_error(
#                     error_traceback,
#                     f"Commission Calculation Error - {docname}",
#                 )

#             finally:
#                 progress.update(1)
#                 progress.set_postfix(
#                     success=success_count,
#                     errors=error_count,
#                 )

#     result = {
#         "status": "completed",
#         "total_processed": total_records,
#         "success_count": success_count,
#         "error_count": error_count,
#         "errors": errors,
#     }

#     print("\n\n========== Commission Calculation Result ==========")
#     print(f"Status          : {result['status'].upper()}")
#     print(f"Total Processed : {total_records}")
#     print(f"Success Count   : {success_count}")
#     print(f"Error Count     : {error_count}")
#     print("===================================================")

#     return result


@frappe.whitelist()
def calculate_commission_for_all():
    """
    Calculate commission on all Commission documents
    using the optimized bulk calculation method.
    """
    return calculate_commission_for_all_optimized(
        batch_size=5000,
        show_progress=False,
    )


@frappe.whitelist()
def calculate_commission_for_all_with_progress_bar():
    """
    Calculate commission on all Commission documents
    using the optimized bulk calculation method.
    Shows a terminal progress bar.
    """
    return calculate_commission_for_all_optimized(
        batch_size=5000,
        show_progress=True,
    )
#


@frappe.whitelist()
def calculate_commission_for_selected(commission_names):
    """
    Calculate commission only for the selected Commission documents.
    Uses the existing calculate_commission_amount() method.
    """
    frappe.only_for(("System Manager",))
    _validate_commission_calculation_enabled()

    if isinstance(commission_names, str):
        commission_names = frappe.parse_json(commission_names)

    if not commission_names:
        frappe.throw(_("Please select at least one Commission record."))

    # Remove duplicates while preserving order.
    commission_names = list(dict.fromkeys(commission_names))

    success_count = 0
    error_count = 0
    errors = []

    for docname in commission_names:
        try:
            # Validate that the document exists.
            if not frappe.db.exists("Commission", docname):
                frappe.throw(
                    _("Commission document {0} does not exist.").format(
                        docname
                    )
                )

            # Run the existing calculation method.
            calculate_commission_amount(docname)
            success_count += 1

        except Exception:
            error_count += 1
            errors.append({
                "docname": docname,
                "error": frappe.get_traceback(),
            })

            frappe.log_error(
                frappe.get_traceback(),
                f"Selected Commission Calculation Error - {docname}",
            )

    return {
        "status": "completed",
        "total_processed": len(commission_names),
        "success_count": success_count,
        "error_count": error_count,
        "errors": errors,
    }


# @frappe.whitelist()
# def mark_due_deferred_commissions(payment_date=None):
#     """
#     Mark deferred schedule rows as Due when their due_date has arrived.
#     Actual payment remains a manual action.
#     """
#     frappe.only_for(("System Manager",))

#     payment_date = getdate(payment_date) if payment_date else getdate()

#     result = frappe.db.sql(
#         """
#         UPDATE `tabDeferred Commission Detail`
#         SET status = 'Due'
#         WHERE parenttype = 'Commission'
#         AND parentfield = 'deferred_commission_details'
#         AND status = 'Pending'
#         AND due_date <= %s
#         """,
#         payment_date,
#     )

#     frappe.db.commit()

#     return {
#         "status": "success",
#         "payment_date": payment_date,
#         "message": _("Deferred commission rows marked as Due"),
#     }


@frappe.whitelist()
def mark_due_deferred_commissions(payment_date=None):
    """
    Mark Deferred Commission Item rows as Due when their due_date has arrived.
    Actual payment remains a manual action.
    """
    frappe.only_for(("System Manager",))

    payment_date = getdate(payment_date) if payment_date else getdate()

    result = frappe.db.sql(
        """
        UPDATE `tabCommission Item`
        SET status = 'Due'
        WHERE parenttype = 'Commission'
        AND parentfield = 'commission_items'
        AND commission_type = 'Deferred'
        AND status = 'Pending'
        AND due_date <= %s
        """,
        payment_date,
    )

    frappe.db.commit()

    return {
        "status": "success",
        "payment_date": payment_date,
        "message": _("Deferred commission rows marked as Due"),
    }


# @frappe.whitelist()
# def get_due_deferred_commissions(payment_date=None):
#     """
#     Return Deferred Commission Detail rows that are due and not yet paid.
#     """
#     frappe.only_for(("System Manager",))

#     payment_date = getdate(payment_date) if payment_date else getdate()

#     return frappe.db.sql(
#         """
#         SELECT
#             c.name AS commission_name,
#             c.agent_code,
#             c.agent_name,
#             c.scheme_code,
#             c.customer_account_number,
#             c.customer_account_name,
#             d.name AS deferred_detail_name,
#             d.year_no,
#             d.commission_rate,
#             d.eligible_amount,
#             d.gross_commission,
#             d.tds,
#             d.security_deposit,
#             d.netpay,
#             d.due_date,
#             d.status
#         FROM `tabDeferred Commission Detail` d
#         INNER JOIN `tabCommission` c
#             ON c.name = d.parent
#         WHERE d.parenttype = 'Commission'
#         AND d.parentfield = 'deferred_commission_details'
#         AND d.status IN ('Pending', 'Due')
#         AND d.due_date <= %s
#         AND c.docstatus < 2
#         ORDER BY d.due_date, c.agent_code, c.name
#         """,
#         payment_date,
#         as_dict=True,
#     )


@frappe.whitelist()
def get_due_deferred_commissions(payment_date=None):
    """
    Return Deferred Commission Item rows that are due and not yet paid.
    """
    frappe.only_for(("System Manager",))

    payment_date = getdate(payment_date) if payment_date else getdate()

    return frappe.db.sql(
        """
        SELECT
            c.name AS commission_name,
            c.agent_code,
            c.agent_name,
            c.scheme_code,
            c.customer_account_number,
            c.customer_account_name,
            d.name AS deferred_detail_name,
            d.year_no,
            d.commission_rate,
            d.eligible_amount,
            d.gross_commission,
            d.tds,
            d.security_deposit,
            d.netpay,
            d.due_date,
            d.status
        FROM `tabCommission Item` d
        INNER JOIN `tabCommission` c
            ON c.name = d.parent
        WHERE d.parenttype = 'Commission'
        AND d.parentfield = 'commission_items'
        AND d.commission_type = 'Deferred'
        AND d.status IN ('Pending', 'Due')
        AND d.due_date <= %s
        AND c.docstatus < 2
        ORDER BY d.due_date, c.agent_code, c.name
        """,
        payment_date,
        as_dict=True,
    )


# @frappe.whitelist()
# def mark_deferred_commission_paid(
#     commission_name,
#     deferred_detail_name,
#     payment_reference=None,
#     paid_on=None,
# ):
#     """
#     Mark exactly one deferred annual installment as paid.
#     Stops duplicate payment of the same year.
#     """
#     frappe.only_for(("System Manager",))

#     paid_on = getdate(paid_on) if paid_on else getdate()

#     commission_doc = frappe.get_doc("Commission", commission_name)

#     deferred_row = next(
#         (
#             row for row in commission_doc.deferred_commission_details
#             if row.name == deferred_detail_name
#         ),
#         None,
#     )

#     if not deferred_row:
#         frappe.throw(_("Deferred Commission Detail row not found"))

#     if deferred_row.status == "Paid":
#         frappe.throw(
#             _("Deferred commission for Year {0} is already paid").format(
#                 deferred_row.year_no
#             )
#         )

#     if getdate(deferred_row.due_date) > paid_on:
#         frappe.throw(
#             _("This deferred commission is not due until {0}").format(
#                 deferred_row.due_date
#             )
#         )

#     deferred_row.status = "Paid"
#     deferred_row.paid_on = paid_on
#     deferred_row.payment_reference = payment_reference

#     commission_doc.save(ignore_permissions=True)
#     frappe.db.commit()

#     return {
#         "status": "success",
#         "commission_name": commission_doc.name,
#         "year_no": deferred_row.year_no,
#         "gross_commission": deferred_row.gross_commission,
#         "tds": deferred_row.tds,
#         "security_deposit": deferred_row.security_deposit,
#         "netpay": deferred_row.netpay,
#         "paid_on": paid_on,
#         "payment_reference": payment_reference,
#         "message": _("Deferred commission installment marked as paid"),
#     }


@frappe.whitelist()
def mark_deferred_commission_paid(
    commission_name,
    deferred_detail_name,
    payment_reference=None,
    paid_on=None,
):
    """
    Mark exactly one deferred annual installment as paid.
    Stops duplicate payment of the same year.
    """
    frappe.only_for(("System Manager",))

    paid_on = getdate(paid_on) if paid_on else getdate()

    commission_doc = frappe.get_doc("Commission", commission_name)

    deferred_row = next(
        (
            row for row in commission_doc.commission_items
            if row.name == deferred_detail_name
        ),
        None,
    )

    if not deferred_row:
        frappe.throw(_("Commission Item row not found"))

    if deferred_row.commission_type != "Deferred":
        frappe.throw(
            _("Commission Item row is not a Deferred commission row")
        )

    if deferred_row.status == "Paid":
        frappe.throw(
            _("Deferred commission for Year {0} is already paid").format(
                deferred_row.year_no
            )
        )

    if getdate(deferred_row.due_date) > paid_on:
        frappe.throw(
            _("This deferred commission is not due until {0}").format(
                deferred_row.due_date
            )
        )

    deferred_row.status = "Paid"
    deferred_row.paid_on = paid_on
    deferred_row.payment_reference = payment_reference

    commission_doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "status": "success",
        "commission_name": commission_doc.name,
        "year_no": deferred_row.year_no,
        "gross_commission": deferred_row.gross_commission,
        "tds": deferred_row.tds,
        "security_deposit": deferred_row.security_deposit,
        "netpay": deferred_row.netpay,
        "paid_on": paid_on,
        "payment_reference": payment_reference,
        "message": _("Deferred commission installment marked as paid"),
    }


@frappe.whitelist()
def get_commission_status_counts():
    """
    Return total, calculated, and not-calculated Commission counts.
    A Commission is calculated when netpay has a value.
    """
    # frappe.only_for(("System Manager",))
    frappe.only_for(("System Manager", "Commission Admin User"))

    result = frappe.db.sql(
        """
        SELECT
            COUNT(name) AS total_records,
            SUM(
                CASE
                    WHEN IFNULL(netpay, '') != ''
                    THEN 1
                    ELSE 0
                END
            ) AS calculated_records,
            SUM(
                CASE
                    WHEN IFNULL(netpay, '') = ''
                    THEN 1
                    ELSE 0
                END
            ) AS not_calculated_records
        FROM `tabCommission`
        """,
        as_dict=True,
    )

    data = result[0] if result else {}

    return {
        "total_records": cint(
            data.get("total_records") or 0
        ),
        "calculated_records": cint(
            data.get("calculated_records") or 0
        ),
        "not_calculated_records": cint(
            data.get("not_calculated_records") or 0
        ),
    }
