# Fictional company allowance policy

Policy ID: DEMO-ALLOWANCE. Version: 1.0. Effective date: 2026-01-01.
Currency: MYR. This example must be replaced and approved before real employee use.

## Eligibility
Employees may prepare drafts for business expenses from 2026-01-01 onward.
Claims must identify the employee, expense date, business purpose, and claim category.
Future expense dates are ineligible. The deadline is 30 calendar days after the expense,
inclusive. This example does not cover advances, foreign currency, commuting, or personal expenses.

## Mileage
Business mileage is reimbursed at RM0.60 per kilometre, capped at RM300.00 per claim.
A route and positive distance are required. A receipt is not required. Normal commuting
and personal trips are ineligible; the employee must affirm business travel.

## Meal
Business meals are reimbursed at the actual receipt amount, capped at RM30.00 per claim.
A receipt, business purpose, and employee affirmation of business expense are required.

## Parking
Business parking is reimbursed at the actual receipt amount, capped at RM50.00 per claim.
A receipt, business purpose, and employee affirmation of business expense are required.

## Lodging
Business lodging is reimbursed at the actual receipt amount, capped at RM180.00 per night.
The number of nights must be a positive integer. A receipt, business purpose, and employee
affirmation of business expense are required. Only the supported lodging total is eligible.

## Evidence and rounding
Receipts must show merchant, expense date, total, and MYR currency. Extracted fields are
proposals: the user must review and confirm them. The receipt date and amount must match
the claim. Amounts must be positive with at most two decimal places. Amounts are rounded
to two decimal places with ROUND_HALF_UP. No tax additions or duplicate receipts are allowed.
Duplicate evidence is checked against this assistant's saved drafts only, not existing eClaim records.

## Drafts and approval
The assistant prepares local drafts only. It must show the applicable policy, calculation,
missing fields, and supporting evidence before asking for confirmation. A saved draft is
not approval, payment, or submission to the Spring Boot eClaim system.
