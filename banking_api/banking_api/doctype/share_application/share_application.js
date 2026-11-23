frappe.ui.form.on("Share Application", {
	// refresh(frm) {
	// 	if (frm.is_new()) return;

	// 	if (frm.doc.payment_status === "Success") {
	// 		frm.add_custom_button(__("Print Share Certificate"), function () {
	// 			open_share_certificate_dialog(frm);
	// 		});

	// 		frm.change_custom_button_type(__("Print Share Certificate"), null, "primary");
	// 	}

	// 	const can_pay = frm.doc.docstatus === 0 && frm.doc.payment_status !== "Success";
	// 	if (!can_pay) return;

	// 	frm.add_custom_button(__("Pay Now"), function () {
	// 		frappe.confirm(
	// 			__("Are you sure you want to initiate the fund transfer for this Share Application?"),
	// 			function () {
	// 				frappe.call({
	// 					method: "banking_api.banking_api.doctype.share_application_settings.share_application_settings.pay_now_share_application",
	// 					args: {
	// 						entry_name: frm.doc.name
	// 					},
	// 					freeze: true,
	// 					freeze_message: __("Initiating fund transfer..."),
	// 					callback: function (r) {
	// 						if (r.message) {
	// 							frappe.msgprint({
	// 								title: __("Fund Transfer Result"),
	// 								message: r.message.message || __("Process completed."),
	// 								indicator:
	// 									r.message.status === "success"
	// 										? "green"
	// 										: (r.message.status === "warning" ? "orange" : "red")
	// 							});
	// 						}
	// 						frm.reload_doc();
	// 					}
	// 				});
	// 			}
	// 		);
	// 	});

	// 	frm.change_custom_button_type(__("Pay Now"), null, "primary");
	// }

	refresh(frm) {
		if (frm.is_new()) return;

		if (frm.doc.docstatus === 1) {
			setTimeout(() => {
				frm.page.wrapper.find('[data-label="Cancel"]').each(function () {
					$(this).closest('button, a, .menu-item, li').hide();
					$(this).closest('button, a, .menu-item, li').remove();
				});

				frm.page.actions.find('[data-label="Cancel"]').parent().parent().remove();
				frm.page.btn_secondary.find('[data-label="Cancel"]').hide();
				frm.page.btn_secondary.hide();
			}, 10);
		}

		if (frm.doc.payment_status === "Success") {
			frm.add_custom_button(__("Print Share Certificate"), function () {
				open_share_certificate_dialog(frm);
			});

			frm.change_custom_button_type(__("Print Share Certificate"), null, "primary");
		}

		const can_pay = frm.doc.docstatus === 0 && frm.doc.payment_status !== "Success";
		if (!can_pay) return;

		frm.add_custom_button(__("Pay Now"), function () {
			frappe.confirm(
				__("Are you sure you want to initiate the fund transfer for this Share Application?"),
				function () {
					frappe.call({
						method: "banking_api.banking_api.doctype.share_application_settings.share_application_settings.pay_now_share_application",
						args: {
							entry_name: frm.doc.name
						},
						freeze: true,
						freeze_message: __("Initiating fund transfer..."),
						callback: function (r) {
							if (r.message) {
								frappe.msgprint({
									title: __("Fund Transfer Result"),
									message: r.message.message || __("Process completed."),
									indicator:
										r.message.status === "success"
											? "green"
											: (r.message.status === "warning" ? "orange" : "red")
								});
							}
							frm.reload_doc();
						}
					});
				}
			);
		});

		frm.change_custom_button_type(__("Pay Now"), null, "primary");
	}
});

// function open_share_certificate_dialog(frm) {
// 	const today = frappe.datetime.nowdate();

// 	const cert_data = {
// 		share_certificate_no: frm.doc.name || "",
// 		account_no: frm.doc.account_number || "",
// 		name: frm.doc.customer_name || "",
// 		address: frm.doc.address || "",
// 		number_of_share: "1",
// 		from_no: "1",
// 		to_no: "1",
// 		rs: "10",
// 		// issued_date: frm.doc.cif_creation_date || today
// 		issued_date: frappe.datetime.str_to_user(frm.doc.cif_creation_date)
// 	};

// 	const positions = {
// 		certificate: {
// 			share_certificate_no: { top: 169, left: 495, width: 150, font_size: 12 },
// 			account_no: { top: 180, left: 832, width: 120, font_size: 12 },
// 			name: { top: 233, left: 454, width: 490, font_size: 12 },
// 			address: { top: 261, left: 418, width: 540, font_size: 11 },
// 			number_of_share: { top: 288, left: 544, width: 55, font_size: 12 },
// 			from_no: { top: 288, left: 765, width: 65, font_size: 12 },
// 			to_no: { top: 288, left: 904, width: 70, font_size: 12 },
// 			rs: { top: 315, left: 882, width: 80, font_size: 12 },
// 			issued_date: { top: 480, left: 630, width: 150, font_size: 12 }
// 		},
// 		receipt: {
// 			share_certificate_no: { top: 28, left: 24, width: 120, font_size: 12 },
// 			account_no: { top: 28, left: 202, width: 115, font_size: 12 },
// 			name: { top: 174, left: 78, width: 250, font_size: 12 },
// 			address: { top: 195, left: 52, width: 290, font_size: 11 },
// 			number_of_share: { top: 236, left: 184, width: 40, font_size: 12 },
// 			from_no: { top: 256, left: 113, width: 75, font_size: 12 },
// 			to_no: { top: 256, left: 265, width: 65, font_size: 12 },
// 			rs: { top: 297, left: 164, width: 70, font_size: 12 },
// 			issued_date: { top: 461, left: 187, width: 130, font_size: 12 }
// 		}
// 	};

// 	const d = new frappe.ui.Dialog({
// 		title: __("Share Certificate Preview"),
// 		size: "extra-large",
// 		fields: [
// 			{
// 				fieldname: "html_preview",
// 				fieldtype: "HTML"
// 			}
// 		],
// 		primary_action_label: __("Download PDF"),
// 		primary_action() {
// 			download_share_certificate_pdf(frm);
// 		}
// 	});

// 	d.show();

// 	const html = `
// 		<div style="overflow:auto; max-height:75vh; border:1px solid #d1d8dd; background:#f5f7fa; padding:16px;">
// 			<div id="share-certificate-preview"
// 				style="
// 					position: relative;
// 					width: 1000px;
// 					margin: 0 auto;
// 					background: #fff;
// 				">
// 				<img
// 					src="/assets/banking_api/images/share_certificate.png"
// 					alt="Share Certificate"
// 					style="width: 100%; display: block;"
// 				/>
// 			</div>
// 		</div>
// 	`;

// 	d.fields_dict.html_preview.$wrapper.html(html);

// 	const preview = d.fields_dict.html_preview.$wrapper.find("#share-certificate-preview")[0];

// 	function addText(key, value, cfg) {
//     const node = document.createElement("div");
//     node.className = "share-cert-text";
//     node.setAttribute("data-key", key);
//     node.style.position = "absolute";
//     node.style.top = `${cfg.top}px`;
//     node.style.left = `${cfg.left}px`;
//     node.style.width = `${cfg.width}px`;
//     node.style.fontSize = `${cfg.font_size}px`;
//     node.style.lineHeight = "1.2";
//     node.style.fontWeight = "600";
//     node.style.color = "#111";
//     node.style.fontFamily = "Arial, sans-serif";

//     const should_wrap =
//         key.includes("address") ||
//         key.includes("name");

//     node.style.whiteSpace = should_wrap ? "normal" : "nowrap";
//     node.style.wordBreak = should_wrap ? "break-word" : "normal";
//     node.style.overflowWrap = should_wrap ? "break-word" : "normal";

//     node.textContent = value || "";
//     preview.appendChild(node);
// }

// 	function renderPreview() {
// 		preview.querySelectorAll(".share-cert-text").forEach(el => el.remove());

// 		Object.keys(cert_data).forEach((key) => {
// 			// addText(`certificate_${key}`, cert_data[key], positions.certificate[key], key === "address");
// 			addText(`certificate_${key}`, cert_data[key], positions.certificate[key]);
// 		});

// 		Object.keys(cert_data).forEach((key) => {
// 			// addText(`receipt_${key}`, cert_data[key], positions.receipt[key], key === "address");
// 			addText(`receipt_${key}`, cert_data[key], positions.receipt[key]);
// 		});
// 	}

// 	renderPreview();

// 	window.__share_certificate_dialog_state = {
// 		frm_name: frm.doc.name,
// 		cert_data,
// 		positions
// 	};
// }


function open_share_certificate_dialog(frm) {
	frappe.call({
		method: "banking_api.banking_api.doctype.share_application_settings.share_application_settings.get_share_certificate_image",
		freeze: true,
		freeze_message: __("Loading share certificate template..."),
		callback: function (r) {
			if (!r.message || r.message.status !== "success" || !r.message.image_url) {
				frappe.msgprint({
					title: __("Certificate Image Missing"),
					message: __("Share Certificate Image is not set in Share Application Settings."),
					indicator: "red"
				});
				return;
			}

			const image_url = r.message.image_url;
			const today = frappe.datetime.nowdate();

			const cert_data = {
				share_certificate_no: frm.doc.name || "",
				account_no: frm.doc.account_number || "",
				name: frm.doc.customer_name || "",
				address: frm.doc.address || "",
				number_of_share: "1",
				from_no: "1",
				to_no: "1",
				rs: "10",
				issued_date: frm.doc.cif_creation_date
					? frappe.datetime.str_to_user(frm.doc.cif_creation_date)
					: frappe.datetime.str_to_user(today)
			};

			const positions = {
				certificate: {
					share_certificate_no: { top: 169, left: 495, width: 150, font_size: 12 },
					account_no: { top: 179, left: 821, width: 120, font_size: 12 },
					name: { top: 234, left: 454, width: 490, font_size: 12 },
					address: { top: 262, left: 418, width: 540, font_size: 11 },
					number_of_share: { top: 288, left: 544, width: 55, font_size: 12 },
					from_no: { top: 288, left: 765, width: 65, font_size: 12 },
					to_no: { top: 288, left: 904, width: 70, font_size: 12 },
					rs: { top: 315, left: 882, width: 80, font_size: 12 },
					issued_date: { top: 480, left: 630, width: 150, font_size: 12 }
				},
				receipt: {
					share_certificate_no: { top: 28, left: 24, width: 120, font_size: 12 },
					account_no: { top: 28, left: 203, width: 115, font_size: 12 },
					name: { top: 174, left: 78, width: 250, font_size: 12 },
					address: { top: 216, left: 52, width: 290, font_size: 11 },
					number_of_share: { top: 256, left: 184, width: 40, font_size: 12 },
					from_no: { top: 276, left: 113, width: 75, font_size: 12 },
					to_no: { top: 276, left: 265, width: 65, font_size: 12 },
					rs: { top: 317, left: 164, width: 70, font_size: 12 },
					issued_date: { top: 481, left: 187, width: 130, font_size: 12 }
				}
			};

			const d = new frappe.ui.Dialog({
				title: __("Share Certificate Preview"),
				size: "extra-large",
				fields: [
					{
						fieldname: "html_preview",
						fieldtype: "HTML"
					}
				],
				primary_action_label: __("Download PDF"),
				primary_action() {
					download_share_certificate_pdf(frm);
				}
			});

			d.show();

			const html = `
                <div style="overflow:auto; max-height:75vh; border:1px solid #d1d8dd; background:#f5f7fa; padding:16px;">
                    <div id="share-certificate-preview"
                        style="
                            position: relative;
                            width: 1000px;
                            margin: 0 auto;
                            background: #fff;
                        ">
                        <img
                            src="${image_url}"
                            alt="Share Certificate"
                            style="width: 100%; display: block;"
                        />
                    </div>
                </div>
            `;

			d.fields_dict.html_preview.$wrapper.html(html);

			const preview = d.fields_dict.html_preview.$wrapper.find("#share-certificate-preview")[0];

			function addText(key, value, cfg) {
				const node = document.createElement("div");
				node.className = "share-cert-text";
				node.setAttribute("data-key", key);
				node.style.position = "absolute";
				node.style.top = `${cfg.top}px`;
				node.style.left = `${cfg.left}px`;
				node.style.width = `${cfg.width}px`;
				node.style.fontSize = `${cfg.font_size}px`;
				node.style.lineHeight = "1.2";
				node.style.fontWeight = "600";
				node.style.color = "#111";
				node.style.fontFamily = "Arial, sans-serif";

				const should_wrap = key.includes("address") || key.includes("name");
				node.style.whiteSpace = should_wrap ? "normal" : "nowrap";
				node.style.wordBreak = should_wrap ? "break-word" : "normal";
				node.style.overflowWrap = should_wrap ? "break-word" : "normal";

				node.textContent = value || "";
				preview.appendChild(node);
			}

			function renderPreview() {
				preview.querySelectorAll(".share-cert-text").forEach(el => el.remove());

				Object.keys(cert_data).forEach((key) => {
					addText(`certificate_${key}`, cert_data[key], positions.certificate[key]);
				});

				Object.keys(cert_data).forEach((key) => {
					addText(`receipt_${key}`, cert_data[key], positions.receipt[key]);
				});
			}

			renderPreview();

			window.__share_certificate_dialog_state = {
				frm_name: frm.doc.name,
				cert_data,
				positions,
				image_url
			};
		}
	});
}


function download_share_certificate_pdf(frm) {
	const target = document.getElementById("share-certificate-preview");

	if (!target) {
		frappe.msgprint(__("Preview not found."));
		return;
	}

	const load_script = (src) => {
		return new Promise((resolve, reject) => {
			const existing = document.querySelector(`script[src="${src}"]`);
			if (existing) {
				resolve();
				return;
			}
			const script = document.createElement("script");
			script.src = src;
			script.onload = resolve;
			script.onerror = reject;
			document.head.appendChild(script);
		});
	};

	Promise.all([
		load_script("https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"),
		load_script("https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js")
	]).then(() => {
		frappe.dom.freeze(__("Generating PDF..."));

		window.html2canvas(target, {
			scale: 2,
			useCORS: true,
			backgroundColor: "#ffffff"
		}).then((canvas) => {
			const imgData = canvas.toDataURL("image/png");
			const { jsPDF } = window.jspdf;

			const pdf = new jsPDF("l", "mm", "a4");
			const pdfWidth = pdf.internal.pageSize.getWidth();
			const pdfHeight = pdf.internal.pageSize.getHeight();

			const imgWidth = canvas.width;
			const imgHeight = canvas.height;
			const ratio = Math.min(pdfWidth / imgWidth, pdfHeight / imgHeight);

			const finalWidth = imgWidth * ratio;
			const finalHeight = imgHeight * ratio;
			const x = (pdfWidth - finalWidth) / 2;
			const y = (pdfHeight - finalHeight) / 2;

			pdf.addImage(imgData, "PNG", x, y, finalWidth, finalHeight);
			pdf.save(`Share-Certificate-${frm.doc.name}.pdf`);
		}).catch((err) => {
			console.error(err);
			frappe.msgprint(__("Failed to generate PDF."));
		}).finally(() => {
			frappe.dom.unfreeze();
		});
	}).catch((err) => {
		console.error(err);
		frappe.msgprint(__("Could not load PDF libraries."));
	});
}