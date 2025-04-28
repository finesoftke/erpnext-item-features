import frappe
import json
from frappe.utils import cstr, flt, nowdate, nowtime
from erpnext.stock.utils import get_valuation_method, get_serial_nos_data, _get_fifo_lifo_rate

import erpnext
from erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle import (
	get_available_serial_nos,
)

from erpnext.stock.serial_batch_bundle import BatchNoValuation, SerialNoValuation

@frappe.whitelist()
def get_stock_balance(
	item_code,
	warehouse,
	posting_date=None,
	posting_time=None,
	custom_feature=None,
	with_valuation_rate=False,
	with_serial_no=False,
	inventory_dimensions_dict=None,
):
	"""Returns stock balance quantity at given warehouse on given posting date or current date.

	If `with_valuation_rate` is True, will return tuple (qty, rate)"""

	from erpnext.stock.stock_ledger import get_previous_sle

	if posting_date is None:
		posting_date = nowdate()
	if posting_time is None:
		posting_time = nowtime()

	args = {
		"item_code": item_code,
		"warehouse": warehouse,
		"posting_date": posting_date,
		"posting_time": posting_time,
	}

	if custom_feature:
		args["custom_feature"] = custom_feature

	extra_cond = ""
	if inventory_dimensions_dict:
		for field, value in inventory_dimensions_dict.items():
			args[field] = value
			extra_cond += f" and {field} = %({field})s"

	last_entry = get_previous_sle(args, extra_cond=extra_cond)

	if with_valuation_rate:
		if with_serial_no:
			serial_no_details = get_available_serial_nos(
				frappe._dict(
					{
						"item_code": item_code,
						"warehouse": warehouse,
						"posting_date": posting_date,
						"posting_time": posting_time,
						"ignore_warehouse": 1,
					}
				)
			)

			serial_nos = ""
			if serial_no_details:
				serial_nos = "\n".join(d.serial_no for d in serial_no_details)

			return (
				(last_entry.qty_after_transaction, last_entry.valuation_rate, serial_nos)
				if last_entry
				else (0.0, 0.0, None)
			)
		else:
			return (last_entry.qty_after_transaction, last_entry.valuation_rate) if last_entry else (0.0, 0.0)
	else:
		return last_entry.qty_after_transaction if last_entry else 0.0


@frappe.whitelist()
def get_incoming_rate(args, raise_error_if_no_rate=True):
	"""Get Incoming Rate based on valuation method"""
	from erpnext.stock.stock_ledger import get_previous_sle, get_valuation_rate

	if isinstance(args, str):
		args = json.loads(args)

	in_rate = None

	item_details = frappe.get_cached_value(
		"Item", args.get("item_code"), ["has_serial_no", "has_batch_no"], as_dict=1
	)

	use_moving_avg_for_batch = frappe.db.get_single_value("Stock Settings", "do_not_use_batchwise_valuation")

	if isinstance(args, dict):
		args = frappe._dict(args)

	if item_details and item_details.has_serial_no and args.get("serial_and_batch_bundle"):
		args.actual_qty = args.qty
		sn_obj = SerialNoValuation(
			sle=args,
			warehouse=args.get("warehouse"),
			item_code=args.get("item_code"),
		)

		return sn_obj.get_incoming_rate()

	elif (
		item_details
		and item_details.has_batch_no
		and args.get("serial_and_batch_bundle")
		and not use_moving_avg_for_batch
	):
		args.actual_qty = args.qty
		batch_obj = BatchNoValuation(
			sle=args,
			warehouse=args.get("warehouse"),
			item_code=args.get("item_code"),
		)

		return batch_obj.get_incoming_rate()

	elif (args.get("serial_no") or "").strip() and not args.get("serial_and_batch_bundle"):
		args.actual_qty = args.qty
		args.serial_nos = get_serial_nos_data(args.get("serial_no"))

		sn_obj = SerialNoValuation(sle=args, warehouse=args.get("warehouse"), item_code=args.get("item_code"))

		return sn_obj.get_incoming_rate()
	elif args.get("batch_no") and not args.get("serial_and_batch_bundle") and not use_moving_avg_for_batch:
		args.actual_qty = args.qty
		args.batch_nos = frappe._dict({args.batch_no: args})

		batch_obj = BatchNoValuation(
			sle=args,
			warehouse=args.get("warehouse"),
			item_code=args.get("item_code"),
		)

		return batch_obj.get_incoming_rate()
	else:
		valuation_method = get_valuation_method(args.get("item_code"))
		previous_sle = get_previous_sle(args)
		if valuation_method in ("FIFO", "LIFO"):
			if previous_sle:
				previous_stock_queue = json.loads(previous_sle.get("stock_queue", "[]") or "[]")
				in_rate = (
					_get_fifo_lifo_rate(previous_stock_queue, args.get("qty") or 0, valuation_method)
					if previous_stock_queue
					else None
				)
		elif valuation_method == "Moving Average":
			in_rate = previous_sle.get("valuation_rate")

	if in_rate is None:
		voucher_no = args.get("voucher_no") or args.get("name")
		in_rate = get_valuation_rate(
			args.get("item_code"),
			args.get("warehouse"),
			args.get("voucher_type"),
			voucher_no,
			args.get("allow_zero_valuation"),
			args.get("custom_feature", None),
			currency=erpnext.get_company_currency(args.get("company")),
			company=args.get("company"),
			raise_error_if_no_rate=raise_error_if_no_rate,
		)

	return flt(in_rate)

