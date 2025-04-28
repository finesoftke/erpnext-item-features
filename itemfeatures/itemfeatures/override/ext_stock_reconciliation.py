from erpnext.stock.doctype.stock_reconciliation.stock_reconciliation import (
    StockReconciliation, 
	EmptyStockReconciliationItemsError,
	get_batch_qty_for_stock_reco,
	get_itemwise_batch,
	get_item_and_warehouses,
	)

import frappe
from frappe import _, bold, json, msgprint
from frappe.utils import cint, flt

from erpnext.stock.doctype.batch.batch import  get_batch_qty
from erpnext.stock.doctype.inventory_dimension.inventory_dimension import get_inventory_dimensions

from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos
from erpnext.stock.utils import get_incoming_rate, get_stock_balance


class ExtStockReconciliation(StockReconciliation):

	def remove_items_with_no_change(self):
		"""Remove items if qty or rate is not changed"""
		self.difference_amount = 0.0

		def _changed(item):
			if item.current_serial_and_batch_bundle:
				bundle_data = frappe.get_all(
					"Serial and Batch Bundle",
					filters={"name": item.current_serial_and_batch_bundle},
					fields=["total_qty as qty", "avg_rate as rate"],
				)[0]

				bundle_data.qty = abs(bundle_data.qty)
				self.calculate_difference_amount(item, bundle_data)

				return True

			inventory_dimensions_dict = {}
			if not item.batch_no and not item.serial_no:
				for dimension in get_inventory_dimensions():
					if item.get(dimension.get("fieldname")):
						inventory_dimensions_dict[dimension.get("fieldname")] = item.get(
							dimension.get("fieldname")
						)

			item_dict = get_stock_balance_for(
				item.item_code,
				item.warehouse,
				self.posting_date,
				self.posting_time,
				batch_no=item.batch_no,
				inventory_dimensions_dict=inventory_dimensions_dict,
				row=item,
				custom_feature=item.custom_feature,
			)

			if (
				(item.qty is None or item.qty == item_dict.get("qty"))
				and (item.valuation_rate is None or item.valuation_rate == item_dict.get("rate"))
				and (not item.serial_no or (item.serial_no == item_dict.get("serial_nos")))
			):
				return False
			else:
				# set default as current rates
				if item.qty is None:
					item.qty = item_dict.get("qty")

				if item.valuation_rate is None:
					item.valuation_rate = item_dict.get("rate")

				if item_dict.get("serial_nos"):
					item.current_serial_no = item_dict.get("serial_nos")
					if self.purpose == "Stock Reconciliation" and not item.serial_no and item.qty:
						item.serial_no = item.current_serial_no

				item.current_qty = item_dict.get("qty")
				item.current_valuation_rate = item_dict.get("rate")
				self.calculate_difference_amount(item, item_dict)
				return True

		items = list(filter(lambda d: _changed(d), self.items))

		if not items:
			frappe.throw(
				_("None of the items have any change in quantity or value."),
				EmptyStockReconciliationItemsError,
			)

		elif len(items) != len(self.items):
			self.items = items
			for i, item in enumerate(self.items):
				item.idx = i + 1
			frappe.msgprint(_("Removed items with no change in quantity or value."))


	def validate_data(self):
		def _get_msg(row_num, msg):
			return _("Row # {0}:").format(row_num + 1) + " " + msg

		self.validation_messages = []
		item_warehouse_combinations = []

		default_currency = frappe.db.get_default("currency")

		for row_num, row in enumerate(self.items):
			# find duplicates
			key = [row.item_code, row.warehouse]
			for field in ["serial_no", "batch_no", "custom_feature"]:
				if row.get(field):
					key.append(row.get(field))

			# if key in item_warehouse_combinations:
			# 	self.validation_messages.append(
			# 		_get_msg(row_num, _("Same item and warehouse combination already entered."))
			# 	)
			# else:
			item_warehouse_combinations.append(key)

			self.validate_item(row.item_code, row)

			if row.serial_no and not row.qty:
				self.validation_messages.append(
					_get_msg(
						row_num,
						f"Quantity should not be zero for the {bold(row.item_code)} since serial nos are specified",
					)
				)

			# validate warehouse
			if not frappe.db.get_value("Warehouse", row.warehouse):
				self.validation_messages.append(_get_msg(row_num, _("Warehouse not found in the system")))

			# if both not specified
			if row.qty in ["", None] and row.valuation_rate in ["", None]:
				self.validation_messages.append(
					_get_msg(row_num, _("Please specify either Quantity or Valuation Rate or both"))
				)

			# do not allow negative quantity
			if flt(row.qty) < 0:
				self.validation_messages.append(_get_msg(row_num, _("Negative Quantity is not allowed")))

			# do not allow negative valuation
			if flt(row.valuation_rate) < 0:
				self.validation_messages.append(
					_get_msg(row_num, _("Negative Valuation Rate is not allowed"))
				)

			if row.qty and row.valuation_rate in ["", None]:
				row.valuation_rate = get_stock_balance(
					row.item_code,
					row.warehouse,
					self.posting_date,
					self.posting_time,
					with_valuation_rate=True,
				)[1]
				if not row.valuation_rate:
					# try if there is a buying price list in default currency
					buying_rate = frappe.db.get_value(
						"Item Price",
						{"item_code": row.item_code, "buying": 1, "currency": default_currency},
						"price_list_rate",
					)
					if buying_rate:
						row.valuation_rate = buying_rate

					else:
						# get valuation rate from Item
						row.valuation_rate = frappe.get_value("Item", row.item_code, "valuation_rate")

		# throw all validation messages
		if self.validation_messages:
			for msg in self.validation_messages:
				msgprint(msg)

			raise frappe.ValidationError(self.validation_messages)


	def update_stock_ledger(self):
		"""find difference between current and expected entries
		and create stock ledger entries based on the difference"""
		from erpnext.stock.stock_ledger import get_previous_sle

		sl_entries = []
		for row in self.items:
			if not row.qty and not row.valuation_rate and not row.current_qty:
				self.make_adjustment_entry(row, sl_entries)
				continue

			item = frappe.get_cached_value(
				"Item", row.item_code, ["has_serial_no", "has_batch_no"], as_dict=1
			)

			if item.has_serial_no or item.has_batch_no:
				self.get_sle_for_serialized_items(row, sl_entries)
			else:
				if row.serial_and_batch_bundle:
					frappe.throw(
						_(
							"Row #{0}: Item {1} is not a Serialized/Batched Item. It cannot have a Serial No/Batch No against it."
						).format(row.idx, frappe.bold(row.item_code))
					)

				previous_sle = get_previous_sle(
					{
						"item_code": row.item_code,
						"warehouse": row.warehouse,
						"custom_feature": row.custom_feature,
						"posting_date": self.posting_date,
						"posting_time": self.posting_time,
					}
				)

				if previous_sle:
					if row.qty in ("", None):
						row.qty = previous_sle.get("qty_after_transaction", 0)

					if row.valuation_rate in ("", None):
						row.valuation_rate = previous_sle.get("valuation_rate", 0)

				if row.qty and not row.valuation_rate and not row.allow_zero_valuation_rate:
					frappe.throw(
						_("Valuation Rate required for Item {0} at row {1}").format(row.item_code, row.idx)
					)

				if (
					previous_sle
					and row.qty == previous_sle.get("qty_after_transaction")
					and (row.valuation_rate == previous_sle.get("valuation_rate") or row.qty == 0)
				) or (not previous_sle and not row.qty):
					continue

				sl_entries.append(self.get_sle_for_items(row))

		if sl_entries:
			allow_negative_stock = cint(frappe.db.get_single_value("Stock Settings", "allow_negative_stock"))
			self.make_sl_entries(sl_entries, allow_negative_stock=allow_negative_stock)


	def get_sle_for_items(self, row, serial_nos=None, current_bundle=True):
		"""Insert Stock Ledger Entries"""

		if not serial_nos and row.serial_no:
			serial_nos = get_serial_nos(row.serial_no)

		data = frappe._dict(
			{
				"doctype": "Stock Ledger Entry",
				"item_code": row.item_code,
				"warehouse": row.warehouse,
				"posting_date": self.posting_date,
				"posting_time": self.posting_time,
				"voucher_type": self.doctype,
				"voucher_no": self.name,
				"voucher_detail_no": row.name,
				"actual_qty": 0,
				"company": self.company,
				"stock_uom": frappe.db.get_value("Item", row.item_code, "stock_uom"),
				"is_cancelled": 1 if self.docstatus == 2 else 0,
				"valuation_rate": flt(row.valuation_rate, row.precision("valuation_rate")),
				"custom_feature": row.custom_feature
			}
		)

		if not row.batch_no:
			data.qty_after_transaction = flt(row.qty, row.precision("qty"))

		dimensions = get_inventory_dimensions()
		has_dimensions = False
		for dimension in dimensions:
			if row.get(dimension.get("fieldname")):
				has_dimensions = True

		if self.docstatus == 2 and (not row.batch_no or not row.serial_and_batch_bundle):
			if row.current_qty and current_bundle:
				data.actual_qty = -1 * row.current_qty
				data.qty_after_transaction = flt(row.current_qty)
				data.previous_qty_after_transaction = flt(row.qty)
				data.valuation_rate = flt(row.current_valuation_rate)
				data.serial_and_batch_bundle = row.current_serial_and_batch_bundle
				data.stock_value = data.qty_after_transaction * data.valuation_rate
				data.stock_value_difference = -1 * flt(row.amount_difference)
			else:
				data.actual_qty = row.qty
				data.qty_after_transaction = 0.0
				data.serial_and_batch_bundle = row.serial_and_batch_bundle
				data.valuation_rate = flt(row.valuation_rate)
				data.stock_value_difference = -1 * flt(row.amount_difference)

		elif self.docstatus == 1 and has_dimensions and (not row.batch_no or not row.serial_and_batch_bundle):
			data.actual_qty = row.qty
			data.qty_after_transaction = 0.0
			data.incoming_rate = flt(row.valuation_rate)

		self.update_inventory_dimensions(row, data)

		return data

	def recalculate_current_qty(self, voucher_detail_no):
		from erpnext.stock.stock_ledger import get_valuation_rate

		for row in self.items:
			if voucher_detail_no != row.name:
				continue

			val_rate = 0.0
			current_qty = 0.0
			if row.current_serial_and_batch_bundle:
				current_qty = self.get_current_qty_for_serial_or_batch(row)
			elif row.serial_no:
				item_dict = get_stock_balance_for(
					row.item_code,
					row.warehouse,
					self.posting_date,
					self.posting_time,
					row=row,
					custom_feature=row.custom_feature,
				)

				current_qty = item_dict.get("qty")
				row.current_serial_no = item_dict.get("serial_nos")
				row.current_valuation_rate = item_dict.get("rate")
				val_rate = item_dict.get("rate")
			elif row.batch_no:
				current_qty = get_batch_qty_for_stock_reco(
					row.item_code,
					row.warehouse,
					row.batch_no,
					self.posting_date,
					self.posting_time,
					self.name,
				)

			precesion = row.precision("current_qty")
			if flt(current_qty, precesion) != flt(row.current_qty, precesion):
				if not row.serial_no:
					val_rate = get_incoming_rate(
						frappe._dict(
							{
								"item_code": row.item_code,
								"warehouse": row.warehouse,
								"qty": current_qty * -1,
								"serial_and_batch_bundle": row.current_serial_and_batch_bundle,
								"batch_no": row.batch_no,
								"voucher_type": self.doctype,
								"voucher_no": self.name,
								"company": self.company,
								"posting_date": self.posting_date,
								"posting_time": self.posting_time,
								"custom_feature": row.custom_feature
							}
						)
					)

				row.current_valuation_rate = val_rate
				row.current_qty = current_qty
				row.db_set(
					{
						"current_qty": row.current_qty,
						"current_valuation_rate": row.current_valuation_rate,
						"current_amount": flt(row.current_qty * row.current_valuation_rate),
					}
				)


@frappe.whitelist()
def get_items(warehouse, posting_date, posting_time, company, item_code=None, ignore_empty_stock=False):
	ignore_empty_stock = cint(ignore_empty_stock)
	items = []
	if item_code and warehouse:
		items = get_item_and_warehouses(item_code, warehouse)

	if not item_code:
		items = get_items_for_stock_reco(warehouse, company)

	res = []
	itemwise_batch_data = get_itemwise_batch(warehouse, posting_date, company, item_code)

	for d in items:
		if d.item_code in itemwise_batch_data:
			valuation_rate = get_stock_balance(
				d.item_code, d.warehouse,  posting_date, posting_time, custom_feature=d.custom_feature, with_valuation_rate=True
			)[1]

			for row in itemwise_batch_data.get(d.item_code):
				if ignore_empty_stock and not row.qty:
					continue

				args = get_item_data(row, row.qty, valuation_rate)
				res.append(args)
		else:
			stock_bal = get_stock_balance(
				d.item_code,
				d.warehouse,
				posting_date,
				posting_time,
				custom_feature=d.custom_feature,
				with_valuation_rate=True,
				with_serial_no=cint(d.has_serial_no),
			)
			qty, valuation_rate, serial_no = (
				stock_bal[0],
				stock_bal[1],
				stock_bal[2] if cint(d.has_serial_no) else "",
			)

			if ignore_empty_stock and not stock_bal[0]:
				continue

			args = get_item_data(d, qty, valuation_rate, serial_no)

			res.append(args)

	return res


def get_items_for_stock_reco(warehouse, company):
	lft, rgt = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt"])
	items = frappe.db.sql(
		f"""
		select
			i.name as item_code, i.item_name, bin.custom_feature as custom_feature, bin.warehouse as warehouse, i.has_serial_no, i.has_batch_no, i.stock_uom
		from
			`tabBin` bin, `tabItem` i
		where
			i.name = bin.item_code
			and IFNULL(i.disabled, 0) = 0
			and i.is_stock_item = 1
			and i.has_variants = 0
			and exists(
				select name from `tabWarehouse` where lft >= {lft} and rgt <= {rgt} and name = bin.warehouse and is_group = 0
			)
	""",
		as_dict=1,
	)

	items += frappe.db.sql(
		"""
		select
			i.name as item_code, i.item_name, id.default_warehouse as warehouse, i.has_serial_no, i.has_batch_no, i.stock_uom
		from
			`tabItem` i, `tabItem Default` id
		where
			i.name = id.parent
			and exists(
				select name from `tabWarehouse` where lft >= %s and rgt <= %s and name=id.default_warehouse and is_group = 0
			)
			and i.is_stock_item = 1
			and i.has_variants = 0
			and IFNULL(i.disabled, 0) = 0
			and id.company = %s
		group by i.name
	""",
		(lft, rgt, company),
		as_dict=1,
	)

	# remove duplicates
	# check if item-warehouse key extracted from each entry exists in set iw_keys
	# and update iw_keys
	iw_keys = set()
	items = [
		item
		for item in items
		if [
			(item.item_code + (item.custom_feature if item.custom_feature else ""), item.warehouse) not in iw_keys,
			iw_keys.add((item.item_code + (item.custom_feature if item.custom_feature else ""), item.warehouse)),
		][0]
	]

	return items


def get_item_data(row, qty, valuation_rate, serial_no=None):
	roles = frappe.get_roles(frappe.session.user)

	if "System Manager" in roles:
		return {
			"item_code": row.item_code,
			"warehouse": row.warehouse,
			"qty": qty,
			"custom_feature": row.custom_feature,
			"item_name": row.item_name,
			"valuation_rate": valuation_rate,
			"current_qty": qty,
			"current_valuation_rate": valuation_rate,
			"current_serial_no": serial_no,
			"serial_no": serial_no,
			"stock_uom": row.stock_uom,
			"batch_no": row.get("batch_no"),
		}
	else:
		return {
			"item_code": row.item_code,
			"warehouse": row.warehouse,
			"qty": 0,
			"custom_feature": row.custom_feature,
			"item_name": row.item_name,
			"valuation_rate": valuation_rate,
			"current_qty": 0,
			"current_valuation_rate": valuation_rate,
			"current_serial_no": serial_no,
			"serial_no": serial_no,
			"stock_uom": row.stock_uom,
			"batch_no": row.get("batch_no"),
		}

@frappe.whitelist()
def get_stock_balance_for(
	item_code: str,
	warehouse: str,
	posting_date,
	posting_time,
	batch_no: str | None = None,
	with_valuation_rate: bool = True,
	inventory_dimensions_dict=None,
	row=None,
	custom_feature=None,
):
	frappe.has_permission("Stock Reconciliation", "write", throw=True)

	item_dict = frappe.get_cached_value("Item", item_code, ["has_serial_no", "has_batch_no"], as_dict=1)

	if isinstance(row, str):
		row = json.loads(row)

	if isinstance(row, dict):
		row = frappe._dict(row)

	if not item_dict:
		# In cases of data upload to Items table
		msg = _("Item {} does not exist.").format(item_code)
		frappe.throw(msg, title=_("Missing"))

	serial_nos = None
	has_serial_no = bool(item_dict.get("has_serial_no"))
	has_batch_no = bool(item_dict.get("has_batch_no"))

	use_serial_batch_fields = frappe.db.get_single_value("Stock Settings", "use_serial_batch_fields")

	if not batch_no and has_batch_no:
		# Not enough information to fetch data
		return {
			"qty": 0,
			"rate": 0,
			"serial_nos": None,
			"use_serial_batch_fields": row.use_serial_batch_fields if row else use_serial_batch_fields,
		}

	# TODO: fetch only selected batch's values
	data = get_stock_balance(
		item_code,
		warehouse,
		posting_date,
		posting_time,
		custom_feature,
		with_valuation_rate=with_valuation_rate,
		with_serial_no=has_serial_no,
		inventory_dimensions_dict=inventory_dimensions_dict,
	)

	if has_serial_no:
		qty, rate, serial_nos = data
	else:
		qty, rate = data

	if item_dict.get("has_batch_no"):
		qty = (
			get_batch_qty(
				batch_no,
				warehouse,
				posting_date=posting_date,
				posting_time=posting_time,
				for_stock_levels=True,
			)
			or 0
		)

	return {
		"qty": qty,
		"rate": rate,
		"serial_nos": serial_nos,
		"use_serial_batch_fields": row.use_serial_batch_fields if row else use_serial_batch_fields,
	}


