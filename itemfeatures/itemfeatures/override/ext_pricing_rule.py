
import frappe;
from frappe import _, throw
from frappe.utils import cint, flt, getdate
import copy
import json
import re


from erpnext.accounts.doctype.pricing_rule.pricing_rule import PricingRule, apply_on_dict, other_fields, set_transaction_type, update_args_for_pricing_rule, update_pricing_rule_uom, remove_pricing_rule_for_item, get_pricing_rule_details, apply_price_discount_rule

class ExtPricingRule(PricingRule):
        
    def validate_mandatory(self):
        for apply_on, field in apply_on_dict.items():
            if self.apply_on == apply_on and len(self.get(field) or []) < 1:
                throw(_("{0} is not added in the table").format(apply_on), frappe.MandatoryError)

        tocheck = frappe.scrub(self.get("applicable_for", ""))
        if tocheck and not self.get(tocheck):
            throw(_("{0} is required").format(self.meta.get_label(tocheck)), frappe.MandatoryError)

        if self.apply_rule_on_other:
            o_field = "other_" + frappe.scrub(self.apply_rule_on_other)
            if not self.get(o_field) and o_field in other_fields:
                frappe.throw(
                    _("For the 'Apply Rule On Other' condition the field {0} is mandatory").format(
                        frappe.bold(self.apply_rule_on_other)
                    )
                )

        if (not self.apply_features_rule == 1) and (self.price_or_product_discount == "Price" and not self.rate_or_discount):
            throw(_("Rate or Discount is required for the price discount."), frappe.MandatoryError)

        if self.apply_discount_on_rate:
            if not self.priority:
                throw(
                    _("As the field {0} is enabled, the field {1} is mandatory.").format(
                        frappe.bold("Apply Discount on Discounted Rate"), frappe.bold("Priority")
                    )
                )

            if self.priority and cint(self.priority) == 1:
                throw(
                    _("As the field {0} is enabled, the value of the field {1} should be more than 1.").format(
                        frappe.bold("Apply Discount on Discounted Rate"), frappe.bold("Priority")
                    )
                )


@frappe.whitelist()
def apply_pricing_rule(args, doc=None):
    """
    args = {
            "items": [{"doctype": "", "name": "", "item_code": "", "brand": "", "item_group": ""}, ...],
            "customer": "something",
            "customer_group": "something",
            "territory": "something",
            "supplier": "something",
            "supplier_group": "something",
            "currency": "something",
            "conversion_rate": "something",
            "price_list": "something",
            "plc_conversion_rate": "something",
            "company": "something",
            "transaction_date": "something",
            "campaign": "something",
            "sales_partner": "something",
            "ignore_pricing_rule": "something"
    }
    """

    if isinstance(args, str):
        args = json.loads(args)

    args = frappe._dict(args)

    if not args.transaction_type:
        set_transaction_type(args)

    # list of dictionaries
    out = []

    if args.get("doctype") == "Material Request":
        return out

    item_list = args.get("items")
    args.pop("items")

    set_serial_nos_based_on_fifo = frappe.db.get_single_value(
        "Stock Settings", "automatically_set_serial_nos_based_on_fifo"
    )

    item_code_list = tuple(item.get("item_code") for item in item_list)
    query_items = frappe.get_all(
        "Item",
        fields=["item_code", "has_serial_no"],
        filters=[["item_code", "in", item_code_list]],
        as_list=1,
    )
    serialized_items = dict()
    for item_code, val in query_items:
        serialized_items.setdefault(item_code, val)

    for item in item_list:
        args_copy = copy.deepcopy(args)
        args_copy.update(item)
        data = get_pricing_rule_for_item_ext(args_copy, doc=doc)

        out.append(data)

        # if (
        #     serialized_items.get(item.get("item_code"))
        #     and not item.get("serial_no")
        #     and set_serial_nos_based_on_fifo
        #     and not args.get("is_return")
        # ):
        #     out[0].update(get_serial_no_for_item(args_copy))

    return out

def get_pricing_rule_for_item_ext(args, doc=None, for_validate=False):
    from erpnext.accounts.doctype.pricing_rule.utils import (
        get_applied_pricing_rules,
        get_pricing_rule_items,
        get_pricing_rules,
        get_product_discount_rule,
    )
    print("pricing for item in ext...............")

    if isinstance(doc, str):
        doc = json.loads(doc)

    if doc:
        doc = frappe.get_doc(doc)

    if args.get("is_free_item") or args.get("parenttype") == "Material Request":
        return {}

    item_details = frappe._dict(
        {
            "doctype": args.doctype,
            "has_margin": False,
            "name": args.name,
            "free_item_data": [],
            "parent": args.parent,
            "parenttype": args.parenttype,
            "child_docname": args.get("child_docname"),
        }
    )

    if args.ignore_pricing_rule or not args.item_code:
        if frappe.db.exists(args.doctype, args.name) and args.get("pricing_rules"):
            item_details = remove_pricing_rule_for_item(
                args.get("pricing_rules"),
                item_details,
                item_code=args.get("item_code"),
                rate=args.get("price_list_rate"),
            )
        return item_details

    update_args_for_pricing_rule(args)

    pricing_rules = (
        get_applied_pricing_rules(args.get("pricing_rules"))
        if for_validate and args.get("pricing_rules")
        else get_pricing_rules(args, doc)
    )

    if pricing_rules:
        rules = []

        for pricing_rule in pricing_rules:
            if not pricing_rule:
                continue

            if isinstance(pricing_rule, str):
                pricing_rule = frappe.get_cached_doc("Pricing Rule", pricing_rule)
                update_pricing_rule_uom(pricing_rule, args)
                pricing_rule.apply_rule_on_other_items = get_pricing_rule_items(pricing_rule) or []

            if pricing_rule.get("suggestion"):
                continue
            

            item_details.validate_applied_rule = pricing_rule.get("validate_applied_rule", 0)
            item_details.price_or_product_discount = pricing_rule.get("price_or_product_discount")

            rules.append(get_pricing_rule_details(args, pricing_rule))

            if pricing_rule.mixed_conditions or pricing_rule.apply_rule_on_other:
                item_details.update(
                    {
                        "price_or_product_discount": pricing_rule.price_or_product_discount,
                        "apply_rule_on": (
                            frappe.scrub(pricing_rule.apply_rule_on_other)
                            if pricing_rule.apply_rule_on_other
                            else frappe.scrub(pricing_rule.get("apply_on"))
                        ),
                    }
                )

                if pricing_rule.apply_rule_on_other_items:
                    item_details["apply_rule_on_other_items"] = json.dumps(pricing_rule.apply_rule_on_other_items)

            if pricing_rule.coupon_code_based == 1 and args.coupon_code == None:
                return item_details

            if not pricing_rule.validate_applied_rule:
                if pricing_rule.price_or_product_discount == "Price":
                    apply_price_discount_rule(pricing_rule, item_details, args)
                else:
                    get_product_discount_rule(pricing_rule, item_details, args, doc)
            

            if pricing_rule.apply_features_rule == 1:
                item_details.apply_features_rule = 1
                apply_feature_price_rule(pricing_rule, item_details, args);

        if not item_details.get("has_margin"):
            item_details.margin_type = None
            item_details.margin_rate_or_amount = 0.0

        item_details.has_pricing_rule = 1

        item_details.pricing_rules = frappe.as_json([d.pricing_rule for d in rules])

        if not doc:
            return item_details

    elif args.get("pricing_rules"):
        item_details = remove_pricing_rule_for_item(
            args.get("pricing_rules"),
            item_details,
            item_code=args.get("item_code"),
            rate=args.get("price_list_rate"),
        )

    return item_details


def apply_feature_price_rule(pricing_rule, item_details, args):
    """
    Apply feature price rule
    """
    additional_features_price = 0.0
    item_features = frappe.get_all("Item Feature Detail", filters={"parent": args.item_code}, fields=["feature", "additional_cost"])
    for feature in args.get("features"):
        priced = False
        for feat in item_features:
    
            if feature.get("item_feature") == feat.feature:
                additional_features_price += feat.additional_cost
                priced = True
                break

        if not priced:
            feature_doc = frappe.get_doc("Item Feature", feature.get("item_feature"))
            for feat in item_features:
                if feature_doc.type == feat.feature_type:
                    if feat.additional_cost:
                        additional_features_price += feat.additional_cost
                    else :
                        additional_features_price += feature_doc.additional_cost
                    break

    item_details.additional_features_price = additional_features_price


