# -*- coding: utf-8 -*-
"""
OrderValidator — Validates extracted order data against Odoo database.
"""
import logging

_logger = logging.getLogger(__name__)


class OrderValidator:
    """
    Validates order data fields against live Odoo records.
    Performs fuzzy matching for partners and products.
    """

    def __init__(self, env):
        self.env = env

    def map_with_lookup_aliases(self, text, product_category=None, partner_id=None, field_type='product'):
        """
        Search in the active category's lookup aliases for a match of document text.
        
        :param text: str - the text to look up
        :param product_category: str - the active category type ('blind', 'fabric', 'track')
        :param partner_id: int - (optional) if we already resolved the customer, check customer-specific aliases
        :param field_type: str - 'product' or 'customer', indicates which field we are resolving
        :return: record or None
        """
        if not text or not product_category:
            return None
            
        # 1. Find the active category record
        category = self.env['alias.category'].sudo().search([('type', '=', product_category)], limit=1)
        if not category:
            return None
            
        # 2. Search alias lines in this category
        # Match alias_name exactly (case-insensitive)
        alias_lines = category.line_ids.filtered(lambda l: (l.alias_name or '').strip().lower() == text.strip().lower())
        
        # If no exact match, try a cleaned comparison
        if not alias_lines:
            import re
            def clean_text(val):
                return re.sub(r'[\W_]+', '', val).lower() if val else ''
            text_clean = clean_text(text)
            if text_clean:
                alias_lines = category.line_ids.filtered(lambda l: clean_text(l.alias_name) == text_clean)

        if not alias_lines:
            return None
            
        # 3. If field_type is 'product', resolve to a product record
        if field_type == 'product':
            # Prioritize alias lines that match the partner_id if provided
            if partner_id:
                partner_match_lines = alias_lines.filtered(lambda l: partner_id in l.partner_ids.ids)
                if partner_match_lines and partner_match_lines[0].product_ids:
                    return partner_match_lines[0].product_ids[0]
            
            # If no partner match or partner_id not provided, look for global lines (partner_ids is empty)
            global_lines = alias_lines.filtered(lambda l: not l.partner_ids)
            if global_lines and global_lines[0].product_ids:
                return global_lines[0].product_ids[0]
                
            # Fallback to any matching alias line's first product
            for line in alias_lines:
                if line.product_ids:
                    return line.product_ids[0]
                    
        # 4. If field_type is 'customer', resolve to a partner record
        elif field_type == 'customer':
            # For customer, return the first partner in partner_ids if defined
            for line in alias_lines:
                if line.partner_ids:
                    return line.partner_ids[0]
                    
        return None

    def validate_and_enrich(self, order_data, is_manual=False):
        """
        Validate and enrich order data. Supports both single order dict and multiple orders dict.
        """
        if not order_data:
            return {}, [], []

        if 'orders' in order_data and isinstance(order_data['orders'], list):
            enriched_orders = []
            all_errors = []
            all_warnings = []
            for order in order_data['orders']:
                if 'product_category' not in order and 'product_category' in order_data:
                    order['product_category'] = order_data['product_category']
                
                enriched_order, errors, warnings = self._validate_and_enrich_single(order, is_manual=is_manual)
                enriched_order['errors'] = errors
                enriched_order['warnings'] = warnings
                
                # Keep existing sales order link if present
                if 'sale_order_id' not in enriched_order and 'sale_order_id' in order:
                    enriched_order['sale_order_id'] = order['sale_order_id']
                if 'sale_order_name' not in enriched_order and 'sale_order_name' in order:
                    enriched_order['sale_order_name'] = order['sale_order_name']
                if 'state' not in enriched_order and 'state' in order:
                    enriched_order['state'] = order['state']

                enriched_orders.append(enriched_order)
                all_errors.extend(errors)
                all_warnings.extend(warnings)
            
            enriched = {
                'orders': enriched_orders,
                'product_category': order_data.get('product_category')
            }
            # Remove duplicates from errors/warnings while preserving order
            seen_err = set()
            unique_err = [e for e in all_errors if not (e in seen_err or seen_err.add(e))]
            seen_warn = set()
            unique_warn = [w for w in all_warnings if not (w in seen_warn or seen_warn.add(w))]
            
            return enriched, unique_err, unique_warn
        else:
            return self._validate_and_enrich_single(order_data, is_manual=is_manual)

    def _validate_and_enrich_single(self, order_data, is_manual=False):
        """
        Validate and enrich order data by resolving IDs for customer and products.

        :param order_data: dict — the extracted order data
        :param is_manual: bool — if True, do not overwrite user-typed names/labels and don't fuzzy match unless exact match
        :return: (enriched_data, validation_errors, validation_warnings)
        """
        errors = []
        warnings = []
        enriched = dict(order_data)
        product_category = order_data.get('product_category')

        # --- Default Quotation Date to today if missing ---
        quotation_date = enriched.get('quotation_date')
        if not quotation_date or not str(quotation_date).strip():
            from datetime import date
            enriched['quotation_date'] = date.today().strftime('%Y-%m-%d')

        # --- Clean LPO Number ---
        lpo = enriched.get('lpo_number')
        if lpo:
            enriched['lpo_number'] = str(lpo).replace('#', '').strip()

        # --- Validate customer ---
        customer_name = (order_data.get('customer') or '').strip()
        customer_id = order_data.get('customer_id')

        if is_manual:
            if customer_id:
                partner = self.env['res.partner'].sudo().browse(int(customer_id)).exists()
                if partner and partner.active:
                    enriched['customer_id'] = partner.id
                else:
                    enriched['customer_id'] = None
                    warnings.append(f"Customer ID '{customer_id}' not found or inactive in the system.")
            elif customer_name and customer_name != 'UNRESOLVED':
                partner = self.env['res.partner'].sudo().search([
                    ('name', '=ilike', customer_name),
                    ('active', '=', True)
                ], limit=1)
                if partner:
                    enriched['customer_id'] = partner.id
                else:
                    enriched['customer_id'] = None
                    warnings.append(f"Customer '{customer_name}' not found in system.")
            elif customer_name == 'UNRESOLVED':
                enriched['customer_id'] = None
                errors.append('Customer name is required.')
            else:
                enriched['customer_id'] = None
                errors.append('Customer name is required to create a Sales Order.')
        else:
            customer_result = self.validate_customer(customer_name, product_category=product_category)
            if customer_result['status'] == 'found':
                enriched['customer'] = customer_result['name']
                enriched['customer_id'] = customer_result['id']
            elif customer_result['status'] == 'not_found':
                if customer_name and customer_name != 'UNRESOLVED':
                    warnings.append(f"Customer '{customer_name}' not found in system.")
                else:
                    errors.append('Customer name is required.')
            elif customer_result['status'] == 'empty':
                errors.append('Customer name is required to create a Sales Order.')

        # Determine customer suggestions if not resolved
        enriched['customer_suggestions'] = []
        if not enriched.get('customer_id'):
            enriched['customer_suggestions'] = self.get_customer_suggestions(customer_name)

        # --- Validate order lines ---
        product_category = order_data.get('product_category')
        categ_ids = self._get_category_ids_for_type(product_category) if product_category else []

        enriched_lines = []
        for line in order_data.get('order_lines', []):
            prod_name = (line.get('product') or '').strip()
            prod_id = line.get('product_id')
            enriched_line = dict(line)

            product_rec = None
            if is_manual:
                if prod_id:
                    product = self.env['product.product'].sudo().browse(int(prod_id)).exists()
                    if product and product.active:
                        enriched_line['product_id'] = product.id
                        enriched_line['validated'] = True
                        product_rec = product
                    else:
                        enriched_line['product_id'] = None
                        enriched_line['validated'] = False
                        warnings.append(f"Product ID '{prod_id}' not found or inactive in the system.")
                elif prod_name and prod_name != 'UNRESOLVED':
                    import re
                    code, name_part = None, prod_name
                    match = re.match(r'^\[(.*?)\]\s*(.*)$', prod_name)
                    if match:
                        code = match.group(1).strip()
                        name_part = match.group(2).strip()

                    product = None
                    domain = [('active', '=', True), ('sale_ok', '=', True)]
                    if categ_ids:
                        domain.append(('categ_id', 'in', categ_ids))

                    if code:
                        product = self.env['product.product'].sudo().search(
                            domain + [('default_code', '=ilike', code)], limit=1
                        )
                    if not product:
                        product = self.env['product.product'].sudo().search(
                            domain + [('name', '=ilike', name_part)], limit=1
                        )

                    if product:
                        enriched_line['product_id'] = product.id
                        enriched_line['validated'] = True
                        product_rec = product
                    else:
                        enriched_line['product_id'] = None
                        enriched_line['validated'] = False
                        warnings.append(f"Product '{prod_name}' not found in system.")
                else:
                    enriched_line['product_id'] = None
                    enriched_line['validated'] = False
                    errors.append('Product name is required for each order line.')
            else:
                line_result = self.validate_product(prod_name, product_category=product_category, partner_id=enriched.get('customer_id'))
                if line_result['status'] == 'found':
                    enriched_line['product'] = line_result['name']
                    enriched_line['product_id'] = line_result['id']
                    enriched_line['validated'] = True
                    product_rec = self.env['product.product'].sudo().browse(line_result['id']).exists()
                elif line_result['status'] == 'not_found':
                    warnings.append(f"Product '{prod_name}' not found in system.")
                    enriched_line['validated'] = False
                    enriched_line['product_id'] = None
                else:
                    errors.append('Product name is required for each order line.')
                    enriched_line['validated'] = False

            if product_rec:
                # Default Price from product if not provided or empty
                price_val = enriched_line.get('price')
                if price_val is None or str(price_val).strip() == '':
                    enriched_line['price'] = product_rec.lst_price
                else:
                    try:
                        enriched_line['price'] = float(price_val)
                    except (TypeError, ValueError):
                        enriched_line['price'] = product_rec.lst_price

                # Default UOM from product if not provided or empty
                if not enriched_line.get('uom') or str(enriched_line.get('uom')).strip() == '':
                    enriched_line['uom'] = product_rec.uom_id.name or 'Units'

                # Default Tax from product if not provided or empty
                has_manual_tax = False
                if enriched_line.get('tax_ids') or enriched_line.get('tax_id') or enriched_line.get('tax'):
                    has_manual_tax = True
                if not has_manual_tax:
                    product_taxes = product_rec.taxes_id.filtered(lambda t: t.company_id == self.env.company)
                    if product_taxes:
                        enriched_line['tax'] = product_taxes[0].name
                        enriched_line['tax_id'] = product_taxes[0].id
                        enriched_line['tax_ids'] = product_taxes.ids
                    else:
                        enriched_line['tax'] = '0%'
                        enriched_line['tax_id'] = None
                        enriched_line['tax_ids'] = []

            # Validate quantity
            qty = enriched_line.get('qty', 0)
            try:
                qty_val = float(qty)
                if qty_val <= 0:
                    warnings.append(f"Quantity for '{enriched_line.get('product')}' should be greater than 0.")
                    enriched_line['qty'] = 1.0
                else:
                    enriched_line['qty'] = qty_val
            except (TypeError, ValueError):
                warnings.append(f"Invalid quantity for '{enriched_line.get('product')}'. Defaulting to 1.")
                enriched_line['qty'] = 1.0

            # Validate height
            height = enriched_line.get('height', 1.0)
            try:
                height_val = float(height)
                if height_val <= 0:
                    enriched_line['height'] = 1.0
                else:
                    enriched_line['height'] = height_val
            except (TypeError, ValueError):
                enriched_line['height'] = 1.0

            # Validate width
            width = enriched_line.get('width', 1.0)
            try:
                width_val = float(width)
                if width_val <= 0:
                    enriched_line['width'] = 1.0
                else:
                    enriched_line['width'] = width_val
            except (TypeError, ValueError):
                enriched_line['width'] = 1.0

            # Validate discount
            discount = enriched_line.get('discount', 0.0)
            try:
                discount_val = float(discount)
                if discount_val < 0:
                    enriched_line['discount'] = 0.0
                else:
                    enriched_line['discount'] = discount_val
            except (TypeError, ValueError):
                enriched_line['discount'] = 0.0

            # Match and validate tax
            tax_val = enriched_line.get('tax')
            manual_tax_ids = enriched_line.get('tax_ids') or ([enriched_line.get('tax_id')] if enriched_line.get('tax_id') else [])
            manual_tax_ids = [tid for tid in manual_tax_ids if tid]
            
            resolved_tax = None
            if manual_tax_ids:
                taxes = self.env['account.tax'].sudo().browse(manual_tax_ids).filtered('active')
                if taxes:
                    resolved_tax = taxes[0]
            elif tax_val:
                resolved_tax = self.validate_tax(tax_val)
                if not resolved_tax:
                    is_zero_tax = False
                    try:
                        import re
                        tax_val_clean = str(tax_val).strip()
                        if tax_val_clean in ('0', '0%', '0.0', 'exempt', 'none'):
                            is_zero_tax = True
                        else:
                            pct_match = re.search(r'^0+(\.0+)?\s*%', tax_val_clean)
                            if pct_match:
                                is_zero_tax = True
                    except Exception:
                        pass
                    if not is_zero_tax:
                        warnings.append(f"Tax '{tax_val}' for product '{enriched_line.get('product')}' could not be matched. Default tax will be used.")

            if resolved_tax:
                enriched_line['tax_id'] = resolved_tax.id
                enriched_line['tax_ids'] = [resolved_tax.id]
                enriched_line['tax_name'] = resolved_tax.name
            else:
                enriched_line['tax_id'] = None
                enriched_line['tax_ids'] = []
                enriched_line['tax_name'] = tax_val or ''

            enriched_lines.append(enriched_line)

        # Collapse duplicate lines (same product_id or same product name AND same width AND same height)
        merged_lines = []
        for line in enriched_lines:
            match = None
            pid = line.get('product_id')
            pname = (line.get('product') or '').strip().lower()
            
            # Only merge if product name is specified and not unresolved
            if pname and pname != 'unresolved':
                for m_line in merged_lines:
                    m_pid = m_line.get('product_id')
                    m_pname = (m_line.get('product') or '').strip().lower()
                    
                    product_match = False
                    if pid and m_pid:
                        product_match = (pid == m_pid)
                    elif pname and m_pname:
                        product_match = (pname == m_pname)
                        
                    if product_match:
                        # Compare width and height (defaulting to 1.0 consistently if not set)
                        w1 = float(line.get('width') or 1.0)
                        w2 = float(m_line.get('width') or 1.0)
                        h1 = float(line.get('height') or 1.0)
                        h2 = float(m_line.get('height') or 1.0)
                        if abs(w1 - w2) < 0.0001 and abs(h1 - h2) < 0.0001:
                            match = m_line
                            break
            
            if match:
                # Sum quantity, discount (do not sum width or height!)
                try:
                    match['qty'] = (match.get('qty') or 0.0) + (line.get('qty') or 0.0)
                except Exception:
                    pass
                try:
                    match['discount'] = (match.get('discount') or 0.0) + (line.get('discount') or 0.0)
                except Exception:
                    pass
                # Keep/propagate resolved fields if the matched line lacks them but the current line has them
                if not match.get('product_id') and line.get('product_id'):
                    match['product_id'] = line['product_id']
                    match['product'] = line.get('product')
                    match['validated'] = line.get('validated', False)
                for field in ['price', 'uom', 'tax', 'tax_id', 'tax_ids', 'tax_name']:
                    if line.get(field) is not None and match.get(field) is None:
                        match[field] = line[field]
            else:
                merged_lines.append(dict(line))
        
        enriched_lines = merged_lines
        enriched['order_lines'] = enriched_lines

        # --- Validate Payment Term ---
        pay_term_name = (order_data.get('payment_term') or '').strip()
        pay_term_id = order_data.get('payment_term_id')
        if is_manual:
            if pay_term_id:
                term = self.env['account.payment.term'].sudo().browse(int(pay_term_id)).exists()
                if term:
                    enriched['payment_term_id'] = term.id
                else:
                    enriched['payment_term_id'] = None
                    warnings.append(f"Payment Term ID '{pay_term_id}' not found.")
            elif pay_term_name and pay_term_name != 'UNRESOLVED':
                term = self.env['account.payment.term'].sudo().search([('name', '=ilike', pay_term_name)], limit=1)
                if term:
                    enriched['payment_term_id'] = term.id
                else:
                    enriched['payment_term_id'] = None
                    warnings.append(f"Payment Term '{pay_term_name}' not matched. Default customer payment terms will be used.")
            else:
                enriched['payment_term_id'] = None
        else:
            if pay_term_name:
                term_res = self.validate_payment_term(pay_term_name)
                if term_res['status'] == 'found':
                    enriched['payment_term'] = term_res['name']
                    enriched['payment_term_id'] = term_res['id']
                else:
                    warnings.append(f"Payment Term '{pay_term_name}' not matched. Default customer payment terms will be used.")
                    enriched['payment_term_id'] = None
            else:
                enriched['payment_term_id'] = None

        # --- Validate Salesperson ---
        salesperson_name = (order_data.get('salesperson') or '').strip()
        user_id = order_data.get('user_id')
        if is_manual:
            if user_id:
                user = self.env['res.users'].sudo().browse(int(user_id)).exists()
                if user and user.active:
                    enriched['user_id'] = user.id
                else:
                    enriched['user_id'] = None
                    warnings.append(f"Salesperson User ID '{user_id}' not found or inactive.")
            elif salesperson_name and salesperson_name != 'UNRESOLVED':
                user = self.env['res.users'].sudo().search([('name', '=ilike', salesperson_name), ('active', '=', True)], limit=1)
                if user:
                    enriched['user_id'] = user.id
                else:
                    enriched['user_id'] = None
                    warnings.append(f"Salesperson '{salesperson_name}' not matched. Default salesperson will be used.")
            else:
                enriched['user_id'] = None
        else:
            if salesperson_name:
                sp_res = self.validate_salesperson(salesperson_name)
                if sp_res['status'] == 'found':
                    enriched['salesperson'] = sp_res['name']
                    enriched['user_id'] = sp_res['id']
                else:
                    warnings.append(f"Salesperson '{salesperson_name}' not matched. Default salesperson will be used.")
                    enriched['user_id'] = None
            else:
                enriched['user_id'] = None

        # --- Calculate Confidence Score ---
        has_customer = bool(enriched.get('customer') and enriched.get('customer') != 'UNRESOLVED')
        has_products = False
        if enriched_lines:
            has_products = True
            for line in enriched_lines:
                if not line.get('product') or line.get('product') == 'UNRESOLVED':
                    has_products = False
                    break
                qty = line.get('qty', 0)
                price = line.get('price', 0)
                if qty is None or price is None or float(qty) <= 0 or float(price) <= 0:
                    has_products = False
                    break

        has_quotation = bool(enriched.get('quotation_date'))

        req_count = sum([has_customer, has_products, has_quotation])
        confidence = req_count * 20.0

        if req_count == 3:
            if enriched.get('payment_term') and enriched.get('payment_term') != 'UNRESOLVED':
                confidence += 10.0
            if enriched.get('delivery_date'):
                confidence += 10.0
            if enriched.get('salesperson') and enriched.get('salesperson') != 'UNRESOLVED':
                confidence += 10.0
            if enriched.get('notes') and enriched.get('notes').strip():
                confidence += 10.0

        enriched['confidence'] = confidence

        if not enriched_lines:
            errors.append('At least one product is required to create a Sales Order.')

        return enriched, errors, warnings

    def get_customer_suggestions(self, name):
        """
        Get 3-4 customer suggestions based on customer name words matching, or fallback if none.
        """
        name = (name or '').strip()
        suggestions = []
        
        # Helper to check if partner is own company
        def is_own_company_partner(partner_id):
            p = self.env['res.partner'].sudo().browse(partner_id)
            if not p.exists():
                return False
            if p.id == self.env.company.partner_id.id:
                return True
            p_name = (p.name or '').lower()
            if 'tesro' in p_name and 'furnishing' in p_name:
                return True
            return False

        if name and name != 'UNRESOLVED':
            # Split name into words and find matching partners
            import re
            words = re.findall(r'\b\w{3,}\b', name)  # words of length >= 3
            common_words = {'llc', 'ltd', 'limited', 'inc', 'corp', 'company', 'and', 'the', 'fabrics', 'furnishing', 'furnishings'}
            search_words = [w for w in words if w.lower() not in common_words]
            if not search_words:
                search_words = words

            matched_partner_ids = set()
            for word in search_words:
                partners = self.env['res.partner'].sudo().search([
                    ('name', 'ilike', word),
                    ('active', '=', True)
                ], limit=10)
                for p in partners:
                    if not is_own_company_partner(p.id):
                        matched_partner_ids.add(p.id)
            
            if matched_partner_ids:
                # Sort by similarity ratio
                from difflib import SequenceMatcher
                def get_similarity(s1, s2):
                    if not s1 or not s2:
                        return 0.0
                    return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()

                partner_recs = self.env['res.partner'].sudo().browse(list(matched_partner_ids))
                sorted_recs = sorted(partner_recs, key=lambda p: get_similarity(name, p.name or ''), reverse=True)
                suggestions = [{'id': p.id, 'name': p.name} for p in sorted_recs[:4]]

        # Fallback to default active partners if suggestions is empty
        if not suggestions:
            partners = self.env['res.partner'].sudo().search([
                ('active', '=', True),
                ('is_company', '=', False),
                ('type', '=', 'contact')
            ], limit=10)
            partners = [p for p in partners if not is_own_company_partner(p.id)]
            suggestions = [{'id': p.id, 'name': p.name} for p in partners[:4]]

        return suggestions[:4]

    def validate_customer(self, name, product_category=None):
        """
        Search for a partner by name using various matching strategies.
        Requires at least 80% similarity match, otherwise fails and returns suggestions.

        :return: dict with keys: status ('found'|'not_found'|'empty'), id, name, suggestions
        """
        name = (name or '').strip()
        if not name or name == 'UNRESOLVED':
            return {'status': 'empty', 'id': None, 'name': '', 'suggestions': []}

        # Check lookup aliases first
        if product_category:
            mapped_partner = self.map_with_lookup_aliases(name, product_category=product_category, field_type='customer')
            if mapped_partner:
                return {
                    'status': 'found',
                    'id': mapped_partner.id,
                    'name': mapped_partner.name,
                    'suggestions': [{'id': mapped_partner.id, 'name': mapped_partner.name}]
                }

        # Helper to check similarity
        from difflib import SequenceMatcher
        def get_similarity(s1, s2):
            if not s1 or not s2:
                return 0.0
            return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()

        # Helper to check if partner is own company
        def is_own_company_partner(partner_id):
            p = self.env['res.partner'].sudo().browse(partner_id)
            if not p.exists():
                return False
            if p.id == self.env.company.partner_id.id:
                return True
            p_name = (p.name or '').lower()
            if 'tesro' in p_name and 'furnishing' in p_name:
                return True
            return False

        # 1. Try using name_search (natively matches references/names/emails)
        partners = self.env['res.partner'].name_search(name, limit=10)
        # Filter out own company
        partners = [p for p in partners if not is_own_company_partner(p[0])]
        
        best_candidate = None
        best_sim = 0.0
        for p in partners:
            sim = get_similarity(name, p[1])
            if sim >= 0.80 and sim > best_sim:
                best_sim = sim
                best_candidate = p

        if best_candidate:
            return {
                'status': 'found',
                'id': best_candidate[0],
                'name': best_candidate[1],
                'suggestions': [{'id': pt[0], 'name': pt[1]} for pt in partners[:4]],
            }

        # 2. Exact match (case-insensitive) fallback
        partner = self.env['res.partner'].search(
            [('name', '=ilike', name), ('active', '=', True)], limit=1
        )
        if partner and not is_own_company_partner(partner.id):
            sim = get_similarity(name, partner.name)
            if sim >= 0.80:
                return {'status': 'found', 'id': partner.id, 'name': partner.name, 'suggestions': []}

        # 3. Partial match fallback
        partner_recs = self.env['res.partner'].search(
            [('name', 'ilike', name), ('active', '=', True)], limit=10
        )
        partner_recs = partner_recs.filtered(lambda p: not is_own_company_partner(p.id))
        
        best_candidate = None
        best_sim = 0.0
        for p in partner_recs:
            sim = get_similarity(name, p.name)
            if sim >= 0.80 and sim > best_sim:
                best_sim = sim
                best_candidate = p

        if best_candidate:
            return {
                'status': 'found',
                'id': best_candidate.id,
                'name': best_candidate.name,
                'suggestions': [{'id': pt.id, 'name': pt.name} for pt in partner_recs[:4]],
            }

        # 4. Word-by-word search with smart single-match auto-resolution
        words = [w for w in name.split() if len(w) > 2]
        for word in words:
            partner = self.env['res.partner'].search(
                [('name', '=ilike', word), ('active', '=', True)], limit=2
            )
            if len(partner) == 1 and not is_own_company_partner(partner.id):
                sim = get_similarity(name, partner.name)
                if sim >= 0.80:
                    return {
                        'status': 'found',
                        'id': partner.id,
                        'name': partner.name,
                        'suggestions': [{'id': partner.id, 'name': partner.name}]
                    }

        # No match found with similarity >= 80%
        # Fall back to suggestions based on significant words matching
        suggestions = self.get_customer_suggestions(name)
        return {'status': 'not_found', 'id': None, 'name': name, 'suggestions': suggestions}

    def resolve_customer_from_text(self, text, product_category=None):
        """
        Scan raw extracted text to auto-detect and resolve a res.partner record.
        Prioritizes scanning adjacent pairs of words from the top of the document (header).
        """
        if not text:
            return None

        # Search category aliases first if category is selected
        if product_category:
            category = self.env['alias.category'].sudo().search([('type', '=', product_category)], limit=1)
            if category:
                for line in category.line_ids:
                    if line.alias_name and line.alias_name.strip().lower() in text.lower():
                        if line.partner_ids:
                            return line.partner_ids[0]
            
        import re
        
        # Helper to check if partner is own company
        def is_own_company_partner(partner_id):
            p = self.env['res.partner'].sudo().browse(partner_id)
            if not p.exists():
                return False
            if p.id == self.env.company.partner_id.id:
                return True
            p_name = (p.name or '').lower()
            if 'tesro' in p_name and 'furnishing' in p_name:
                return True
            return False

        # Helper to verify if the Odoo partner's full name is in the uploaded document
        text_lower = text.lower()
        def partner_name_in_text(partner_name):
            p_name = partner_name.lower().strip()
            # 1. Direct match
            if p_name in text_lower:
                return True
            # 2. Match without non-alphabetic leading characters (e.g. "001-")
            p_clean = re.sub(r'^[\d\s\-\.\#\_]+', '', p_name)
            if p_clean and p_clean in text_lower:
                return True
            # 3. Match without company suffix (e.g. "llc", "ltd")
            p_clean_no_suffix = re.sub(r'\b(llc|ltd|limited|inc|corp|co)\b', '', p_clean).strip()
            if p_clean_no_suffix and p_clean_no_suffix in text_lower:
                return True
            return False

        # Clean lines and split the document
        raw_lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        common_words_to_skip = {
            'purchase order', 'invoice', 'tax invoice', 'quotation', 'sales order', 'delivery note',
            'order number', 'po number', 'date', 'page', 'tel', 'fax', 'email', 'website', 'trn', 'lpo'
        }

        # Scan helper that searches adjacent pairs of words inside each line
        def scan_lines(lines):
            for line in lines:
                line_lower = line.lower()
                if len(line) < 4:
                    continue
                if any(lbl in line_lower for lbl in common_words_to_skip):
                    continue
                
                # Tokenize line into words
                words = re.findall(r'\b\w+\b', line)
                if len(words) >= 2:
                    for i in range(len(words) - 1):
                        w1, w2 = words[i], words[i+1]
                        # Skip if both words are just numbers or too short
                        if (w1.isdigit() and w2.isdigit()) or (len(w1) < 2 and len(w2) < 2):
                            continue
                        query = f"{w1} {w2}"
                        
                        # Search in Odoo res.partner
                        partners = self.env['res.partner'].sudo().name_search(query, limit=5)
                        for p in partners:
                            if not is_own_company_partner(p[0]):
                                # Check if Odoo partner's full name is in the document text
                                if partner_name_in_text(p[1]):
                                    return self.env['res.partner'].sudo().browse(p[0])
            return None

        # 1. First scan: First 3 rows only
        res_partner = scan_lines(raw_lines[:3])
        if res_partner:
            return res_partner

        # 2. Fallback: Exact match of any entire line within the first 3 rows of the header
        for line in raw_lines[:3]:
            line_lower = line.lower()
            if len(line) < 4 or line.isdigit() or any(lbl in line_lower for lbl in common_words_to_skip):
                continue
            partner = self.env['res.partner'].sudo().search([
                ('name', '=ilike', line),
                ('active', '=', True)
            ], limit=1)
            if partner and not is_own_company_partner(partner.id):
                return partner

        return None

    def _get_category_ids_for_type(self, product_category):
        if not product_category:
            return []
        categories = self.env['product.category'].sudo().search([])
        categ_ids = []
        for categ in categories:
            categ_type = None
            # Check custom Odoo category type from database first
            if hasattr(categ, 'categ_types') and categ.categ_types:
                if categ.categ_types == 'tracks':
                    categ_type = 'track'
                elif categ.categ_types in ['fabric', 'blind_fabrics']:
                    categ_type = 'fabric'
                elif categ.categ_types == 'blind':
                    categ_type = 'blind'
            
            # Fallback to string matching rules if categ_types is not defined or not set
            if not categ_type:
                name = (categ.name or '').strip()
                name_lower = name.lower()
                if 'track' in name_lower:
                    categ_type = 'track'
                elif 'fabric' in name_lower or name_lower in ['executive edition', 'sunscreen saga', 'karl kimmich', 'pelmet']:
                    categ_type = 'fabric'
                elif 'blind' in name_lower or name_lower.startswith('tb') or name_lower.startswith('ts') or name_lower in ['titos']:
                    categ_type = 'blind'
                
            if categ_type == product_category:
                categ_ids.append(categ.id)
        return categ_ids

    def validate_product(self, name, product_category=None, partner_id=None):
        """
        Search for a product by name using various matching strategies.

        :return: dict with keys: status, id, name, suggestions
        """
        name = (name or '').strip()
        if not name or name == 'UNRESOLVED':
            return {'status': 'empty', 'id': None, 'name': '', 'suggestions': []}

        # Check lookup aliases first
        if product_category:
            mapped_product = self.map_with_lookup_aliases(name, product_category=product_category, partner_id=partner_id, field_type='product')
            if mapped_product:
                return {
                    'status': 'found',
                    'id': mapped_product.id,
                    'name': mapped_product.display_name,
                    'suggestions': [{'id': mapped_product.id, 'name': mapped_product.display_name}]
                }

        categ_ids = self._get_category_ids_for_type(product_category) if product_category else []

        # Try parsing code in brackets (e.g. "[FURN_6741] Large Meeting Table")
        import re
        code, name_part = None, name
        match = re.match(r'^\[(.*?)\]\s*(.*)$', name)
        if match:
            code = match.group(1).strip()
            name_part = match.group(2).strip()

        # 1. Search by code if present
        domain = [('active', '=', True)]
        if categ_ids:
            domain.append(('categ_id', 'in', categ_ids))

        if code:
            product = self.env['product.product'].search(
                domain + [('default_code', '=ilike', code)], limit=1
            )
            if product:
                return {'status': 'found', 'id': product.id, 'name': product.display_name, 'suggestions': []}

        # 2. Try name_search (this searches code and name natively in Odoo)
        ns_domain = [('active', '=', True)]
        if categ_ids:
            ns_domain.append(('categ_id', 'in', categ_ids))
        ns_results = self.env['product.product'].name_search(name, args=ns_domain, limit=5)
        if ns_results:
            best_id = ns_results[0][0]
            best_product = self.env['product.product'].browse(best_id)
            return {
                'status': 'found',
                'id': best_product.id,
                'name': best_product.display_name,
                'suggestions': [{'id': r[0], 'name': r[1]} for r in ns_results],
            }

        # 3. If name_part is different from name, try name_search on name_part
        if name_part != name:
            ns_results = self.env['product.product'].name_search(name_part, args=ns_domain, limit=5)
            if ns_results:
                best_id = ns_results[0][0]
                best_product = self.env['product.product'].browse(best_id)
                return {
                    'status': 'found',
                    'id': best_product.id,
                    'name': best_product.display_name,
                    'suggestions': [{'id': r[0], 'name': r[1]} for r in ns_results],
                }

        # 4. Standard Exact / Partial search on name (fallback)
        product = self.env['product.product'].search(
            ns_domain + [('name', '=ilike', name_part)], limit=1
        )
        if product:
            return {'status': 'found', 'id': product.id, 'name': product.display_name, 'suggestions': []}

        product = self.env['product.product'].search(
            ns_domain + [('name', 'ilike', name_part), ('sale_ok', '=', True)], limit=5
        )
        if product:
            best = product[0]
            return {
                'status': 'found',
                'id': best.id,
                'name': best.display_name,
                'suggestions': [{'id': p.id, 'name': p.display_name} for p in product],
            }

        # 5. Try product template
        tmpl = self.env['product.template'].search(
            ns_domain + [('name', 'ilike', name_part), ('sale_ok', '=', True)], limit=5
        )
        if tmpl:
            best = tmpl[0].product_variant_ids[:1]
            if best:
                return {
                    'status': 'found',
                    'id': best.id,
                    'name': tmpl[0].name,
                    'suggestions': [{'id': t.id, 'name': t.name} for t in tmpl],
                }

        # 6. Try smart normalized search fallback
        normalized_product = self._search_product_by_normalized_name(name_part, ns_domain)
        if normalized_product:
            return {
                'status': 'found',
                'id': normalized_product.id,
                'name': normalized_product.display_name,
                'suggestions': [{'id': normalized_product.id, 'name': normalized_product.display_name}]
            }

        return {'status': 'not_found', 'id': None, 'name': name, 'suggestions': []}

    def _normalize_product_name(self, val):
        if not val:
            return ""
        import re
        val = val.lower()
        val = re.sub(r'\d+', lambda m: str(int(m.group(0))), val)
        val = re.sub(r'[^a-z0-9]', '', val)
        return val

    def _search_product_by_normalized_name(self, search_name, domain):
        search_norm = self._normalize_product_name(search_name)
        if not search_norm:
            return None
        
        # Search all active products matching the domain
        products = self.env['product.product'].search(domain)
        for prod in products:
            if prod.default_code and self._normalize_product_name(prod.default_code) == search_norm:
                return prod
            if prod.name and self._normalize_product_name(prod.name) == search_norm:
                return prod
        return None


    def search_partners(self, query, limit=10):
        """Search partners by name for autocomplete."""
        if not query or len(query) < 2:
            return []
        partners = self.env['res.partner'].search(
            [('name', 'ilike', query), ('active', '=', True)], limit=limit
        )
        return [{'id': p.id, 'name': p.name, 'email': p.email or ''} for p in partners]

    def search_products(self, query, limit=10, product_category=None):
        """Search products by name for autocomplete, optionally filtered by product_category."""
        if not query or len(query) < 2:
            return []
        
        domain = [('name', 'ilike', query), ('active', '=', True), ('sale_ok', '=', True)]
        if product_category:
            categ_ids = self._get_category_ids_for_type(product_category)
            if categ_ids:
                domain.append(('categ_id', 'in', categ_ids))

        products = self.env['product.product'].search(domain, limit=limit)
        return [
            {
                'id': p.id,
                'name': p.name,
                'price': p.list_price,
                'uom': p.uom_id.name if p.uom_id else 'Units',
            }
            for p in products
        ]

    def validate_tax(self, tax_val):
        """
        Search for a sales tax by amount or name.
        :param tax_val: float, int, or str
        :return: account.tax record or None
        """
        if tax_val is None or tax_val == '':
            return None
            
        Tax = self.env['account.tax'].sudo()
        company_id = self.env.company.id
        domain_base = [('type_tax_use', '=', 'sale'), ('active', '=', True), ('company_id', 'in', [company_id, False])]
        
        # 1. If it's a string, try matching by name exactly (case insensitive) or ilike
        if isinstance(tax_val, str):
            tax_val_clean = tax_val.strip()
            if not tax_val_clean:
                return None
            # If the string represents a percentage, extract the numeric value
            # e.g., "15%" -> 15.0
            import re
            pct_match = re.search(r'([\d\.]+)\s*%', tax_val_clean)
            if pct_match:
                try:
                    amount = float(pct_match.group(1))
                    tax = Tax.search(domain_base + [('amount', '=', amount)], limit=1)
                    if tax:
                        return tax
                    if 0.0 < amount < 1.0:
                        tax = Tax.search(domain_base + [('amount', '=', amount * 100.0)], limit=1)
                        if tax:
                            return tax
                except ValueError:
                    pass
            
            # Direct name match
            tax = Tax.search(domain_base + [('name', '=ilike', tax_val_clean)], limit=1)
            if tax:
                return tax
            
            # Try to convert whole string to float (e.g. "15" -> 15.0)
            try:
                amount = float(tax_val_clean)
                tax = Tax.search(domain_base + [('amount', '=', amount)], limit=1)
                if tax:
                    return tax
                if 0.0 < amount < 1.0:
                    tax = Tax.search(domain_base + [('amount', '=', amount * 100.0)], limit=1)
                    if tax:
                        return tax
            except ValueError:
                pass
                
        # 2. If it's already a float or int
        elif isinstance(tax_val, (int, float)):
            amount = float(tax_val)
            tax = Tax.search(domain_base + [('amount', '=', amount)], limit=1)
            if tax:
                return tax
            if 0.0 < amount < 1.0:
                tax = Tax.search(domain_base + [('amount', '=', amount * 100.0)], limit=1)
                if tax:
                    return tax
                
        return None

    def validate_payment_term(self, name):
        """
        Search for a payment term by name.
        :return: dict with keys: status, id, name, suggestions
        """
        name = (name or '').strip()
        if not name or name == 'UNRESOLVED':
            return {'status': 'empty', 'id': None, 'name': '', 'suggestions': []}
            
        # Try exact search
        term = self.env['account.payment.term'].search([('name', '=ilike', name)], limit=1)
        if term:
            return {'status': 'found', 'id': term.id, 'name': term.name, 'suggestions': []}
            
        # Try name_search
        results = self.env['account.payment.term'].name_search(name, limit=5)
        if results:
            best_id = results[0][0]
            best_term = self.env['account.payment.term'].browse(best_id)
            return {
                'status': 'found',
                'id': best_term.id,
                'name': best_term.name,
                'suggestions': [{'id': r[0], 'name': r[1]} for r in results]
            }
            
        # Try partial match
        term = self.env['account.payment.term'].search([('name', 'ilike', name)], limit=5)
        if term:
            return {
                'status': 'found',
                'id': term[0].id,
                'name': term[0].name,
                'suggestions': [{'id': t.id, 'name': t.name} for t in term]
            }
            
        return {'status': 'not_found', 'id': None, 'name': name, 'suggestions': []}

    def validate_salesperson(self, name):
        """
        Search for a salesperson (user) by name.
        :return: dict with keys: status, id, name, suggestions
        """
        name = (name or '').strip()
        if not name or name == 'UNRESOLVED':
            return {'status': 'empty', 'id': None, 'name': '', 'suggestions': []}
            
        # Try exact name match in res.users
        results = self.env['res.users'].name_search(name, limit=5)
        if results:
            best_id = results[0][0]
            best_user = self.env['res.users'].browse(best_id)
            return {
                'status': 'found',
                'id': best_user.id,
                'name': best_user.name,
                'suggestions': [{'id': r[0], 'name': r[1]} for r in results]
            }
            
        # Try exact / partial search on partner name
        user = self.env['res.users'].search([('name', 'ilike', name), ('active', '=', True)], limit=5)
        if user:
            return {
                'status': 'found',
                'id': user[0].id,
                'name': user[0].name,
                'suggestions': [{'id': u.id, 'name': u.name} for u in user]
            }
            
        return {'status': 'not_found', 'id': None, 'name': name, 'suggestions': []}

    def search_payment_terms(self, query, limit=10):
        """Search payment terms for autocomplete."""
        if not query or len(query) < 2:
            return []
        terms = self.env['account.payment.term'].search([
            ('name', 'ilike', query)
        ], limit=limit)
        return [{'id': t.id, 'name': t.name} for t in terms]

    def search_salespersons(self, query, limit=10):
        """Search salespeople (active users) for autocomplete."""
        if not query or len(query) < 2:
            return []
        users = self.env['res.users'].search([
            ('name', 'ilike', query),
            ('active', '=', True)
        ], limit=limit)
        return [{'id': u.id, 'name': u.name} for u in users]
