# Local Private Workspace

This directory is the preferred home for private business state.

Keep real files here:

- `portfolio_book.sqlite` for accounts, products, snapshot batches, positions, and cash
- broker/account settings
- downloaded market data
- SQLite databases
- ad hoc exports

The directory is ignored by Git. Commit only templates that do not contain holdings or private account state, such as `config/secrets.example.yaml`.

Portfolio holdings are loaded from the latest confirmed batch in `local/portfolio_book.sqlite`. Portfolio YAML files are no longer supported.

Bootstrap local runtime files:

```bash
python -m src.runtime.bootstrap
```
