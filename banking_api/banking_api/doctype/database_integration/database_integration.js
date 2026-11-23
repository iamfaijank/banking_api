// Copyright (c) 2026, Talib Sheikh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Database Integration", {
	refresh(frm) {
		frm.trigger("toggle_buttons");
	},

	is_active(frm) {
		frm.trigger("toggle_buttons");
	},

	sync_frequency(frm) {
		frm.trigger("toggle_buttons");
	},

	toggle_buttons(frm) {
		frm.remove_custom_button(__("Sync"));
		frm.remove_custom_button(__("Preview Source Data"));

		if (!frm.is_new()) {
			// Add Preview Source Data button
			frm.add_custom_button(__("Preview Source Data"), function () {
				show_paginated_preview_dialog(frm);
			});

			if (frm.doc.is_active && frm.doc.sync_frequency === "Manual") {
				frm.add_custom_button(__("Sync"), function () {
					frm.call({
						doc: frm.doc,
						method: "sync_data",
						freeze: true,
						freeze_message: __("Running DB to DB Data Pipeline Sync..."),
						callback: function (r) {
							if (!r.exc) {
								frappe.msgprint({
									title: __("Pipeline Sync Successful"),
									indicator: "green",
									message: r.message || __("Data sync completed successfully."),
								});
								frm.reload_doc();
							}
						},
					});
				}).addClass("btn-primary");
			}
		}
	},
});

function show_paginated_preview_dialog(frm) {
	let state = {
		page: 1,
		page_len: 20,
		total_records: 0,
		total_pages: 1,
		rows: [],
		columns: [],
		filter_text: "",
	};

	let dialog = new frappe.ui.Dialog({
		title: __("Source Database Data Preview"),
		size: "extra-large",
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "preview_container",
			},
		],
	});

	dialog.show();

	const wrapper = dialog.fields_dict.preview_container.$wrapper;
	wrapper.html(`
		<div class="db-preview-container" style="display: flex; flex-direction: column; gap: 12px;">
			<!-- Top Control Bar -->
			<div class="d-flex justify-content-between align-items-center flex-wrap" style="gap: 10px; background: var(--fg-color, #f8f9fa); padding: 10px 14px; border-radius: 8px; border: 1px solid var(--border-color, #e2e8f0);">
				<div class="d-flex align-items-center flex-wrap" style="gap: 12px;">
					<span class="badge badge-info" id="preview-total-badge" style="font-size: 13px; padding: 6px 10px;">
						${__("Total Records")}: <strong id="preview-total-count">...</strong>
					</span>
					<div class="d-flex align-items-center" style="gap: 6px;">
						<label class="mb-0 text-muted font-sm">${__("Rows per page")}:</label>
						<select id="preview-page-len" class="form-control form-control-sm" style="width: 80px; display: inline-block;">
							<option value="10">10</option>
							<option value="20" selected>20</option>
							<option value="50">50</option>
							<option value="100">100</option>
						</select>
					</div>
				</div>

				<div class="d-flex align-items-center" style="gap: 10px;">
					<input type="text" id="preview-search" class="form-control form-control-sm" placeholder="${__("Filter loaded rows...")}" style="width: 180px;">
					<button class="btn btn-sm btn-default" id="preview-export-btn" title="${__("Export this page to CSV")}">
						<i class="fa fa-download mr-1"></i> ${__("Export CSV")}
					</button>
				</div>
			</div>

			<!-- Data Table Viewport -->
			<div id="preview-table-wrapper" style="max-height: 480px; min-height: 220px; overflow: auto; border: 1px solid var(--border-color, #e2e8f0); border-radius: 6px; position: relative;">
				<div id="preview-loading" class="text-center py-5 text-muted">
					<i class="fa fa-spinner fa-spin fa-2x"></i>
					<div class="mt-2 font-sm">${__("Fetching query records...")}</div>
				</div>
				<div id="preview-table-content" style="display: none;"></div>
			</div>

			<!-- Bottom Pagination Footer -->
			<div class="d-flex justify-content-between align-items-center flex-wrap" style="gap: 10px; padding: 6px 4px;">
				<div class="text-muted font-sm" id="preview-page-summary">
					${__("Showing")} 0 - 0
				</div>
				<div class="d-flex align-items-center" style="gap: 6px;">
					<button class="btn btn-xs btn-default" id="btn-first" title="${__("First Page")}">
						<i class="fa fa-angle-double-left"></i> ${__("First")}
					</button>
					<button class="btn btn-xs btn-default" id="btn-prev" title="${__("Previous Page")}">
						<i class="fa fa-angle-left"></i> ${__("Prev")}
					</button>
					<span class="mx-2 font-sm" id="preview-page-indicator" style="font-weight: 600;">
						${__("Page 1 of 1")}
					</span>
					<button class="btn btn-xs btn-default" id="btn-next" title="${__("Next Page")}">
						${__("Next")} <i class="fa fa-angle-right"></i>
					</button>
					<button class="btn btn-xs btn-default" id="btn-last" title="${__("Last Page")}">
						${__("Last")} <i class="fa fa-angle-double-right"></i>
					</button>
				</div>
			</div>
		</div>
	`);

	function fetch_data(target_page) {
		wrapper.find("#preview-loading").show();
		wrapper.find("#preview-table-content").hide();
		set_pagination_buttons_disabled(true);

		frm.call({
			doc: frm.doc,
			method: "preview_source_data",
			args: {
				page: target_page || state.page,
				page_len: state.page_len,
			},
			callback: function (r) {
				wrapper.find("#preview-loading").hide();
				if (r.message) {
					state.rows = r.message.rows || [];
					state.columns = r.message.columns || [];
					state.total_records = r.message.total_records || 0;
					state.page = r.message.page || 1;
					state.page_len = r.message.page_len || 20;
					state.total_pages = r.message.total_pages || 1;

					render_table();
					update_pagination_ui();
				}
			},
			error: function () {
				wrapper.find("#preview-loading").html(`
					<div class="text-danger p-4">
						<i class="fa fa-exclamation-triangle fa-2x mb-2"></i>
						<div>${__("Failed to fetch data from Source Database.")}</div>
					</div>
				`).show();
			},
		});
	}

	function render_table() {
		const $content = wrapper.find("#preview-table-content");
		let display_rows = state.rows;

		if (state.filter_text) {
			const query = state.filter_text.toLowerCase();
			display_rows = state.rows.filter((row) =>
				Object.values(row).some((val) => val !== null && String(val).toLowerCase().includes(query))
			);
		}

		if (!display_rows.length) {
			$content.html(`
				<div class="text-center py-5 text-muted">
					<i class="fa fa-inbox fa-2x mb-2 text-muted"></i>
					<div>${state.rows.length ? __("No records match your filter.") : __("0 records returned for this query.")}</div>
				</div>
			`).show();
			return;
		}

		const columns = state.columns.length ? state.columns : Object.keys(display_rows[0]);
		const start_idx = (state.page - 1) * state.page_len;

		let html = `
			<table class="table table-bordered table-hover table-striped mb-0 font-sm" style="width: 100%; border-collapse: separate; border-spacing: 0;">
				<thead style="position: sticky; top: 0; background: var(--bg-light-gray, #edf2f7); z-index: 2; box-shadow: 0 1px 2px rgba(0,0,0,0.06);">
					<tr>
						<th style="width: 50px; text-align: center;">#</th>
						${columns.map((col) => `<th class="text-nowrap" style="padding: 8px 12px;">${frappe.model.unscrub(col)}</th>`).join("")}
					</tr>
				</thead>
				<tbody>
					${display_rows.map((row, idx) => `
						<tr>
							<td style="text-align: center; color: var(--text-muted, #718096); font-weight: 500;">
								${start_idx + idx + 1}
							</td>
							${columns.map((col) => {
								const val = row[col];
								let cell_html = "";
								if (val === null || val === undefined) {
									cell_html = `<span class="badge badge-light text-muted" style="font-weight: normal; font-size: 11px;">null</span>`;
								} else if (typeof val === "boolean") {
									cell_html = val ? `<span class="text-success font-weight-bold">TRUE</span>` : `<span class="text-danger font-weight-bold">FALSE</span>`;
								} else {
									cell_html = frappe.utils.escape_html(String(val));
								}
								return `<td style="padding: 6px 12px; max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${frappe.utils.escape_html(String(val || ''))}">${cell_html}</td>`;
							}).join("")}
						</tr>
					`).join("")}
				</tbody>
			</table>
		`;

		$content.html(html).show();
	}

	function update_pagination_ui() {
		wrapper.find("#preview-total-count").text(state.total_records.toLocaleString());
		wrapper.find("#preview-page-indicator").text(__("Page {0} of {1}", [state.page, state.total_pages]));

		const start = state.total_records === 0 ? 0 : (state.page - 1) * state.page_len + 1;
		const end = Math.min(state.page * state.page_len, state.total_records);
		wrapper.find("#preview-page-summary").text(
			__("Showing {0} - {1} of {2} records", [start, end, state.total_records.toLocaleString()])
		);

		wrapper.find("#btn-first, #btn-prev").prop("disabled", state.page <= 1);
		wrapper.find("#btn-next, #btn-last").prop("disabled", state.page >= state.total_pages);
	}

	function set_pagination_buttons_disabled(disabled) {
		wrapper.find("#btn-first, #btn-prev, #btn-next, #btn-last").prop("disabled", disabled);
	}

	// Event Handlers
	wrapper.find("#btn-first").on("click", function () {
		if (state.page > 1) fetch_data(1);
	});

	wrapper.find("#btn-prev").on("click", function () {
		if (state.page > 1) fetch_data(state.page - 1);
	});

	wrapper.find("#btn-next").on("click", function () {
		if (state.page < state.total_pages) fetch_data(state.page + 1);
	});

	wrapper.find("#btn-last").on("click", function () {
		if (state.page < state.total_pages) fetch_data(state.total_pages);
	});

	wrapper.find("#preview-page-len").on("change", function () {
		state.page_len = parseInt($(this).val(), 10) || 20;
		fetch_data(1);
	});

	wrapper.find("#preview-search").on("input", function () {
		state.filter_text = $(this).val();
		render_table();
	});

	wrapper.find("#preview-export-btn").on("click", function () {
		if (!state.rows.length) {
			frappe.msgprint(__("No data to export."));
			return;
		}
		const csv_content = frappe.tools.to_csv(state.rows);
		frappe.tools.downloadify(csv_content, null, `preview_${frm.doc.name}_page_${state.page}`);
	});

	// Initial Load
	fetch_data(1);
}
