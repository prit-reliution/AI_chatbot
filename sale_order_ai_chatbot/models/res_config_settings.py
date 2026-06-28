# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    groq_api_key = fields.Char(
        string='Groq API Key',
        config_parameter='sale_order_ai_chatbot.groq_api_key',
        help='Your Groq API key from https://console.groq.com/keys',
    )
    groq_model = fields.Char(
        string='Groq Chat Model',
        config_parameter='sale_order_ai_chatbot.groq_model',
        default='llama-3.3-70b-versatile',
        help='Groq model for conversation and order extraction.',
    )
    groq_vision_model = fields.Char(
        string='Groq Vision Model',
        config_parameter='sale_order_ai_chatbot.groq_vision_model',
        default='qwen/qwen3.6-27b',
        help='Groq vision model for image OCR and document understanding.',
    )
    groq_max_tokens = fields.Integer(
        string='Max Response Tokens',
        config_parameter='sale_order_ai_chatbot.groq_max_tokens',
        default=4096,
        help='Maximum number of tokens in AI responses.',
    )
