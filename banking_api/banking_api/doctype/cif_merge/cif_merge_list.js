frappe.listview_settings['CIF Merge'] = {
	onload: function(listview) {
		// Status Capsules (Active / Inactive / All) & Count Filter
		frappe.call({
			method: 'banking_api.banking_api.doctype.cif_merge.cif_merge.get_status_summary',
			callback: function(r) {
				const summary = r.message || { Active: 0, Inactive: 0, Total: 0 };
				const fmt = (num) => Number(num || 0).toLocaleString('en-IN');

				const $container = $(`
					<div class="cif-custom-toolbar-filters d-flex align-items-center" style="gap: 6px; display: inline-flex;">
						<button class="btn btn-xs btn-default cif-report-btn text-primary font-weight-bold" style="border-radius: 12px; border: 1px solid #93c5fd; background: #eff6ff;" title="${__('View CIF Merge Status Report')}">
							<i class="fa fa-bar-chart mr-1"></i>${__('Report')}
						</button>
						<button class="btn btn-xs btn-default cif-count-filter-btn text-muted font-weight-bold" style="border-radius: 12px; border: 1px solid #d1d5db;" title="${__('Filter by CIF count')}">
							<i class="fa fa-filter mr-1"></i>${__('Count Filter')}
						</button>
						<button class="btn btn-xs btn-default text-success font-weight-bold" style="border-radius: 12px; border: 1px solid #86efac; background: #f0fdf4;" title="Filter Active CIFs">
							● Active <span class="badge badge-success ml-1">${fmt(summary.Active)}</span>
						</button>
						<button class="btn btn-xs btn-default text-danger font-weight-bold" style="border-radius: 12px; border: 1px solid #fca5a5; background: #fef2f2;" title="Filter Inactive CIFs">
							● Inactive <span class="badge badge-danger ml-1">${fmt(summary.Inactive)}</span>
						</button>
						<button class="btn btn-xs btn-default text-muted" style="border-radius: 12px; border: 1px solid #e2e8f0; background: #f8fafc;" title="Clear Status Filter">
							All <span class="badge badge-light border ml-1">${fmt(summary.Total)}</span>
						</button>
					</div>
				`);

				// Report shortcut button click
				$container.find('.cif-report-btn').on('click', function() {
					frappe.set_route('query-report', 'CIF Merge Status Report');
				});

				// Count filter click
				$container.find('.cif-count-filter-btn').on('click', function() {
					frappe.call({
						method: 'banking_api.banking_api.doctype.cif_merge.cif_merge.get_top_cif_counts',
						freeze: true,
						freeze_message: __('Loading CIF counts...'),
						callback: function(res) {
							const data = res.message || [];
							if (!data.length) {
								frappe.msgprint(__('No CIF records found.'));
								return;
							}
							show_top_cif_dialog(listview, data);
						}
					});
				});

				// Filter actions
				$container.find('.text-success').on('click', function() {
					listview.filter_area.clear();
					listview.filter_area.add([['CIF Merge', 'status', '=', 'Active']]);
				});

				$container.find('.text-danger').on('click', function() {
					listview.filter_area.clear();
					listview.filter_area.add([['CIF Merge', 'status', '=', 'Inactive']]);
				});

				$container.find('.text-muted').not('.cif-count-filter-btn').on('click', function() {
					listview.filter_area.clear();
				});

				if (listview.page.custom_actions) {
					listview.page.custom_actions.removeClass('hide');
				}

				if (listview.page.inner_toolbar) {
					listview.page.inner_toolbar.append($container);
				} else {
					listview.page.add_inner_button($container);
				}

				// Hide only the view switcher dropdown button
				listview.page.wrapper.find('.custom-btn-group').hide();
			}
		});

		// Explicitly add List Settings to Page Menu
		listview.page.add_menu_item(__('List Settings'), function() {
			listview.show_list_settings();
		});
	},
	refresh: function(listview) {
		// Ensure only view switcher is hidden and filters container remains visible
		if (listview.page && listview.page.wrapper) {
			listview.page.wrapper.find('.custom-btn-group').hide();
		}
	},
	get_indicator: function(doc) {
		if (doc.status === "Active") {
			return [__("Active"), "green", "status,=,Active"];
		} else {
			return [__("Inactive"), "red", "status,=,Inactive"];
		}
	},
	formatters: {
		status: function(val) {
			if (val === "Active") {
				return `<span class="indicator-pill green">${__("Active")}</span>`;
			} else {
				return `<span class="indicator-pill red">${__("Inactive")}</span>`;
			}
		},
		cif_status: function(val) {
			let status = val || "Draft";
			let map = {
				"Draft": { color: "gray", label: __("Draft") },
				"Pending": { color: "orange", label: __("Pending") },
				"Pending Verification": { color: "orange", label: __("Pending Verification") },
				"Approved": { color: "green", label: __("Approved") },
				"Completed": { color: "green", label: __("Approved") },
				"Rejected": { color: "red", label: __("Rejected") },
				"No Action Needed": { color: "blue", label: __("No Action Needed") }
			};
			let info = map[status] || { color: "gray", label: status };
			return `<span class="indicator-pill ${info.color} font-weight-bold">${info.label}</span>`;
		}
	}
};

function show_top_cif_dialog(listview, data) {
	let rowsHtml = data.map((item, index) => `
		<tr style="cursor: pointer;" class="top-cif-row" data-count="${item.total_cif_count}">
			<td class="text-center font-weight-bold">${index + 1}</td>
			<td><span class="badge badge-primary font-weight-bold" style="font-size: 13px;">${item.total_cif_count} CIFs</span></td>
			<td><b>${item.doc_count}</b> Aadhaars</td>
			<td class="text-right"><button class="btn btn-xs btn-primary apply-filter-btn" data-count="${item.total_cif_count}">Filter</button></td>
		</tr>
	`).join('');

	const d = new frappe.ui.Dialog({
		title: __('CIF Count Filter'),
		fields: [
			{
				fieldname: 'html_table',
				fieldtype: 'HTML',
				options: `
					<div class="table-responsive" style="max-height: 450px; overflow-y: auto;">
						<table class="table table-bordered table-hover mb-0">
							<thead class="thead-light">
								<tr>
									<th style="width: 50px;" class="text-center">#</th>
									<th>CIFs per Aadhaar</th>
									<th>Total Aadhaar Count</th>
									<th style="width: 80px;" class="text-right">Action</th>
								</tr>
							</thead>
							<tbody>
								${rowsHtml}
							</tbody>
						</table>
					</div>
				`
			}
		]
	});

	d.show();

	d.$wrapper.find('.apply-filter-btn, .top-cif-row').on('click', function(e) {
		const count = $(this).data('count');
		if (count !== undefined) {
			listview.filter_area.clear();
			listview.filter_area.add([['CIF Merge', 'total_cif_count', '=', parseInt(count)]]);
			d.hide();
		}
	});
}
