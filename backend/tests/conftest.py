import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import MagicMock

# Create a clean sqlite in-memory database for testing
from app.main import app
from app.dependencies import get_db, get_current_user, get_current_active_user
from app.models.user import User as UserModel
from app.models.document import Document as DocumentModel

# Mock out external services at the module import level to prevent connection attempts
import sys
from unittest.mock import Mock

# Setup patches for database engines and clients
mock_redis_pkg = Mock()
mock_redis_client = MagicMock()
mock_redis_client.get.return_value = None
mock_redis_pkg.Redis.from_url.return_value = mock_redis_client
sys.modules["redis"] = mock_redis_pkg

sys.modules["qdrant_client"] = Mock()
sys.modules["neo4j"] = Mock()


@pytest.fixture(scope="session", autouse=True)
def mock_external_clients():
    """Mock database and external API clients globally for all tests."""
    import app.retrieval.semantic_search as search_mod

    search_mod.client = MagicMock()

    import app.db.neo4j_client as neo_mod

    neo_mod.driver = MagicMock()

    # Mock LLM provider factory
    import app.llm.providers.factory as factory_mod

    mock_provider = MagicMock()
    mock_provider.llm.invoke = MagicMock(return_value=MagicMock(content="[]"))
    factory_mod.get_llm_provider = MagicMock(return_value=mock_provider)

    yield


@pytest.fixture(scope="function")
def db_engine():
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    import app.dependencies as deps_mod
    import app.api.routes.chat as chat_mod
    import app.api.routes.document as doc_mod
    import app.api.routes.auth as auth_mod

    testing_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    deps_mod.SessionLocal = testing_SessionLocal
    chat_mod.SessionLocal = testing_SessionLocal
    doc_mod.SessionLocal = testing_SessionLocal
    auth_mod.SessionLocal = testing_SessionLocal

    from app.models.user import Base
    import app.models.user
    import app.models.document
    import app.models.conversation
    import app.models.message
    import app.models.chunk
    import app.models.processing_job

    Base.metadata.create_all(bind=engine)
    yield engine


@pytest.fixture(scope="function")
def db_session(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def test_user(db_session):
    # Create a test user in sqlite
    user = UserModel(
        email="test@example.com",
        full_name="Test User",
        hashed_password="fakehash",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def client(db_session, test_user):
    # Override get_db
    def override_get_db():
        yield db_session

    # Override get_current_user
    def override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_active_user] = override_get_current_user

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_active_user, None)


@pytest.fixture
def auth_headers():
    from app.core.security import create_access_token

    token = create_access_token({"sub": "test@example.com", "user_id": 1})
    return {"Authorization": f"Bearer {token}"}
