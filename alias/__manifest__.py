# -*- coding: utf-8 -*-
{
    'name': 'Lookup Aliases',
    'version': '17.0.1.0.0',
    'category': 'Sales',
    'summary': 'B2B Lookup Aliases for products and customers',
    'description': """
Lookup Aliases
==============
Defines alias categories and lookup lines.
    """,
    'author': 'Antigravity',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'sale',
        'product',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/alias_data.xml',
        'views/alias_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
