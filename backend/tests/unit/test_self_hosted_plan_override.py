"""SELF_HOSTED_PLAN pins entitlement reads without rewriting stored billing state."""

import pytest

import database.users as users_db
import utils.subscription as subscription_utils
from models.users import PlanType, SubscriptionStatus

STORED_BASIC = {
    'plan': 'basic',
    'status': 'active',
    'stripe_subscription_id': 'sub_real_123',
    'current_price_id': 'price_real_123',
}


class _Snapshot:
    exists = True
    id = 'user-1'

    def to_dict(self):
        return {'subscription': dict(STORED_BASIC)}


class _Database:
    """Minimal Firestore stand-in returning one stored basic subscription."""

    def __init__(self):
        self.writes = []

    def collection(self, *_args):
        return self

    def document(self, *_args):
        return self

    def get(self, *_args, **_kwargs):
        return _Snapshot()

    def set(self, payload, **_kwargs):
        self.writes.append(payload)


@pytest.fixture
def stub_db(monkeypatch):
    database = _Database()
    monkeypatch.setattr(users_db, 'db', database)
    return database


def _set_plan(monkeypatch, value):
    monkeypatch.setattr(subscription_utils, 'SELF_HOSTED_PLAN', value)


def test_unset_leaves_the_stored_plan_alone(stub_db, monkeypatch):
    _set_plan(monkeypatch, '')

    subscription = users_db.get_user_subscription('user-1')

    assert subscription.plan == PlanType.basic
    assert subscription.current_period_end is None


def test_override_pins_the_plan_for_entitlement_reads(stub_db, monkeypatch):
    _set_plan(monkeypatch, 'architect')

    subscription = users_db.get_user_subscription('user-1')

    assert subscription.plan == PlanType.architect
    assert subscription.status == SubscriptionStatus.active
    assert subscription.limits == subscription_utils.get_plan_limits(PlanType.architect)
    # A paid plan whose period has lapsed is demoted back to Free by the validity
    # check, so the pinned plan must survive get_user_valid_subscription().
    assert users_db.get_user_valid_subscription('user-1').plan == PlanType.architect


def test_override_preserves_stripe_identity(stub_db, monkeypatch):
    _set_plan(monkeypatch, 'operator')

    subscription = users_db.get_user_subscription('user-1')

    # Account deletion reads these off the entitlement subscription to cancel a
    # real Stripe subscription; the override must not blank them.
    assert subscription.stripe_subscription_id == 'sub_real_123'
    assert subscription.current_price_id == 'price_real_123'


def test_override_never_rewrites_stored_billing_state(stub_db, monkeypatch):
    _set_plan(monkeypatch, 'architect')

    users_db.get_user_subscription('user-1')

    assert stub_db.writes == []
    # The Stripe webhook and sync fair-use read this path — it stays on stored truth.
    assert users_db.get_existing_user_subscription('user-1').plan == PlanType.basic


def test_invalid_plan_value_is_ignored(stub_db, monkeypatch):
    _set_plan(monkeypatch, 'platinum')

    assert subscription_utils.get_self_hosted_plan_override() is None
    assert users_db.get_user_subscription('user-1').plan == PlanType.basic
