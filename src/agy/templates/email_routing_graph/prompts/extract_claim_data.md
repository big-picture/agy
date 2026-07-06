# Extract Travel Cancellation Claim Data

You are extracting structured data from a travel cancellation insurance claim
email.

## Task

Extract the following fields from the customer's email. If a field is not
mentioned or cannot be determined, return `null` for that field.

## Fields to Extract

### Mandatory Fields

1. **policy_number** (string): The insurance policy number (e.g., "TC123456",
   "POL-2024-789")
2. **full_name** (string): Customer's full name (first and last name)
3. **email** (string): Customer's email address
4. **travel_date** (string): Originally planned travel/departure date (any
   format is acceptable)
5. **cancellation_date** (string): Date when the trip was canceled (any format)
6. **cancellation_reason** (string): Reason for cancellation (e.g., "illness",
   "family emergency", "job loss")
7. **amount_claimed** (float): Dollar amount being claimed (e.g., 1500.00,
   2350.50)

### Optional Fields

1. **phone** (string): Customer's phone number (if provided)
2. **booking_reference** (string): Airline/hotel booking reference number
3. **destination** (string): Destination of the canceled trip
4. **travel_provider** (string): Airline, hotel, or tour operator name

## Extraction Guidelines

- **Be flexible with formats**: Dates can be in any format (MM/DD/YYYY,
  DD-MM-YYYY, "June 15, 2024", etc.)
- **Extract from context**: If information is implied but not explicitly stated,
  use reasonable inference
- **Handle variations**: Policy numbers may have different prefixes or formats
- **Currency**: For amounts, extract only the number (strip $, commas, etc. and
  return as float)
- **Null for missing**: If a field is truly not mentioned or cannot be inferred,
  return `null`
- **Full names**: Combine first and last name into a single string
- **Cancellation reason**: Summarize in a few words (don't copy entire
  paragraphs)

## Examples

**Example Email:** "Hi, I need to file a claim. My policy number is
TC-2024-123456. I'm John Smith (<john.smith@email.com>). I had to cancel my trip
to Paris on March 15th due to a serious illness. The trip was supposed to start
on April 1st. I'm claiming $2,450 which was my total booking cost with Air
France (booking ref: AF78901)."

*Expected Output:*

```json
{
  "policy_number": "TC-2024-123456",
  "full_name": "John Smith",
  "email": "john.smith@email.com",
  "phone": null,
  "travel_date": "April 1st",
  "cancellation_date": "March 15th",
  "cancellation_reason": "serious illness",
  "amount_claimed": 2450.0,
  "booking_reference": "AF78901",
  "destination": "Paris",
  "travel_provider": "Air France"
}
```

**Example with Missing Fields:** "Policy TC999. I'm Mary Johnson. Had to cancel
my trip. Claiming $800."

*Expected Output:*

```json
{
  "policy_number": "TC999",
  "full_name": "Mary Johnson",
  "email": null,
  "phone": null,
  "travel_date": null,
  "cancellation_date": null,
  "cancellation_reason": null,
  "amount_claimed": 800.0,
  "booking_reference": null,
  "destination": null,
  "travel_provider": null
}
```

## Output Format

Return ONLY a valid JSON object with all 11 fields. Use `null` for missing
values.
