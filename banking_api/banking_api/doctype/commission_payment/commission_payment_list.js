frappe.listview_settings["Commission Payment"] = {
    refresh(listview) {
        if (listview.page.__commission_payment_actions_added) return;
        listview.page.__commission_payment_actions_added = true;

        const action_label = __("Actions");

        listview.page.add_inner_button(
            __("Pay Commission"),
            () => {
                const selected = listview.get_checked_items();

                if (!selected.length) {
                    frappe.msgprint(
                        __("Please select at least one Commission Payment record.")
                    );
                    return;
                }

                const paymentNames = selected
                    .map((row) => row.name)
                    .filter(Boolean);

                if (!paymentNames.length) {
                    frappe.msgprint(
                        __("Unable to identify selected Commission Payment records.")
                    );
                    return;
                }

                frappe.confirm(
                    __(
                        "Initiate Finacle payment for {0} selected Commission Payment record(s)?",
                        [paymentNames.length]
                    ),
                    () => {
                        frappe.call({
                            method: "banking_api.banking_api.doctype.commission_payment.commission_payment.run_bulk_commission_payment",
                            args: {
                                payment_names: paymentNames
                            },
                            freeze: true,
                            freeze_message: __(
                                "Processing selected Commission Payments..."
                            ),
                            callback(r) {
                                const data = r.message || {};

                                frappe.msgprint({
                                    title: __("Bulk Commission Payment Result"),
                                    indicator:
                                        data.status === "success"
                                            ? "green"
                                            : "orange",
                                    message: `
                                        <div>
                                            <p><b>Processed:</b> ${data.processed_count || 0}</p>
                                            <p><b>Success:</b> ${data.success_count || 0}</p>
                                            <p><b>Failed:</b> ${data.failed_count || 0}</p>
                                            <p><b>Skipped:</b> ${data.skipped_count || 0}</p>
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
    }
};