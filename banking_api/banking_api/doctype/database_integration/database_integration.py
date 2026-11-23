# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

import json
import math
import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch
import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe.model.document import Document


class DatabaseIntegration(Document):
    def render_query(self, query_string: str, extra_context: dict = None) -> str:
        """
        Renders dynamic Jinja expressions inside SQL queries.
        Provides helpful context such as today, now, days_ago, add_days, add_months, frappe, and doc.
        """
        if not query_string:
            return ""

        context = {
            "frappe": frappe,
            "doc": self,
            "today": frappe.utils.today(),
            "nowdate": frappe.utils.nowdate(),
            "now": frappe.utils.now(),
            "now_datetime": frappe.utils.now_datetime(),
            "getdate": frappe.utils.getdate,
            "add_days": frappe.utils.add_days,
            "add_months": frappe.utils.add_months,
            "add_years": frappe.utils.add_years,
            "days_ago": lambda n: frappe.utils.add_days(frappe.utils.today(), -int(n)),
            "days_ahead": lambda n: frappe.utils.add_days(frappe.utils.today(), int(n)),
            "format_date": frappe.utils.format_date,
        }

        if extra_context:
            context.update(extra_context)

        try:
            return frappe.render_template(query_string, context)
        except Exception as e:
            frappe.throw(
                _("Failed to render query template: {0}").format(str(e)))

    def get_source_query_with_filters(self) -> tuple[str, str, str]:
        """
        Returns (final_query, filter_from, filter_to).
        Wraps rendered source query with dynamic date filter condition if enable_date_filter is active.
        """
        rendered_query = self.render_query(self.source_query)
        if not self.enable_date_filter or not self.date_filter_column:
            return rendered_query, None, None

        clean_query = rendered_query.strip().rstrip(";")
        col = self.date_filter_column.strip()
        mode = self.date_filter_mode or "Last N Days"
        filter_from = None
        filter_to = None

        if mode == "Last N Days":
            days = int(self.last_n_days or 3)
            filter_from = frappe.utils.add_days(frappe.utils.today(), -days)
            filter_to = frappe.utils.today()
            wrapped_query = f"SELECT * FROM ({clean_query}) AS _src_filtered WHERE {col} >= '{filter_from}'"
            return wrapped_query, str(filter_from), str(filter_to)

        elif mode == "Today Only":
            filter_from = frappe.utils.today()
            filter_to = frappe.utils.today()
            wrapped_query = f"SELECT * FROM ({clean_query}) AS _src_filtered WHERE {col} >= '{filter_from}'"
            return wrapped_query, str(filter_from), str(filter_to)

        elif mode == "Incremental (Sync From)":
            filter_from = self.sync_from or frappe.utils.add_days(
                frappe.utils.today(), -3)
            wrapped_query = f"SELECT * FROM ({clean_query}) AS _src_filtered WHERE {col} > '{filter_from}' ORDER BY {col} ASC"
            return wrapped_query, str(filter_from), None

        return rendered_query, None, None

    @frappe.whitelist()
    def preview_source_data(self, page: int = 1, page_len: int = 20):
        """
        Fetches paginated sample records and total record count from Source Database using rendered source_query.
        """
        if not self.source_database:
            frappe.throw(_("Please select a Source Database."))

        if not self.source_query:
            frappe.throw(_("Please specify a Source Query."))

        page = max(1, int(page or 1))
        page_len = min(500, max(5, int(page_len or 20)))
        offset = (page - 1) * page_len

        source_query, _, _ = self.get_source_query_with_filters()
        clean_query = source_query.strip().rstrip(";")

        source_db_doc = frappe.get_doc(
            "Database Configuration", self.source_database)
        conn = None

        try:
            conn = source_db_doc.get_connection()
            total_records = 0
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # 1. Fetch total count
                count_query = f"SELECT COUNT(*) AS total_count FROM ({clean_query}) AS _preview_subquery"
                try:
                    cursor.execute(count_query)
                    count_row = cursor.fetchone()
                    total_records = count_row["total_count"] if count_row else 0
                except Exception:
                    if conn:
                        conn.rollback()

                # 2. Fetch paginated records
                paginated_query = f"SELECT * FROM ({clean_query}) AS _preview_subquery LIMIT {page_len} OFFSET {offset}"
                cursor.execute(paginated_query)
                rows = [dict(row) for row in cursor.fetchall()
                        ] if cursor.description else []

                total_pages = max(1, math.ceil(
                    total_records / page_len)) if total_records else 1

                return {
                    "rows": rows,
                    "columns": list(rows[0].keys()) if rows else [],
                    "total_records": total_records,
                    "page": page,
                    "page_len": page_len,
                    "total_pages": total_pages,
                }
        except Exception as e:
            frappe.throw(_("Source DB Preview failed: {0}").format(str(e)))
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    # @frappe.whitelist()
    # def sync_data(self):
    # 	"""
    # 	Executes DB-to-DB data pipeline synchronization and logs audit request in Database Request.
    # 	"""
    # 	if not self.is_active:
    # 		frappe.throw(_("This Database Integration is inactive. Enable 'Is Active' to run synchronization."))

    # 	if not self.source_database:
    # 		frappe.throw(_("Please select a Source Database."))

    # 	if not self.destination_database:
    # 		frappe.throw(_("Please select a Destination Database."))

    # 	if not self.source_query:
    # 		frappe.throw(_("Please specify a Source Query."))

    # 	if not self.destination_query:
    # 		frappe.throw(_("Please specify a Destination Query."))

    # 	source_query, filter_from, filter_to = self.get_source_query_with_filters()
    # 	rendered_destination_query = self.render_query(self.destination_query)

    # 	source_db_doc = frappe.get_doc("Database Configuration", self.source_database)
    # 	dest_db_doc = frappe.get_doc("Database Configuration", self.destination_database)

    # 	source_conn = None
    # 	dest_conn = None
    # 	dict_rows = []
    # 	records_count = 0
    # 	execution_time = now_datetime()

    # 	try:
    # 		# 1. Fetch data from Source Database as dictionary records
    # 		source_conn = source_db_doc.get_connection()
    # 		with source_conn.cursor(cursor_factory=RealDictCursor) as source_cursor:
    # 			source_cursor.execute(source_query)
    # 			dict_rows = [dict(row) for row in source_cursor.fetchall()] if source_cursor.description else []
    # 			records_count = len(dict_rows)

    # 		# 2. Execute Destination Query in batch mode
    # 		if dict_rows and rendered_destination_query:
    # 			dest_conn = dest_db_doc.get_connection()
    # 			with dest_conn.cursor() as dest_cursor:
    # 				execute_batch(dest_cursor, rendered_destination_query, dict_rows, page_size=100)
    # 				dest_conn.commit()

    # 		log_message = _("Successfully processed {0} record(s).").format(records_count)

    # 		# 3. Calculate new sync_to pointer if incremental
    # 		new_sync_to = filter_to
    # 		if self.enable_date_filter and self.date_filter_mode == "Incremental (Sync From)":
    # 			col = self.date_filter_column.strip() if self.date_filter_column else None
    # 			if dict_rows and col and col in dict_rows[0]:
    # 				vals = [r[col] for r in dict_rows if r.get(col) is not None]
    # 				if vals:
    # 					new_sync_to = str(max(vals))
    # 			elif not new_sync_to:
    # 				new_sync_to = str(filter_from)

    # 		# 4. Format payload with Sr. No. for audit logging
    # 		formatted_payload = [
    # 			{"sr_no": idx + 1, "values": row}
    # 			for idx, row in enumerate(dict_rows)
    # 		]

    # 		# 5. Create Database Request Document as Audit Log
    # 		db_request = frappe.get_doc({
    # 			"doctype": "Database Request",
    # 			"database_integration": self.name,
    # 			"source_database": self.source_database,
    # 			"destination_database": self.destination_database,
    # 			"execution_datetime": execution_time,
    # 			"records_count": records_count,
    # 			"sync_from": str(filter_from) if filter_from else None,
    # 			"sync_to": str(new_sync_to) if new_sync_to else None,
    # 			"status": "Success",
    # 			"synced_payload": json.dumps(formatted_payload, indent=2, default=str),
    # 			"error_log": log_message
    # 		})
    # 		db_request.insert(ignore_permissions=True)

    # 		# 6. Update execution metadata on Database Integration
    # 		self.db_set("last_sync_on", execution_time)
    # 		self.db_set("last_sync_status", "Success")
    # 		self.db_set("records_processed", records_count)
    # 		self.db_set("last_sync_log", log_message)
    # 		if new_sync_to:
    # 			self.db_set("sync_to", str(new_sync_to))
    # 			if self.enable_date_filter and self.date_filter_mode == "Incremental (Sync From)":
    # 				self.db_set("sync_from", str(new_sync_to))

    # 		return log_message

    # 	except Exception as e:
    # 		err_msg = str(e)
    # 		if dest_conn:
    # 			try:
    # 				dest_conn.rollback()
    # 			except Exception:
    # 				pass

    # 		formatted_payload = [
    # 			{"sr_no": idx + 1, "values": row}
    # 			for idx, row in enumerate(dict_rows)
    # 		] if dict_rows else []

    # 		# Log failure in Database Request Document
    # 		try:
    # 			db_request = frappe.get_doc({
    # 				"doctype": "Database Request",
    # 				"database_integration": self.name,
    # 				"source_database": self.source_database,
    # 				"destination_database": self.destination_database,
    # 				"execution_datetime": execution_time,
    # 				"records_count": records_count,
    # 				"status": "Failed",
    # 				"synced_payload": json.dumps(formatted_payload, indent=2, default=str),
    # 				"error_log": err_msg
    # 			})
    # 			db_request.insert(ignore_permissions=True)
    # 		except Exception:
    # 			pass

    # 		self.db_set("last_sync_on", execution_time)
    # 		self.db_set("last_sync_status", "Failed")
    # 		self.db_set("last_sync_log", err_msg)

    # 		frappe.throw(_("Data Pipeline Sync failed: {0}").format(err_msg))

    # 	finally:
    # 		if source_conn:
    # 			try:
    # 				source_conn.close()
    # 			except Exception:
    # 				pass
    # 		if dest_conn:
    # 			try:
    # 				dest_conn.close()
    # 			except Exception:
    # 				pass

    @frappe.whitelist()
    def sync_data(self):
        """
        Executes DB-to-DB data pipeline synchronization and logs audit request in Database Request.
        """
        if not self.is_active:
            frappe.throw(
                _("This Database Integration is inactive. Enable 'Is Active' to run synchronization."))

        if not self.source_database:
            frappe.throw(_("Please select a Source Database."))

        if not self.destination_database:
            frappe.throw(_("Please select a Destination Database."))

        if not self.source_query:
            frappe.throw(_("Please specify a Source Query."))

        if not self.destination_query:
            frappe.throw(_("Please specify a Destination Query."))

        source_query, filter_from, filter_to = self.get_source_query_with_filters()
        rendered_destination_query = self.render_query(self.destination_query)

        source_db_doc = frappe.get_doc(
            "Database Configuration", self.source_database)
        dest_db_doc = frappe.get_doc(
            "Database Configuration", self.destination_database)

        source_conn = None
        dest_conn = None
        dict_rows = []
        records_count = 0
        execution_time = now_datetime()

        try:
            # 1. Fetch data from Source Database as dictionary records
            source_conn = source_db_doc.get_connection()
            with source_conn.cursor(cursor_factory=RealDictCursor) as source_cursor:
                source_cursor.execute(source_query)
                dict_rows = [dict(row) for row in source_cursor.fetchall(
                )] if source_cursor.description else []
            records_count = len(dict_rows)

            # ========== NEW: Filter out already-synced records ==========
            # Build set of (pan, account_number) from all Database Request records
            prev_synced_keys = set()

            db_requests = frappe.get_all(
                "Database Request",
                fields=["synced_payload"],
            )

            for db_req in db_requests:
                payload_raw = db_req.get("synced_payload")
                if not payload_raw:
                    continue

                try:
                    payload = json.loads(payload_raw) if isinstance(
                        payload_raw, str) else payload_raw
                except Exception:
                    continue

                if not isinstance(payload, list):
                    continue

                for item in payload:
                    values = item.get("values") or {}
                    pan = values.get("pan")
                    account_number = values.get("account_number")

                    if not pan or not account_number:
                        continue

                    key = (str(pan).strip(), str(account_number).strip())
                    prev_synced_keys.add(key)

            # Filter dict_rows to only new (pan, account_number)
            new_rows = []
            for row in dict_rows:
                pan = row.get("pan")
                account_number = row.get("account_number")

                if not pan or not account_number:
                    # If you want to always re-sync rows without pan/account_number,
                    # remove this 'continue' and adjust key logic accordingly.
                    new_rows.append(row)
                    continue

                key = (str(pan).strip(), str(account_number).strip())
                if key not in prev_synced_keys:
                    new_rows.append(row)

            dict_rows = new_rows
            records_count = len(dict_rows)
            # ========== END NEW FILTER BLOCK ==========

            # 2. Execute Destination Query in batch mode
            if dict_rows and rendered_destination_query:
                dest_conn = dest_db_doc.get_connection()
                with dest_conn.cursor() as dest_cursor:
                    execute_batch(
                        dest_cursor, rendered_destination_query, dict_rows, page_size=100)
                dest_conn.commit()

            log_message = _("Successfully processed {0} record(s).").format(
                records_count)

            # 3. Calculate new sync_to pointer if incremental
            new_sync_to = filter_to
            if self.enable_date_filter and self.date_filter_mode == "Incremental (Sync From)":
                col = self.date_filter_column.strip() if self.date_filter_column else None
                if dict_rows and col and col in dict_rows[0]:
                    vals = [r[col]
                            for r in dict_rows if r.get(col) is not None]
                    if vals:
                        new_sync_to = str(max(vals))
                elif not new_sync_to:
                    new_sync_to = str(filter_from)

            # 4. Format payload with Sr. No. for audit logging
            formatted_payload = [
                {"sr_no": idx + 1, "values": row}
                for idx, row in enumerate(dict_rows)
            ]

            # 5. Create Database Request Document as Audit Log
            db_request = frappe.get_doc({
                "doctype": "Database Request",
                "database_integration": self.name,
                "source_database": self.source_database,
                "destination_database": self.destination_database,
                "execution_datetime": execution_time,
                "records_count": records_count,
                "sync_from": str(filter_from) if filter_from else None,
                "sync_to": str(new_sync_to) if new_sync_to else None,
                "status": "Success",
                "synced_payload": json.dumps(formatted_payload, indent=2, default=str),
                "error_log": log_message
            })
            db_request.insert(ignore_permissions=True)

            # 6. Update execution metadata on Database Integration
            self.db_set("last_sync_on", execution_time)
            self.db_set("last_sync_status", "Success")
            self.db_set("records_processed", records_count)
            self.db_set("last_sync_log", log_message)
            if new_sync_to:
                self.db_set("sync_to", str(new_sync_to))
            if self.enable_date_filter and self.date_filter_mode == "Incremental (Sync From)":
                self.db_set("sync_from", str(new_sync_to))

            return log_message

        except Exception as e:
            err_msg = str(e)
            if dest_conn:
                try:
                    dest_conn.rollback()
                except Exception:
                    pass

            formatted_payload = [
                {"sr_no": idx + 1, "values": row}
                for idx, row in enumerate(dict_rows)
            ] if dict_rows else []

            # Log failure in Database Request Document
            try:
                db_request = frappe.get_doc({
                    "doctype": "Database Request",
                    "database_integration": self.name,
                    "source_database": self.source_database,
                    "destination_database": self.destination_database,
                    "execution_datetime": execution_time,
                    "records_count": records_count,
                    "status": "Failed",
                    "synced_payload": json.dumps(formatted_payload, indent=2, default=str),
                    "error_log": err_msg
                })
                db_request.insert(ignore_permissions=True)
            except Exception:
                pass

            self.db_set("last_sync_on", execution_time)
            self.db_set("last_sync_status", "Failed")
            self.db_set("last_sync_log", err_msg)

            frappe.throw(_("Data Pipeline Sync failed: {0}").format(err_msg))

        finally:
            if source_conn:
                try:
                    source_conn.close()
                except Exception:
                    pass
            if dest_conn:
                try:
                    dest_conn.close()
                except Exception:
                    pass


def execute_scheduled_sync(frequency):
    """
    Executes all active Database Integration data pipelines matching the given sync_frequency.
    """
    integrations = frappe.get_all(
        "Database Integration",
        filters={"sync_frequency": frequency, "is_active": 1},
        pluck="name"
    )
    for name in integrations:
        try:
            doc = frappe.get_doc("Database Integration", name)
            doc.sync_data()
        except Exception as e:
            frappe.log_error(
                title=f"Database Integration Scheduled Sync Failed for {name}",
                message=frappe.get_traceback()
            )


def execute_hourly_sync():
    execute_scheduled_sync("Hourly")


def execute_daily_sync():
    execute_scheduled_sync("Daily")
