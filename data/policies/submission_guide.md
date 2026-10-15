# Fictional submission guide

Policy ID: DEMO-ALLOWANCE. Version: 1.0. Effective date: 2026-01-01.

## Required fields
Provide employee_id, category, expense_date (YYYY-MM-DD), purpose, and business_expense=true.
Mileage also needs distance_km and route. Meal and parking need amount and confirmed receipt.
Lodging needs amount, nights, and confirmed receipt. Only MYR is supported.

## Receipt review
Paste receipt text, read an image through browser OCR, or use the optional vision/local OCR path.
Verify merchant, date, total, and currency, then confirm the evidence. Extraction never
proves authenticity. Replacing evidence clears its confirmation.

## Confirmation
Review the proposed amount and policy citations. Send exactly `confirm` or use the API's
confirm=true action to save the current ready draft. Changes invalidate readiness and
require a new review. Send `new` to start another claim in the same session.
