# -*- coding: utf-8 -*-
"""
OrderExtractor — Parses AI response and extracts structured order data JSON.
"""
import json
import re
import logging

_logger = logging.getLogger(__name__)


class OrderExtractor:
    """
    Responsible for parsing AI response text and extracting the embedded JSON order data.
    Also manages merging new extracted data with existing session data.
    """

    EMPTY_ORDER = {
        'key': '',
        'customer': '',
        'customer_id': None,
        'customer_suggestions': [],
        'lpo_number': '',
        'order_lines': [],
        'delivery_date': None,
        'quotation_date': None,
        'payment_term': '',
        'payment_term_id': None,
        'salesperson': '',
        'user_id': None,
        'notes': '',
        'confidence': 0.0,
        'missing_fields': [],
        'follow_up_questions': [],
    }

    def extract_from_ai_response(self, ai_response_text):
        """
        Parse the AI response to extract the embedded JSON order data.

        The AI is instructed to always include a ```json ... ``` block.

        :param ai_response_text: str — full AI response
        :return: (reply_text, order_data_dict)
        """
        reply_text = ai_response_text
        order_data = {}

        # Extract JSON block from markdown code fence
        json_pattern = r'```json\s*([\s\S]*?)```'
        matches = re.findall(json_pattern, ai_response_text, re.IGNORECASE)

        if matches:
            json_str = matches[-1].strip()  # Use last JSON block if multiple
            try:
                order_data = json.loads(json_str)
                # Remove JSON block from visible reply
                reply_text = re.sub(json_pattern, '', ai_response_text, flags=re.IGNORECASE).strip()
            except json.JSONDecodeError as e:
                _logger.warning('Failed to parse JSON from AI response: %s', str(e))
                order_data = {}
        else:
            # Try finding raw JSON object anywhere in response
            json_obj_pattern = r'\{[\s\S]*"order_lines"[\s\S]*\}'
            match = re.search(json_obj_pattern, ai_response_text)
            if match:
                try:
                    order_data = json.loads(match.group())
                    reply_text = ai_response_text[:match.start()].strip()
                except json.JSONDecodeError:
                    pass

        # Strip HTML tags from reply_text
        reply_text = re.sub(r'</?[a-zA-Z][^>]*>', '', reply_text)

        # Normalize the order data structure
        order_data = self._normalize_order_data(order_data)
        return reply_text, order_data

    def merge_order_data(self, existing_data, new_data, env=None, user_message=None, product_category=None):
        """
        Merge newly extracted data (which has {"orders": [...]}) with existing session order data.
        """
        existing_data_norm = self._normalize_order_data(existing_data)
        new_data_norm = self._normalize_order_data(new_data)

        existing_orders = existing_data_norm.get('orders', [])
        new_orders = new_data_norm.get('orders', [])

        merged_orders = []
        
        # Step 1: Match by LPO number
        merged_new_indices = set()
        
        for ext_idx, ext_order in enumerate(existing_orders):
            ext_lpo = str(ext_order.get('lpo_number') or '').strip().lower()
            matched_new_idx = None
            
            if ext_lpo:
                for new_idx, new_order in enumerate(new_orders):
                    if new_idx in merged_new_indices:
                        continue
                    new_lpo = str(new_order.get('lpo_number') or '').strip().lower()
                    if new_lpo == ext_lpo:
                        matched_new_idx = new_idx
                        break
            
            if matched_new_idx is not None:
                merged_new_indices.add(matched_new_idx)
                merged_order = self._merge_single_order(ext_order, new_orders[matched_new_idx], env=env, user_message=user_message, product_category=product_category)
                # preserve created sales order details
                merged_order['sale_order_id'] = ext_order.get('sale_order_id')
                merged_order['sale_order_name'] = ext_order.get('sale_order_name')
                merged_order['state'] = ext_order.get('state') or 'draft'
                merged_orders.append(merged_order)
            else:
                merged_orders.append(None)

        # Step 2: For existing orders not matched by LPO, match them to remaining new orders by index alignment
        for ext_idx, ext_order in enumerate(existing_orders):
            if merged_orders[ext_idx] is not None:
                continue
            
            matched_new_idx = None
            for new_idx in range(len(new_orders)):
                if new_idx not in merged_new_indices:
                    matched_new_idx = new_idx
                    break
            
            if matched_new_idx is not None:
                merged_new_indices.add(matched_new_idx)
                merged_order = self._merge_single_order(ext_order, new_orders[matched_new_idx], env=env, user_message=user_message, product_category=product_category)
                # preserve created sales order details
                merged_order['sale_order_id'] = ext_order.get('sale_order_id')
                merged_order['sale_order_name'] = ext_order.get('sale_order_name')
                merged_order['state'] = ext_order.get('state') or 'draft'
                merged_orders[ext_idx] = merged_order
            else:
                # No remaining new orders, keep the existing order as is
                merged_orders[ext_idx] = ext_order

        # Step 3: Append any remaining new orders that were not matched to any existing order
        for new_idx, new_order in enumerate(new_orders):
            if new_idx not in merged_new_indices:
                merged_order = self._normalize_single_order(new_order)
                merged_order['sale_order_id'] = None
                merged_order['sale_order_name'] = None
                merged_order['state'] = 'draft'
                merged_orders.append(merged_order)

        return {"orders": merged_orders}

    def _merge_single_order(self, existing_data, new_data, env=None, user_message=None, product_category=None):
        """
        Merge newly extracted data into existing session order data.
        New data takes precedence for resolved fields.
        """
        merged = dict(existing_data) if existing_data else dict(self.EMPTY_ORDER)

        # Customer: update only if new value is not empty/UNRESOLVED
        new_customer = new_data.get('customer', '')
        if new_customer and new_customer != 'UNRESOLVED':
            merged['customer'] = new_customer
            if new_data.get('customer_id'):
                merged['customer_id'] = new_data['customer_id']
        elif new_customer == 'UNRESOLVED':
            merged['customer'] = 'UNRESOLVED'
            merged['customer_id'] = None

        # Order lines: merge by product name or product_id
        validator = None
        if env:
            try:
                from .order_validator import OrderValidator
                validator = OrderValidator(env)
            except Exception as e:
                _logger.warning('Could not import or initialize OrderValidator: %s', str(e))

        existing_lines = merged.get('order_lines', [])
        remaining_existing = [dict(ln) for ln in existing_lines]
        merged_lines = []

        for new_line in new_data.get('order_lines', []):
            new_prod_name = (new_line.get('product') or '').strip()
            if not new_prod_name:
                continue

            matched_line = None
            resolved_id = None
            resolved_name = None

            if validator:
                try:
                    res = validator.validate_product(new_prod_name, product_category=product_category, partner_id=merged.get('customer_id'))
                    if res and res.get('status') == 'found':
                        resolved_id = res.get('id')
                        resolved_name = res.get('name')
                except Exception as e:
                    _logger.warning('Error resolving product "%s": %s', new_prod_name, str(e))

            for idx, ext_line in enumerate(remaining_existing):
                product_match = False
                if resolved_id and ext_line.get('product_id') == resolved_id:
                    product_match = True
                elif resolved_name and (ext_line.get('product') or '').strip().lower() == resolved_name.strip().lower():
                    product_match = True
                elif (ext_line.get('product') or '').strip().lower() == new_prod_name.lower():
                    product_match = True

                if product_match:
                    new_w = new_line.get('width')
                    ext_w = ext_line.get('width')
                    new_h = new_line.get('height')
                    ext_h = ext_line.get('height')
                    
                    if new_w is not None and ext_w is not None and new_h is not None and ext_h is not None:
                        try:
                            if abs(float(new_w) - float(ext_w)) > 0.0001 or abs(float(new_h) - float(ext_h)) > 0.0001:
                                continue
                        except (ValueError, TypeError):
                            pass
                            
                    matched_line = remaining_existing.pop(idx)
                    break

            if matched_line:
                updated_line = dict(matched_line)
                
                new_qty = None
                for k in ('qty', 'quantity', 'Qty', 'QTY'):
                    if k in new_line:
                        new_qty = new_line[k]
                        break
                if new_qty is not None:
                    updated_line['qty'] = new_qty

                new_height = None
                for k in ('height', 'H', 'h'):
                    if k in new_line:
                        new_height = new_line[k]
                        break
                if new_height is not None:
                    updated_line['height'] = new_height

                new_width = None
                for k in ('width', 'W', 'w'):
                    if k in new_line:
                        new_width = new_line[k]
                        break
                if new_width is not None:
                    updated_line['width'] = new_width

                new_price = None
                for k in ('price', 'unit_price', 'unit price', 'rate', 'Rate', 'Price'):
                    if k in new_line:
                        new_price = new_line[k]
                        break
                if new_price is not None:
                    updated_line['price'] = new_price

                if 'discount' in new_line and new_line['discount'] is not None:
                    updated_line['discount'] = new_line['discount']
                if 'tax' in new_line and new_line['tax'] is not None:
                    if str(matched_line.get('tax', '')).strip().lower() != str(new_line['tax']).strip().lower():
                        updated_line['tax'] = new_line['tax']
                        updated_line['tax_id'] = None
                        updated_line['tax_ids'] = []
                        updated_line['tax_name'] = new_line['tax']
                if 'uom' in new_line and new_line['uom'] is not None and new_line['uom'] != '':
                    updated_line['uom'] = new_line['uom']
                merged_lines.append(updated_line)
            else:
                new_line_copy = dict(new_line)
                pid = new_line_copy.get('product_id') or resolved_id
                if pid and not new_line_copy.get('product_id'):
                    new_line_copy['product_id'] = pid
                if resolved_name and not new_line_copy.get('product'):
                    new_line_copy['product'] = resolved_name
                merged_lines.append(new_line_copy)

        is_deletion_request = False
        if user_message:
            msg_lower = user_message.lower()
            delete_keywords = {'remove', 'delete', 'exclude', 'drop', 'discard', 'clear', 'cancel', 'omit'}
            if any(kw in msg_lower for kw in delete_keywords):
                is_deletion_request = True

        for ext_line in remaining_existing:
            if is_deletion_request:
                ext_prod_name = ext_line.get('product', '')
                if self._is_product_mentioned(ext_prod_name, user_message):
                    continue

            if user_message:
                merged_lines.append(ext_line)

        merged['order_lines'] = merged_lines

        new_lpo = new_data.get('lpo_number') or new_data.get('purchase_order') or new_data.get('po_number')
        if new_lpo:
            merged['lpo_number'] = str(new_lpo).replace('#', '').strip()

        new_delivery = None
        for k in ('delivery_date', 'installation_date', 'Installation Date', 'Delivery Date'):
            if new_data.get(k):
                new_delivery = new_data[k]
                break
        if new_delivery:
            merged['delivery_date'] = new_delivery

        if new_data.get('payment_term'):
            merged['payment_term'] = new_data['payment_term']
        if new_data.get('payment_term_id'):
            merged['payment_term_id'] = new_data['payment_term_id']

        if new_data.get('salesperson'):
            merged['salesperson'] = new_data['salesperson']
        if new_data.get('user_id'):
            merged['user_id'] = new_data['user_id']

        new_quotation = None
        for k in ('quotation_date', 'order_date', 'Order Date', 'Quotation Date'):
            if new_data.get(k):
                new_quotation = new_data[k]
                break
        if new_quotation:
            merged['quotation_date'] = new_quotation

        new_notes = (new_data.get('notes') or '').strip()
        existing_notes = (merged.get('notes') or '').strip()
        if new_notes and new_notes not in existing_notes:
            merged['notes'] = (existing_notes + '\n' + new_notes).strip() if existing_notes else new_notes

        merged['confidence'] = new_data.get('confidence', merged.get('confidence', 0.0))
        merged['missing_fields'] = new_data.get('missing_fields', [])
        merged['follow_up_questions'] = new_data.get('follow_up_questions', [])
        merged['customer_suggestions'] = new_data.get('customer_suggestions', [])

        return merged

    def _normalize_order_data(self, data):
        """Ensure order data is in the format {"orders": [...]} and each order has all required fields."""
        if not isinstance(data, dict):
            if isinstance(data, list):
                orders_list = data
            else:
                orders_list = []
        else:
            if 'orders' in data and isinstance(data['orders'], list):
                orders_list = data['orders']
            elif 'order_lines' in data or 'customer' in data or 'lpo_number' in data:
                orders_list = [data]
            else:
                orders_list = []

        normalized_orders = []
        for idx, order in enumerate(orders_list):
            if not isinstance(order, dict):
                continue
            norm_order = self._normalize_single_order(order)
            if 'key' not in norm_order or not norm_order['key']:
                norm_order['key'] = f"order_{idx}"
            normalized_orders.append(norm_order)

        if not normalized_orders:
            first_order = self._normalize_single_order({})
            first_order['key'] = "order_0"
            normalized_orders.append(first_order)

        return {"orders": normalized_orders}

    def _normalize_single_order(self, data):
        """Ensure order data has all required fields with correct types."""
        normalized = dict(self.EMPTY_ORDER)
        normalized.update(data)

        # Normalize LPO Number
        lpo = data.get('lpo_number') or data.get('purchase_order') or data.get('po_number') or ''
        normalized['lpo_number'] = str(lpo).replace('#', '').strip()

        # Normalize quotation date
        new_quotation = None
        for k in ('quotation_date', 'order_date', 'Order Date', 'Quotation Date'):
            if data.get(k):
                new_quotation = data[k]
                break
        normalized['quotation_date'] = new_quotation

        # Normalize delivery date (mapping installation_date fallback)
        new_delivery = None
        for k in ('delivery_date', 'installation_date', 'Installation Date', 'Delivery Date'):
            if data.get(k):
                new_delivery = data[k]
                break
        normalized['delivery_date'] = new_delivery

        # Normalize payment term and salesperson
        normalized['payment_term'] = str(data.get('payment_term') or '') if data.get('payment_term') else ''
        normalized['payment_term_id'] = data.get('payment_term_id')
        normalized['salesperson'] = str(data.get('salesperson') or '') if data.get('salesperson') else ''
        normalized['user_id'] = data.get('user_id')

        # Ensure order_lines is a list of dicts
        if not isinstance(normalized.get('order_lines'), list):
            normalized['order_lines'] = []

        lines = []
        for line in normalized['order_lines']:
            if isinstance(line, dict) and line.get('product'):
                discount = self._safe_float(line.get('discount'), default=0.0)
                
                height_val = None
                for k in ('height', 'H', 'h'):
                    if k in line:
                        height_val = line[k]
                        break
                height = self._safe_float(height_val, default=1.0)
                if height <= 0.0:
                    height = 1.0

                width_val = None
                for k in ('width', 'W', 'w'):
                    if k in line:
                        width_val = line[k]
                        break
                width = self._safe_float(width_val, default=1.0)
                if width <= 0.0:
                    width = 1.0

                tax_raw = line.get('tax')
                if tax_raw is None or str(tax_raw).strip() == '':
                    tax_formatted = ''
                else:
                    tax_str = str(tax_raw).strip()
                    try:
                        tax_float = float(tax_str)
                        if 0.0 < tax_float < 1.0:
                            tax_formatted = f"{tax_float * 100.0:g}%"
                        elif tax_float >= 1.0:
                            tax_formatted = f"{tax_float:g}%"
                        else:
                            tax_formatted = tax_str
                    except ValueError:
                        tax_formatted = tax_str

                qty_val = None
                for k in ('qty', 'quantity', 'Qty', 'QTY'):
                    if k in line:
                        qty_val = line[k]
                        break
                if qty_val is None:
                    qty_val = 1.0

                price_val = None
                for k in ('price', 'unit_price', 'unit price', 'rate', 'Rate', 'Price'):
                    if k in line:
                        price_val = line[k]
                        break

                normalized_line = {
                    'product': str(line.get('product', '')),
                    'product_id': line.get('product_id'),
                    'qty': self._safe_float(qty_val, default=1.0),
                    'height': height,
                    'width': width,
                    'price': self._safe_float(price_val),
                    'discount': discount,
                    'tax': tax_formatted,
                    'uom': str(line.get('uom') or '').strip(),
                }
                lines.append(normalized_line)
        normalized['order_lines'] = lines

        # Confidence score 0-100
        normalized['confidence'] = max(0.0, min(100.0, float(normalized.get('confidence') or 0.0)))

        # Ensure lists
        if not isinstance(normalized.get('missing_fields'), list):
            normalized['missing_fields'] = []
        if not isinstance(normalized.get('follow_up_questions'), list):
            normalized['follow_up_questions'] = []
        if not isinstance(normalized.get('customer_suggestions'), list):
            normalized['customer_suggestions'] = []

        return normalized

    @staticmethod
    def _safe_float(value, default=None):
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _is_product_mentioned(product_name, message):
        if not message:
            return True
        message_lower = message.lower()
        prod_lower = product_name.lower()
        
        # 1. Direct substring match
        if prod_lower in message_lower:
            return True
            
        # 2. Check if significant words of the product name are in the message
        import re
        clean_name = re.sub(r'\[.*?\]', '', product_name).strip()
        words = [w.lower() for w in re.findall(r'\b\w{3,}\b', clean_name)]
        if not words:
            return True
            
        common_words = {'unit', 'units', 'each', 'pack', 'black', 'white', 'large', 'small', 'wood', 'metal'}
        matching_words = [w for w in words if w not in common_words]
        if not matching_words:
            matching_words = words
            
        for word in matching_words:
            if word in message_lower:
                return True
                
        # 3. Check for general quantifiers that imply updating all lines
        quantifiers = {'all', 'every', 'both', 'each', 'lines', 'items', 'quantities', 'prices', 'everything', 'clear'}
        if any(q in message_lower for q in quantifiers):
            return True
            
        return False
