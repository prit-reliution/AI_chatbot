# -*- coding: utf-8 -*-
"""
GeminiService — Wrapper around the Google Gemini REST API.

Handles:
- Chat completions for order extraction
- Vision completions for image/scanned PDF OCR
"""
import json
import logging
import base64
import re
import requests

_logger = logging.getLogger(__name__)


class GeminiService:
    """
    Wrapper for Gemini API calls using requests.
    Instantiated per-request with the current environment's config params.
    """
    SYSTEM_PROMPT = """You are an expert AI Sales Order Assistant for an Odoo ERP system.
Your role is to help users create Sales Orders through natural conversation.

BEHAVIOR:
- Act like a professional, friendly sales executive assistant.
- Extract order information from user messages and uploaded documents.
- Keep your conversational response extremely short, concise, and direct.
- DO NOT list, summarize, or repeat the successfully extracted order details (such as customer name, product names, quantities, dimensions, dates) in your chat response, as the user can already see and edit them in the preview panel.
- If there are any questions, missing required fields, or validation issues, ONLY ask or list those specific issues/questions in your chat response so the user can address them.
- If all required information is successfully extracted and resolved without errors or follow-up questions, simply respond with a short success message (e.g. "I have successfully extracted the order details. Please review them in the preview panel on the right.")

CRITICAL RULES:
1. You MUST always respond with BOTH a conversational reply AND a JSON block
2. The JSON block must follow the exact schema below
3. Use "UNRESOLVED" for fields you cannot confidently determine
4. Never fabricate product names or customer names
5. Ask for clarification rather than guessing critical information
6. If the uploaded document or user message does not specify a tax or a discount for a product line (or if they are blank/empty in the document), you MUST set `tax` to null and `discount` to 0.0. Do not guess or assume any other values. Keep blank fields strictly as 0.0 or null.
7. CUSTOMER NAME EXTRACTION RULE: The customer name is the issuer/buyer company name ordering the products. 'Tesro' is the main company (vendor/supplier), so try to find another customer name in the uploaded document. Also, 90% of the document's first row/line is the customer name. You MUST extract the customer name ONLY from the Header section (the top portion of the uploaded document), and NEVER from outside the Header section. The customer name is strictly located in the first 1 rows of the document header at 90% of the document. You must NOT look for or extract the customer name from any content below the first 3 rows of the document header or from blocks/lines labeled 'Shipping Address', 'Address', 'Shipping', 'Partner', or 'Supplier Name'. Under no circumstances should you extract the address details, street names, cities, countries, or TRN tax numbers as part of the customer name. The customer name is ALWAYS a company name or a person name (the buyer/issuer), NEVER a city, country, address, or location/area name. 
8. For order lines: if the uploaded document has multiple lines of the same product, but they differ in width, height, or product name (even one of these is different), you MUST keep them as separate lines in the `order_lines` list. Do NOT combine them, and do NOT sum their widths or heights. If and only if the product name, width, and height are all identical across multiple lines, you MUST combine them into a single line and sum only their quantities.
9. MULTIPLE LPO / ORDER NUMBERS RULE: If the uploaded document contains more than one Order Number or LPO (Local Purchase Order) Number (e.g., in a table, headers, or lines), this means the document includes multiple distinct orders. You MUST automatically generate a separate Sales Order preview page/object in the "orders" list for each unique Order/LPO Number, and write that Order/LPO Number in the "lpo_number" field of that order. Under no circumstances should you combine different LPOs or Order Numbers into a single order object.
10. Inside the document's Header section (strictly within the first 3 rows), if any row or 3-4 words end with LLC/L.L.C. then that is the customer name.
11. FIELD MAPPING & TRANSLATION RULES (From Uploaded Document or User Prompt):
    - If you find 'unit price', 'Rate', or 'price' anywhere in the document or user prompt, this represents the price of the item. You MUST write/map this value to the 'price' field in the JSON block (which corresponds to the 'PRICE' field in the order preview section).
    - If you see 'Qty' or 'QTY' anywhere in the document or user prompt, this represents the quantity of the item. You MUST write/map this value to the 'qty' field in the JSON block (which corresponds to the 'QTY' or 'quantity' field in the order preview section).
    - If you find only 'H' (or 'h') with a number value, this represents Height. You MUST write/map this value to the 'height' field in the JSON block.
    - If you find only 'W' (or 'w') with a number value, this represents Width. You MUST write/map this value to the 'width' field in the JSON block.
    - If you find 'Installation Date' anywhere in the document or user prompt, this represents the delivery date. You MUST map this value to the 'delivery_date' field in the JSON block.
    - PRODUCT NAME EXTRACTION RULE: You MUST extract the product name ONLY from the single column named 'Product' or 'Fabric'. Do NOT append, prefix, suffix, or combine any other column values (such as 'Bracket', 'Bunch', 'Inside/Outside', 'Accs. 1', 'Color', 'Design', etc.) into the product name. For example, if the 'Product' column is 'Track', the extracted product name in the JSON MUST be exactly 'Track', and NOT 'Track Ceiling Single Split Outside Wave Rail' or any other combined string. Keep it strictly as the exact value from that single column.

REQUIRED JSON SCHEMA (always include at end of response inside ```json``` block):
```json
{
  "orders": [
    {
      "customer": "Customer name or UNRESOLVED",
      "customer_id": null,
      "lpo_number": "LPO number or Purchase Order number or null",
      "order_lines": [
        {
          "product": "Product name",
          "product_id": null,
          "qty": 1,
          "height": 1.0,
          "width": 1.0,
          "price": null,
          "discount": 0.0,
          "tax": "tax details or null",
          "uom": "Units"
        }
      ],
      "delivery_date": "YYYY-MM-DD or null",
      "quotation_date": "YYYY-MM-DD or null",
      "payment_term": "Payment term name or null",
      "payment_term_id": null,
      "salesperson": "Salesperson name or null",
      "user_id": null,
      "notes": "Any special instructions",
      "confidence": 0.0,
      "missing_fields": ["list of missing required fields"],
      "follow_up_questions": ["questions to ask user if any"]
    }
  ]
}
```

FIELD EXPLANATIONS:
- `lpo_number`: The customer's Purchase Order number or LPO number if specified in the document (e.g. 22384 or PO-982). Do NOT include any "#" prefix character from the number (e.g., "#22384" should be extracted as "22384"). If not specified, set to null.
- `height`: height of the product line converted to meters. If the document/prompt specifies dimensions in other units (like cm, mm, inches, or '"), you MUST convert them to meters (e.g. 150 cm -> 1.5, 2000 mm -> 2.0, 100 inches -> 2.54). If dimensions are present but the unit (cm, m, mm, inches, etc.) is NOT specified anywhere in the document/prompt, you MUST keep height as is, add "height" to `missing_fields`, and add a question to `follow_up_questions` asking the user if the dimensions are in centimeters (cm) or meters (m). If not specified at all, default to 1.0.
- `width`: width of the product line converted to meters. If the document/prompt specifies dimensions in other units (like cm, mm, inches, or '"), you MUST convert them to meters (e.g. 150 cm -> 1.5, 2000 mm -> 2.0, 100 inches -> 2.54). If dimensions are present but the unit (cm, m, mm, inches, etc.) is NOT specified anywhere in the document/prompt, you MUST keep width as is, add "width" to `missing_fields`, and add a question to `follow_up_questions` asking the user if the dimensions are in centimeters (cm) or meters (m). If not specified at all, default to 1.0.
- `discount`: absolute discount amount (e.g. 100.0, 34.87) if a discount is specified for the product line, or 0.0 if none. E.g. 100.0 for $100 discount. CRITICAL: This is an absolute currency amount, not a percentage, and should not be multiplied by 100. If the discount cell/column is blank or empty in the document, you MUST set `discount` to 0.0.
- `tax`: tax rate/details (e.g. "15%" or "5%" or "VAT 15%") if a tax is specified for the product, or null if none. Note: Decimal ratios like 0.05 or 0.02 mean "5%" or "2%". CRITICAL: If the taxes cell/column is blank or empty in the document, you MUST set `tax` to null.
- `payment_term`: name of the payment term (e.g. "Immediate Payment", "30 Days", "15 Days") if specified in the document, or null if none.
- `salesperson`: name of the salesperson (e.g. Mitchell Admin, Marc Demo) if specified in the document/user message, or null if none.

CONFIDENCE SCORING:
- 0-30: Very incomplete, many missing fields
- 30-60: Partial information, needs clarification  
- 60-85: Good information, minor gaps
- 85-100: Complete, ready to create order

Always be warm and professional. Guide the user through providing all necessary information. Note: "order date" or "Quotation Date" refer to the same date, so always extract either as "quotation_date". Also, "Installation Date" or "Delivery Date" refer to the same date, so always extract either as "delivery_date". 'unit price', 'Rate', or 'price' mean the same thing, so always map them to the "price" field. 'Qty' or 'QTY' mean the same thing, so always map them to the "qty" field. 'H' with a number value represents height (map to "height" field) and 'W' with a number value represents width (map to "width" field)."""

    def __init__(self, api_key, model='gemini-2.5-flash',
                 vision_model='gemini-2.5-flash',
                 max_tokens=4096, env=None):
        self.api_key = api_key
        self.model = model or 'gemini-2.5-flash'
        self.vision_model = vision_model or 'gemini-2.5-flash'
        self.max_tokens = max_tokens or 4096
        self.env = env

    def chat_completion(self, conversation_history, extra_context='', odoo_validation='', product_category=None):
        """
        Send conversation history to Gemini and get a response.

        :param conversation_history: list of {'role': ..., 'content': ...}
        :param extra_context: additional text context (from parsed documents)
        :param odoo_validation: details on validation status/errors in Odoo
        :param product_category: selected product category ('blind', 'fabric', or 'track')
        :return: str — AI response text
        """
        system_instructions = [self.SYSTEM_PROMPT]

        if product_category:
            category_instructions = ""
            if product_category == 'fabric':
                category_instructions = (
                    "\nSPECIFIC FABRIC CATEGORY RULES:\n"
                    "- The uploaded document or table contains columns like 'Fabric' (the product name), 'panels', 'Adjusted_height' (height), 'price' (unit price), and 'Qty' (the quantity of fabric in meters, e.g., '8.5m', '12.5m', '6m').\n"
                    "- You MUST extract the value from the 'Qty' column as the quantity ('qty') of the line, converting it to a float (e.g., '8.5m' becomes 8.5). Do NOT use the 'panels' column as the quantity!\n"
                    "- The 'Adjusted_height' column represents the height of the window. Extract this as 'height'.\n"
                    "- The 'price' column represents the unit price. Extract this as 'price'.\n"
                    "- If there is no width column in the document, default the 'width' of the line to 1.0.\n"
                    "- Do NOT sum height and width of lines in the JSON structure; keep them as individual line dimensions.\n"
                    "- If the document contains multiple fabric lines of the same product but with different heights or quantities, do NOT combine them; extract them as separate lines in the JSON.\n"
                )
            elif product_category == 'blind':
                category_instructions = (
                    "\nSPECIFIC BLIND CATEGORY RULES:\n"
                    "- The quantity ('qty') is the number of blind units.\n"
                    "- Extract width and height in meters. If they are in mm (e.g. 3200, 2810), convert to meters (3.2, 2.81).\n"
                    "- If the document contains multiple blind lines of the same product but with different widths or heights, do NOT combine them; extract them as separate lines in the JSON.\n"
                )
            elif product_category == 'track':
                category_instructions = (
                    "\nSPECIFIC TRACK CATEGORY RULES:\n"
                    "- The quantity ('qty') is the number of track units.\n"
                    "- Extract width and height in meters. If they are in mm (e.g. 3200, 2810), convert to meters (3.2, 2.81).\n"
                    "- If the document contains multiple track lines of the same product but with different widths or heights, do NOT combine them; extract them as separate lines in the JSON.\n"
                )

            system_instructions.append(
                f'The user has selected the product category: **{product_category.upper()}**.\n'
                f'You MUST only extract and process products belonging to the **{product_category.upper()}** category.\n'
                f'If the user mentions products or options from other categories, politely remind them '
                f'that this session is specifically for generating a {product_category.title()} sales order.\n'
                f'{category_instructions}'
            )

        # Fetch category aliases if env is available to make AI aware of them
        aliases_context = ""
        if self.env and product_category:
            try:
                category = self.env['alias.category'].sudo().search([('type', '=', product_category)], limit=1)
                if category and category.line_ids:
                    # Build search text from history and extra_context
                    search_text = (extra_context or "")
                    for msg in conversation_history:
                        if msg.get('content'):
                            search_text += " " + msg['content']

                    product_aliases = []
                    customer_aliases = []
                    from .order_validator import OrderValidator
                    validator = OrderValidator(self.env)
                    for line in category.line_ids:
                        if line.alias_name and validator.is_alias_standalone_in_text(search_text, line.alias_name):
                            # Product alias mapping
                            if line.product_ids:
                                real_name = line.product_ids[0].name
                                product_aliases.append(f"- Alias '{line.alias_name}' maps to Product '{real_name}'")
                            # Customer alias mapping
                            if line.partner_ids:
                                real_customer = line.partner_ids[0].name
                                customer_aliases.append(f"- Alias '{line.alias_name}' maps to Customer '{real_customer}'")
                    
                    if product_aliases or customer_aliases:
                        aliases_context = "\nB2B LOOKUP ALIASES DEFINED IN SYSTEM:\n"
                        if product_aliases:
                            aliases_context += "Product Aliases:\n" + "\n".join(product_aliases) + "\n"
                        if customer_aliases:
                            aliases_context += "Customer Aliases:\n" + "\n".join(customer_aliases) + "\n"
                        aliases_context += (
                            "\nCRITICAL ALIAS RESOLUTION RULES:\n"
                            "1. If an Alias name listed above appears ALONE in a field or column (such as the customer name, product description/name, width, height, quantity, or price), you MUST replace it with its corresponding real name (the real product name or real customer name) in your JSON output block.\n"
                            "2. If an Alias name appears accompanied by other words or characters (e.g. 'KK-Fabric with backing' or 'KK-Customer Ltd'), do NOT replace or change it. Take it exactly as-is in your JSON block.\n"
                            "3. Do NOT change or resolve the alias name if it appears in any other general context in the document (like shipping instructions, general notes, etc.) that does not directly represent one of the fields listed above.\n"
                        )
            except Exception as e:
                _logger.warning("Error fetching category aliases for chatbot context: %s", str(e))

        if aliases_context:
            system_instructions.append(aliases_context)

        if extra_context:
            system_instructions.append(f'DOCUMENT CONTENT EXTRACTED:\n\n{extra_context}\n\nUse this information to help extract order details.')

        if odoo_validation:
            system_instructions.append(
                f'LIVE ODOO SYSTEM VALIDATION STATUS:\n\n{odoo_validation}\n\n'
                'CRITICAL USER FEEDBACK INSTRUCTION:\n'
                'In your conversational response, keep it extremely brief. If there are validation errors or warnings '
                'preventing the Sales Order from being created, ONLY list these issues so the user knows what needs correction. '
                'Do NOT describe or repeat successfully resolved or extracted values.'
            )

        full_system_prompt = "\n\n=== ADDITIONAL CONTEXT/RULES ===\n\n".join(system_instructions)

        # Build contents array from conversation history with role serialization & consolidation
        contents = []
        for msg in conversation_history:
            role = 'user' if msg.get('role') == 'user' else 'model'
            text = msg.get('content', '') or ''
            if not text.strip():
                continue
            
            # Combine consecutive messages with the same role
            if contents and contents[-1]['role'] == role:
                contents[-1]['parts'][0]['text'] += f"\n\n{text}"
            else:
                contents.append({
                    'role': role,
                    'parts': [{'text': text}]
                })
        
        # Google Gemini API requires contents to start with a 'user' message
        if contents and contents[0]['role'] == 'model':
            contents.insert(0, {
                'role': 'user',
                'parts': [{'text': 'Hello'}]
            })
            
        # Ensure contents is never empty to prevent 400 Bad Request
        if not contents:
            contents.append({
                'role': 'user',
                'parts': [{'text': 'Extract order details from the provided document.'}]
            })

        payload = {
            "contents": contents,
            "systemInstruction": {
                "parts": [{"text": full_system_prompt}]
            },
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": self.max_tokens or 8192,
            }
        }

        model_name = self.model
        if not model_name.startswith("models/"):
            model_name = f"models/{model_name}"

        # Gemini 2.5 models use reasoning/thinking tokens by default which consume
        # the maxOutputTokens budget. Disable reasoning to save output token limits and speed up response times.
        if '2.5' in model_name:
            payload["generationConfig"]["thinkingConfig"] = {
                "thinkingBudget": 0
            }

        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            res_data = response.json()
            candidates = res_data.get('candidates', [])
            if candidates:
                parts = candidates[0].get('content', {}).get('parts', [])
                if parts:
                    raw_text = parts[0].get('text', '')
                    
                    # Sanitize raw_text: If Gemini outputs raw ``` blocks without the 'json' label,
                    # convert them to ```json to ensure the parser in order_extractor.py matches correctly.
                    if raw_text:
                        raw_text = re.sub(r'```(?:[\s\n]*\{)', '```json\n{', raw_text)
                    return raw_text
                    
            raise ValueError(f"Unexpected API response structure: {res_data}")
        except Exception as e:
            _logger.error('Gemini chat completion error: %s', str(e))
            raise

    def vision_ocr(self, image_bytes, mime_type='image/jpeg', prompt=None):
        """
        Use Gemini Vision to extract text/data from an image or page.

        :param image_bytes: raw image bytes
        :param mime_type: e.g. 'image/jpeg', 'image/png'
        :param prompt: optional instruction override
        :return: str — extracted text
        """
        if prompt is None:
            prompt = (
                'This is a document image (purchase order, quotation, RFQ, invoice, or similar). '
                'Please extract ALL text content and structured information from this image. '
                'Focus on: customer name, company name, product names, quantities, prices, '
                'delivery dates, order numbers, and any other relevant order information. '
                'Return the extracted information in a clear, structured format.'
            )

        b64_image = base64.b64encode(image_bytes).decode('utf-8')

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": b64_image
                            }
                        },
                        {
                            "text": prompt
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 2048,
            }
        }

        model_name = self.vision_model
        if not model_name.startswith("models/"):
            model_name = f"models/{model_name}"

        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            res_data = response.json()
            candidates = res_data.get('candidates', [])
            if candidates:
                parts = candidates[0].get('content', {}).get('parts', [])
                if parts:
                    return parts[0].get('text', '')
            raise ValueError(f"Unexpected API response structure: {res_data}")
        except Exception as e:
            _logger.error('Gemini vision OCR error: %s', str(e))
            raise

    @classmethod
    def from_env(cls, env):
        """Create GeminiService from Odoo environment config params."""
        ICP = env['ir.config_parameter'].sudo()
        api_key = ICP.get_param('sale_order_ai_chatbot.gemini_api_key', '')
        model = ICP.get_param('sale_order_ai_chatbot.gemini_model', 'gemini-2.5-flash')
        vision_model = ICP.get_param(
            'sale_order_ai_chatbot.gemini_vision_model',
            'gemini-2.5-flash'
        )
        max_tokens_val = ICP.get_param('sale_order_ai_chatbot.gemini_max_tokens', '8192')
        try:
            max_tokens = int(max_tokens_val) if max_tokens_val else 8192
        except (ValueError, TypeError):
            max_tokens = 8192

        if max_tokens <= 0:
            max_tokens = 8192

        if not api_key:
            raise ValueError(
                'Gemini API key is not configured. '
                'Please go to Settings → AI Sales Bot and enter your Gemini API key.'
            )
        return cls(api_key=api_key, model=model, vision_model=vision_model, max_tokens=max_tokens, env=env)
