"""
Global functions for travel insurance claim processing.

These functions are used in the email routing flow for validating
and submitting travel cancellation insurance claims.
"""

import random
from typing import Any


def validate_claim(claim_data: dict[str, Any]) -> dict[str, Any]:
    """
    Validate if a claim has all mandatory fields.

    Args:
        claim_data: Dictionary with extracted claim data

    Returns:
        Dictionary with:
            - is_complete (bool): True if all mandatory fields present
            - missing_fields (list[str]): List of missing mandatory field names

    Mandatory fields:
        - policy_number
        - full_name
        - email
        - travel_date
        - cancellation_date
        - cancellation_reason
        - amount_claimed
    """
    mandatory_fields = [
        "policy_number",
        "full_name",
        "email",
        "travel_date",
        "cancellation_date",
        "cancellation_reason",
        "amount_claimed",
    ]

    missing_fields = []

    for field in mandatory_fields:
        value = claim_data.get(field)

        if value is None or value == "":
            missing_fields.append(field)
        elif field == "amount_claimed":
            try:
                amount = float(value)
                if amount <= 0:
                    missing_fields.append(field)
            except (ValueError, TypeError):
                missing_fields.append(field)

    return {"is_complete": len(missing_fields) == 0, "missing_fields": missing_fields}


def submit_claim(claim_data: dict[str, Any]) -> str:
    """
    Submit a claim to the mock insurance system.

    This is a mock function that simulates submitting a claim to an API.
    In a real system, this would make an HTTP request to a claims processing API.

    Args:
        claim_data: Dictionary with validated claim data

    Returns:
        Confirmation message with claim reference number
    """
    year = 2024
    sequence = random.randint(100000, 999999)
    claim_ref = f"CLM-{year}-{sequence}"

    policy_number = claim_data.get("policy_number", "Unknown")
    amount = claim_data.get("amount_claimed", 0)

    confirmation = (
        f"Claim submitted successfully!\n\n"
        f"Reference Number: {claim_ref}\n"
        f"Policy Number: {policy_number}\n"
        f"Amount Claimed: ${amount}\n\n"
        f"Our claims team will review your submission within 5 business days. "
        f"You will receive an email update on the status of your claim.\n\n"
        f"If you have any questions, please reference your claim number {claim_ref} "
        f"when contacting us."
    )

    return confirmation
