/** @odoo-module **/
/**
 * Chat Panel OWL Component
 * Left-side chat conversation UI
 */

import { Component, useState, useRef, onMounted, onPatched, xml, markup } from "@odoo/owl";

export class ChatPanel extends Component {
    static template = xml`
        <div class="o_chatbot_left_panel"
             t-ref="chatPanel"
             t-on-dragover.prevent="onDragOver"
             t-on-dragleave="onDragLeave"
             t-on-drop.prevent="onDrop">

            <!-- Drag overlay -->
            <div t-att-class="'o_drag_overlay' + (state.isDragging ? ' visible' : '')">
                <div class="o_drag_overlay_icon">📎</div>
                <div class="o_drag_overlay_text">Drop your file here</div>
                <div style="font-size:13px;color:var(--bot-text-muted)">PDF, DOCX, Excel, Images supported</div>
            </div>

            <!-- Messages -->
            <div class="o_chatbot_messages_container" t-ref="messagesContainer">
                <t t-if="props.messages.length === 0">
                    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:16px;padding:40px;text-align:center;opacity:0.6">
                        <div style="font-size:52px">🤖</div>
                        <div style="font-size:16px;font-weight:600;color:var(--bot-text-secondary)">AI Sales Assistant</div>
                        <div style="font-size:13px;color:var(--bot-text-muted);line-height:1.7;max-width:280px">
                            Start by describing your order, uploading a document, or asking me anything about creating a Sales Order.
                        </div>
                    </div>
                </t>

                <t t-foreach="props.messages" t-as="msg" t-key="msg.id || msg_index">
                    <!-- User message -->
                    <t t-if="msg.role === 'user'">
                        <div class="o_chat_message user">
                            <div class="o_chat_avatar">
                                <t t-esc="getUserInitial()"/>
                            </div>
                            <div class="o_chat_bubble_wrap">
                                <div class="o_chat_bubble">
                                    <t t-if="msg.message_type === 'file'">
                                        <div style="display:flex;flex-direction:column;gap:8px">
                                            <div class="o_chat_file_bubble" style="background:rgba(108,99,255,0.15);border-color:rgba(108,99,255,0.3)">
                                                <div class="o_chat_file_icon"><t t-esc="getFileIcon(msg)"/></div>
                                                <div class="o_chat_file_info">
                                                    <div class="o_chat_file_name" t-esc="getFileName(msg)"/>
                                                    <div class="o_chat_file_size">File uploaded &amp; processed</div>
                                                </div>
                                            </div>
                                            <t t-if="getFileMessageText(msg)">
                                                <div class="o_chat_file_message_text" style="font-size:14px;line-height:1.6;word-break:break-word;color:#fff;text-align:left">
                                                    <t t-esc="getFileMessageText(msg)"/>
                                                </div>
                                            </t>
                                        </div>
                                    </t>
                                    <t t-else="">
                                        <t t-esc="msg.content"/>
                                    </t>
                                </div>
                                <div class="o_chat_timestamp" t-esc="formatTime(msg.timestamp)"/>
                            </div>
                        </div>
                    </t>

                    <!-- AI message -->
                    <t t-elif="msg.role === 'assistant'">
                        <div class="o_chat_message assistant">
                            <div class="o_chat_avatar">🤖</div>
                            <div class="o_chat_bubble_wrap">
                                <div class="o_chat_bubble" t-out="renderMarkdown(msg.content)"/>
                                <t t-if="msg.message_type === 'category_selection'">
                                    <div class="o_category_buttons_container">
                                        <button type="button" class="o_bot_btn o_category_btn" t-on-click="() => selectCategory('blind')" t-att-disabled="isCategorySelected()">
                                            Blind
                                        </button>
                                        <button type="button" class="o_bot_btn o_category_btn" t-on-click="() => selectCategory('fabric')" t-att-disabled="isCategorySelected()">
                                            Fabric
                                        </button>
                                        <button type="button" class="o_bot_btn o_category_btn" t-on-click="() => selectCategory('track')" t-att-disabled="isCategorySelected()">
                                            Track
                                        </button>
                                    </div>
                                </t>
                                <div class="o_chat_timestamp" t-esc="formatTime(msg.timestamp)"/>
                            </div>
                        </div>
                    </t>
                </t>

                <!-- Typing indicator -->
                <t t-if="props.isTyping">
                    <div class="o_typing_indicator" style="display:flex;align-items:center;justify-content:space-between;width:100%;padding-right:8px">
                        <div style="display:flex;align-items:center;gap:12px">
                            <div class="o_chat_avatar" style="background:var(--bot-bg-tertiary);border:1px solid var(--bot-border);color:var(--bot-accent-light)">🤖</div>
                            <div class="o_typing_dots">
                                <div class="o_typing_dot"/>
                                <div class="o_typing_dot"/>
                                <div class="o_typing_dot"/>
                            </div>
                        </div>
                        <button type="button" class="o_bot_btn o_bot_btn_ghost" style="padding:4px 8px;font-size:11px;border-radius:4px" t-on-click="cancelRequest">
                            ✕ Cancel
                        </button>
                    </div>
                </t>

                <!-- Processing indicator -->
                <t t-if="props.isProcessing">
                    <div class="o_processing_indicator" style="display:flex;align-items:center;justify-content:space-between;width:100%">
                        <div style="display:flex;align-items:center;gap:10px">
                            <div class="o_processing_spinner"/>
                            <span t-esc="props.processingText || 'Processing document...'"/>
                        </div>
                        <button type="button" class="o_bot_btn o_bot_btn_ghost" style="padding:4px 8px;font-size:11px;border-radius:4px;border-color:rgba(239, 68, 68, 0.3);color:#fca5a5" t-on-click="cancelRequest">
                            ✕ Cancel
                        </button>
                    </div>
                </t>
            </div>

            <!-- Input area -->
            <div class="o_chatbot_input_area">
                <!-- Upload feedback -->
                <t t-if="state.uploadingFile">
                    <div class="o_processing_indicator" style="margin-bottom:10px">
                        <div class="o_processing_spinner"/>
                        <span>Uploading and analyzing <strong t-esc="state.uploadFileName"/>...</span>
                    </div>
                </t>

                <!-- Selected file preview -->
                <t t-if="state.selectedFile">
                    <div class="o_selected_file_preview" style="display:flex;align-items:center;justify-content:space-between;background:rgba(108,99,255,0.1);border:1px solid var(--bot-border);border-radius:var(--bot-radius-md);padding:8px 12px;margin-bottom:10px">
                        <div style="display:flex;align-items:center;gap:10px;min-width:0">
                            <span style="font-size:16px">📎</span>
                            <span style="font-weight:500;font-size:13px;color:var(--bot-text-primary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap" t-esc="state.selectedFile.name"/>
                            <span style="font-size:11px;color:var(--bot-text-muted)" t-esc="formatFileSize(state.selectedFile.size)"/>
                        </div>
                        <button type="button" class="o_bot_btn o_bot_btn_icon" style="width:24px;height:24px;font-size:12px;background:rgba(255,255,255,0.05)" t-on-click="removeSelectedFile">
                            ✕
                        </button>
                    </div>
                </t>

                <div class="o_chat_input_row">
                    <!-- File upload -->
                    <input type="file"
                           id="chatbot_file_upload"
                           name="chatbot_file_upload"
                           t-ref="fileInput"
                           style="display:none"
                           accept=".pdf,.docx,.xlsx,.xls,.png,.jpg,.jpeg,.webp"
                           t-on-change="onFileSelected"/>

                    <button class="o_bot_btn o_bot_btn_icon"
                            title="Upload file (PDF, DOCX, Excel, Image)"
                            t-on-click="triggerFileUpload">
                        📎
                    </button>

                    <textarea
                        id="chatbot_message_input"
                        name="chatbot_message_input"
                        class="o_chat_textarea"
                        t-ref="textInput"
                        placeholder="Describe your order or ask me anything..."
                        rows="1"
                        t-model="state.inputText"
                        t-on-keydown="onKeyDown"
                        t-on-input="autoResize"
                        t-att-disabled="props.isTyping || props.isProcessing || state.uploadingFile"
                    />

                    <div class="o_input_actions">
                        <button class="o_bot_btn o_bot_btn_send"
                                title="Send message (Enter)"
                                t-on-click="sendMessage"
                                t-att-disabled="(!state.inputText.trim() &amp;&amp; !state.selectedFile) || props.isTyping || props.isProcessing">
                            ➤
                        </button>
                    </div>
                </div>

                <div style="display:flex;align-items:center;justify-content:space-between;margin-top:8px;padding:0 4px">
                    <div style="font-size:11px;color:var(--bot-text-muted)">
                        Enter to send · Shift+Enter for new line · Drag &amp; drop files
                    </div>
                    <div style="font-size:11px;color:var(--bot-text-muted)" t-esc="'Session: ' + (props.sessionName || 'None')"/>
                </div>
            </div>
        </div>
    `;

    static props = {
        messages: { type: Array, optional: true },
        isTyping: { type: Boolean, optional: true },
        isProcessing: { type: Boolean, optional: true },
        processingText: { type: String, optional: true },
        sessionId: { type: Number, optional: true },
        sessionName: { type: String, optional: true },
        productCategory: { type: String, optional: true },
        onSendMessage: { type: Function },
        onFileUpload: { type: Function },
        onCancelRequest: { type: Function },
        onSelectCategory: { type: Function },
    };

    static defaultProps = {
        messages: [],
        isTyping: false,
        isProcessing: false,
        processingText: 'Processing...',
    };

    setup() {
        this.state = useState({
            inputText: '',
            isDragging: false,
            uploadingFile: false,
            uploadFileName: '',
            selectedFile: null,
        });
        this.messagesContainer = useRef('messagesContainer');
        this.fileInput = useRef('fileInput');
        this.textInput = useRef('textInput');

        this.lastMessagesLength = this.props.messages?.length || 0;

        onMounted(() => {
            this.scrollToBottom();
        });

        onPatched(() => {
            const currentLen = this.props.messages?.length || 0;
            if (currentLen !== this.lastMessagesLength) {
                this.lastMessagesLength = currentLen;
                this.scrollToBottom();
            }
        });

        this.cancelRequest = this.cancelRequest.bind(this);
        this.selectCategory = this.selectCategory.bind(this);
        this.isCategorySelected = this.isCategorySelected.bind(this);
    }

    cancelRequest() {
        this.props.onCancelRequest();
    }

    scrollToBottom() {
        const container = this.messagesContainer.el;
        if (container) {
            setTimeout(() => {
                container.scrollTop = container.scrollHeight;
            }, 50);
        }
    }

    isCategorySelected() {
        return !!this.props.productCategory;
    }

    async selectCategory(category) {
        if (this.props.isTyping || this.props.isProcessing) return;
        await this.props.onSelectCategory(category);
    }

    getUserInitial() {
        const name = (odoo?.session_info?.name || 'U');
        return name.charAt(0).toUpperCase();
    }

    formatTime(timestamp) {
        if (!timestamp) return '';
        try {
            const d = new Date(timestamp);
            return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch {
            return '';
        }
    }

    getFileIcon(msg) {
        const content = (msg.content || '').toLowerCase();
        if (content.includes('.pdf')) return '📄';
        if (content.includes('.docx') || content.includes('.doc')) return '📝';
        if (content.includes('.xlsx') || content.includes('.xls')) return '📊';
        if (content.match(/\.(png|jpg|jpeg|webp)/)) return '🖼️';
        return '📎';
    }

    getFileName(msg) {
        const match = (msg.content || '').match(/\*\*(.*?)\*\*/);
        return match ? match[1] : msg.content;
    }

    getFileMessageText(msg) {
        const content = msg.content || '';
        const match = content.match(/\*\*(.*?)\*\*/);
        if (!match) return '';
        const endPos = content.indexOf(match[0]) + match[0].length;
        return content.slice(endPos).trim();
    }

    renderMarkdown(text) {
        if (!text) return '';
        // Remove HTML tags from the message content
        const cleanText = text.replace(/<\/?[a-zA-Z][^>]*>/g, '');
        // Basic markdown rendering
        let html = cleanText
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code style="background:rgba(255,255,255,0.1);padding:1px 5px;border-radius:4px;font-family:monospace;font-size:12px">$1</code>')
            .replace(/\n/g, '<br>');
        // Bullet points
        html = html.replace(/^• (.+)/gm, '<div style="display:flex;gap:8px;margin:2px 0"><span style="color:var(--bot-accent-light)">•</span><span>$1</span></div>');
        return markup(html);
    }

    onKeyDown(ev) {
        if (ev.key === 'Enter' && !ev.shiftKey) {
            ev.preventDefault();
            this.sendMessage();
        }
    }

    autoResize(ev) {
        const el = ev.target;
        el.style.height = 'auto';
        el.style.height = Math.min(el.scrollHeight, 140) + 'px';
    }

    async sendMessage() {
        const text = this.state.inputText.trim();
        const file = this.state.selectedFile;
        if (!text && !file) return;

        if (file) {
            await this.uploadFile(file, text);
        } else {
            this.state.inputText = '';
            if (this.textInput.el) {
                this.textInput.el.style.height = 'auto';
            }
            await this.props.onSendMessage(text);
            this.scrollToBottom();
        }
    }

    triggerFileUpload() {
        this.fileInput.el?.click();
    }

    onFileSelected(ev) {
        const file = ev.target.files[0];
        if (!file) return;
        ev.target.value = '';
        this.state.selectedFile = file;
    }

    // Drag-and-drop
    onDragOver(ev) {
        if (ev.dataTransfer.types.includes('Files')) {
            this.state.isDragging = true;
        }
    }

    onDragLeave(ev) {
        if (!ev.currentTarget.contains(ev.relatedTarget)) {
            this.state.isDragging = false;
        }
    }

    onDrop(ev) {
        this.state.isDragging = false;
        const file = ev.dataTransfer.files[0];
        if (file) {
            this.state.selectedFile = file;
        }
    }

    async uploadFile(file, messageText) {
        this.state.uploadingFile = true;
        this.state.uploadFileName = file.name;
        try {
            await this.props.onFileUpload(file, messageText);
            this.state.selectedFile = null;
            this.state.inputText = '';
            if (this.textInput.el) {
                this.textInput.el.style.height = 'auto';
            }
            this.scrollToBottom();
        } finally {
            this.state.uploadingFile = false;
            this.state.uploadFileName = '';
        }
    }

    formatFileSize(bytes) {
        if (!bytes) return '';
        const kb = bytes / 1024;
        if (kb < 1024) return kb.toFixed(1) + ' KB';
        const mb = kb / 1024;
        return mb.toFixed(1) + ' MB';
    }

    removeSelectedFile() {
        this.state.selectedFile = null;
    }
}
