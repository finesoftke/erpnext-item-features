# Copyright (c) 2023, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import cint, cstr, flt, today
from erpnext.stock.doctype.item.item import get_item_details
from erpnext.manufacturing.doctype.bom.bom import get_bom_item_rate

class ItemFeature(Document):
	
	@frappe.whitelist()
	def get_bom_material_detail(self, args=None):
		"""Get raw material details like uom, desc and rate"""
		if not args:
			args = frappe.form_dict.get("args")

		if isinstance(args, str):
			import json

			args = json.loads(args)

		item = self.get_item_det(args["item_code"])

		args["bom_no"] = args["bom_no"] or item and cstr(item["default_bom"]) or ""
		args["transfer_for_manufacture"] = (
			cstr(args.get("include_item_in_manufacturing", ""))
			or item
			and item.include_item_in_manufacturing
			or 0
		)
		args.update(item)

		rate = self.get_rm_rate(args)
		ret_item = {
			"item_name": item and args["item_name"] or "",
			"description": item and args["description"] or "",
			"image": item and args["image"] or "",
			"stock_uom": item and args["stock_uom"] or "",
			"uom": item and args["stock_uom"] or "",
			"conversion_factor": 1,
			"bom_no": args["bom_no"],
			"rate": rate,
			"qty": args.get("qty") or args.get("stock_qty") or 1,
			"stock_qty": args.get("qty") or args.get("stock_qty") or 1,
			"base_rate":  1,
			"include_item_in_manufacturing": cint(args.get("transfer_for_manufacture")),
			"sourced_by_supplier": args.get("sourced_by_supplier", 0),
		}

		if args.get("do_not_explode"):
			ret_item["bom_no"] = ""

		return ret_item



	def get_rm_rate(self, arg):
		"""Get raw material rate as per selected method, if bom exists takes bom cost"""
		rate = 0
		if not self.rm_cost_as_per:
			self.rm_cost_as_per = "Valuation Rate"

		# Customer Provided parts and Supplier sourced parts will have zero rate
		if not frappe.db.get_value(
			"Item", arg["item_code"], "is_customer_provided_item"
		) and not arg.get("sourced_by_supplier"):
			if arg.get("bom_no") and self.set_rate_of_sub_assembly_item_based_on_bom:
				rate = flt(self.get_bom_unitcost(arg["bom_no"])) * (arg.get("conversion_factor") or 1)
			else:
				rate = get_bom_item_rate(arg, self)

				if not rate:
					if self.rm_cost_as_per == "Price List":
						frappe.msgprint(
							_("Price not found for item {0} in price list {1}").format(
								arg["item_code"], self.buying_price_list
							),
							alert=True,
						)
					else:
						frappe.msgprint(
							_("{0} not found for item {1}").format(self.rm_cost_as_per, arg["item_code"]), alert=True
						)
		return flt(rate)


	def get_item_det(self, item_code):
		item = get_item_details(item_code)

		if not item:
			frappe.throw(_("Item: {0} does not exist in the system").format(item_code))

		return item
