# EDP fork — divergences from upstream

This fork tracks `BasedHardware/omi`. Every intentional difference from upstream is
listed here so it can be re-applied or dropped deliberately during a rebase.

```
origin    https://github.com/andrewbowlds/omi     (this fork)
upstream  https://github.com/BasedHardware/omi
```

Rebase loop: `git fetch upstream && git rebase upstream/main`, then push to `origin`
and bump the submodule pointer in the parent `edpapp` repo.

---

## 1. `SELF_HOSTED_PLAN` — entitlement override

**Why:** upstream gates transcription, chat, and desktop access on a Stripe-backed
subscription. A self-hosted instance has no Stripe account, so every user resolves
to Free and the paid-tier limits are unreachable.

**What:** setting the `SELF_HOSTED_PLAN` env var to a plan id pins every user to
that plan.

| Value | Effect |
|---|---|
| _(empty, the default)_ | No change — normal Stripe-backed behavior |
| `basic` | Free tier limits |
| `plus` / `unlimited_v2` | Mobile tiers |
| `operator` / `architect` | Full desktop access; `architect` has the highest chat budget |

**Files touched:**

- `backend/utils/subscription.py` — `SELF_HOSTED_PLAN`, `SELF_HOSTED_PERIOD_END`,
  `get_self_hosted_plan_override()`, `apply_self_hosted_plan_override()`, added
  directly after `get_default_basic_subscription()`
- `backend/database/users.py` — `get_user_subscription()` passes both of its return
  values through `apply_self_hosted_plan_override()`; import on the `utils.subscription` line
- `backend/.env.template` — documents the var next to the `STRIPE_*` block
- `backend/tests/unit/test_self_hosted_plan_override.py` — new, fork-only

**Boundaries the override deliberately respects:**

- Only `get_user_subscription()` (the *entitlement* read) is overridden. Every gate —
  `has_transcription_credits`, `get_remaining_transcription_seconds`,
  `get_chat_quota_snapshot`, `plan_grants_desktop` — funnels through it via
  `get_user_valid_subscription()`, so one override point covers all of them.
- `get_existing_user_subscription()` (the *billing-state* read consumed by the Stripe
  webhook and sync fair-use) is **not** overridden and still returns stored truth.
- No Firestore write. The stored subscription record stays `basic`; turning the env
  var off restores original behavior with no backfill.
- `stripe_subscription_id` / `current_price_id` are preserved on the overridden object
  so account deletion still cancels a real Stripe subscription if one exists.
- `current_period_end` is pinned to 2100-01-01 because `get_user_valid_subscription()`
  demotes a paid plan with a lapsed or missing period end back to Free.

**Rebase risk:** low. Both edits are additive and localized; the only conflict-prone
spot is the `from utils.subscription import ...` line in `backend/database/users.py`.
