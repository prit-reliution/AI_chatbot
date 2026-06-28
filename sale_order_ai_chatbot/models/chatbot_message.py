# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleChatbotMessage(models.Model):
    _name = 'sale.chatbot.message'
    _description = 'AI Sales Order Chatbot Message'
    _order = 'create_date asc, id asc'

    session_id = fields.Many2one(
        comodel_name='sale.chatbot.session',
        string='Session',
        required=True,
        ondelete='cascade',
        index=True,
    )
    role = fields.Selection(
        selection=[
            ('user', 'User'),
            ('assistant', 'AI Assistant'),
            ('system', 'System'),
        ],
        string='Role',
        required=True,
        default='user',
    )
    content = fields.Text(
        string='Message Content',
    )
    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        relation='sale_chatbot_message_attachment_rel',
        column1='message_id',
        column2='attachment_id',
        string='Attachments',
    )
    message_type = fields.Selection(
        selection=[
            ('text', 'Text'),
            ('file', 'File Upload'),
            ('order_update', 'Order Update'),
            ('category_selection', 'Category Selection'),
        ],
        string='Message Type',
        default='text',
    )
    extracted_text = fields.Text(
        string='Extracted Document Text',
        help='Text extracted from uploaded documents via OCR or parsing.',
    )
    create_date = fields.Datetime(
        string='Timestamp',
        readonly=True,
    )
