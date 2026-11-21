frappe.ui.form.on("Commission Payment", {
    refresh(frm) {
        frm.trigger("render_commission_records_widget");

        if (frm.is_new()) return;
        if (frm.doc.docstatus === 2) return;
        if (frm.doc.payment_status === "Paid") return;

        frm.add_custom_button(__("Pay Now"), () => {
            // if (!frm.doc.agent_operative_account) {
            //     frappe.msgprint(__("Agent Operative Account is required."));
            //     return;
            // }
            if (!frm.doc.agent_saving_account) {
                frappe.msgprint(__("Agent Saving Account is required."));
                return;
            }

            if (!frm.doc.final_netpay || flt(frm.doc.final_netpay) <= 0) {
                frappe.msgprint(__("Final Net Pay must be greater than zero."));
                return;
            }

            const amount = format_currency(frm.doc.final_netpay);
            // const account = frm.doc.agent_operative_account;
            const account = frm.doc.agent_saving_account;

            frappe.confirm(
                __(
                    // "Initiate commission payment of {0} to operative account {1}?",
                    "Initiate commission payment of {0} to saving account {1}?",
                    [amount, account]
                ),
                () => {
                    frappe.call({
                        method: "banking_api.banking_api.doctype.commission_payment.commission_payment.pay_now_commission_payment",
                        args: {
                            payment_name: frm.doc.name
                        },
                        freeze: true,
                        freeze_message: __("Initiating Finacle commission payment..."),
                        callback(r) {
                            const data = r.message || {};

                            frappe.msgprint({
                                title: __("Commission Payment Result"),
                                message: data.message || __("Process completed."),
                                indicator:
                                    data.status === "success"
                                        ? "green"
                                        : (
                                            data.status === "warning"
                                                ? "orange"
                                                : "red"
                                        )
                            });

                            frm.reload_doc();
                        }
                    });
                }
            );
        }).addClass("btn-primary");
    },

    agent_code(frm) {
        frm.trigger("render_commission_records_widget");
    },

    render_commission_records_widget(frm) {
        if (!frm.fields_dict.commission_records_html) return;
        const wrapper = $(frm.fields_dict.commission_records_html.wrapper);
        wrapper.empty();

        if (!frm.doc.agent_code) {
            wrapper.html(`
                <div class="p-3 text-center border rounded bg-light text-muted small">
                    <i class="fa fa-info-circle mr-1 text-info"></i>
                    ${__("Please select an Agent Code to view linked commission records.")}
                </div>
            `);
            return;
        }

        wrapper.html(`
            <div class="p-4 text-center border rounded bg-light text-muted small">
                <i class="fa fa-spinner fa-spin mr-2 text-primary"></i>
                ${__("Loading linked commission records for Agent {0}...", [frappe.utils.escape_html(frm.doc.agent_code)])}
            </div>
        `);

        frappe.call({
            method: "banking_api.banking_api.doctype.commission_payment.commission_payment.get_linked_commission_records",
            args: {
                payment_name: frm.is_new() ? null : frm.doc.name,
                agent_code: frm.doc.agent_code,
                creation: frm.doc.creation
            },
            callback: function (r) {
                const data = r.message || { records: [], count: 0, totals: {} };
                frm.events._render_commission_table(frm, wrapper, data);
            }
        });
    },

    _render_commission_table(frm, wrapper, data) {
        const escape_html = (str) => frappe.utils.escape_html(str || "");
        const fmt_money = (val) => {
            if (val === null || val === undefined || val === "") return "-";
            const num = flt(val);
            return isNaN(num) ? escape_html(String(val)) : format_currency(num);
        };
        const fmt_val = (val) => {
            if (val === null || val === undefined || val === "") return "-";
            return escape_html(String(val));
        };

        const records = data.records || [];
        const count = data.count || records.length;
        const totals = data.totals || {};
        const period = data.period_display || "Same Month";
        const agent = data.agent_code || frm.doc.agent_code || "-";

        if (!records.length) {
            wrapper.html(`
                <div class="p-4 text-center border rounded bg-light text-muted small">
                    <i class="fa fa-info-circle mr-1" style="color: #b45309;"></i>
                    ${__("No commission records found for Agent <b>{0}</b> created in <b>{1}</b>.", [
                escape_html(agent),
                escape_html(period)
            ])}
                </div>
            `);
            return;
        }

        const stats_html = `
            <div class="row no-gutters mb-3" style="gap: 10px;">
                <div class="col p-2 rounded border bg-light d-flex flex-column" style="min-width: 110px;">
                    <span class="text-muted" style="font-size: 11px; text-transform: uppercase; font-weight: 600;">Total Records</span>
                    <span class="font-weight-bold text-dark" style="font-size: 15px;">${count}</span>
                </div>
                <div class="col p-2 rounded border bg-light d-flex flex-column" style="min-width: 110px;">
                    <span class="text-muted" style="font-size: 11px; text-transform: uppercase; font-weight: 600;">Total Deposit</span>
                    <span class="font-weight-bold text-secondary" style="font-size: 15px;">${format_currency(totals.deposit_amount || 0)}</span>
                </div>
                <div class="col p-2 rounded border bg-light d-flex flex-column" style="min-width: 110px;">
                    <span class="text-muted" style="font-size: 11px; text-transform: uppercase; font-weight: 600;">Gross Commission</span>
                    <span class="font-weight-bold text-primary" style="font-size: 15px;">${format_currency(totals.gross_commission || 0)}</span>
                </div>
                <div class="col p-2 rounded border bg-light d-flex flex-column" style="min-width: 110px;">
                    <span class="text-muted" style="font-size: 11px; text-transform: uppercase; font-weight: 600;">TDS</span>
                    <span class="font-weight-bold text-danger" style="font-size: 15px;">${format_currency(totals.tds || 0)}</span>
                </div>
                <div class="col p-2 rounded border bg-light d-flex flex-column" style="min-width: 110px;">
                    <span class="text-muted" style="font-size: 11px; text-transform: uppercase; font-weight: 600;">Security Deposit</span>
                    <span class="font-weight-bold" style="font-size: 15px; color: #b45309;">${format_currency(totals.security_deposit || 0)}</span>
                </div>
                <div class="col p-2 rounded border bg-light d-flex flex-column" style="min-width: 110px;">
                    <span class="text-muted" style="font-size: 11px; text-transform: uppercase; font-weight: 600;">Net Pay</span>
                    <span class="font-weight-bold text-info" style="font-size: 15px;">${format_currency(totals.netpay || 0)}</span>
                </div>
                <div class="col p-2 rounded border bg-light d-flex flex-column" style="min-width: 110px;">
                    <span class="text-muted" style="font-size: 11px; text-transform: uppercase; font-weight: 600;">Final Net Pay</span>
                    <span class="font-weight-bold text-success" style="font-size: 15px;">${format_currency(totals.final_netpay || 0)}</span>
                </div>
                
            </div>
        `;

        const rows_html = records.map((row, idx) => {
            const comm_id = escape_html(row.name);
            const scheme_text = (row.scheme_code || row.scheme_description)
                ? `${escape_html(row.scheme_code || "")} - ${escape_html(row.scheme_description || "")}`
                : "-";
            const sol_text = (row.sol_id || row.sol_description)
                ? `${escape_html(row.sol_id || "")} - ${escape_html(row.sol_description || "")}`
                : "-";

            return `
                <tr class="comm-data-row" data-idx="${idx}" data-name="${comm_id}" style="cursor: pointer;" title="${__('Click to open Commission {0}', [comm_id])}">
                    <td class="text-center text-muted small" style="width: 40px;">${idx + 1}</td>
                    <td style="white-space: nowrap;"><span class="font-weight-bold">${fmt_val(row.customer_account_number)}</span></td>
                    <td>${fmt_val(row.customer_account_name)}</td>
                    <td style="white-space: nowrap;"><span class="badge badge-light border">${scheme_text}</span></td>
                    <td class="text-right" style="white-space: nowrap;">${fmt_money(row.deposit_amount)}</td>
                    <td class="text-right" style="white-space: nowrap;">${fmt_money(row.eligible_amount)}</td>
                    <td class="text-right font-weight-bold text-primary" style="white-space: nowrap;">${fmt_money(row.commission_amount)}</td>
                    <td class="text-right text-danger" style="white-space: nowrap;">${fmt_money(row.tds)}</td>
                    <td class="text-right font-weight-bold" style="white-space: nowrap; color: #b45309;">${fmt_money(row.security_deposit)}</td>
                    <td class="text-right font-weight-bold text-info" style="white-space: nowrap;">${fmt_money(row.netpay)}</td>
                    <td class="text-right font-weight-bold text-success" style="white-space: nowrap;">${fmt_money(row.final_net_pay)}</td>
                    <td style="white-space: nowrap;"><span class="text-muted small">${sol_text}</span></td>
                    <td class="text-muted small" style="white-space: nowrap;">${fmt_val(row.creation_formatted || row.creation)}</td>
                </tr>
            `;
        }).join("");

        const container_html = `
            <div class="commission-records-widget-wrapper  rounded p-3 bg-white mb-3">
                <div class="d-flex justify-content-between align-items-center mb-2 pb-2 border-bottom flex-wrap" style="gap: 8px;">
                    <div>
                        <h6 class="m-0 font-weight-bold text-dark">
                            <i class="fa fa-table text-primary mr-1"></i> ${__("Commission Records")}
                        </h6>
                        <small class="text-muted">
                            ${__("Created in <b>{0}</b> for Agent <b>{1}</b>", [escape_html(period), escape_html(agent)])}
                        </small>
                    </div>
                    <div class="d-flex align-items-center flex-wrap" style="gap: 8px;">
                        <span class="indicator-pill no-indicator-dot whitespace-nowrap blue" style="padding: 6px 14px; font-size: 12px; font-weight: 500;"><span>${count} Records</span></span>
                        <span class="indicator-pill no-indicator-dot whitespace-nowrap purple" style="padding: 6px 14px; font-size: 12px; font-weight: 500;"><span>${escape_html(period)}</span></span>
                        <a href="/app/commission?agent_code=${encodeURIComponent(agent)}" target="_blank" class="btn btn-xs btn-default" title="${__('Open in Commission List View')}">
                            <i class="fa fa-external-link text-secondary mr-1"></i> ${__("List View")}
                        </a>
                        <button type="button" class="btn btn-xs btn-default comm-btn-refresh" title="${__('Reload records')}">
                            <i class="fa fa-refresh text-secondary mr-1"></i> ${__("Refresh")}
                        </button>
                    </div>
                </div>

                ${stats_html}

                <div class="d-flex justify-content-between align-items-start mb-3 flex-wrap" style="gap: 12px;">
                    <div style="flex: 1 1 450px; max-width: 600px;">
                        <div class="d-flex align-items-center" style="gap: 10px;">
                            <div style="position: relative; flex: 1;">
                                <i class="fa fa-search text-muted" style="position: absolute; left: 10px; top: 50%; transform: translateY(-50%); pointer-events: none; font-size: 12px; z-index: 2;"></i>
                                <input type="text" class="form-control form-control-sm comm-search-input" placeholder="${__('Search account, customer name, scheme, branch, SOL...')}" style="padding-left: 30px; font-size: 12px; height: 30px; border-radius: 6px;">
                            </div>
                            <span class="text-muted small comm-record-count" style="white-space: nowrap; flex-shrink: 0; font-weight: 500;">Showing ${count} of ${count} records</span>
                        </div>
                        <div class="text-muted mt-1" style="font-size: 11px; padding-left: 2px;">
                            ${__("Filter commission records by Customer Account Number, Name, Scheme Code/Description, or Branch.")}
                        </div>
                    </div>
                    <div class="text-muted small pt-1" style="white-space: nowrap;">
                        <i class="fa fa-mouse-pointer text-primary mr-1"></i> ${__("Click any row to open commission record")}
                    </div>
                </div>

                <div class="table-responsive border rounded" style="max-height: 480px; overflow-y: auto;">
                    <table class="table table-sm table-hover table-bordered m-0" style="vertical-align: middle; font-size: 12px;">
                        <thead class="thead-light" style="position: sticky; top: 0; background: #f8fafc; z-index: 2; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
                            <tr>
                                <th style="width: 40px;" class="text-center">#</th>
                                <th style="min-width: 140px;">${__("Customer Account")}</th>
                                <th style="min-width: 160px;">${__("Customer Name")}</th>
                                <th style="min-width: 140px;">${__("Scheme")}</th>
                                <th style="min-width: 90px;" class="text-right">${__("Deposit")}</th>
                                <th style="min-width: 90px;" class="text-right">${__("Eligible Amt")}</th>
                                <th style="min-width: 100px;" class="text-right text-primary">${__("Gross Comm.")}</th>
                                <th style="min-width: 80px;" class="text-right text-danger">${__("TDS")}</th>
                                <th style="min-width: 90px; color: #b45309;" class="text-right">${__("Sec. Dep.")}</th>
                                <th style="min-width: 90px;" class="text-right text-info">${__("Net Pay")}</th>
                                <th style="min-width: 95px;" class="text-right text-success">${__("Final Net Pay")}</th>
                                <th style="min-width: 130px;">${__("Branch / SOL")}</th>
                                <th style="min-width: 120px;">${__("Created On")}</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rows_html}
                        </tbody>
                    </table>
                </div>
            </div>
        `;

        wrapper.html(container_html);

        // Click row to open Commission record
        wrapper.find("tbody tr.comm-data-row").on("click", function (e) {
            if ($(e.target).closest("a, button, input").length) return;
            const comm_name = $(this).attr("data-name");
            if (!comm_name) return;
            if (e.ctrlKey || e.metaKey) {
                window.open(`/app/commission/${encodeURIComponent(comm_name)}`, "_blank");
            } else {
                frappe.set_route("Form", "Commission", comm_name);
            }
        });

        // Real-time instant search filter
        wrapper.find(".comm-search-input").on("input", function () {
            const query = $(this).val().toLowerCase().trim();
            let visible_count = 0;
            wrapper.find("tbody tr.comm-data-row").each(function () {
                const text = $(this).text().toLowerCase();
                const commName = ($(this).attr("data-name") || "").toLowerCase();
                const matches = !query || text.indexOf(query) !== -1 || commName.indexOf(query) !== -1;
                $(this).toggle(matches);
                if (matches) visible_count++;
            });
            wrapper.find(".comm-record-count").text(
                `Showing ${visible_count} of ${count} records`
            );
        });

        // Refresh button click
        wrapper.find(".comm-btn-refresh").on("click", function () {
            frm.trigger("render_commission_records_widget");
        });
    }
});