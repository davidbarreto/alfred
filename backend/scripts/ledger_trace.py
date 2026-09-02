"""Read-only diagnostic: print one account's full transaction history in
chronological order with a running computed balance, so a divergence from the real
bank balance can be pinpointed to a specific transaction rather than reasoned about
in aggregate.

Running balance starts at opening_balance (0 if unset) and, for each transaction in
date order, applies the same signed-delta rule as the live app (see
TransactionService._account_delta): expense debits (stored as an unsigned
magnitude); income and transfer both already store their real signed delta
directly (positive = arrived/credited, negative = left/debited this account), so
they're added as-is. Only ever touches this account -- counterpart_account_id is
pure linking metadata, never a second account's balance mutation (see
TransactionService.create's note); the counterpart's own balance always comes
from its own transaction row, so run this script against that account directly
to see its side.

Rows dated before opening_balance_date are marked [pre-opening] but still
included in the running total below, unlike backfill_account_balances.py's
delta-sum fallback (which excludes them, since opening_balance already reflects
that history) -- this script shows the full ledger for inspection; check the
[pre-opening] flag rather than assuming this running total matches the backfill
script's result.

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
            delta = -row.amount if row.type == "expense" else row.amount
            running += delta
            flags = []
            if account.opening_balance_date is not None and row.date.date() < account.opening_balance_date:
                flags.append("pre-opening")
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
