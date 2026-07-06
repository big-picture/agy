"""Main entry point for validating and executing invoice processing flows."""

import asyncio
import sys
from pathlib import Path

from objects.invoice import Invoice, pdf2text

from agy import Flow, FlowExecutor
from agy.action_type import ActionType


async def main():
    """Validate and execute invoice processing flow."""
    # Get flow file from CLI argument
    flow_file = sys.argv[1] if len(sys.argv) > 1 else "invoice_valid.flowsy"

    # Register custom actions (used for validation and execution)
    action_types = [
        ActionType(
            object_name="global_function",
            method_name="pdf2text",
            callable=pdf2text,
            description="Extract text from PDF file",
        )
    ]

    # Validate the flow
    # Create a dummy invoice for validation
    dummy_invoice = Invoice(pdf_file="data/invoices/invoice_001.pdf")
    validation_result = Flow.validate(
        flow_file,
        context_in={"invoice": dummy_invoice},
        action_types=action_types,
    )

    if not validation_result.is_valid:
        print(f"\n⚠️  Validation failed: {len(validation_result.errors)} error(s)")
        for error in validation_result.errors:
            location_str = f" ({error.location})" if error.location else ""
            # Error message already contains line number and line content if available
            print(f"  - {error.message}{location_str}")
        if validation_result.warnings:
            print(f"\n⚠️  {len(validation_result.warnings)} warning(s):")
            for warning in validation_result.warnings:
                location_str = f" ({warning.location})" if warning.location else ""
                # Warning message already contains line number and line content if available
                print(f"  - {warning.message}{location_str}")
        return

    print("✓ Validation passed")

    # Execute (only if valid)
    flow = Flow.from_flowsy(flow_file)
    invoices_dir = Path("data/invoices")
    pdf_files = sorted(invoices_dir.glob("*.pdf"))

    if not pdf_files:
        print("No PDF files found in data/invoices/")
        return

    print(f"\nFound {len(pdf_files)} invoice(s) to process")

    # Process each invoice
    for pdf_path in pdf_files:
        invoice = Invoice(pdf_file=str(pdf_path))
        executor = FlowExecutor(
            context_in={"invoice": invoice},
            action_types=action_types,
        )
        await executor.execute(flow)
        print(f"✓ Processed {pdf_path.name}")

    print(f"\n{'=' * 60}")
    print("All invoices processed!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
