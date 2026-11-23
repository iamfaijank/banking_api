
frappe.pages['cif-updation'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('CIF Assignment'),
		single_column: true
	});

	const form_html = `
        <style>
            .cif-page {
                max-width: 560px;
                margin: 36px auto;
                padding: 0 16px 32px;
            }

            .cif-card {
                background: var(--card-bg, #fff);
                border: 1px solid var(--border-color, #e5e7eb);
                border-radius: 14px;
                overflow: hidden;
                box-shadow: 0 5px 22px rgba(0, 0, 0, 0.045);
            }

            .cif-card-header {
                padding: 25px 28px 21px;
                border-bottom: 1px solid var(--border-color, #e5e7eb);
            }

            .cif-heading {
                display: flex;
                align-items: center;
                gap: 13px;
            }

            .cif-heading-icon {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 46px;
                height: 46px;
                flex-shrink: 0;
                border-radius: 12px;
                background: var(--subtle-accent, #eaf2ff);
                color: var(--primary, #2878d0);
                font-size: 23px;
            }

            .cif-heading h4 {
                margin: 0 0 5px;
                font-size: 19px;
                font-weight: 650;
                color: var(--heading-color, #202b3c);
            }

            .cif-subtitle {
                margin: 0;
                color: var(--text-muted, #737b87);
                font-size: 12px;
                line-height: 1.6;
            }

            .cif-card-body {
                padding: 25px 28px 28px;
            }

            .cif-section-label {
                display: block;
                margin-bottom: 10px;
                font-size: 12px;
                font-weight: 650;
                color: var(--text-color, #374151);
            }

            .cif-segment {
                display: flex;
                padding: 4px;
                gap: 5px;
                background: var(--control-bg, #f3f5f8);
                border: 1px solid var(--border-color, #e5e7eb);
                border-radius: 10px;
                margin-bottom: 25px;
            }

            .cif-segment button {
                flex: 1;
                min-height: 42px;
                border: 1px solid transparent;
                border-radius: 7px;
                background: transparent;
                color: var(--text-muted, #737b87);
                font-size: 13px;
                font-weight: 600;
                transition: background 0.15s ease, color 0.15s ease;
            }

            .cif-segment button.active {
                background: var(--card-bg, #fff);
                color: var(--primary, #2878d0);
                border-color: var(--border-color, #e0e5ec);
                box-shadow: 0 1px 4px rgba(0, 0, 0, 0.07);
            }

            .cif-segment button:focus-visible {
                outline: 2px solid var(--primary, #2878d0);
                outline-offset: 2px;
            }

            .cif-field {
                margin-bottom: 20px;
            }

            .cif-field label {
                display: block;
                margin-bottom: 8px;
                color: var(--text-color, #374151);
                font-size: 12px;
                font-weight: 650;
            }

            .cif-field .form-control {
                height: 43px;
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 13px;
                border-color: var(--border-color, #dce1e8);
                box-shadow: none;
                transition: border-color 0.15s ease;
            }

            .cif-field .form-control:focus {
                border-color: var(--primary, #2878d0);
                box-shadow: 0 0 0 3px rgba(40, 120, 208, 0.10);
            }

            .cif-field .form-control::placeholder {
                color: var(--text-light, #a0a7b2);
            }

            .cif-hint {
                margin-top: 7px;
                font-size: 11px;
                color: var(--text-muted, #818895);
                line-height: 1.5;
            }

            .cif-submit {
                width: 100%;
                height: 44px;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
                margin-top: 7px;
                transition: opacity 0.15s ease;
            }

            .cif-submit:disabled {
                cursor: not-allowed;
                opacity: 0.7;
            }

            .cif-footer {
                text-align: center;
                margin-top: 17px;
                color: var(--text-muted, #818895);
                font-size: 11px;
            }

            @media (max-width: 480px) {
                .cif-page {
                    margin-top: 20px;
                    padding-left: 12px;
                    padding-right: 12px;
                }

                .cif-card-header {
                    padding: 21px 18px;
                }

                .cif-card-body {
                    padding: 22px 18px;
                }
            }
        </style>

        <div class="cif-page">
            <div class="cif-card">

                <div class="cif-card-header">
                    <div class="cif-heading">
                        <div class="cif-heading-icon">
                            <i class="fa fa-id-card-o"></i>
                        </div>

                        <div>
                            <h4>${__('CIF Assignment')}</h4>
                            <p class="cif-subtitle">
                                ${__('Assign a CIF to the appropriate user using their Auth ID.')}
                            </p>
                        </div>
                    </div>
                </div>

                <div class="cif-card-body">

                    <label class="cif-section-label">
                        ${__('Select CIF Type')}
                    </label>

                    <div class="cif-segment" role="group"
                        aria-label="${__('CIF Type')}">

                        <button type="button"
                            id="btn-retail-cif"
                            class="active"
                            aria-pressed="true">
                            <i class="fa fa-user-o"></i>
                            &nbsp; ${__('Retail')}
                        </button>

                        <button type="button"
                            id="btn-corporate-cif"
                            aria-pressed="false">
                            <i class="fa fa-building-o"></i>
                            &nbsp; ${__('Corporate')}
                        </button>

                    </div>

                    <div class="cif-field">
                        <label for="cif-auth-id">
                            ${__('Auth ID')}
                            <span style="color: var(--red, #d9534f)">*</span>
                        </label>

                        <input
                            type="text"
                            class="form-control"
                            id="cif-auth-id"
                            placeholder="${__('Enter Auth ID (e.g., SAH01549)')}"
                            autocomplete="off"
                            spellcheck="false">

                        <div class="cif-hint">
                            ${__('Enter the user login ID to retrieve their Person ID.')}
                        </div>
                    </div>

                    <div class="cif-field">
                        <label for="cif-id">
                            ${__('CIF ID')}
                            <span style="color: var(--red, #d9534f)">*</span>
                        </label>

                        <input
                            type="text"
                            class="form-control"
                            id="cif-id"
                            placeholder="${__('Enter CIF ID (e.g., 400357659)')}"
                            autocomplete="off"
                            spellcheck="false">

                        <div class="cif-hint" id="cif-type-hint">
                            ${__('The Retail CIF will be updated for the selected user.')}
                        </div>
                    </div>

                    <button type="button"
                        class="btn btn-primary cif-submit"
                        id="btn-submit-cif">

                        <i class="fa fa-check-circle"></i>
                        <span>${__('Update Assignment')}</span>
                    </button>

                    <div class="cif-footer">
                        <i class="fa fa-shield"></i>
                        &nbsp; ${__('Please verify the Auth ID and CIF ID before updating.')}
                    </div>

                </div>
            </div>
        </div>
    `;

	$(page.body).html(form_html);

	const $auth_input = $(page.body).find('#cif-auth-id');
	const $cif_input = $(page.body).find('#cif-id');
	const $submit_btn = $(page.body).find('#btn-submit-cif');
	const $retail_btn = $(page.body).find('#btn-retail-cif');
	const $corporate_btn = $(page.body).find('#btn-corporate-cif');
	const $cif_hint = $(page.body).find('#cif-type-hint');

	let cif_type = 'Retail';
	let is_submitting = false;

	// Toggle CIF type without changing the existing backend logic.
	function set_cif_type(type) {
		cif_type = type;

		const is_retail = type === 'Retail';

		$retail_btn
			.toggleClass('active', is_retail)
			.attr('aria-pressed', String(is_retail));

		$corporate_btn
			.toggleClass('active', !is_retail)
			.attr('aria-pressed', String(!is_retail));

		$cif_hint.text(
			is_retail
				? __('The Retail CIF will be updated for the selected user.')
				: __('The Corporate CIF will be updated for the selected user.')
		);
	}

	$retail_btn.on('click', function () {
		set_cif_type('Retail');
	});

	$corporate_btn.on('click', function () {
		set_cif_type('Corporate');
	});

	function handleSubmit() {
		if (is_submitting) return;

		const auth_id = $auth_input.val().trim();
		const cif_id = $cif_input.val().trim();

		if (!auth_id || !cif_id) {
			frappe.msgprint({
				title: __('Validation Error'),
				message: __('Please enter both Auth ID and CIF ID.'),
				indicator: 'orange'
			});

			if (!auth_id) {
				$auth_input.trigger('focus');
			} else {
				$cif_input.trigger('focus');
			}

			return;
		}

		is_submitting = true;
		$submit_btn.prop('disabled', true);
		$submit_btn.html(`
            <i class="fa fa-spinner fa-spin"></i>
            <span>${__('Updating Assignment...')}</span>
        `);

		frappe.call({
			method: 'banking_api.banking_api.page.cif_updation.cif_updation.update_cif_assignment',

			args: {
				auth_id: auth_id,
				cif_id: cif_id,
				cif_type: cif_type
			},

			freeze: true,
			freeze_message: __('Updating CIF Assignment...'),

			callback: function (response) {
				const res = response.message;

				if (!res) return;

				if (res.status === 'success') {
					frappe.msgprint({
						title: __('Assignment Updated'),

						message: `
                            <div style="line-height: 1.9;">
                                <p style="color: var(--green, #28a745); font-weight: 600;">
                                    ${frappe.utils.escape_html(res.message)}
                                </p>

                                <hr>

                                <div>
                                    <b>${__('CIF Type')}:</b>
                                    ${frappe.utils.escape_html(res.cif_type || cif_type)}
                                </div>

                                <div>
                                    <b>${__('CIF ID')}:</b>
                                    ${frappe.utils.escape_html(String(res.cif_id))}
                                </div>

                                <div>
                                    <b>${__('Person ID')}:</b>
                                    ${frappe.utils.escape_html(String(res.person_id))}
                                </div>

                                <div>
                                    <b>${__('Rows Affected')}:</b>
                                    ${Number(res.rows_updated) || 0}
                                </div>
                            </div>
                        `,

						indicator: 'green'
					});

					$cif_input.val('').trigger('focus');

				} else if (res.status === 'error') {
					frappe.msgprint({
						title: __('Error'),
						message: frappe.utils.escape_html(res.message),
						indicator: 'red'
					});
				}
			},

			error: function () {
				frappe.msgprint({
					title: __('Error'),
					message: __('Unable to update the CIF assignment. Please try again.'),
					indicator: 'red'
				});
			},

			always: function () {
				is_submitting = false;

				$submit_btn.prop('disabled', false);
				$submit_btn.html(`
                    <i class="fa fa-check-circle"></i>
                    <span>${__('Update Assignment')}</span>
                `);
			}
		});
	}

	$submit_btn.on('click', handleSubmit);

	$auth_input.add($cif_input).on('keypress', function (e) {
		if (e.which === 13) {
			e.preventDefault();
			handleSubmit();
		}
	});
};
