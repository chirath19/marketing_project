# Unified payments workspace

Invoices and receipts now appear together under **Payments** for each client. The previous invoice and receipt URLs remain available and both open the unified workspace.

## Owner and staff workflow

1. Open a client's **Payments** area and select **Create invoice**.
2. Enter the scope, amount, currency and dates. Save a draft or select the option to issue it to the client immediately.
3. Edit a draft before issuing it. Once issued, its original details are preserved; corrections use voiding and a replacement invoice.
4. On an issued invoice, choose **Record payment & issue receipt**. The invoice, client, currency and related service are fixed to that invoice. The outstanding balance is prefilled as the amount; enter a smaller amount for a partial payment.
5. Confirm the payment date and method, then issue the receipt after receiving the payment.

Each invoice shows its total, paid amount, remaining balance and linked receipts. **Record other payment** also supports payments without an invoice. Receipts and invoices link to each other and use matching printable layouts. Clients see their own issued invoices and receipts; they cannot record payments.

## References and correctness

- Dashboard references are generated automatically: `INV-YYYY-00001` for invoices and `RCT-YYYY-00001` for receipts. The year is the allocation year.
- Invoice and receipt counters are separate and protected by database locks. Existing references are preserved, including references supplied by import/service callers. Allocation skips occupied references.
- Dashboard forms carry a submission key. Repeating a successful submission returns its original document instead of creating another invoice or receipt.
- Partial payments are supported. Invoice balance is derived from non-voided receipts; it is not an independently editable total.
- Payments cannot exceed the outstanding balance, including simultaneous submissions, and must match the invoice currency and recipient.
- Voiding a receipt retains the record and restores the related invoice balance. An invoice with active recorded payments cannot be voided until those receipts are corrected.
- Summary totals are separated by currency. Draft and voided invoices are excluded from issued/outstanding totals; voided receipts are excluded from received totals. Received totals include payments without invoices.

This is a manual payment-record workflow. It does not charge a card, initiate a transfer or send outbound email/SMS.

## Idle chat refresh

The chat poll now compares the incoming message panel with the displayed panel. If its content is unchanged, no DOM replacement occurs. Search visibility is ignored in that comparison, so searching does not trigger idle replacements. Changed feeds restore the reading position immediately after swapping, rather than after the settling delay. Drafts and search fields remain outside the refreshed region.

Browser verification confirmed that the same feed and message DOM nodes remain connected across timed idle polls in both Messages and quotation chat. New incoming messages still appear afterward.

## Deployment and verification

Migration `subscriptions.0004_billingsequence_invoice_submission_key_and_more` adds the global numbering counter and optional submission keys; it does not rewrite existing records. It has been applied to the local project database. Run migrations and `npm run css` when deploying elsewhere.

Focused tests cover numbering, concurrent allocation, duplicate submissions, draft editing, partial payments, correction history, currency separation and client isolation. Browser checks cover the invoice-to-receipt journey, desktop/mobile layouts, document links, printing and idle chat behavior. Screenshots and accessibility results in `docs/payments-redesign/` use an isolated test database.

Final verification: the full regression suite passed with **2,427 passed and 2 skipped**. The browser workflow passed, with no accessibility violations or horizontal overflow on the 12 checked payment screens. Django system checks, migration consistency, Ruff, JavaScript syntax checks and the CSS build also passed.
