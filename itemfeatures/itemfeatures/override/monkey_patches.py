import frappe
from frappe import _
import erpnext
from sales_and_purchase_returns import get_return_against_item_fields, get_filters
from frappe.utils import cint, flt, format_datetime, now, nowtime, get_link_to_form
from frappe.query_builder.functions import Sum
from erpnext.accounts.utils import cancel_exchange_gain_loss_journal, get_fiscal_year
from erpnext.stock.stock_balance import (
	repost_actual_qty,
	get_reserved_qty,
	get_indented_qty,
	get_ordered_qty,
	get_planned_qty,
	get_balance_qty_from_sle
)
from erpnext.stock.utils import (
	get_combine_datetime,
	get_incoming_rate,
	get_or_make_bin,
	get_valuation_method,
)

from erpnext.stock.doctype.bin.bin import update_qty as update_bin_qty

from erpnext.stock.stock_ledger import (
	is_internal_transfer, 
	get_incoming_rate_for_inter_company_transfer, 
	NegativeStockError, 
	get_stock_reco_qty_shift,
	get_datetime_limit_condition,
	validate_negative_qty_in_future_sle
)

def update_bin_on_delete(row, doctype):
	"""Update bin for deleted item (row)."""
	from erpnext.stock.stock_balance import (
		get_indented_qty,
		get_ordered_qty,
		get_reserved_qty,
		update_bin_qty,
	)

	qty_dict = {}

	if doctype == "Sales Order":
		qty_dict["reserved_qty"] = get_reserved_qty(row.item_code, row.warehouse)
	else:
		if row.material_request_item:
			qty_dict["indented_qty"] = get_indented_qty(row.item_code, row.warehouse)

		qty_dict["ordered_qty"] = get_ordered_qty(row.item_code, row.warehouse)

	if row.warehouse:
		update_bin_qty(row.item_code, row.warehouse, qty_dict, feature=row.custom_feature)
		


def set_rate_for_standalone_debit_note(self):
    if self.get("is_return") and self.get("update_stock") and not self.return_against:
        for row in self.items:
            if row.rate <= 0:
                # override the rate with valuation rate
                row.rate = get_incoming_rate(
                    {
                        "item_code": row.item_code,
                        "warehouse": row.warehouse,
                        "posting_date": self.get("posting_date"),
                        "posting_time": self.get("posting_time"),
                        "qty": row.qty,
                        "serial_and_batch_bundle": row.get("serial_and_batch_bundle"),
                        "company": self.company,
                        "voucher_type": self.doctype,
                        "voucher_no": self.name,
                        "voucher_detail_no": row.name,
                        "custom_feature": row.custom_feature
                    },
                    raise_error_if_no_rate=False,
                )

                row.discount_percentage = 0.0
                row.discount_amount = 0.0
                row.margin_rate_or_amount = 0.0


def get_rate_for_return(
	voucher_type,
	voucher_no,
	item_code,
	return_against=None,
	item_row=None,
	voucher_detail_no=None,
	sle=None,
):
	if not return_against:
		return_against = frappe.get_cached_value(voucher_type, voucher_no, "return_against")

	return_against_item_field = get_return_against_item_fields(voucher_type)

	filters = get_filters(
		voucher_type,
		voucher_no,
		voucher_detail_no,
		return_against,
		item_code,
		return_against_item_field,
		item_row,
	)

	if voucher_type in ("Purchase Receipt", "Purchase Invoice", "Subcontracting Receipt"):
		select_field = "incoming_rate"
	else:
		select_field = "abs(stock_value_difference / actual_qty)"

	rate = flt(frappe.db.get_value("Stock Ledger Entry", filters, select_field))
	if not (rate and return_against) and voucher_type in ["Sales Invoice", "Delivery Note"]:
		rate = frappe.db.get_value(f"{voucher_type} Item", voucher_detail_no, "incoming_rate")

		if not rate and sle:
			rate = get_incoming_rate(
				{
					"item_code": sle.item_code,
					"warehouse": sle.warehouse,
					"posting_date": sle.get("posting_date"),
					"posting_time": sle.get("posting_time"),
					"qty": sle.actual_qty,
					"serial_and_batch_bundle": sle.get("serial_and_batch_bundle"),
					"company": sle.company,
					"voucher_type": sle.voucher_type,
					"voucher_no": sle.voucher_no,
					"custom_feature": sle.custom_feature,
				},
				raise_error_if_no_rate=False,
			)

	return rate

def set_incoming_rate(self):
    if self.doctype not in ("Delivery Note", "Sales Invoice"):
        return

    allow_at_arms_length_price = frappe.get_cached_value(
        "Stock Settings", None, "allow_internal_transfer_at_arms_length_price"
    )
    items = self.get("items") + (self.get("packed_items") or [])
    for d in items:
        if not frappe.get_cached_value("Item", d.item_code, "is_stock_item"):
            continue

        if not self.get("return_against") or (
            get_valuation_method(d.item_code) == "Moving Average" and self.get("is_return")
        ):
            # Get incoming rate based on original item cost based on valuation method
            qty = flt(d.get("stock_qty") or d.get("actual_qty") or d.get("qty"))

            if (
                not d.incoming_rate
                or self.is_internal_transfer()
                or (get_valuation_method(d.item_code) == "Moving Average" and self.get("is_return"))
            ):
                d.incoming_rate = get_incoming_rate(
                    {
                        "item_code": d.item_code,
                        "warehouse": d.warehouse,
                        "posting_date": self.get("posting_date") or self.get("transaction_date"),
                        "posting_time": self.get("posting_time") or nowtime(),
                        "qty": qty if cint(self.get("is_return")) else (-1 * qty),
                        "serial_and_batch_bundle": d.serial_and_batch_bundle,
                        "company": self.company,
                        "voucher_type": self.doctype,
                        "voucher_no": self.name,
                        "voucher_detail_no": d.name,
                        "allow_zero_valuation": d.get("allow_zero_valuation"),
                        "batch_no": d.batch_no,
                        "serial_no": d.serial_no,
                        "custom_feature": d.custom_feature	
                    },
                    raise_error_if_no_rate=False,
                )

            if (
                not d.incoming_rate
                and self.get("return_against")
                and self.get("is_return")
                and get_valuation_method(d.item_code) == "Moving Average"
            ):
                d.incoming_rate = get_rate_for_return(
                    self.doctype, self.name, d.item_code, self.return_against, item_row=d
                )

            # For internal transfers use incoming rate as the valuation rate
            if self.is_internal_transfer():
                if self.doctype == "Delivery Note" or self.get("update_stock"):
                    if d.doctype == "Packed Item":
                        incoming_rate = flt(
                            flt(d.incoming_rate, d.precision("incoming_rate")) * d.conversion_factor,
                            d.precision("incoming_rate"),
                        )
                        if d.incoming_rate != incoming_rate:
                            d.incoming_rate = incoming_rate
                    else:
                        if allow_at_arms_length_price:
                            continue

                        rate = flt(
                            flt(d.incoming_rate, d.precision("incoming_rate")) * d.conversion_factor,
                            d.precision("rate"),
                        )
                        if d.rate != rate:
                            d.rate = rate
                            frappe.msgprint(
                                _(
                                    "Row {0}: Item rate has been updated as per valuation rate since its an internal stock transfer"
                                ).format(d.idx),
                                alert=1,
                            )

                        d.discount_percentage = 0.0
                        d.discount_amount = 0.0
                        d.margin_rate_or_amount = 0.0

        elif self.get("return_against"):
            # Get incoming rate of return entry from reference document
            # based on original item cost as per valuation method
            d.incoming_rate = get_rate_for_return(
                self.doctype, self.name, d.item_code, self.return_against, item_row=d
            )

def get_sl_entries(self, d, args):
    sl_dict = frappe._dict(
        {
            "item_code": d.get("item_code", None),
            "warehouse": d.get("warehouse", None),
            "custom_feature": d.get("custom_feature", None),
            "serial_and_batch_bundle": d.get("serial_and_batch_bundle"),
            "posting_date": self.posting_date,
            "posting_time": self.posting_time,
            "fiscal_year": get_fiscal_year(self.posting_date, company=self.company)[0],
            "voucher_type": self.doctype,
            "voucher_no": self.name,
            "voucher_detail_no": d.name,
            "actual_qty": (self.docstatus == 1 and 1 or -1) * flt(d.get("stock_qty")),
            "stock_uom": frappe.get_cached_value(
                "Item", args.get("item_code") or d.get("item_code"), "stock_uom"
            ),
            "incoming_rate": 0,
            "company": self.company,
            "project": d.get("project") or self.get("project"),
            "is_cancelled": 1 if self.docstatus == 2 else 0,
        }
    )

    sl_dict.update(args)
    self.update_inventory_dimensions(d, sl_dict)

    if self.docstatus == 2:
        # To handle denormalized serial no records, will br deprecated in v16
        for field in ["serial_no", "batch_no"]:
            if d.get(field):
                sl_dict[field] = d.get(field)

    return sl_dict


def future_sle_exists(args, sl_entries=None, allow_force_reposting=True):
	if allow_force_reposting and frappe.db.get_single_value(
		"Stock Reposting Settings", "do_reposting_for_each_stock_transaction"
	):
		return True

	key = (args.voucher_type, args.voucher_no)
	if not hasattr(frappe.local, "future_sle"):
		frappe.local.future_sle = {}

	if validate_future_sle_not_exists(args, key, sl_entries):
		return False
	elif get_cached_data(args, key):
		return True

	if not sl_entries:
		sl_entries = get_sle_entries_against_voucher(args)
		if not sl_entries:
			return

	or_conditions = get_conditions_to_validate_future_sle(sl_entries)

	data = frappe.db.sql(
		"""
		select item_code, warehouse, custom_feature, count(name) as total_row
		from `tabStock Ledger Entry` force index (item_warehouse)
		where
			({})
			and timestamp(posting_date, posting_time)
				>= timestamp(%(posting_date)s, %(posting_time)s)
			and voucher_no != %(voucher_no)s
			and is_cancelled = 0
		GROUP BY
			item_code, warehouse, custom_feature
		""".format(" or ".join(or_conditions)),
		args,
		as_dict=1,
	)

	for d in data:
		frappe.local.future_sle[key][(d.item_code, d.warehouse, d.custom_feature)] = d.total_row

	return len(data)


def validate_future_sle_not_exists(args, key, sl_entries=None):
	item_key = ""
	if args.get("item_code"):
		item_key = (args.get("item_code"), args.get("warehouse"), args.get("custom_feature", None))

	if not sl_entries and hasattr(frappe.local, "future_sle"):
		if key not in frappe.local.future_sle:
			return False

		if not frappe.local.future_sle.get(key) or (
			item_key and item_key not in frappe.local.future_sle.get(key)
		):
			return True


def get_cached_data(args, key):
	if key not in frappe.local.future_sle:
		frappe.local.future_sle[key] = frappe._dict({})

	if args.get("item_code"):
		item_key = (args.get("item_code"), args.get("warehouse"), args.get("custom_feature", None))
		count = frappe.local.future_sle[key].get(item_key)

		return True if (count or count == 0) else False
	else:
		return frappe.local.future_sle[key]


def get_sle_entries_against_voucher(args):
	return frappe.get_all(
		"Stock Ledger Entry",
		filters={"voucher_type": args.voucher_type, "voucher_no": args.voucher_no},
		fields=["item_code", "warehouse", "custom_feature"],
		order_by="creation asc",
	)


def get_conditions_to_validate_future_sle(sl_entries):
    warehouse_items_map = {}
    
    for entry in sl_entries:
        if entry.warehouse not in warehouse_items_map:
            warehouse_items_map[entry.warehouse] = []

        warehouse_items_map[entry.warehouse].append({
            "item_code": entry.item_code,
            "feature": entry.custom_feature
        })

    or_conditions = []
    for warehouse, items in warehouse_items_map.items():
        item_conditions = []
        for item in items:
            if item["feature"]:  # If value is present
                item_conditions.append(
                    f"""(item_code = {frappe.db.escape(item["item_code"])}
                        and custom_feature = {frappe.db.escape(item["feature"])})"""
                )
            else:  # If value is empty
                item_conditions.append(
                    f"""(item_code = {frappe.db.escape(item["item_code"])}
                        and (custom_feature IS NULL OR custom_feature = ''))"""
                )

        or_conditions.append(
            f"""warehouse = {frappe.db.escape(warehouse)}
                and ({' OR '.join(item_conditions)})"""
        )

    return or_conditions



def repost(only_actual=False, allow_negative_stock=False, allow_zero_rate=False, only_bin=False):
	"""
	Repost everything!
	"""
	frappe.db.auto_commit_on_many_writes = 1

	if allow_negative_stock:
		existing_allow_negative_stock = frappe.db.get_value("Stock Settings", None, "allow_negative_stock")
		frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 1)

	item_warehouses = frappe.db.sql(
		"""
		select distinct item_code, warehouse, custom_feature
		from
			(select item_code, warehouse, custom_feature from tabBin
			union
			select item_code, warehouse, custom_feature from `tabStock Ledger Entry`) a
	"""
	)
	for d in item_warehouses:
		try:
			repost_stock(d[0], d[1], d[2], allow_zero_rate, only_actual, only_bin, allow_negative_stock,)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()

	if allow_negative_stock:
		frappe.db.set_single_value("Stock Settings", "allow_negative_stock", existing_allow_negative_stock)
	frappe.db.auto_commit_on_many_writes = 0


def repost_stock(
	item_code,
	warehouse,
	custom_feature,
	allow_zero_rate=False,
	only_actual=False,
	only_bin=False,
	allow_negative_stock=False,
):
	if not only_bin:
		repost_actual_qty(item_code, warehouse, allow_zero_rate, allow_negative_stock)

	if item_code and warehouse and not only_actual:
		qty_dict = {
			"reserved_qty": get_reserved_qty(item_code, warehouse),
			"indented_qty": get_indented_qty(item_code, warehouse),
			"ordered_qty": get_ordered_qty(item_code, warehouse),
			"planned_qty": get_planned_qty(item_code, warehouse),
		}
		if only_bin:
			qty_dict.update({"actual_qty": get_balance_qty_from_sle(item_code, warehouse)})

		update_bin_qty(item_code, warehouse, qty_dict, feature=custom_feature)


def update_bin_qty(item_code, warehouse, qty_dict=None, feature=None):
	from erpnext.stock.utils import get_bin

	bin = get_bin(item_code, warehouse, feature)
	mismatch = False
	for field, value in qty_dict.items():
		if flt(bin.get(field)) != flt(value):
			bin.set(field, flt(value))
			mismatch = True

	bin.modified = now()
	if mismatch:
		bin.set_projected_qty()
		bin.db_update()
		bin.clear_cache()
		

def get_sle_against_current_voucher(self):
    self.args["posting_datetime"] = get_combine_datetime(self.args.posting_date, self.args.posting_time)

    feature_condition = " and (custom_feature is null or custom_feature = '') "
    if self.args.get("custom_feature"):
        feature = self.args.get("custom_feature")
        feature_condition = f" and custom_feature = '{feature}'"

    return frappe.db.sql(
        f"""
        select
            *, posting_datetime as "timestamp"
        from
            `tabStock Ledger Entry`
        where
            item_code = %(item_code)s
            and warehouse = %(warehouse)s
            {feature_condition}
            and is_cancelled = 0
            and (
                posting_datetime = %(posting_datetime)s
            )
            and creation = %(creation)s
        order by
            creation ASC
        for update
    """,
        self.args,
        as_dict=1,
    )


def get_incoming_outgoing_rate_from_transaction(self, sle):
    rate = 0
    # Material Transfer, Repack, Manufacturing
    if sle.voucher_type == "Stock Entry":
        self.recalculate_amounts_in_stock_entry(sle.voucher_no, sle.voucher_detail_no)
        rate = frappe.db.get_value("Stock Entry Detail", sle.voucher_detail_no, "valuation_rate")
    # Sales and Purchase Return
    elif sle.voucher_type in (
        "Purchase Receipt",
        "Purchase Invoice",
        "Delivery Note",
        "Sales Invoice",
        "Subcontracting Receipt",
    ):
        if frappe.get_cached_value(sle.voucher_type, sle.voucher_no, "is_return"):
            from erpnext.controllers.sales_and_purchase_return import (
                get_rate_for_return,  # don't move this import to top
            )

            if (
                self.valuation_method == "Moving Average"
                and not sle.get("serial_no")
                and not sle.get("batch_no")
                and not sle.get("serial_and_batch_bundle")
            ):
                rate = get_incoming_rate(
                    {
                        "item_code": sle.item_code,
                        "warehouse": sle.warehouse,
                        "posting_date": sle.posting_date,
                        "posting_time": sle.posting_time,
                        "qty": sle.actual_qty,
                        "serial_no": sle.get("serial_no"),
                        "batch_no": sle.get("batch_no"),
                        "serial_and_batch_bundle": sle.get("serial_and_batch_bundle"),
                        "company": sle.company,
                        "voucher_type": sle.voucher_type,
                        "voucher_no": sle.voucher_no,
                        "allow_zero_valuation": self.allow_zero_rate,
                        "sle": sle.name,
                        "custom_feature": sle.custom_feature,
                    }
                )

                if not rate and sle.voucher_type in ["Delivery Note", "Sales Invoice"]:
                    rate = get_rate_for_return(
                        sle.voucher_type,
                        sle.voucher_no,
                        sle.item_code,
                        voucher_detail_no=sle.voucher_detail_no,
                        sle=sle,
                    )

            else:
                rate = get_rate_for_return(
                    sle.voucher_type,
                    sle.voucher_no,
                    sle.item_code,
                    voucher_detail_no=sle.voucher_detail_no,
                    sle=sle,
                )

            if (
                sle.get("serial_and_batch_bundle")
                and rate > 0
                and sle.voucher_type in ["Delivery Note", "Sales Invoice"]
            ):
                frappe.db.set_value(
                    sle.voucher_type + " Item",
                    sle.voucher_detail_no,
                    "incoming_rate",
                    rate,
                )
        elif (
            sle.voucher_type in ["Purchase Receipt", "Purchase Invoice"]
            and sle.voucher_detail_no
            and is_internal_transfer(sle)
        ):
            rate = get_incoming_rate_for_inter_company_transfer(sle)
        else:
            if sle.voucher_type in ("Purchase Receipt", "Purchase Invoice"):
                rate_field = "valuation_rate"
            elif sle.voucher_type == "Subcontracting Receipt":
                rate_field = "rate"
            else:
                rate_field = "incoming_rate"

            # check in item table
            item_code, incoming_rate = frappe.db.get_value(
                sle.voucher_type + " Item", sle.voucher_detail_no, ["item_code", rate_field]
            )

            if item_code == sle.item_code:
                rate = incoming_rate
            else:
                if sle.voucher_type in ("Delivery Note", "Sales Invoice"):
                    ref_doctype = "Packed Item"
                elif sle == "Subcontracting Receipt":
                    ref_doctype = "Subcontracting Receipt Supplied Item"
                else:
                    ref_doctype = "Purchase Receipt Item Supplied"

                rate = frappe.db.get_value(
                    ref_doctype,
                    {"parent_detail_docname": sle.voucher_detail_no, "item_code": sle.item_code},
                    rate_field,
                )

    return rate

def get_fallback_rate(self, sle) -> float:
    """When exact incoming rate isn't available use any of other "average" rates as fallback.
    This should only get used for negative stock."""
    return get_valuation_rate(
        sle.item_code,
        sle.warehouse,
        sle.voucher_type,
        sle.voucher_no,
        self.allow_zero_rate,
        custom_feature=sle.custom_feature,
        currency=erpnext.get_company_currency(sle.company),
        company=sle.company,
    )


def raise_exceptions(self):
    msg_list = []
    for warehouse, exceptions in self.exceptions.items():
        deficiency = min(e["diff"] for e in exceptions)
        feature = ""

        if exceptions[0]["custom_feature"]:
            feature = exceptions[0]["custom_feature"]

        if (
            exceptions[0]["voucher_type"],
            exceptions[0]["voucher_no"],
        ) in frappe.local.flags.currently_saving:
            msg = _("{0} units of {1} needed in {2} to complete this transaction.").format(
                frappe.bold(abs(deficiency)),
                frappe.get_desk_link("Item", exceptions[0]["item_code"]) + " " + feature,
                frappe.get_desk_link("Warehouse", warehouse),
            )
        else:
            msg = _(
                "{0} units of {1} needed in {2} on {3} {4} for {5} to complete this transaction."
            ).format(
                frappe.bold(abs(deficiency)),
                frappe.get_desk_link("Item", exceptions[0]["item_code"]),
                frappe.get_desk_link("Warehouse", warehouse),
                exceptions[0]["posting_date"],
                exceptions[0]["posting_time"],
                frappe.get_desk_link(exceptions[0]["voucher_type"], exceptions[0]["voucher_no"]),
            )

        if msg:
            if self.reserved_stock:
                allowed_qty = abs(exceptions[0]["actual_qty"]) - abs(exceptions[0]["diff"])

                if allowed_qty > 0:
                    msg = "{} As {} units are reserved for other sales orders, you are allowed to consume only {} units.".format(
                        msg, frappe.bold(self.reserved_stock), frappe.bold(allowed_qty)
                    )
                else:
                    msg = f"{msg} As the full stock is reserved for other sales orders, you're not allowed to consume the stock."

            msg_list.append(msg)

    if msg_list:
        message = "\n\n".join(msg_list)
        if self.verbose:
            frappe.throw(message, NegativeStockError, title=_("Insufficient Stock"))
        else:
            raise NegativeStockError(message)

def update_bin(self):
    # update bin for each warehouse
    for warehouse, data in self.data.items():
        bin_name = get_or_make_bin(self.item_code, warehouse, self.args.get("custom_feature", None))

        updated_values = {"actual_qty": data.qty_after_transaction, "stock_value": data.stock_value}
        if data.valuation_rate is not None:
            updated_values["valuation_rate"] = data.valuation_rate
        frappe.db.set_value("Bin", bin_name, updated_values, update_modified=True)


def get_previous_sle_of_current_voucher(args, operator="<", exclude_current_voucher=False):
	"""get stock ledger entries filtered by specific posting datetime conditions"""

	if not args.get("posting_date"):
		args["posting_datetime"] = "1900-01-01 00:00:00"

	if not args.get("posting_datetime"):
		args["posting_datetime"] = get_combine_datetime(args["posting_date"], args["posting_time"])

	feature_condition = " and (custom_feature is null or custom_feature = '') "
	if args.get("custom_feature"):
		feature = args.get("custom_feature")
		feature_condition = f" and custom_feature = '{feature}'"


	voucher_condition = ""
	if exclude_current_voucher:
		voucher_no = args.get("voucher_no")
		voucher_condition = f"and voucher_no != '{voucher_no}'"

	elif args.get("creation") and args.get("sle_id"):
		creation = args.get("creation")
		operator = "<="
		voucher_condition = f"and creation < '{creation}'"

	sle = frappe.db.sql(  # nosemgrep
		f"""
		select *, posting_datetime as "timestamp"
		from `tabStock Ledger Entry`
		where item_code = %(item_code)s
			and warehouse = %(warehouse)s
			{feature_condition}
			and is_cancelled = 0
			{voucher_condition}
			and (
				posting_datetime {operator} %(posting_datetime)s
			)
		order by posting_date desc, posting_time desc, creation desc
		limit 1
		for update""",
		{
			"item_code": args.get("item_code"),
			"warehouse": args.get("warehouse"),
			"posting_datetime": args.get("posting_datetime"),
		},
		as_dict=1,
	)

	return sle[0] if sle else frappe._dict()

def get_stock_ledger_entries(
	previous_sle,
	operator=None,
	order="desc",
	limit=None,
	for_update=False,
	debug=False,
	check_serial_no=True,
	extra_cond=None,
):
	"""get stock ledger entries filtered by specific posting datetime conditions"""
	conditions = f" and posting_datetime {operator} %(posting_datetime)s"
	if previous_sle.get("warehouse"):
		conditions += " and warehouse = %(warehouse)s"
	elif previous_sle.get("warehouse_condition"):
		conditions += " and " + previous_sle.get("warehouse_condition")

	if check_serial_no and previous_sle.get("serial_no"):
		# conditions += " and serial_no like {}".format(frappe.db.escape('%{0}%'.format(previous_sle.get("serial_no"))))
		serial_no = previous_sle.get("serial_no")
		conditions += (
			""" and
			(
				serial_no = {}
				or serial_no like {}
				or serial_no like {}
				or serial_no like {}
			)
		"""
		).format(
			frappe.db.escape(serial_no),
			frappe.db.escape(f"{serial_no}\n%"),
			frappe.db.escape(f"%\n{serial_no}"),
			frappe.db.escape(f"%\n{serial_no}\n%"),
		)

	if not previous_sle.get("posting_date"):
		previous_sle["posting_datetime"] = "1900-01-01 00:00:00"
	else:
		posting_time = previous_sle.get("posting_time")
		if not posting_time:
			posting_time = "00:00:00"

		previous_sle["posting_datetime"] = get_combine_datetime(previous_sle["posting_date"], posting_time)

	if operator in (">", "<=") and previous_sle.get("name"):
		conditions += " and name!=%(name)s"

	if extra_cond:
		conditions += f"{extra_cond}"

	feature_condition = " and (custom_feature is null or custom_feature = '') "
	if previous_sle.get("custom_feature"):
		feature = previous_sle.get("custom_feature")
		feature_condition = f" and custom_feature = '{feature}'"
		
	# nosemgrep
	return frappe.db.sql(
		"""
		select *, posting_datetime as "timestamp"
		from `tabStock Ledger Entry`
		where item_code = %(item_code)s
		{feature_condition}
		and is_cancelled = 0
		{conditions}
		order by posting_date {order}, posting_time {order}, creation {order}
		{limit} {for_update}""".format(
			conditions=conditions,
			feature_condition = feature_condition,
			limit=limit or "",
			for_update=for_update and "for update" or "",
			order=order,
		),
		previous_sle,
		as_dict=1,
		debug=debug,
	)

def get_valuation_rate(
	item_code,
	warehouse,
	voucher_type,
	voucher_no,
	custom_feature=None,
	allow_zero_rate=False,
	currency=None,
	company=None,
	raise_error_if_no_rate=True,
	batch_no=None,
	serial_and_batch_bundle=None,
):
	from erpnext.stock.serial_batch_bundle import BatchNoValuation

	if not company:
		company = frappe.get_cached_value("Warehouse", warehouse, "company")

	if warehouse and batch_no and frappe.db.get_value("Batch", batch_no, "use_batchwise_valuation"):
		table = frappe.qb.DocType("Stock Ledger Entry")
		query = (
			frappe.qb.from_(table)
			.select(Sum(table.stock_value_difference) / Sum(table.actual_qty))
			.where(
				(table.item_code == item_code)
				& (table.warehouse == warehouse)
				& (table.batch_no == batch_no)
				& (table.is_cancelled == 0)
				& (table.voucher_no != voucher_no)
				& (table.voucher_type != voucher_type)
			)
		)

		last_valuation_rate = query.run()
		if last_valuation_rate:
			return flt(last_valuation_rate[0][0])

	# Get moving average rate of a specific batch number
	if warehouse and serial_and_batch_bundle:
		sabb = frappe.db.get_value(
			"Serial and Batch Bundle", serial_and_batch_bundle, ["posting_date", "posting_time"], as_dict=True
		)
		batch_obj = BatchNoValuation(
			sle=frappe._dict(
				{
					"item_code": item_code,
					"warehouse": warehouse,
					"actual_qty": -1,
					"serial_and_batch_bundle": serial_and_batch_bundle,
					"posting_date": sabb.posting_date,
					"posting_time": sabb.posting_time,
				}
			)
		)

		return batch_obj.get_incoming_rate()


	feature_condition = " and (custom_feature is null or custom_feature = '') "
	if custom_feature:
		feature_condition = f" and custom_feature = '{feature_condition}'"

	# Get valuation rate from last sle for the same item and warehouse
	if last_valuation_rate := frappe.db.sql(  # nosemgrep
		"""select valuation_rate
		from `tabStock Ledger Entry` force index (item_warehouse)
		where
			item_code = %s
			AND warehouse = %s
			%s
			AND valuation_rate >= 0
			AND is_cancelled = 0
			AND NOT (voucher_no = %s AND voucher_type = %s)
		order by posting_date desc, posting_time desc, name desc limit 1""",
		(item_code, warehouse, feature_condition, voucher_no, voucher_type),
	):
		return flt(last_valuation_rate[0][0])

	# If negative stock allowed, and item delivered without any incoming entry,
	# system does not found any SLE, then take valuation rate from Item
	valuation_rate = frappe.db.get_value("Item", item_code, "valuation_rate")

	if not valuation_rate:
		# try Item Standard rate
		valuation_rate = frappe.db.get_value("Item", item_code, "standard_rate")

		if not valuation_rate:
			# try in price list
			valuation_rate = frappe.db.get_value(
				"Item Price", dict(item_code=item_code, buying=1, currency=currency), "price_list_rate"
			)

	if (
		not allow_zero_rate
		and not valuation_rate
		and raise_error_if_no_rate
		and cint(erpnext.is_perpetual_inventory_enabled(company))
	):
		form_link = get_link_to_form("Item", item_code)

		message = _(
			"Valuation Rate for the Item {0}, is required to do accounting entries for {1} {2}."
		).format(form_link, voucher_type, voucher_no)
		message += "<br><br>" + _("Here are the options to proceed:")
		solutions = (
			"<li>"
			+ _(
				"If the item is transacting as a Zero Valuation Rate item in this entry, please enable 'Allow Zero Valuation Rate' in the {0} Item table."
			).format(voucher_type)
			+ "</li>"
		)
		solutions += (
			"<li>"
			+ _("If not, you can Cancel / Submit this entry")
			+ " {} ".format(frappe.bold("after"))
			+ _("performing either one below:")
			+ "</li>"
		)
		sub_solutions = "<ul><li>" + _("Create an incoming stock transaction for the Item.") + "</li>"
		sub_solutions += "<li>" + _("Mention Valuation Rate in the Item master.") + "</li></ul>"
		msg = message + solutions + sub_solutions + "</li>"

		frappe.throw(msg=msg, title=_("Valuation Rate Missing"))

	return valuation_rate

def update_qty_in_future_sle(args, allow_negative_stock=False):
	"""Recalculate Qty after Transaction in future SLEs based on current SLE."""
	datetime_limit_condition = ""
	qty_shift = args.actual_qty

	args["posting_datetime"] = get_combine_datetime(args["posting_date"], args["posting_time"])

	# find difference/shift in qty caused by stock reconciliation
	if args.voucher_type == "Stock Reconciliation":
		qty_shift = get_stock_reco_qty_shift(args)

	# find the next nearest stock reco so that we only recalculate SLEs till that point
	next_stock_reco_detail = get_next_stock_reco(args)
	if next_stock_reco_detail:
		detail = next_stock_reco_detail[0]
		datetime_limit_condition = get_datetime_limit_condition(detail)

	feature_condition = " and (custom_feature is null or custom_feature = '') "
	if args.get("custom_feature"):
		feature = args.get("custom_feature")
		feature_condition = f" and custom_feature = '{feature}'"

	frappe.db.sql(  # nosemgrep
		f"""
		update `tabStock Ledger Entry`
		set qty_after_transaction = qty_after_transaction + {qty_shift}
		where
			item_code = %(item_code)s
			and warehouse = %(warehouse)s
			{feature_condition}
			and voucher_no != %(voucher_no)s
			and is_cancelled = 0
			and (
				posting_datetime > %(posting_datetime)s
			)
			{datetime_limit_condition}
		""",
		args,
	)

	validate_negative_qty_in_future_sle(args, allow_negative_stock)

def get_next_stock_reco(kwargs):
	"""Returns next nearest stock reconciliaton's details."""

	sle = frappe.qb.DocType("Stock Ledger Entry")

	query = (
		frappe.qb.from_(sle)
		.select(
			sle.name,
			sle.posting_date,
			sle.custom_feature,
			sle.posting_time,
			sle.creation,
			sle.voucher_no,
			sle.item_code,
			sle.batch_no,
			sle.serial_and_batch_bundle,
			sle.actual_qty,
			sle.has_batch_no,
		)
		.force_index("item_warehouse")
		.where(
			(sle.item_code == kwargs.get("item_code"))
			& (sle.warehouse == kwargs.get("warehouse"))
			& (sle.voucher_type == "Stock Reconciliation")
			& (sle.voucher_no != kwargs.get("voucher_no"))
			& (sle.is_cancelled == 0)
			& (
				sle.posting_datetime
				>= get_combine_datetime(kwargs.get("posting_date"), kwargs.get("posting_time"))
			)
		)
		.orderby(sle.posting_datetime)
		.orderby(sle.creation)
		.limit(1)
	)

	if kwargs.get("batch_no"):
		query = query.where(sle.batch_no == kwargs.get("batch_no"))

	return query.run(as_dict=True)

def get_future_sle_with_negative_qty(sle_args):

	feature_condition = " and (custom_feature is null or custom_feature = '') "
	if sle_args.get("custom_feature"):
		feature = sle_args.get("custom_feature")
		feature_condition = f" and custom_feature = '{feature}'" 

	return frappe.db.sql(  # nosemgrep
		f"""
		select
			qty_after_transaction, posting_date, posting_time,
			voucher_type, voucher_no
		from `tabStock Ledger Entry`
		where
			item_code = %(item_code)s
			and warehouse = %(warehouse)s
			{feature_condition}
			and voucher_no != %(voucher_no)s
			and posting_datetime >= %(posting_datetime)s
			and is_cancelled = 0
			and qty_after_transaction < 0
		order by posting_date asc, posting_time asc
		limit 1
	""",
		sle_args,
		as_dict=1,
	)

def get_future_sle_with_negative_batch_qty(sle_args):
	
	feature_condition = " and (custom_feature is null or custom_feature = '') "
	if sle_args.get("custom_feature"):
		feature = sle_args.get("custom_feature")
		feature_condition = f" and custom_feature = '{feature}'"
	return frappe.db.sql(  # nosemgrep
		f"""
		with batch_ledger as (
			select
				posting_date, posting_time, posting_datetime, voucher_type, voucher_no,
				sum(actual_qty) over (order by posting_date, posting_time, creation) as cumulative_total
			from `tabStock Ledger Entry`
			where
				item_code = %(item_code)s
				and warehouse = %(warehouse)s
				{feature_condition}
				and batch_no=%(batch_no)s
				and is_cancelled = 0
			order by posting_date, posting_time, creation
		)
		select * from batch_ledger
		where
			cumulative_total < 0.0
			and posting_datetime >= %(posting_datetime)s
		limit 1
	""",
		sle_args,
		as_dict=1,
	)




def get_bin(item_code, warehouse, feature=None):
	if feature == "":
		feature = None
	bin = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse, "custom_feature": feature})
	if not bin:
		bin_obj = _create_bin(item_code, warehouse, feature)
	else:
		bin_obj = frappe.get_doc("Bin", bin)
	bin_obj.flags.ignore_permissions = True
	return bin_obj


def get_or_make_bin(item_code: str, warehouse: str, feature=None) -> str:

	if feature == "":
		feature = None
	bin_record = frappe.get_cached_value("Bin", {"item_code": item_code, "warehouse": warehouse, "custom_feature": feature})

	if not bin_record:
		bin_obj = _create_bin(item_code, warehouse, feature)
		bin_record = bin_obj.name
	return bin_record


def _create_bin(item_code, warehouse, feature=None):
	"""Create a bin and take care of concurrent inserts."""

	bin_creation_savepoint = "create_bin"
	if feature == "":
		feature = None

	try:
		frappe.db.savepoint(bin_creation_savepoint)
		bin_obj = frappe.get_doc(doctype="Bin", item_code=item_code, warehouse=warehouse, custom_feature=feature)
		bin_obj.flags.ignore_permissions = 1
		bin_obj.insert()
	except frappe.UniqueValidationError:
		frappe.db.rollback(save_point=bin_creation_savepoint)  # preserve transaction in postgres
		bin_obj = frappe.get_last_doc("Bin", {"item_code": item_code, "warehouse": warehouse, "custom_feature": feature})

	return bin_obj

