import frappe
import json
from frappe import _
from erpnext.manufacturing.doctype.work_order.work_order import get_item_details, add_variant_item 
from frappe.utils import (
	cint,
	date_diff,
	flt,
	get_datetime,
	get_link_to_form,
	getdate,
	nowdate,
	time_diff_in_hours,
)

@frappe.whitelist()
def make_work_order_from_bom(bom_no, item, qty=0, project=None, variant_items=None, features = []):
	if not frappe.has_permission("Work Order", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	item_details = get_item_details(item, project)
	if isinstance(features, str):
		features = json.loads(features)

	wo_doc = frappe.new_doc("Work Order")
	wo_doc.production_item = item
	wo_doc.update(item_details)
	wo_doc.bom_no = bom_no
	
	for feat in features:
		wo_doc.append("item_features", {
			'item_feature': feat["item_feature"]
		})

	if flt(qty) > 0:
		wo_doc.qty = flt(qty)
		wo_doc.get_items_and_operations_from_bom()

	if variant_items:
		add_variant_item(variant_items, wo_doc, bom_no, "required_items")

	return wo_doc