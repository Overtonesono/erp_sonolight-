from __future__ import annotations
from typing import Optional
from core.models.quote import Quote, PaymentRecord
from core.models.accounting import AccountingEntry
from core.services.quote_service import QuoteService
from core.services.invoice_service import InvoiceService
from core.services.accounting_service import AccountingService

class WorkflowService:
    def __init__(self):
        self.quotes = QuoteService()
        self.invoices = InvoiceService()
        self.acc = AccountingService()

    # Etape 2 : refus
    def refuse_quote(self, q: Quote) -> Quote:
        q.status = "REFUSED"
        q.decided_at = q.decided_at or q.created_at
        self.quotes.update_quote(q)
        return q

    # Etape 3 : acompte
    def record_deposit(self, q: Quote, amount_cent: int, method: Optional[str]) -> tuple[Quote, str]:
        # 1) enregistrer paiement sur le devis (master)
        pay = PaymentRecord(kind="ACOMPTE", amount_cent=amount_cent, method=method)
        q.payments.append(pay)
        q.status = "VALIDATED"
        self.quotes.update_quote(q)

        # 2) générer facture d'acompte (ISSUED) + PDF
        inv = self.invoices.gen_deposit(q, explicit_amount=amount_cent)
        pdf_path = self.invoices.export_invoice_pdf(inv)

        # 3) écriture comptable (encaissement acompte)
        self.acc.add_entry(AccountingEntry(
            type="ACOMPTE", amount_cent=amount_cent, payment_method=method,
            invoice_id=inv.id, label=f"Encaissement ACOMPTE {inv.number}"
        ))

        # 4) lier facture au paiement
        pay.invoice_id = inv.id
        self.quotes.update_quote(q)

        return q, pdf_path

    # Etape 4 : solde
    def record_balance(self, q: Quote, amount_cent: int, method: Optional[str]) -> tuple[Quote, str, str]:
        # 1) paiement solde
        pay = PaymentRecord(kind="SOLDE", amount_cent=amount_cent, method=method)
        q.payments.append(pay)
        self.quotes.update_quote(q)

        # 2) facture de solde + PDF
        inv_solde = self.invoices.gen_balance(q, explicit_amount=amount_cent)
        pdf_solde = self.invoices.export_invoice_pdf(inv_solde)

        # 3) écriture comptable
        self.acc.add_entry(AccountingEntry(
            type="SOLDE", amount_cent=amount_cent, payment_method=method,
            invoice_id=inv_solde.id, label=f"Encaissement SOLDE {inv_solde.number}"
        ))

        pay.invoice_id = inv_solde.id
        self.quotes.update_quote(q)

        # 4) si solde=0 → facture finale + status FINALIZED
        if q.remaining_cent() == 0:
            q.status = "FINALIZED"
            self.quotes.update_quote(q)
            inv_final = self.invoices.gen_final(q)
            pdf_final = self.invoices.export_invoice_pdf(inv_final)
            return q, pdf_solde, pdf_final

        return q, pdf_solde, ""
