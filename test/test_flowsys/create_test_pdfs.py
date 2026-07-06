"""Create simple test PDF files for invoice processing flow tests."""

import sys
from pathlib import Path

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
except ImportError:
    print("ERROR: reportlab is not installed. Please install it:")
    print("  pip install reportlab")
    print("  or")
    print("  uv add reportlab")
    sys.exit(1)


def create_invoice_pdf(
    pdf_path: Path,
    invoice_number: str,
    date: str,
    party_name: str,
    amount: float,
    vat: float,
):
    """Create a simple invoice PDF."""
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    c.drawString(100, 750, f"Invoice Number: {invoice_number}")
    c.drawString(100, 730, f"Date: {date}")
    c.drawString(100, 710, f"Party Name: {party_name}")
    c.drawString(100, 690, f"Amount: {amount:.2f}")
    c.drawString(100, 670, f"VAT: {vat:.2f}")
    c.save()


def main():
    """Create 5 test invoice PDFs."""
    invoices_dir = Path("data/invoices")
    invoices_dir.mkdir(parents=True, exist_ok=True)

    # Test invoice data
    invoices = [
        ("INV-001", "2024-01-15", "Acme Corp", 1000.00, 190.00),
        ("INV-002", "2024-02-20", "Beta LLC", 2500.50, 475.10),
        ("INV-003", "2024-03-10", "Gamma Inc", 750.25, 142.55),
        ("INV-004", "2024-04-05", "Delta GmbH", 3200.00, 608.00),
        ("INV-005", "2024-05-12", "Epsilon Ltd", 1500.75, 285.14),
    ]

    for i, (invoice_number, date, party_name, amount, vat) in enumerate(invoices, 1):
        pdf_path = invoices_dir / f"invoice_{i:03d}.pdf"
        create_invoice_pdf(pdf_path, invoice_number, date, party_name, amount, vat)
        print(f"Created {pdf_path}")

    print(f"\n✓ Created {len(invoices)} invoice PDFs in {invoices_dir}")


if __name__ == "__main__":
    main()
