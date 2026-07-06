# Classify Software Support Ticket

Classify the support ticket description into exactly one category:

- `invalid_request` = invalid, spam, duplicate, or wrong request (Fehlanfrage)
- `faq_resolvable` = can be answered directly from known FAQ/procedures
- `needs_specialist` = requires specialist/engineer handling

Return only one label from `invalid_request`, `faq_resolvable`, `needs_specialist`.
