# M11.1 — Extraction evaluation

Offline results on `m11_extraction_eval_v1` measure the current M4 extractor against synthetic ground truth. They are not a claim about production accuracy.

## Architecture

`python -m app.evaluation.m11_runner` builds an in-memory source for each case, classifies it, and runs the existing `build_candidate` function. The scorer compares that prediction with the case ground truth. It does not call Gemini, the network, or a database.

`--live` scores only `clean-invoice` with the existing Gemini extractor. If `GEMINI_API_KEY` is unset, the command exits 0 and reports `KEY_ABSENT_LIVE_SKIPPED`. Offline evaluation does not depend on that key.

M6 is `NOT_RUN` in the offline comparison. A delta is present only for a live case result.

## Dataset

`m11_extraction_eval_v1` has 20 synthetic cases: clean invoice, purchase order, and goods receipt; decimal quantity and price; tax; multiple lines; absent optional fields; an unambiguous day-first date; currency formatting; vendor whitespace and case; identical-looking identifiers on different fields; malformed values; a line without a price; an unexpected identifier; an empty source; noisy text; an XLSX-style table; PDF-style text; and OCR-style text. No real personal data is included.

## Ground truth

`GroundTruth` stores the expected document type, vendor, PO number, invoice number, GRN number, dates, currency, subtotal, tax, total, and lines. A null field is not expected. Line fields are item identifier, description, quantity, unit price, tax rate, and line total.

## Normalization

- Vendor names and descriptions: trim, collapse whitespace, casefold.
- Identifiers: trim and collapse whitespace. Case is preserved. A case-only difference is `NORMALIZATION_MISMATCH`.
- Dates: compare canonical dates. ISO dates parse. `DD/MM/YYYY` parses only when the day is greater than 12. Ambiguous dates do not match.
- Decimals: parse after removing currency symbols and thousands commas. Absolute tolerance is 0. `10` equals `10.00`. `18` does not equal `0.18`. Floats do not parse.
- Currency: compare uppercase letters. A symbol is not mapped to a code.
- Lines: pair on item identifier when both sides have one, otherwise on a unique normalized description. Line order is not a match key.

## Metrics

Header accuracy = correct header fields / header fields that were predicted and expected.

Header completeness = correct header fields / non-null expected header fields.

Line accuracy = correct fields on matched lines / expected fields on matched lines.

Line completeness = correct line fields / expected line fields, including fields on unmatched lines.

Document exact-match rate = cases with zero errors / cases.

Document success rate = cases with no blocking error / cases. `UNEXPECTED_FIELD` fails exact match and does not, by itself, fail success. Every other category fails both.

The report prints each numerator and denominator.

## Errors

`MISSING_FIELD`, `INCORRECT_FIELD`, `NORMALIZATION_MISMATCH`, `NUMERIC_MISMATCH`, `DATE_MISMATCH`, `MISSING_LINE`, `EXTRA_LINE`, `LINE_FIELD_MISMATCH`, `DOCUMENT_TYPE_MISMATCH`, `EMPTY_EXTRACTION`, `UNEXPECTED_FIELD`.

Each error stores the case, field, expected value, predicted value, and category. It does not store source text.

## Regression gates

`REGRESSION_GATES` in `app/evaluation/m11_harness.py` freeze the M11.1 offline measurement on this dataset:

- header accuracy `1.0000` (58/58)
- header completeness `0.7733` (58/75)
- line accuracy `0.9667` (29/30)
- line completeness `0.6170` (29/47)
- exact-match rate `0.6000` (12/20)

A later extractor change that drops a listed metric below its floor fails the runner. These floors are engineering regression gates. They are not production accuracy targets. Header accuracy excludes fields the extractor did not predict; completeness is the metric that counts those misses.
