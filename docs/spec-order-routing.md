# Change request: route order and shipping questions correctly

## Problem
Requests asking where an order is, or whether it has shipped, are classified as `other` and sent
to human review, even though the knowledge base has articles that answer them. In the August
batch, REQ-1014, REQ-1017, REQ-1019, and REQ-1021 are all order-tracking questions routed to
`other`. Two return requests that mention delivery (REQ-1023, REQ-1028) are classified as
`orders_shipping` instead of `returns_refunds`.

## Requirements
1. Requests about order status, tracking, shipping progress, or a package that has not arrived
   are classified as `orders_shipping`.
2. When a request matches both `returns_refunds` and `orders_shipping`, `returns_refunds` wins.
   A customer returning a shipped order is asking about the return.
3. Existing routing for billing, account access, returns, and product issues is unchanged.
4. Requests that match no category still go to `other` and human review.

## Acceptance examples
- "Order 48311 was placed nine days ago and the tracking number still shows label created" → `orders_shipping`
- "My order has said processing for five days. Has it shipped?" → `orders_shipping`
- "Tracking shows my package has been sitting at a carrier hub" → `orders_shipping`
- "I sent back my order and the carrier shows it delivered to you, but no refund has appeared" → `returns_refunds`
- "I was charged twice for one order" → `billing` (unchanged)
- "Can I add gift wrapping to a purchase?" → `other` (unchanged)

## Non-goals
- No change to how drafts are written or to escalation rules.
- No new dependencies, no rewrite of the routing approach. Keyword rules stay.
- The bare word "order" is not a shipping signal; it appears in billing and return requests too.
