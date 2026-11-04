# Dataset provenance and scope

Provider: **Bitext**. Source: https://github.com/bitext/customer-support-llm-chatbot-training-dataset
License: **Community Data License Agreement ? Sharing 1.0** (unmodified copy: [DATA_LICENSE.txt](DATA_LICENSE.txt)). Computational use and publication are permitted under its terms. Preserve attribution and the same license when redistributing the dataset or modified data. Results are separately covered by section 3.5. No raw dataset is checked into this project.

The pinned revision and SHA-256 are in `artifacts/dataset-source.json`. `python -m ml.download` saves the CSV, upstream README, license, and source manifest in `data/raw/`. Retain `source.json` to reuse the same revision. To recreate from an entirely fresh checkout, copy `artifacts/dataset-source.json` to `data/raw/source.json` before downloading.

## Verified label meanings

Only the customer `instruction` is used as input. The `category` column is the target. Responses, intent labels, and generation tags are excluded from model features. The CSV has **27 intents and 11 categories**. The upstream README describes 10 categories; this project uses the actual pinned CSV and explicitly records the discrepancy.

| Dataset category | Dataset intents | Invented example team |
| --- | --- | --- |
| ACCOUNT | create_account, delete_account, edit_account, recover_password, registration_problems, switch_account | Account Care |
| CANCEL | check_cancellation_fee | Order Operations |
| CONTACT | contact_customer_service, contact_human_agent | Customer Care |
| DELIVERY | delivery_options, delivery_period | Fulfillment |
| FEEDBACK | complaint, review | Customer Care |
| INVOICE | check_invoice, get_invoice | Billing |
| ORDER | cancel_order, change_order, place_order, track_order | Order Operations |
| PAYMENT | check_payment_methods, payment_issue | Billing |
| REFUND | check_refund_policy, get_refund, track_refund | Returns |
| SHIPPING | change_shipping_address, set_up_shipping_address | Fulfillment |
| SUBSCRIPTION | newsletter_subscription | Account Care |

These are intent/category labels, **not actual Bitext operational teams**. Teams are examples defined in `config/routing.json`. Unknown/unmapped labels enter review. Routing snapshots are persisted with each inference; reviews preserve their chosen team separately.

## Leakage controls and limitations

Normalize with Unicode NFKC, lowercase, remove punctuation, replace numbered/entity slots. Exclude exact normalized strings that have conflicting categories, then remove exact duplicates. A stateless character 3?5-gram hashing representation forms a cosine-radius graph (similarity >=0.85); connected components are indivisible split groups. Five seeded stratified group folds allocate folds 2?4 to training, fold 1 to validation, and fold 0 to test. Fitted TF-IDF vocabulary and IDF use training only. BERT uses its original pretrained tokenizer; task weights train on training rows only.

Near-duplicate grouping occurs before splitting and without fitting a vocabulary/IDF on held-out text. Cross-label similarity edges are also grouped. This conservative transitive closure creates a large 3,953-row group and uneven split sizes. Exact and above-threshold character near duplicates cannot cross splits. The dataset lacks seed/template family IDs, so more distant semantic paraphrases may still cross splits; this method cannot certify independence of every synthetic generation family.

Source language is English. Bitext describes hybrid synthetic generation from natural-text seeds, NLP and NLG, curated by linguists. This is short customer-intent language, not a collection of real multi-turn support tickets. No deployment accuracy, real users, multilingual coverage or production scale is implied. In-domain confidence can be high for unfamiliar/ambiguous messages; the manual-review threshold is not an out-of-distribution detector.

Prepared rows and split manifests are locally generated **modified data derived from Bitext**, attributed to Bitext, and remain under CDLA-Sharing-1.0 if distributed. Representative error texts in evaluation reports are Bitext excerpts; they retain this attribution and license. Keep this file and the license with exported artifacts.
