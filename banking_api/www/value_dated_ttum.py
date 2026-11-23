import frappe
from frappe import _


def get_context(context):
    # Not logged in
    if not frappe.session.user or frappe.session.user == "Guest":
        context.no_cache = 1
        context.is_access_denied = True
        context.access_title = _("Login Required")
        context.access_message = _(
            "You must be logged in to access Value Dated TTUM.")
        context.access_icon = "lock"  # you can use this in template if you want
        return

    # Logged in but no required role
    if "Value Dated TTUM User" not in frappe.get_roles(frappe.session.user):
        context.no_cache = 1
        context.is_access_denied = True
        context.access_title = _("Access Restricted")
        context.access_message = _(
            "You do not have the required role to access Value Dated TTUM. "
            "Please contact your system administrator."
        )
        context.required_role = "Value Dated TTUM User"
        return

    # User has role → normal page
    context.no_cache = 1
    context.is_access_denied = False
