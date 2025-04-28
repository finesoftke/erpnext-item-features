#import Item
from erpnext.stock.doctype.item.item import Item
import frappe

class ExtItem(Item):

	def recalculate_bin_qty(self, new_name):
		from erpnext.stock.stock_balance import repost_stock

		existing_allow_negative_stock = frappe.db.get_value("Stock Settings", None, "allow_negative_stock")
		frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 1)

		repost_stock_for_warehouses = frappe.get_all(
			"Stock Ledger Entry",
			"warehouse",
			filters={"item_code": new_name},
			pluck="warehouse",
			distinct=True,
		)

		# Delete all existing bins to avoid duplicate bins for the same item and warehouse
		frappe.db.delete("Bin", {"item_code": new_name})

		for warehouse in repost_stock_for_warehouses:
			repost_stock(new_name, warehouse, None)

		frappe.db.set_single_value("Stock Settings", "allow_negative_stock", existing_allow_negative_stock)

