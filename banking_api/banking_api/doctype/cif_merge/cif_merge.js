frappe.ui.form.on("CIF Merge", {
	onload(frm) {
		let is_admin = frappe.user_roles.includes("System Manager") || frappe.session.user === "Administrator";
		frm.toggle_display("cif_details", is_admin);
	},
	refresh(frm) {
		frm.set_df_property("aadhar", "hidden", 0);
		let is_admin = frappe.user_roles.includes("System Manager") || frappe.session.user === "Administrator";
		frm.toggle_display("cif_details", is_admin);

		// Workflow status indicator badge
		let status = frm.doc.cif_status || "Draft";
		let status_colors = {
			"Draft": "gray",
			"Pending Verification": "orange",
			"Approved": "green",
			"Rejected": "red",
			"No Action Needed": "blue"
		};
		frm.page.set_indicator(__(status), status_colors[status] || "gray");

		// Role checks
		let is_maker = frappe.user_roles.includes("CIF Maker") || is_admin;
		let is_checker = frappe.user_roles.includes("CIF Checker") || is_admin;

		let handle_workflow_action = function(action, confirm_msg) {
			frappe.confirm(confirm_msg, function() {
				let call_action = function() {
					frappe.call({
						method: "banking_api.banking_api.doctype.cif_merge.cif_merge.update_workflow_status",
						args: {
							docname: frm.doc.name,
							action: action
						},
						freeze: true,
						freeze_message: __("Updating CIF Merge status..."),
						callback: function(r) {
							if (r.message) {
								frappe.show_alert({ message: __(r.message.message), indicator: "green" });
								frm.reload_doc();
							}
						}
					});
				};

				if (action === "send_to_checker") {
					// Maker sending to checker - always force save first
					frm.dirty();
					frm.save().then(() => {
						call_action();
					}).catch(() => {
						frappe.msgprint(__("Error saving form before sending to checker."));
					});
				} else {
					call_action();
				}
			});
		};

		if (status === "No Action Needed") {
			frm.set_intro(__("This CIF Merge record is marked as <b>No Action Needed</b>."), "blue");
			frm.set_read_only();
		} else if (status === "Approved") {
			frm.set_intro(__("This CIF Merge record is <b>Approved</b>."), "green");
			frm.set_read_only();
		} else if (status === "Rejected") {
			frm.set_intro(__("This CIF Merge record has been <b>Rejected</b> by Checker."), "red");
		} else if (status === "Pending Verification") {
			frm.set_intro(__("Record is pending verification by <b>CIF Checker</b>."), "orange");
		}

		// Standard Frappe Workflow renders all actions in Actions dropdown

		let expected_count = frm.doc.total_cif_count || 0;
		let current_count = (frm.doc.cif_details || []).length;

		if (!frm.is_new() && expected_count > current_count) {
			frappe.call({
				method: "banking_api.banking_api.doctype.cif_merge.cif_merge.get_full_cif_details",
				args: { parent: frm.doc.name },
				callback: function(r) {
					if (r.message && r.message.length) {
						frm.doc.cif_details = r.message;
						frm.trigger("render_custom_table");
					}
				}
			});
		} else {
			frm.trigger("render_custom_table");
		}
	},
	cif_details_on_form_rendered(frm) {
		let is_admin = frappe.user_roles.includes("System Manager") || frappe.session.user === "Administrator";
		frm.toggle_display("cif_details", is_admin);
		let expected_count = frm.doc.total_cif_count || 0;
		let current_count = (frm.doc.cif_details || []).length;

		if (!frm.is_new() && expected_count > current_count) {
			frappe.call({
				method: "banking_api.banking_api.doctype.cif_merge.cif_merge.get_full_cif_details",
				args: { parent: frm.doc.name },
				callback: function(r) {
					if (r.message && r.message.length) {
						frm.doc.cif_details = r.message;
						frm.trigger("render_custom_table");
					}
				}
			});
		} else {
			frm.trigger("render_custom_table");
		}
	},
	aadhar(frm) {
		frm.trigger("fetch_cifs");
	},
	pan(frm) {
		frm.trigger("fetch_cifs");
	},
	fetch_cifs(frm) {
		if (!frm.doc.aadhar && !frm.doc.pan) {
			frm.clear_table("cif_details");
			frm.refresh_field("cif_details");
			frm.trigger("render_custom_table");
			return;
		}
		frappe.call({
			method: "banking_api.banking_api.doctype.cif_merge.cif_merge.get_cif_records",
			args: {
				aadhar: frm.doc.aadhar,
				pan: frm.doc.pan
			},
			callback: function(r) {
				frm.clear_table("cif_details");
				if (r.message && r.message.length > 0) {
					if (!frm.doc.aadhar && r.message[0] && r.message[0].aadhar) {
						frm.set_value("aadhar", r.message[0].aadhar);
					}
					r.message.forEach(row => {
						let child = frm.add_child("cif_details");
						child.cif_id = row.cif_id;
						child.first_name = row.first_name;
						child.middle_name = row.middle_name;
						child.last_name = row.last_name;
						child.cif_creation = row.cif_creation;
						child.date_of_birth = row.date_of_birth;
						child.pan = row.pan;
						child.mobile = row.mobile;
						child.phone_local_code = row.phone_local_code;
						child.sol_id = row.sol_id;
						child.address_line_1 = row.address_line_1;
						child.address_line_2 = row.address_line_2;
						child.address_line_3 = row.address_line_3;
						child.pin_code = row.pin_code;
						child.active_accounts_count = row.active_accounts_count || 0;
						child.active_account_numbers = row.active_account_numbers || "";
						child.primary = row.primary || 0;
						child.merge = row.merge || 0;
						child.re_kyc = row.re_kyc || 0;
					});
				}
				frm.refresh_field("cif_details");
				frm.trigger("render_custom_table");
			}
		});
	},
	render_custom_table(frm) {
		if (!frm.fields_dict.merge_widget) return;
		let wrapper = $(frm.fields_dict.merge_widget.wrapper);
		wrapper.empty();

		let data = frm.doc.cif_details || [];
		if (!data.length) {
			wrapper.html(`
				<div class="p-4 text-center border rounded bg-light text-muted small">
					<i class="fa fa-info-circle mr-1"></i> Search Aadhar or PAN to load and match CIF records.
				</div>
			`);
			return;
		}

		// Collect individual word tokens as well as full names
		let counts = {};
		data.forEach(row => {
			let fn = (row.first_name || '').trim().toLowerCase();
			let ln = (row.last_name || '').trim().toLowerCase();
			
			let words = [...fn.split(/\s+/), ...ln.split(/\s+/)].filter(w => w.length >= 2);
			words.forEach(w => {
				counts[w] = (counts[w] || 0) + 1;
			});
		});

		let color_themes = [
			{ bg: '#dcfce7', text: '#15803d', border: '#86efac' },
			{ bg: '#e0e7ff', text: '#4338ca', border: '#a5b4fc' },
			{ bg: '#ffedd5', text: '#c2410c', border: '#fdba74' },
			{ bg: '#fce7f3', text: '#be185d', border: '#f9a8d4' },
			{ bg: '#e0f2fe', text: '#0369a1', border: '#7dd3fc' },
			{ bg: '#ccfbf1', text: '#0f766e', border: '#5eead4' },
			{ bg: '#fae8ff', text: '#86198f', border: '#f0abfc' },
			{ bg: '#fef9c3', text: '#854d0e', border: '#fde047' }
		];

		let token_map = {};
		let c_idx = 0;
		// Sort longer tokens first so larger substrings match first
		let sorted_tokens = Object.keys(counts).filter(t => counts[t] >= 2).sort((a, b) => b.length - a.length);

		sorted_tokens.forEach(token => {
			token_map[token] = {
				theme: color_themes[c_idx % color_themes.length],
				count: counts[token]
			};
			c_idx++;
		});

		let escape_html = (str) => frappe.utils.escape_html(str || '');

		let format_date = (d) => {
			if (!d) return '-';
			let s = String(d).trim();
			// Agar YYYY-MM-DD ya YYYY-MM-DD HH:mm:ss format ho
			let m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
			if (m) {
				return `${m[3]}/${m[2]}/${m[1]}`;
			}
			return escape_html(frappe.datetime.str_to_user ? frappe.datetime.str_to_user(s) : s);
		};

		let render_token_name = (name) => {
			if (!name) return '<span class="text-muted font-italic small">Empty</span>';
			let clean = name.trim();
			let words = clean.split(/(\s+)/); // keep whitespace separators

			return words.map(chunk => {
				let lower = chunk.toLowerCase();
				if (token_map[lower]) {
					let t = token_map[lower].theme;
					return `
						<span class="cif-token-badge font-weight-bold" 
							data-token="${lower}"
							style="background:${t.bg}; color:${t.text}; border:1px solid ${t.border}; padding: 2px 6px; border-radius: 4px; display: inline-block; cursor: pointer; transition: all 0.2s;"
							title="Matched substring/word '${lower}' across ${token_map[lower].count} rows">
							${escape_html(chunk)}
						</span>
					`;
				}
				// Partial substring inside a chunk
				let sub_token = sorted_tokens.find(st => st.length >= 3 && lower.includes(st));
				if (sub_token) {
					let t = token_map[sub_token].theme;
					let regex = new RegExp(`(${sub_token})`, 'gi');
					return escape_html(chunk).replace(regex, `<span class="cif-token-badge font-weight-bold" data-token="${sub_token}" style="background:${t.bg}; color:${t.text}; border:1px solid ${t.border}; padding: 1px 5px; border-radius: 3px;" title="Substring match '${sub_token}'">$1</span>`);
				}
				return escape_html(chunk);
			}).join('');
		};

		let primary_count = data.filter(r => r.primary).length;
		let merge_count = data.filter(r => r.merge).length;
		let rekyc_count = data.filter(r => r.re_kyc).length;

		let legend_pills = Object.keys(token_map).map(token => {
			let item = token_map[token];
			let t = item.theme;
			return `
				<span class="cif-token-badge font-weight-bold mr-1 mb-1" 
					data-token="${token}"
					style="background:${t.bg}; color:${t.text}; border:1px solid ${t.border}; padding: 3px 8px; border-radius: 4px; display: inline-block; font-size: 11px; cursor: pointer;">
					${token.toUpperCase()} <span style="opacity: 0.8; font-weight: normal;">(${item.count})</span>
				</span>
			`;
		}).join('') || '<span class="text-muted font-italic small">No duplicate string tokens detected</span>';

		let is_admin = frappe.user_roles.includes("System Manager") || frappe.session.user === "Administrator";
		let is_maker = frappe.user_roles.includes("CIF Maker") || is_admin;
		let status = frm.doc.cif_status || "Draft";
		let is_editable = is_admin || ((status === "Draft" || status === "Rejected" || status === "Pending") && is_maker);
		let disabled_attr = is_editable ? '' : 'disabled';
		let chk_cursor = is_editable ? 'cursor:pointer;' : 'cursor:not-allowed; opacity:0.65;';

		let rows_html = data.map((row, idx) => {
			let row_style = "";
			let row_class = "";
			if (row.primary) {
				row_class = "table-success";
				row_style = "border-left: 5px solid #16a34a; background-color: #f0fdf4;";
			} else if (row.merge) {
				row_style = "border-left: 5px solid #9333ea; background-color: #faf5ff;";
			} else if (row.re_kyc) {
				row_style = "border-left: 5px solid #d97706; background-color: #fffbeb;";
			}

			return `
				<tr class="${row_class}" style="${row_style}" data-idx="${idx}">
					<td class="text-center text-muted small">${idx + 1}</td>
					<td>
						<span class="font-weight-bold">${escape_html(row.cif_id)}</span>
						${row.primary ? '<span class="badge badge-success ml-1">PRIMARY</span>' : ''}
						${row.merge ? '<span class="badge ml-1" style="background:#9333ea; color:white;">MERGE</span>' : ''}
						${row.re_kyc ? '<span class="badge badge-warning ml-1">RE-KYC</span>' : ''}
					</td>
					<td>${render_token_name(row.first_name)}</td>
					<td>${render_token_name(row.last_name)}</td>
					<td class="text-muted small">${format_date(row.cif_creation)}</td>
					<td class="text-center">
						<input type="checkbox" class="cif-primary-chk" data-idx="${idx}" ${row.primary ? 'checked' : ''} ${disabled_attr} style="${chk_cursor} width:16px; height:16px;">
					</td>
					<td class="text-center">
						<input type="checkbox" class="cif-merge-chk" data-idx="${idx}" ${row.merge ? 'checked' : ''} ${disabled_attr} style="${chk_cursor} width:16px; height:16px;">
					</td>
					<td class="text-center">
						<input type="checkbox" class="cif-rekyc-chk" data-idx="${idx}" ${row.re_kyc ? 'checked' : ''} ${disabled_attr} style="${chk_cursor} width:16px; height:16px;">
					</td>
				</tr>
			`;
		}).join('');

		let widget_html = `
		<style>
			.cif-scroll-wrapper {
				overflow-x: scroll !important;
				overflow-y: auto !important;
				scrollbar-width: thin !important;
				scrollbar-color: #64748b #f1f5f9 !important;
				-webkit-overflow-scrolling: touch;
				display: block;
				width: 100%;
			}
			.cif-scroll-wrapper::-webkit-scrollbar {
				width: 10px !important;
				height: 10px !important;
			}
			.cif-scroll-wrapper::-webkit-scrollbar-track {
				background: #f1f5f9 !important;
				border-radius: 4px;
				border: 1px solid #e2e8f0;
			}
			.cif-scroll-wrapper::-webkit-scrollbar-thumb {
				background: #64748b !important;
				border-radius: 4px;
			}
			.cif-scroll-wrapper::-webkit-scrollbar-thumb:hover {
				background: #475569 !important;
			}
		</style>
		<div class="cif-table-control-container p-3 bg-white border rounded shadow-sm mb-3">
			<!-- Header & Action Status -->
			<div class="d-flex justify-content-between align-items-center mb-2 pb-2 border-bottom flex-wrap gap-2">
				<div>
					<h6 class="m-0 font-weight-bold text-dark"><i class="fa fa-users text-primary mr-1"></i> CIF Deduplication & Table Control</h6>
					<small class="text-muted">Multi-color tokens highlight duplicate names and substrings across records.</small>
				</div>
				<div class="d-flex align-items-center gap-2">
					<span class="badge badge-success px-2 py-1">Primary: ${primary_count}</span>
					<span class="badge px-2 py-1" style="background-color: #9333ea; color: white;">Merge: ${merge_count}</span>
					<span class="badge badge-warning px-2 py-1">Re-KYC: ${rekyc_count}</span>
				</div>
			</div>

			<!-- Active Duplicate Token Legends -->
			<div class="p-2 mb-3 rounded bg-light border d-flex align-items-center flex-wrap gap-1">
				<strong class="text-secondary small mr-2"><i class="fa fa-tags mr-1"></i> Duplicate Tokens:</strong>
				<div class="d-flex flex-wrap align-items-center">${legend_pills}</div>
			</div>

			<!-- Table 1: Actions & Deduplication Control -->
			<div class="mb-3">
				<h6 class="text-secondary font-weight-bold mb-1" style="font-size: 13px;"><i class="fa fa-sliders mr-1 text-primary"></i> 1. CIF Selection & Deduplication Table (${data.length} CIFs)</h6>
				<div class="cif-scroll-wrapper border rounded" style="max-height: none; overflow-y: visible;">
					<table class="table table-sm table-bordered m-0" style="vertical-align: middle; min-width: 600px;">
						<thead class="thead-light small" style="position: sticky; top: 0; z-index: 2; background: #f8f9fa;">
							<tr>
								<th style="width: 40px;" class="text-center">#</th>
								<th style="min-width: 120px;">CIF ID</th>
								<th style="min-width: 140px;">First Name</th>
								<th style="min-width: 140px;">Last Name</th>
								<th style="min-width: 110px;">Creation Date</th>
								<th style="width: 90px;" class="text-center bg-success text-white">Primary</th>
								<th style="width: 105px;" class="text-center text-dark" style="background:#e9d5ff;">
									<div class="d-flex align-items-center justify-content-center gap-1">
										<input type="checkbox" class="cif-merge-select-all" ${disabled_attr} style="${chk_cursor} width:15px; height:15px;" title="Select all except Primary" ${data.length > 1 && data.filter(r => !r.primary).every(r => r.merge) ? 'checked' : ''}>
										<span>Merge</span>
									</div>
								</th>
								<th style="width: 90px;" class="text-center bg-warning text-dark">Re KYC</th>
							</tr>
						</thead>
						<tbody>
							${rows_html}
						</tbody>
					</table>
				</div>
			</div>

			<!-- Table 2: User Other Details -->
			<div class="mb-3">
				<h6 class="text-secondary font-weight-bold mb-1" style="font-size: 13px;"><i class="fa fa-id-card-o mr-1 text-info"></i> 2. CIF User Full Details (${data.length} CIFs)</h6>
				<div class="cif-scroll-wrapper border rounded" style="max-height: none; overflow-y: visible;">
					<table class="table table-sm table-hover table-bordered m-0" style="vertical-align: middle; min-width: 1350px;">
						<thead class="thead-light small" style="position: sticky; top: 0; z-index: 2; background: #f8f9fa;">
							<tr>
								<th style="width: 40px;" class="text-center">#</th>
								<th style="min-width: 120px;">CIF ID</th>
								<th style="min-width: 130px;">First Name</th>
								<th style="min-width: 120px;">Middle Name</th>
								<th style="min-width: 130px;">Last Name</th>
								<th style="min-width: 110px;">Date of Birth</th>
								<th style="min-width: 110px;">Mobile</th>
								<th style="min-width: 120px;">PAN</th>
								<th style="width: 70px;" class="text-center">Sol ID</th>
								<th style="min-width: 110px;">Creation Date</th>
								<th style="min-width: 180px;">Active Accounts</th>
								<th style="min-width: 90px;">Pin Code</th>
								<th style="min-width: 180px;">Address</th>
							</tr>
						</thead>
						<tbody>
							${data.map((row, idx) => {
								let row_style = "";
								let row_class = "";
								if (row.primary) {
									row_class = "table-success";
									row_style = "border-left: 5px solid #16a34a; background-color: #f0fdf4;";
								} else if (row.merge) {
									row_style = "border-left: 5px solid #9333ea; background-color: #faf5ff;";
								} else if (row.re_kyc) {
									row_style = "border-left: 5px solid #d97706; background-color: #fffbeb;";
								}

								return `
									<tr class="${row_class}" style="${row_style}">
										<td class="text-center text-muted small">${idx + 1}</td>
										<td>
											<span class="font-weight-bold">${escape_html(row.cif_id)}</span>
											${row.primary ? '<span class="badge badge-success ml-1">PRIMARY</span>' : ''}
											${row.merge ? '<span class="badge ml-1" style="background:#9333ea; color:white;">MERGE</span>' : ''}
											${row.re_kyc ? '<span class="badge badge-warning ml-1">RE-KYC</span>' : ''}
										</td>
										<td>${escape_html(row.first_name || '-')}</td>
										<td>${escape_html(row.middle_name || '-')}</td>
										<td>${escape_html(row.last_name || '-')}</td>
										<td>${format_date(row.date_of_birth)}</td>
										<td>${escape_html(row.mobile || '-')}</td>
										<td><span class="badge badge-light border text-monospace font-weight-bold">${escape_html(row.pan || '-')}</span></td>
										<td><span class="badge badge-light border">${escape_html(row.sol_id || '-')}</span></td>
										<td class="text-muted small">${format_date(row.cif_creation)}</td>
										<td>
											${row.active_accounts_count > 0 
												? `<span class="badge badge-success mb-1">${row.active_accounts_count} Active</span><div class="small font-weight-bold text-dark font-monospace" style="word-break: break-all;">${escape_html(row.active_account_numbers || '-')}</div>` 
												: '<span class="badge badge-secondary">0 Active</span><div class="small text-muted font-italic">No active account</div>'}
										</td>
										<td><span class="badge badge-light border font-weight-bold">${escape_html(row.pin_code || '-')}</span></td>
										<td class="small text-muted">${escape_html([row.address_line_1, row.address_line_2, row.address_line_3].filter(Boolean).join(', ') || '-')}</td>
									</tr>
								`;
							}).join('')}
						</tbody>
					</table>
				</div>
			</div>

			<!-- Minimal Checklist Pill Bar -->
			<div class="d-flex justify-content-between align-items-center flex-wrap pt-2 mt-2 border-top text-muted" style="font-size: 11.5px;">
				<div class="d-flex align-items-center flex-wrap gap-2">
					<span class="text-uppercase font-weight-bold tracking-wider text-secondary mr-1" style="font-size: 10px; letter-spacing: 0.5px;">Checklist:</span>

					<!-- Primary Pill -->
					<span class="d-inline-flex align-items-center px-2 py-0.5 rounded-pill border ${primary_count === 1 ? 'border-success text-success bg-white font-weight-bold' : 'border-light text-muted bg-light'}" style="transition: all 0.2s;">
						<i class="fa ${primary_count === 1 ? 'fa-check text-success' : 'fa-circle-thin text-muted'} mr-1" style="font-size: 10px;"></i>
						1 Primary
						<span class="badge ${primary_count === 1 ? 'badge-success text-white' : 'badge-light text-muted border'} ml-1 px-1.5 py-0.2" style="font-size: 9.5px;">${primary_count}/1</span>
					</span>

					<!-- Merge Pill -->
					<span class="d-inline-flex align-items-center px-2 py-0.5 rounded-pill border ${merge_count > 0 ? 'bg-white font-weight-bold' : 'border-light text-muted bg-light'}" style="${merge_count > 0 ? 'border-color: #9333ea; color: #9333ea;' : ''}; transition: all 0.2s;">
						<i class="fa ${merge_count > 0 ? 'fa-check' : 'fa-circle-thin text-muted'} mr-1" style="font-size: 10px;"></i>
						Merge
						<span class="badge ml-1 px-1.5 py-0.2" style="${merge_count > 0 ? 'background-color: #9333ea; color: white;' : 'background-color: #e9ecef; color: #6c757d;'}; font-size: 9.5px;">${merge_count}</span>
					</span>

					<!-- Re-KYC Pill -->
					<span class="d-inline-flex align-items-center px-2 py-0.5 rounded-pill border ${rekyc_count > 0 ? 'border-warning text-dark bg-white font-weight-bold' : 'border-light text-muted bg-light'}" style="transition: all 0.2s;">
						<i class="fa ${rekyc_count > 0 ? 'fa-check text-warning' : 'fa-circle-thin text-muted'} mr-1" style="font-size: 10px;"></i>
						Re-KYC
						<span class="badge ${rekyc_count > 0 ? 'badge-warning text-dark' : 'badge-light text-muted border'} ml-1 px-1.5 py-0.2" style="font-size: 9.5px;">${rekyc_count}</span>
					</span>
				</div>
				<div class="text-muted" style="font-size: 11px;">
					<i class="fa fa-info-circle mr-1"></i>Merge and Re-KYC are mutually exclusive
				</div>
			</div>
		</div>`;

		wrapper.html(widget_html);

		// Event: Hover highlights across table
		wrapper.find('.cif-token-badge').hover(
			function() {
				let tk = $(this).attr('data-token');
				if (!tk) return;
				wrapper.find(`.cif-token-badge[data-token="${tk}"]`).css({
					"transform": "scale(1.08)",
					"box-shadow": "0 2px 6px rgba(0,0,0,0.25)"
				});
			},
			function() {
				let tk = $(this).attr('data-token');
				if (!tk) return;
				wrapper.find(`.cif-token-badge[data-token="${tk}"]`).css({
					"transform": "",
					"box-shadow": ""
				});
			}
		);

		// Event: Primary Checkbox (Strictly single selection)
		wrapper.find('.cif-primary-chk').on('change', function() {
			let idx = $(this).data('idx');
			let is_checked = $(this).is(':checked');
			(frm.doc.cif_details || []).forEach((r, i) => {
				let val = (i === idx && is_checked) ? 1 : 0;
				frappe.model.set_value(r.doctype, r.name, "primary", val);
				if (val) {
					frappe.model.set_value(r.doctype, r.name, "merge", 0);
					frappe.model.set_value(r.doctype, r.name, "re_kyc", 0);
				}
			});
			frm.dirty();
			frm.refresh();
		});

		// Event: Select All Merge Checkbox (Excludes Primary row)
		wrapper.find('.cif-merge-select-all').on('change', function() {
			let is_checked = $(this).is(':checked');
			(frm.doc.cif_details || []).forEach(r => {
				if (!r.primary) {
					frappe.model.set_value(r.doctype, r.name, "merge", is_checked ? 1 : 0);
					if (is_checked) {
						frappe.model.set_value(r.doctype, r.name, "re_kyc", 0);
					}
				}
			});
			frm.dirty();
			frm.refresh();
		});

		// Event: Merge Checkbox (Mutually exclusive with Re-KYC & Primary)
		wrapper.find('.cif-merge-chk').on('change', function() {
			let idx = $(this).data('idx');
			let is_checked = $(this).is(':checked');
			let row = frm.doc.cif_details[idx];
			if (row) {
				frappe.model.set_value(row.doctype, row.name, "merge", is_checked ? 1 : 0);
				if (is_checked) {
					frappe.model.set_value(row.doctype, row.name, "re_kyc", 0);
					frappe.model.set_value(row.doctype, row.name, "primary", 0);
				}
				frm.dirty();
				frm.refresh();
			}
		});

		// Event: Re-KYC Checkbox (Mutually exclusive with Merge & Primary)
		wrapper.find('.cif-rekyc-chk').on('change', function() {
			let idx = $(this).data('idx');
			let is_checked = $(this).is(':checked');
			let row = frm.doc.cif_details[idx];
			if (row) {
				frappe.model.set_value(row.doctype, row.name, "re_kyc", is_checked ? 1 : 0);
				if (is_checked) {
					frappe.model.set_value(row.doctype, row.name, "merge", 0);
					frappe.model.set_value(row.doctype, row.name, "primary", 0);
				}
				frm.dirty();
				frm.refresh();
			}
		});
	}
});



