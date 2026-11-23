# # Copyright (c) 2026, Talib Sheikh and contributors
# # For license information, please see license.txt

# import frappe
# from frappe import _
# from frappe.model.document import Document
# from frappe.utils import flt


# class CommissionPayment(Document):
#     def validate(self):
#         self.validate_payment_reference()
#         self.calculate_final_netpay()

#     def validate_payment_reference(self):
#         if self.payment_type not in ("Normal", "Deferred"):
#             frappe.throw(
#                 _("Payment Type must be Normal or Deferred")
#             )

#         if not self.agent_code:
#             frappe.throw(
#                 _("Agent Code is required")
#             )

#         if not self.agent_operative_account:
#             frappe.throw(
#                 _("Agent Operative Account is required")
#             )

#         if not self.payment_year or self.payment_year <= 0:
#             frappe.throw(
#                 _("Payment Year must be greater than zero")
#             )

#         if not self.due_date:
#             frappe.throw(
#                 _("Due Date is required")
#             )

#         # Deferred payment must point to one exact Commission record
#         # and one exact source child schedule row.
#         if self.payment_type == "Deferred":
#             if not self.commission:
#                 frappe.throw(
#                     _("Commission is required for Deferred payment")
#                 )

#             if not self.source_deferred_detail:
#                 frappe.throw(
#                     _("Source Deferred Detail is required for Deferred payment")
#                 )

#             existing_payment = frappe.db.exists(
#                 "Commission Payment",
#                 {
#                     "commission": self.commission,
#                     "payment_type": "Deferred",
#                     "payment_year": self.payment_year,
#                     "docstatus": ("<", 2),
#                 },
#             )

#             if existing_payment and existing_payment != self.name:
#                 frappe.throw(
#                     _(
#                         "Deferred Commission Payment already exists for "
#                         "Commission {0}, Payment Year {1}"
#                     ).format(
#                         self.commission,
#                         self.payment_year,
#                     )
#                 )

#         # Normal payment is consolidated agent-wise.
#         # It may intentionally have no single Commission Link.
#         elif self.payment_type == "Normal":
#             existing_payment = frappe.db.exists(
#                 "Commission Payment",
#                 {
#                     "agent_code": self.agent_code,
#                     "payment_type": "Normal",
#                     "due_date": self.due_date,
#                     "docstatus": ("<", 2),
#                 },
#             )

#             if existing_payment and existing_payment != self.name:
#                 frappe.throw(
#                     _(
#                         "Normal Commission Payment already exists for "
#                         "Agent {0} and Due Date {1}"
#                     ).format(
#                         self.agent_code,
#                         self.due_date,
#                     )
#                 )

#     def calculate_final_netpay(self):
#         gross_commission = flt(self.gross_commission)
#         tds_amount = flt(self.tds_amount)
#         security_deposit_amount = flt(self.security_deposit_amount)
#         deduction_amount = flt(self.deduction_amount)

#         calculated_netpay = (
#             gross_commission
#             - tds_amount
#             - security_deposit_amount
#         )

#         # Preserve the source value when it has been supplied.
#         # Otherwise calculate it from Gross - TDS - Security Deposit.
#         if self.netpay_amount in (None, ""):
#             self.netpay_amount = calculated_netpay

#         self.final_netpay = (
#             flt(self.netpay_amount)
#             - deduction_amount
#         )

#         if flt(self.final_netpay) < 0:
#             frappe.throw(
#                 _("Final Net Pay cannot be negative")
#             )

############################################################################################################################


# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt
#
import random
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from xml.sax.saxutils import escape as xml_escape

import frappe
import requests
import xmltodict
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, now, now_datetime
from requests.exceptions import ConnectionError, ReadTimeout, Timeout


class CommissionPayment(Document):
    def validate(self):
        self.validate_required_payment_fields()
        self.calculate_final_netpay()

    def validate_required_payment_fields(self):
        if self.payment_type not in ("Normal", "Deferred"):
            frappe.throw(
                _("Payment Type must be Normal or Deferred")
            )

        if not self.agent_code:
            frappe.throw(
                _("Agent Code is required")
            )

        if not self.agent_operative_account:
            frappe.throw(
                _("Agent Operative Account is required")
            )
        if not self.agent_saving_account:
            frappe.throw(
                _("Agent Saving Account is required")
            )

        if not self.payment_year or cint(self.payment_year) <= 0:
            frappe.throw(
                _("Payment Year must be greater than zero")
            )

        if not self.due_date:
            frappe.throw(
                _("Due Date is required")
            )

        if self.payment_type == "Deferred":
            self.validate_deferred_payment()

        elif self.payment_type == "Normal":
            self.validate_normal_payment()

    def validate_deferred_payment(self):
        if not self.commission:
            frappe.throw(
                _("Commission is required for Deferred payment")
            )

        if not self.source_deferred_detail:
            frappe.throw(
                _("Source Deferred Detail is required for Deferred payment")
            )

        existing_payment = frappe.db.exists(
            "Commission Payment",
            {
                "commission": self.commission,
                "payment_type": "Deferred",
                "payment_year": self.payment_year,
                "docstatus": ("<", 2),
            },
        )

        if existing_payment and existing_payment != self.name:
            frappe.throw(
                _(
                    "Deferred Commission Payment already exists for "
                    "Commission {0}, Payment Year {1}"
                ).format(
                    self.commission,
                    self.payment_year,
                )
            )

    def validate_normal_payment(self):
        existing_payment = frappe.db.exists(
            "Commission Payment",
            {
                "agent_code": self.agent_code,
                "payment_type": "Normal",
                "due_date": self.due_date,
                "docstatus": ("<", 2),
            },
        )

        if existing_payment and existing_payment != self.name:
            frappe.throw(
                _(
                    "Normal Commission Payment already exists for "
                    "Agent {0}, Due Date {1}"
                ).format(
                    self.agent_code,
                    self.due_date,
                )
            )

    def calculate_final_netpay(self):
        gross_commission = flt(self.gross_commission)
        tds_amount = flt(self.tds_amount)
        security_deposit_amount = flt(
            self.security_deposit_amount
        )
        deduction_amount = flt(self.deduction_amount)

        calculated_netpay = (
            gross_commission
            - tds_amount
            - security_deposit_amount
        )

        if self.netpay_amount in (None, ""):
            self.netpay_amount = calculated_netpay

        self.final_netpay = (
            flt(self.netpay_amount)
            - deduction_amount
        )

        if flt(self.final_netpay) < 0:
            frappe.throw(
                _("Final Net Pay cannot be negative")
            )


def _get_commission_settings():
    """
    Required fields in Commission Settings:
    - enable_commission_payment
    - finacle_api_url
    - debit_account_number
    """
    settings = frappe.get_single("Commission Settings")

    if not getattr(settings, "enable_commission_payment", 0):
        return settings, {
            "allowed": False,
            "message": _(
                "Commission payment is disabled in Commission Settings."
            ),
        }

    if not getattr(settings, "finacle_api_url", None):
        frappe.throw(
            _(
                "Finacle API URL is mandatory in Commission Settings."
            )
        )

    if not getattr(settings, "debit_account_number", None):
        frappe.throw(
            _(
                "Debit Account Number is mandatory in Commission Settings."
            )
        )

    return settings, {
        "allowed": True,
        "message": "",
    }


def _money(amount):
    """
    Convert a Frappe numeric value into a decimal value with two places.
    """
    return Decimal(str(flt(amount))).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def _update_payment_failure(
    payment_doc,
    failure_reason,
    payment_status="Failed",
    increase_retry=True,
):
    """
    Store full failure details in failure_reason.

    IMPORTANT:
    failure_reason must be a Long Text field if it stores complete XML.
    """
    payment_doc = frappe.get_doc(
        "Commission Payment",
        payment_doc.name,
    )

    payment_doc.payment_status = payment_status
    payment_doc.failure_reason = str(failure_reason or "")

    if increase_retry:
        payment_doc.retry_count = cint(
            payment_doc.retry_count
        ) + 1

    payment_doc.save(ignore_permissions=True)
    frappe.db.commit()


# def _build_finacle_xml(
#     debit_account,
#     credit_account,
#     amount,
#     settings,
#     payment_doc,
# ):
#     """
#     Build Finacle XferTrnAdd XML.

#     Debit account:
#         Commission Settings.debit_account_number

#     Credit account:
#         Commission Payment.agent_operative_account

#     Amount:
#         Commission Payment.final_netpay
#     """
#     current_date = datetime.now().strftime(
#         "%Y-%m-%dT%H:%M:%S.%f"
#     )[:-3]

#     request_uuid = random.randint(
#         1000000000,
#         9999999999,
#     )

#     transaction_type = (
#         getattr(settings, "transaction_type", None)
#         or "T"
#     )

#     transaction_sub_type = (
#         getattr(settings, "transaction_sub_type", None)
#         or "CI"
#     )

#     bank_id = (
#         getattr(settings, "bank_id", None)
#         or "01"
#     )

#     channel_id = (
#         getattr(settings, "channel_id", None)
#         or "COR"
#     )

#     debit_particulars = (
#         getattr(settings, "debit_particulars", None)
#         or "Commission Payment Debited"
#     )

#     credit_particulars = (
#         getattr(settings, "credit_particulars", None)
#         or "Agent Commission Credited"
#     )

#     payment_reference = (
#         f"Commission Payment {payment_doc.name} "
#         f"Agent {payment_doc.agent_code}"
#     )

#     debit_account = xml_escape(
#         str(debit_account or "").strip()
#     )

#     credit_account = xml_escape(
#         str(credit_account or "").strip()
#     )

#     transaction_type = xml_escape(
#         str(transaction_type or "").strip()
#     )

#     transaction_sub_type = xml_escape(
#         str(transaction_sub_type or "").strip()
#     )

#     bank_id = xml_escape(
#         str(bank_id or "").strip()
#     )

#     channel_id = xml_escape(
#         str(channel_id or "").strip()
#     )

#     debit_particulars = xml_escape(
#         str(debit_particulars or "").strip()
#     )

#     credit_particulars = xml_escape(
#         str(credit_particulars or "").strip()
#     )

#     payment_reference = xml_escape(
#         str(payment_reference or "").strip()
#     )

#     amount = _money(amount)

#     return f"""<?xml version="1.0" encoding="UTF-8"?>
# <FIXML xsi:schemaLocation="http://www.finacle.com/fixml XferTrnAdd.xsd"
#        xmlns="http://www.finacle.com/fixml"
#        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
#     <Header>
#         <RequestHeader>
#             <MessageKey>
#                 <RequestUUID>{request_uuid}</RequestUUID>
#                 <ServiceRequestId>XferTrnAdd</ServiceRequestId>
#                 <ServiceRequestVersion>10.2</ServiceRequestVersion>
#                 <ChannelId>{channel_id}</ChannelId>
#                 <LanguageId></LanguageId>
#             </MessageKey>
#             <RequestMessageInfo>
#                 <BankId>{bank_id}</BankId>
#                 <TimeZone></TimeZone>
#                 <EntityId></EntityId>
#                 <EntityType></EntityType>
#                 <ArmCorrelationId>{payment_doc.name}</ArmCorrelationId>
#                 <MessageDateTime>{current_date}</MessageDateTime>
#             </RequestMessageInfo>
#             <Security>
#                 <Token>
#                     <PasswordToken>
#                         <UserId></UserId>
#                         <Password></Password>
#                     </PasswordToken>
#                 </Token>
#             </Security>
#         </RequestHeader>
#     </Header>
#     <Body>
#         <XferTrnAddRequest>
#             <XferTrnAddRq>
#                 <XferTrnHdr>
#                     <TrnType>{transaction_type}</TrnType>
#                     <TrnSubType>{transaction_sub_type}</TrnSubType>
#                 </XferTrnHdr>
#                 <XferTrnDetail>
#                     <PartTrnRec>
#                         <AcctId>
#                             <AcctId>{debit_account}</AcctId>
#                         </AcctId>
#                         <CreditDebitFlg>D</CreditDebitFlg>
#                         <TrnAmt>
#                             <amountValue>{amount:.2f}</amountValue>
#                             <currencyCode>INR</currencyCode>
#                         </TrnAmt>
#                         <TrnParticulars>{debit_particulars}</TrnParticulars>
#                         <PartTrnRmks>{payment_reference}</PartTrnRmks>
#                         <ValueDt>{current_date}</ValueDt>
#                     </PartTrnRec>
#                     <PartTrnRec>
#                         <AcctId>
#                             <AcctId>{credit_account}</AcctId>
#                         </AcctId>
#                         <CreditDebitFlg>C</CreditDebitFlg>
#                         <TrnAmt>
#                             <amountValue>{amount:.2f}</amountValue>
#                             <currencyCode>INR</currencyCode>
#                         </TrnAmt>
#                         <TrnParticulars>{credit_particulars}</TrnParticulars>
#                         <PartTrnRmks>{payment_reference}</PartTrnRmks>
#                         <ValueDt>{current_date}</ValueDt>
#                     </PartTrnRec>
#                 </XferTrnDetail>
#             </XferTrnAddRq>
#         </XferTrnAddRequest>
#     </Body>
# </FIXML>"""


def _build_finacle_xml(
    debit_account,
    credit_account,
    amount,
    settings,
    payment_doc,
):
    current_date = datetime.now().strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3]

    request_uuid = random.randint(
        1000000000,
        9999999999,
    )

    debit_particulars = (
        getattr(settings, "debit_particulars", None)
        or "Commission Fund Debited"
    )

    credit_particulars = (
        getattr(settings, "credit_particulars", None)
        or "COMMISSION PAYMENT"
    )

    amount = _money(amount)

    debit_account = xml_escape(
        str(debit_account).strip()
    )

    credit_account = xml_escape(
        str(credit_account).strip()
    )

    debit_particulars = xml_escape(
        str(debit_particulars).strip()
    )

    credit_particulars = xml_escape(
        str(credit_particulars).strip()
    )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<FIXML xsi:schemaLocation="http://www.finacle.com/fixml XferTrnAdd.xsd" xmlns="http://www.finacle.com/fixml" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <Header>
        <RequestHeader>
            <MessageKey>
                <RequestUUID>{request_uuid}</RequestUUID>
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
                    <PartTrnRec>
                        <AcctId>
                            <AcctId>{debit_account}</AcctId>
                        </AcctId>
                        <CreditDebitFlg>D</CreditDebitFlg>
                        <TrnAmt>
                            <amountValue>{amount:.2f}</amountValue>
                            <currencyCode>INR</currencyCode>
                        </TrnAmt>
                        <TrnParticulars>{debit_particulars}</TrnParticulars>
                        <ValueDt>{current_date}</ValueDt>
                    </PartTrnRec>

                    <PartTrnRec>
                        <AcctId>
                            <AcctId>{credit_account}</AcctId>
                        </AcctId>
                        <CreditDebitFlg>C</CreditDebitFlg>
                        <TrnAmt>
                            <amountValue>{amount:.2f}</amountValue>
                            <currencyCode>INR</currencyCode>
                        </TrnAmt>
                        <TrnParticulars>{credit_particulars}</TrnParticulars>
                        <ValueDt>{current_date}</ValueDt>
                    </PartTrnRec>
                </XferTrnDetail>
            </XferTrnAddRq>
        </XferTrnAddRequest>
    </Body>
</FIXML>"""


def _parse_finacle_response(response_text):
    """
    Extract important values from a Finacle XferTrnAdd XML response.

    The complete raw XML is still stored in failure_reason separately.
    """
    try:
        response_dict = xmltodict.parse(response_text)
    except Exception as e:
        return {
            "success": False,
            "transaction_id": "",
            "status": "ERROR",
            "error_code": "",
            "error_description": "",
            "ubus_transaction_id": "",
            "host_transaction_id": "",
            "request_uuid": "",
            "message": (
                "Unable to parse Finacle XML response: "
                f"{str(e)}"
            ),
        }

    fixml = response_dict.get("FIXML", {}) or {}

    header = fixml.get("Header", {}) or {}
    response_header = header.get("ResponseHeader", {}) or {}

    request_message_key = (
        response_header.get("RequestMessageKey", {}) or {}
    )

    host_transaction = (
        response_header.get("HostTransaction", {}) or {}
    )

    ubus_transaction = (
        response_header.get("UBUSTransaction", {}) or {}
    )

    body = fixml.get("Body", {}) or {}

    transfer_response = (
        body.get("XferTrnAddResponse", {}) or {}
    )

    transfer_result = (
        transfer_response.get("XferTrnAddRs", {}) or {}
    )

    transaction_identifier = (
        transfer_result.get("TrnIdentifier", {}) or {}
    )

    error = body.get("Error", {}) or {}

    fi_system_exception = (
        error.get("FISystemException", {}) or {}
    )

    error_detail = (
        fi_system_exception.get("ErrorDetail", {}) or {}
    )

    status = str(
        host_transaction.get("Status") or ""
    ).strip().upper()

    transaction_id = str(
        transaction_identifier.get("TrnId") or ""
    ).strip()

    error_code = str(
        error_detail.get("ErrorCode") or ""
    ).strip()

    error_description = str(
        error_detail.get("ErrorDesc") or ""
    ).strip()

    ubus_transaction_id = str(
        ubus_transaction.get("Id") or ""
    ).strip()

    host_transaction_id = str(
        host_transaction.get("Id") or ""
    ).strip()

    request_uuid = str(
        request_message_key.get("RequestUUID") or ""
    ).strip()

    if status == "SUCCESS" and transaction_id:
        return {
            "success": True,
            "transaction_id": transaction_id,
            "status": status,
            "error_code": "",
            "error_description": "",
            "ubus_transaction_id": ubus_transaction_id,
            "host_transaction_id": host_transaction_id,
            "request_uuid": request_uuid,
            "message": "Finacle transaction completed successfully.",
        }

    message_parts = []

    if error_code:
        message_parts.append(
            f"Finacle Error Code: {error_code}"
        )

    if error_description:
        message_parts.append(error_description)

    if status:
        message_parts.append(
            f"Host Transaction Status: {status}"
        )

    if host_transaction_id:
        message_parts.append(
            f"Host Transaction ID: {host_transaction_id}"
        )

    if ubus_transaction_id:
        message_parts.append(
            f"UBUS Transaction ID: {ubus_transaction_id}"
        )

    if request_uuid:
        message_parts.append(
            f"Request UUID: {request_uuid}"
        )

    return {
        "success": False,
        "transaction_id": transaction_id,
        "status": status or "FAILED",
        "error_code": error_code,
        "error_description": error_description,
        "ubus_transaction_id": ubus_transaction_id,
        "host_transaction_id": host_transaction_id,
        "request_uuid": request_uuid,
        "message": (
            " | ".join(message_parts)
            or "Finacle did not return a success status."
        ),
    }


def _build_failure_reason(
    http_status_code,
    parsed_response,
    raw_finacle_response,
):
    """
    Build the exact content written into failure_reason.

    First part:
        Short readable summary.

    Second part:
        Full raw Finacle XML response.
    """
    summary = (
        f"Finacle HTTP Status: {http_status_code}\n"
        f"Finacle Status: {parsed_response.get('status', '')}\n"
        f"Finacle Error Code: {parsed_response.get('error_code', '')}\n"
        f"Finacle Error Description: "
        f"{parsed_response.get('error_description', '')}\n"
        f"Host Transaction ID: "
        f"{parsed_response.get('host_transaction_id', '')}\n"
        f"UBUS Transaction ID: "
        f"{parsed_response.get('ubus_transaction_id', '')}\n"
        f"Request UUID: "
        f"{parsed_response.get('request_uuid', '')}\n\n"
        f"========== RAW FINACLE RESPONSE ==========\n"
        f"{raw_finacle_response or ''}"
    )

    return summary


@frappe.whitelist()
def pay_now_commission_payment(payment_name):
    """
    Process one Commission Payment through Finacle XferTrnAdd.

    Debit:
        Commission Settings.debit_account_number

    Credit:
        # Commission Payment.agent_operative_account
        Commission Payment.agent_saving_account

    Amount:
        Commission Payment.final_netpay
    """
    if not payment_name:
        frappe.throw(
            _("Commission Payment document name is required.")
        )

    payment_doc = frappe.get_doc(
        "Commission Payment",
        payment_name,
    )

    lock_name = (
        f"commission_payment_pay_now::{payment_doc.name}"
    )

    if payment_doc.docstatus == 2:
        frappe.throw(
            _("Cancelled Commission Payment cannot be processed.")
        )

    if payment_doc.payment_status == "Paid":
        return {
            "status": "warning",
            "message": _(
                "This Commission Payment is already paid."
            ),
            "transaction_id": payment_doc.transaction_id,
        }

    if payment_doc.payment_status == "Processing":
        return {
            "status": "warning",
            "message": _(
                "This Commission Payment is already Processing. "
                "Verify Finacle status before retrying."
            ),
        }

    if payment_doc.payment_status not in (
        "Pending",
        "Due",
        "Failed",
    ):
        return {
            "status": "warning",
            "message": _(
                "Payment cannot be processed with status: {0}"
            ).format(
                payment_doc.payment_status
            ),
        }

    if not payment_doc.agent_operative_account:
        frappe.throw(
            _("Agent Operative Account is required.")
        )
    if not payment_doc.agent_saving_account:
        frappe.throw(
            _("Agent Saving Account is required.")
        )

    payment_amount = _money(
        payment_doc.final_netpay
    )

    if payment_amount <= 0:
        frappe.throw(
            _("Final Net Pay must be greater than zero.")
        )

    settings, control = _get_commission_settings()

    if not control["allowed"]:
        return {
            "status": "skipped",
            "message": control["message"],
        }

    try:
        if frappe.cache().get_value(lock_name):
            frappe.throw(
                _(
                    "A payment is already in progress for this "
                    "Commission Payment."
                )
            )

        frappe.cache().set_value(
            lock_name,
            frappe.session.user,
            expires_in_sec=180,
        )

    except frappe.ValidationError:
        raise

    except Exception:
        pass

    try:
        debit_account = str(
            settings.debit_account_number
        ).strip()

        # credit_account = str(
        #     payment_doc.agent_operative_account
        # ).strip()
        credit_account = str(
            payment_doc.agent_saving_account
        ).strip()

        if not debit_account:
            frappe.throw(
                _(
                    "Debit Account Number is missing in "
                    "Commission Settings."
                )
            )

        if not credit_account:
            frappe.throw(
                _(
                    "Agent Operative Account is missing in "
                    "Commission Payment."
                )
            )

        payment_doc.payment_status = "Processing"
        payment_doc.payment_initiated_on = now_datetime()
        payment_doc.failure_reason = ""

        payment_doc.save(ignore_permissions=True)
        frappe.db.commit()

        xml_data = _build_finacle_xml(
            debit_account=debit_account,
            credit_account=credit_account,
            amount=payment_amount,
            settings=settings,
            payment_doc=payment_doc,
        )

        connect_timeout = cint(
            getattr(
                settings,
                "connection_timeout",
                None,
            )
            or 10
        )

        read_timeout = cint(
            getattr(
                settings,
                "read_timeout",
                None,
            )
            or 30
        )

        ssl_verify = cint(
            getattr(
                settings,
                "ssl_verify",
                0,
            )
        )

        try:
            frappe.log_error(
                title=f"Commission XML - {payment_doc.name}",
                message=xml_data,
            )
            response = requests.post(
                settings.finacle_api_url,
                data=xml_data.encode("utf-8"),
                headers={
                    "Content-Type": "application/xml",
                },
                verify=bool(ssl_verify),
                timeout=(
                    connect_timeout,
                    read_timeout,
                ),
            )

        except (Timeout, ReadTimeout):
            error_message = (
                "Finacle API timeout occurred. Transaction status is "
                "unknown. Verify in Finacle before retrying."
            )

            _update_payment_failure(
                payment_doc=payment_doc,
                failure_reason=error_message,
                payment_status="Processing",
                increase_retry=False,
            )

            return {
                "status": "warning",
                "message": error_message,
            }

        except ConnectionError:
            error_message = (
                "Unable to confirm Finacle API response. Transaction status "
                "is unknown. Verify in Finacle before retrying."
            )

            _update_payment_failure(
                payment_doc=payment_doc,
                failure_reason=error_message,
                payment_status="Processing",
                increase_retry=False,
            )

            return {
                "status": "warning",
                "message": error_message,
            }

        response_text = response.text or ""

        parsed_response = _parse_finacle_response(
            response_text
        )

        if response.status_code >= 400:
            failure_reason = _build_failure_reason(
                http_status_code=response.status_code,
                parsed_response=parsed_response,
                raw_finacle_response=response_text,
            )

            _update_payment_failure(
                payment_doc=payment_doc,
                failure_reason=failure_reason,
                payment_status="Failed",
                increase_retry=True,
            )

            return {
                "status": "error",
                "message": _(
                    "Finacle rejected the commission payment. "
                    "Full Finacle XML response is saved in Failure Reason."
                ),
                "transaction_id": parsed_response.get(
                    "transaction_id",
                    "",
                ),
                "http_status_code": response.status_code,
                "finacle_error_code": parsed_response.get(
                    "error_code",
                    "",
                ),
                "ubus_transaction_id": parsed_response.get(
                    "ubus_transaction_id",
                    "",
                ),
                "host_transaction_id": parsed_response.get(
                    "host_transaction_id",
                    "",
                ),
            }

        if parsed_response["success"]:
            payment_doc = frappe.get_doc(
                "Commission Payment",
                payment_doc.name,
            )

            payment_doc.payment_status = "Paid"
            payment_doc.transaction_id = parsed_response[
                "transaction_id"
            ]

            payment_doc.payment_initiated_on = (
                payment_doc.payment_initiated_on
                or now_datetime()
            )

            payment_doc.paid_on = now_datetime()
            payment_doc.failure_reason = ""

            payment_doc.save(ignore_permissions=True)

            frappe.db.sql(
                """
                UPDATE `tabCommission Item`
                SET status = 'Paid', paid_on = %(paid_on)s
                WHERE payment_reference = %(payment_name)s
                """,
                {
                    "paid_on": payment_doc.paid_on or now_datetime(),
                    "payment_name": payment_doc.name,
                },
            )

            frappe.db.set_single_value(
                "Commission Settings",
                "last_payment_run",
                now(),
            )

            frappe.db.commit()

            return {
                "status": "success",
                "message": _(
                    "Commission payment completed successfully. "
                    "Transaction ID: {0}"
                ).format(
                    parsed_response["transaction_id"]
                ),
                "transaction_id": parsed_response[
                    "transaction_id"
                ],
                "payment_name": payment_doc.name,
                "amount": float(payment_amount),
            }

        failure_reason = _build_failure_reason(
            http_status_code=response.status_code,
            parsed_response=parsed_response,
            raw_finacle_response=response_text,
        )

        _update_payment_failure(
            payment_doc=payment_doc,
            failure_reason=failure_reason,
            payment_status="Failed",
            increase_retry=True,
        )

        return {
            "status": "error",
            "message": _(
                "Commission payment failed. "
                "Full Finacle XML response is saved in Failure Reason."
            ),
            "transaction_id": parsed_response.get(
                "transaction_id",
                "",
            ),
            "http_status_code": response.status_code,
            "finacle_error_code": parsed_response.get(
                "error_code",
                "",
            ),
            "ubus_transaction_id": parsed_response.get(
                "ubus_transaction_id",
                "",
            ),
            "host_transaction_id": parsed_response.get(
                "host_transaction_id",
                "",
            ),
        }

    except Exception:
        error_message = frappe.get_traceback()

        frappe.log_error(
            error_message,
            (
                "Commission Payment API Error - "
                f"{payment_doc.name}"
            ),
        )

        try:
            _update_payment_failure(
                payment_doc=payment_doc,
                failure_reason=error_message,
                payment_status="Failed",
                increase_retry=True,
            )
        except Exception:
            frappe.db.rollback()

        return {
            "status": "error",
            "message": _(
                "Commission payment failed. Check Error Log and Failure Reason."
            ),
        }

    finally:
        try:
            frappe.cache().delete_value(lock_name)
        except Exception:
            pass


@frappe.whitelist()
def run_bulk_commission_payment(payment_names=None):
    """
    Process selected Commission Payment records one at a time.

    Each record calls pay_now_commission_payment(), which means every
    payment receives an independent Finacle request, response, status,
    transaction ID, failure reason, and retry count.
    """
    frappe.only_for(("System Manager",))

    payment_names = (
        frappe.parse_json(payment_names)
        if isinstance(payment_names, str)
        else (payment_names or [])
    )

    if not payment_names:
        frappe.throw(
            _("Select at least one Commission Payment record.")
        )

    payment_names = list(
        dict.fromkeys(payment_names)
    )

    processed_count = 0
    success_count = 0
    failed_count = 0
    skipped_count = 0
    results = []

    for payment_name in payment_names:
        processed_count += 1

        try:
            result = pay_now_commission_payment(
                payment_name
            )

            result_status = str(
                result.get("status") or "error"
            ).lower()

            if result_status == "success":
                success_count += 1

            elif result_status in (
                "warning",
                "skipped",
            ):
                skipped_count += 1

            else:
                failed_count += 1

            results.append({
                "payment_name": payment_name,
                "status": result_status,
                "message": result.get(
                    "message",
                    "",
                ),
                "transaction_id": result.get(
                    "transaction_id",
                    "",
                ),
                "finacle_error_code": result.get(
                    "finacle_error_code",
                    "",
                ),
                "ubus_transaction_id": result.get(
                    "ubus_transaction_id",
                    "",
                ),
                "host_transaction_id": result.get(
                    "host_transaction_id",
                    "",
                ),
            })

        except Exception:
            failed_count += 1

            traceback = frappe.get_traceback()

            frappe.log_error(
                traceback,
                (
                    "Bulk Commission Payment Failed - "
                    f"{payment_name}"
                ),
            )

            results.append({
                "payment_name": payment_name,
                "status": "error",
                "message": _(
                    "Unhandled error. Check Error Log."
                ),
                "transaction_id": "",
                "finacle_error_code": "",
                "ubus_transaction_id": "",
                "host_transaction_id": "",
            })

    frappe.db.set_single_value(
        "Commission Settings",
        "last_payment_run",
        now(),
    )

    frappe.db.commit()

    return {
        "status": (
            "success"
            if failed_count == 0
            else "warning"
        ),
        "message": _(
            "Bulk commission payment completed. Processed: {0}, "
            "Success: {1}, Failed: {2}, Skipped: {3}."
        ).format(
            processed_count,
            success_count,
            failed_count,
            skipped_count,
        ),
        "processed_count": processed_count,
        "success_count": success_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "results": results,
    }


@frappe.whitelist()
def get_linked_commission_records(payment_name=None, agent_code=None, creation=None):
    """
    Fetch all Commission records linked to a Commission Payment record:
    1. Commission.agent_code matches Commission Payment.agent_code
    2. Commission.creation is in the same month and year as Commission Payment.creation
    """
    payment_doc = None
    if payment_name and frappe.db.exists("Commission Payment", payment_name):
        payment_doc = frappe.get_doc("Commission Payment", payment_name)
        agent_code = (agent_code or payment_doc.agent_code or "").strip()
        creation_val = payment_doc.creation
    elif agent_code:
        agent_code = str(agent_code).strip()
        creation_val = creation or now_datetime()
    else:
        return {
            "records": [],
            "count": 0,
            "agent_code": None,
            "period_display": "",
            "totals": {},
        }

    if not agent_code:
        return {
            "records": [],
            "count": 0,
            "agent_code": None,
            "period_display": "",
            "totals": {},
        }

    try:
        creation_dt = frappe.utils.get_datetime(creation_val) if creation_val else now_datetime()
    except Exception:
        creation_dt = now_datetime()

    target_year = creation_dt.year
    target_month = creation_dt.month
    month_name = creation_dt.strftime("%B")
    period_display = f"{month_name} {target_year}"

    records = frappe.db.sql(
        """
        SELECT
            name,
            creation,
            agent_code,
            agent_name,
            customer_account_number,
            customer_account_name,
            scheme_code,
            scheme_description,
            sol_id,
            sol_description,
            deposit_amount,
            collection,
            demand,
            eligible_amount,
            commission_amount,
            tds,
            security_deposit,
            netpay,
            deduction,
            final_net_pay
        FROM `tabCommission`
        WHERE agent_code = %(agent_code)s
          AND YEAR(creation) = %(year)s
          AND MONTH(creation) = %(month)s
          AND docstatus < 2
        ORDER BY creation DESC, name DESC
        """,
        {
            "agent_code": agent_code,
            "year": target_year,
            "month": target_month,
        },
        as_dict=True,
    )

    def _to_flt(val):
        try:
            return float(str(val).strip()) if val not in (None, "") else 0.0
        except (ValueError, TypeError):
            return 0.0

    total_gross = sum(_to_flt(r.get("commission_amount")) for r in records)
    total_tds = sum(_to_flt(r.get("tds")) for r in records)
    total_security = sum(_to_flt(r.get("security_deposit")) for r in records)
    total_netpay = sum(_to_flt(r.get("netpay")) for r in records)
    total_deposit = sum(_to_flt(r.get("deposit_amount")) for r in records)

    # Pick single final_net_pay value without summing
    single_final_netpay = None
    if payment_doc:
        single_final_netpay = _to_flt(payment_doc.final_netpay)
    if not single_final_netpay:
        for r in records:
            if r.get("final_net_pay") not in (None, ""):
                single_final_netpay = _to_flt(r.get("final_net_pay"))
                break
    if single_final_netpay is None:
        single_final_netpay = 0.0

    formatted_records = []
    for r in records:
        rec = dict(r)
        if rec.get("creation"):
            rec["creation_str"] = str(rec["creation"])
            rec["creation_formatted"] = frappe.utils.format_datetime(
                rec["creation"], "yyyy-MM-dd HH:mm"
            )
        else:
            rec["creation_str"] = ""
            rec["creation_formatted"] = "-"
        formatted_records.append(rec)

    return {
        "records": formatted_records,
        "count": len(formatted_records),
        "agent_code": agent_code,
        "month": target_month,
        "month_name": month_name,
        "year": target_year,
        "period_display": period_display,
        "totals": {
            "gross_commission": total_gross,
            "tds": total_tds,
            "security_deposit": total_security,
            "netpay": total_netpay,
            "final_netpay": single_final_netpay,
            "deposit_amount": total_deposit,
        },
    }
