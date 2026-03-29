from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


AccountState = Literal[
    "disconnected",
    "awaiting_code",
    "awaiting_2fa",
    "connected",
    "reauth_required",
    "disconnecting",
    "resetting",
    "error",
]

AuthWorkflowState = Literal["awaiting_code", "awaiting_2fa", "connected"]
AuthErrorCode = Literal[
    "AUTH_FLOW_EXPIRED",
    "AUTH_FLOW_NOT_FOUND",
    "INVALID_CODE",
    "INVALID_2FA",
]


class AuthWorkflowError(BaseModel):
    code: AuthErrorCode
    message: str
    retryable: bool
    user_action_required: bool
    recommended_action: str | None = None


class AccountProfile(BaseModel):
    display_name: str


class AuthStatusError(BaseModel):
    code: str
    message: str


_AUTH_WORKFLOW_ERRORS: dict[AuthErrorCode, AuthWorkflowError] = {
    "AUTH_FLOW_EXPIRED": AuthWorkflowError(
        code="AUTH_FLOW_EXPIRED",
        message="Your login session expired. Start again from step 1.",
        retryable=False,
        user_action_required=True,
        recommended_action="Restart onboarding from the first step.",
    ),
    "AUTH_FLOW_NOT_FOUND": AuthWorkflowError(
        code="AUTH_FLOW_NOT_FOUND",
        message="We couldn't find that login session. Start again from step 1.",
        retryable=False,
        user_action_required=True,
        recommended_action="Restart onboarding from the first step.",
    ),
    "INVALID_CODE": AuthWorkflowError(
        code="INVALID_CODE",
        message="That login code was not accepted. Enter the latest code and try again.",
        retryable=True,
        user_action_required=True,
        recommended_action="Enter the latest Telegram login code and submit again.",
    ),
    "INVALID_2FA": AuthWorkflowError(
        code="INVALID_2FA",
        message="That 2FA password was not accepted. Try again.",
        retryable=True,
        user_action_required=True,
        recommended_action="Enter your Telegram 2FA password again.",
    ),
}


def get_auth_workflow_error(code: AuthErrorCode) -> AuthWorkflowError:
    return _AUTH_WORKFLOW_ERRORS[code]


class AuthStartLoginRequest(BaseModel):
    api_id: str
    api_hash: str
    phone_number: str
    display_timezone: str


class AuthStartLoginResponse(BaseModel):
    auth_flow_id: str
    account_state: Literal["awaiting_code"]
    expires_at: datetime
    masked_phone_number: str


class AuthSubmitCodeRequest(BaseModel):
    auth_flow_id: str
    login_code: str


class AuthSubmitCodeResponse(BaseModel):
    account_state: Literal["connected", "awaiting_2fa"]
    account_profile: AccountProfile | None = None


class AuthSubmit2FARequest(BaseModel):
    auth_flow_id: str
    two_factor_password: str


class AuthSubmit2FAResponse(BaseModel):
    account_state: Literal["connected"]
    account_profile: AccountProfile | None = None


class AuthStatusResponse(BaseModel):
    account_state: AccountState
    account_profile: AccountProfile | None = None
    last_successful_auth_at: datetime | None = None
    last_auth_error: AuthStatusError | None = None
