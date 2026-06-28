/** @odoo-module **/
/**
 * Order Preview Panel OWL Component
 * Right-side live editable sales order preview
 * Supporting multiple tabbed orders from a single document
 */

import { Component, useState, onWillUpdateProps, useRef, xml } from "@odoo/owl";

export class OrderPreviewPanel extends Component {
    static template = xml`
        <div class="o_chatbot_right_panel">
            <!-- Panel header -->
            <div class="o_preview_header">
                <div class="o_preview_header_title">
                    <div class="o_preview_header_icon">📋</div>
                    <div>
                        <div>Order Preview</div>
                        <div style="font-size:11px;font-weight:400;color:var(--bot-text-muted);margin-top:1px">
                            Live preview · Editable
                        </div>
                    </div>
                </div>
                <div style="display:flex;align-items:center;gap:10px">
                    <div t-att-class="'o_confidence_badge ' + getConfidenceClass()">
                        <t t-esc="getConfidenceLabel()"/>
                    </div>
                </div>
            </div>

            <!-- Page Tabs for Multiple Orders -->
            <t t-if="getOrdersCount() > 1">
                <div class="o_order_pages_tabs">
                    <t t-foreach="state.localData.orders" t-as="order" t-key="order_index">
                        <button type="button" 
                                t-att-class="'o_order_page_tab ' + (state.currentIndex === order_index ? 'active' : '')"
                                t-on-click="() => selectPage(order_index)">
                            <span t-att-class="'o_order_page_tab_status ' + (order.sale_order_id ? 'done' : 'ready')"/>
                            <t t-esc="getPageLabel(order, order_index)"/>
                        </button>
                    </t>
                </div>
            </t>

            <!-- Main content -->
            <div class="o_preview_content" t-ref="previewContent">

                <!-- Validation errors -->
                <t t-if="hasValidationIssues()">
                    <div class="o_preview_section">
                        <div class="o_preview_section_header">
                            <span>⚠️</span> Validation Issues
                        </div>
                        <div class="o_preview_section_body o_validation_alerts">
                            <t t-foreach="getActiveOrder().errors" t-as="err" t-key="err_index">
                                <div class="o_alert o_alert_error">
                                    <span>✗</span>
                                    <span t-esc="err"/>
                                </div>
                            </t>
                            <t t-foreach="getValidationWarnings()" t-as="warn" t-key="warn_index">
                                <div class="o_alert o_alert_warning">
                                    <span>!</span>
                                    <span t-esc="warn"/>
                                </div>
                            </t>
                        </div>
                    </div>
                </t>

                <!-- Customer section -->
                <div class="o_preview_section">
                    <div class="o_preview_section_header">
                        <span>👤</span> Customer
                    </div>
                    <div class="o_preview_section_body">
                        <div t-att-class="'o_preview_field ' + getFieldStatus('customer')">
                            <div class="o_preview_field_label">Customer Name *</div>
                            <div style="position:relative">
                                <input type="text"
                                       id="chatbot_customer_name"
                                       name="chatbot_customer_name"
                                       class="o_preview_input"
                                       placeholder="Type customer name..."
                                       t-att-disabled="isOrderCreated()"
                                       t-att-value="getActiveOrder().customer || ''"
                                       t-on-input="(e) => onCustomerInput(e.target.value, e)"
                                       t-on-blur="onCustomerBlur"
                                       t-on-focus="onCustomerFocus"/>
                                <!-- Autocomplete dropdown -->
                                <t t-if="showPartnerDropdown()">
                                    <div class="o_autocomplete_dropdown">
                                        <t t-foreach="state.partnerSuggestions" t-as="partner" t-key="partner.id">
                                            <div class="o_autocomplete_item" t-on-mousedown="() => selectPartner(partner)">
                                                <span style="color:var(--bot-accent-light)">👤</span>
                                                <div>
                                                    <div class="o_autocomplete_item_name" t-esc="partner.name"/>
                                                </div>
                                            </div>
                                        </t>
                                    </div>
                                </t>
                            </div>
                            <t t-if="getActiveOrder().customer_id">
                                <div class="o_field_status_indicator o_field_valid">
                                    <span>✓</span> Matched in system
                                </div>
                            </t>
                            <t t-elif="getActiveOrder().customer">
                                <div class="o_field_status_indicator o_field_warning">
                                    <span>!</span> Not yet verified in system
                                </div>
                            </t>
                            <t t-if="!getActiveOrder().customer_id &amp;&amp; getActiveOrder().customer_suggestions &amp;&amp; getActiveOrder().customer_suggestions.length &gt; 0">
                                <div class="o_customer_suggestions_container">
                                    <div class="o_suggestions_title">
                                        💡 Suggested Customers:
                                    </div>
                                    <div class="o_suggestions_list">
                                        <t t-foreach="getActiveOrder().customer_suggestions" t-as="suggestion" t-key="suggestion.id">
                                            <button type="button"
                                                    class="o_suggestion_badge"
                                                    t-on-click="() =&gt; selectPartner(suggestion)"
                                                    t-att-disabled="isOrderCreated()">
                                                <span>👤</span> <t t-esc="suggestion.name"/>
                                            </button>
                                        </t>
                                    </div>
                                </div>
                            </t>
                        </div>
                        
                        <!-- LPO Number container -->
                        <div class="o_preview_field" style="margin-top: 12px;">
                            <div class="o_preview_field_label">LPO Number</div>
                            <input type="text"
                                   id="chatbot_lpo_number"
                                   name="chatbot_lpo_number"
                                   class="o_preview_input"
                                   placeholder="Type LPO / PO number..."
                                   t-att-disabled="isOrderCreated()"
                                   t-att-value="getActiveOrder().lpo_number || ''"
                                   t-on-input="(e) => onLpoNumberInput(e.target.value, e)"/>
                        </div>
                    </div>
                </div>

                <!-- Order lines section -->
                <div class="o_preview_section">
                    <div class="o_preview_section_header">
                        <span>🛒</span> Order Lines
                        <span style="margin-left:auto;font-weight:400;text-transform:none;font-size:11px;letter-spacing:0">
                            <t t-esc="getLineCount()"/> items
                        </span>
                    </div>
                    <div class="o_preview_section_body" style="padding:8px 0">
                        <t t-if="getLineCount() === 0">
                            <div style="padding:20px;text-align:center;color:var(--bot-text-muted);font-size:13px">
                                No products extracted yet
                            </div>
                        </t>
                        <table class="o_preview_lines_table">
                             <thead>
                                 <tr>
                                     <th style="width:24px"></th>
                                     <th>Product Name</th>
                                     <t t-if="props.productCategory !== 'fabric' &amp;&amp; props.productCategory !== 'track'">
                                         <th style="width:80px">Height (m)</th>
                                     </t>
                                     <t t-if="props.productCategory !== 'fabric'">
                                         <th style="width:80px">Width (m)</th>
                                     </t>
                                     <th style="width:75px">Qty</th>
                                     <t t-if="props.productCategory !== 'track'">
                                         <th style="width:95px">Price</th>
                                     </t>
                                     <th style="width:95px">Disc(Amt)</th>
                                     <th style="width:30px"></th>
                                 </tr>
                             </thead>
                            <tbody>
                                <t t-foreach="getActiveOrder().order_lines" t-as="line" t-key="line_index">
                                    <tr>
                                        <td>
                                            <span t-att-class="'o_line_status_dot ' + getLineStatus(line)"
                                                  t-att-title="getLineStatusText(line)"/>
                                        </td>
                                        <td>
                                            <div style="position:relative">
                                                <textarea t-att-id="'chatbot_line_product_' + line_index"
                                                          t-att-name="'chatbot_line_product_' + line_index"
                                                          class="o_line_input o_line_textarea"
                                                          t-att-disabled="isOrderCreated()"
                                                          t-att-value="line.product || ''"
                                                          placeholder="Product name"
                                                          rows="2"
                                                          t-on-input="(e) => onLineInput(line_index, 'product', e.target.value, e)"
                                                          t-on-focus="() => onProductFocus(line_index)"
                                                          t-on-blur="() => onProductBlur(line_index)"/>
                                                <t t-if="showProductDropdown(line_index)">
                                                    <div class="o_autocomplete_dropdown" style="left:0;right:0;width:auto">
                                                        <t t-foreach="state.productSuggestions" t-as="prod" t-key="prod.id">
                                                            <div class="o_autocomplete_item" t-on-mousedown="() => selectProduct(line_index, prod)">
                                                                <span style="color:var(--bot-accent-light)">📦</span>
                                                                <div>
                                                                    <div class="o_autocomplete_item_name" t-esc="prod.name"/>
                                                                    <div class="o_autocomplete_item_sub">
                                                                        <t t-esc="prod.uom || 'Units'"/> · $<t t-esc="(prod.price || 0).toFixed(2)"/>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        </t>
                                                    </div>
                                                </t>
                                            </div>
                                        </td>
                                        <t t-if="props.productCategory !== 'fabric' &amp;&amp; props.productCategory !== 'track'">
                                            <td>
                                                <input type="number"
                                                       t-att-id="'chatbot_line_height_' + line_index"
                                                       t-att-name="'chatbot_line_height_' + line_index"
                                                       class="o_line_input"
                                                       min="0"
                                                       step="0.01"
                                                       t-att-disabled="isOrderCreated()"
                                                       t-att-value="line.height || 1.0"
                                                       t-on-input="(e) => onLineInput(line_index, 'height', e.target.value, e)"
                                                       t-on-focus="(e) => e.target.select()"/>
                                            </td>
                                        </t>
                                        <t t-if="props.productCategory !== 'fabric'">
                                            <td>
                                                <input type="number"
                                                       t-att-id="'chatbot_line_width_' + line_index"
                                                       t-att-name="'chatbot_line_width_' + line_index"
                                                       class="o_line_input"
                                                       min="0"
                                                       step="0.01"
                                                       t-att-disabled="isOrderCreated()"
                                                       t-att-value="line.width || 1.0"
                                                       t-on-input="(e) => onLineInput(line_index, 'width', e.target.value, e)"
                                                       t-on-focus="(e) => e.target.select()"/>
                                            </td>
                                        </t>
                                        <td>
                                            <input type="number"
                                                   t-att-id="'chatbot_line_qty_' + line_index"
                                                   t-att-name="'chatbot_line_qty_' + line_index"
                                                   class="o_line_input"
                                                   min="0"
                                                   step="1"
                                                   t-att-disabled="isOrderCreated()"
                                                   t-att-value="line.qty || 1"
                                                   t-on-input="(e) => onLineInput(line_index, 'qty', e.target.value, e)"
                                                   t-on-focus="(e) => e.target.select()"/>
                                        </td>
                                        <t t-if="props.productCategory !== 'track'">
                                            <td>
                                                <input type="number"
                                                       t-att-id="'chatbot_line_price_' + line_index"
                                                       t-att-name="'chatbot_line_price_' + line_index"
                                                       class="o_line_input"
                                                       min="0"
                                                       step="0.01"
                                                       t-att-disabled="isOrderCreated()"
                                                       t-att-value="line.price || ''"
                                                       placeholder="Auto"
                                                       t-on-input="(e) => onLineInput(line_index, 'price', e.target.value, e)"
                                                       t-on-focus="(e) => e.target.select()"/>
                                            </td>
                                        </t>
                                        <td>
                                            <input type="number"
                                                   t-att-id="'chatbot_line_discount_' + line_index"
                                                   t-att-name="'chatbot_line_discount_' + line_index"
                                                   class="o_line_input"
                                                   min="0"
                                                   step="0.01"
                                                   t-att-disabled="isOrderCreated()"
                                                   t-att-value="line.discount || 0"
                                                   t-on-input="(e) => onLineInput(line_index, 'discount', e.target.value, e)"
                                                   t-on-focus="(e) => e.target.select()"/>
                                        </td>
                                        <td>
                                            <button type="button"
                                                    class="o_remove_line_btn"
                                                    t-att-disabled="isOrderCreated()"
                                                    t-on-click="() => removeLine(line_index)"
                                                    title="Remove line">✕</button>
                                        </td>
                                    </tr>
                                </t>
                            </tbody>
                        </table>
                        <button type="button"
                                class="o_add_line_btn"
                                t-att-disabled="isOrderCreated()"
                                t-on-click="addLine">
                            + Add Product Line
                        </button>
                    </div>
                </div>

                <!-- Dates and Notes -->
                <div class="o_preview_section">
                    <div class="o_preview_section_header">
                        <span>📅</span> Dates &amp; Notes
                    </div>
                    <div class="o_preview_section_body">
                        <div class="o_preview_field">
                            <div class="o_preview_field_label">Quotation Date</div>
                            <input type="date"
                                   id="chatbot_quotation_date"
                                   name="chatbot_quotation_date"
                                   class="o_preview_input"
                                   t-att-disabled="isOrderCreated()"
                                   t-att-value="getActiveOrder().quotation_date || ''"
                                   t-on-input="(e) => onFieldInput('quotation_date', e.target.value, e)"
                                   style="color-scheme:dark"/>
                        </div>
                        <div class="o_preview_field">
                            <div class="o_preview_field_label">Delivery Date</div>
                            <input type="date"
                                   id="chatbot_delivery_date"
                                   name="chatbot_delivery_date"
                                   class="o_preview_input"
                                   t-att-disabled="isOrderCreated()"
                                   t-att-value="getActiveOrder().delivery_date || ''"
                                   t-on-input="(e) => onFieldInput('delivery_date', e.target.value, e)"
                                   style="color-scheme:dark"/>
                        </div>
                        <div class="o_preview_field">
                            <div class="o_preview_field_label">Notes / Special Instructions</div>
                            <textarea id="chatbot_notes"
                                      name="chatbot_notes"
                                      class="o_preview_input o_preview_textarea"
                                      t-att-disabled="isOrderCreated()"
                                      placeholder="Any special instructions..."
                                      rows="3"
                                      t-att-value="getActiveOrder().notes || ''"
                                      t-on-input="(e) => onFieldInput('notes', e.target.value, e)"/>
                        </div>
                    </div>
                </div>

                <!-- Payment and Salesperson -->
                <div class="o_preview_section">
                    <div class="o_preview_section_header">
                        <span>💳</span> Payment &amp; Salesperson
                    </div>
                    <div class="o_preview_section_body">
                        <!-- Payment Term -->
                        <div class="o_preview_field">
                            <div class="o_preview_field_label">Payment Term</div>
                            <div style="position:relative">
                                <input type="text"
                                       id="chatbot_payment_term"
                                       name="chatbot_payment_term"
                                       class="o_preview_input"
                                       placeholder="Type payment term..."
                                       t-att-disabled="isOrderCreated()"
                                       t-att-value="getActiveOrder().payment_term || ''"
                                       t-on-input="(e) => onPaymentTermInput(e.target.value, e)"
                                       t-on-blur="onPaymentTermBlur"
                                       t-on-focus="onPaymentTermFocus"/>
                                <t t-if="showPaymentTermDropdown()">
                                    <div class="o_autocomplete_dropdown">
                                        <t t-foreach="state.paymentTermSuggestions" t-as="term" t-key="term.id">
                                            <div class="o_autocomplete_item" t-on-mousedown="() => selectPaymentTerm(term)">
                                                <span style="color:var(--bot-accent-light)">💳</span>
                                                <div>
                                                    <div class="o_autocomplete_item_name" t-esc="term.name"/>
                                                </div>
                                            </div>
                                        </t>
                                    </div>
                                </t>
                            </div>
                            <t t-if="getActiveOrder().payment_term_id">
                                <div class="o_field_status_indicator o_field_valid">
                                    <span>✓</span> Matched in system
                                </div>
                            </t>
                            <t t-elif="getActiveOrder().payment_term">
                                <div class="o_field_status_indicator o_field_warning">
                                    <span>!</span> Not yet verified in system
                                </div>
                            </t>
                        </div>

                        <!-- Sales Person -->
                        <div class="o_preview_field">
                            <div class="o_preview_field_label">Sales Person</div>
                            <div style="position:relative">
                                <input type="text"
                                       id="chatbot_salesperson"
                                       name="chatbot_salesperson"
                                       class="o_preview_input"
                                       placeholder="Type salesperson name..."
                                       t-att-disabled="isOrderCreated()"
                                       t-att-value="getActiveOrder().salesperson || ''"
                                       t-on-input="(e) => onSalespersonInput(e.target.value, e)"
                                       t-on-blur="onSalespersonBlur"
                                       t-on-focus="onSalespersonFocus"/>
                                <t t-if="showSalespersonDropdown()">
                                    <div class="o_autocomplete_dropdown">
                                        <t t-foreach="state.salespersonSuggestions" t-as="sp" t-key="sp.id">
                                            <div class="o_autocomplete_item" t-on-mousedown="() => selectSalesperson(sp)">
                                                <span style="color:var(--bot-accent-light)">👤</span>
                                                <div>
                                                    <div class="o_autocomplete_item_name" t-esc="sp.name"/>
                                                </div>
                                            </div>
                                        </t>
                                    </div>
                                </t>
                            </div>
                            <t t-if="getActiveOrder().user_id">
                                <div class="o_field_status_indicator o_field_valid">
                                    <span>✓</span> Matched in system
                                </div>
                            </t>
                            <t t-elif="getActiveOrder().salesperson">
                                <div class="o_field_status_indicator o_field_warning">
                                    <span>!</span> Not yet verified in system
                                </div>
                            </t>
                        </div>
                    </div>
                </div>

                <!-- AI missing fields -->
                <t t-if="hasMissingFields()">
                    <div class="o_preview_section">
                        <div class="o_preview_section_header">
                            <span>🔍</span> AI Needs More Info
                        </div>
                        <div class="o_preview_section_body">
                            <t t-foreach="getMissingFieldsList()" t-as="field" t-key="field_index">
                                <div style="display:flex;align-items:center;gap:8px;padding:6px 0;font-size:13px;color:var(--bot-warning)">
                                    <span>→</span>
                                    <span t-esc="field"/>
                                </div>
                            </t>
                        </div>
                    </div>
                </t>

                <!-- Confidence score -->
                <div class="o_preview_section">
                    <div class="o_preview_section_header">
                        <span>📈</span> AI Confidence Score
                    </div>
                    <div class="o_preview_section_body">
                        <div style="display:flex;align-items:center;gap:14px">
                            <div style="flex:1">
                                <div style="height:8px;background:var(--bot-bg-hover);border-radius:4px;overflow:hidden">
                                    <div t-att-style="getConfidenceBarStyle()"/>
                                </div>
                                <div style="display:flex;justify-content:space-between;margin-top:4px;font-size:11px;color:var(--bot-text-muted)">
                                    <span>0%</span><span>50%</span><span>100%</span>
                                </div>
                            </div>
                            <div t-att-style="'font-size:24px;font-weight:700;color:' + getConfidenceColor()">
                                <t t-esc="getConfidencePct()"/>%
                            </div>
                        </div>
                    </div>
                </div>

            </div>

            <!-- Submit bar -->
            <div class="o_preview_submit_bar">
                <t t-if="isOrderCreated()">
                    <div class="o_order_created_card">
                        <div class="o_order_created_icon">🎉</div>
                        <div class="o_order_created_title">Order Created!</div>
                        <div class="o_order_created_subtitle">
                            <strong t-esc="getCreatedOrderName()"/> has been created as a draft quotation.
                        </div>
                        <button type="button" class="o_order_link_btn" t-on-click="openSaleOrder">
                            <span>📋</span> View Sales Order
                        </button>
                    </div>
                </t>
                <t t-else="">
                    <t t-if="!isCurrentPageConfirmed()">
                        <div class="o_review_needed_card" style="margin-bottom:2px">
                            <div class="o_review_needed_icon">🔍</div>
                            <div class="o_review_needed_title">Verification Required</div>
                            <div class="o_review_needed_subtitle">
                                Please review the extracted details. You can edit any field directly. Once satisfied, click "Confirm Details" to unlock order generation.
                            </div>
                            <button type="button"
                                    class="o_bot_btn o_bot_btn_primary"
                                    style="width:100%;justify-content:center"
                                    t-on-click="confirmDetails"
                                    t-att-disabled="!canSubmit()">
                                ✓ Confirm Details
                            </button>
                        </div>
                    </t>
                    <t t-else="">
                        <div class="o_review_confirmed_card" style="margin-bottom:12px">
                            <div class="o_review_confirmed_icon">✅</div>
                            <div class="o_review_confirmed_title">Details Confirmed!</div>
                            <div class="o_review_confirmed_subtitle">
                                Everything looks good. Click below to create the Sales Order in Odoo.
                            </div>
                        </div>
                        <button type="button"
                                class="o_bot_btn o_bot_btn_success"
                                style="width:100%"
                                t-on-click="submitOrder">
                            <t t-if="props.isSubmitting">
                                <span class="o_processing_spinner" style="width:16px;height:16px;border-width:2px;border-top-color:#fff"/>
                                Creating Order...
                            </t>
                            <t t-else="">
                                🚀 Create Sales Order in Odoo
                            </t>
                        </button>
                    </t>
                    <div style="text-align:center;margin-top:3px;font-size:10px;color:var(--bot-text-muted)">
                        <t t-if="!canSubmit()">
                            Complete the required fields above to enable confirmation
                        </t>
                        <t t-elif="!isCurrentPageConfirmed()">
                            Click "Confirm Details" to review and lock details
                        </t>
                        <t t-else="">
                            Ready to generate Odoo Sales Order
                        </t>
                    </div>
                </t>
            </div>
        </div>
    `;

    static props = {
        orderData:          { optional: true },
        validationErrors:   { type: Array, optional: true },
        validationWarnings: { type: Array, optional: true },
        isSubmitting:       { type: Boolean, optional: true },
        saleOrderId:        { optional: true },
        saleOrderName:      { optional: true },
        sessionId:          { optional: true },
        productCategory:    { type: String, optional: true },
        onUpdateOrder:      { type: Function },
        onSubmitOrder:      { type: Function },
        onOpenSaleOrder:    { type: Function },
    };

    static defaultProps = {
        validationErrors:   [],
        validationWarnings: [],
        isSubmitting:       false,
    };

    setup() {
        this.state = useState({
            localData:           {
                orders: []
            },
            currentIndex:        0,
            showPartnerDropdown: false,
            partnerSuggestions:  [],
            productSuggestions:  [],
            activeProductIndex:  -1,
            showPaymentTermDropdown: false,
            paymentTermSuggestions:  [],
            showSalespersonDropdown: false,
            salespersonSuggestions:  [],
            confirmedPages:      {},
        });
        this.previewContent = useRef('previewContent');
        this._updateTimer = null;

        // Sync initial props
        this._syncData(this.props.orderData);

        // Sync whenever parent passes updated orderData
        onWillUpdateProps((nextProps) => {
            const nextData = nextProps.orderData || {};
            const oldStr = JSON.stringify(this.state.localData);
            const newStr = JSON.stringify(nextData);
            if (oldStr !== newStr) {
                this.state.confirmedPages = {};
                this._syncData(nextProps.orderData);
            }
        });

        // Bind methods to preserve 'this' context in template arrow functions
        this.onFieldInput = this.onFieldInput.bind(this);
        this.onCustomerInput = this.onCustomerInput.bind(this);
        this.onLpoNumberInput = this.onLpoNumberInput.bind(this);
        this.onLineInput = this.onLineInput.bind(this);
        this.addLine = this.addLine.bind(this);
        this.removeLine = this.removeLine.bind(this);
        this.onCustomerFocus = this.onCustomerFocus.bind(this);
        this.onCustomerBlur = this.onCustomerBlur.bind(this);
        this.onProductFocus = this.onProductFocus.bind(this);
        this.onProductBlur = this.onProductBlur.bind(this);
        this.selectPartner = this.selectPartner.bind(this);
        this.selectProduct = this.selectProduct.bind(this);
        this.onPaymentTermFocus = this.onPaymentTermFocus.bind(this);
        this.onPaymentTermBlur = this.onPaymentTermBlur.bind(this);
        this.onPaymentTermInput = this.onPaymentTermInput.bind(this);
        this.selectPaymentTerm = this.selectPaymentTerm.bind(this);
        this.onSalespersonFocus = this.onSalespersonFocus.bind(this);
        this.onSalespersonBlur = this.onSalespersonBlur.bind(this);
        this.onSalespersonInput = this.onSalespersonInput.bind(this);
        this.selectSalesperson = this.selectSalesperson.bind(this);
        this.confirmDetails = this.confirmDetails.bind(this);
        this.submitOrder = this.submitOrder.bind(this);
        this.openSaleOrder = this.openSaleOrder.bind(this);
        this.selectPage = this.selectPage.bind(this);
    }

    _syncData(orderData) {
        const defaults = {
            orders: []
        };
        let data = Object.assign({}, defaults, orderData);

        // Auto wrap single order structure for backward compatibility
        if (data && !data.orders && (data.customer || (data.order_lines && data.order_lines.length > 0))) {
            data = {
                orders: [data]
            };
        }

        if (!data.orders || data.orders.length === 0) {
            data.orders = [{
                customer: '',
                customer_id: null,
                customer_suggestions: [],
                payment_term: '',
                payment_term_id: null,
                salesperson: '',
                user_id: null,
                order_lines: [],
                delivery_date: '',
                quotation_date: '',
                notes: '',
                confidence: 0,
                missing_fields: [],
                lpo_number: '',
                sale_order_id: null,
                sale_order_name: null,
                state: 'draft',
                errors: [],
                warnings: []
            }];
        }

        // Deep copy / sanitize order lines width, height, discount
        data.orders = JSON.parse(JSON.stringify(data.orders));
        for (let order of data.orders) {
            if (order.order_lines) {
                for (let line of order.order_lines) {
                    if (line.height === undefined || line.height === null) {
                        line.height = 1.0;
                    }
                    if (line.width === undefined || line.width === null) {
                        line.width = 1.0;
                    }
                    if (line.discount === undefined || line.discount === null) {
                        line.discount = 0.0;
                    }
                }
            }
        }

        if (this.state.currentIndex >= data.orders.length) {
            this.state.currentIndex = 0;
        }

        const oldLinesCount = (this.getActiveOrder().order_lines || []).length;
        this.state.localData = data;
        const newLinesCount = (this.getActiveOrder().order_lines || []).length;

        // Auto scroll to bottom if new product lines are added
        if (newLinesCount > oldLinesCount || (newLinesCount > 0 && oldLinesCount === 0)) {
            this.scrollToBottom();
        }
    }

    scrollToBottom() {
        const container = this.previewContent.el;
        if (container) {
            setTimeout(() => {
                container.scrollTop = container.scrollHeight;
            }, 50);
        }
    }

    // ---- Multiple orders helpers ----

    getActiveOrder() {
        const orders = this.state.localData.orders || [];
        if (orders.length === 0) return {};
        const idx = this.state.currentIndex || 0;
        return orders[idx] || orders[0] || {};
    }

    getOrdersCount() {
        return (this.state.localData.orders || []).length;
    }

    selectPage(index) {
        this.state.currentIndex = index;
    }

    getPageLabel(order, index) {
        if (order.lpo_number) {
            return `Page ${index + 1} (${order.lpo_number})`;
        }
        return `Page ${index + 1}`;
    }

    isOrderCreated() {
        const active = this.getActiveOrder();
        if (this.getOrdersCount() > 1) {
            return !!active.sale_order_id;
        }
        return !!(active.sale_order_id || this.props.saleOrderId);
    }

    getCreatedOrderId() {
        if (this.getOrdersCount() > 1) {
            return this.getActiveOrder().sale_order_id;
        }
        return this.getActiveOrder().sale_order_id || this.props.saleOrderId;
    }

    getCreatedOrderName() {
        if (this.getOrdersCount() > 1) {
            return this.getActiveOrder().sale_order_name;
        }
        return this.getActiveOrder().sale_order_name || this.props.saleOrderName;
    }

    isCurrentPageConfirmed() {
        return !!this.state.confirmedPages[this.state.currentIndex];
    }

    _invalidateConfirmed() {
        this.state.confirmedPages[this.state.currentIndex] = false;
    }

    // ---- Template condition helpers ----

    showEmptyState() {
        return !this.hasOrderData();
    }

    showOrderData() {
        return this.hasOrderData();
    }

    hasOrderData() {
        const d = this.getActiveOrder();
        if (!d) return false;
        return !!(d.customer || (d.order_lines && d.order_lines.length > 0));
    }

    hasValidationIssues() {
        const active = this.getActiveOrder();
        return active.errors && active.errors.length > 0;
    }

    hasMissingFields() {
        return this.getMissingFieldsList().length > 0;
    }

    getMissingFieldsList() {
        const d = this.getActiveOrder();
        if (!d) return [];
        const missing = [];

        const isCustomerMissing = !d.customer || d.customer.trim() === '' || d.customer === 'UNRESOLVED';
        
        let isProductMissing = false;
        let isQtyMissing = false;
        let isPriceMissing = false;
        
        if (!d.order_lines || d.order_lines.length === 0) {
            isProductMissing = true;
        } else {
            for (const line of d.order_lines) {
                if (!line.product || line.product.trim() === '' || line.product === 'UNRESOLVED') {
                    isProductMissing = true;
                }
                if (line.qty === undefined || line.qty === null || parseFloat(line.qty) <= 0) {
                    isQtyMissing = true;
                }
                if (line.price === undefined || line.price === null || parseFloat(line.price) <= 0) {
                    isPriceMissing = true;
                }
            }
        }

        const isQuotationDateMissing = !d.quotation_date || d.quotation_date.trim() === '';

        if (isCustomerMissing) missing.push("Customer Name");
        if (isProductMissing) missing.push("Product Name");
        if (isQtyMissing) missing.push("Product Quantity");
        if (isPriceMissing) missing.push("Product Price");
        if (isQuotationDateMissing) missing.push("Quotation Date");

        if (missing.length === 0) {
            if (!d.delivery_date || d.delivery_date.trim() === '') {
                missing.push("Delivery Date");
            }
            if (!d.payment_term || d.payment_term.trim() === '') {
                missing.push("Payment Term");
            }
            if (!d.salesperson || d.salesperson.trim() === '') {
                missing.push("Sales Person");
            }
            if (!d.notes || d.notes.trim() === '') {
                missing.push("Notes");
            }
        }

        return missing;
    }

    showPartnerDropdown() {
        return this.state.showPartnerDropdown && this.state.partnerSuggestions.length > 0;
    }

    showProductDropdown(index) {
        return this.state.activeProductIndex === index && this.state.productSuggestions.length > 0;
    }

    showPaymentTermDropdown() {
        return this.state.showPaymentTermDropdown && this.state.paymentTermSuggestions.length > 0;
    }

    showSalespersonDropdown() {
        return this.state.showSalespersonDropdown && this.state.salespersonSuggestions.length > 0;
    }

    getValidationWarnings() {
        return this.getActiveOrder().warnings || [];
    }

    getLineCount() {
        return (this.getActiveOrder().order_lines || []).length;
    }

    // ---- Confidence display helpers ----

    getConfidenceClass() {
        const c = this.getConfidencePct();
        if (c >= 75) return 'o_confidence_high';
        if (c >= 40) return 'o_confidence_medium';
        return 'o_confidence_low';
    }

    getConfidenceLabel() {
        const c = this.getConfidencePct();
        if (c >= 75) return `✓ ${c}% Confident`;
        if (c >= 40) return `~ ${c}% Partial`;
        return `✗ ${c}% Low`;
    }

    getConfidenceColor() {
        const c = this.getConfidencePct();
        if (c >= 75) return 'var(--bot-success)';
        if (c >= 40) return 'var(--bot-warning)';
        return 'var(--bot-danger)';
    }

    getConfidenceBarStyle() {
        const c = this.getConfidencePct();
        return `height:100%;border-radius:4px;width:${c}%;background:${this.getConfidenceColor()};transition:width 0.6s ease`;
    }

    getConfidencePct() {
        const d = this.getActiveOrder();
        if (!d) return 0;
        
        const hasCustomer = d.customer && d.customer.trim() !== '' && d.customer !== 'UNRESOLVED';
        
        let hasProducts = false;
        if (d.order_lines && d.order_lines.length > 0) {
            hasProducts = true;
            for (const line of d.order_lines) {
                if (!line.product || line.product.trim() === '' || line.product === 'UNRESOLVED') {
                    hasProducts = false;
                    break;
                }
                const qty = parseFloat(line.qty);
                const price = parseFloat(line.price);
                if (isNaN(qty) || qty <= 0 || line.price === undefined || line.price === null || isNaN(price) || price <= 0) {
                    hasProducts = false;
                    break;
                }
            }
        }
        
        const hasQuotation = d.quotation_date && d.quotation_date.trim() !== '';
        
        let reqCount = 0;
        if (hasCustomer) reqCount++;
        if (hasProducts) reqCount++;
        if (hasQuotation) reqCount++;
        
        let confidence = reqCount * 20;
        
        if (reqCount === 3) {
            if (d.payment_term && d.payment_term.trim() !== '' && d.payment_term !== 'UNRESOLVED') {
                confidence += 10;
            }
            if (d.delivery_date && d.delivery_date.trim() !== '') {
                confidence += 10;
            }
            if (d.salesperson && d.salesperson.trim() !== '' && d.salesperson !== 'UNRESOLVED') {
                confidence += 10;
            }
            if (d.notes && d.notes.trim() !== '') {
                confidence += 10;
            }
        }
        
        return Math.round(confidence);
    }

    // ---- Field/line status helpers ----

    getFieldStatus(field) {
        const val = this.getActiveOrder()[field];
        if (!val || val === 'UNRESOLVED') return 'invalid';
        return 'valid';
    }

    getLineStatus(line) {
        if (line.product_id) return 'valid';
        if (line.product) return 'unknown';
        return 'invalid';
    }

    getLineStatusText(line) {
        if (line.product_id) return 'Product found in system';
        if (line.product)    return 'Product not yet verified';
        return 'No product name';
    }

    canSubmit() {
        if (this.props.isSubmitting) return false;
        if (this.isOrderCreated())  return false;
        const d = this.getActiveOrder();
        const hasCustomer = d.customer && d.customer !== 'UNRESOLVED';
        const hasLines    = d.order_lines && d.order_lines.length > 0 &&
                            d.order_lines.some(l => l.product && l.product !== 'UNRESOLVED');
        return !!(hasCustomer && hasLines);
    }

    // ---- Field editing ----

    onFieldInput(field, value, e) {
        this._invalidateConfirmed();
        const active = this.getActiveOrder();
        if (active) {
            active[field] = value;
        }
        this._debounceUpdate();
    }

    onCustomerInput(value, e) {
        this._invalidateConfirmed();
        const active = this.getActiveOrder();
        if (active) {
            active.customer = value;
            active.customer_id = null;
        }
        this.state.showPartnerDropdown = true;
        this._searchPartners(value);
        this._debounceUpdate();
    }

    onLpoNumberInput(value, e) {
        this._invalidateConfirmed();
        const active = this.getActiveOrder();
        if (active) {
            const cleanedValue = value.replace(/#/g, '');
            active.lpo_number = cleanedValue;
        }
        this._debounceUpdate();
    }

    onLineInput(index, field, value, e) {
        this._invalidateConfirmed();
        const active = this.getActiveOrder();
        if (active) {
            const lines = [...(active.order_lines || [])];
            let val = value;
            if (field === 'qty') {
                val = parseFloat(value) || 1;
            } else if (field === 'height') {
                val = value === '' ? 1.0 : (parseFloat(value) || 1.0);
            } else if (field === 'width') {
                val = value === '' ? 1.0 : (parseFloat(value) || 1.0);
            } else if (field === 'price') {
                val = value === '' ? null : (parseFloat(value) || null);
            } else if (field === 'discount') {
                val = value === '' ? 0.0 : (parseFloat(value) || 0.0);
            }
            lines[index] = { ...lines[index], [field]: val };
            if (field === 'product') {
                lines[index].product_id = null;
                lines[index].validated  = false;
                this._searchProducts(value, index);
            }
            if (field === 'tax') {
                lines[index].tax_id = null;
                lines[index].tax_ids = [];
            }
            active.order_lines = lines;
        }
        this._debounceUpdate();
    }

    addLine() {
        this._invalidateConfirmed();
        const active = this.getActiveOrder();
        if (active) {
            const lines = [...(active.order_lines || [])];
            lines.push({ product: '', qty: 1, height: 1.0, width: 1.0, price: null, uom: '', product_id: null, discount: 0.0, tax: '', tax_ids: [], tax_id: null });
            active.order_lines = lines;
        }
        this._debounceUpdate();
    }

    removeLine(index) {
        this._invalidateConfirmed();
        const active = this.getActiveOrder();
        if (active) {
            const lines = [...(active.order_lines || [])];
            lines.splice(index, 1);
            active.order_lines = lines;
        }
        this._debounceUpdate();
    }

    // ---- Partner autocomplete ----

    onCustomerFocus() {
        this.state.showPartnerDropdown = true;
        const val = this.getActiveOrder().customer || '';
        if (val.length >= 2) {
            this._searchPartners(val);
        } else {
            this.state.partnerSuggestions = [];
        }
    }

    onCustomerBlur() {
        setTimeout(() => {
            this.state.showPartnerDropdown = false;
            this.state.partnerSuggestions = [];
        }, 200);
    }

    async _searchPartners(query) {
        if (!query || query.length < 2) { this.state.partnerSuggestions = []; return; }
        try {
            const result = await this._rpc('/sale_order_ai_chatbot/autocomplete/partners', { query });
            this.state.partnerSuggestions = result.results || [];
        } catch (_) {}
    }

    selectPartner(partner) {
        this._invalidateConfirmed();
        const active = this.getActiveOrder();
        if (active) {
            active.customer    = partner.name;
            active.customer_id = partner.id;
        }
        this.state.showPartnerDropdown   = false;
        this.state.partnerSuggestions    = [];
        this._debounceUpdate();
    }

    // ---- Product autocomplete ----

    onProductFocus(index) {
        this.state.activeProductIndex = index;
        const line = (this.getActiveOrder().order_lines || [])[index];
        if (line && line.product && line.product.length >= 2) {
            this._searchProducts(line.product, index);
        } else {
            this.state.productSuggestions = [];
        }
    }

    onProductBlur(index) {
        setTimeout(() => {
            if (this.state.activeProductIndex === index) {
                this.state.activeProductIndex = -1;
                this.state.productSuggestions = [];
            }
        }, 200);
    }

    async _searchProducts(query, index) {
        if (!query || query.length < 2) { this.state.productSuggestions = []; return; }
        try {
            const result = await this._rpc('/sale_order_ai_chatbot/autocomplete/products', { 
                query,
                session_id: this.props.sessionId
            });
            if (this.state.activeProductIndex === index) {
                this.state.productSuggestions = result.results || [];
            }
        } catch (_) {}
    }

    selectProduct(index, prod) {
        this._invalidateConfirmed();
        const active = this.getActiveOrder();
        if (active) {
            const lines = [...(active.order_lines || [])];
            lines[index] = {
                ...lines[index],
                product:    prod.name,
                product_id: prod.id,
                price:      lines[index].price || prod.price,
                uom:        prod.uom || '',
                validated:  true,
            };
            active.order_lines  = lines;
        }
        this.state.activeProductIndex     = -1;
        this.state.productSuggestions     = [];
        this._debounceUpdate();
    }

    // ---- Payment Term autocomplete ----

    onPaymentTermFocus() {
        this.state.showPaymentTermDropdown = true;
        const val = this.getActiveOrder().payment_term || '';
        if (val.length >= 2) {
            this._searchPaymentTerms(val);
        } else {
            this.state.paymentTermSuggestions = [];
        }
    }

    onPaymentTermBlur() {
        setTimeout(() => {
            this.state.showPaymentTermDropdown = false;
            this.state.paymentTermSuggestions = [];
        }, 200);
    }

    onPaymentTermInput(value, e) {
        this._invalidateConfirmed();
        const active = this.getActiveOrder();
        if (active) {
            active.payment_term = value;
            active.payment_term_id = null;
        }
        this._searchPaymentTerms(value);
        this._debounceUpdate();
    }

    async _searchPaymentTerms(query) {
        if (!query || query.length < 2) { this.state.paymentTermSuggestions = []; return; }
        try {
            const result = await this._rpc('/sale_order_ai_chatbot/autocomplete/payment_terms', { query });
            this.state.paymentTermSuggestions = result.results || [];
        } catch (_) {}
    }

    selectPaymentTerm(term) {
        this._invalidateConfirmed();
        const active = this.getActiveOrder();
        if (active) {
            active.payment_term = term.name;
            active.payment_term_id = term.id;
        }
        this.state.showPaymentTermDropdown = false;
        this.state.paymentTermSuggestions = [];
        this._debounceUpdate();
    }

    // ---- Salesperson autocomplete ----

    onSalespersonFocus() {
        this.state.showSalespersonDropdown = true;
        const val = this.getActiveOrder().salesperson || '';
        if (val.length >= 2) {
            this._searchSalespersons(val);
        } else {
            this.state.salespersonSuggestions = [];
        }
    }

    onSalespersonBlur() {
        setTimeout(() => {
            this.state.showSalespersonDropdown = false;
            this.state.salespersonSuggestions = [];
        }, 200);
    }

    onSalespersonInput(value, e) {
        this._invalidateConfirmed();
        const active = this.getActiveOrder();
        if (active) {
            active.salesperson = value;
            active.user_id = null;
        }
        this._searchSalespersons(value);
        this._debounceUpdate();
    }

    async _searchSalespersons(query) {
        if (!query || query.length < 2) { this.state.salespersonSuggestions = []; return; }
        try {
            const result = await this._rpc('/sale_order_ai_chatbot/autocomplete/salespersons', { query });
            this.state.salespersonSuggestions = result.results || [];
        } catch (_) {}
    }

    selectSalesperson(sp) {
        this._invalidateConfirmed();
        const active = this.getActiveOrder();
        if (active) {
            active.salesperson = sp.name;
            active.user_id = sp.id;
        }
        this.state.showSalespersonDropdown = false;
        this.state.salespersonSuggestions = [];
        this._debounceUpdate();
    }

    // ---- Debounced sync to parent ----

    _debounceUpdate() {
        clearTimeout(this._updateTimer);
        this._updateTimer = setTimeout(() => {
            const data = JSON.parse(JSON.stringify(this.state.localData));
            const active = data.orders[this.state.currentIndex];
            if (active) {
                active.confidence = this.getConfidencePct();
            }
            this.props.onUpdateOrder(data);
        }, 600);
    }

    // ---- Submit ----

    async submitOrder() {
        if (!this.canSubmit()) return;
        await this.props.onSubmitOrder(JSON.parse(JSON.stringify(this.getActiveOrder())));
    }

    confirmDetails() {
        if (this.canSubmit()) {
            this.state.confirmedPages[this.state.currentIndex] = true;
        }
    }

    openSaleOrder() {
        this.props.onOpenSaleOrder(this.getCreatedOrderId());
    }

    // ---- JSON-RPC helper ----

    async _rpc(route, params = {}) {
        const response = await fetch(route, {
            method:  'POST',
            headers: {
                'Content-Type':     'application/json',
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params }),
        });
        const data = await response.json();
        return data.result || {};
    }
}
