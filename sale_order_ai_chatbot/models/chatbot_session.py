# -*- coding: utf-8 -*-
import json
import logging
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class SaleChatbotSession(models.Model):
    _name = 'sale.chatbot.session'
    _description = 'AI Sales Order Chatbot Session'
    _order = 'create_date desc'
    _inherit = ['mail.thread']

    name = fields.Char(
        string='Session Name',
        required=True,
        default=lambda self: _('New Chat Session'),
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('processing', 'Processing'),
            ('ready', 'Ready to Submit'),
            ('done', 'Order Created'),
        ],
        string='Status',
        default='draft',
        tracking=True,
    )
    message_ids = fields.One2many(
        comodel_name='sale.chatbot.message',
        inverse_name='session_id',
        string='Messages',
    )
    order_data = fields.Text(
        string='Extracted Order Data (JSON)',
        default='{}',
    )
    sale_order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Generated Sale Order',
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    user_id = fields.Many2one(
        comodel_name='res.users',
        string='Sales User',
        default=lambda self: self.env.user,
    )
    confidence_score = fields.Float(
        string='AI Confidence (%)',
        default=0.0,
    )
    product_category = fields.Selection(
        selection=[
            ('blind', 'Blind'),
            ('fabric', 'Fabric'),
            ('track', 'Track'),
        ],
        string='Product Category',
        tracking=True,
    )
    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        relation='sale_chatbot_session_attachment_rel',
        column1='session_id',
        column2='attachment_id',
        string='Uploaded Files',
    )
    message_count = fields.Integer(
        string='Message Count',
        compute='_compute_message_count',
    )
    order_line_count = fields.Integer(
        string='Order Lines',
        compute='_compute_order_line_count',
    )

    @api.depends('message_ids')
    def _compute_message_count(self):
        for rec in self:
            rec.message_count = len(rec.message_ids)

    @api.depends('order_data')
    def _compute_order_line_count(self):
        for rec in self:
            try:
                data = json.loads(rec.order_data or '{}')
                if 'orders' in data and isinstance(data['orders'], list):
                    rec.order_line_count = sum(len(o.get('order_lines', [])) for o in data['orders'])
                else:
                    rec.order_line_count = len(data.get('order_lines', []))
            except Exception:
                rec.order_line_count = 0

    def get_order_data_dict(self):
        """Return parsed order data as dict."""
        self.ensure_one()
        try:
            return json.loads(self.order_data or '{}')
        except Exception:
            return {}

    def set_order_data_dict(self, data):
        """Save order data dict as JSON string."""
        self.ensure_one()
        self.order_data = json.dumps(data, ensure_ascii=False, indent=2)

    def action_create_sale_order(self, order_data=None):
        """
        Create a standard sale.order from extracted order data.
        Returns the created sale.order record.
        """
        self.ensure_one()
        
        # Parse existing order data
        session_data = self.get_order_data_dict()
        
        # Determine if we are processing a single order out of multiple orders
        is_multiple = 'orders' in session_data and isinstance(session_data['orders'], list)
        
        # If no order_data was passed, default to the first order if multiple, or the root if single
        if not order_data:
            if is_multiple:
                # Find the first not-yet-created order
                pending_orders = [o for o in session_data['orders'] if not o.get('sale_order_id')]
                if pending_orders:
                    data = pending_orders[0]
                else:
                    data = session_data['orders'][0]
            else:
                data = session_data
        else:
            data = order_data

        if not data:
            raise UserError(_('No order data available to create a Sales Order.'))

        # --- Resolve customer ---
        partner = self._resolve_partner(data)
        if not partner:
            raise UserError(_(
                'Customer "%s" could not be found in the system. '
                'Please correct the customer name in the preview panel.',
                data.get('customer', '')
            ))

        # --- Build order lines ---
        order_line_vals = []
        for line in data.get('order_lines', []):
            product = self._resolve_product(line)
            if not product:
                _logger.warning('Product not resolved: %s', line.get('product'))
                continue
            qty = float(line.get('qty', line.get('quantity', 1)) or 1)
            price = line.get('price') or line.get('unit_price')
            
            # Default UOM from product
            uom_name = line.get('uom')
            product_uom = product.uom_id.id
            if uom_name:
                uom = self.env['uom.uom'].search([('name', '=ilike', uom_name.strip())], limit=1)
                if uom:
                    product_uom = uom.id

            # Height and Width
            height = line.get('height')
            try:
                height_val = float(height) if height is not None and str(height).strip() != '' else 1.0
            except (ValueError, TypeError):
                height_val = 1.0
            if height_val <= 0.0:
                height_val = 1.0

            width = line.get('width')
            try:
                width_val = float(width) if width is not None and str(width).strip() != '' else 1.0
            except (ValueError, TypeError):
                width_val = 1.0
            if width_val <= 0.0:
                width_val = 1.0

            # Discount
            discount = line.get('discount')
            try:
                discount_val = float(discount) if discount is not None and str(discount).strip() != '' else 0.0
            except (ValueError, TypeError):
                discount_val = 0.0

            # Price unit (default to product list price if empty/none)
            if price is not None and str(price).strip() != '':
                try:
                    price_unit = float(price)
                except (ValueError, TypeError):
                    price_unit = product.lst_price
            else:
                price_unit = product.lst_price

            # Taxes
            if line.get('tax_ids'):
                tax_ids = line['tax_ids']
            elif line.get('tax_id'):
                tax_ids = [line['tax_id']]
            else:
                tax_str = str(line.get('tax') or '').strip().lower()
                if tax_str in ('0', '0%', '0.0', 'exempt', 'none', 'no tax', 'free'):
                    tax_ids = []
                else:
                    product_taxes = product.taxes_id.filtered(lambda t: t.company_id == self.company_id)
                    tax_ids = product_taxes.ids

            order_line_vals.append((0, 0, {
                'product_id': product.id,
                'product_uom_qty': qty,
                'product_uom': product_uom,
                'name': product.name,
                'price_unit': price_unit,
                'height': height_val,
                'width': width_val,
                'discount_amount': discount_val,
                'discount': 0.0,
                'tax_id': [(6, 0, tax_ids)],
            }))

        if not order_line_vals:
            raise UserError(_('No valid order lines could be resolved. Please check product names in the preview panel.'))

        # --- Delivery date ---
        commitment_date = False
        delivery_str = data.get('delivery_date', '')
        if delivery_str:
            try:
                from datetime import datetime
                commitment_date = datetime.strptime(delivery_str[:10], '%Y-%m-%d')
            except Exception:
                pass

        # --- Quotation / Order date ---
        date_order = False
        quotation_str = data.get('quotation_date', '') or data.get('order_date', '')
        if quotation_str:
            try:
                from datetime import datetime
                date_order = datetime.strptime(quotation_str[:10], '%Y-%m-%d')
            except Exception:
                pass

        # --- Create sale.order ---
        user_id = int(data.get('user_id')) if data.get('user_id') else self.user_id.id
        order_vals = {
            'partner_id': partner.id,
            'order_line': order_line_vals,
            'note': data.get('notes', ''),
            'user_id': user_id,
            'company_id': self.company_id.id,
        }
        if data.get('lpo_number'):
            order_vals['client_order_ref'] = str(data['lpo_number']).replace('#', '').strip()
        if data.get('payment_term_id'):
            order_vals['payment_term_id'] = int(data['payment_term_id'])
        if commitment_date:
            order_vals['commitment_date'] = commitment_date
        if date_order:
            order_vals['date_order'] = date_order

        sale_order = self.env['sale.order'].create(order_vals)
        
        # --- Update session state and json ---
        if is_multiple:
            matched = False
            order_key = data.get('key')
            # 1. Try matching by key
            if order_key:
                for o in session_data['orders']:
                    if o.get('key') == order_key:
                        o['sale_order_id'] = sale_order.id
                        o['sale_order_name'] = sale_order.name
                        o['state'] = 'done'
                        matched = True
                        break
            
            # 2. Fallback to LPO or customer match if not matched by key
            if not matched:
                lpo = data.get('lpo_number')
                for o in session_data['orders']:
                    if (lpo and o.get('lpo_number') == lpo) or (o.get('customer') == data.get('customer') and not o.get('sale_order_id')):
                        o['sale_order_id'] = sale_order.id
                        o['sale_order_name'] = sale_order.name
                        o['state'] = 'done'
                        matched = True
                        break
            
            # 3. Fallback to any not-yet-created order
            if not matched:
                for o in session_data['orders']:
                    if not o.get('sale_order_id'):
                        o['sale_order_id'] = sale_order.id
                        o['sale_order_name'] = sale_order.name
                        o['state'] = 'done'
                        matched = True
                        break
            all_done = all(o.get('state') == 'done' for o in session_data['orders'])
            
            self.set_order_data_dict(session_data)
            if all_done:
                self.sale_order_id = sale_order
                self.state = 'done'
            else:
                self.state = 'processing'
        else:
            self.sale_order_id = sale_order
            self.state = 'done'
            data['sale_order_id'] = sale_order.id
            data['sale_order_name'] = sale_order.name
            data['state'] = 'done'
            self.set_order_data_dict(data)

        # Add confirmation message
        self.env['sale.chatbot.message'].create({
            'session_id': self.id,
            'role': 'assistant',
            'content': _(
                '✅ Sales Order **%s** has been created successfully!\n\n'
                'Customer: %s\n'
                'Lines: %d products\n\n'
                'You can find it in Sales → Quotations.',
                sale_order.name,
                partner.name,
                len(sale_order.order_line),
            ),
            'message_type': 'order_update',
        })

        return sale_order

    def _resolve_partner(self, data):
        """Fuzzy search for partner by name. If not found, create one."""
        customer_name = (data.get('customer') or '').strip()
        if not customer_name:
            return None

        # Helper to check similarity
        from difflib import SequenceMatcher
        def get_similarity(s1, s2):
            if not s1 or not s2:
                return 0.0
            return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()

        # Helper to check if partner is own company
        def is_own_company(p):
            if not p:
                return False
            if p.id == self.env.company.partner_id.id:
                return True
            p_name = (p.name or '').lower()
            if 'tesro' in p_name and 'furnishing' in p_name:
                return True
            return False

        # Try by stored ID first
        if data.get('customer_id'):
            partner = self.env['res.partner'].browse(int(data['customer_id'])).exists()
            if partner and partner.active and not is_own_company(partner):
                return partner

        # Try using name_search (natively matches references/names)
        partners = self.env['res.partner'].name_search(customer_name, limit=5)
        for p_val in partners:
            partner = self.env['res.partner'].browse(p_val[0])
            if partner and partner.active and not is_own_company(partner):
                if get_similarity(customer_name, partner.name) >= 0.80:
                    return partner

        # Exact match
        partner = self.env['res.partner'].search(
            [('name', '=ilike', customer_name), ('active', '=', True)], limit=1
        )
        if partner and not is_own_company(partner):
            if get_similarity(customer_name, partner.name) >= 0.80:
                return partner

        # Partial match
        partner = self.env['res.partner'].search(
            [('name', 'ilike', customer_name), ('active', '=', True)], limit=1
        )
        if partner and not is_own_company(partner):
            if get_similarity(customer_name, partner.name) >= 0.80:
                return partner

        # If not found, create a new partner with the name exactly as the user typed it in the preview
        return self.env['res.partner'].create({
            'name': customer_name,
        })

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

    def _resolve_product(self, line):
        """Fuzzy search for product by name. If not found, create one."""
        product_name = (line.get('product') or '').strip()
        if not product_name:
            return None
        # Try by stored ID first
        if line.get('product_id'):
            prod = self.env['product.product'].browse(int(line['product_id'])).exists()
            if prod:
                return prod

        # Get category domain from product category if set
        categ_ids = self._get_category_ids_for_type(self.product_category) if self.product_category else []

        # Try parsing code in brackets (e.g. "[FURN_6741] Large Meeting Table")
        import re
        code, name_part = None, product_name
        match = re.match(r'^\[(.*?)\]\s*(.*)$', product_name)
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
                return product

        # 2. Try name_search (searches default_code and name in Odoo)
        ns_domain = [('active', '=', True)]
        if categ_ids:
            ns_domain.append(('categ_id', 'in', categ_ids))
        products = self.env['product.product'].name_search(product_name, args=ns_domain, limit=1)
        if products:
            return self.env['product.product'].browse(products[0][0])

        # 3. If name_part is different, try name_search on name_part
        if name_part != product_name:
            products = self.env['product.product'].name_search(name_part, args=ns_domain, limit=1)
            if products:
                return self.env['product.product'].browse(products[0][0])

        # 4. Fallback search by name
        prod = self.env['product.product'].search(
            ns_domain + [('name', '=ilike', name_part)], limit=1
        )
        if prod:
            return prod
        prod = self.env['product.product'].search(
            ns_domain + [('name', 'ilike', name_part)], limit=1
        )
        if prod:
            return prod

        # 5. Smart normalized search fallback
        normalized_product = self._search_product_by_normalized_name(name_part, ns_domain)
        if normalized_product:
            return normalized_product

        # If not found, create a new product with the name exactly as the user typed it in the preview
        product_vals = {
            'name': product_name,
            'sale_ok': True,
            'active': True,
        }
        if categ_ids:
            product_vals['categ_id'] = categ_ids[0]
        return self.env['product.product'].create(product_vals)

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


    def action_reset(self):
        """Reset session to start a new conversation."""
        self.ensure_one()
        self.message_ids.unlink()
        self.order_data = '{}'
        self.state = 'draft'
        self.confidence_score = 0.0
        self.sale_order_id = False
        self.product_category = False
        self.name = _('New Chat Session')

    def check_and_reset_done_session(self):
        """If the session was completed (done), reset its order fields so the user can continue chatting."""
        self.ensure_one()
        if self.state == 'done':
            self.write({
                'order_data': '{}',
                'state': 'draft',
                'confidence_score': 0.0,
                'product_category': False,
            })

    def action_open_sale_order(self):
        """Open the generated sale order."""
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError(_('No Sales Order has been created yet.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def get_conversation_history(self):
        """Return messages formatted for Gemini API."""
        self.ensure_one()
        history = []
        for msg in self.message_ids.sorted('create_date'):
            if msg.role in ('user', 'assistant'):
                history.append({
                    'role': msg.role,
                    'content': msg.content or '',
                })
        return history

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == _('New Chat Session'):
                seq = self.env['ir.sequence'].next_by_code('sale.chatbot.session') or '/'
                vals['name'] = _('Chat Session %s') % seq
        return super().create(vals_list)

