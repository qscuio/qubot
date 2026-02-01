# Paginate EastMoney Spot Data (HTTP Crawler)

## Context
`HttpCrawlerProvider.get_all_spot_data()` and `get_stock_list()` call EastMoney `clist/get` with `pz=10000`, but the API caps responses to 100 rows. As a result, the service only retrieves ~100 A-share stocks instead of ~5800+, which breaks initial DB population and sync.

## Decision
Implement pagination for the EastMoney `clist/get` endpoint in both `get_all_spot_data()` and `get_stock_list()` by reading `total` and iterating pages until all data is retrieved.

## Scope
In-scope:
- Add paginated fetch logic in `app/services/data_provider/http_crawler_provider.py` for:
  - `get_all_spot_data()`
  - `get_stock_list()`

Out-of-scope:
- Changing provider priority (crawler remains first).
- Switching to AkShare/BaoStock as primary.
- Changing schema or downstream filters.

## Design Notes
- Use a fixed page size of 100 (observed API cap).
- Fetch page 1 to read `total` and `diff`.
- Loop pages 2..N (N = ceil(total / page_size)) and append results.
- If any page fails, log and continue; return aggregated results if non-empty.
- Preserve existing field mappings and filters.

## Risks
- Additional HTTP requests per sync; acceptable trade-off for correctness.

## Verification
- Manual: `get_all_spot_data()` should return ~5000+ rows (verify `raw rows` count).
- Manual: stock list count should be ~5000+.
