{% docs __overview__ %}

# legacy-erp-dbt

A legacy ERP's undocumented stock-movement data, modeled into trustworthy
marts, where every rule found in the raw data is enforced by an automated test.

The story: a fictional industrial-parts distributor (bearings, seals, belts)
runs a legacy Turkish ERP. It has two depots, sells to customers and dealers,
and buys from suppliers in EUR, USD and TL. **All data is synthetic**: every
company, product code, account and price is invented.

## Layers

| Layer | Schema | Job |
|---|---|---|
| Seeds | `raw`, `reference` | The ERP export, every column as text. Plus `account_reviews`: human decisions the data cannot make. |
| Staging | `staging` | Rename, cast, clean. Changes the format, never the meaning. |
| Intermediate | `intermediate` | Every business rule, once: flows, account classes, latest cost, currency evidence, stock and invoice reconciliation. |
| Marts | `marts` | The public interface. A star schema with enforced contracts: `dim_products`, `dim_accounts`, `fct_sales`, `fct_stock_positions`, `fct_sale_invoices`. |

The seed `trap_manifest` (schema `answer_key`) is the generator's answer key.
Tests read it; models never do, and a test enforces that.

## The traps

Each trap is something naive SQL gets wrong. Each one has an answer-key test
in `tests/answer_key/`, and most also have an invariant that would run on
real data.

| Trap | What naive SQL gets wrong |
|---|---|
| T1 | Counting only invoices loses open sales, which are never invoiced. |
| T2 | Using the cost-named columns, which are 0 on every row. |
| T3 | Taking the latest inbound price by date: a return can win. |
| T4 | Same-date ties: the "latest" cost changes between runs. |
| T5 | Treating a customer adjustment price as a cost. |
| T6 | Mixing dealer and end-customer sales. |
| T7 | Reporting internal counter-accounts under 120- as customer sales. |
| T8 | Excluding collector accounts, which are real revenue. |
| T9 | Netting purchase returns against sales on dealer accounts. |
| T10 | `COALESCE(balance, 0)` hides products missing from the balance view. |
| T11 | Picking one stock source as the truth. |
| T12 | Ignoring a third depot the depot source does not know. |
| T13 | Trusting the master's currency flag, which can be wrong. |
| T14 | Recomputing invoices without VAT or at the wrong grain. |
| T15 | Joining on dirty product codes, or on a shared base code. |
| T16 | Recomputing totals from 2-decimal display prices. |

## Tests

- **Invariants** hold on any data and never read the answer key.
- **Answer-key tests** (tag `answer_key`) compare the models with the answer
  key in both directions: every planted case is found, and nothing else is.
  A production run excludes them: `dbt build --exclude tag:answer_key`.
- **Monitors** (`severity: warn`) report the ERP's known data problems on
  every run (T10, T11, T13) without failing the build.

Start with the lineage graph (bottom right), or open `fct_sales`.

{% enddocs %}
