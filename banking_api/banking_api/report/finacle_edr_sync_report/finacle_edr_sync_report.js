frappe.query_reports["Finacle EDR Sync Report"] = {
    filters: [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            reqd: 0,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            reqd: 0,
        },
    ],
    onload: function (report) {
        report.page.add_button(__("Download Excel"), function () {
            let filters = report.get_values();
            frappe.call({
                method: "frappe.client.get_list",
                args: {
                    doctype: "Finacle EDR Sync Log",
                    filters: report.get_filters_for_query(),
                    limit_page_length: 0,
                    as_array: true,
                },
                callback: function () {
                    let url = frappe.request.url;
                    let api_url =
                        url.split("/api/method")[0] +
                        "/api/method/frappe.desk.query_report.run";
                    let form = document.createElement("form");
                    form.method = "POST";
                    form.action = api_url;
                    form.target = "_blank";

                    let inputdoctype = document.createElement("input");
                    inputdoctype.type = "hidden";
                    inputdoctype.name = "doctype";
                    inputdoctype.value = "Finacle EDR Sync Report";
                    form.appendChild(inputdoctype);

                    if (filters.from_date) {
                        let inputfrom = document.createElement("input");
                        inputfrom.type = "hidden";
                        inputfrom.name = "from_date";
                        inputfrom.value = filters.from_date;
                        form.appendChild(inputfrom);
                    }
                    if (filters.to_date) {
                        let inputto = document.createElement("input");
                        inputto.type = "hidden";
                        inputto.name = "to_date";
                        inputto.value = filters.to_date;
                        form.appendChild(inputto);
                    }

                    let inputformat = document.createElement("input");
                    inputformat.type = "hidden";
                    inputformat.name = "file_format_type";
                    inputformat.value = "Excel";
                    form.appendChild(inputformat);

                    let inputctype = document.createElement("input");
                    inputctype.type = "hidden";
                    inputctype.name = "content_type";
                    inputctype.value = "xlsx";
                    form.appendChild(inputctype);

                    document.body.appendChild(form);
                    form.submit();
                    document.body.removeChild(form);
                },
            });
        }, __("Export"));
    },
};
