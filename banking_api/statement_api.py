import frappe
import oracledb
from frappe import _
from frappe.utils.pdf import get_pdf
from datetime import datetime
import csv
from io import StringIO

@frappe.whitelist()
def get_share_data():
	return frappe.db.sql(
		"""select department,division,region,user_id,branch from `tabEmployee`;""",
		as_dict=True,
	)

@frappe.whitelist(allow_guest=True)
def test_db(branch_code, ac_code, ac_no, start_date, end_date, export_format="pdf"):
	connection = None
	cursor = None
	try:
		# Initialize Oracle Client for Thick Mode
		settings = frappe.get_single("Netwin Settings")
		try:
			if settings.oracle_client_path:
				oracledb.init_oracle_client(lib_dir=settings.oracle_client_path)
			else:
				oracledb.init_oracle_client()
		except oracledb.ProgrammingError:
			pass  # Already initialized
		except Exception as e:
			frappe.log_error(f"Oracle Client Init Error: {str(e)}", "test_db")

		# Flexible date parsing
		def parse_date(date_str):
			for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
				try:
					return datetime.strptime(date_str, fmt)
				except ValueError:
					continue
			frappe.throw(_("Invalid date format: {0}. Please use DD/MM/YYYY.").format(date_str))

		start_date_obj = parse_date(start_date)
		end_date_obj = parse_date(end_date)

		# Fetch connection details from "Netwin Settings" (Modified from "Netwin Database Settings" to match existing DocType)
		settings = frappe.get_single("Netwin Settings")
		username = settings.username
		password = settings.get_password('password')
		host = settings.host
		port = settings.port
		sid = settings.sid

		# Create DSN and connect
		dsn = oracledb.makedsn(host, port, service_name=sid)
		connection = oracledb.connect(user=username, password=password, dsn=dsn)
		cursor = connection.cursor()

		# 1. Fetch Branch Name and Code
		cursor.execute(
			"SELECT branchname, branchcode FROM SAHYOG.BRANCHMAS WHERE branchcode = :branch_code",
			{'branch_code': branch_code}
		)
		branch_result = cursor.fetchone()
		if not branch_result:
			frappe.throw(_("Branch not found for the given Branch Code."))
		branch_name, branch_code = branch_result

		# Mapping dictionary for ACMASTCODE to table names
		acmastcode_to_table = {
			157: 'CURMAS', 419: 'CURMAS', 444: 'CURMAS', 500: 'CURMAS', 628: 'CURMAS',
			255: 'CURMAS', 288: 'CURMAS', 442: 'CURMAS', 305: 'CURMAS', 324: 'CURMAS',
			564: 'CURMAS', 605: 'SAVMAS', 377: 'SAVMAS', 143: 'SAVMAS', 627: 'SAVMAS',
			445: 'SAVMAS', 559: 'SAVMAS', 3: 'SAVMAS', 385: 'SAVMAS', 431: 'SAVMAS',
			22: 'LNMAS', 25: 'LNMAS', 245: 'LNMAS', 152: 'LNMAS', 474: 'LNMAS',
			619: 'LNMAS', 386: 'LNMAS', 457: 'LNMAS', 620: 'LNMAS', 26: 'LNMAS',
			21: 'LNMAS', 20: 'LNMAS', 365: 'LNMAS', 223: 'LNMAS', 250: 'LNMAS',
			306: 'LNMAS', 24: 'LNMAS', 622: 'LNMAS', 23: 'LNMAS', 352: 'LNMAS',
			453: 'LNMAS', 482: 'LNMAS', 557: 'LNMAS', 615: 'LNMAS', 451: 'LNMAS',
			383: 'LNMAS', 623: 'LNMAS', 27: 'LNMAS', 18: 'LNMAS', 195: 'LNMAS',
			196: 'LNMAS', 421: 'LNMAS', 221: 'LNMAS', 405: 'LNMAS', 503: 'LNMAS',
			517: 'LNMAS', 621: 'LNMAS', 19: 'LNMAS', 159: 'LNMAS', 338: 'LNMAS',
			373: 'LNMAS', 343: 'LNMAS', 548: 'LNMAS', 617: 'LNMAS', 618: 'LNMAS',
			380: 'SSDMAS',
			418: 'SSDMAS', 328: 'SSDMAS', 142: 'SSDMAS', 216: 'SSDMAS', 1: 'FDMAS',
			247: 'FDMAS', 194: 'FDMAS', 155: 'FDMAS', 599: 'FDMAS', 2: 'FDMAS',
			148: 'FDMAS', 149: 'FDMAS', 4: 'FDMAS', 432: 'FDMAS', 233: 'FDMAS',
			154: 'FDMAS', 256: 'FDMAS', 290: 'SHMAS', 480: 'BA_MASTER', 561: 'INVMAS',
			609: 'INVMAS', 392: 'INVMAS', 519: 'INVMAS', 514: 'INVMAS', 568: 'INVMAS',
			287: 'INVMAS', 520: 'INVMAS', 160: 'INVMAS', 448: 'INVMAS', 501: 'INVMAS'
		}

		# Step 1: Fetch ACMASTCODE using AC_CODE
		cursor.execute(
			"SELECT ACMASTCODE, AC_NAME FROM SAHYOG.ACMAST WHERE AC_CODE = :ac_code",
			{'ac_code': ac_code}
		)
		acmastcode_result = cursor.fetchone()

		if not acmastcode_result:
			frappe.throw(_("ACMASTCODE not found for the given AC_CODE."))

		acmastcode, ac_name = acmastcode_result

		# Step 2: Get the corresponding table name
		table_name = acmastcode_to_table.get(acmastcode)
		if not table_name:
			frappe.throw(_("Table mapping not found for ACMASTCODE: {0}").format(acmastcode))

		# Step 3: Dynamically fetch GMST_CODE and Customer details in one query
		query = f"""
			SELECT t.GMST_CODE, b.name, b.addr, b.city, b.adharno, b.mobileno
			FROM SAHYOG.{table_name} t
			JOIN SAHYOG.BANKMAS b ON t.GMST_CODE = b.GMST_CODE
			WHERE t.AC_NO = :ac_no
			AND t.ACMASTCODE = :acmastcode
			AND t.BRANCHCODE = :branch_code
		"""

		cursor.execute(query, {
			'ac_no': ac_no,
			'acmastcode': acmastcode,
			'branch_code': branch_code
		})
		customer_result = cursor.fetchone()

		if not customer_result:
			frappe.throw(_("Customer details or GMST_CODE not found for the given criteria."))

		gmst_code, cust_name, cust_addr, cust_city, cust_aadhar, cust_mobile = customer_result

		customer_info = {
			"name": cust_name,
			"address": cust_addr,
			"city": cust_city,
			"aadhar": cust_aadhar,
			"telephone": cust_mobile,
		}

		# Step 4: Fetch opening balance and transactions in one query using UNION ALL
		# Row 1 is Opening Balance (identified by sort_order = -1)
		# Remaining rows are transactions
		query = """
			SELECT NULL as tdate, 
			       NVL(SUM(CASE WHEN credit > 0 THEN credit ELSE 0 END), 0) as credit,
			       NVL(SUM(CASE WHEN debit > 0 THEN debit ELSE 0 END), 0) as debit,
			       'OPENING BALANCE' as prtcls, 
			       NULL as doc_no, 
			       -1 as sort_order
			FROM SAHYOG.ACBK
			WHERE AC_NO = :ac_no 
			  AND FORBRANCH = :branch_code 
			  AND ACMASTCODE = :acmastcode 
			  AND tdate < :start_date
			  AND POST = 1
			  AND (cncled != 1 OR cncled IS NULL)
			UNION ALL
			SELECT tdate, credit, debit, prtcls, doc_no, ctrnno as sort_order
			FROM SAHYOG.ACBK
			WHERE AC_NO = :ac_no 
			  AND FORBRANCH = :branch_code 
			  AND ACMASTCODE = :acmastcode 
			  AND tdate BETWEEN :start_date AND :end_date
			  AND POST = 1
			  AND (cncled != 1 OR cncled IS NULL)
			ORDER BY sort_order
		"""

		cursor.execute(query, {
			'ac_no': ac_no,
			'branch_code': branch_code,
			'acmastcode': acmastcode,
			'start_date': start_date_obj,
			'end_date': end_date_obj
		})
		results = cursor.fetchall()

		opening_row = results[0]
		opening_balance = float(opening_row[1]) - float(opening_row[2])

		# 8. Prepare transaction data for rendering
		transaction_data = []
		current_balance = opening_balance

		# Skip the first row as it's the opening balance row
		for record in results[1:]:
			tdate, credit, debit, prtcls, doc_no, _ = record
			credit = float(credit) if credit else 0.0
			debit = float(debit) if debit else 0.0
			current_balance += (credit - debit)
			
			transaction_data.append({
				'transaction_date': tdate.strftime("%d/%m/%Y") if tdate else "",
				'transaction_type': 'Debit' if debit > 0 else 'Credit',
				'description': prtcls,
				'doc_no': doc_no,
				'debit': round(debit, 2),
				'credit': round(credit, 2),
				'balance': round(current_balance, 2)
			})


		# Prepare context
		context = {
			"customer_info": customer_info,
			"transactions": transaction_data,
			"branch_code": branch_code,
			"branch_name": branch_name,
			"ac_no": ac_no,
			"ac_name": ac_name,
			"start_date": start_date_obj.strftime("%d/%m/%Y"),
			"end_date": end_date_obj.strftime("%d/%m/%Y"),
			"opening_balance": round(opening_balance, 2),
		}

		if export_format == "csv":
			output = StringIO()
			writer = csv.writer(output)
			
			writer.writerow(["Bank", "SAHAYOG BANK"])
			writer.writerow(["Branch", f"{branch_name} ({branch_code})"])
			writer.writerow(["Statement for", ac_name])
			writer.writerow(["Account No", ac_no])
			writer.writerow(["Customer Name", customer_info.get('name')])
			writer.writerow(["Period", f"{context['start_date']} to {context['end_date']}"])
			writer.writerow([])
			
			writer.writerow(["Date", "Type", "Description", "Doc No.", "Debit", "Credit", "Balance"])
			writer.writerow([context['start_date'], "-", "Opening Balance", "-", "-", "-", context['opening_balance']])
			
			for tx in transaction_data:
				writer.writerow([
					tx['transaction_date'],
					tx['transaction_type'],
					tx['description'],
					tx['doc_no'] if tx['doc_no'] else '-',
					tx['debit'],
					tx['credit'],
					tx['balance']
				])
			
			frappe.local.response.filename = f"Transaction_Statement_{ac_no}.csv"
			frappe.local.response.filecontent = output.getvalue()
			frappe.local.response.type = "download"
			output.close()
			
		else:
			# Default to PDF
			html_content = frappe.render_template("templates/transaction_statement.html", context)
			pdf_data = get_pdf(html_content)

			frappe.local.response.filename = f"Transaction_Statement_{ac_no}.pdf"
			frappe.local.response.filecontent = pdf_data
			frappe.local.response.type = "download"

	except oracledb.DatabaseError as e:
		error = e.args[0] if e.args else e
		message = getattr(error, "message", str(error))
		frappe.throw(_("Database error: {0}").format(message))
	except Exception as e:
		frappe.throw(str(e))
	finally:
		if cursor:
			cursor.close()
		if connection:
			connection.close()

def check_credentials():
	settings = frappe.get_single("Netwin Settings")
	username = settings.username
	password = settings.get_password('password')
	host = settings.host
	port = settings.port
	sid = settings.sid

	try:
		try:
			if settings.oracle_client_path:
				oracledb.init_oracle_client(lib_dir=settings.oracle_client_path)
			else:
				oracledb.init_oracle_client()
		except oracledb.ProgrammingError:
			pass
			
		dsn = oracledb.makedsn(host, port, service_name=sid)
		connection = oracledb.connect(user=username, password=password, dsn=dsn)
		connection.close()
		return True
	except Exception as e:
		frappe.log_error(f"Credentials Check Failed: {str(e)}", "check_credentials")
		return False

def check_netwin():
	# Hardcoded for testing as per user code
	username = "sahyog"
	password = "sahyog"
	host = "10.0.115.20"
	port = "1521"
	sid = "orcl"

	try:
		try:
			settings = frappe.get_single("Netwin Settings")
			if settings.oracle_client_path:
				oracledb.init_oracle_client(lib_dir=settings.oracle_client_path)
			else:
				oracledb.init_oracle_client()
		except oracledb.ProgrammingError:
			pass
			
		dsn = oracledb.makedsn(host, port, service_name=sid)
		connection = oracledb.connect(user=username, password=password, dsn=dsn)
		connection.close()
		return True
	except Exception as e:
		frappe.log_error(f"Netwin Check Failed: {str(e)}", "check_netwin")
		return False
