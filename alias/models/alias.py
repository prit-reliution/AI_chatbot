# -*- coding: utf-8 -*-
from odoo import api, fields, models

class AliasCategory(models.Model):
    _name = 'alias.category'
    _description = 'Lookup Alias Category'
    _order = 'sequence'

    name = fields.Char(string='Category Name', required=True)
    type = fields.Selection([
        ('blind', 'Blind'),
        ('fabric', 'Fabric'),
        ('track', 'Track')
    ], string='Type', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    line_ids = fields.One2many('alias.line', 'category_id', string='Alias Lines')
    allowed_product_category_ids = fields.Many2many(
        'product.category',
        string='Allowed Product Categories',
        compute='_compute_allowed_product_category_ids',
        store=False
    )

    @api.depends('type')
    def _compute_allowed_product_category_ids(self):
        for rec in self:
            if not rec.type:
                rec.allowed_product_category_ids = self.env['product.category']
                continue
            # Logic similar to chatbot session product category filtering
            categories = self.env['product.category'].sudo().search([])
            categ_ids = []
            for categ in categories:
                categ_type = None
                if hasattr(categ, 'categ_types') and categ.categ_types:
                    if categ.categ_types == 'tracks':
                        categ_type = 'track'
                    elif categ.categ_types in ['fabric', 'blind_fabrics']:
                        categ_type = 'fabric'
                    elif categ.categ_types == 'blind':
                        categ_type = 'blind'
                
                if not categ_type:
                    name = (categ.name or '').strip()
                    name_lower = name.lower()
                    if 'track' in name_lower:
                        categ_type = 'track'
                    elif 'fabric' in name_lower or name_lower in ['executive edition', 'sunscreen saga', 'karl kimmich', 'pelmet']:
                        categ_type = 'fabric'
                    elif 'blind' in name_lower or name_lower.startswith('tb') or name_lower.startswith('ts') or name_lower in ['titos']:
                        categ_type = 'blind'
                    
                if categ_type == rec.type:
                    categ_ids.append(categ.id)
            rec.allowed_product_category_ids = [(6, 0, categ_ids)]


class AliasLine(models.Model):
    _name = 'alias.line'
    _description = 'Lookup Alias Line'

    category_id = fields.Many2one('alias.category', string='Category', required=True, ondelete='cascade')
    alias_name = fields.Char(string='Alias Name', required=True)
    product_ids = fields.Many2many(
        'product.product',
        'alias_line_product_rel',
        'line_id',
        'product_id',
        string='Products',
        required=True
    )
    partner_ids = fields.Many2many(
        'res.partner',
        'alias_line_partner_rel',
        'line_id',
        'partner_id',
        string='Partners'
    )
    allowed_product_category_ids = fields.Many2many(
        'product.category',
        string='Allowed Product Categories',
        related='category_id.allowed_product_category_ids',
        readonly=True
    )
