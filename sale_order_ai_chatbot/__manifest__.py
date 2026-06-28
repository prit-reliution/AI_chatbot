# -*- coding: utf-8 -*-
{
    'name': 'Sale Order AI Chatbot',
    'version': '17.0.1.0.0',
    'category': 'Sales',
    'summary': 'AI-powered chatbot to generate Sales Orders from natural language, documents, images and PDFs',
    'description': """
Sale Order AI Chatbot
=====================

An independent AI-powered Sales Order assistant for Odoo 19.

Features:
- Modern split-panel chat UI (ChatGPT-style)
- Groq LLM integration for natural language understanding
- Groq Vision OCR for images, scanned PDFs, and screenshots
- PDF, DOCX, XLSX, PNG, JPG, JPEG document parsing
- Drag-and-drop file uploads
- Live editable Sales Order preview panel
- Confidence scoring and validation
- Creates standard Odoo sale.order records
- Multi-turn conversation memory within sessions
- Full session history
    """,
    'author': 'Antigravity',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'sale',
        'mail',
        'base_setup',
        'web',
        'alias',
    ],
    'data': [
        # Security — must load first
        'security/security_groups.xml',
        'security/ir.model.access.csv',

        # Data defaults
        'data/ir_config_parameter.xml',

        # Views
        'views/chatbot_session_list_view.xml',
        'views/chatbot_main_view.xml',
        'views/res_config_settings_views.xml',
        'views/chatbot_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sale_order_ai_chatbot/static/src/css/chatbot_styles.css',
            'sale_order_ai_chatbot/static/src/js/sale_order_chatbot.js',
            'sale_order_ai_chatbot/static/src/js/chat_panel.js',
            'sale_order_ai_chatbot/static/src/js/order_preview_panel.js',
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
