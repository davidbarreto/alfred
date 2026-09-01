"""One-off maintenance script: fix the sign of InstallmentPlan.original_amount for
plans created before the ActivoBank card PDF parser was fixed to store it negative
(see card_pdf_statement_parser.py::_parse_text, "Valor Transação" column).

original_amount is only ever populated from that parser (banco_inter/nubank always
pass None, and the portal never lets a user type one in -- see
InstallmentPlanCreate.original_amount) and represents an expense, which this
codebase always stores as negative. A stored positive value is therefore always a
plan caught by the bug, never a legitimate value -- there is no scenario where a
positive original_amount is correct.

Effect of the bug: a positive original_amount could never equal a real (negative)
Transaction.amount, so find_unmatched_transaction never matched the plan's
lump-sum purchase at import time (superseded path never ran), and the resulting
0.00 placeholder's transfer-match search substituted the wrong-signed amount,
so its transfer counterpart was never found either. Flipping the sign here fixes
both retroactively -- get_transfer_match_candidates re-reads the plan's
original_amount live, no other backfill needed.

Dry-run by default; pass --apply to commit.

Usage (from backend/, with the venv active):
    python scripts/fix_installment_plan_original_amount_sign.py
    python scripts/fix_installment_plan_original_amount_sign.py --apply
"""
import asyncio
import sys

from sqlalchemy import select

from app.db.session import async_session
from app.features.finance.installment_plans.tables import InstallmentPlan


async def main(apply: bool) -> None:
    async with async_session() as session:
        result = await session.execute(
            select(InstallmentPlan).where(InstallmentPlan.original_amount > 0)
        )
        plans = result.scalars().all()
        if not plans:
            print("No affected plans found.")
            return
        for plan in plans:
            old = plan.original_amount
            print(f"  plan_id={plan.id} description={plan.description!r} {old} -> {-old}")
            if apply:
                plan.original_amount = -old
        if apply:
            await session.commit()
            print(f"Updated {len(plans)} plan(s).")
        else:
            print(f"{len(plans)} plan(s) would be updated. Re-run with --apply to commit.")


if __name__ == "__main__":
    asyncio.run(main(apply="--apply" in sys.argv[1:]))
