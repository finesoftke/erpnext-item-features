
__version__ = '0.0.1'

# from erpnext.accounts.doctype.pricing_rule.pricing_rule import get_pricing_rule_for_item
# from itemfeatures.itemfeatures.override.ext_pricing_rule import get_pricing_rule_for_item_ext

# get_pricing_rule_for_item = get_pricing_rule_for_item_ext
from erpnext.controllers.accounts_controller import update_bin_on_delete
from erpnext.controllers.buying_controller import BuyingController
from erpnext.controllers.sales_and_purchase_returns import get_rate_for_return
from erpnext.controllers.selling_controller import SellingController
from erpnext.controllers.stock_controller import (
    StockController,
)
from erpnext.stock.stock_ledger import update_entries_after

from apps.itemfeatures.itemfeatures.itemfeatures.override.monkey_patches import (
    update_bin_on_delete as update_bin_on_delete_custom,
    set_rate_for_standalone_debit_note as set_rate_for_standalone_debit_note_custom,
    get_rate_for_return as get_rate_for_return_custom,
    set_incoming_rate as set_incoming_rate_custom,
    get_sl_entries as get_sl_entries_custom,
    future_sle_exists as future_sle_exists_custom,
    validate_future_sle_not_exists as validate_future_sle_not_exists_custom,
    get_cached_data as get_cached_data_custom,
    get_sle_entries_against_voucher as get_sle_entries_against_voucher_custom,
    get_conditions_to_validate_future_sle as get_conditions_to_validate_future_sle_custom,
    repost as repost_custom,
    repost_stock as repost_stock_custom,
    update_bin_qty as update_bin_qty_custom,
    update_bin as update_bin_custom,
    raise_exceptions as raise_exceptions_custom,
    get_fallback_rate as get_fallback_rate_custom,
    get_incoming_outgoing_rate_from_transaction as get_incoming_outgoing_rate_from_transaction_custom,
    get_sle_against_current_voucher as get_sle_against_current_voucher_custom,  
    get_previous_sle_of_current_voucher as get_previous_sle_of_current_voucher_custom,
    get_stock_ledger_entries as get_stock_ledger_entries_custom,
    get_valuation_rate as get_valuation_rate_custom,
    update_qty_in_future_sle as update_qty_in_future_sle_custom,
    get_next_stock_reco as get_next_stock_reco_custom,
    get_future_sle_with_negative_qty as get_future_sle_with_negative_qty_custom,
    get_future_sle_with_negative_batch_qty as get_future_sle_with_negative_batch_qty_custom,
    get_bin as get_bin_custom,
    get_or_make_bin as get_or_make_bin_custom,
    _create_bin as _create_bin_custom,
)

from apps.itemfeatures.itemfeatures.itemfeatures.override.ext_stock_entry import (
    get_available_materials as get_available_materials_custom,
    get_stock_entry_data as get_stock_entry_data_custom,
)
from apps.itemfeatures.itemfeatures.itemfeatures.override.ext_stock_reconciliation import (
    get_items_for_stock_reco as get_items_for_stock_reco_custom,
    get_item_data as get_item_data_custom,
)

erpnext.controllers.accounts_controller.update_bin_on_delete = update_bin_on_delete_custom
BuyingController.set_rate_for_standalone_debit_note = set_rate_for_standalone_debit_note_custom
erpnext.controllers.sales_and_purchase_returns.get_rate_for_return = get_rate_for_return_custom
SellingController.set_incoming_rate = set_incoming_rate_custom
StockController.get_sl_entries = get_sl_entries_custom
erpnext.controllers.stock_controller.future_sle_exists = future_sle_exists_custom
erpnext.controllers.stock_controller.validate_future_sle_not_exists = validate_future_sle_not_exists_custom
erpnext.controllers.stock_controller.get_cached_data = get_cached_data_custom
erpnext.controllers.stock_controller.get_sle_entries_against_voucher = get_sle_entries_against_voucher_custom
erpnext.controllers.stock_controller.get_conditions_to_validate_future_sle = get_conditions_to_validate_future_sle_custom
erpnext.stock.doctype.stock_entry.stock_entry.get_available_materials = get_available_materials_custom
erpnext.stock.doctype.stock_entry.stock_entry.get_stock_entry_data = get_stock_entry_data_custom
erpnext.stock.doctype.stock_reconciliation.stock_reconciliation.get_items_for_stock_reco = get_items_for_stock_reco_custom
erpnext.stock.doctype.stock_reconciliation.stock_reconciliation.get_item_data = get_item_data_custom
erpnext.stock.stock_balance.repost = repost_custom
erpnext.stock.stock_balance.repost_stock = repost_stock_custom
erpnext.stock.stock_balance.update_bin_qty = update_bin_qty_custom
update_entries_after.update_bin = update_bin_custom
update_entries_after.raise_exceptions = raise_exceptions_custom
update_entries_after.get_fallback_rate = get_fallback_rate_custom
update_entries_after.get_incoming_outgoing_rate_from_transaction = get_incoming_outgoing_rate_from_transaction_custom
update_entries_after.get_sle_against_current_voucher = get_sle_against_current_voucher_custom
erpnext.stock.stock_ledger.get_previous_sle_of_current_voucher = get_previous_sle_of_current_voucher_custom
erpnext.stock.stock_ledger.get_stock_ledger_entries = get_stock_ledger_entries_custom
erpnext.stock.stock_ledger.get_valuation_rate = get_valuation_rate_custom
erpnext.stock.stock_ledger.update_qty_in_future_sle = update_qty_in_future_sle_custom
erpnext.stock.stock_ledger.get_next_stock_reco = get_next_stock_reco_custom
erpnext.stock.stock_ledger.get_future_sle_with_negative_qty = get_future_sle_with_negative_qty_custom
erpnext.stock.stock_ledger.get_future_sle_with_negative_batch_qty = get_future_sle_with_negative_batch_qty_custom
erpnest.stock.utils.get_bin = get_bin_custom
erpnext.stock.utils.get_or_make_bin = get_or_make_bin_custom
erpnext.stock.utils._create_bin = _create_bin_custom