# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt
import base64
import csv
import html
import io
import json
import mimetypes
import os
import random
import re
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, InvalidOperation

import frappe
import psycopg2
from docx import Document as DocxDocument
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from frappe import _
from frappe.model.document import Document
from frappe.utils import formatdate, getdate
from frappe.utils.pdf import get_pdf
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
from PIL import Image
from psycopg2.extras import RealDictCursor


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
        frappe.log_error(
            frappe.get_traceback(),
            "PostgreSQL Connection Failed"
        )
        frappe.throw(
            _("Database Connection Error: {0}").format(str(e))
        )


def cint_safe(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def execute_finacle_query(query, params=None):
    """
    Execute a read-only query against Finacle PostgreSQL and return
    records as Frappe-style dictionaries.
    """
    conn = None
    cursor = None

    try:
        conn = db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute(query, params or ())
        rows = cursor.fetchall()

        return [dict(row) for row in rows]

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "Finacle PostgreSQL Query Failed"
        )
        frappe.throw(_("Unable to fetch data from Finacle database."))

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()


def set_docx_cell_background(cell, hex_color):
    """
    Apply Word table-cell background colour.
    Pass colour without '#', e.g. 'D9E1F2'.
    """
    tc_pr = cell._tc.get_or_add_tcPr()

    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), hex_color.replace("#", ""))
    shading.set(qn("w:val"), "clear")
    tc_pr.append(shading)


def set_docx_cell_text(
    cell,
    value,
    *,
    bold=False,
    alignment=WD_ALIGN_PARAGRAPH.LEFT,
    font_size=8
):
    """Set one formatted paragraph in a DOCX table cell."""
    cell.text = ""
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

    paragraph = cell.paragraphs[0]
    paragraph.alignment = alignment

    paragraph_format = paragraph.paragraph_format
    paragraph_format.space_before = Pt(0)
    paragraph_format.space_after = Pt(0)

    run = paragraph.add_run(str(value if value is not None else ""))
    run.bold = bold
    run.font.name = "Arial"
    run.font.size = Pt(font_size)


def safe_float(value, default=0.0):
    """Convert Finacle numeric values safely for totals."""
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def format_amount(value):
    """Format a numeric loan amount without currency symbol."""
    return "{:,.2f}".format(safe_float(value))


class ShareApplication(Document):
    def autoname(self):
        from frappe import _
        from frappe.model.naming import getseries

        sol_id = str(self.sol_id or "").strip()

        if not sol_id:
            frappe.throw(_("SOL ID is mandatory for naming."))

        if not sol_id.isdigit():
            frappe.throw(_("SOL ID must contain digits only."))

        if len(sol_id) != 4:
            frappe.throw(_("SOL ID must be exactly 4 digits."))

        prefix = f"{sol_id}01"

        for _ in range(5):
            sequence = getseries("Share Application-", 9)
            new_name = f"{prefix}{sequence}"

            if not frappe.db.exists("Share Application", new_name):
                self.name = new_name
                return

        frappe.throw(
            _("Unable to generate a unique Share Application ID. Please try again."))

    def validate(self):
        if self.docstatus == 1:
            if self.payment_status != "Success":
                frappe.throw(
                    _("Only documents with Status = 'Success' can be submitted."))

            if not self.transaction_id:
                frappe.throw(
                    _("Transaction ID is mandatory before submission."))

#########################################################################################


# list of directors
DIRECTORS = [
    "जयेशचंद्र रमण रामादे",
    "दत्तात्रय शायमराव सावंत",
    "आशीष वासुदेव बाहेकर",
    "जितेंद्र इंद्रराज रंगारी",
    "शुभम गोपाल भिमटे"
]


# APP_PATH = frappe.get_app_path("banking_api")
# IMAGES_PATH = os.path.join(APP_PATH, "public", "images")

# JAYESH_SIGN_PATH = os.path.join(IMAGES_PATH, "jayesh_sir_sign.png")
# WASNIK_SIGN_PATH = os.path.join(IMAGES_PATH, "wasnik_sir_sign.png")


def add_page_number(paragraph):
    """Insert an automatic PAGE field into the given paragraph."""
    run = paragraph.add_run()
    fld_char_begin = OxmlElement('w:fldChar')
    fld_char_begin.set(qn('w:fldCharType'), 'begin')
    run._r.append(fld_char_begin)

    instr_text = OxmlElement('w:instrText')
    instr_text.text = "PAGE"
    run._r.append(instr_text)

    fld_char_end = OxmlElement('w:fldChar')
    fld_char_end.set(qn('w:fldCharType'), 'end')
    run._r.append(fld_char_end)


def add_footer_page_number(doc):
    section = doc.sections[0]
    footer = section.footer

    # Use the first footer paragraph (or create one if needed)
    if not footer.paragraphs:
        footer_para = footer.add_paragraph()
    else:
        footer_para = footer.paragraphs[0]

    footer_para.clear()  # remove any existing text
    footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Optional label: "Page " + number
    footer_para.text = "Page "
    add_page_number(footer_para)

    # Small font
    for run in footer_para.runs:
        run.font.size = Pt(8)


def normalize_branch_name(branch_name: str) -> str:
    if not branch_name:
        return branch_name
    if branch_name.lower() == "main branch":
        return "Gondia"
    else:
        words = branch_name.split()
        filtered = [w for w in words if w.lower() != "branch"]
        return " ".join(filtered).strip()


# def get_proposer_approver(selected_date):
#     """
#     Get (or create) proposer & approver for a given date from Share Proceeding Log.
#     Returns: (proposer, approver)
#     """
#     date_obj = getdate(selected_date)
#     date_str = date_obj.strftime("%Y-%m-%d")

#     # Try to fetch existing record
#     existing_name = frappe.db.get_value(
#         "Share Proceeding Log",
#         {"date": date_obj},
#         "name"
#     )

#     if existing_name:
#         existing_doc = frappe.get_doc("Share Proceeding Log", existing_name)
#         if existing_doc.json:
#             schedule = existing_doc.json
#             return schedule["proposer"], schedule["approver"]

#     # No record found → create one with a new pair
#     DIRECTORS = [
#         "जयेशचंद्र रमण रामादे",
#         "दत्तात्रय शायमराव सावंत",
#         "आशीष वासुदेव बाहेकर",
#         "जितेंद्र इंद्रराज रंगारी",
#         "शुभम गोपाल भिमटे"
#     ]

#     # Deterministic per date
#     random.seed(date_str)
#     proposer, approver = random.sample(DIRECTORS, 2)
#     random.seed()  # reset

#     schedule = {
#         "proposer": proposer,
#         "approver": approver
#     }

#     doc = frappe.get_doc({
#         "doctype": "Share Proceeding Log",
#         "date": date_obj,
#         "json": schedule
#     })
#     doc.insert(ignore_permissions=True)
#     frappe.db.commit()

#     return proposer, approver

def get_proceeding_data(selected_date):
    """
    Get (or create) proposer, approver, and meeting number for a given date
    from Share Proceeding Log.
    Returns: (proposer, approver, meeting_no)
    """
    date_obj = getdate(selected_date)
    date_str = date_obj.strftime("%Y-%m-%d")

    # Try to fetch existing record by date
    existing_name = frappe.db.get_value(
        "Share Proceeding Log",
        {"date": date_obj},
        "name"
    )

    if existing_name:
        existing_doc = frappe.get_doc("Share Proceeding Log", existing_name)
        if existing_doc.json:
            # Parse JSON string to dict
            schedule = existing_doc.json
            if isinstance(schedule, str):
                schedule = json.loads(schedule)

            return (
                schedule["proposer"],
                schedule["approver"],
                schedule.get("meeting_no", 1)
            )

    # No record found → create one with new proposer, approver, and meeting_no
    DIRECTORS = [
        "जयेशचंद्र रमण रामादे",
        "दत्तात्रय शायमराव सावंत",
        "आशीष वासुदेव बाहेकर",
        "जितेंद्र इंद्रराज रंगारी",
        "शुभम गोपाल भिमटे"
    ]

    # Deterministic per date
    random.seed(date_str)
    proposer, approver = random.sample(DIRECTORS, 2)
    meeting_no = random.randint(1, 15)
    random.seed()  # reset

    schedule = {
        "proposer": proposer,
        "approver": approver,
        "meeting_no": meeting_no
    }

    doc = frappe.get_doc({
        "doctype": "Share Proceeding Log",
        "date": date_obj,
        "json": schedule  # Frappe will store this as JSON text
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return proposer, approver, meeting_no


def get_signature_file_path(file_url, label):
    """
    Convert the Frappe attachment URL to a server filesystem path.
    Validates that a signature is configured and its image file exists.
    """
    if not file_url:
        frappe.throw(
            f"{label} is not configured. "
            "Please upload it in Share Application Setting."
        )

    # Reject remote URL files because python-docx needs a local path.
    if file_url.startswith(("http://", "https://")):
        frappe.throw(
            f"{label} must be uploaded as a local image file, "
            "not an external URL."
        )

    # Frappe attachment paths normally begin with /files/ or /private/files/
    file_path = frappe.get_site_path(file_url.lstrip("/"))

    if not os.path.exists(file_path):
        frappe.throw(
            f"{label} file was not found on the server: {file_url}. "
            "Please upload the signature again in Share Application Setting."
        )

    allowed_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".gif"}
    extension = os.path.splitext(file_path)[1].lower()

    if extension not in allowed_extensions:
        frappe.throw(
            f"{label} must be an image file. Allowed formats: "
            "PNG, JPG, JPEG, BMP, GIF."
        )
    validate_image_file(file_path, label)
    return file_path


def get_proceeding_signatures():
    """
    Reads both signatures from the Share Application Setting Single DocType.
    Returns local filesystem paths for python-docx.
    """
    settings = frappe.get_single("Share Application Settings")

    chairman_signature_path = get_signature_file_path(
        settings.chairman_signature,
        "Chairman Signature"
    )

    ceo_signature_path = get_signature_file_path(
        settings.ceo_signature,
        "CEO Signature"
    )

    return chairman_signature_path, ceo_signature_path


def add_centered_image(doc, image_path, width_inch=1.8):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = p.add_run()
    run.add_picture(image_path, width=Inches(width_inch))
    return p


def validate_image_file(file_path, label):
    try:
        with Image.open(file_path) as image:
            image.verify()
    except Exception:
        frappe.throw(
            f"{label} is not a valid image file. "
            "Please upload a valid PNG or JPG signature image."
        )


@frappe.whitelist()
def download_proceeding_form(account_opening_date):

    if not account_opening_date:
        frappe.throw(_("Account Opening Date is required."))

    try:
        selected_date = getdate(account_opening_date)
    except Exception:
        frappe.throw(_("Invalid date selected."))

    records = frappe.get_all(
        "Share Application",
        filters={
            "account_opening_date": selected_date,
            "payment_status": "Success"
        },
        fields=["name", "customer_name", "branch"],
        order_by="name asc"
    )

    # if not records:
    #     frappe.throw(
    #         _("No Share Application records with successful payment found for the selected Account Opening Date."))

    if not records:
        frappe.msgprint(
            _("No Share Application records with successful payment found for the selected Account Opening Date."),
            title=_("No Records"),
            indicator="orange"
        )
        return

    def to_devanagari_digits(number):
        """
        Convert an integer to Devanagari (Marathi) digits.
        Example: 708 -> '७०८'
        """
        devanagari_digits = "०१२३४५६७८९"
        return "".join(devanagari_digits[int(d)] for d in str(number))

    total_members = len(records)
    total_members_dev = to_devanagari_digits(total_members)

    def to_devanagari_date(date_obj):
        """
        Convert a Python date object to Devanagari digits in dd/mm/yyyy format.
        Example: 2026-08-18 -> '१८/०८/२०२६'
        """
        day = to_devanagari_digits(date_obj.day)
        month = to_devanagari_digits(date_obj.month)
        year = to_devanagari_digits(date_obj.year)
        return f"{day}/{month}/{year}"

    selected_date_dev = to_devanagari_date(selected_date)

    def add_image_paragraph(image_path, width_inch=0.5):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run()
        run.add_picture(image_path, width=Inches(width_inch))
        return p

    doc = DocxDocument()

    section = doc.sections[0]
    section.top_margin = Inches(0.6)
    section.bottom_margin = Inches(0.6)
    section.left_margin = Inches(0.7)
    section.right_margin = Inches(0.7)

    DEFAULT_FONT = "Kokila"
    DEFAULT_SIZE = 14

    def set_run_font(run, bold=False, size=DEFAULT_SIZE, font_name=DEFAULT_FONT):
        run.bold = bold
        run.font.size = Pt(size)
        run.font.name = font_name
        r = run._element
        if r.rPr is None:
            r.get_or_add_rPr()
        r.rPr.rFonts.set(qn("w:ascii"), font_name)
        r.rPr.rFonts.set(qn("w:hAnsi"), font_name)
        r.rPr.rFonts.set(qn("w:cs"), font_name)
        r.rPr.rFonts.set(qn("w:eastAsia"), font_name)

    def apply_paragraph_spacing(paragraph, alignment=WD_ALIGN_PARAGRAPH.LEFT):
        paragraph.alignment = alignment
        pf = paragraph.paragraph_format
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.line_spacing = Pt(22)
        return paragraph

    def add_center(text, bold=False, size=DEFAULT_SIZE):
        p = doc.add_paragraph()
        apply_paragraph_spacing(p, WD_ALIGN_PARAGRAPH.CENTER)
        run = p.add_run(text)
        set_run_font(run, bold=bold, size=size)
        return p

    def add_left(text, bold=False, size=DEFAULT_SIZE):
        p = doc.add_paragraph()
        apply_paragraph_spacing(p, WD_ALIGN_PARAGRAPH.LEFT)
        run = p.add_run(text)
        set_run_font(run, bold=bold, size=size)
        return p

    def add_left_mixed(parts, size=DEFAULT_SIZE):
        p = doc.add_paragraph()
        apply_paragraph_spacing(p, WD_ALIGN_PARAGRAPH.LEFT)

        for part in parts:
            if isinstance(part, str):
                run = p.add_run(part)
                set_run_font(run, bold=False, size=size)
            else:
                text, is_bold = part
                run = p.add_run(text)
                set_run_font(run, bold=is_bold, size=size)

        return p

    def set_table_col_widths(table, widths):
        table.autofit = False
        try:
            table.allow_autofit = False
        except Exception:
            pass

        for col_idx, width in enumerate(widths):
            try:
                table.columns[col_idx].width = width
            except Exception:
                pass

        for row in table.rows:
            for col_idx, width in enumerate(widths):
                row.cells[col_idx].width = width

    def format_cell_paragraph(paragraph, alignment=WD_ALIGN_PARAGRAPH.CENTER):
        apply_paragraph_spacing(paragraph, alignment)
        return paragraph

    formatted_date = formatdate(selected_date, "dd / mm / yyyy")
    formatted_date_dev = to_devanagari_date(selected_date)
    proposer, approver, meeting_no = get_proceeding_data(selected_date)

    # Read dynamic signatures from Share Application Setting
    chairman_signature_path, ceo_signature_path = get_proceeding_signatures()

    meeting_no_dev = to_devanagari_digits(meeting_no)

    add_center("सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.",
               bold=True, size=24)
    add_center("")
    add_left("सभासद उपसमिती बैठकीची कार्यवाही", bold=True, size=14)

    # add_left("बैठक क्र.: __________", bold=True, size=14)
    add_left(f"दिनांक: {formatted_date_dev}", bold=True, size=14)
    add_left("वेळ: ____११:३०____", bold=True, size=14)
    add_left("स्थळ: मुख्यालय, गोंदिया", bold=True, size=14)
    add_left(
        f"विषय क्र. {meeting_no_dev}: नवीन सभासदत्व मंजूर करण्याबाबत", bold=True, size=14)

    add_left_mixed([
        "मुख्य कार्यकारी अधिकारी यांनी सभेस अवगत केले की, संस्थेचे सभासदत्व प्राप्त करण्यासाठी विविध अर्जदारांकडून विहित नमुन्यात अर्ज प्राप्त झाले आहेत. सदर अर्जांची कार्यालयीन स्तरावर छाननी व पडताळणी करण्यात आली असून, अर्जदारांनी ",
        ("मल्टी स्टेट को-ऑपरेटिव्ह सोसायटीज अधिनियम, 2002,", True),
        " त्याअंतर्गत नियम व संस्थेच्या उपविधींनुसार आवश्यक पात्रता, प्रवेश फी, भागभांडवल रक्कम व इतर आवश्यक कागदपत्रांची पूर्तता केलेली आहे."
    ], size=14)

    add_left_mixed([
        "सदर अर्जदारांची तपशीलवार यादी ",
        ("परिशिष्ट – अ", True),
        " मध्ये जोडण्यात आलेली असून ती सभासद उपसमिती समोर विचारार्थ सादर करण्यात आली."
    ], size=14)

    add_left("")
    add_left(f"ठराव क्र. {meeting_no_dev}", bold=True)

    p = doc.add_paragraph()
    apply_paragraph_spacing(p, WD_ALIGN_PARAGRAPH.LEFT)

    r1 = p.add_run(
        "सभासद उपसमिती विषयावर सविस्तर चर्चा केली. परिशिष्ट – अ मधील सर्व अर्जदारांनी संस्थेच्या उपविधींनुसार सभासदत्वासाठी आवश्यक अटी पूर्ण केल्याचे निदर्शनास आले.\n"
    )
    set_run_font(r1, bold=False, size=14)

    r2 = p.add_run(
        "त्याअनुषंगाने खालीलप्रमाणे ठराव एकमताने मंजूर करण्यात आला :\n"
    )
    set_run_font(r2, bold=False, size=14)

    # r3 = p.add_run(
    #     '"ठरविण्यात येते की, मल्टी स्टेट को-ऑपरेटिव्ह सोसायटीज अधिनियम, 2002, त्याअंतर्गत नियम व संस्थेच्या उपविधींमधील तरतुदींनुसार परिशिष्ट – अ मध्ये नमूद १ ते १०० अर्जदारांना संस्थेचे नियमित सभासद म्हणून प्रवेश देण्यास मंजुरी देण्यात येत आहे. तसेच संबंधित अर्जदारांकडून विहित प्रवेश फी, भागभांडवल रक्कम व इतर आवश्यक औपचारिकता पूर्ण करून त्यांची सभासद म्हणून नोंद सदस्य नोंदवहीत करण्यात यावी व नियमानुसार सभासदत्व/भाग प्रमाणपत्र निर्गमित करण्यात यावे. असे सर्व समंतीने ठरविण्यात आले. "'
    # )
    resolution_text = (
        f'"ठरविण्यात येते की, मल्टी स्टेट को-ऑपरेटिव्ह सोसायटीज अधिनियम, 2002, त्याअंतर्गत नियम व संस्थेच्या उपविधींमधील तरतुदींनुसार '
        f'परिशिष्ट – अ मध्ये नमूद १ ते {total_members_dev} अर्जदारांना संस्थेचे नियमित सभासद म्हणून प्रवेश देण्यास मंजुरी देण्यात येत आहे. '
        f'तसेच संबंधित अर्जदारांकडून विहित प्रवेश फी, भागभांडवल रक्कम व इतर आवश्यक औपचारिकता पूर्ण करून त्यांची सभासद म्हणून नोंद सदस्य नोंदवहीत करण्यात यावी '
        f'व नियमानुसार सभासदत्व/भाग प्रमाणपत्र निर्गमित करण्यात यावे. असे सर्व समंतीने ठरविण्यात आले. "'
    )

    r3 = p.add_run(resolution_text)
    set_run_font(r3, bold=False, size=14)

    add_left("")
    # proposer, ap0prover = random.sample(DIRECTORS, 2)
    # proposer, approver, meeting_no = get_proceeding_data(selected_date)
    add_left(f"प्रस्तावक : {proposer}", bold=True)
    add_left(f"अनुमोदक : {approver}", bold=True)
    # add_left("प्रस्तावक : _______________________", bold=True)
    # add_left("अनुमोदक : _______________________", bold=True)
    add_left("ठराव सर्वानुमते मंजूर.", bold=True)
    # add_left("")
    add_left("")

    # # Jayesh Sir signature
    # add_image_paragraph(JAYESH_SIGN_PATH, width_inch=0.8)
    # # Wasnik Sir signature
    # add_image_paragraph(WASNIK_SIGN_PATH, width_inch=0.8)

    # Single paragraph with both signatures side by side
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Jayesh Sir signature
    run1 = p.add_run()
    # run1.add_picture(JAYESH_SIGN_PATH, width=Inches(1.0))
    # Chairman / Jayesh signature
    run1.add_picture(chairman_signature_path, width=Inches(1.0))

    # Space between signatures
    p.add_run("                                                      ")

    # Wasnik Sir signature
    run2 = p.add_run()
    # run2.add_picture(WASNIK_SIGN_PATH, width=Inches(1.0))
    # CEO / Wasnik signature
    run2.add_picture(ceo_signature_path, width=Inches(1.0))

    add_left("अध्यक्ष                                                             मुख्य कार्यकारी अधिकारी", bold=True)
    add_left("सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.     सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.", bold=True)
    add_left(
        "मुख्यालय, गोंदिया                                           मुख्यालय, गोंदिया", bold=True)

    doc.add_page_break()

    add_center("परिशिष्ट – अ", bold=True, size=14)
    add_center(
        "नवीन सभासदत्वासाठी मंजुरी देण्यात आलेल्या अर्जदारांची यादी", bold=True, size=14)
    add_left("बैठक क्र.: __________", bold=True)
    add_left(f"दिनांक: {formatted_date_dev}", bold=True)
    add_left("")

    table = doc.add_table(rows=1, cols=6)
    table.style = "Table Grid"
    table.autofit = False

    col_widths = [
        Inches(0.45),  # अ.क्र.
        Inches(1.55),  # अर्ज क्र.
        Inches(2.45),  # अर्जदाराचे नाव
        Inches(1.05),  # गाव/शहर
        Inches(0.80),  # भागभांडवल रक्कम
        Inches(0.75),  # प्रवेश फी
    ]

    hdr = table.rows[0].cells
    headers = [
        "अ.क्र.",
        "अर्ज क्र.",
        "अर्जदाराचे नाव",
        "गाव/शहर",
        "भागभांडवल रक्कम",
        "प्रवेश फी"
    ]

    for i, text in enumerate(headers):
        paragraph = hdr[i].paragraphs[0]
        format_cell_paragraph(paragraph, WD_ALIGN_PARAGRAPH.CENTER)
        run = paragraph.add_run(text)
        set_run_font(run, bold=True, size=14)

    # Set column widths ONCE, not in the loop
    set_table_col_widths(table, col_widths)

    # Add all data rows WITHOUT re-setting widths each time
    # for idx, row in enumerate(records, start=1):
    #     cells = table.add_row().cells
    #     row_values = [
    #         str(idx),
    #         row.get("name") or "",
    #         row.get("customer_name") or "",
    #         branch_name,
    #         row.get("branch") or "",
    #         "10"
    #     ]

    #     for col_idx, value in enumerate(row_values):
    #         paragraph = cells[col_idx].paragraphs[0]

    #         if col_idx in (0, 4, 5):
    #             format_cell_paragraph(paragraph, WD_ALIGN_PARAGRAPH.CENTER)
    #         else:
    #             format_cell_paragraph(paragraph, WD_ALIGN_PARAGRAPH.LEFT)

    #         run = paragraph.add_run(value)
    #         set_run_font(run, bold=False, size=14)

    for idx, row in enumerate(records, start=1):
        cells = table.add_row().cells

        # Normalize this row's branch
        branch_raw = (row.get("branch") or "").strip()
        branch_value = normalize_branch_name(branch_raw)

        row_values = [
            str(idx),
            row.get("name") or "",
            row.get("customer_name") or "",
            branch_value,  # per-row branch
            "10",
            "10"
        ]

        for col_idx, value in enumerate(row_values):
            paragraph = cells[col_idx].paragraphs[0]

            if col_idx in (0, 4, 5):
                format_cell_paragraph(paragraph, WD_ALIGN_PARAGRAPH.CENTER)
            else:
                format_cell_paragraph(paragraph, WD_ALIGN_PARAGRAPH.LEFT)

            run = paragraph.add_run(value)
            set_run_font(run, bold=False, size=14)

    # Optional: set widths once at the end if needed
    # set_table_col_widths(table, col_widths)

    add_left("")
    # add_left(
    #     "प्रमाणित करण्यात येते की, परिशिष्ट – अ मध्ये नमूद १ ते १०० अर्जदारांची यादी संचालक मंडळाच्या बैठकी क्र. _____ दिनांक _____ मध्ये मंजूर करण्यात आलेल्या ठराव क्र. _____ चा अविभाज्य भाग आहे.",
    #     bold=True
    # )
    add_left(
        f"प्रमाणित करण्यात येते की, परिशिष्ट – अ मध्ये नमूद १ ते {total_members_dev} अर्जदारांची यादी संचालक मंडळाच्या बैठकी क्र. {meeting_no_dev} दिनांक __{selected_date_dev}__ मध्ये मंजूर करण्यात आलेल्या ठराव क्र. {meeting_no_dev} चा अविभाज्य भाग आहे.",
        bold=True
    )
    # add_left("")
    # add_left("मुख्य कार्यकारी अधिकारी", bold=True)
    # add_left("सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.", bold=True)
    # add_left("मुख्यालय, गोंदिया", bold=True)
    # add_left("")
    # add_left("अध्यक्ष", bold=True)
    # add_left("सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.", bold=True)
    # add_left("मुख्यालय, गोंदिया", bold=True)

    add_left("")

    # add_left("")

    # Wasnik Sir sign
    # add_centered_image(doc, WASNIK_SIGN_PATH, width_inch=1.0)
    add_centered_image(doc, ceo_signature_path, width_inch=1.0)

    add_left("मुख्य कार्यकारी अधिकारी", bold=True)
    add_left("सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.", bold=True)
    add_left("मुख्यालय, गोंदिया", bold=True)

    # add_left("")

    # Jayesh Sir sign
    # add_centered_image(doc, JAYESH_SIGN_PATH, width_inch=1.0)
    add_centered_image(doc, chairman_signature_path, width_inch=1.0)

    add_left("अध्यक्ष", bold=True)
    add_left("सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.", bold=True)
    add_left("मुख्यालय, गोंदिया", bold=True)

    file_buffer = io.BytesIO()

    add_footer_page_number(doc)
    doc.save(file_buffer)
    file_buffer.seek(0)

    frappe.response.filename = f"Proceeding_Form_{selected_date}.docx"
    frappe.response.filecontent = file_buffer.getvalue()
    frappe.response.type = "download"
    frappe.response.display_content_as = "attachment"


# ########################################################################################


@frappe.whitelist()
def download_share_application_report(report_type):
    report_type = (report_type or "").strip().lower()

    filters = {}
    filename = ""

    export_fields = [
        "name",
        # "docstatus",
        "sol_id",
        "cif",
        "account_number",
        "customer_name",
        "scheme_type",
        "scheme_code",
        "transaction_amount",
        "payment_status",
        "failed_reason",
        "transaction_id",
        "error_log",
        "fund_transfer_date",
        "amount",
        "cif_creation_date",
        "account_opening_date",
        "success_but_fund_not_debited",
        # "retry_attempted",
        # "last_retry_attempted",
        # "owner",
        # "creation",
        "address",
    ]

    db_fields = [
        "name",
        # "docstatus",
        "sol_id",
        "cif",
        "account_number",
        "customer_name",
        "scheme_type",
        "scheme_code",
        "transaction_amount",
        "payment_status",
        "transaction_id",
        "error_log",
        "fund_transfer_date",
        "amount",
        "cif_creation_date",
        "account_opening_date",
        "success_but_fund_not_debited",
        # "retry_attempted",
        # "last_retry_attempted",
        # "owner",
        # "creation",
        "address",
        "insufficient_balance",
        "account_closed",
        "account_frozen",
        "account_not_found",
    ]

    if report_type == "success":
        filters = {"payment_status": "Success"}
        filename = "share_application_success_report.csv"

    elif report_type == "failed":
        filters = {"payment_status": "Failed"}
        filename = "share_application_failed_report.csv"

    elif report_type == "pending":
        filters = {"payment_status": "Pending"}
        filename = "share_application_pending_report.csv"

    elif report_type == "consolidated":
        filters = {}
        filename = "share_application_consolidated_report.csv"

    else:
        frappe.throw(_("Invalid report type."))

    label_map = {
        "name": "Share Application ID",
        # "docstatus": "Doc Status",
        "sol_id": "SOL ID",
        "cif": "CIF",
        "account_number": "Account Number",
        "customer_name": "Customer Name",
        "scheme_type": "Scheme Type",
        "scheme_code": "Scheme Code",
        "transaction_amount": "Transaction Amount",
        "payment_status": "Payment Status",
        "failed_reason": "Failed Reason",
        "transaction_id": "Transaction ID",
        "error_log": "API Response",
        "fund_transfer_date": "Fund Transfer Date",
        "amount": "Amount",
        "cif_creation_date": "CIF Creation Date",
        "account_opening_date": "Account Opening Date",
        "success_but_fund_not_debited": "Success But Fund Not Debited",
        # "retry_attempted": "Retry Attempted",
        # "last_retry_attempted": "Last Retry Attempted",
        # "owner": "Owner",
        # "creation": "Created On",
        "address": "Address",
    }

    docstatus_map = {
        0: "Draft",
        1: "Submitted",
        2: "Cancelled",
    }

    def get_failed_reason(row):
        if row.get("payment_status") != "Failed":
            return ""

        if row.get("insufficient_balance"):
            return "Insufficient Balance"
        if row.get("account_closed"):
            return "Account Closed"
        if row.get("account_frozen"):
            return "Account Frozen"
        if row.get("account_not_found"):
            return "Account Not Found"

        return "Network Issue"

    def set_success_but_fund_not_debited(row):
        if row.get("payment_status") == "Success" and row.get("success_but_fund_not_debited"):
            return "Yes"
        return "No"

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([label_map.get(field, field) for field in export_fields])

    chunk_size = 10000
    start = 0

    while True:
        records = frappe.get_all(
            "Share Application",
            filters=filters,
            fields=db_fields,
            limit_start=start,
            limit_page_length=chunk_size,
            order_by="name asc"
        )

        if not records:
            break

        for row in records:
            row_data = []

            # for field in export_fields:
            #     if field == "failed_reason":
            #         value = get_failed_reason(row)
            #     elif field == "docstatus":
            #         value = docstatus_map.get(row.get(field), row.get(field))
            #     else:
            #         value = row.get(field, "")

            #     row_data.append(value)

            for field in export_fields:
                if field == "failed_reason":
                    value = get_failed_reason(row)
                elif field == "docstatus":
                    value = docstatus_map.get(row.get(field), row.get(field))
                elif field == "success_but_fund_not_debited":
                    value = set_success_but_fund_not_debited(row)
                else:
                    value = row.get(field, "")

                row_data.append(value)

            writer.writerow(row_data)

        start += chunk_size

    frappe.response.filename = filename
    frappe.response.filecontent = output.getvalue()
    frappe.response.type = "download"
    frappe.response.display_content_as = "attachment"


@frappe.whitelist()
def get_share_application_status_counts():
    data = frappe.db.sql("""
        SELECT payment_status, COUNT(*) AS count
        FROM `tabShare Application`
        GROUP BY payment_status
    """, as_dict=True)

    counts = {
        "Success": 0,
        "Pending": 0,
        "Failed": 0
    }

    for row in data:
        status = row.get("payment_status")
        if status in counts:
            counts[status] = row.get("count", 0)

    return counts


# def normalize_group_value(value, default="Unassigned Zone"):
#     """
#     Normalize group values so 'Zone 1', ' Zone 1 ', and 'zone 1'
#     are treated as one group.
#     """
#     value = " ".join(str(value or "").split()).strip()
#     return value if value else default


def set_row_cant_split(table_row):
    """
    Prevent one DOCX table row from breaking across pages.

    If the row does not fit in the remaining page area, Word moves
    the complete row to the next page.
    """
    tr_pr = table_row._tr.get_or_add_trPr()

    cant_split = tr_pr.find(qn("w:cantSplit"))
    if cant_split is None:
        cant_split = OxmlElement("w:cantSplit")
        cant_split.set(qn("w:val"), "true")
        tr_pr.append(cant_split)


def normalize_branch_name(branch_name: str) -> str:
    if not branch_name:
        return branch_name

    if branch_name.lower() == "main branch":
        return "Gondia"

    words = branch_name.split()
    filtered = [w for w in words if w.lower() != "branch"]

    return " ".join(filtered).strip()


@frappe.whitelist()
def download_loan_meeting_register_docx(start_date=None, end_date=None):
    """
    Generate and download a zone-wise Loan Meeting Register DOCX.

    Grouping order:
    1. Zone
    2. Region
    3. Branch
    4. Customer Name

    Output columns:
    Zone | Region | Branch | Customer Name | Scheme Name | Months |
    A/c No./CIF. | Req. Loan Amount
    """

    if not start_date:
        frappe.throw(_("Start Date is required."))

    if not end_date:
        frappe.throw(_("End Date is required."))

    try:
        start_date_obj = getdate(start_date)
        end_date_obj = getdate(end_date)
    except Exception:
        frappe.throw(_("Please select valid Start Date and End Date."))

    if start_date_obj > end_date_obj:
        frappe.throw(_("Start Date cannot be greater than End Date."))

    def add_unicode_paragraph(
        document,
        text="",
        bold=False,
        size=11,
        alignment=WD_ALIGN_PARAGRAPH.LEFT,
        font_name="Nirmala UI",
        space_before=0,
        space_after=0
    ):
        """
        Add Hindi/Marathi Unicode text safely to a DOCX paragraph.
        """
        paragraph = document.add_paragraph()
        paragraph.alignment = alignment

        paragraph.paragraph_format.space_before = Pt(space_before)
        paragraph.paragraph_format.space_after = Pt(space_after)
        paragraph.paragraph_format.line_spacing = 1.15

        run = paragraph.add_run(text)
        run.bold = bold
        run.font.name = font_name
        run.font.size = Pt(size)

        r_pr = run._element.get_or_add_rPr()
        r_fonts = r_pr.rFonts
        r_fonts.set(qn("w:ascii"), font_name)
        r_fonts.set(qn("w:hAnsi"), font_name)
        r_fonts.set(qn("w:cs"), font_name)
        r_fonts.set(qn("w:eastAsia"), font_name)

        return paragraph

    query = """
        SELECT
            g.cif_id,
            g.foracid AS ac_no,
            g.acct_name,
            g.acct_opn_date,
            g.acct_cls_date,
            g.sol_id,
            s.sol_desc,

            CASE
                WHEN g.schm_type = 'LAA'
                THEN l.dis_amt
                ELSE lh.sanct_lim
            END AS dis_amt,

            lr.flow_amt,
            e.interest_rate,
            g.clr_bal_amt,
            g.cum_cr_amt AS total_amt_received,
            g.schm_code,
            g2.schm_desc,
            g.schm_type,

            CASE
                WHEN g.schm_type = 'LAA'
                THEN l.rep_perd_mths
                ELSE NULL
            END AS rep_perd_mths,

            l2.lim_exp_date,

            CASE
                WHEN g.schm_type = 'LAA'
                THEN l.ei_perd_start_date
                ELSE NULL
            END AS ei_perd_start_date,

            CASE
                WHEN g.schm_type = 'LAA'
                THEN l.ei_perd_end_date
                ELSE NULL
            END AS ei_perd_end_date,

            g.acct_cls_flg,
            a.address_line1,
            a.address_line2,
            s.division_name,
            s.region_name,
            s.circle_office_name

        FROM tbaadm.gam g

        JOIN tbaadm.sol s
            ON g.sol_id = s.sol_id

        JOIN tbaadm.gsp g2
            ON g.schm_code = g2.schm_code

        LEFT JOIN crmuser.accounts a
            ON g.cif_id = a.orgkey

        LEFT JOIN tbaadm.lam l
            ON g.acid = l.acid

        LEFT JOIN tbaadm.eit e
            ON e.entity_id = g.acid

        LEFT JOIN tbaadm.lht l2
            ON l2.acid = g.acid

        LEFT JOIN (
            SELECT DISTINCT ON (acid)
                acid,
                sanct_lim
            FROM tbaadm.lht
            ORDER BY acid, applicable_date DESC
        ) lh
            ON lh.acid = g.acid

        LEFT JOIN (
            SELECT
                acid,
                MAX(flow_amt) AS flow_amt
            FROM tbaadm.lrs
            GROUP BY acid
        ) lr
            ON lr.acid = g.acid

        WHERE (
            g.schm_type = 'LAA'
            OR g.schm_code IN ('1301', '1302', '3028', '3047', '3050')
        )
        AND g.entity_cre_flg = 'Y'
        AND g.del_flg = 'N'
        AND g.acct_opn_date BETWEEN %(start_date)s AND %(end_date)s

        ORDER BY
            s.circle_office_name NULLS LAST,
            s.region_name NULLS LAST,
            s.sol_desc NULLS LAST,
            g.acct_name NULLS LAST,
            g.foracid NULLS LAST
    """

    params = {
        "start_date": start_date_obj,
        "end_date": end_date_obj
    }

    # This executes the PostgreSQL query through Finacle connection.
    rows = execute_finacle_query(query, params)

    if not rows:
        frappe.msgprint(
            _("No loan records found for the selected date range."),
            title=_("No Records"),
            indicator="orange"
        )
        return

    # def normalize_group_value(value, default=""):
    #     """
    #     Prevent duplicate groups caused by whitespace differences.
    #     Example:
    #     ' Nagpur Zone ', 'Nagpur   Zone' -> 'Nagpur Zone'
    #     """
    #     value = " ".join(str(value or "").split()).strip()
    #     return value if value else default
    def normalize_group_value(value, default=""):
        """
        Basic cleanup for Region, Branch, Customer and other display values.
        """
        value = " ".join(str(value or "").split()).strip()
        return value if value else default

    def normalize_zone_name(value):
        """
        Convert multiple Finacle zone formats to one canonical key.

        Examples:
        ZONE 1  -> Zone 1
        Zone-1  -> Zone 1
        zone_1  -> Zone 1
        ZONE-01 -> Zone 1
        """
        raw_value = normalize_group_value(value, default="")

        if not raw_value:
            return "Unassigned Zone"

        normalized = raw_value.upper()
        normalized = normalized.replace("_", " ")
        normalized = normalized.replace("-", " ")
        normalized = " ".join(normalized.split())

        # Normalise numbered zone values.
        # ZONE 1 / ZONE 01 / ZONE-1 become Zone 1.
        match = re.fullmatch(r"ZONE\s*0*(\d+)", normalized)
        if match:
            return "Zone {0}".format(int(match.group(1)))

        # For nonstandard zone values, preserve a readable title style.
        return raw_value.title()

    def safe_float(value, default=0.0):
        """Safely convert Finacle amounts to float for summation."""
        try:
            if value in (None, ""):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def format_amount(value):
        """Format report amount without a currency sign."""
        return "{:,.2f}".format(safe_float(value))

    def set_cell_background(cell, hex_color):
        """
        Set background colour of one DOCX table cell.
        Use hex color without #, e.g. D9E1F2.
        """
        tc_pr = cell._tc.get_or_add_tcPr()

        shading = OxmlElement("w:shd")
        shading.set(qn("w:fill"), hex_color.replace("#", ""))
        shading.set(qn("w:val"), "clear")
        tc_pr.append(shading)

    def set_row_cant_split(table_row):
        """
        Do not split one table row across two pages.
        If row does not fit, Word moves the row to the next page.
        """
        tr_pr = table_row._tr.get_or_add_trPr()

        cant_split = OxmlElement("w:cantSplit")
        cant_split.set(qn("w:val"), "true")
        tr_pr.append(cant_split)

    def set_cell_text(
        cell,
        value,
        bold=False,
        alignment=WD_ALIGN_PARAGRAPH.LEFT,
        font_size=7
    ):
        """Apply standard text formatting to a DOCX table cell."""
        cell.text = ""
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

        paragraph = cell.paragraphs[0]
        paragraph.alignment = alignment

        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.line_spacing = 1

        run = paragraph.add_run(str(value if value is not None else ""))
        run.bold = bold
        run.font.name = "Arial"
        run.font.size = Pt(font_size)

    # Group only by canonical Zone value.
    # Thus Zone-1, ZONE 1, and Zone 1 become the same Zone 1 group.
    zone_wise_rows = {}

    for row in rows:
        zone = normalize_zone_name(
            row.get("circle_office_name")
        )

        zone_wise_rows.setdefault(zone, []).append(row)

    # Ensure all records within each Zone are ordered by Region, Branch,
    # Customer Name, then CIF ID.
    for zone in zone_wise_rows:
        zone_wise_rows[zone].sort(
            key=lambda row: (
                normalize_group_value(row.get("region_name"), default=""),
                # normalize_group_value(row.get("sol_desc"), default=""),
                normalize_branch_name(
                    normalize_group_value(row.get("sol_desc"), default="")
                ),
                normalize_group_value(row.get("acct_name"), default=""),
                normalize_group_value(row.get("cif_id"), default="")
            )
        )

    document = DocxDocument()

    # section = document.sections[0]
    # section.top_margin = Inches(0.45)
    # section.bottom_margin = Inches(0.45)
    # section.left_margin = Inches(0.30)
    # section.right_margin = Inches(0.30)

    # normal_style = document.styles["Normal"]
    # normal_style.font.name = "Arial"
    # normal_style.font.size = Pt(8)

    section = document.sections[0]

    # A4 Portrait
    section.page_width = Inches(8.27)
    section.page_height = Inches(11.69)

    section.top_margin = Inches(0.50)
    section.bottom_margin = Inches(0.50)
    section.left_margin = Inches(0.35)
    section.right_margin = Inches(0.35)

    section.header_distance = Inches(0.15)
    section.footer_distance = Inches(0.15)

    meeting_date_text = start_date_obj.strftime("%d/%m/%Y")

    add_unicode_paragraph(
        document,
        "सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि., गोंदिया",
        bold=True,
        size=15,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        font_name="Kruti Dev 010"
    )

    add_unicode_paragraph(
        document,
        "मुख्यालय: सहयोग हॉस्पिटल समोर, राणी अवंतीबाई चौक, रिंग रोड, गोंदिया",
        bold=False,
        size=10,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        font_name="Kokila"
    )

    add_unicode_paragraph(
        document,
        "प्रोसिडिंग रजिस्टर",
        bold=True,
        size=14,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        font_name="Kokila",
        space_before=4
    )

    add_unicode_paragraph(
        document,
        "\"कर्ज समिती दैनिक सभा कार्यवृत्तांत\"",
        bold=True,
        size=12,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        font_name="Kokila"
    )

    add_unicode_paragraph(
        document,
        (
            f"आज दिनांक {meeting_date_text} रोजी सायंकाळी 05:00 वाजता "
            "संस्थेच्या मुख्यालय, सहयोग हॉस्पिटल समोर, राणी अवंतीबाई चौक, "
            "रिंग रोड, गोंदिया येथे कर्ज समितीची दैनिक सभा आयोजित करण्यात आली."
        ),
        size=11,
        alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
        font_name="Kokila",
        space_before=5
    )

    add_unicode_paragraph(
        document,
        "सदर सभेस खालील पदाधिकारी उपस्थित होते:"
        "",
        bold=True,
        size=11,
        font_name="Kokila",
        space_before=4
    )

    add_unicode_paragraph(
        document,
        "",
        size=11,
        font_name="Kokila",
        space_before=14
    )

    committee_table = document.add_table(rows=1, cols=3)
    committee_table.style = "Table Grid"
    committee_table.autofit = False
    committee_table.alignment = WD_ALIGN_PARAGRAPH.CENTER

    committee_headers = [
        "अनु. क्र.",
        "पदाधिकारी / संचालक यांचे नाव",
        "पद"
    ]

    committee_widths = [
        Inches(0.65),
        Inches(3.85),
        Inches(2.40)
    ]

    for index, header in enumerate(committee_headers):
        cell = committee_table.rows[0].cells[index]
        cell.width = committee_widths[index]
        set_cell_background(cell, "D9E1F2")
        set_cell_text(
            cell,
            header,
            bold=True,
            alignment=WD_ALIGN_PARAGRAPH.CENTER,
            font_size=9
        )

    committee_members = [
        ("1", "श्री. जयेशचंद्र रमण रामादे", "अध्यक्ष"),
        ("2", "श्री. दत्तात्रय श्यामराव सावंत", "उपाध्यक्ष"),
        ("3", "श्री. शुभम गोपाल भिमटे", "संचालक"),
        ("4", "श्री. विलास रामलाल वासनिक", "मुख्य कार्यकारी अधिकारी"),
        ("5", "श्री. राजेश मनोहरलाल सोनी", "सहाय्यक क्षेत्रीय व्यवस्थापक"),
    ]

    for serial_no, member_name, designation in committee_members:
        member_row = committee_table.add_row()
        set_row_cant_split(member_row)

        member_values = [
            serial_no,
            member_name,
            designation
        ]

        for index, value in enumerate(member_values):
            cell = member_row.cells[index]
            cell.width = committee_widths[index]

            set_cell_text(
                cell,
                value,
                bold=False,
                alignment=(
                    WD_ALIGN_PARAGRAPH.CENTER
                    if index in (0, 2)
                    else WD_ALIGN_PARAGRAPH.LEFT
                ),
                font_size=9
            )

    add_unicode_paragraph(
        document,
        "अध्यक्ष महोदयांच्या अनुमतीने सभेच्या कामकाजास प्रारंभ करण्यात आला."
        "",
        size=11,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        font_name="Kokila",
        space_before=5,
        bold=True
    )

    add_unicode_paragraph(
        document,
        "विषय क्र. 1 : मागील सभेचे कार्यवृत्तांत वाचन करून कायम करणे.",
        bold=True,
        size=11,
        font_name="Kokila",
        space_before=5,
        alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
    )

    add_unicode_paragraph(
        document,
        (
            "ठराव क्र. 1 : मागील सभेचे कार्यवृत्तांत सभेसमोर वाचन करून सादर "
            "करण्यात आले. सदर कार्यवृत्तांतावर सविस्तर साधक-बाधक चर्चा करून "
            "ते सर्वानुमते मंजूर करण्यात आले."
        ),
        size=11,
        alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
        font_name="Kokila"
    )

    add_unicode_paragraph(
        document,
        "प्रस्तावक : मा. श्री. शुभम गोपाल भिमटे",
        # bold=True,
        size=11,
        font_name="Kokila",
        space_before=3,
        alignment=WD_ALIGN_PARAGRAPH.RIGHT,
    )

    add_unicode_paragraph(
        document,
        "अनुमोदक : मा. श्री. दत्तात्रय श्यामराव सावंत",
        # bold=True,
        size=11,
        font_name="Kokila",
        alignment=WD_ALIGN_PARAGRAPH.RIGHT,
    )

    add_unicode_paragraph(
        document,
        "ठराव सर्व संमतीने मंजूर.",
        bold=True,
        size=11,
        font_name="Kokila",
        alignment=WD_ALIGN_PARAGRAPH.RIGHT,
    )

    add_unicode_paragraph(
        document,
        (
            f"विषय क्र. 2 : दिनांक {meeting_date_text} रोजी मंजूर करण्यात "
            "आलेल्या कर्ज प्रस्तावांना मान्यता देणे."
        ),
        bold=True,
        size=11,
        font_name="Kokila",
        space_before=6,
        alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
    )

    add_unicode_paragraph(
        document,
        (
            f"ठराव क्र. 2 : दिनांक {meeting_date_text} रोजी प्राप्त झालेल्या "
            "कर्ज अर्जांवर कार्यालयीन छाननी, परीक्षण व आवश्यक कार्यवाही पूर्ण करून "
            "मंजुरीसाठी सभेसमोर सादर करण्यात आलेल्या कर्ज प्रस्तावांचा सविस्तर तपशील खालीलप्रमाणे आहे."
        ),
        size=11,
        alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
        font_name="Kokila"
    )

    add_unicode_paragraph(
        document,
        "झोननिहाय / शाखानिहाय / ग्राहक / सभासदनिहाय / योजनानिहाय कर्ज मंजुरीचा तपशील",
        bold=True,
        size=11,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        font_name="Kokila",
        space_before=6,
        space_after=5
    )

    # title = document.add_paragraph()
    # title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # title_run = title.add_run("LOAN MEETING REGISTER")
    # title_run.bold = True
    # title_run.font.name = "Arial"
    # title_run.font.size = Pt(15)

    # date_line = document.add_paragraph()
    # date_line.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # date_run = date_line.add_run(
    #     "Account Opening Date: {0} To {1}".format(
    #         start_date_obj.strftime("%d-%m-%Y"),
    #         end_date_obj.strftime("%d-%m-%Y")
    #     )
    # )
    # date_run.bold = True
    # date_run.font.name = "Arial"
    # date_run.font.size = Pt(9)

    document.add_paragraph("")

    headers = [
        "Zone",
        "Region",
        "Branch",
        "Customer Name",
        "Scheme Name",
        "Months",
        "A/c No./CIF.",
        "Req. Loan Amount"
    ]

    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.autofit = False
    # Center the complete table horizontally within page margins.
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Force fixed layout so Word does not expand columns due to long text.
    tbl_pr = table._tbl.tblPr

    tbl_layout = OxmlElement("w:tblLayout")
    tbl_layout.set(qn("w:type"), "fixed")
    tbl_pr.append(tbl_layout)

    # column_widths = [
    #     Inches(0.95),  # Zone
    #     Inches(0.95),  # Region
    #     Inches(1.10),  # Branch
    #     Inches(1.70),  # Customer Name
    #     Inches(1.20),  # Scheme Name
    #     Inches(0.60),  # Months
    #     Inches(1.20),  # A/c No./CIF.
    #     Inches(1.10),  # Req. Loan Amount
    # ]
    column_widths = [
        Inches(0.70),  # Zone
        Inches(0.70),  # Region
        Inches(0.98),  # Branch
        Inches(1.45),  # Customer Name
        Inches(1.45),  # Scheme Name
        Inches(0.70),  # Months: APR
        Inches(0.82),  # A/c No./CIF.
        Inches(1.10),  # Req. Loan Amount
    ]

    header_row = table.rows[0]
    set_row_cant_split(header_row)

    for column_index, header in enumerate(headers):
        header_cell = header_row.cells[column_index]
        header_cell.width = column_widths[column_index]

        set_cell_background(header_cell, "D9E1F2")

        set_cell_text(
            header_cell,
            header,
            bold=True,
            alignment=WD_ALIGN_PARAGRAPH.CENTER,
            font_size=8
        )

    grand_total_records = 0
    grand_total_amount = 0.0

    # Zone 1 records -> Zone 1 Total -> Zone 2 records -> Zone 2 Total...
    # for zone, zone_rows in sorted(
    #     zone_wise_rows.items(),
    #     key=lambda item: item[0].lower()
    # ):

    def zone_sort_key(zone_name):
        """
        Sort numeric zones logically:
        Zone 1, Zone 2, Zone 3 ... Zone 10
        instead of Zone 1, Zone 10, Zone 2.
        """
        match = re.fullmatch(r"Zone\s+(\d+)", zone_name, flags=re.IGNORECASE)

        if match:
            return (0, int(match.group(1)))

        return (1, zone_name.lower())

    for zone, zone_rows in sorted(
        zone_wise_rows.items(),
        key=lambda item: zone_sort_key(item[0])
    ):
        zone_total_records = 0
        zone_total_amount = 0.0

        # All Regions under current Zone are included here.
        for row in zone_rows:
            record_row = table.add_row()
            set_row_cant_split(record_row)

            for column_index, width in enumerate(column_widths):
                record_row.cells[column_index].width = width

            cif_id = str(row.get("cif_id") or "").strip()
            ac_no = str(row.get("ac_no") or "").strip()

            # Requirement says cif_id. Account number is fallback only
            # if Finacle CIF is blank.
            account_or_cif = cif_id or ac_no

            requested_amount = safe_float(row.get("dis_amt"))

            # values = [
            #     zone,
            #     normalize_group_value(row.get("region_name"), default=""),
            #     normalize_group_value(row.get("sol_desc"), default=""),
            #     normalize_group_value(row.get("acct_name"), default=""),
            #     normalize_group_value(row.get("schm_desc"), default=""),
            #     "APR",
            #     account_or_cif,
            #     format_amount(requested_amount)
            # ]
            values = [
                zone,
                normalize_group_value(row.get("region_name"), default=""),
                # normalize_group_value(row.get("sol_desc"), default=""),
                normalize_branch_name(
                    normalize_group_value(row.get("sol_desc"), default="")
                ),
                normalize_group_value(row.get("acct_name"), default=""),
                normalize_group_value(row.get("schm_desc"), default=""),
                "APR",
                account_or_cif,
                format_amount(requested_amount)
            ]

            for column_index, value in enumerate(values):
                alignment = WD_ALIGN_PARAGRAPH.LEFT

                if column_index in (5, 7):
                    alignment = WD_ALIGN_PARAGRAPH.CENTER

                set_cell_text(
                    record_row.cells[column_index],
                    value,
                    bold=False,
                    alignment=alignment,
                    font_size=7
                )

            zone_total_records += 1
            zone_total_amount += requested_amount
            grand_total_records += 1
            grand_total_amount += requested_amount

        # Exactly one total row for this Zone after all its Regions.
        zone_total_row = table.add_row()
        set_row_cant_split(zone_total_row)

        for column_index, width in enumerate(column_widths):
            zone_total_row.cells[column_index].width = width

        for cell in zone_total_row.cells:
            set_cell_background(cell, "63A4F7")

        # Total label only in Zone column. No merged cells.
        set_cell_text(
            zone_total_row.cells[0],
            "{0} Total".format(zone),
            bold=True,
            alignment=WD_ALIGN_PARAGRAPH.LEFT,
            font_size=8
        )

        # Region through A/c No./CIF. remain blank.
        for column_index in range(1, 7):
            set_cell_text(
                zone_total_row.cells[column_index],
                "",
                bold=True,
                alignment=WD_ALIGN_PARAGRAPH.LEFT,
                font_size=8
            )

        # Zone amount only in final column.
        set_cell_text(
            zone_total_row.cells[7],
            format_amount(zone_total_amount),
            bold=True,
            alignment=WD_ALIGN_PARAGRAPH.CENTER,
            font_size=8
        )

    # One final Grand Total after all Zone groups.
    grand_total_row = table.add_row()
    set_row_cant_split(grand_total_row)

    for column_index, width in enumerate(column_widths):
        grand_total_row.cells[column_index].width = width

    for cell in grand_total_row.cells:
        set_cell_background(cell, "D9E1F2")

    # Grand Total label only in Zone column. No merged cells.
    set_cell_text(
        grand_total_row.cells[0],
        "Grand Total",
        bold=True,
        alignment=WD_ALIGN_PARAGRAPH.LEFT,
        font_size=9
    )

    # Region through A/c No./CIF. remain blank.
    for column_index in range(1, 7):
        set_cell_text(
            grand_total_row.cells[column_index],
            "",
            bold=True,
            alignment=WD_ALIGN_PARAGRAPH.LEFT,
            font_size=9
        )

    # Grand total amount only in final column.
    set_cell_text(
        grand_total_row.cells[7],
        format_amount(grand_total_amount),
        bold=True,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        font_size=9
    )

    # document.add_paragraph("")

    # summary = document.add_paragraph()
    # summary.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # summary_run = summary.add_run(
    #     "Total Records: {0} | Grand Total Requested Loan Amount: {1}".format(
    #         grand_total_records,
    #         format_amount(grand_total_amount)
    #     )
    # )
    # summary_run.bold = True
    # summary_run.font.name = "Arial"
    # summary_run.font.size = Pt(9)

    add_unicode_paragraph(
        document,
        (
            "यामध्ये डेली डिपॉझिट योजना, डेली डिपॉझिट तारण कर्ज, आरडी / एसएमबीजी "
            "तारण कर्ज, मुदत ठेवीवरील कर्ज, वैयक्तिक कर्ज, कर्मचारी वैयक्तिक कर्ज, "
            "वाहन कर्ज, वापरलेले वाहन कर्ज, सहयोग महिला उद्योजिका सक्षमीकरण योजना कर्ज, "
            "संयुक्त दायित्व कर्ज, हॉस्पिटल व स्कूल कर्मचारी कर्ज तसेच इतर विविध कर्ज योजनांचा समावेश आहे."
        ),
        size=11,
        alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
        font_name="Kokila",
        space_before=8
    )

    add_unicode_paragraph(
        document,
        "",
        size=11,
        font_name="Kokila",
        space_before=14
    )

    add_unicode_paragraph(
        document,
        (
            "सदर सर्व कर्ज प्रस्तावांवर समितीच्या सभेत सविस्तर साधक-बाधक चर्चा करण्यात आली. "
            "चर्चेनंतर कर्ज समितीने सदर सर्व कर्ज प्रस्तावांना सर्वानुमते मान्यता देण्यात आली."
        ),
        size=11,
        alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
        font_name="kruti Dev 010",
        space_before=5
    )

    add_unicode_paragraph(
        document,
        "",
        size=11,
        font_name="Kokila",
        space_before=14
    )

    add_unicode_paragraph(
        document,
        (
            f"त्यानुसार, कर्ज समितीच्या दिनांक {meeting_date_text} रोजीच्या "
            "सभेचे कार्यवृत्त सर्वानुमते मंजूर करण्यात आले."
        ),
        bold=True,
        size=11,
        alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
        font_name="Kokila",
        space_before=5
    )

    add_unicode_paragraph(
        document,
        "",
        size=11,
        font_name="Kokila",
        space_before=14
    )

    signature_table = document.add_table(rows=1, cols=2)
    signature_table.autofit = False
    signature_table.alignment = WD_TABLE_ALIGNMENT.CENTER

    signature_widths = [
        Inches(3.40),
        Inches(3.40)
    ]

    for index, width in enumerate(signature_widths):
        signature_table.rows[0].cells[index].width = width

    set_cell_text(
        signature_table.rows[0].cells[0],
        "मुख्य कार्यकारी अधिकारी\n\nसहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.\nमुख्यालय, गोंदिया",
        bold=True,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        font_size=10
    )

    set_cell_text(
        signature_table.rows[0].cells[1],
        "अध्यक्ष\n\nसहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.\nमुख्यालय, गोंदिया",
        bold=True,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        font_size=10
    )

    file_buffer = io.BytesIO()
    document.save(file_buffer)
    file_buffer.seek(0)

    frappe.response.filename = (
        "Loan_Meeting_Register_{0}_to_{1}.docx".format(
            start_date_obj.strftime("%Y-%m-%d"),
            end_date_obj.strftime("%Y-%m-%d")
        )
    )
    frappe.response.filecontent = file_buffer.getvalue()
    frappe.response.type = "download"
    frappe.response.display_content_as = "attachment"


def get_signature_base64_data_uri(file_url, label):
    """
    Read a Frappe signature attachment from server storage and return it as
    a Base64 data URI suitable for <img src="..."> in wkhtmltopdf PDF HTML.

    This works for both:
    /files/<file>
    /private/files/<file>
    """
    file_path = get_signature_file_path(file_url, label)

    mime_type, _ = mimetypes.guess_type(file_path)

    if not mime_type or not mime_type.startswith("image/"):
        extension = os.path.splitext(file_path)[1].lower()

        mime_type_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".bmp": "image/bmp"
        }

        mime_type = mime_type_map.get(extension, "image/png")

    try:
        with open(file_path, "rb") as signature_file:
            encoded_image = base64.b64encode(
                signature_file.read()
            ).decode("utf-8")

        return "data:{0};base64,{1}".format(
            mime_type,
            encoded_image
        )

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "{0} Base64 Conversion Failed".format(label)
        )
        frappe.throw(
            _("{0} could not be loaded for PDF generation.").format(label)
        )


@frappe.whitelist()
def download_loan_meeting_register_pdf(account_opening_date=None):
    """
    Generate and download a Zone-wise Loan Meeting Register as PDF.

    The PDF uses separate one-row tables for loan records. This avoids
    wkhtmltopdf splitting one record across two PDF pages.

    Sequence:
    Zone 1 records -> Zone 1 Total
    Zone 2 records -> Zone 2 Total
    ...
    Grand Total
    """

    if not account_opening_date:
        frappe.throw(_("Account Opening Date is required."))

    try:
        account_opening_date_obj = getdate(account_opening_date)
    except Exception:
        frappe.throw(_("Please select a valid Account Opening Date."))

    query = """
        SELECT
            g.cif_id,
            g.foracid AS ac_no,
            g.acct_name,
            g.acct_opn_date,
            g.acct_cls_date,
            g.sol_id,
            s.sol_desc,

            CASE
                WHEN g.schm_type = 'LAA'
                THEN l.dis_amt
                ELSE lh.sanct_lim
            END AS dis_amt,

            lr.flow_amt,
            e.interest_rate,
            g.clr_bal_amt,
            g.cum_cr_amt AS total_amt_received,
            g.schm_code,
            g2.schm_desc,
            g.schm_type,

            CASE
                WHEN g.schm_type = 'LAA'
                THEN l.rep_perd_mths
                ELSE NULL
            END AS rep_perd_mths,

            l2.lim_exp_date,

            CASE
                WHEN g.schm_type = 'LAA'
                THEN l.ei_perd_start_date
                ELSE NULL
            END AS ei_perd_start_date,

            CASE
                WHEN g.schm_type = 'LAA'
                THEN l.ei_perd_end_date
                ELSE NULL
            END AS ei_perd_end_date,

            g.acct_cls_flg,
            a.address_line1,
            a.address_line2,
            s.division_name,
            s.region_name,
            s.circle_office_name

        FROM tbaadm.gam g

        JOIN tbaadm.sol s
            ON g.sol_id = s.sol_id

        JOIN tbaadm.gsp g2
            ON g.schm_code = g2.schm_code

        LEFT JOIN crmuser.accounts a
            ON g.cif_id = a.orgkey

        LEFT JOIN tbaadm.lam l
            ON g.acid = l.acid

        LEFT JOIN tbaadm.eit e
            ON e.entity_id = g.acid

        LEFT JOIN tbaadm.lht l2
            ON l2.acid = g.acid

        LEFT JOIN (
            SELECT DISTINCT ON (acid)
                acid,
                sanct_lim
            FROM tbaadm.lht
            ORDER BY acid, applicable_date DESC
        ) lh
            ON lh.acid = g.acid

        LEFT JOIN (
            SELECT
                acid,
                MAX(flow_amt) AS flow_amt
            FROM tbaadm.lrs
            GROUP BY acid
        ) lr
            ON lr.acid = g.acid

        WHERE (
            g.schm_type = 'LAA'
            OR g.schm_code IN ('1301', '1302', '3028', '3047', '3050')
        )
        AND g.entity_cre_flg = 'Y'
        AND g.del_flg = 'N'
        AND g.acct_opn_date = %(account_opening_date)s

        ORDER BY
            s.circle_office_name NULLS LAST,
            s.region_name NULLS LAST,
            s.sol_desc NULLS LAST,
            g.acct_name NULLS LAST,
            g.foracid NULLS LAST
    """

    params = {
        "account_opening_date": account_opening_date_obj
    }

    rows = execute_finacle_query(query, params)

    if not rows:
        frappe.msgprint(
            _("No loan records found for the selected date range."),
            title=_("No Records"),
            indicator="orange"
        )
        return

    def esc(value):
        """Escape Finacle values before placing them in report HTML."""
        return html.escape(str(value or ""))

    def normalize_group_value(value, default=""):
        """Normalize spaces in fields used for grouping and display."""
        value = " ".join(str(value or "").split()).strip()
        return value if value else default

    def normalize_zone_name(value):
        """
        Convert zone variants to a canonical key.

        Examples:
        ZONE 1, Zone-1, zone_1, ZONE-01 => Zone 1
        """
        raw_value = normalize_group_value(value, default="")

        if not raw_value:
            return "Unassigned Zone"

        normalized = raw_value.upper()
        normalized = normalized.replace("_", " ")
        normalized = normalized.replace("-", " ")
        normalized = " ".join(normalized.split())

        match = re.fullmatch(r"ZONE\s*0*(\d+)", normalized)
        if match:
            return "Zone {0}".format(int(match.group(1)))

        return raw_value.title()

    def zone_sort_key(zone_name):
        """Sort Zone 1, Zone 2, ... Zone 10 in numeric order."""
        match = re.fullmatch(
            r"Zone\s+(\d+)",
            zone_name,
            flags=re.IGNORECASE
        )

        if match:
            return (0, int(match.group(1)))

        return (1, zone_name.lower())

    def safe_float(value, default=0.0):
        """Convert Finacle amount values safely for summation."""
        try:
            if value in (None, ""):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def format_amount(value):
        """Format loan amounts without a currency symbol."""
        return "{:,.2f}".format(safe_float(value))

    def format_account_opening_date(value):
        """
        Format Finacle acct_opn_date for the Months column.

        Example:
        2026-08-01 -> 01-08-2026
        """
        if not value:
            return ""

        try:
            return getdate(value).strftime("%d-%m-%Y")
        except Exception:
            return str(value)

    def build_loan_row(cells, row_class="data-row"):
        """
        Each record is an independent table inside an unbreakable wrapper.

        This is more reliable in wkhtmltopdf than keeping all records inside
        one long <table> with many <tr> tags.
        """
        return f"""
            <div class="loan-row-wrapper {row_class}">
                <table class="loan-table loan-row-table">
                    <tbody>
                        <tr>
                            <td class="col-zone">{cells[0]}</td>
                            <td class="col-region">{cells[1]}</td>
                            <td class="col-branch">{cells[2]}</td>
                            <td class="col-customer">{cells[3]}</td>
                            <td class="col-scheme">{cells[4]}</td>
                            <td class="col-months center-cell">{cells[5]}</td>
                            <td class="col-account center-cell">{cells[6]}</td>
                            <td class="col-amount amount-cell">{cells[7]}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        """

    zone_wise_rows = {}

    for row in rows:
        zone = normalize_zone_name(row.get("circle_office_name"))
        zone_wise_rows.setdefault(zone, []).append(row)

    # for zone in zone_wise_rows:
    #     zone_wise_rows[zone].sort(
    #         key=lambda row: (
    #             normalize_group_value(row.get("region_name"), default=""),
    #             normalize_branch_name(
    #                 normalize_group_value(row.get("sol_desc"), default="")
    #             ),
    #             normalize_group_value(row.get("acct_name"), default=""),
    #             normalize_group_value(row.get("cif_id"), default="")
    #         )
    #     )

    def get_sortable_date(value):
        """
        Convert PostgreSQL date/datetime/string to a sortable ISO date value.

        Empty/invalid dates are intentionally placed at the end of a Zone.
        """
        if not value:
            return "9999-12-31"

        try:
            return getdate(value).strftime("%Y-%m-%d")
        except Exception:
            return "9999-12-31"

    for zone in zone_wise_rows:
        zone_wise_rows[zone].sort(
            key=lambda row: (
                get_sortable_date(row.get("acct_opn_date")),
                normalize_group_value(row.get("region_name"), default=""),
                normalize_branch_name(
                    normalize_group_value(row.get("sol_desc"), default="")
                ),
                normalize_group_value(row.get("acct_name"), default=""),
                normalize_group_value(row.get("cif_id"), default="")
            )
        )

    report_rows = []
    grand_total_records = 0
    grand_total_amount = 0.0

    for zone, zone_rows in sorted(
        zone_wise_rows.items(),
        key=lambda item: zone_sort_key(item[0])
    ):
        zone_total_amount = 0.0

        for row in zone_rows:
            cif_id = str(row.get("cif_id") or "").strip()
            ac_no = str(row.get("ac_no") or "").strip()
            # account_or_cif = cif_id or ac_no
            account_or_cif = ac_no or cif_id

            requested_amount = safe_float(row.get("dis_amt"))

            region = normalize_group_value(
                row.get("region_name"),
                default=""
            )

            branch = normalize_branch_name(
                normalize_group_value(
                    row.get("sol_desc"),
                    default=""
                )
            )

            customer_name = normalize_group_value(
                row.get("acct_name"),
                default=""
            )

            scheme_name = normalize_group_value(
                row.get("schm_desc"),
                default=""
            )

            # report_rows.append(
            #     build_loan_row(
            #         [
            #             esc(zone),
            #             esc(region),
            #             esc(branch),
            #             esc(customer_name),
            #             esc(scheme_name),
            #             "APR",
            #             esc(account_or_cif),
            #             esc(format_amount(requested_amount))
            #         ],
            #         "data-row"
            #     )
            # )
            account_opening_date = format_account_opening_date(
                row.get("acct_opn_date")
            )

            report_rows.append(
                build_loan_row(
                    [
                        esc(zone),
                        esc(region),
                        esc(branch),
                        esc(customer_name),
                        esc(scheme_name),
                        esc(account_opening_date),
                        esc(account_or_cif),
                        esc(format_amount(requested_amount))
                    ],
                    "data-row"
                )
            )

            zone_total_amount += requested_amount
            grand_total_amount += requested_amount
            grand_total_records += 1

        # Add exactly one subtotal after all records of one zone.
        report_rows.append(
            build_loan_row(
                [
                    esc(f"{zone} Total"),
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    esc(format_amount(zone_total_amount))
                ],
                "zone-total-row"
            )
        )

    # Add one final grand total after all zones.
    report_rows.append(
        build_loan_row(
            [
                "Grand Total",
                "",
                "",
                "",
                "",
                "",
                "",
                esc(format_amount(grand_total_amount))
            ],
            "grand-total-row"
        )
    )

    meeting_date_text = account_opening_date_obj.strftime("%d/%m/%Y")
    previous_date_obj = account_opening_date_obj - timedelta(days=1)

    previous_meeting_date_text = previous_date_obj.strftime("%d/%m/%Y")

    # settings = frappe.get_single("Share Application Settings")

    # ceo_signature = (settings.ceo_signature or "").strip()
    # chairman_signature = (settings.chairman_signature or "").strip()

    # if not ceo_signature:
    #     frappe.throw(
    #         _("CEO Signature is not configured in Share Application Settings.")
    #     )

    # if not chairman_signature:
    #     frappe.throw(
    #         _("Chairman Signature is not configured in Share Application Settings.")
    #     )

    # site_url = frappe.utils.get_url().rstrip("/")

    # ceo_signature_url = (
    #     ceo_signature
    #     if ceo_signature.startswith(("http://", "https://"))
    #     else f"{site_url}{ceo_signature}"
    # )

    # chairman_signature_url = (
    #     chairman_signature
    #     if chairman_signature.startswith(("http://", "https://"))
    #     else f"{site_url}{chairman_signature}"
    # )

    settings = frappe.get_single("Share Application Settings")

    ceo_signature_data_uri = get_signature_base64_data_uri(
        settings.ceo_signature,
        "CEO Signature"
    )

    chairman_signature_data_uri = get_signature_base64_data_uri(
        settings.chairman_signature,
        "Chairman Signature"
    )

    report_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">

        <style>
            @page {{
                size: A4 portrait;
                margin: 12mm 7mm 14mm 7mm;
            }}

            * {{
                box-sizing: border-box;
            }}

            body {{
                margin: 0;
                padding: 0;
                color: #000;
                font-size: 15px;
                font-family: "Noto Sans Devanagari", "Nirmala UI", "Kokila", sans-serif;
            }}

            .company-name {{
                text-align: center;
                font-weight: bold;
                font-size: 21px;
                margin: 0 0 5px;
            }}

            .company-address {{
                text-align: center;
                font-size: 15px;
                margin: 0 0 10px;
            }}

            .report-title {{
                text-align: center;
                font-weight: bold;
                font-size: 20px;
                margin: 5px 0;
            }}

            .report-subtitle {{
                text-align: center;
                font-weight: bold;
                font-size: 17px;
                margin: 4px 0 12px;
            }}

            .content {{
                font-size: 15px;
                line-height: 1.45;
                text-align: justify;
                margin: 8px 0;
            }}

            .content-bold {{
                font-size: 15px;
                font-weight: bold;
                line-height: 1.45;
                margin: 8px 0;
            }}

            .right-content {{
                font-size: 15px;
                line-height: 1.40;
                text-align: right;
                margin: 5px 0;
            }}

            .committee-table {{
                width: 94%;
                margin: 12px auto;
                border-collapse: collapse;
                font-size: 14px;
            }}

            .committee-table th,
            .committee-table td {{
                border: 1px solid #000;
                padding: 6px 7px;
                vertical-align: middle;
            }}

            .committee-table th {{
                background-color: #D9E1F2;
                text-align: center;
                font-size: 15px;
                font-weight: bold;
            }}

            .loan-table-container {{
                width: 100%;
                margin: 12px auto;
                display: block;
            }}

            .loan-table {{
                width: 100%;
                border-collapse: collapse;
                table-layout: fixed;
                font-family: Arial, sans-serif;
                font-size: 11.5px;
                margin: 0;
                padding: 0;
            }}

            .loan-header-table {{
                margin: 0;
            }}

            .loan-row-table {{
                margin: 0;
                border-top: 0;
            }}

            .loan-table th,
            .loan-table td {{
                border: 1px solid #000;
                padding: 5px 4px;
                vertical-align: middle;
                overflow-wrap: break-word;
                word-wrap: break-word;
                line-height: 1.20;
            }}

            .loan-table th {{
                background-color: #D9E1F2;
                text-align: center;
                font-size: 12.5px;
                font-weight: bold;
                line-height: 1.15;
            }}

            .loan-row-wrapper {{
                display: block;
                width: 100%;
                margin: 0;
                padding: 0;

                page-break-inside: avoid !important;
                page-break-before: auto !important;
                page-break-after: auto !important;
                break-inside: avoid !important;
            }}

            .loan-row-wrapper table,
            .loan-row-wrapper tr,
            .loan-row-wrapper td {{
                page-break-inside: avoid !important;
                break-inside: avoid !important;
            }}

            .col-zone {{
                width: 7%;
            }}

            .col-region {{
                width: 7%;
            }}

            .col-branch {{
                width: 10%;
            }}

            .col-customer {{
                width: 20%;
            }}

            .col-scheme {{
                width: 15%;
            }}

            .col-months {{
                width: 10%;
            }}

            .col-account {{
                width: 17%;
            }}

            .col-amount {{
                width: 14%;
            }}

            .center-cell {{
                text-align: center;
            }}

            .amount-cell {{
                text-align: right;
                white-space: nowrap;
            }}

            .zone-total-row td {{
                background-color: #63A4F7;
                font-weight: bold;
                font-size: 13.5px;
            }}

            .grand-total-row td {{
                background-color: #D9E1F2;
                font-weight: bold;
                font-size: 14px;
            }}

            .signature-table {{
                width: 92%;
                margin: 32px auto 0;
                border-collapse: collapse;
                font-size: 16px;
                font-weight: bold;
                page-break-inside: avoid;
                break-inside: avoid;
            }}

            .signature-table td {{
                width: 50%;
                padding: 14px;
                text-align: center;
                vertical-align: top;
            }}

            .signature-image {{
                display: block;
                width: 145px;
                height: 65px;
                max-width: 145px;
                max-height: 65px;
                object-fit: contain;
                margin: 0 auto 8px auto;
            }}

            .signature-designation {{
                font-size: 16px;
                font-weight: bold;
                margin: 0 0 8px 0;
                font-family: "Noto Sans Devanagari", "Nirmala UI", "Kokila", sans-serif;
            }}

            .signature-organization {{
                font-size: 13px;
                line-height: 1.35;
                font-weight: bold;
                font-family: "Noto Sans Devanagari", "Nirmala UI", "Kokila", sans-serif;
            }}
        </style>
    </head>

    <body>
        <div class="company-name">
            सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि. गोंदिया
        </div>

        <div class="company-address">
            मुख्यालय: सहयोग हॉस्पिटल समोर, राणी अवंतीबाई चौक, रिंग रोड, गोंदिया
        </div>

        <div class="report-title">प्रोसिडिंग रजिस्टर</div>

        <div class="report-subtitle">
            "कर्ज समिती दैनिक सभा कार्यवृत्तांत"
        </div>

        <p class="content">
            आज दिनांक {meeting_date_text} रोजी सायंकाळी 05:00 वाजता, संस्थेच्या मुख्यालय, सहयोग हॉस्पिटल समोर, राणी अवंतीबाई चौक, रिंग रोड, गोंदिया येथे कर्ज समितीची दैनंदिन सभा संस्थेचे अध्यक्ष श्री. जयेशचंद्र रमण रामदे यांच्या अध्यक्षतेखाली आयोजित करण्यात आली.
        </p>

        <p class="content-bold">
            सदर सभेस खालील पदाधिकारी उपस्थित होते:
        </p>

        <table class="committee-table">
            <thead>
                <tr>
                    <th style="width:10%;">अनु. क्र.</th>
                    <th style="width:55%;">पदाधिकारी / संचालक यांचे नाव</th>
                    <th style="width:35%;">पद</th>
                </tr>
            </thead>

            <tbody>
                <tr>
                    <td style="text-align:center;">1</td>
                    <td>श्री. जयेशचंद्र रमण रामादे</td>
                    <td style="text-align:center;">अध्यक्ष</td>
                </tr>
                <tr>
                    <td style="text-align:center;">2</td>
                    <td>श्री. दत्तात्रय श्यामराव सावंत</td>
                    <td style="text-align:center;">उपाध्यक्ष</td>
                </tr>
                <tr>
                    <td style="text-align:center;">3</td>
                    <td>श्री. शुभम गोपाल भिमटे</td>
                    <td style="text-align:center;">संचालक</td>
                </tr>
                <tr>
                    <td style="text-align:center;">4</td>
                    <td>श्री. विलास रामलाल वासनिक</td>
                    <td style="text-align:center;">मुख्य कार्यकारी अधिकारी</td>
                </tr>
                <tr>
                    <td style="text-align:center;">5</td>
                    <td>श्री. राजेश मनोहरलाल सोनी</td>
                    <td style="text-align:center;">सहाय्यक क्षेत्रीय व्यवस्थापक</td>
                </tr>
            </tbody>
        </table>

        <p class="content-bold" style="text-align:center;">
            अध्यक्ष महोदयांच्या अनुमतीने सभेच्या कामकाजास प्रारंभ करण्यात आला.
        </p>

        <p class="content-bold">
            विषय क्र. 1 : मागील सभेचे कार्यवृत्तांत वाचन करून कायम करणे.
        </p>

        <p class="content">
            ठराव क्र. 1 : मागील सभा दिनांक {previous_meeting_date_text} रोजी झालेल्या दैनंदिन सभेचे कार्यवृत्त सभेसमोर वाचन करून सादर करण्यात आले. सदर कार्यवृत्तावर सविस्तर साधक-बाधक चर्चा करण्यात आली. चर्चेनंतर दिनांक {previous_meeting_date_text} रोजीच्या सभेचे कार्यवृत्त सर्वानुमते मंजूर करण्यात आले.
        </p>

        <p class="right-content">
            प्रस्तावक : मा. श्री. शुभम गोपाल भिमटे
        </p>

        <p class="right-content">
            अनुमोदक : मा. श्री. दत्तात्रय श्यामराव सावंत
        </p>

        <p class="right-content" style="font-weight:bold;">
            ठराव सर्व संमतीने मंजूर.
        </p>

        <p class="content-bold">
            विषय क्र. 2 : दिनांक {meeting_date_text} रोजी मंजूर करण्यात आलेल्या
            कर्ज प्रस्तावांना मान्यता देणे.
        </p>

        <p class="content">
            ठराव क्र. 2 : दिनांक {meeting_date_text} रोजी प्राप्त झालेल्या कर्ज अर्जांवर कार्यालयीन छाननी, परीक्षण व आवश्यक कार्यवाही पूर्ण करून मंजुरीसाठी सभेसमोर झोननिहाय व कर्ज योजनानिहाय मंजूर करण्यात आलेल्या कर्ज प्रस्तावांचा सविस्तर तपशील सादर करण्यात आला.
        </p>

        <p class="content-bold" style="text-align:center;">
            झोननिहाय / शाखानिहाय / ग्राहक / सभासदनिहाय / योजनानिहाय कर्ज मंजुरीचा तपशील
        </p>

        <div class="loan-table-container">
            <table class="loan-table loan-header-table">
                <thead>
                    <tr>
                        <th class="col-zone">Zone</th>
                        <th class="col-region">Region</th>
                        <th class="col-branch">Branch</th>
                        <th class="col-customer">Customer Name</th>
                        <th class="col-scheme">Scheme Name</th>
                        <th class="col-months">A/c Open Date</th>
                        <th class="col-account">A/c No.</th>
                        <th class="col-amount">Req. Loan Amount</th>
                    </tr>
                </thead>
            </table>

            {"".join(report_rows)}
        </div>

        <p class="content">
            यामध्ये डेली डिपॉझिट योजना, डेली डिपॉझिट तारण कर्ज, आरडी / एसएमबीजी तारण कर्ज,
            मुदत ठेवीवरील कर्ज, वैयक्तिक कर्ज, कर्मचारी वैयक्तिक कर्ज, वाहन कर्ज,
            वापरलेले वाहन कर्ज, सहयोग महिला उद्योजिका सक्षमीकरण योजना कर्ज,
            संयुक्त दायित्व कर्ज, हॉस्पिटल व स्कूल कर्मचारी कर्ज तसेच इतर विविध
            कर्ज योजनांचा समावेश आहे.
        </p>

        <p class="content">
            सदर सर्व कर्ज प्रस्तावांवर समितीच्या सभेत सविस्तर साधक-बाधक चर्चा करण्यात आली. चर्चेनंतर कर्ज समितीने दिनांक {meeting_date_text} रोजी मंजूर केलेल्या सर्व कर्ज प्रस्तावांना सर्वानुमते मान्यता देण्यात आली.
        </p>

        <p class="content-bold">
            त्यानुसार, कर्ज समितीच्या दिनांक {meeting_date_text} रोजीच्या सभेचे कार्यवृत्त
            सर्वानुमते मंजूर करण्यात आले.
        </p>

        <table class="signature-table">
    <tr>
        <td>
            <img
                src="{ceo_signature_data_uri}"
                alt="CEO Signature"
                class="signature-image"
            >

            <div class="signature-designation">
                मुख्य कार्यकारी अधिकारी
            </div>

            <div class="signature-organization">
                सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.<br>
                मुख्यालय, गोंदिया
            </div>
        </td>

        <td>
            <img
                src="{chairman_signature_data_uri}"
                alt="Chairman Signature"
                class="signature-image"
            >

            <div class="signature-designation">
                अध्यक्ष
            </div>

            <div class="signature-organization">
                सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.<br>
                मुख्यालय, गोंदिया
            </div>
        </td>
    </tr>
</table>
    </body>
    </html>
    """

    pdf_options = {
        "page-size": "A4",
        "orientation": "Portrait",
        "margin-top": "12mm",
        "margin-right": "7mm",
        "margin-bottom": "14mm",
        "margin-left": "7mm",
        "encoding": "UTF-8",
        "quiet": "",
        "footer-right": "Page [page] of [toPage]",
        "footer-font-size": "7",
        "footer-spacing": "3"
    }

    pdf_content = get_pdf(report_html, pdf_options)

    frappe.response.filename = (
        "Loan_Meeting_Register_{0}.pdf".format(
            account_opening_date_obj.strftime("%Y-%m-%d")
        )
    )
    frappe.response.filecontent = pdf_content
    frappe.response.type = "download"
    frappe.response.display_content_as = "attachment"


def get_signature_base64_data_uri(file_url, label):
    """
    Read an uploaded Frappe image attachment and return a base64 data URI
    suitable for use in an HTML <img> tag.
    """
    file_path = get_signature_file_path(file_url, label)

    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type or not mime_type.startswith("image/"):
        frappe.throw(
            _("{0} must be a valid image file.").format(label)
        )

    try:
        with open(file_path, "rb") as image_file:
            encoded_image = base64.b64encode(image_file.read()).decode("utf-8")
    except OSError:
        frappe.throw(
            _("{0} could not be read from the server. "
              "Please upload the image again.").format(label)
        )

    return f"data:{mime_type};base64,{encoded_image}"


def prevent_row_break_across_pages(row):
    """
    Prevent one DOCX table row from breaking across pages.

    If the row does not fit in the remaining page area, Word moves
    the complete row to the next page.
    """
    tr_pr = row._tr.get_or_add_trPr()

    cant_split = OxmlElement("w:cantSplit")
    cant_split.set(qn("w:val"), "1")

    tr_pr.append(cant_split)


@frappe.whitelist()
def download_proceeding_form_pdfs(account_opening_date):
    """
    Generate and download the Share Proceeding Form as a PDF.
    """

    if not account_opening_date:
        frappe.throw(_("Account Opening Date is required."))

    try:
        selected_date = getdate(account_opening_date)
    except Exception:
        frappe.throw(_("Invalid date selected."))

    records = frappe.get_all(
        "Share Application",
        filters={
            "account_opening_date": selected_date,
            "payment_status": "Success"
        },
        fields=["name", "customer_name", "branch"],
        order_by="name asc"
    )

    if not records:
        frappe.msgprint(
            _(
                "No Share Application records with successful payment "
                "found for the selected Account Opening Date."
            ),
            title=_("No Records"),
            indicator="orange"
        )
        return

    def to_devanagari_digits(number):
        devanagari_digits = "०१२३४५६७८९"
        return "".join(devanagari_digits[int(d)] for d in str(number))

    def to_devanagari_date(date_obj):
        day = to_devanagari_digits(date_obj.day)
        month = to_devanagari_digits(date_obj.month)
        year = to_devanagari_digits(date_obj.year)
        return f"{day}/{month}/{year}"

    def esc(value):
        """Escape all variable values before placing them in HTML."""
        return html.escape(str(value or ""))

    total_members = len(records)
    total_members_dev = to_devanagari_digits(total_members)
    selected_date_dev = to_devanagari_date(selected_date)

    proposer, approver, meeting_no = get_proceeding_data(selected_date)
    meeting_no_dev = to_devanagari_digits(meeting_no)

    # Read signatures from Share Application Settings.
    settings = frappe.get_single("Share Application Settings")

    chairman_signature_data_uri = get_signature_base64_data_uri(
        settings.chairman_signature,
        "Chairman Signature"
    )

    ceo_signature_data_uri = get_signature_base64_data_uri(
        settings.ceo_signature,
        "CEO Signature"
    )

    # Build Appendix-A table rows.
    table_rows = []

    for idx, row in enumerate(records, start=1):
        branch_raw = (row.get("branch") or "").strip()
        branch_value = normalize_branch_name(branch_raw)

        table_rows.append(f"""
            <tr>
                <td class="center">{esc(to_devanagari_digits(idx))}</td>
                <td>{esc(row.get("name") or "")}</td>
                <td>{esc(row.get("customer_name") or "")}</td>
                <td>{esc(branch_value)}</td>
                <td class="center">१०</td>
                <td class="center">१०</td>
            </tr>
        """)

    report_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">

        <style>
            @page {{
                size: A4 portrait;
                margin: 13mm 13mm 18mm 13mm;
            }}

            * {{
                box-sizing: border-box;
            }}

            body {{
                margin: 0;
                padding: 0;
                color: #000;
                font-family: "Noto Sans Devanagari", "Nirmala UI", "Kokila", sans-serif;
                font-size: 17px;
                line-height: 1.45;
            }}

            .company-name {{
                text-align: center;
                font-size: 27px;
                line-height: 1.30;
                font-weight: bold;
                margin: 0 0 8px 0;
            }}

            .heading {{
                text-align: left;
                font-size: 17px;
                font-weight: bold;
                margin: 0 0 4px 0;
            }}

            .content {{
                text-align: justify;
                font-size: 17px;
                line-height: 1.55;
                margin: 6px 0;
            }}

            .content-bold {{
                font-size: 17px;
                line-height: 1.50;
                font-weight: bold;
                margin: 6px 0;
            }}

            .resolution-title {{
                font-size: 17px;
                font-weight: bold;
                margin: 10px 0 4px 0;
            }}

            .signatory-lines {{
                font-size: 17px;
                font-weight: bold;
                line-height: 1.50;
                margin: 10px 0 0 0;
            }}

            .signature-table {{
                width: 100%;
                margin: 10px 0 0 0;
                border-collapse: collapse;
                page-break-inside: avoid;
                break-inside: avoid;
            }}

            .signature-table td {{
                width: 50%;
                vertical-align: top;
                text-align: center;
                padding: 0 10px;
            }}

            .signature-image {{
                display: block;
                width: 95px;
                height: 45px;
                max-width: 95px;
                max-height: 45px;
                object-fit: contain;
                margin: 0 auto 3px auto;
            }}

            .signature-designation {{
                font-size: 17px;
                font-weight: bold;
                line-height: 1.35;
                margin: 0 0 2px 0;
            }}

            .signature-organization {{
                font-size: 15px;
                font-weight: bold;
                line-height: 1.35;
                margin: 0;
            }}

            .page-break {{
                page-break-before: always;
            }}

            .appendix-title {{
                text-align: center;
                font-size: 17px;
                font-weight: bold;
                margin: 0 0 4px 0;
            }}

            .appendix-subtitle {{
                text-align: center;
                font-size: 17px;
                font-weight: bold;
                margin: 0 0 8px 0;
            }}

            .appendix-meta {{
                font-size: 17px;
                font-weight: bold;
                margin: 2px 0;
            }}

            .members-table {{
                width: 100%;
                border-collapse: collapse;
                table-layout: fixed;
                margin: 10px 0 8px 0;
                font-size: 14px;
            }}

            .members-table th,
            .members-table td {{
                border: 1px solid #000;
                padding: 5px 4px;
                vertical-align: middle;
                overflow-wrap: break-word;
                word-wrap: break-word;
                line-height: 1.30;
            }}

            .members-table th {{
                text-align: center;
                font-size: 14px;
                font-weight: bold;
            }}

            .members-table th:nth-child(1),
            .members-table td:nth-child(1) {{
                width: 7%;
            }}

            .members-table th:nth-child(2),
            .members-table td:nth-child(2) {{
                width: 20%;
            }}

            .members-table th:nth-child(3),
            .members-table td:nth-child(3) {{
                width: 31%;
            }}

            .members-table th:nth-child(4),
            .members-table td:nth-child(4) {{
                width: 14%;
            }}

            .members-table th:nth-child(5),
            .members-table td:nth-child(5) {{
                width: 15%;
            }}

            .members-table th:nth-child(6),
            .members-table td:nth-child(6) {{
                width: 13%;
            }}

            .center {{
                text-align: center;
            }}

            .certification {{
                text-align: justify;
                font-size: 17px;
                line-height: 1.55;
                font-weight: bold;
                margin: 10px 0 8px 0;
            }}

            .individual-signature {{
                margin: 12px 0 0 0;
                page-break-inside: avoid;
                break-inside: avoid;
            }}

            .individual-signature-image {{
                display: block;
                width: 95px;
                height: 45px;
                max-width: 95px;
                max-height: 45px;
                object-fit: contain;
                margin: 0 auto 3px auto;
            }}

            .individual-signature-text {{
                text-align: left;
                font-size: 17px;
                font-weight: bold;
                line-height: 1.40;
                margin: 0;
            }}
        </style>
    </head>

    <body>
        <!-- Page 1 -->
        <div class="company-name">
            सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.
        </div>

        <p class="heading">सभासद उपसमिती बैठकीची कार्यवाही</p>

        <p class="heading">दिनांक: {esc(selected_date_dev)}</p>
        <p class="heading">वेळ: ____११:३०____</p>
        <p class="heading">स्थळ: मुख्यालय, गोंदिया</p>
        <p class="heading">
            विषय क्र. {esc(meeting_no_dev)}: नवीन सभासदत्व मंजूर करण्याबाबत
        </p>

        <p class="content">
            मुख्य कार्यकारी अधिकारी यांनी सभेस अवगत केले की, संस्थेचे सभासदत्व प्राप्त करण्यासाठी विविध अर्जदारांकडून विहित नमुन्यात अर्ज प्राप्त झाले आहेत. सदर अर्जांची कार्यालयीन स्तरावर छाननी व पडताळणी करण्यात आली असून, अर्जदारांनी <strong>मल्टी स्टेट को-ऑपरेटिव्ह सोसायटीज अधिनियम, 2002,</strong> त्याअंतर्गत नियम व संस्थेच्या उपविधींनुसार आवश्यक पात्रता, प्रवेश फी, भागभांडवल रक्कम व इतर आवश्यक कागदपत्रांची पूर्तता केलेली आहे.
        </p>

        <p class="content">
            सदर अर्जदारांची तपशीलवार यादी <strong>परिशिष्ट – अ</strong> मध्ये जोडण्यात आलेली असून ती सभासद उपसमिती समोर विचारार्थ सादर करण्यात आली.
        </p>

        <p class="resolution-title">ठराव क्र. {esc(meeting_no_dev)}</p>

        <p class="content">
            सभासद उपसमिती विषयावर सविस्तर चर्चा केली. परिशिष्ट – अ मधील सर्व अर्जदारांनी संस्थेच्या उपविधींनुसार सभासदत्वासाठी आवश्यक अटी पूर्ण केल्याचे निदर्शनास आले.
            <br>
            त्याअनुषंगाने खालीलप्रमाणे ठराव एकमताने मंजूर करण्यात आला:
            <br>
            "ठरविण्यात येते की, मल्टी स्टेट को-ऑपरेटिव्ह सोसायटीज अधिनियम, 2002, त्याअंतर्गत नियम व संस्थेच्या उपविधींमधील तरतुदींनुसार परिशिष्ट – अ मध्ये नमूद १ ते {esc(total_members_dev)} अर्जदारांना संस्थेचे नियमित सभासद म्हणून प्रवेश देण्यास मंजुरी देण्यात येत आहे. तसेच संबंधित अर्जदारांकडून विहित प्रवेश फी, भागभांडवल रक्कम व इतर आवश्यक औपचारिकता पूर्ण करून त्यांची सभासद म्हणून नोंद सदस्य नोंदवहीत करण्यात यावी व नियमानुसार सभासदत्व/भाग प्रमाणपत्र निर्गमित करण्यात यावे. असे सर्व समंतीने ठरविण्यात आले. "
        </p>

        <div class="signatory-lines">
            <div>प्रस्तावक : {esc(proposer)}</div>
            <div>अनुमोदक : {esc(approver)}</div>
            <div>ठराव सर्वानुमते मंजूर.</div>
        </div>

        <table class="signature-table">
            <tr>
                <td>
                    <img
                        src="{chairman_signature_data_uri}"
                        alt="Chairman Signature"
                        class="signature-image"
                    >
                    <div class="signature-designation">अध्यक्ष</div>
                    <div class="signature-organization">
                        सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.<br>
                        मुख्यालय, गोंदिया
                    </div>
                </td>

                <td>
                    <img
                        src="{ceo_signature_data_uri}"
                        alt="CEO Signature"
                        class="signature-image"
                    >
                    <div class="signature-designation">मुख्य कार्यकारी अधिकारी</div>
                    <div class="signature-organization">
                        सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.<br>
                        मुख्यालय, गोंदिया
                    </div>
                </td>
            </tr>
        </table>

        <!-- Page 2 -->
        <div class="page-break"></div>

        <p class="appendix-title">परिशिष्ट – अ</p>
        <p class="appendix-subtitle">
            नवीन सभासदत्वासाठी मंजुरी देण्यात आलेल्या अर्जदारांची यादी
        </p>

        <p class="appendix-meta">बैठक क्र.: __________</p>
        <p class="appendix-meta">दिनांक: {esc(selected_date_dev)}</p>

        <table class="members-table">
            <thead>
                <tr>
                    <th>अ.क्र.</th>
                    <th>अर्ज क्र.</th>
                    <th>अर्जदाराचे नाव</th>
                    <th>गाव/शहर</th>
                    <th>भागभांडवल रक्कम</th>
                    <th>प्रवेश फी</th>
                </tr>
            </thead>

            <tbody>
                {"".join(table_rows)}
            </tbody>
        </table>

        <p class="certification">
            प्रमाणित करण्यात येते की, परिशिष्ट – अ मध्ये नमूद १ ते {esc(total_members_dev)} अर्जदारांची यादी संचालक मंडळाच्या बैठकी क्र. {esc(meeting_no_dev)} दिनांक __{esc(selected_date_dev)}__ मध्ये मंजूर करण्यात आलेल्या ठराव क्र. {esc(meeting_no_dev)} चा अविभाज्य भाग आहे.
        </p>

        <div class="individual-signature">
            <img
                src="{ceo_signature_data_uri}"
                alt="CEO Signature"
                class="individual-signature-image"
            >
            <p class="individual-signature-text">
                मुख्य कार्यकारी अधिकारी<br>
                सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.<br>
                मुख्यालय, गोंदिया
            </p>
        </div>

        <div class="individual-signature">
            <img
                src="{chairman_signature_data_uri}"
                alt="Chairman Signature"
                class="individual-signature-image"
            >
            <p class="individual-signature-text">
                अध्यक्ष<br>
                सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.<br>
                मुख्यालय, गोंदिया
            </p>
        </div>
    </body>
    </html>
    """

    pdf_options = {
        "page-size": "A4",
        "orientation": "Portrait",
        "margin-top": "13mm",
        "margin-right": "13mm",
        "margin-bottom": "18mm",
        "margin-left": "13mm",
        "encoding": "UTF-8",
        "quiet": "",
        "footer-right": "Page [page] of [toPage]",
        "footer-font-size": "10",
        "footer-spacing": "4"
    }

    pdf_content = get_pdf(report_html, pdf_options)

    frappe.response.filename = (
        f"Proceeding_Form_{selected_date.strftime('%Y-%m-%d')}.pdf"
    )
    frappe.response.filecontent = pdf_content
    frappe.response.type = "download"
    frappe.response.display_content_as = "attachment"


@frappe.whitelist()
def download_proceeding_form_pdf(account_opening_date):
    """
    Generate and download the Share Proceeding Form as a PDF.

    Each Appendix-A member row is rendered as a separate one-row table
    inside an unbreakable wrapper. This prevents wkhtmltopdf from splitting
    a member record across PDF pages.
    """

    if not account_opening_date:
        frappe.throw(_("Account Opening Date is required."))

    try:
        selected_date = getdate(account_opening_date)
    except Exception:
        frappe.throw(_("Invalid date selected."))

    records = frappe.get_all(
        "Share Application",
        filters={
            "account_opening_date": selected_date,
            "payment_status": "Success"
        },
        fields=["name", "customer_name", "branch"],
        order_by="name asc"
    )

    if not records:
        frappe.msgprint(
            _(
                "No Share Application records with successful payment "
                "found for the selected Account Opening Date."
            ),
            title=_("No Records"),
            indicator="orange"
        )
        return

    def to_devanagari_digits(number):
        devanagari_digits = "०१२३४५६७८९"
        return "".join(devanagari_digits[int(d)] for d in str(number))

    def to_devanagari_date(date_obj):
        day = to_devanagari_digits(date_obj.day)
        month = to_devanagari_digits(date_obj.month)
        year = to_devanagari_digits(date_obj.year)
        return f"{day}/{month}/{year}"

    def esc(value):
        """Escape variable values before using them inside HTML."""
        return html.escape(str(value or ""))

    def build_member_row(cells):
        """
        Render one applicant record as an independent one-row table.

        A normal long HTML table can have a row split by wkhtmltopdf across
        pages. A separate wrapper/table makes the entire applicant row
        an atomic printable unit.
        """
        return f"""
            <div class="member-row-wrapper">
                <table class="members-table member-row-table">
                    <tbody>
                        <tr>
                            <td class="col-sr center">{cells[0]}</td>
                            <td class="col-application">{cells[1]}</td>
                            <td class="col-name">{cells[2]}</td>
                            <td class="col-branch">{cells[3]}</td>
                            <td class="col-share center">{cells[4]}</td>
                            <td class="col-fee center">{cells[5]}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        """

    total_members = len(records)
    total_members_dev = to_devanagari_digits(total_members)
    selected_date_dev = to_devanagari_date(selected_date)

    proposer, approver, meeting_no = get_proceeding_data(selected_date)
    meeting_no_dev = to_devanagari_digits(meeting_no)

    # Dynamic signatures from Share Application Settings.
    settings = frappe.get_single("Share Application Settings")

    chairman_signature_data_uri = get_signature_base64_data_uri(
        settings.chairman_signature,
        "Chairman Signature"
    )

    ceo_signature_data_uri = get_signature_base64_data_uri(
        settings.ceo_signature,
        "CEO Signature"
    )

    # Build Appendix-A member rows as separate protected blocks.
    member_rows = []

    for idx, row in enumerate(records, start=1):
        branch_raw = (row.get("branch") or "").strip()
        branch_value = normalize_branch_name(branch_raw)

        member_rows.append(
            build_member_row([
                esc(to_devanagari_digits(idx)),
                esc(row.get("name") or ""),
                esc(row.get("customer_name") or ""),
                esc(branch_value),
                "१०",
                "१०"
            ])
        )

    report_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">

        <style>
            @page {{
                size: A4 portrait;
                margin: 13mm 13mm 18mm 13mm;
            }}

            * {{
                box-sizing: border-box;
            }}

            body {{
                margin: 0;
                padding: 0;
                color: #000;
                font-family: "Noto Sans Devanagari", "Nirmala UI", "Kokila", sans-serif;
                font-size: 17px;
                line-height: 1.45;
            }}

            .company-name {{
                text-align: center;
                font-size: 27px;
                line-height: 1.30;
                font-weight: bold;
                margin: 0 0 8px 0;
            }}

            .heading {{
                text-align: left;
                font-size: 17px;
                font-weight: bold;
                margin: 0 0 4px 0;
            }}

            .content {{
                text-align: justify;
                font-size: 17px;
                line-height: 1.55;
                margin: 6px 0;
            }}

            .content-bold {{
                font-size: 17px;
                line-height: 1.50;
                font-weight: bold;
                margin: 6px 0;
            }}

            .resolution-title {{
                font-size: 17px;
                font-weight: bold;
                margin: 10px 0 4px 0;
            }}

            .signatory-lines {{
                font-size: 17px;
                font-weight: bold;
                line-height: 1.50;
                margin: 10px 0 0 0;
            }}

            .signature-table {{
                width: 100%;
                margin: 10px 0 0 0;
                border-collapse: collapse;
                page-break-inside: avoid !important;
                break-inside: avoid !important;
            }}

            .signature-table td {{
                width: 50%;
                vertical-align: top;
                text-align: center;
                padding: 0 10px;
            }}

            .signature-image {{
                display: block;
                width: 95px;
                height: 45px;
                max-width: 95px;
                max-height: 45px;
                object-fit: contain;
                margin: 0 auto 3px auto;
            }}

            .signature-designation {{
                font-size: 17px;
                font-weight: bold;
                line-height: 1.35;
                margin: 0 0 2px 0;
            }}

            .signature-organization {{
                font-size: 15px;
                font-weight: bold;
                line-height: 1.35;
                margin: 0;
            }}

            .page-break {{
                page-break-before: always;
            }}

            .appendix-title {{
                text-align: center;
                font-size: 17px;
                font-weight: bold;
                margin: 0 0 4px 0;
            }}

            .appendix-subtitle {{
                text-align: center;
                font-size: 17px;
                font-weight: bold;
                margin: 0 0 8px 0;
            }}

            .appendix-meta {{
                font-size: 17px;
                font-weight: bold;
                margin: 2px 0;
            }}

            /*
             * Appendix-A table structure:
             *
             * - One header table
             * - Each applicant row in a separate table
             *
             * This is more reliable in wkhtmltopdf than a single long
             * table with multiple <tr> tags.
             */
            .members-table-container {{
                display: block;
                width: 100%;
                margin: 10px 0 8px 0;
                padding: 0;
            }}

            .members-table {{
                width: 100%;
                margin: 0;
                padding: 0;
                border-collapse: collapse;
                border-spacing: 0;
                table-layout: fixed;
                font-size: 14px;
            }}

            .members-header-table {{
                margin: 0;
            }}

            .member-row-table {{
                margin: 0;
                border-top: 0;
            }}

            .members-table th,
            .members-table td {{
                border: 1px solid #000;
                padding: 5px 4px;
                vertical-align: middle;
                overflow-wrap: break-word;
                word-wrap: break-word;
                line-height: 1.30;
            }}

            .members-table th {{
                text-align: center;
                font-size: 14px;
                font-weight: bold;
            }}

            /*
             * Critical page-break protection.
             * If the record does not fit in the remaining page space,
             * wkhtmltopdf should place the complete block on the next page.
             */
            .member-row-wrapper {{
                display: block;
                width: 100%;
                margin: 0;
                padding: 0;

                page-break-inside: avoid !important;
                page-break-before: auto !important;
                page-break-after: auto !important;

                break-inside: avoid !important;
            }}

            .member-row-wrapper table,
            .member-row-wrapper tbody,
            .member-row-wrapper tr,
            .member-row-wrapper td {{
                page-break-inside: avoid !important;
                break-inside: avoid !important;
            }}

            /*
             * Table widths total 100%.
             * The same CSS classes are used in both header and data tables.
             */
            .col-sr {{
                width: 7%;
            }}

            .col-application {{
                width: 20%;
            }}

            .col-name {{
                width: 31%;
            }}

            .col-branch {{
                width: 14%;
            }}

            .col-share {{
                width: 15%;
            }}

            .col-fee {{
                width: 13%;
            }}

            .center {{
                text-align: center;
            }}

            .certification {{
                text-align: justify;
                font-size: 17px;
                line-height: 1.55;
                font-weight: bold;
                margin: 10px 0 8px 0;
            }}

            .individual-signature {{
                margin: 12px 0 0 0;
                text-align: left;

                page-break-inside: avoid !important;
                break-inside: avoid !important;
            }}

            .individual-signature-image {{
                display: block;
                width: 95px;
                height: 45px;
                max-width: 95px;
                max-height: 45px;
                object-fit: contain;

                /* Left-align the image */
                margin: 0 0 3px 0;
            }}

            .individual-signature-text {{
                text-align: left;
                font-size: 17px;
                font-weight: bold;
                line-height: 1.40;
                margin: 0;
            }}
        </style>
    </head>

    <body>
        <!-- First Page -->
        <div class="company-name">
            सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.
        </div>

        <p class="heading">सभासद उपसमिती बैठकीची कार्यवाही</p>

        <p class="heading">दिनांक: {esc(selected_date_dev)}</p>
        <p class="heading">वेळ: ____११:३०____</p>
        <p class="heading">स्थळ: मुख्यालय, गोंदिया</p>

        <p class="heading">
            विषय क्र. {esc(meeting_no_dev)}: नवीन सभासदत्व मंजूर करण्याबाबत
        </p>

        <p class="content">
            मुख्य कार्यकारी अधिकारी यांनी सभेस अवगत केले की, संस्थेचे सभासदत्व प्राप्त करण्यासाठी विविध अर्जदारांकडून विहित नमुन्यात अर्ज प्राप्त झाले आहेत. सदर अर्जांची कार्यालयीन स्तरावर छाननी व पडताळणी करण्यात आली असून, अर्जदारांनी <strong>मल्टी स्टेट को-ऑपरेटिव्ह सोसायटीज अधिनियम, 2002,</strong> त्याअंतर्गत नियम व संस्थेच्या उपविधींनुसार आवश्यक पात्रता, प्रवेश फी, भागभांडवल रक्कम व इतर आवश्यक कागदपत्रांची पूर्तता केलेली आहे.
        </p>

        <p class="content">
            सदर अर्जदारांची तपशीलवार यादी <strong>परिशिष्ट – अ</strong> मध्ये जोडण्यात आलेली असून ती सभासद उपसमिती समोर विचारार्थ सादर करण्यात आली.
        </p>

        <p class="resolution-title">ठराव क्र. {esc(meeting_no_dev)}</p>

        <p class="content">
            सभासद उपसमिती विषयावर सविस्तर चर्चा केली. परिशिष्ट – अ मधील सर्व अर्जदारांनी संस्थेच्या उपविधींनुसार सभासदत्वासाठी आवश्यक अटी पूर्ण केल्याचे निदर्शनास आले.
            <br>
            त्याअनुषंगाने खालीलप्रमाणे ठराव एकमताने मंजूर करण्यात आला:
            <br>
            "ठरविण्यात येते की, मल्टी स्टेट को-ऑपरेटिव्ह सोसायटीज अधिनियम, 2002, त्याअंतर्गत नियम व संस्थेच्या उपविधींमधील तरतुदींनुसार परिशिष्ट – अ मध्ये नमूद १ ते {esc(total_members_dev)} अर्जदारांना संस्थेचे नियमित सभासद म्हणून प्रवेश देण्यास मंजुरी देण्यात येत आहे. तसेच संबंधित अर्जदारांकडून विहित प्रवेश फी, भागभांडवल रक्कम व इतर आवश्यक औपचारिकता पूर्ण करून त्यांची सभासद म्हणून नोंद सदस्य नोंदवहीत करण्यात यावी व नियमानुसार सभासदत्व/भाग प्रमाणपत्र निर्गमित करण्यात यावे. असे सर्व समंतीने ठरविण्यात आले. "
        </p>

        <div class="signatory-lines">
            <div>प्रस्तावक : {esc(proposer)}</div>
            <div>अनुमोदक : {esc(approver)}</div>
            <div>ठराव सर्वानुमते मंजूर.</div>
        </div>

        <table class="signature-table">
            <tr>
                <td>
                    <img
                        src="{chairman_signature_data_uri}"
                        alt="Chairman Signature"
                        class="signature-image"
                    >
                    <div class="signature-designation">अध्यक्ष</div>
                    <div class="signature-organization">
                        सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.<br>
                        मुख्यालय, गोंदिया
                    </div>
                </td>

                <td>
                    <img
                        src="{ceo_signature_data_uri}"
                        alt="CEO Signature"
                        class="signature-image"
                    >
                    <div class="signature-designation">मुख्य कार्यकारी अधिकारी</div>
                    <div class="signature-organization">
                        सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.<br>
                        मुख्यालय, गोंदिया
                    </div>
                </td>
            </tr>
        </table>

        <!-- Second Page -->
        <div class="page-break"></div>

        <p class="appendix-title">परिशिष्ट – अ</p>

        <p class="appendix-subtitle">
            नवीन सभासदत्वासाठी मंजुरी देण्यात आलेल्या अर्जदारांची यादी
        </p>

        <p class="appendix-meta">बैठक क्र.: __________</p>
        <p class="appendix-meta">दिनांक: {esc(selected_date_dev)}</p>

        <div class="members-table-container">

            <!-- Header remains separate from member rows. -->
            <table class="members-table members-header-table">
                <thead>
                    <tr>
                        <th class="col-sr">अ.क्र.</th>
                        <th class="col-application">अर्ज क्र.</th>
                        <th class="col-name">अर्जदाराचे नाव</th>
                        <th class="col-branch">गाव/शहर</th>
                        <th class="col-share">भागभांडवल रक्कम</th>
                        <th class="col-fee">प्रवेश फी</th>
                    </tr>
                </thead>
            </table>

            <!-- Every applicant is a separate unbreakable PDF block. -->
            {"".join(member_rows)}

        </div>

        <p class="certification">
            प्रमाणित करण्यात येते की, परिशिष्ट – अ मध्ये नमूद १ ते {esc(total_members_dev)} अर्जदारांची यादी संचालक मंडळाच्या बैठकी क्र. {esc(meeting_no_dev)} दिनांक __{esc(selected_date_dev)}__ मध्ये मंजूर करण्यात आलेल्या ठराव क्र. {esc(meeting_no_dev)} चा अविभाज्य भाग आहे.
        </p>

        <div class="individual-signature">
            <img
                src="{ceo_signature_data_uri}"
                alt="CEO Signature"
                class="individual-signature-image"
            >

            <p class="individual-signature-text">
                मुख्य कार्यकारी अधिकारी<br>
                सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.<br>
                मुख्यालय, गोंदिया
            </p>
        </div>

        <div class="individual-signature">
            <img
                src="{chairman_signature_data_uri}"
                alt="Chairman Signature"
                class="individual-signature-image"
            >

            <p class="individual-signature-text">
                अध्यक्ष<br>
                सहयोग मल्टीस्टेट क्रेडिट को-ऑपरेटिव्ह सोसायटी लि.<br>
                मुख्यालय, गोंदिया
            </p>
        </div>
    </body>
    </html>
    """

    pdf_options = {
        "page-size": "A4",
        "orientation": "Portrait",
        "margin-top": "13mm",
        "margin-right": "13mm",
        "margin-bottom": "18mm",
        "margin-left": "13mm",
        "encoding": "UTF-8",
        "quiet": "",
        "footer-right": "Page [page] of [toPage]",
        "footer-font-size": "10",
        "footer-spacing": "4"
    }

    pdf_content = get_pdf(report_html, pdf_options)

    frappe.response.filename = (
        f"Proceeding_Form_{selected_date.strftime('%Y-%m-%d')}.pdf"
    )
    frappe.response.filecontent = pdf_content
    frappe.response.type = "download"
    frappe.response.display_content_as = "attachment"
