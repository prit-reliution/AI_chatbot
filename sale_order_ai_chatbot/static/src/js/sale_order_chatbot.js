/** @odoo-module **/
/**
 * Sale Order AI Chatbot — Root OWL Component
 * Orchestrates the full split-panel chatbot interface
 */

import { Component, useState, onMounted, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ChatPanel } from "./chat_panel";
import { OrderPreviewPanel } from "./order_preview_panel";

class SaleOrderChatbot extends Component {
    static template = xml`
        <div class="o_sale_chatbot_root">

            <!-- Header -->
            <div class="o_chatbot_header">
                <div class="o_chatbot_header_brand">
                    <button class="o_bot_btn o_bot_btn_icon"
                            title="Toggle session history"
                            t-on-click="toggleSidebar">
                        ☰
                    </button>
                    <div class="o_chatbot_header_icon">🤖</div>
                    <div>
                        <div class="o_chatbot_header_title">AI Sales Order Bot</div>
                        <div class="o_chatbot_header_subtitle">
                            <t t-if="state.currentSession">
                                <span t-att-class="'o_session_state_dot ' + state.currentSession.state"
                                      style="display:inline-block"/>
                                <t t-esc="state.currentSession.name"/>
                            </t>
                            <t t-else="">
                                No active session
                            </t>
                        </div>
                    </div>
                </div>
                <div class="o_chatbot_header_actions">
                    <button class="o_bot_btn o_header_btn" t-on-click="newChat">
                        + New Chat
                    </button>
                    <button class="o_bot_btn o_header_btn" t-on-click="resetSession"
                            t-if="state.currentSession">
                        🔄 Reset
                    </button>
                    <button class="o_bot_btn o_header_btn" t-on-click="openSettings">
                        ⚙️ Settings
                    </button>
                </div>
            </div>

            <!-- Main layout -->
            <div class="o_chatbot_main">

                <!-- Sidebar: Session history -->
                <div t-att-class="'o_session_sidebar' + (state.sidebarOpen ? '' : ' collapsed')">
                    <div class="o_session_sidebar_header">💬 Chat History</div>
                    <div class="o_session_list">
                        <t t-if="state.sessionHistory.length === 0">
                            <div style="padding:20px;text-align:center;color:var(--bot-text-muted);font-size:13px">
                                No previous sessions
                            </div>
                        </t>
                        <t t-foreach="state.sessionHistory" t-as="sess" t-key="sess.id">
                            <div t-att-class="getSessionItemClass(sess)"
                                 t-on-click="() => loadSession(sess.id)"
                                 style="display:flex;justify-content:space-between;align-items:center">
                                <div style="min-width:0;flex:1">
                                    <div class="o_session_item_name" t-esc="sess.name"/>
                                    <div class="o_session_item_meta">
                                        <span t-att-class="'o_session_state_dot ' + sess.state"/>
                                        <t t-if="sess.sale_order_name">
                                            <span t-esc="sess.sale_order_name"/>
                                        </t>
                                        <t t-else="">
                                            <span t-esc="sess.message_count"/> messages
                                        </t>
                                    </div>
                                </div>
                                <button type="button"
                                        class="o_session_delete_btn"
                                        title="Delete chat session"
                                        t-on-click.stop="() => deleteSession(sess.id)">
                                    🗑️
                                </button>
                            </div>
                        </t>
                    </div>
                    <div style="padding:12px;border-top:1px solid var(--bot-border)">
                        <button class="o_bot_btn o_bot_btn_primary" style="width:100%;justify-content:center" t-on-click="newChat">
                            + New Chat
                        </button>
                    </div>
                </div>

                <!-- Chat panel (left) -->
                <ChatPanel
                    messages="state.messages"
                    isTyping="state.isTyping"
                    isProcessing="state.isProcessing"
                    processingText="state.processingText"
                    sessionId="state.currentSession ? state.currentSession.id : 0"
                    sessionName="state.currentSession ? state.currentSession.name : ''"
                    productCategory="getProductCategory()"
                    onSendMessage.bind="onSendMessage"
                    onFileUpload.bind="onFileUpload"
                    onCancelRequest.bind="onCancelRequest"
                    onSelectCategory.bind="onSelectCategory"
                />

                <!-- Preview panel (right) -->
                <OrderPreviewPanel
                    orderData="state.orderData"
                    validationErrors="state.validationErrors"
                    validationWarnings="state.validationWarnings"
                    isSubmitting="state.isSubmitting"
                    saleOrderId="state.saleOrderId"
                    saleOrderName="state.saleOrderName"
                    sessionId="state.currentSession ? state.currentSession.id : 0"
                    productCategory="getProductCategory()"
                    onUpdateOrder.bind="onUpdateOrder"
                    onSubmitOrder.bind="onSubmitOrder"
                    onOpenSaleOrder.bind="onOpenSaleOrder"
                />
            </div>
        </div>
    `;

    static components = { ChatPanel, OrderPreviewPanel };

    setup() {
        this.notification = useService('notification');
        this.action = useService('action');

        this.state = useState({
            currentSession: null,
            messages: [],
            orderData: null,
            validationErrors: [],
            validationWarnings: [],
            isTyping: false,
            isProcessing: false,
            processingText: 'Processing...',
            isSubmitting: false,
            saleOrderId: null,
            saleOrderName: null,
            sessionHistory: [],
            sidebarOpen: false,
        });

        // Bind loadSession to preserve 'this' context in template arrow functions
        this.loadSession = this.loadSession.bind(this);
        this.onCancelRequest = this.onCancelRequest.bind(this);
        this.onSelectCategory = this.onSelectCategory.bind(this);
        this.deleteSession = this.deleteSession.bind(this);
        this._abortController = null;

        onMounted(async () => {
            await this.loadSessionHistory();
            if (this.state.sessionHistory.length > 0) {
                await this.loadSession(this.state.sessionHistory[0].id);
            } else {
                await this.newChat();
            }
        });
    }

    // -------------------------------------------------------------------------
    // Session management
    // -------------------------------------------------------------------------

    async newChat() {
        try {
            const result = await this._rpc('/sale_order_ai_chatbot/session/new', {});
            if (result.success) {
                this.state.currentSession = {
                    id: result.session_id,
                    name: result.session_name,
                    state: 'draft',
                    product_category: null,
                };
                this.state.messages = [{
                    id: 'welcome',
                    role: 'assistant',
                    content: result.welcome_message,
                    message_type: 'category_selection',
                    timestamp: new Date().toISOString(),
                }];
                this.state.orderData = null;
                this.state.validationErrors = [];
                this.state.validationWarnings = [];
                this.state.saleOrderId = null;
                this.state.saleOrderName = null;
                await this.loadSessionHistory();
            }
        } catch (e) {
            this.notification.add('Failed to create new chat session', { type: 'danger' });
        }
    }

    async loadSession(sessionId) {
        try {
            const result = await this._rpc(`/sale_order_ai_chatbot/session/${sessionId}/data`, {});
            if (result.success) {
                this.state.currentSession = {
                    id: result.session_id,
                    name: result.session_name,
                    state: result.state,
                    product_category: result.product_category,
                };
                this.state.messages = result.messages || [];
                this.state.orderData = result.order_data;
                this.state.validationErrors = result.validation_errors || [];
                this.state.validationWarnings = result.validation_warnings || [];
                this.state.saleOrderId = result.sale_order_id || null;
                this.state.saleOrderName = result.sale_order_name || null;
            }
        } catch (e) {
            this.notification.add('Failed to load session', { type: 'danger' });
        }
    }

    async loadSessionHistory() {
        try {
            const result = await this._rpc('/sale_order_ai_chatbot/sessions', {});
            if (result.success) {
                this.state.sessionHistory = result.sessions || [];
            }
        } catch { }
    }

    async resetSession() {
        if (!this.state.currentSession) return;
        const sid = this.state.currentSession.id;
        try {
            const result = await this._rpc(`/sale_order_ai_chatbot/session/${sid}/reset`, {});
            if (result.success) {
                await this.loadSession(sid);
                this.notification.add('Session reset', { type: 'success' });
            } else {
                this.notification.add(result.error || 'Failed to reset session', { type: 'danger' });
            }
        } catch (e) {
            this.notification.add('Error resetting session', { type: 'danger' });
        }
    }

    async deleteSession(sessionId) {
        if (!confirm('Are you sure you want to delete this chat session?')) {
            return;
        }
        try {
            const result = await this._rpc(`/sale_order_ai_chatbot/session/${sessionId}/delete`, {});
            if (result.success) {
                this.notification.add('Chat session deleted', { type: 'success' });
                if (this.state.currentSession && this.state.currentSession.id === sessionId) {
                    await this.newChat();
                } else {
                    await this.loadSessionHistory();
                }
            } else {
                this.notification.add(result.error || 'Failed to delete session', { type: 'danger' });
            }
        } catch {
            this.notification.add('Error deleting session', { type: 'danger' });
        }
    }

    /** Returns CSS class string for a session sidebar item */
    getSessionItemClass(sess) {
        const isActive = this.state.currentSession &&
                         this.state.currentSession.id === sess.id;
        return 'o_session_item' + (isActive ? ' active' : '');
    }

    getProductCategory() {
        if (this.state.currentSession && typeof this.state.currentSession.product_category === 'string') {
            return this.state.currentSession.product_category;
        }
        return undefined;
    }

    toggleSidebar() {
        this.state.sidebarOpen = !this.state.sidebarOpen;
        if (this.state.sidebarOpen) {
            this.loadSessionHistory();
        }
    }

    openSettings() {
        this.action.doAction('sale_order_ai_chatbot.action_sale_chatbot_config_settings');
    }

    // -------------------------------------------------------------------------
    // Chat interactions
    // -------------------------------------------------------------------------

    async onSelectCategory(category) {
        if (!this.state.currentSession) return;
        this.state.isTyping = true;
        try {
            const sid = this.state.currentSession.id;
            const result = await this._rpc(
                `/sale_order_ai_chatbot/session/${sid}/select_category`,
                { category: category }
            );
            if (result.success) {
                // Reload session data to get the new messages and product category
                await this.loadSession(sid);
            } else {
                this.notification.add(result.error || 'Failed to select category', { type: 'danger' });
            }
        } catch (e) {
            this.notification.add('Network error selecting category', { type: 'danger' });
        } finally {
            this.state.isTyping = false;
        }
    }

    async onSendMessage(messageText) {
        if (!this.state.currentSession) {
            await this.newChat();
        }
        // Optimistically add user message
        const tempMsg = {
            id: 'temp_' + Date.now(),
            role: 'user',
            content: messageText,
            message_type: 'text',
            timestamp: new Date().toISOString(),
        };
        this.state.messages = [...this.state.messages, tempMsg];
        this.state.isTyping = true;

        try {
            const sid = this.state.currentSession.id;
            this._abortController = new AbortController();
            const result = await this._rpc(
                `/sale_order_ai_chatbot/session/${sid}/message`,
                { message: messageText },
                this._abortController.signal
            );

            if (result.success) {
                // Add AI reply
                const aiMsg = {
                    id: 'ai_' + Date.now(),
                    role: 'assistant',
                    content: result.ai_reply,
                    message_type: 'text',
                    timestamp: new Date().toISOString(),
                };
                this.state.messages = [...this.state.messages, aiMsg];
                this.state.orderData = result.order_data || this.state.orderData;
                this.state.validationErrors = result.validation_errors || [];
                this.state.validationWarnings = result.validation_warnings || [];
            } else {
                this.notification.add(result.error || 'Failed to send message', { type: 'danger' });
            }
        } catch (e) {
            if (e.name === 'AbortError') {
                console.log('Request aborted by user');
            } else {
                this.notification.add('Network error sending message', { type: 'danger' });
            }
        } finally {
            this.state.isTyping = false;
            this._abortController = null;
        }
    }

    async onFileUpload(file, messageText) {
        if (!this.state.currentSession) {
            await this.newChat();
        }

        const sid = this.state.currentSession.id;
        this.state.isProcessing = true;
        this.state.processingText = `Processing ${file.name}...`;

        // Add upload message immediately, including the optional messageText
        let uploadContent = `📎 Uploaded file: **${file.name}**`;
        if (messageText && messageText.trim()) {
            uploadContent += `\n\n${messageText.trim()}`;
        }
        const uploadMsg = {
            id: 'upload_' + Date.now(),
            role: 'user',
            content: uploadContent,
            message_type: 'file',
            timestamp: new Date().toISOString(),
        };
        this.state.messages = [...this.state.messages, uploadMsg];

        try {
            const formData = new FormData();
            formData.append('file', file);
            if (messageText && messageText.trim()) {
                formData.append('message', messageText.trim());
            }

            this._abortController = new AbortController();
            const response = await fetch(
                `/sale_order_ai_chatbot/session/${sid}/upload`,
                {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                    signal: this._abortController.signal,
                }
            );

            const result = await response.json();

            if (result.success) {
                const aiMsg = {
                    id: 'ai_file_' + Date.now(),
                    role: 'assistant',
                    content: result.ai_reply,
                    message_type: 'text',
                    timestamp: new Date().toISOString(),
                };
                this.state.messages = [...this.state.messages, aiMsg];
                this.state.orderData = result.order_data || this.state.orderData;
                this.state.validationErrors = result.validation_errors || [];
                this.state.validationWarnings = result.validation_warnings || [];
                this.notification.add(`${file.name} processed successfully`, { type: 'success' });
            } else {
                this.notification.add(result.error || 'Failed to process file', { type: 'danger' });
            }
        } catch (e) {
            if (e.name === 'AbortError') {
                console.log('File upload aborted by user');
            } else {
                this.notification.add('Error uploading file', { type: 'danger' });
            }
        } finally {
            this.state.isProcessing = false;
            this._abortController = null;
        }
    }

    onCancelRequest() {
        if (this._abortController) {
            this._abortController.abort();
            this._abortController = null;
        }
        this.state.isTyping = false;
        this.state.isProcessing = false;

        const cancelMsg = {
            id: 'cancel_' + Date.now(),
            role: 'assistant',
            content: '❌ Process cancelled by user.',
            message_type: 'text',
            timestamp: new Date().toISOString(),
        };
        this.state.messages = [...this.state.messages, cancelMsg];
        this.notification.add('Processing cancelled', { type: 'warning' });
    }

    // -------------------------------------------------------------------------
    // Order panel interactions
    // -------------------------------------------------------------------------

    async onUpdateOrder(orderData) {
        if (!this.state.currentSession) return;
        try {
            const sid = this.state.currentSession.id;
            const result = await this._rpc(
                `/sale_order_ai_chatbot/session/${sid}/update_order`,
                { order_data: orderData }
            );
            if (result.success) {
                this.state.orderData = result.order_data || orderData;
                this.state.validationErrors = result.validation_errors || [];
                this.state.validationWarnings = result.validation_warnings || [];
            }
        } catch { }
    }

    async onSubmitOrder(orderData) {
        if (!this.state.currentSession) return;
        this.state.isSubmitting = true;
        try {
            const sid = this.state.currentSession.id;
            const result = await this._rpc(
                `/sale_order_ai_chatbot/session/${sid}/create_order`,
                { order_data: orderData }
            );
            if (result.success) {
                const isMultiple = this.state.orderData && Array.isArray(this.state.orderData.orders) && this.state.orderData.orders.length > 1;
                
                if (isMultiple) {
                    if (this.state.orderData && this.state.orderData.orders) {
                        const updatedOrders = this.state.orderData.orders.map(o => {
                            const matchKey = o.key && orderData.key && o.key === orderData.key;
                            const matchLpo = o.lpo_number && orderData.lpo_number && o.lpo_number === orderData.lpo_number;
                            const matchCustomer = o.customer && orderData.customer && o.customer === orderData.customer && !o.sale_order_id;
                            if (matchKey || ((matchLpo || matchCustomer) && !o.sale_order_id)) {
                                return {
                                    ...o,
                                    sale_order_id: result.sale_order_id,
                                    sale_order_name: result.sale_order_name,
                                    state: 'done'
                                };
                            }
                            return o;
                        });
                        this.state.orderData = {
                            ...this.state.orderData,
                            orders: updatedOrders
                        };
                    }
                } else {
                    this.state.saleOrderId = result.sale_order_id;
                    this.state.saleOrderName = result.sale_order_name;
                }

                // Add success message to chat
                const successMsg = {
                    id: 'order_' + Date.now(),
                    role: 'assistant',
                    content: `✅ Sales Order **${result.sale_order_name}** created successfully!\n\nCustomer: ${result.partner_name}\nProducts: ${result.line_count} lines\n\nYou can find it in Sales → Quotations.`,
                    message_type: 'order_update',
                    timestamp: new Date().toISOString(),
                };
                this.state.messages = [...this.state.messages, successMsg];
                this.notification.add(`Sales Order ${result.sale_order_name} created!`, { type: 'success' });
                
                if (!isMultiple) {
                    this.onOpenSaleOrder(result.sale_order_id);
                } else {
                    await this.loadSession(sid);
                }
                await this.loadSessionHistory();
            } else {
                this.notification.add(result.error || 'Failed to create order', { type: 'danger' });
                const errorMsg = {
                    id: 'error_' + Date.now(),
                    role: 'assistant',
                    content: `⚠️ Failed to create Sales Order in Odoo. Reason:\n${result.error || 'Unknown error'}`,
                    message_type: 'text',
                    timestamp: new Date().toISOString(),
                };
                this.state.messages = [...this.state.messages, errorMsg];
            }
        } catch (e) {
            this.notification.add('Error creating Sales Order', { type: 'danger' });
            const errorMsg = {
                id: 'error_catch_' + Date.now(),
                role: 'assistant',
                content: `⚠️ Error occurred while creating Sales Order:\n${e.message || e}`,
                message_type: 'text',
                timestamp: new Date().toISOString(),
            };
            this.state.messages = [...this.state.messages, errorMsg];
        } finally {
            this.state.isSubmitting = false;
        }
    }

    onOpenSaleOrder(orderId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'sale.order',
            res_id: orderId,
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'current',
        });
    }

    // -------------------------------------------------------------------------
    // JSON-RPC helper
    // -------------------------------------------------------------------------

    async _rpc(route, params = {}, signal = null) {
        const response = await fetch(route, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'call',
                params,
            }),
            signal,
        });
        const data = await response.json();
        if (data.error) throw new Error(data.error.message);
        return data.result || {};
    }
}

// Register as a client action
registry.category('actions').add('sale_order_ai_chatbot.chatbot_client_action', SaleOrderChatbot);
