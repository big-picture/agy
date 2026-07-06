"""Invoice class and PDF processing functions for flow validation tests."""

from pathlib import Path
from typing import Any

import openpyxl
import pdfplumber
from openpyxl import Workbook


class Invoice:
    """Invoice object with PDF file path and extracted data."""

    def __init__(self, pdf_file: str):
        """Initialize Invoice with PDF file path.

        Args:
            pdf_file: Path to the PDF file
        """
        self.pdf_file = pdf_file
        self.invoice_number: str | None = None
        self.date: str | None = None
        self.amount: float | None = None
        self.vat: float | None = None
        self.party_name: str | None = None

    def update_data(self, invoice_data: dict[str, Any]) -> None:
        """Update invoice attributes from extracted data dictionary.

        Args:
            invoice_data: Dictionary with keys: invoice_number, date, amount, vat, party_name
        """
        self.invoice_number = invoice_data.get("invoice_number")
        self.date = invoice_data.get("date")
        self.amount = invoice_data.get("amount")
        self.vat = invoice_data.get("vat")
        self.party_name = invoice_data.get("party_name")

    def add_to_spreadsheet(self, spreadsheet_path: str) -> None:
        """Add invoice data as a row to Excel spreadsheet.

        Creates file and headers if not present.
        Adds row with: party_name | amount | vat | invoice_number | date

        Args:
            spreadsheet_path: Path to the Excel file
        """
        path = Path(spreadsheet_path)

        # Load or create workbook
        if path.exists():
            wb = openpyxl.load_workbook(path)
            ws = wb.active
        else:
            wb = Workbook()
            ws = wb.active
            # Add headers
            ws.append(
                [
                    "Name of invoicing party",
                    "Invoice amount",
                    "Value added tax",
                    "Invoice number",
                    "Date",
                ]
            )

        # Add invoice data row
        ws.append(
            [
                self.party_name or "",
                self.amount or 0.0,
                self.vat or 0.0,
                self.invoice_number or "",
                self.date or "",
            ]
        )

        # Save workbook
        path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(path)


def pdf2text(file_path: str) -> str:
    """Extract text content from PDF file.

    Args:
        file_path: Path to the PDF file

    Returns:
        Extracted text content as string
    """
    with pdfplumber.open(file_path) as pdf:
        text_parts = []
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        return "\n".join(text_parts)
