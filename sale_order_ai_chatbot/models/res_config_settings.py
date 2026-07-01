# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    gemini_api_key = fields.Char(
        string='Gemini API Key',
        config_parameter='sale_order_ai_chatbot.gemini_api_key',
        help='Your Gemini API key from Google AI Studio',
    )
    gemini_model = fields.Char(
        string='Gemini Chat Model',
        config_parameter='sale_order_ai_chatbot.gemini_model',
        default='gemini-2.5-flash',
        help='Gemini model for conversation and order extraction.',
    )
    gemini_vision_model = fields.Char(
        string='Gemini Vision Model',
        config_parameter='sale_order_ai_chatbot.gemini_vision_model',
        default='gemini-2.5-flash',
        help='Gemini vision model for image OCR and document understanding.',
    )
    gemini_max_tokens = fields.Integer(
        string='Max Response Tokens',
        config_parameter='sale_order_ai_chatbot.gemini_max_tokens',
        default=4096,
        help='Maximum number of tokens in AI responses.',
    )

    # Deprecated Groq fields to prevent server crash before module upgrade
    groq_api_key = fields.Char(string='Groq API Key (Deprecated)')
    groq_model = fields.Char(string='Groq Chat Model (Deprecated)')
    groq_vision_model = fields.Char(string='Groq Vision Model (Deprecated)')
    groq_max_tokens = fields.Integer(string='Groq Max Tokens (Deprecated)')

