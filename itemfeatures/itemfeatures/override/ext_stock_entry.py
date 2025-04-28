from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry, create_serial_and_batch_bundle,get_supplied_items,
import frappe
from frappe import _
from collections import defaultdict

from frappe.utils import (
	cint,
	comma_or,
	cstr,
	flt,
	format_time,
	formatdate,
	get_link_to_form,
	getdate,
	nowdate,
)
from erpnext.stock.stock_ledger import  get_valuation_rate

import erpnext

from erpnext.stock.doctype.item.item import get_item_defaults
from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos

from erpnext.stock.get_item_details import (
	get_conversion_factor,
	get_default_cost_center,
)
from erpnext.stock.utils import get_bin



class ExtStockEntry(StockEntry):

	def set_basic_rate(self, reset_outgoing_rate=True, raise_error_if_no_rate=True):
		"""
		Set rate for outgoing, scrapped and finished items
		"""
		# Set rate for outgoing items
		outgoing_items_cost = self.set_rate_for_outgoing_items(reset_outgoing_rate, raise_error_if_no_rate)
		finished_item_qty = sum(d.transfer_qty for d in self.items if d.is_finished_item)

		items = []
		# Set basic rate for incoming items
		for d in self.get("items"):
			if d.s_warehouse or d.set_basic_rate_manually:
				continue

			if d.allow_zero_valuation_rate:
				d.basic_rate = 0.0
				items.append(d.item_code)

			elif d.is_finished_item:
				if self.purpose == "Manufacture":
					d.basic_rate = self.get_basic_rate_for_manufactured_item(
						finished_item_qty, outgoing_items_cost
					)
				elif self.purpose == "Repack":
					d.basic_rate = self.get_basic_rate_for_repacked_items(d.transfer_qty, outgoing_items_cost)

			if not d.basic_rate and not d.allow_zero_valuation_rate:
				if self.is_new():
					raise_error_if_no_rate = False

				d.basic_rate = get_valuation_rate(
					d.item_code,
					d.t_warehouse,
					self.doctype,
					self.name,
					custom_feature=d.custom_feature,
					allow_zero_rate=d.allow_zero_valuation_rate,
					currency=erpnext.get_company_currency(self.company),
					company=self.company,
					raise_error_if_no_rate=raise_error_if_no_rate,
					batch_no=d.batch_no,
					serial_and_batch_bundle=d.serial_and_batch_bundle,
				)

			# do not round off basic rate to avoid precision loss
			d.basic_rate = flt(d.basic_rate)
			d.basic_amount = flt(flt(d.transfer_qty) * flt(d.basic_rate), d.precision("basic_amount"))

		if items:
			message = ""

			if len(items) > 1:
				message = _(
					"Items rate has been updated to zero as Allow Zero Valuation Rate is checked for the following items: {0}"
				).format(", ".join(frappe.bold(item) for item in items))
			else:
				message = _(
					"Item rate has been updated to zero as Allow Zero Valuation Rate is checked for item {0}"
				).format(frappe.bold(items[0]))

			frappe.msgprint(message, alert=True)

	def get_args_for_incoming_rate(self, item):
		return frappe._dict(
			{
				"item_code": item.item_code,
				"warehouse": item.s_warehouse or item.t_warehouse,
				"posting_date": self.posting_date,
				"posting_time": self.posting_time,
				"qty": item.s_warehouse and -1 * flt(item.transfer_qty) or flt(item.transfer_qty),
				"voucher_type": self.doctype,
				"voucher_no": self.name,
				"company": self.company,
				"allow_zero_valuation": item.allow_zero_valuation_rate,
				"serial_and_batch_bundle": item.serial_and_batch_bundle,
				"voucher_detail_no": item.name,
				"batch_no": item.batch_no,
				"serial_no": item.serial_no,
				"custom_feature": item.custom_feature,
			}
		)

	def load_items_from_bom(self):
		feature = None
		if self.work_order:
			item_code = self.pro_doc.production_item
			to_warehouse = self.pro_doc.fg_warehouse
			from itemfeatures.itemfeatures.utils import get_composite_feature
			wo = frappe.get_doc("Work Order", self.work_order)
			features_list = []
			if wo.item_features:
				for feat in wo.item_features:
					features_list.append(feat.item_feature)

			if len(features_list):
				feature = get_composite_feature(features_list)
		else:
			item_code = frappe.db.get_value("BOM", self.bom_no, "item")
			to_warehouse = self.to_warehouse

		item = get_item_defaults(item_code, self.company)

		if not self.work_order and not to_warehouse:
			# in case of BOM
			to_warehouse = item.get("default_warehouse")
		args = {
			"to_warehouse": to_warehouse,
			"from_warehouse": "",
			"qty": flt(self.fg_completed_qty) - flt(self.process_loss_qty),
			"item_name": item.item_name,
			"custom_feature": feature,
			"description": item.description,
			"stock_uom": item.stock_uom,
			"expense_account": item.get("expense_account"),
			"cost_center": item.get("buying_cost_center"),
			"is_finished_item": 1,
		}

		if (
			self.work_order
			and self.pro_doc.has_batch_no
			and not self.pro_doc.has_serial_no
			and cint(
				frappe.db.get_single_value(
					"Manufacturing Settings", "make_serial_no_batch_from_work_order", cache=True
				)
			)
		):
			self.set_batchwise_finished_goods(args, item)
		else:
			self.add_finished_goods(args, item)


	def update_item_in_stock_entry_detail(self, row, item, qty) -> None:
		if not qty:
			return

		use_serial_batch_fields = frappe.db.get_single_value("Stock Settings", "use_serial_batch_fields")

		conversion_factor = get_conversion_factor(item.item_code, item.uom).get("conversion_factor")

		ste_item_details = {
			"from_warehouse": item.warehouse,
			"to_warehouse": "",
			"qty": qty,
			"uom": item.uom,
			"custom_feature": item.custom_feature,
			"item_name": item.item_name,
			"serial_and_batch_bundle": create_serial_and_batch_bundle(self, row, item, "Outward")
			if not use_serial_batch_fields
			else "",
			"description": item.description,
			"stock_uom": item.stock_uom,
			"conversion_factor": conversion_factor,
			"expense_account": item.expense_account,
			"cost_center": item.buying_cost_center,
			"original_item": item.original_item,
			"serial_no": "\n".join(row.serial_nos)
			if row.serial_nos and not row.batches_to_be_consume
			else "",
			"use_serial_batch_fields": use_serial_batch_fields,
		}

		if self.is_return:
			ste_item_details["to_warehouse"] = item.s_warehouse

		if use_serial_batch_fields and not row.serial_no and row.batches_to_be_consume:
			for batch_no, batch_qty in row.batches_to_be_consume.items():
				ste_item_details.update(
					{
						"batch_no": batch_no,
						"qty": batch_qty,
					}
				)

				self.add_to_stock_entry_detail({item.item_code: ste_item_details})
		else:
			self.add_to_stock_entry_detail({item.item_code: ste_item_details})


	def add_to_stock_entry_detail(self, item_dict, bom_no=None):
		precision = frappe.get_precision("Stock Entry Detail", "qty")
		for d in item_dict:
			item_row = item_dict[d]

			child_qty = flt(item_row["qty"], precision)
			if not self.is_return and child_qty <= 0:
				continue

			se_child = self.append("items")
			stock_uom = item_row.get("stock_uom") or frappe.db.get_value("Item", d, "stock_uom")
			se_child.s_warehouse = item_row.get("from_warehouse")
			se_child.t_warehouse = item_row.get("to_warehouse")
			se_child.item_code = item_row.get("item_code") or cstr(d)
			se_child.uom = item_row["uom"] if item_row.get("uom") else stock_uom
			se_child.stock_uom = stock_uom
			se_child.custom_feature = item_row.get("custom_feature")
			se_child.qty = child_qty
			se_child.allow_alternative_item = item_row.get("allow_alternative_item", 0)
			se_child.subcontracted_item = item_row.get("main_item_code")
			se_child.cost_center = item_row.get("cost_center") or get_default_cost_center(
				item_row, company=self.company
			)
			se_child.is_finished_item = item_row.get("is_finished_item", 0)
			se_child.is_scrap_item = item_row.get("is_scrap_item", 0)
			se_child.po_detail = item_row.get("po_detail")
			se_child.sco_rm_detail = item_row.get("sco_rm_detail")

			for field in [
				self.subcontract_data.rm_detail_field,
				"original_item",
				"expense_account",
				"description",
				"item_name",
				"serial_and_batch_bundle", 
				"allow_zero_valuation_rate",
				"use_serial_batch_fields",
				"batch_no",
				"serial_no",
			]:
				if item_row.get(field):
					se_child.set(field, item_row.get(field))

			if se_child.s_warehouse is None:
				se_child.s_warehouse = self.from_warehouse
			if se_child.t_warehouse is None:
				se_child.t_warehouse = self.to_warehouse

			# in stock uom
			se_child.conversion_factor = flt(item_row.get("conversion_factor")) or 1
			se_child.transfer_qty = flt(
				item_row["qty"] * se_child.conversion_factor, se_child.precision("qty")
			)

			se_child.bom_no = bom_no  # to be assigned for finished item
			se_child.job_card_item = item_row.get("job_card_item") if self.get("job_card") else None


	def update_subcontract_order_supplied_items(self):
		if self.get(self.subcontract_data.order_field) and (
			self.purpose in ["Send to Subcontractor", "Material Transfer"] or self.is_return
		):
			# Get Subcontract Order Supplied Items Details
			order_supplied_items = frappe.db.get_all(
				self.subcontract_data.order_supplied_items_field,
				filters={"parent": self.get(self.subcontract_data.order_field)},
				fields=["name", "rm_item_code", "reserve_warehouse"],
			)

			# Get Items Supplied in Stock Entries against Subcontract Order
			supplied_items = get_supplied_items(
				self.get(self.subcontract_data.order_field),
				self.subcontract_data.rm_detail_field,
				self.subcontract_data.order_field,
			)

			for row in order_supplied_items:
				key, item = row.name, {}
				if not supplied_items.get(key):
					# no stock transferred against Subcontract Order Supplied Items row
					item = {"supplied_qty": 0, "returned_qty": 0, "total_supplied_qty": 0}
				else:
					item = supplied_items.get(key)

				frappe.db.set_value(self.subcontract_data.order_supplied_items_field, row.name, item)

			# RM Item-Reserve Warehouse Dict
			item_wh = {x.get("rm_item_code"): x.get("reserve_warehouse") for x in order_supplied_items}

			for d in self.get("items"):
				# Update reserved sub contracted quantity in bin based on Supplied Item Details and
				item_code = d.get("original_item") or d.get("item_code")
				reserve_warehouse = item_wh.get(item_code)
				if not (reserve_warehouse and item_code):
					continue
				stock_bin = get_bin(item_code, reserve_warehouse, d.custom_feature)
				stock_bin.update_reserved_qty_for_sub_contracting()




def get_available_materials(work_order) -> dict:
	data = get_stock_entry_data(work_order)

	available_materials = {}
	for row in data:
		key = (row.item_code, row.warehouse, row.custom_feature)
		if row.purpose != "Material Transfer for Manufacture":
			key = (row.item_code, row.s_warehouse, row.custom_feature)

		if key not in available_materials:
			available_materials.setdefault(
				key,
				frappe._dict(
					{"item_details": row, "batch_details": defaultdict(float), "qty": 0, "serial_nos": []}
				),
			)

		item_data = available_materials[key]

		if row.purpose == "Material Transfer for Manufacture":
			item_data.qty += row.qty
			if row.batch_no:
				item_data.batch_details[row.batch_no] += row.qty

			elif row.batch_nos:
				for batch_no, qty in row.batch_nos.items():
					item_data.batch_details[batch_no] += qty

			if row.serial_no:
				item_data.serial_nos.extend(get_serial_nos(row.serial_no))
				item_data.serial_nos.sort()

			elif row.serial_nos:
				item_data.serial_nos.extend(get_serial_nos(row.serial_nos))
				item_data.serial_nos.sort()
		else:
			# Consume raw material qty in case of 'Manufacture' or 'Material Consumption for Manufacture'

			item_data.qty -= row.qty
			if row.batch_no:
				item_data.batch_details[row.batch_no] -= row.qty

			elif row.batch_nos:
				for batch_no, qty in row.batch_nos.items():
					item_data.batch_details[batch_no] += qty

			if row.serial_no:
				for serial_no in get_serial_nos(row.serial_no):
					if serial_no in item_data.serial_nos:
						item_data.serial_nos.remove(serial_no)

			elif row.serial_nos:
				for serial_no in get_serial_nos(row.serial_nos):
					if serial_no in item_data.serial_nos:
						item_data.serial_nos.remove(serial_no)
	return available_materials


def get_stock_entry_data(work_order):
	from erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle import (
		get_voucher_wise_serial_batch_from_bundle,
	)

	stock_entry = frappe.qb.DocType("Stock Entry")
	stock_entry_detail = frappe.qb.DocType("Stock Entry Detail")

	data = (
		frappe.qb.from_(stock_entry)
		.from_(stock_entry_detail)
		.select(
			stock_entry_detail.item_name,
			stock_entry_detail.original_item,
			stock_entry_detail.item_code,
			stock_entry_detail.qty,
			(stock_entry_detail.t_warehouse).as_("warehouse"),
			(stock_entry_detail.s_warehouse).as_("s_warehouse"),
			stock_entry_detail.description,
			stock_entry_detail.stock_uom,
			stock_entry_detail.uom,
			stock_entry_detail.expense_account,
			stock_entry_detail.cost_center,
			stock_entry_detail.serial_and_batch_bundle,
			stock_entry_detail.batch_no,
			stock_entry_detail.serial_no,
			stock_entry_detail.custom_feature,
			stock_entry.purpose,
			stock_entry.name,
		)
		.where(
			(stock_entry.name == stock_entry_detail.parent)
			& (stock_entry.work_order == work_order)
			& (stock_entry.docstatus == 1)
			& (stock_entry_detail.s_warehouse.isnotnull())
			& (
				stock_entry.purpose.isin(
					[
						"Manufacture",
						"Material Consumption for Manufacture",
						"Material Transfer for Manufacture",
					]
				)
			)
		)
		.orderby(stock_entry.creation, stock_entry_detail.item_code, stock_entry_detail.idx)
	).run(as_dict=1)

	if not data:
		return []

	voucher_nos = [row.get("name") for row in data if row.get("name")]
	if voucher_nos:
		bundle_data = get_voucher_wise_serial_batch_from_bundle(voucher_no=voucher_nos)
		for row in data:
			key = (row.item_code, row.warehouse, row.name)
			if row.purpose != "Material Transfer for Manufacture":
				key = (row.item_code, row.s_warehouse, row.name)

			if bundle_data.get(key):
				row.update(bundle_data.get(key))

	return data
