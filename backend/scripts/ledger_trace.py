"""Read-only diagnostic: print one account's full transaction history in
chronological order with a running computed balance, so a divergence from the real
bank balance can be pinpointed to a specific transaction rather than reasoned about
in aggregate.

Running balance starts at opening_balance (0 if unset) and, for each transaction in
date order, applies the same signed-delta rule as the live app (see
TransactionService._account_delta / ImportService._sync_account_balance):
income credits; expense and transfer legs debit their own account; a transfer's
counterpart_account_id also credits this account when IT is the counterpart side
(counterpart_transaction_id NULL only -- see the recent double-counting fix) --
this script only traces one account at a time, so a counterpart-credit is shown
inline as a synthetic row when this account is the *destination* of an unconfirmed
guess from another account's transaction (not modeled here; run per source account
instead if that matters for the account being traced).

Makes no changes.

Usage (from backend/, with the venv active):
    python scripts/ledger_trace.py <account_id>
"""
import asyncio
import sys
from decimal import Decimal

from sqlalchemy import text

from app.db.session import async_session

_QUERY = text(
    """
    SELECT t.id, t.date, t.type, t.amount, t.currency, t.bank_description, t.description,
           t.counterpart_account_id, t.counterpart_transaction_id, t.installment_plan_id,
           t.balance_after, t.source
    FROM finance.transactions t
    WHERE t.account_id = :account_id
    ORDER BY t.date, t.id
    """
)

_ACCOUNT_QUERY = text(
    "SELECT name, opening_balance, opening_balance_date FROM finance.accounts WHERE id = :account_id"
)


async def main(account_id: int) -> None:
    async with async_session() as session:
        account = (await session.execute(_ACCOUNT_QUERY, {"account_id": account_id})).first()
        if account is None:
            print(f"No account with id={account_id}")
            return
        print(f"Account: {account.name!r} opening_balance={account.opening_balance} opening_balance_date={account.opening_balance_date}")

        running = account.opening_balance or Decimal("0")
        print(f"{'date':<12} {'id':>6} {'type':<10} {'amount':>12} {'running':>14}  description")
        print(f"{'':<12} {'':>6} {'':<10} {'':>12} {running:>14.2f}  (opening balance)")

        rows = (await session.execute(_QUERY, {"account_id": account_id})).all()
        for row in rows:
            delta = row.amount if row.type == "income" else -row.amount
            running += delta
            flags = []
            if row.counterpart_account_id is not None:
                flags.append(
                    f"counterpart={row.counterpart_account_id}"
                    + ("(confirmed)" if row.counterpart_transaction_id else "(guess)")
                )
            if row.installment_plan_id is not None:
                flags.append(f"plan={row.installment_plan_id}")
            if row.balance_after is not None:
                flags.append(f"stmt_balance_after={row.balance_after}")
            flag_str = f"  [{' '.join(flags)}]" if flags else ""
            desc = row.description or row.bank_description or ""
            print(
                f"{str(row.date.date()):<12} {row.id:>6} {row.type:<10} {row.amount:>12.2f} "
                f"{running:>14.2f}  {desc}{flag_str}"
            )
        print(f"\nFinal computed balance (own-leg only, no cross-account counterpart credits applied): {running:.2f}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/ledger_trace.py <account_id>")
        sys.exit(1)
    asyncio.run(main(int(sys.argv[1])))
