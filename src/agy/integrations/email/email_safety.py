"""Email safety and validation utilities."""

from __future__ import annotations

import logging
import os
import re

from dotenv import load_dotenv

from .env_config import ProviderKey, get_safety_config

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class EmailSafetyValidator:
    """Validates email addresses for safety before sending emails."""

    def __init__(
        self,
        allowed_domains: list[str] | None = None,
        allowed_addresses: list[str] | None = None,
        *,
        provider: ProviderKey | None = None,
    ):
        """
        Initialize EmailSafetyValidator.

        Args:
            allowed_domains: List of allowed email domains (e.g., ["big-picture.com"])
            allowed_addresses: List of specific allowed email addresses.
            provider: When set, load allowlists from {PROVIDER}_ALLOWED_EMAIL_* env.
        """
        if allowed_domains is None and allowed_addresses is None and provider is not None:
            config = get_safety_config(provider)
            allowed_domains = config["allowed_domains"]
            allowed_addresses = config["allowed_addresses"]
        elif allowed_domains is None:
            env_domains = os.getenv("ALLOWED_EMAIL_DOMAINS", "big-picture.com")
            allowed_domains = [d.strip() for d in env_domains.split(",") if d.strip()]

        if allowed_addresses is None and provider is None:
            env_addresses = os.getenv("ALLOWED_EMAIL_ADDRESSES", "")
            allowed_addresses = [
                a.strip() for a in env_addresses.split(",") if a.strip()
            ]
        elif allowed_addresses is None and provider is not None:
            allowed_addresses = []

        self.allowed_domains = [domain.lower() for domain in (allowed_domains or [])]
        self.allowed_addresses = [
            address.lower() for address in (allowed_addresses or [])
        ]
        self.provider = provider

        logger.info(
            "EmailSafetyValidator initialized (%s) with %s allowed domains and %s allowed addresses",
            provider or "global",
            len(self.allowed_domains),
            len(self.allowed_addresses),
        )
        if self.allowed_domains:
            logger.info("Allowed domains: %s", ", ".join(self.allowed_domains))
        if self.allowed_addresses:
            logger.info("Allowed addresses: %s", ", ".join(self.allowed_addresses))

    @staticmethod
    def extract_domain(email_address: str) -> str | None:
        """Extract domain from email address."""
        if not email_address:
            return None

        email_address = email_address.strip()
        if "<" in email_address and ">" in email_address:
            match = re.search(r"<([^>]+)>", email_address)
            if match:
                email_address = match.group(1)

        if "@" in email_address:
            return email_address.split("@")[-1].lower().strip()
        return None

    def is_allowed_domain(self, domain: str) -> bool:
        """Check if domain is in the allowed list."""
        if not domain:
            return False
        return domain.lower().strip() in self.allowed_domains

    def is_allowed_address(self, email_address: str) -> bool:
        """Check if specific email address is in the allowed list."""
        if not email_address:
            return False
        return email_address.lower().strip() in self.allowed_addresses

    def validate_recipient(
        self, email_address: str, operation: str = "send"
    ) -> tuple[bool, str]:
        """Validate that an email address is allowed for sending operations."""
        if not email_address:
            return False, "Email address is empty"

        if self.is_allowed_address(email_address):
            logger.info(
                "Email address %s is explicitly allowed for %s",
                email_address,
                operation,
            )
            return True, ""

        domain = self.extract_domain(email_address)
        if not domain:
            return False, f"Invalid email address format: {email_address}"

        if self.is_allowed_domain(domain):
            logger.info("Email domain %s is allowed for %s", domain, operation)
            return True, ""

        error_msg = (
            f"Email address {email_address} (domain: {domain}) is not allowed. "
            f"Allowed domains: {', '.join(self.allowed_domains)}. "
            f"Allowed addresses: {', '.join(self.allowed_addresses) if self.allowed_addresses else 'none'}"
        )
        logger.warning("SAFETY CHECK FAILED for %s: %s", operation, error_msg)
        return False, error_msg

    def validate_reply(self, original_from_address: str) -> tuple[bool, str]:
        """Validate that replying to an email is safe."""
        return self.validate_recipient(original_from_address, operation="reply")

    def validate_forward(self, forward_to_address: str) -> tuple[bool, str]:
        """Validate that forwarding an email is safe."""
        return self.validate_recipient(forward_to_address, operation="forward")


_global_validator: EmailSafetyValidator | None = None
_provider_validators: dict[ProviderKey, EmailSafetyValidator] = {}


def get_validator(provider: ProviderKey | None = None) -> EmailSafetyValidator:
    """Get or create an EmailSafetyValidator for a provider (or legacy global)."""
    global _global_validator
    if provider is None:
        if _global_validator is None:
            _global_validator = EmailSafetyValidator()
        return _global_validator

    if provider not in _provider_validators:
        _provider_validators[provider] = EmailSafetyValidator(provider=provider)
    return _provider_validators[provider]


def reset_validator(provider: ProviderKey | None = None) -> None:
    """Reset cached validator(s) (useful for testing)."""
    global _global_validator
    if provider is None:
        _global_validator = None
        _provider_validators.clear()
        return
    _provider_validators.pop(provider, None)
