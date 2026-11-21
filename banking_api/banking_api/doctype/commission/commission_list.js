frappe.dom.set_style(`
    /* Commission status buttons only */
    .commission-status-buttons {
        display: inline-flex !important;
        align-items: center;
        gap: 5px;
        margin-right: 8px;
        vertical-align: middle;
        white-space: nowrap;
        width: max-content;
        flex-shrink: 0;
        overflow: visible;
    }

    .commission-status-buttons .commission-status-btn {
        display: inline-flex;
        align-items: center;
        cursor: pointer;
        white-space: nowrap;
        flex-shrink: 0;
    }

    .commission-status-buttons .commission-status-pill {
        display: inline-block;
        padding: 3px 8px !important;
        font-size: 12px !important;
        line-height: 18px !important;
        font-weight: 500;
        white-space: nowrap;
        border-radius: 10px;
    }

    .commission-status-buttons .commission-status-pill.blue {
        background-color: #e7f0fe !important;
        color: #1f6feb !important;
    }

    .commission-status-buttons .commission-status-pill.green {
        background-color: #e6f6ec !important;
        color: #1a7f37 !important;
    }

    .commission-status-buttons .commission-status-pill.orange {
        background-color: #fff3e0 !important;
        color: #b45309 !important;
    }

    .commission-status-buttons .commission-status-btn:hover
    .commission-status-pill {
        opacity: 0.85;
    }
`);

frappe.listview_settings["Commission"] = {
    hide_name_column: true,
    hide_name_filter: true,

    onload(listview) {
        // Keep any existing onload behavior here if needed.
    },

    refresh(listview) {
        const page = listview.page;

        /*
         * PART 1: EXISTING COMMISSION ACTION BUTTONS
         *
         * Register the actions once per page.
         * Do not remove or replace existing page action groups.
         */

        if (!page.__commission_actions_added) {
            page.__commission_actions_added = true;

            const action_label = __("Actions");

            // 1. Fetch Commission Data
            page.add_inner_button(
                __("Fetch Commission Data"),
                () => {
                    const today = frappe.datetime.get_today();
                    const default_start = frappe.datetime.month_start();
                    const default_end = frappe.datetime.add_days(today, -1);

                    const d = new frappe.ui.Dialog({
                        title: __("Fetch Commission Data from DB"),
                        fields: [
                            {
                                label: __("From Date"),
                                fieldname: "from_date",
                                fieldtype: "Date",
                                default: default_start,
                                reqd: 1
                            },
                            {
                                label: __("To Date"),
                                fieldname: "to_date",
                                fieldtype: "Date",
                                default: default_end,
                                reqd: 1
                            }
                        ],
                        primary_action_label: __("Fetch"),
                        primary_action(values) {
                            const max_date = frappe.datetime.add_days(frappe.datetime.get_today(), -1);
                            if (values.to_date > max_date) {
                                frappe.msgprint(__("To Date cannot be today or a future date. Maximum allowed date is {0} (T-1).", [max_date]));
                                return;
                            }
                            if (values.from_date > values.to_date) {
                                frappe.msgprint(__("From Date cannot be after To Date."));
                                return;
                            }
                            d.hide();

                            frappe.call({
                                method: "banking_api.banking_api.doctype.commission.commission.fetch_and_create_commission",
                                args: {
                                    from_date: values.from_date,
                                    to_date: values.to_date
                                },
                                freeze: true,
                                freeze_message: __(
                                    "Fetching commission data ({0} to {1})...",
                                    [values.from_date, values.to_date]
                                ),
                                callback(r) {
                                    if (!r.message) {
                                        return;
                                    }

                                    const data = r.message;

                                    frappe.msgprint({
                                        title: __(
                                            "Commission Fetch Result"
                                        ),
                                        indicator: data.error_count
                                            ? "orange"
                                            : "green",

                                        message: `
                                            <div>
                                                <p><b>Status:</b> ${frappe.utils.escape_html(
                                            String(data.status || "Completed")
                                        )}</p>

                                                <p><b>Query 1 Rows:</b> ${cint(
                                            data.query_1_fetched || data.query_1_count || 0
                                        )}</p>

                                                <p><b>Query 2 Rows:</b> ${cint(
                                            data.query_2_fetched || data.query_2_count || 0
                                        )}</p>

                                                <p><b>Inserted Docs:</b> ${cint(
                                            data.inserted_count || 0
                                        )}</p>

                                                <p><b>Updated Docs:</b> ${cint(
                                            data.updated_count || 0
                                        )}</p>

                                                <p><b>Total Processed:</b> ${cint(
                                            data.total_processed || 0
                                        )}</p>

                                                <p><b>Errors:</b> ${cint(
                                            data.error_count || 0
                                        )}</p>
                                            </div>
                                        `
                                    });

                                    listview.refresh();
                                }
                            });
                        }
                    });
                    d.show();
                },
                action_label
            );

            // 2. Calculate Commission for Selected Records
            page.add_inner_button(
                __("Calculate Commission (Selected Records)"),
                () => {
                    const selected = listview.get_checked_items();

                    if (!selected.length) {
                        frappe.msgprint(
                            __("Please select at least one Commission record.")
                        );
                        return;
                    }

                    const commission_names = selected.map(
                        row => row.name
                    );

                    frappe.confirm(
                        __(
                            `Calculate commission for ${commission_names.length} selected record(s)?`
                        ),
                        () => {
                            frappe.call({
                                method: "banking_api.banking_api.doctype.commission.commission.calculate_commission_for_selected",

                                args: {
                                    commission_names: commission_names
                                },

                                freeze: true,

                                freeze_message: __(
                                    "Calculating commission for selected records..."
                                ),

                                callback(r) {
                                    if (!r.message) {
                                        return;
                                    }

                                    const data = r.message;

                                    frappe.msgprint({
                                        title: __(
                                            "Selected Commission Calculation Result"
                                        ),

                                        indicator: data.error_count
                                            ? "orange"
                                            : "green",

                                        message: `
                                            <div>
                                                <p><b>Status:</b> ${frappe.utils.escape_html(
                                            String(data.status || "Completed")
                                        )}</p>

                                                <p><b>Total Selected:</b> ${cint(
                                            data.total_processed || 0
                                        )}</p>

                                                <p><b>Successful:</b> ${cint(
                                            data.success_count || 0
                                        )}</p>

                                                <p><b>Errors:</b> ${cint(
                                            data.error_count || 0
                                        )}</p>
                                            </div>
                                        `
                                    });

                                    listview.refresh();
                                }
                            });
                        }
                    );
                },
                action_label
            );

            // 3. Calculate Commission for All Records
            page.add_inner_button(
                __("Calculate Commission (All Records)"),
                () => {
                    frappe.confirm(
                        __(
                            "This will calculate commission on ALL Commission documents. This may take some time. Do you want to continue?"
                        ),
                        () => {
                            frappe.call({
                                method: "banking_api.banking_api.doctype.commission.commission.calculate_commission_for_all",

                                freeze: true,

                                freeze_message: __(
                                    "Calculating commission on all records..."
                                ),

                                callback(r) {
                                    if (!r.message) {
                                        return;
                                    }

                                    const data = r.message;

                                    frappe.msgprint({
                                        title: __(
                                            "Commission Calculation Result"
                                        ),

                                        indicator: data.error_count
                                            ? "orange"
                                            : "green",

                                        message: `
                                            <div>
                                                <p><b>Status:</b> ${frappe.utils.escape_html(
                                            String(data.status || "Completed")
                                        )}</p>

                                                <p><b>Total Processed:</b> ${cint(
                                            data.total_processed || 0
                                        )}</p>

                                                <p><b>Successful:</b> ${cint(
                                            data.success_count || 0
                                        )}</p>

                                                <p><b>Errors:</b> ${cint(
                                            data.error_count || 0
                                        )}</p>
                                            </div>
                                        `
                                    });

                                    listview.refresh();
                                }
                            });
                        }
                    );
                },
                action_label
            );

            // 4. Commission Dashboard
            page.add_inner_button(
                __("Commission Dashboard (View Only)"),
                () => {
                    window.open("/commission", "_blank");
                },
                action_label
            );

            // 5. Commission Reports
            page.add_inner_button(
                __("Commission Reports"),
                () => {
                    window.open("/commission-report", "_blank");
                },
                action_label
            );

            // 6. Clear Data (Testing/Developer)
            if (frappe.user_roles.includes("System Manager")) {
                page.add_inner_button(
                    __("Clear Commission / Payment Data"),
                    () => {
                        const d = new frappe.ui.Dialog({
                            title: __("Clear Data (Testing Mode)"),
                            fields: [
                                {
                                    fieldtype: "HTML",
                                    fieldname: "warning_html",
                                    options: `<div class="alert alert-danger" style="margin-bottom: 12px; font-size: 13px;">
                                        <b>Warning:</b> Truncating tables is irreversible. Selected tables will be permanently cleared.
                                    </div>`
                                },
                                {
                                    label: __("Commission Records (Includes Commission Items)"),
                                    fieldname: "clear_commission",
                                    fieldtype: "Check",
                                    default: 1
                                },
                                {
                                    label: __("Commission Payment Records"),
                                    fieldname: "clear_payments",
                                    fieldtype: "Check",
                                    default: 1
                                }
                            ],
                            primary_action_label: __("Truncate Selected"),
                            primary_action(values) {
                                if (!values.clear_commission && !values.clear_payments) {
                                    frappe.msgprint(__("Please select at least one option to clear."));
                                    return;
                                }

                                frappe.confirm(
                                    __("Are you sure you want to permanently clear the selected data?"),
                                    () => {
                                        d.hide();
                                        frappe.call({
                                            method: "banking_api.banking_api.doctype.commission.commission.truncate_commission_and_payments",
                                            args: {
                                                clear_commission: values.clear_commission ? 1 : 0,
                                                clear_payments: values.clear_payments ? 1 : 0
                                            },
                                            freeze: true,
                                            freeze_message: __("Clearing selected data..."),
                                            callback(r) {
                                                if (r.message && r.message.status === "success") {
                                                    frappe.show_alert({
                                                        message: r.message.message,
                                                        indicator: "green"
                                                    });
                                                    listview.refresh();
                                                }
                                            }
                                        });
                                    }
                                );
                            }
                        });
                        d.show();
                    },
                    action_label
                );
            }
        }

        /*
         * PART 2: COMMISSION STATUS COUNTS
         *
         * This code only manages .commission-status-buttons.
         * It does not remove or modify existing action buttons.
         */

        frappe.call({
            method: "banking_api.banking_api.doctype.commission.commission.get_commission_status_counts",

            callback(r) {
                if (!r.message) {
                    return;
                }

                const data = r.message;

                const total_records = cint(
                    data.total_records || 0
                );

                const calculated_records = cint(
                    data.calculated_records || 0
                );

                const not_calculated_records = cint(
                    data.not_calculated_records || 0
                );

                const get_count_html = (label, count, color) => `
                    <span class="indicator-pill no-indicator-dot whitespace-nowrap ${color} commission-status-pill">
                        <span>${label}: ${count}</span>
                    </span>
                `;

                /*
                 * Remove only our own previous status buttons.
                 * Never remove .custom-btn-group or .page-actions.
                 */
                const $page_head = $(page.wrapper)
                    .find(".page-head")
                    .add($(".page-head").filter(function () {
                        return $(this).closest(".page-container").length > 0;
                    }))
                    .first();

                const $global_page_head = $(".page-head").first();

                const $head = $global_page_head.length
                    ? $global_page_head
                    : $page_head;

                if (!$head.length) {
                    console.warn(
                        "Commission: Page header not found."
                    );
                    return;
                }

                $head.find(".commission-status-buttons").remove();

                /*
                 * Find the actual List View dropdown.
                 * Do not assume the first custom button group
                 * is the List View group.
                 */
                const $list_view_button = $head
                    .find(".custom-btn-group")
                    .filter(function () {
                        return $(this)
                            .find(".custom-btn-group-label")
                            .filter(function () {
                                return $(this).text().trim() === "List View";
                            }).length > 0;
                    })
                    .first();

                if (!$list_view_button.length) {
                    console.warn(
                        "Commission: List View dropdown not found."
                    );
                    return;
                }

                const buttons_html = `
                    <div class="commission-status-buttons">

                        <span class="commission-status-btn"
                              data-status="total"
                              title="${__("Show all Commission records")}">
                            ${get_count_html(
                    __("Total"),
                    total_records,
                    "blue"
                )}
                        </span>

                        <span class="commission-status-btn"
                              data-status="calculated"
                              title="${__("Show calculated Commission records")}">
                            ${get_count_html(
                    __("Calculated"),
                    calculated_records,
                    "green"
                )}
                        </span>

                        <span class="commission-status-btn"
                              data-status="not_calculated"
                              title="${__("Show Commission records that are not calculated")}">
                            ${get_count_html(
                    __("Not Calculated"),
                    not_calculated_records,
                    "orange"
                )}
                        </span>

                    </div>
                `;

                const $buttons = $(buttons_html);

                /*
                 * Insert immediately before List View.
                 * Existing Actions and Group Actions are untouched.
                 */
                $list_view_button.before($buttons);

                // Bind click handlers only inside this container.
                $buttons.on(
                    "click",
                    ".commission-status-btn",
                    function () {
                        const status = $(this).attr("data-status");

                        let filters = [];

                        if (status === "calculated") {
                            filters = [
                                [
                                    "Commission",
                                    "netpay",
                                    "is",
                                    "set"
                                ]
                            ];
                        } else if (status === "not_calculated") {
                            filters = [
                                [
                                    "Commission",
                                    "netpay",
                                    "is",
                                    "not set"
                                ]
                            ];
                        }

                        // Total clears the filters.
                        listview.filter_area.clear();

                        if (filters.length) {
                            listview.filter_area.add(filters);
                        }

                        listview.refresh();
                    }
                );
            },

            error(r) {
                console.error(
                    "Failed to fetch Commission status counts:",
                    r
                );
            }
        });
    }
};