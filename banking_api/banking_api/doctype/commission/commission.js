// // Copyright (c) 2026, Talib Sheikh and contributors
// // For license information, please see license.txt


// frappe.ui.form.on("Commission", {
//     refresh(frm) {
//         if (frm.is_new()) return;

//         frm.add_custom_button(__("Calculate Commission"), function () {
//             if (!frm.doc.scheme_code) {
//                 frappe.msgprint(__("Scheme Code is required."));
//                 return;
//             }

//             if (!frm.doc.collection) {
//                 frappe.msgprint(__("Collection is required."));
//                 return;
//             }

//             frappe.call({
//                 method: "banking_api.banking_api.doctype.commission.commission.calculate_commission_amount",
//                 args: {
//                     docname: frm.doc.name
//                 },
//                 freeze: true,
//                 freeze_message: __("Calculating commission amount..."),
//                 callback: function (r) {
//                     if (r.message) {
//                         frappe.msgprint(
//                             __("Commission Amount calculated successfully: {0}", [r.message.commission_amount])
//                         );
//                         frm.reload_doc();
//                     }
//                 }
//             });
//         }).addClass("btn-primary");
//     }
// });

frappe.ui.form.on("Commission", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Calculate Commission"), function () {
            if (!frm.doc.scheme_code) {
                frappe.msgprint(__("Scheme Code is required."));
                return;
            }

            if (!frm.doc.collection) {
                frappe.msgprint(__("Collection is required."));
                return;
            }

            // Check Commission Settings before calculation.
            frappe.call({
                method: "frappe.client.get_single_value",
                args: {
                    doctype: "Commission Settings",
                    field: "calculate_commission"
                },
                callback: function (settings_response) {
                    if (!cint(settings_response.message)) {
                        frappe.msgprint({
                            title: __("Calculation Disabled"),
                            message: __(
                                "Enable 'Calculate Commission' in Commission Settings before calculating commission."
                            ),
                            indicator: "red"
                        });
                        return;
                    }

                    // Existing calculation call.
                    frappe.call({
                        method: "banking_api.banking_api.doctype.commission.commission.calculate_commission_amount",
                        args: {
                            docname: frm.doc.name
                        },
                        freeze: true,
                        freeze_message: __(
                            "Calculating commission amount..."
                        ),
                        callback: function (r) {
                            if (r.message) {
                                frappe.msgprint(
                                    __(
                                        "Commission Amount calculated successfully: {0}",
                                        [
                                            r.message.commission_amount
                                        ]
                                    )
                                );

                                frm.reload_doc();
                            }
                        }
                    });
                }
            });
        }).addClass("btn-primary");
    }
});