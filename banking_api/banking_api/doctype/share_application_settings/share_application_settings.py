# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

from datetime import timedelta
import frappe
import psycopg2
import psycopg2.extras
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, now
import random
from datetime import datetime
import time

from tqdm import tqdm
import requests
import xmltodict
from requests.exceptions import ConnectionError, HTTPError, ReadTimeout, Timeout


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


def cint_safe(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def get_share_application_query():
    return """
        SELECT *
        FROM (
            SELECT 
                g.cif_id AS cif_id,
                a.relationshipopeningdate AS cif_opening_date,
                g.foracid AS account_no,
                g.acct_opn_date AS acct_opn_date,
                g.sol_id AS sol_id,
                s.sol_desc AS sol_desc,
                g.acct_name AS acct_name,
                g.clr_bal_amt AS clr_bal_amt,
                g.schm_code AS schm_code,
                g2.schm_desc AS schm_desc,
                g.frez_code AS frez_code,
                g.schm_type AS schm_type,
                g.acct_cls_date AS acct_cls_date,
                g.acct_cls_flg AS acct_cls_flg,
                adr.name AS customer_name,
                adr.address_line1 AS address_line1,
                adr.address_line2 AS address_line2,
                concat_ws(', ', adr.address_line1, adr.address_line2) AS address,
                CASE
                    WHEN cif_htd.cif_id IS NOT NULL THEN 'DEDUCTED'
                    ELSE 'NOT DEDUCTED'
                END AS remark,
                CASE
                    WHEN g.clr_bal_amt >= 20 THEN 'SUFFICIENT BALANCE'
                    ELSE 'INSUFFICIENT BALANCE'
                END AS balance_status,
                CASE
                    WHEN acc_htd.acid IS NOT NULL THEN 'YES'
                    ELSE NULL
                END AS share_fund_status,
                ROW_NUMBER() OVER (
                    PARTITION BY g.cif_id
                    ORDER BY CASE g.schm_code
                        WHEN '1001' THEN 1
                        WHEN '1002' THEN 2
                        WHEN '1003' THEN 3
                        WHEN '1004' THEN 4
                        WHEN '1005' THEN 5
                        WHEN '1006' THEN 6
                        WHEN '1008' THEN 7
                        WHEN '1010' THEN 8
                        WHEN '1009' THEN 9
                        WHEN '1011' THEN 10
                        WHEN '1012' THEN 11
                        WHEN '1013' THEN 12
                        WHEN '1101' THEN 13
                        WHEN '1102' THEN 14
                        WHEN '1103' THEN 15
                        WHEN '1104' THEN 16
                        WHEN '1105' THEN 17
                        WHEN '1117' THEN 18
                        ELSE 999
                    END,
                    g.foracid
                ) AS rn
            FROM tbaadm.gam g
            JOIN tbaadm.sol s ON g.sol_id = s.sol_id
            JOIN tbaadm.gsp g2 ON g.schm_code = g2.schm_code

            LEFT JOIN LATERAL (
                SELECT orgkey, relationshipopeningdate
                FROM crmuser.accounts a
                WHERE a.orgkey = g.cif_id
                    AND a.relationshipopeningdate <= CURRENT_DATE
                ORDER BY a.relationshipopeningdate DESC
                LIMIT 1
            ) a ON TRUE

            LEFT JOIN LATERAL (
                SELECT
                    adr.orgkey,
                    adr.name,
                    adr.address_line1,
                    adr.address_line2
                FROM crmuser.address adr
                WHERE adr.orgkey = g.cif_id
                ORDER BY adr.name NULLS LAST
                LIMIT 1
            ) adr ON TRUE

            LEFT JOIN (
                SELECT DISTINCT g.cif_id
                FROM tbaadm.htd h
                JOIN tbaadm.gam g ON h.acid = g.acid
                WHERE h.tran_particular = 'SHARE FUND DEBITED'
                AND h.part_tran_type = 'D'
                AND g.cif_id IN (
                    SELECT DISTINCT g2.cif_id
                    FROM tbaadm.gam g2
                    WHERE g2.schm_code IN (
                        '1001','1002','1003','1004','1005','1006','1008','1010',
                        '1009','1011','1012','1013','1101','1102','1103','1104',
                        '1105','1117'
                    )
                    AND g2.entity_cre_flg = 'Y'
                    AND g2.del_flg = 'N'
                    AND g2.acct_cls_flg = 'N'
                )
            ) cif_htd ON g.cif_id = cif_htd.cif_id

            LEFT JOIN (
                SELECT DISTINCT h.acid
                FROM tbaadm.htd h
                WHERE h.tran_particular = 'SHARE FUND DEBITED'
                AND h.part_tran_type = 'D'
            ) acc_htd ON g.acid = acc_htd.acid

            WHERE g.schm_code IN (
                '1001','1002','1003','1004','1005','1006','1008','1010',
                '1009','1011','1012','1013','1101','1102','1103','1104',
                '1105','1117'
            )
            AND g.entity_cre_flg = 'Y'
            AND g.del_flg = 'N'
            AND g.acct_cls_flg = 'N'
            AND cif_htd.cif_id IS NULL
            AND a.relationshipopeningdate IS NOT NULL
        ) AS final_data
        WHERE rn = 1;
    """


def run_share_application_sync():
    settings = frappe.get_single("Share Application Settings")

    if not settings.enable_sync:
        return {
            "status": "skipped",
            "message": "Share Application Sync is disabled."
        }

    conn = None
    cursor = None
    created_count = 0
    skipped_count = 0
    total_rows = 0

    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        query = get_share_application_query()
        cursor.execute(query)

        existing_cifs = set(
            str(cif).strip()
            for cif in frappe.get_all("Share Application", pluck="cif")
            if cif is not None
        )

        with tqdm(
            total=None,
            desc="Share Application Sync",
            unit="row",
            ncols=120
        ) as pbar:

            while True:
                row = cursor.fetchone()
                if not row:
                    break

                total_rows += 1

                cif_id = row.get("cif_id")
                foracid = row.get("account_no")
                sol_id = row.get("sol_id")
                cif_opening_date = row.get("cif_opening_date")

                if cif_id is None:
                    skipped_count += 1
                    pbar.update(1)
                    pbar.set_postfix(
                        created=created_count,
                        skipped=skipped_count
                    )
                    continue

                cif_id_str = str(cif_id).strip()
                if cif_id_str in existing_cifs:
                    skipped_count += 1
                    pbar.update(1)
                    pbar.set_postfix(
                        created=created_count,
                        skipped=skipped_count
                    )
                    continue

                try:
                    doc = frappe.new_doc("Share Application")
                    doc.cif = cif_id
                    doc.account_number = foracid
                    doc.sol_id = sol_id
                    doc.cif_creation_date = cif_opening_date
                    doc.status = "Pending"
                    doc.customer_name = row.get(
                        "customer_name") or row.get("acct_name") or ""
                    doc.address = row.get("address") or ""
                    doc.scheme_code = row.get("schm_code") or ""
                    doc.scheme_type = row.get("schm_type") or ""
                    doc.account_opening_date = row.get("acct_opn_date")

                    doc.insert(ignore_permissions=True)
                    frappe.db.commit()

                    existing_cifs.add(cif_id_str)
                    created_count += 1

                except Exception:
                    frappe.db.rollback()
                    skipped_count += 1
                    frappe.log_error(
                        frappe.get_traceback(),
                        f"Share Application Sync Row Failed - CIF {cif_id}"
                    )

                pbar.update(1)
                pbar.set_postfix(
                    created=created_count,
                    skipped=skipped_count
                )

        frappe.db.set_single_value(
            "Share Application Settings",
            "last_sync_run",
            now()
        )
        frappe.db.commit()

        return {
            "status": "success",
            "total_rows": total_rows,
            "created_count": created_count,
            "skipped_count": skipped_count,
            "message": (
                f"Sync completed. Total fetched: {total_rows}, "
                f"created: {created_count}, skipped existing/errors: {skipped_count}."
            )
        }

    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            frappe.get_traceback(),
            "Share Application Sync Failed"
        )
        raise

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@frappe.whitelist()
def run_share_application_sync_manual():
    current_hour = now_datetime().hour

    # Run only from 10 AM to 6 PM
    if not (10 <= current_hour <= 18):
        return {
            "status": "skipped",
            "message": "Share Application Sync runs only between 10 AM and 6 PM."
        }

    return run_share_application_sync()


# def hourly_share_application_sync():
#     settings = frappe.get_single("Share Application Settings")

#     if not settings.enable_sync:
#         return

#     if (settings.sync_timing or "").strip() != "Hourly":
#         return

#     # run_share_application_sync()
#     run_share_application_sync_and_payment()


# def daily_share_application_sync():
#     settings = frappe.get_single("Share Application Settings")

#     if not settings.enable_sync:
#         return

#     if (settings.sync_timing or "").strip() != "Daily":
#         return

#     # run_share_application_sync()
#     run_share_application_sync_and_payment()


def _set_share_application_error(
    docname,
    error_message,
    account_closed=0,
    insufficient_balance=0,
    account_frozen=0
):
    if not docname:
        return

    frappe.db.set_value(
        "Share Application",
        docname,
        {
            "error_log": (error_message or "")[:65535],
            "payment_status": "Failed",
            "account_closed": account_closed,
            "insufficient_balance": insufficient_balance,
            "account_frozen": account_frozen
        },
        update_modified=True
    )


@frappe.whitelist()
def pay_now_share_application(entry_name):

    settings = frappe.get_single("Share Application Settings")
    lock_name = f"share_application_pay_now::{entry_name}"

    if not entry_name:

        frappe.throw(_("Share Application document name is required."))

    if not settings.enable_fund_transfer:

        return {
            "status": "skipped",
            "message": "Fund transfer is disabled in Share Application Settings."
        }

    if not settings.finacle_api_url:

        frappe.throw(
            _("Finacle API URL is mandatory in Share Application Settings."))

    share_amount = cint_safe(settings.share_account_credit_amount, 0)
    member_fee_amount = cint_safe(settings.member_fee_credit_amount, 0)
    total_debit_amount = share_amount + member_fee_amount

    if not settings.share_account_gl:

        frappe.throw(
            _("Share Account GL is mandatory in Share Application Settings."))

    if not settings.share_member_fee_gl:

        frappe.throw(
            _("Share Member Fee GL is mandatory in Share Application Settings."))

    if share_amount <= 0 and member_fee_amount <= 0:

        frappe.throw(
            _("At least one credit amount must be greater than zero."))

    if total_debit_amount <= 0:

        frappe.throw(_("Total debit amount must be greater than zero."))

    try:
        if frappe.cache().get_value(lock_name):

            frappe.throw(
                _("A fund transfer is already in progress for this Share Application."))
        frappe.cache().set_value(lock_name, frappe.session.user, expires_in_sec=120)

    except frappe.ValidationError:
        raise
    except Exception as lock_error:

        pass

    try:
        doc = frappe.get_doc("Share Application", entry_name)

        if doc.docstatus != 0:

            return {
                "status": "warning",
                "message": "Only draft Share Application documents can be processed."
            }

        if doc.payment_status == "Success":

            return {
                "status": "warning",
                "message": "This Share Application is already processed successfully."
            }

        debit_account = str(doc.account_number).strip(
        ) if doc.account_number else ""

        if not debit_account:
            error_message = "Account Number is missing on Share Application."

            _set_share_application_error(
                doc.name,
                error_message,
                account_closed=0,
                insufficient_balance=0
            )
            frappe.db.commit()
            return {
                "status": "error",
                "message": error_message
            }

        conn = None
        cursor = None
        try:

            conn = db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            closed_account_query = """
                SELECT
                    foracid,
                    acct_name,
                    cust_id,
                    schm_code,
                    acct_opn_date,
                    acct_cls_flg,
                    acct_cls_date
                FROM tbaadm.gam
                WHERE foracid = %s
                  AND (
                        (acct_cls_flg = 'N' AND acct_cls_date IS NOT NULL)
                        OR
                        (acct_cls_flg = 'Y' AND acct_cls_date IS NOT NULL)
                      )
            """
            cursor.execute(closed_account_query, (debit_account,))
            closed_account_row = cursor.fetchone()

            if closed_account_row:
                error_message = f"Debit account number is closed: {debit_account}"

                _set_share_application_error(
                    doc.name,
                    error_message,
                    account_closed=1,
                    insufficient_balance=0
                )
                frappe.db.commit()
                return {
                    "status": "error",
                    "message": error_message
                }

            balance_query = """
                SELECT
                    g.foracid,
                    g.acct_name,
                    g.sol_id,
                    g.clr_bal_amt
                FROM tbaadm.gam g
                WHERE g.del_flg = 'N'
                  AND g.foracid = %s
            """
            cursor.execute(balance_query, (debit_account,))
            balance_row = cursor.fetchone()

            if not balance_row:
                error_message = f"Debit account not found or inactive: {debit_account}"

                _set_share_application_error(
                    doc.name,
                    error_message,
                    account_closed=0,
                    insufficient_balance=0
                )
                frappe.db.commit()
                return {
                    "status": "error",
                    "message": error_message
                }

            available_balance = float(balance_row.get("clr_bal_amt") or 0)

            if available_balance < float(total_debit_amount):
                error_message = (
                    f"Insufficient balance in debit account {debit_account}. "
                    f"Available balance is {available_balance}, required amount is {total_debit_amount}."
                )

                _set_share_application_error(
                    doc.name,
                    error_message,
                    account_closed=0,
                    insufficient_balance=1
                )
                frappe.db.commit()
                return {
                    "status": "error",
                    "message": error_message
                }

        except Exception as db_check_error:
            error_message = f"Debit account validation failed: {str(db_check_error)}"

            _set_share_application_error(
                doc.name,
                error_message,
                account_closed=0,
                insufficient_balance=0
            )
            frappe.db.commit()
            return {
                "status": "error",
                "message": error_message
            }
        finally:
            if cursor:
                cursor.close()

            if conn:
                conn.close()

        current_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        guid = random.randint(1000000000, 9999999999)
        url = settings.finacle_api_url

        xml_parts = []
        xml_parts.append(
            f"""<PartTrnRec><AcctId><AcctId>{debit_account}</AcctId></AcctId><CreditDebitFlg>D</CreditDebitFlg><TrnAmt><amountValue>{total_debit_amount}</amountValue><currencyCode>INR</currencyCode></TrnAmt><TrnParticulars>Share Fund Debited</TrnParticulars><ValueDt>{current_date}</ValueDt></PartTrnRec>"""
        )

        if share_amount > 0:
            xml_parts.append(
                f"""<PartTrnRec><AcctId><AcctId>{settings.share_account_gl}</AcctId></AcctId><CreditDebitFlg>C</CreditDebitFlg><TrnAmt><amountValue>{share_amount}</amountValue><currencyCode>INR</currencyCode></TrnAmt><TrnParticulars>SHARE ACCOUNT</TrnParticulars><ValueDt>{current_date}</ValueDt></PartTrnRec>"""
            )

        if member_fee_amount > 0:
            xml_parts.append(
                f"""<PartTrnRec><AcctId><AcctId>{settings.share_member_fee_gl}</AcctId></AcctId><CreditDebitFlg>C</CreditDebitFlg><TrnAmt><amountValue>{member_fee_amount}</amountValue><currencyCode>INR</currencyCode></TrnAmt><TrnParticulars>SHARE MEMBER FEE</TrnParticulars><ValueDt>{current_date}</ValueDt></PartTrnRec>"""
            )

        xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
<FIXML xsi:schemaLocation="http://www.finacle.com/fixml XferTrnAdd.xsd" xmlns="http://www.finacle.com/fixml" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <Header>
        <RequestHeader>
            <MessageKey>
                <RequestUUID>{guid}</RequestUUID>
                <ServiceRequestId>XferTrnAdd</ServiceRequestId>
                <ServiceRequestVersion>10.2</ServiceRequestVersion>
                <ChannelId>COR</ChannelId>
            </MessageKey>
            <RequestMessageInfo>
                <BankId>01</BankId>
                <MessageDateTime>{current_date}</MessageDateTime>
            </RequestMessageInfo>
            <Security>
                <Token>
                    <PasswordToken>
                        <UserId></UserId>
                        <Password></Password>
                    </PasswordToken>
                </Token>
            </Security>
        </RequestHeader>
    </Header>
    <Body>
        <XferTrnAddRequest>
            <XferTrnAddRq>
                <XferTrnHdr>
                    <TrnType>T</TrnType>
                    <TrnSubType>CI</TrnSubType>
                </XferTrnHdr>
                <XferTrnDetail>
                    {''.join(xml_parts)}
                </XferTrnDetail>
            </XferTrnAddRq>
        </XferTrnAddRequest>
    </Body>
</FIXML>"""

        try:

            response = requests.post(
                url,
                data=xml_data.encode("utf-8"),
                headers={"Content-Type": "application/xml"},
                verify=False,
                timeout=(10, 30)
            )

            response.raise_for_status()
        except (Timeout, ReadTimeout):
            error_message = "Finacle API timeout occurred while processing the transaction. Transaction status is unknown; verify before retrying."

            _set_share_application_error(
                doc.name,
                error_message,
                account_closed=0,
                insufficient_balance=0
            )
            frappe.db.commit()
            return {
                "status": "error",
                "message": error_message
            }
        except ConnectionError:
            error_message = "Unable to connect to Finacle API. Please verify network or server availability before retrying."

            _set_share_application_error(
                doc.name,
                error_message,
                account_closed=0,
                insufficient_balance=0
            )
            frappe.db.commit()
            return {
                "status": "error",
                "message": error_message
            }
        except HTTPError:
            error_message = f"Finacle API returned HTTP {getattr(response, 'status_code', 'error')}. Response: {getattr(response, 'text', '')}"

            _set_share_application_error(
                doc.name,
                error_message,
                account_closed=0,
                insufficient_balance=0
            )
            frappe.db.commit()
            return {
                "status": "error",
                "message": "Finacle API returned an error response."
            }

        response_text = response.text or ""

        response_text_lower = response_text.lower()

        if "frozen" in response_text_lower or "a/c. is frozen" in response_text_lower:
            error_message = response_text or "Debit account is frozen."
            _set_share_application_error(
                doc.name,
                error_message,
                account_closed=0,
                insufficient_balance=0,
                account_frozen=1
            )
            frappe.db.set_single_value(
                "Share Application Settings", "last_transfer_run", now()
            )
            frappe.db.commit()
            return {
                "status": "error",
                "message": "Fund transfer failed because account is frozen."
            }

        try:
            res_dict = xmltodict.parse(response_text)
        except Exception:
            error_message = f"Unable to parse Finacle API response. Raw response: {response_text}"

            _set_share_application_error(
                doc.name,
                error_message,
                account_closed=0,
                insufficient_balance=0
            )
            frappe.db.commit()
            return {
                "status": "error",
                "message": "Unable to parse Finacle API response."
            }

        fixml_root = res_dict.get("FIXML", {}) if isinstance(
            res_dict, dict) else {}
        header = fixml_root.get("Header", {}) or {}
        response_header = header.get("ResponseHeader", {}) or {}
        host_transaction = response_header.get("HostTransaction", {}) or {}
        body = fixml_root.get("Body", {}) or {}
        xfer_response = body.get("XferTrnAddResponse", {}) or {}
        xfer_rs = xfer_response.get("XferTrnAddRs", {}) or {}
        trn_identifier = xfer_rs.get("TrnIdentifier", {}) or {}

        status = (host_transaction.get("Status") or "").strip().upper()
        transaction_id = (trn_identifier.get("TrnId") or "").strip()

        if status == "SUCCESS" and transaction_id:
            frappe.db.set_value(
                "Share Application",
                doc.name,
                {
                    "transaction_id": transaction_id,
                    "fund_transfer_date": now_datetime(),
                    "payment_status": "Success",
                    "error_log": "",
                    "account_closed": 0,
                    "insufficient_balance": 0,
                    "account_frozen": 0,
                    "transaction_amount": total_debit_amount,
                    "amount": total_debit_amount / 2
                },
                update_modified=True
            )

            frappe.db.set_single_value(
                "Share Application Settings", "last_transfer_run", now()
            )
            frappe.db.set_single_value(
                "Share Application Settings", "total_debit_amount", total_debit_amount
            )

            submitted_doc = frappe.get_doc("Share Application", doc.name)
            if submitted_doc.docstatus == 0:

                submitted_doc.submit()

            frappe.db.commit()

            return {
                "status": "success",
                "message": f"Fund transfer completed successfully. Transaction ID: {transaction_id}",
                "transaction_id": transaction_id
            }

        error_message = response_text or "Finacle API did not return a success status."

        _set_share_application_error(
            doc.name,
            error_message,
            account_closed=0,
            insufficient_balance=0
        )
        frappe.db.set_single_value(
            "Share Application Settings", "last_transfer_run", now()
        )
        frappe.db.commit()
        return {
            "status": "error",
            "message": "Fund transfer failed. Error log updated in Share Application."
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(),
                         "Share Application Pay Now Failed")

        try:
            _set_share_application_error(
                entry_name,
                str(e),
                account_closed=0,
                insufficient_balance=0
            )
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
        return {
            "status": "error",
            "message": str(e)
        }
    finally:
        try:
            frappe.cache().delete_value(lock_name)

        except Exception:
            pass


@frappe.whitelist()
def run_bulk_share_application_payment():
    settings = frappe.get_single("Share Application Settings")

    if not settings.enable_fund_transfer:
        return {
            "status": "skipped",
            "message": "Fund transfer is disabled in Share Application Settings."
        }

    share_applications = frappe.get_all(
        "Share Application",
        filters={
            "payment_status": ["=", "Pending"],
            "docstatus": 0
        },
        fields=["name", "payment_status"]
    )

    if not share_applications:
        return {
            "status": "success",
            "message": "No pending Share Application records found for bulk payment.",
            "processed_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "skipped_count": 0
        }

    processed_count = 0
    success_count = 0
    failed_count = 0
    skipped_count = 0
    result_lines = []

    pause_after_records = 500
    pause_seconds = 10

    with tqdm(
        total=len(share_applications),
        desc="Share Application Payment",
        unit="doc",
        ncols=120,
        position=0,
        leave=True
    ) as pbar:

        for row in share_applications:
            docname = row.get("name")

            if not docname:
                skipped_count += 1
                processed_count += 1

                pbar.update(1)
                pbar.set_postfix(
                    success=success_count,
                    failed=failed_count,
                    skipped=skipped_count
                )
                continue

            processed_count += 1

            try:
                result = pay_now_share_application(docname)

                if isinstance(result, dict):
                    result_status = (result.get("status") or "").lower()
                    result_message = result.get("message") or ""

                    if result_status == "success":
                        success_count += 1
                    elif result_status in ("skipped", "warning"):
                        skipped_count += 1
                    else:
                        failed_count += 1

                    result_lines.append(f"{docname}: {result_message}")
                else:
                    failed_count += 1
                    result_lines.append(
                        f"{docname}: Unexpected response returned.")

            except Exception as e:
                failed_count += 1
                frappe.log_error(
                    frappe.get_traceback(),
                    f"Bulk Share Payment Failed for {docname}"
                )
                result_lines.append(f"{docname}: {str(e)}")

            pbar.update(1)
            pbar.set_postfix(
                success=success_count,
                failed=failed_count,
                skipped=skipped_count
            )

            if processed_count % pause_after_records == 0:
                with tqdm(
                    total=pause_seconds,
                    desc=f"Paused after {processed_count} records | Press Ctrl+Z to stop",
                    unit="sec",
                    ncols=120,
                    position=1,
                    leave=False
                ) as pause_bar:
                    for remaining in range(pause_seconds, 0, -1):
                        pause_bar.set_postfix(remaining=f"{remaining}s")
                        time.sleep(1)
                        pause_bar.update(1)

    return {
        "status": "success" if failed_count == 0 else "warning",
        "message": (
            f"Bulk payment completed. Processed: {processed_count}, "
            f"Success: {success_count}, Failed: {failed_count}, Skipped: {skipped_count}."
            + ("<br><br>" + "<br>".join(result_lines) if result_lines else "")
        ),
        "processed_count": processed_count,
        "success_count": success_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count
    }


def test_progress():
    total_records = 1000
    batch_size = 5

    with tqdm(
        total=total_records,
        desc="Processing Share Applications",
        unit="record",
        ncols=100
    ) as pbar:

        for batch_start in range(1, total_records + 1, batch_size):

            # Process 5 records
            for _ in range(batch_size):
                if pbar.n >= total_records:
                    break

                time.sleep(0.01)  # Your processing logic
                pbar.update(1)

            # Pause after every batch except the last one
            if pbar.n < total_records:
                tqdm.write(
                    f"Processed {pbar.n}/{total_records} records. "
                    "Pausing for 5 seconds... (Press Ctrl+C to stop)"
                )
                time.sleep(5)

    print("\nDone!")


# test_progress()


def process_bulk_record():
    total_records = 35000

    start_time = time.time()
    batch_start = time.time()

    with tqdm(total=total_records, ncols=120) as pbar:

        for i in range(1, total_records + 1):

            # process record
            time.sleep(0.001)

            pbar.update(1)

            if i % 500 == 0:

                batch_time = time.time() - batch_start
                total_time = time.time() - start_time

                rate = i / total_time
                eta = (total_records - i) / rate

                pbar.set_description(
                    f"{i:,}/{total_records:,} ({i/total_records*100:.2f}%) "
                    f"| Batch:{str(timedelta(seconds=int(batch_time)))} "
                    f"| Rate:{rate:.0f}/s "
                    f"| ETA:{str(timedelta(seconds=int(eta)))}"
                )

                time.sleep(5)
                batch_start = time.time()


def run_share_application_sync_and_payment():
    sync_result = run_share_application_sync()

    if not isinstance(sync_result, dict):
        return {
            "status": "warning",
            "message": "Sync did not return a valid response. Bulk payment was not started."
        }

    if sync_result.get("status") != "success":
        return {
            "status": "warning",
            "message": "Share Application sync did not complete successfully. Bulk payment was not started.",
            "sync_result": sync_result
        }

    payment_result = run_bulk_share_application_payment()

    return {
        "status": "success" if payment_result.get("status") == "success" else "warning",
        "sync_result": sync_result,
        "payment_result": payment_result
    }


@frappe.whitelist()
def retry_share_application_payment():
    settings = frappe.get_single("Share Application Settings")

    if not settings.enable_fund_transfer:
        return {
            "status": "skipped",
            "message": "Fund transfer is disabled in Share Application Settings."
        }

    share_applications = frappe.get_all(
        "Share Application",
        filters={
            "payment_status": ["=", "Failed"],
            "docstatus": 0
        },
        fields=["name", "payment_status", "retry_attempted"]
    )

    if not share_applications:
        return {
            "status": "success",
            "message": "No pending Share Application records found for bulk payment.",
            "processed_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "skipped_count": 0
        }

    processed_count = 0
    success_count = 0
    failed_count = 0
    skipped_count = 0
    result_lines = []

    pause_after_records = 500
    pause_seconds = 10

    with tqdm(
        total=len(share_applications),
        desc="Share Application Payment",
        unit="doc",
        ncols=120,
        position=0,
        leave=True
    ) as pbar:

        for row in share_applications:
            docname = row.get("name")

            if not docname:
                skipped_count += 1
                processed_count += 1

                pbar.update(1)
                pbar.set_postfix(
                    success=success_count,
                    failed=failed_count,
                    skipped=skipped_count
                )
                continue

            processed_count += 1

            try:
                current_retry = row.get("retry_attempted") or 0
                frappe.db.set_value(
                    "Share Application", docname, "retry_attempted", current_retry + 1)
                frappe.db.set_value(
                    "Share Application", docname, "last_retry_attempted", frappe.utils.now())

                result = pay_now_share_application(docname)

                if isinstance(result, dict):
                    result_status = (result.get("status") or "").lower()
                    result_message = result.get("message") or ""

                    if result_status == "success":
                        success_count += 1
                    elif result_status in ("skipped", "warning"):
                        skipped_count += 1
                    else:
                        failed_count += 1

                    result_lines.append(f"{docname}: {result_message}")
                else:
                    failed_count += 1
                    result_lines.append(
                        f"{docname}: Unexpected response returned.")

            except Exception as e:
                failed_count += 1
                frappe.log_error(
                    frappe.get_traceback(),
                    f"Bulk Share Payment Failed for {docname}"
                )
                result_lines.append(f"{docname}: {str(e)}")

            pbar.update(1)
            pbar.set_postfix(
                success=success_count,
                failed=failed_count,
                skipped=skipped_count
            )

            if processed_count % pause_after_records == 0:
                with tqdm(
                    total=pause_seconds,
                    desc=f"Paused after {processed_count} records | Press Ctrl+Z to stop",
                    unit="sec",
                    ncols=120,
                    position=1,
                    leave=False
                ) as pause_bar:
                    for remaining in range(pause_seconds, 0, -1):
                        pause_bar.set_postfix(remaining=f"{remaining}s")
                        time.sleep(1)
                        pause_bar.update(1)

    return {
        "status": "success" if failed_count == 0 else "warning",
        "message": (
            f"Bulk payment completed. Processed: {processed_count}, "
            f"Success: {success_count}, Failed: {failed_count}, Skipped: {skipped_count}."
            + ("<br><br>" + "<br>".join(result_lines) if result_lines else "")
        ),
        "processed_count": processed_count,
        "success_count": success_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count
    }


@frappe.whitelist()
def get_share_certificate_image():
    image = frappe.db.get_single_value(
        "Share Application Settings",
        "share_certificate_image"
    )

    if not image:
        return {
            "status": "error",
            "message": "Share Certificate Image is not set in Share Application Settings."
        }

    return {
        "status": "success",
        "image_url": image
    }
