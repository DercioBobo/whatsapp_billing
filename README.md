# WhatsApp Billing

Automated WhatsApp/USSD session billing for ERPNext.

Compatible with ERPNext v13, v14, v15.

## Overview

This app lets you bill ERPNext Customers based on daily unique end-user sessions
fetched from an external JSON API.

**Billing logic:**
- 1 billable unit = 1 unique end-user that had at least 1 session on a given calendar day
- Billing period = calendar month
- `total_amount = total_billable_units × price_per_unit`

## Installation

```bash
# From your bench directory
bench get-app https://github.com/your-org/whatsapp_billing
bench --site yoursite.local install-app whatsapp_billing
bench --site yoursite.local migrate
```

## Usage

1. **Create a WhatsApp Billing Config** for each ERPNext Customer:
   - Set the API endpoint, optional Bearer token, price per unit, and billing item.

2. **Create a Sales Invoice** for the customer as usual.

3. **Enable WhatsApp Billing** on the invoice:
   - Check the *WhatsApp Billing Invoice* checkbox in the *WhatsApp Billing* section.
   - The app auto-populates the Billing Config and sets the previous calendar month.

4. **Click "Fetch WhatsApp Usage"**:
   - The app calls the API, counts unique (end-user, date) pairs for the month,
     updates the invoice items row, and creates a WhatsApp Usage Log for audit.

5. **Review and submit** the invoice normally.

## DocTypes

| DocType | Purpose |
|---|---|
| `WhatsApp Billing Config` | Per-customer API endpoint, pricing, and billing item |
| `WhatsApp Usage Log` | Immutable audit record per calculation run |

## Custom Fields on Sales Invoice

| Field | Type | Purpose |
|---|---|---|
| `wb_enabled` | Check | Opt this invoice into WhatsApp Billing |
| `wb_config` | Link | Points to WhatsApp Billing Config |
| `wb_billing_month` | Data | Target month (YYYY-MM) |
| `wb_total_units` | Int | Billable units (read-only, set by app) |
| `wb_last_fetched` | Datetime | Timestamp of last fetch |
| `wb_usage_log` | Link | Link to WhatsApp Usage Log |

## API Endpoints (whitelisted)

| Method | Description |
|---|---|
| `whatsapp_billing.api.billing.get_usage` | Fetch & calculate — read-only |
| `whatsapp_billing.api.billing.apply_usage_to_invoice` | Fetch, apply, save |
| `whatsapp_billing.api.billing.get_config_for_customer` | Auto-populate config |

## License

MIT
