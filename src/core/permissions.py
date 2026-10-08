from src.core.security import verify_password
from src.database.models import User
from src.models.exceptions import ForbiddenError, ValidationError
from src.schemas.users import ADMIN_ONLY_USER_FIELDS, UserUpdatePatch


def ensure_active(user: User) -> None:
    if not user.is_active:
        raise ForbiddenError("Аккаунт деактивирован")


def ensure_admin(user: User) -> None:
    if not user.is_admin:
        raise ForbiddenError("Недостаточно прав")


def ensure_self_or_admin(user: User, target_user_id: int) -> None:
    if not user.is_admin and user.id != target_user_id:
        raise ForbiddenError("Недостаточно прав")


def ensure_owner(user: User, owner_id: int) -> None:
    if user.id != owner_id:
        raise ForbiddenError("Недостаточно прав")


def ensure_can_update_user(user: User, target_user_id: int, update: UserUpdatePatch) -> None:
    ensure_self_or_admin(user, target_user_id)

    restricted = ADMIN_ONLY_USER_FIELDS & update.model_fields_set
    if restricted and not user.is_admin:
        raise ForbiddenError(f"Только администратор может менять поля: {', '.join(sorted(restricted))}")

    if update.password is not None and user.id == target_user_id:
        if update.current_password is None or not verify_password(update.current_password, user.hashed_password):
            raise ValidationError("Неверный текущий пароль")


def order_owner_filter(user: User) -> int | None:
    return None if user.is_admin else user.id
