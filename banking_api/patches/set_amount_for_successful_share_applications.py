import frappe
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from tqdm import tqdm


PATCH_DATE = date(2026, 8, 4)
# PATCH_DATE = date(2026, 6, 22)


def parse_fund_transfer_date(value):
    """
    Convert fund_transfer_date into a Python date.

    Supports:
    - Python datetime
    - Python date
    - DD-MM-YYYY string
    - YYYY-MM-DD string
    - YYYY-MM-DD HH:MM:SS string
    """

    if not value:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    value = str(value).strip()

    if not value:
        return None

    date_formats = [
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M:%S.%f",
    ]

    for date_format in date_formats:
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue

    return None


def get_half_amount(transaction_amount):
    """
    Return transaction_amount divided by 2.

    Explicitly returns 0 when transaction_amount is zero or empty.
    """

    if transaction_amount in (None, "", 0, "0", 0.0, "0.0"):
        return 0

    try:
        amount = Decimal(str(transaction_amount))
        return amount / Decimal("2")
    except (InvalidOperation, TypeError, ValueError):
        return 0


def execute():
    records = frappe.get_all(
        "Share Application",
        filters={
            "payment_status": "Success"
        },
        fields=[
            "name",
            "payment_status",
            "fund_transfer_date",
            "transaction_amount",
            "amount"
        ],
        order_by="name asc"
    )

    eligible_records = []

    for row in records:
        if row.get("payment_status") != "Success":
            continue

        transfer_date = parse_fund_transfer_date(
            row.get("fund_transfer_date")
        )

        if not transfer_date:
            continue

        if transfer_date < PATCH_DATE:
            continue

        eligible_records.append(row)

    updated_count = 0
    skipped_count = 0
    failed_count = 0

    with tqdm(
        total=len(eligible_records),
        desc="Updating Share Application amount",
        unit="record",
        ncols=120
    ) as progress_bar:

        for row in eligible_records:
            docname = row.get("name")

            if not docname:
                skipped_count += 1
                progress_bar.update(1)
                continue

            try:
                transaction_amount = row.get("transaction_amount")
                amount = get_half_amount(transaction_amount)

                frappe.db.set_value(
                    "Share Application",
                    docname,
                    "amount",
                    amount,
                    update_modified=False
                )

                frappe.db.commit()

                updated_count += 1

            except Exception:
                frappe.db.rollback()
                failed_count += 1

                frappe.log_error(
                    frappe.get_traceback(),
                    f"Set Amount Patch Failed - Share Application {docname}"
                )

            progress_bar.update(1)
            progress_bar.set_postfix(
                updated=updated_count,
                failed=failed_count,
                skipped=skipped_count
            )

    frappe.logger().info(
        "Set Amount Patch Completed: "
        f"eligible={len(eligible_records)}, "
        f"updated={updated_count}, "
        f"failed={failed_count}, "
        f"skipped={skipped_count}"
    )
