from __future__ import annotations
import os, json
from typing import List
from pydantic import ValidationError
from core.models.accounting import AccountingEntry
from core.storage.repo import JsonRepository

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data"))
ACCOUNTING_JSON = os.path.join(DATA_DIR, "accounting_entries.json")

class AccountingService:
    def __init__(self, path: str = ACCOUNTING_JSON):
        self.repo = JsonRepository(path, key="id")

    def add_entry(self, e: AccountingEntry) -> AccountingEntry:
        self.repo.add(e.model_dump())
        return e

    def list_entries(self) -> List[AccountingEntry]:
        out: List[AccountingEntry] = []
        for d in self.repo.list_all():
            try:
                out.append(AccountingEntry(**d))
            except ValidationError:
                continue
        return out
