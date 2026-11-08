"""Администрирование из командной строки: пользователи и токены.

Пока нет входа через IdP, это единственный способ выпустить токен.
Запуск: `python -m atomic_tasks <команда>`,
в Docker — `docker compose exec api python -m atomic_tasks ...`.
"""

import argparse
from uuid import UUID

from dishka import AsyncContainer

from atomic_tasks.application.dto import TokenInfo, UserInfo
from atomic_tasks.application.errors import ApplicationError
from atomic_tasks.application.services.token_service import TokenService
from atomic_tasks.application.services.user_service import UserService
from atomic_tasks.domain.entities.api_token import DEFAULT_TTL_DAYS, TokenScope
from atomic_tasks.domain.exceptions import DomainError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m atomic_tasks")
    groups = parser.add_subparsers(dest="group", required=True)

    users = groups.add_parser("users", help="пользователи").add_subparsers(
        dest="cmd", required=True
    )
    create = users.add_parser("create", help="создать пользователя")
    create.add_argument("--name", required=True)
    create.add_argument("--email")
    users.add_parser("list", help="список пользователей")
    for cmd in ("disable", "enable"):
        users.add_parser(cmd).add_argument("user_id", type=UUID)

    tokens = groups.add_parser("tokens", help="personal access tokens").add_subparsers(
        dest="cmd",
        required=True,
    )
    t_create = tokens.add_parser("create", help="выпустить токен")
    t_create.add_argument("--user", type=UUID, required=True)
    t_create.add_argument("--name", required=True)
    t_create.add_argument("--scope", choices=[s.value for s in TokenScope], default="write")
    ttl = t_create.add_mutually_exclusive_group()
    ttl.add_argument("--days", type=int, default=DEFAULT_TTL_DAYS)
    ttl.add_argument("--no-expiry", action="store_true", help="бессрочный токен")
    tokens.add_parser("list", help="токены пользователя").add_argument(
        "--user",
        type=UUID,
        required=True,
    )
    t_revoke = tokens.add_parser("revoke", help="отозвать токен")
    t_revoke.add_argument("--user", type=UUID, required=True)
    t_revoke.add_argument("token_id", type=UUID)
    return parser


async def run(container: AsyncContainer, argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    try:
        async with container() as request_container:
            if args.group == "users":
                await _users(args, await request_container.get(UserService))
            else:
                await _tokens(args, await request_container.get(TokenService))
    except (DomainError, ApplicationError) as exc:
        print(f"Ошибка: {exc.message}")
        return 1
    return 0


async def _users(args: argparse.Namespace, users: UserService) -> None:
    if args.cmd == "create":
        _print_user(await users.create(display_name=args.name, email=args.email))
    elif args.cmd == "list":
        for user in await users.list_all():
            _print_user(user)
    else:
        _print_user(await users.set_disabled(args.user_id, disabled=args.cmd == "disable"))


async def _tokens(args: argparse.Namespace, tokens: TokenService) -> None:
    if args.cmd == "create":
        created = await tokens.create(
            user_id=args.user,
            name=args.name,
            scope=TokenScope(args.scope),
            ttl_days=None if args.no_expiry else args.days,
        )
        _print_token(created.info)
        print(f"\n{created.token}\n\nТокен показывается один раз — сохраните его сейчас.")
    elif args.cmd == "list":
        for info in await tokens.list_for_user(args.user):
            _print_token(info)
    else:
        await tokens.revoke(user_id=args.user, token_id=args.token_id)
        print("Токен отозван.")


def _print_user(user: UserInfo) -> None:
    status = "отключён" if user.disabled else "активен"
    print(f"{user.id}  {user.display_name}  {user.email or '-'}  {status}")


def _print_token(info: TokenInfo) -> None:
    expires = info.expires_at.date().isoformat() if info.expires_at else "бессрочно"
    state = "отозван" if info.revoked_at else f"до {expires}"
    used = (
        info.last_used_at.isoformat(timespec="minutes") if info.last_used_at else "не использовался"
    )
    print(f"{info.id}  at_{info.prefix}_…  {info.name}  {info.scope}  {state}  {used}")
