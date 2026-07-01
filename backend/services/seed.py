from core.config import settings
from core.security import hash_password
from models import QuotaPlan, User, UserQuota
from models.quota import first_day_of_month
from models.team import Team, TeamMember
from sqlalchemy.orm import Session

UNLIMITED = -1
DEFAULT_IMAGE_LIMIT = 50
DEFAULT_VIDEO_LIMIT = 10

# 固定团队 ID，供 E2E 探针复现团队隔离
SEED_ADMIN_TEAM_ID = "a1000000-0000-4000-8000-000000000001"
SEED_TESTUSER2_TEAM_ID = "a2000000-0000-4000-8000-000000000002"


def _seed_password(env_value: str, env_name: str) -> str:
    value = (env_value or "").strip()
    if value:
        return value
    raise ValueError(
        f"种子数据需要设置 {env_name}（见 backend/.env.example），"
        "勿将默认密码写入源码"
    )


def seed_database(db: Session) -> None:
    if settings.is_production:
        return

    admin_pw = _seed_password(settings.seed_admin_password, "SEED_ADMIN_PASSWORD")
    test_pw = _seed_password(settings.seed_testuser_password, "SEED_TESTUSER_PASSWORD")
    test2_pw = _seed_password(settings.seed_testuser2_password, "SEED_TESTUSER2_PASSWORD")

    plans = [
        ("default", DEFAULT_IMAGE_LIMIT, DEFAULT_VIDEO_LIMIT),
        ("pro", 500, 100),
        ("unlimited", UNLIMITED, UNLIMITED),
    ]
    for name, image_limit, video_limit in plans:
        if not db.query(QuotaPlan).filter(QuotaPlan.name == name).first():
            db.add(
                QuotaPlan(
                    name=name,
                    image_limit=image_limit,
                    video_limit=video_limit,
                )
            )

    admin = _ensure_user(
        db,
        username="admin",
        email="admin@aistudio.local",
        password=admin_pw,
        role="admin",
        image_limit=UNLIMITED,
        video_limit=UNLIMITED,
        plan_name="unlimited",
    )
    _ensure_user(
        db,
        username="testuser",
        email="testuser@aistudio.local",
        password=test_pw,
        role="user",
        image_limit=DEFAULT_IMAGE_LIMIT,
        video_limit=DEFAULT_VIDEO_LIMIT,
        plan_name="default",
    )
    testuser2 = _ensure_user(
        db,
        username="testuser2",
        email="testuser2@aistudio.local",
        password=test2_pw,
        role="user",
        image_limit=DEFAULT_IMAGE_LIMIT,
        video_limit=DEFAULT_VIDEO_LIMIT,
        plan_name="default",
    )

    _ensure_team(db, SEED_ADMIN_TEAM_ID, "探针团队 A", admin)
    if testuser2:
        _ensure_team(db, SEED_TESTUSER2_TEAM_ID, "探针团队 B", testuser2)

    db.commit()


def _ensure_user(
    db: Session,
    username: str,
    email: str,
    password: str,
    role: str,
    image_limit: int,
    video_limit: int,
    plan_name: str,
) -> User | None:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(
            UserQuota(
                user_id=user.id,
                plan_name=plan_name,
                image_limit=image_limit,
                video_limit=video_limit,
                image_used=0,
                video_used=0,
                period_start=first_day_of_month(),
            )
        )
    else:
        if user.role != role:
            user.role = role
        quota = db.query(UserQuota).filter(UserQuota.user_id == user.id).first()
        if quota:
            quota.image_limit = image_limit
            quota.video_limit = video_limit
            quota.plan_name = plan_name
    return user


def _ensure_team(db: Session, team_id: str, name: str, owner: User) -> Team:
    team = db.query(Team).filter(Team.owner_id == owner.id).first()
    if not team:
        team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        team = Team(id=team_id, name=name, owner_id=owner.id)
        db.add(team)
        db.flush()
        db.add(TeamMember(team_id=team.id, user_id=owner.id, role="owner"))
    else:
        if team.name != name:
            team.name = name
        member = (
            db.query(TeamMember)
            .filter(TeamMember.team_id == team.id, TeamMember.user_id == owner.id)
            .first()
        )
        if not member:
            db.add(TeamMember(team_id=team.id, user_id=owner.id, role="owner"))
    return team
