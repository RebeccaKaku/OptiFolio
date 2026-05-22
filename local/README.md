# Local Private Workspace

This directory is the preferred home for private business state.

Keep real files here:

- `portfolio.yaml` copied from `config/portfolio.example.yaml`
- cash balances
- broker/account settings
- downloaded market data
- SQLite databases
- ad hoc exports

The directory is ignored by Git. Commit only templates such as
`config/portfolio.example.yaml` and `config/secrets.example.yaml`.

Portfolio loading order:

1. `OPTIFOLIO_PORTFOLIO_PATH`
2. `local/portfolio.yaml`
3. legacy `config/portfolio.yaml`

Bootstrap local runtime files:

```bash
python -m src.runtime.bootstrap
```
