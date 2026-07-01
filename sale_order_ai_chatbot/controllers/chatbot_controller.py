# -*- coding: utf-8 -*-
import json
import base64
import logging
import traceback

from odoo import http, _
from odoo.http import request, Response

from ..services.gemini_service import GeminiService
from ..services.document_parser import DocumentParser
from ..services.order_extractor import OrderExtractor
from ..services.order_validator import OrderValidator

_logger = logging.getLogger(__name__)


def _json_response(data, status=200):
    """Helper to return a JSON response."""
    return Response(
        json.dumps(data, ensure_ascii=False, default=str),
        status=status,
        content_type='application/json',
    )


def _error_response(message, status=400):
    return _json_response({'success': False, 'error': message}, status=status)


class SaleOrderAIChatbotController(http.Controller):
    """
    JSON-RPC / REST endpoints for the AI Sales Order Chatbot.
    All endpoints require authentication.
    """

    BASE_URL = '/sale_order_ai_chatbot'

    # -------------------------------------------------------------------------
    # Session Management
    # -------------------------------------------------------------------------

    @http.route(
        f'{BASE_URL}/session/new',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=False,
    )
    def session_new(self, **kwargs):
        """Create a new chatbot session."""
        try:
            session = request.env['sale.chatbot.session'].create({
                'state': 'draft',
            })
            # Add welcome message
            welcome = _("Please select the product type for which you want to create a sales order.")
            request.env['sale.chatbot.message'].create({
                'session_id': session.id,
                'role': 'assistant',
                'content': welcome,
                'message_type': 'category_selection',
            })
            return {
                'success': True,
                'session_id': session.id,
                'session_name': session.name,
                'welcome_message': welcome,
            }
        except Exception as e:
            _logger.error('Error creating session: %s\n%s', str(e), traceback.format_exc())
            return {'success': False, 'error': str(e)}

    @http.route(
        f'{BASE_URL}/session/<int:session_id>/data',
        type='json',
        auth='user',
        methods=['GET', 'POST'],
        csrf=False,
    )
    def session_data(self, session_id, **kwargs):
        """Get current session state including messages and order data."""
        try:
            session = request.env['sale.chatbot.session'].browse(session_id)
            if not session.exists():
                return {'success': False, 'error': 'Session not found'}

            # Do not reset done session on read/get data to allow user to see confirmation previews
            # session.check_and_reset_done_session()

            messages = []
            for msg in session.message_ids.sorted('create_date'):
                attachments = []
                for att in msg.attachment_ids:
                    attachments.append({
                        'id': att.id,
                        'name': att.name,
                        'mimetype': att.mimetype,
                        'size': att.file_size,
                    })
                messages.append({
                    'id': msg.id,
                    'role': msg.role,
                    'content': msg.content or '',
                    'message_type': msg.message_type,
                    'timestamp': msg.create_date.isoformat() if msg.create_date else '',
                    'attachments': attachments,
                })

            order_data = session.get_order_data_dict()
            order_data['product_category'] = session.product_category
            validator = OrderValidator(request.env)
            enriched_data, errors, warnings = validator.validate_and_enrich(order_data, is_manual=True)

            return {
                'success': True,
                'session_id': session.id,
                'session_name': session.name,
                'state': session.state,
                'messages': messages,
                'order_data': enriched_data,
                'confidence_score': session.confidence_score,
                'validation_errors': errors,
                'validation_warnings': warnings,
                'sale_order_id': session.sale_order_id.id if session.sale_order_id and session.state == 'done' else None,
                'sale_order_name': session.sale_order_id.name if session.sale_order_id and session.state == 'done' else None,
                'product_category': session.product_category,
            }
        except Exception as e:
            _logger.error('Error getting session data: %s', str(e))
            return {'success': False, 'error': str(e)}

    # -------------------------------------------------------------------------
    # Chat
    # -------------------------------------------------------------------------

    @http.route(
        f'{BASE_URL}/session/<int:session_id>/message',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=False,
    )
    def send_message(self, session_id, message='', **kwargs):
        """
        Send a user message, get AI response, extract/update order data.
        """
        try:
            session = request.env['sale.chatbot.session'].browse(session_id)
            if not session.exists():
                return {'success': False, 'error': 'Session not found'}

            session.check_and_reset_done_session()

            if not message.strip():
                return {'success': False, 'error': 'Message cannot be empty'}

            if not session.product_category:
                # Save user message
                request.env['sale.chatbot.message'].create({
                    'session_id': session.id,
                    'role': 'user',
                    'content': message,
                    'message_type': 'text',
                })
                # Add welcome prompt with buttons
                welcome = _("Please select the product type for which you want to create a sales order.")
                request.env['sale.chatbot.message'].create({
                    'session_id': session.id,
                    'role': 'assistant',
                    'content': welcome,
                    'message_type': 'category_selection',
                })
                return {
                    'success': True,
                    'ai_reply': welcome,
                    'order_data': session.get_order_data_dict(),
                    'confidence_score': session.confidence_score,
                    'validation_errors': [],
                    'validation_warnings': [],
                }

            # Save user message
            user_msg = request.env['sale.chatbot.message'].create({
                'session_id': session.id,
                'role': 'user',
                'content': message,
                'message_type': 'text',
            })

            # Build AI response
            ai_reply, updated_order_data = self._process_message(session, message)

            # Save AI response
            request.env['sale.chatbot.message'].create({
                'session_id': session.id,
                'role': 'assistant',
                'content': ai_reply,
                'message_type': 'text',
            })

            # Validate and enrich order data
            validator = OrderValidator(request.env)
            if 'product_category' not in updated_order_data:
                updated_order_data['product_category'] = session.product_category
            enriched_data, errors, warnings = validator.validate_and_enrich(updated_order_data)

            # Save the enriched data back to session database so resolved IDs are persisted!
            session.set_order_data_dict(enriched_data)
            session.confidence_score = enriched_data.get('confidence', 0.0)

            return {
                'success': True,
                'ai_reply': ai_reply,
                'order_data': enriched_data,
                'confidence_score': session.confidence_score,
                'validation_errors': errors,
                'validation_warnings': warnings,
            }

        except Exception as e:
            _logger.error('Error sending message: %s\n%s', str(e), traceback.format_exc())
            return {'success': False, 'error': str(e)}

    # -------------------------------------------------------------------------
    # File Upload
    # -------------------------------------------------------------------------

    @http.route(
        f'{BASE_URL}/session/<int:session_id>/upload',
        type='http',
        auth='user',
        methods=['POST'],
        csrf=False,
    )
    def upload_file(self, session_id, **kwargs):
        """
        Handle file upload: parse document, send to AI, update order data.
        Supports PDF, XLSX, PNG, JPG, JPEG.
        """
        try:
            session = request.env['sale.chatbot.session'].browse(session_id)
            if not session.exists():
                return _error_response('Session not found')

            session.check_and_reset_done_session()

            uploaded_file = request.httprequest.files.get('file')
            if not uploaded_file:
                return _error_response('No file provided')

            filename = uploaded_file.filename
            file_bytes = uploaded_file.read()
            mimetype = uploaded_file.content_type or ''

            if not file_bytes:
                return _error_response('Empty file')

            if not session.product_category:
                # Store as ir.attachment
                attachment = request.env['ir.attachment'].create({
                    'name': filename,
                    'datas': base64.b64encode(file_bytes),
                    'mimetype': mimetype,
                    'res_model': 'sale.chatbot.session',
                    'res_id': session.id,
                })
                session.attachment_ids = [(4, attachment.id)]

                # Save user message indicating upload
                user_content = f'📎 Uploaded file: **{filename}**'
                request.env['sale.chatbot.message'].create({
                    'session_id': session.id,
                    'role': 'user',
                    'content': user_content,
                    'message_type': 'file',
                    'attachment_ids': [(4, attachment.id)],
                })

                # Add welcome prompt with buttons
                welcome = _("Please select the product type for which you want to create a sales order.")
                request.env['sale.chatbot.message'].create({
                    'session_id': session.id,
                    'role': 'assistant',
                    'content': welcome,
                    'message_type': 'category_selection',
                })
                return _json_response({
                    'success': True,
                    'filename': filename,
                    'extracted_text_preview': '',
                    'ai_reply': welcome,
                    'order_data': session.get_order_data_dict(),
                    'confidence_score': session.confidence_score,
                    'validation_errors': [],
                    'validation_warnings': [],
                    'attachment_id': attachment.id,
                })

            # Store as ir.attachment
            attachment = request.env['ir.attachment'].create({
                'name': filename,
                'datas': base64.b64encode(file_bytes),
                'mimetype': mimetype,
                'res_model': 'sale.chatbot.session',
                'res_id': session.id,
            })
            session.attachment_ids = [(4, attachment.id)]

            # Initialize services
            try:
                gemini_service = GeminiService.from_env(request.env)
            except ValueError as e:
                return _error_response(str(e))

            doc_parser = DocumentParser(gemini_service=gemini_service)
            extractor = OrderExtractor()

            # Parse document
            extracted_text = doc_parser.parse(
                file_bytes=file_bytes,
                filename=filename,
                mimetype=mimetype,
            )

            # Retrieve optional user message/comment
            message = kwargs.get('message') or ''

            # Save user message indicating upload
            user_content = f'📎 Uploaded file: **{filename}**'
            if message:
                user_content += f'\n\n{message}'
            user_msg = request.env['sale.chatbot.message'].create({
                'session_id': session.id,
                'role': 'user',
                'content': user_content,
                'message_type': 'file',
                'extracted_text': extracted_text,
                'attachment_ids': [(4, attachment.id)],
            })

            # Build conversation history
            conversation_history = session.get_conversation_history()

            # Add system note about the document with critical instruction on multiple LPO/Order numbers
            doc_note = (
                f'I have uploaded a document: {filename}\n\n'
                f'Please analyze the following extracted content and update the order details. '
                f'CRITICAL: If the document contains multiple distinct Order/LPO numbers (e.g. in a table or list), '
                f'you MUST automatically split them and generate a separate order object in the "orders" list for '
                f'each unique Order/LPO number, populating their respective "lpo_number" fields.\n\n'
                f'{extracted_text[:8000]}'  # Limit to avoid token overflow
            )
            conversation_history.append({
                'role': 'user',
                'content': doc_note,
            })

            # Get current validation context
            odoo_validation = self._get_validation_context(session)

            # AI processing
            extra_context = f'Document: {filename}\n\n{extracted_text[:8000]}'
            if message:
                extra_context = f'User instructions related to this document: {message}\n\n' + extra_context
            
            extra_context += (
                '\n\nCRITICAL: If this document contains more than one Order Number or LPO Number, '
                'you MUST automatically split the extraction and create a separate preview object under '
                'the "orders" list in the JSON response for each unique LPO / Order Number. Write the LPO Number '
                'in the "lpo_number" field of each respective order.'
            )

            ai_response = gemini_service.chat_completion(
                conversation_history=conversation_history[:-1],  # exclude the last we just appended
                extra_context=extra_context,
                odoo_validation=odoo_validation,
                product_category=session.product_category,
            )

            ai_reply, new_order_data = extractor.extract_from_ai_response(ai_response)

            # Merge with existing order data
            existing_data = session.get_order_data_dict()
            merged_data = extractor.merge_order_data(existing_data, new_order_data, env=request.env, product_category=session.product_category)

            # If customer is unresolved (e.g. UNRESOLVED or ID is None), scan raw document text for match fallback
            if 'orders' in merged_data:
                for order in merged_data['orders']:
                    if not order.get('customer_id') or order.get('customer') == 'UNRESOLVED':
                        validator = OrderValidator(request.env)
                        detected_partner = validator.resolve_customer_from_text(extracted_text, product_category=session.product_category)
                        if detected_partner:
                            order['customer'] = detected_partner.name
                            order['customer_id'] = detected_partner.id

            session.set_order_data_dict(merged_data)
            
            conf_score = 0.0
            if 'orders' in merged_data and merged_data['orders']:
                conf_score = sum(float(o.get('confidence', 0.0)) for o in merged_data['orders']) / len(merged_data['orders'])
            session.confidence_score = conf_score

            if conf_score > 50:
                session.state = 'ready'

            # Save AI response
            request.env['sale.chatbot.message'].create({
                'session_id': session.id,
                'role': 'assistant',
                'content': ai_reply,
                'message_type': 'text',
            })

            # Validate
            validator = OrderValidator(request.env)
            if 'product_category' not in merged_data:
                merged_data['product_category'] = session.product_category
            enriched_data, errors, warnings = validator.validate_and_enrich(merged_data)

            # Save the enriched data back to session database so resolved IDs are persisted!
            session.set_order_data_dict(enriched_data)
            session.confidence_score = enriched_data.get('confidence', 0.0)

            response_data = {
                'success': True,
                'filename': filename,
                'extracted_text_preview': extracted_text[:500] if extracted_text else '',
                'ai_reply': ai_reply,
                'order_data': enriched_data,
                'confidence_score': session.confidence_score,
                'validation_errors': errors,
                'validation_warnings': warnings,
                'attachment_id': attachment.id,
            }
            return _json_response(response_data)

        except Exception as e:
            _logger.error('Error uploading file: %s\n%s', str(e), traceback.format_exc())
            return _error_response(str(e), status=500)

    # -------------------------------------------------------------------------
    # Order Data Management
    # -------------------------------------------------------------------------

    @http.route(
        f'{BASE_URL}/session/<int:session_id>/update_order',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=False,
    )
    def update_order(self, session_id, order_data=None, **kwargs):
        """
        Accept manually edited order data from the preview panel.
        """
        try:
            session = request.env['sale.chatbot.session'].browse(session_id)
            if not session.exists():
                return {'success': False, 'error': 'Session not found'}

            if order_data is None:
                return {'success': False, 'error': 'No order data provided'}

            session.set_order_data_dict(order_data)

            if 'product_category' not in order_data:
                order_data['product_category'] = session.product_category
            validator = OrderValidator(request.env)
            enriched_data, errors, warnings = validator.validate_and_enrich(order_data, is_manual=True)
            session.set_order_data_dict(enriched_data)

            conf_score = 0.0
            if 'orders' in enriched_data and enriched_data['orders']:
                conf_score = sum(float(o.get('confidence', 0.0)) for o in enriched_data['orders']) / len(enriched_data['orders'])
            session.confidence_score = conf_score
            if conf_score > 50 and not errors:
                session.state = 'ready'

            return {
                'success': True,
                'order_data': enriched_data,
                'validation_errors': errors,
                'validation_warnings': warnings,
            }
        except Exception as e:
            _logger.error('Error updating order: %s', str(e))
            return {'success': False, 'error': str(e)}

    @http.route(
        f'{BASE_URL}/session/<int:session_id>/create_order',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=False,
    )
    def create_order(self, session_id, order_data=None, **kwargs):
        """
        Create the actual sale.order from current session order data.
        """
        try:
            session = request.env['sale.chatbot.session'].browse(session_id)
            if not session.exists():
                return {'success': False, 'error': 'Session not found'}

            sale_order = session.action_create_sale_order(order_data=order_data)

            return {
                'success': True,
                'sale_order_id': sale_order.id,
                'sale_order_name': sale_order.name,
                'partner_name': sale_order.partner_id.name,
                'line_count': len(sale_order.order_line),
                'message': _(
                    'Sales Order %s created successfully!', sale_order.name
                ),
            }
        except Exception as e:
            _logger.error('Error creating order: %s\n%s', str(e), traceback.format_exc())
            return {'success': False, 'error': str(e)}

    @http.route(
        f'{BASE_URL}/session/<int:session_id>/reset',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=False,
    )
    def reset_session(self, session_id, **kwargs):
        """Reset session conversation and order data."""
        try:
            session = request.env['sale.chatbot.session'].browse(session_id)
            if not session.exists():
                return {'success': False, 'error': 'Session not found'}
            session.action_reset()
            # Add welcome back message
            welcome = _("Please select the product type for which you want to create a sales order.")
            request.env['sale.chatbot.message'].create({
                'session_id': session.id,
                'role': 'assistant',
                'content': welcome,
                'message_type': 'category_selection',
            })
            return {'success': True, 'message': 'Session reset successfully'}
        except Exception as e:
            _logger.error('Error resetting session: %s', str(e))
            return {'success': False, 'error': str(e)}

    @http.route(
        f'{BASE_URL}/session/<int:session_id>/select_category',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=False,
    )
    def select_category(self, session_id, category, **kwargs):
        """Set the product category for the session."""
        try:
            session = request.env['sale.chatbot.session'].browse(session_id)
            if not session.exists():
                return {'success': False, 'error': 'Session not found'}
            
            if category not in ('blind', 'fabric', 'track'):
                return {'success': False, 'error': 'Invalid category'}
            
            session.product_category = category
            
            # Add user message to show they selected the category
            request.env['sale.chatbot.message'].create({
                'session_id': session.id,
                'role': 'user',
                'content': category.capitalize(),
                'message_type': 'text',
            })
            
            # Add AI confirmation message
            ai_reply = _(
                "You've selected **%s**.\n\n"
                "Please describe your order in plain text or upload a document to proceed.",
                category.capitalize()
            )
            request.env['sale.chatbot.message'].create({
                'session_id': session.id,
                'role': 'assistant',
                'content': ai_reply,
                'message_type': 'text',
            })
            
            return {
                'success': True,
                'product_category': category,
                'ai_reply': ai_reply,
            }
        except Exception as e:
            _logger.error('Error setting product category: %s', str(e))
            return {'success': False, 'error': str(e)}

    @http.route(
        f'{BASE_URL}/session/<int:session_id>/delete',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=False,
    )
    def delete_session(self, session_id, **kwargs):
        """Delete a chatbot session."""
        try:
            session = request.env['sale.chatbot.session'].browse(session_id)
            if not session.exists():
                return {'success': False, 'error': 'Session not found'}
            if session.user_id.id != request.env.user.id:
                return {'success': False, 'error': 'Permission denied'}
            session.unlink()
            return {'success': True}
        except Exception as e:
            _logger.error('Error deleting session: %s', str(e))
            return {'success': False, 'error': str(e)}

    # -------------------------------------------------------------------------
    # Autocomplete
    # -------------------------------------------------------------------------

    @http.route(
        f'{BASE_URL}/autocomplete/partners',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=False,
    )
    def autocomplete_partners(self, query='', **kwargs):
        """Search partners for autocomplete."""
        validator = OrderValidator(request.env)
        return {'success': True, 'results': validator.search_partners(query)}

    @http.route(
        f'{BASE_URL}/autocomplete/products',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=False,
    )
    def autocomplete_products(self, query='', session_id=None, **kwargs):
        """Search products for autocomplete."""
        product_category = None
        if session_id:
            session = request.env['sale.chatbot.session'].browse(int(session_id))
            if session.exists():
                product_category = session.product_category
        validator = OrderValidator(request.env)
        return {'success': True, 'results': validator.search_products(query, product_category=product_category)}

    @http.route(
        f'{BASE_URL}/autocomplete/payment_terms',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=False,
    )
    def autocomplete_payment_terms(self, query='', **kwargs):
        """Search payment terms for autocomplete."""
        validator = OrderValidator(request.env)
        return {'success': True, 'results': validator.search_payment_terms(query)}

    @http.route(
        f'{BASE_URL}/autocomplete/salespersons',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=False,
    )
    def autocomplete_salespersons(self, query='', **kwargs):
        """Search salesperson users for autocomplete."""
        validator = OrderValidator(request.env)
        return {'success': True, 'results': validator.search_salespersons(query)}

    @http.route(
        f'{BASE_URL}/taxes',
        type='json',
        auth='user',
        methods=['POST', 'GET'],
        csrf=False,
    )
    def list_taxes(self, **kwargs):
        """Get list of active sales taxes."""
        try:
            taxes = request.env['account.tax'].search([
                ('type_tax_use', '=', 'sale'),
                ('active', '=', True)
            ])
            return {
                'success': True,
                'results': [{'id': t.id, 'name': t.name, 'amount': t.amount} for t in taxes]
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # -------------------------------------------------------------------------
    # Session History
    # -------------------------------------------------------------------------

    @http.route(
        f'{BASE_URL}/sessions',
        type='json',
        auth='user',
        methods=['GET', 'POST'],
        csrf=False,
    )
    def list_sessions(self, limit=20, **kwargs):
        """List recent chatbot sessions for the current user."""
        try:
            sessions = request.env['sale.chatbot.session'].search(
                [('user_id', '=', request.env.user.id)],
                limit=limit,
                order='create_date desc',
            )
            return {
                'success': True,
                'sessions': [
                    {
                        'id': s.id,
                        'name': s.name,
                        'state': s.state,
                        'message_count': s.message_count,
                        'confidence_score': s.confidence_score,
                        'sale_order_name': s.sale_order_id.name if s.sale_order_id else None,
                        'create_date': s.create_date.isoformat() if s.create_date else '',
                    }
                    for s in sessions
                ],
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _get_validation_context(self, session):
        """Helper to get current Odoo validation messages as a string."""
        try:
            order_data = session.get_order_data_dict()
            validator = OrderValidator(request.env)
            _, errors, warnings = validator.validate_and_enrich(order_data, is_manual=True)
            
            lines = []
            if errors:
                lines.append("Errors preventing Sales Order creation:")
                for err in errors:
                    lines.append(f"- {err}")
            if warnings:
                lines.append("Warnings/Issues:")
                for warn in warnings:
                    lines.append(f"- {warn}")
                    
            if lines:
                return "\n".join(lines)
        except Exception:
            pass
        return ""

    def _process_message(self, session, user_message):
        """
        Core AI processing for a text message.
        Returns (ai_reply, updated_order_data).
        """
        extractor = OrderExtractor()

        try:
            gemini_service = GeminiService.from_env(request.env)
        except ValueError as e:
            # No API key — return a helpful message
            mock_reply = (
                f"⚠️ {str(e)}\n\n"
                "I've noted your request. Once the API key is configured, I'll be able to process it fully."
            )
            return mock_reply, session.get_order_data_dict()

        # Get current validation context
        odoo_validation = self._get_validation_context(session)

        # Get conversation history
        conversation_history = session.get_conversation_history()
        conversation_history.append({'role': 'user', 'content': user_message})

        # Call AI
        ai_response = gemini_service.chat_completion(
            conversation_history=conversation_history[:-1],
            odoo_validation=odoo_validation,
            product_category=session.product_category
        )

        # Parse response
        ai_reply, new_order_data = extractor.extract_from_ai_response(ai_response)

        # Merge with existing, passing user_message to filter changes to mentioned products only
        existing_data = session.get_order_data_dict()
        merged_data = extractor.merge_order_data(existing_data, new_order_data, env=request.env, user_message=user_message, product_category=session.product_category)
        session.set_order_data_dict(merged_data)
        conf_score = 0.0
        if 'orders' in merged_data and merged_data['orders']:
            conf_score = sum(float(o.get('confidence', 0.0)) for o in merged_data['orders']) / len(merged_data['orders'])
        session.confidence_score = conf_score

        if conf_score > 50:
            session.state = 'ready'
        elif session.state == 'draft':
            session.state = 'processing'

        return ai_reply, merged_data
