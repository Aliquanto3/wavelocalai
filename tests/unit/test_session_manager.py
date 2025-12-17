# tests/unit/test_session_manager.py
"""
Tests unitaires pour SessionManager.
"""

import time

import pytest

from src.core.session.session_manager import (
    Session,
    SessionManager,
    get_session_manager,
)


class TestSession:
    """Tests de la classe Session."""

    def test_session_get_set(self):
        """Test get/set de données."""
        from datetime import datetime

        session = Session(
            id="test-id",
            user_id="user-1",
            created_at=datetime.now(),
            last_activity=datetime.now(),
        )

        session.set("key1", "value1")
        assert session.get("key1") == "value1"
        assert session.get("nonexistent", "default") == "default"

    def test_session_delete(self):
        """Test suppression de données."""
        from datetime import datetime

        session = Session(
            id="test-id",
            user_id="user-1",
            created_at=datetime.now(),
            last_activity=datetime.now(),
        )

        session.set("key1", "value1")
        assert session.delete("key1") is True
        assert session.get("key1") is None
        assert session.delete("nonexistent") is False

    def test_session_clear(self):
        """Test vidage de session."""
        from datetime import datetime

        session = Session(
            id="test-id",
            user_id="user-1",
            created_at=datetime.now(),
            last_activity=datetime.now(),
        )

        session.set("key1", "value1")
        session.set("key2", "value2")
        session.clear()

        assert session.get("key1") is None
        assert session.get("key2") is None


class TestSessionManager:
    """Tests du SessionManager."""

    def setup_method(self):
        """Crée un nouveau manager pour chaque test."""
        self.manager = SessionManager(
            session_timeout_minutes=1,
            max_sessions=10,
        )

    def test_create_session(self):
        """Test création de session."""
        session = self.manager.create_session(user_id="user-1")

        assert session is not None
        assert session.id is not None
        assert session.user_id == "user-1"

    def test_get_session(self):
        """Test récupération de session."""
        created = self.manager.create_session(user_id="user-1")
        retrieved = self.manager.get_session(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id

    def test_get_session_not_found(self):
        """Test récupération session inexistante."""
        result = self.manager.get_session("nonexistent-id")
        assert result is None

    def test_get_or_create_session_existing(self):
        """Test get_or_create avec session existante."""
        created = self.manager.create_session(user_id="user-1")
        retrieved = self.manager.get_or_create_session(session_id=created.id)

        assert retrieved.id == created.id

    def test_get_or_create_session_new(self):
        """Test get_or_create crée une nouvelle session."""
        session = self.manager.get_or_create_session(
            session_id="nonexistent",
            user_id="user-1",
        )

        assert session is not None
        assert session.id != "nonexistent"

    def test_get_user_sessions(self):
        """Test récupération des sessions d'un utilisateur."""
        self.manager.create_session(user_id="user-1")
        self.manager.create_session(user_id="user-1")
        self.manager.create_session(user_id="user-2")

        user1_sessions = self.manager.get_user_sessions("user-1")
        user2_sessions = self.manager.get_user_sessions("user-2")

        assert len(user1_sessions) == 2
        assert len(user2_sessions) == 1

    def test_delete_session(self):
        """Test suppression de session."""
        session = self.manager.create_session(user_id="user-1")

        assert self.manager.delete_session(session.id) is True
        assert self.manager.get_session(session.id) is None

    def test_delete_user_sessions(self):
        """Test suppression de toutes les sessions d'un utilisateur."""
        self.manager.create_session(user_id="user-1")
        self.manager.create_session(user_id="user-1")
        self.manager.create_session(user_id="user-2")

        deleted = self.manager.delete_user_sessions("user-1")

        assert deleted == 2
        assert len(self.manager.get_user_sessions("user-1")) == 0
        assert len(self.manager.get_user_sessions("user-2")) == 1

    def test_max_sessions_limit(self):
        """Test limite du nombre de sessions."""
        # Créer le maximum de sessions
        for i in range(10):
            self.manager.create_session(user_id=f"user-{i}")

        # La 11ème devrait échouer
        with pytest.raises(RuntimeError, match="maximum"):
            self.manager.create_session(user_id="user-overflow")

    def test_get_stats(self):
        """Test statistiques du manager."""
        self.manager.create_session(user_id="user-1")
        self.manager.create_session(user_id="user-1")
        self.manager.create_session(user_id="user-2")

        stats = self.manager.get_stats()

        assert stats["total_sessions"] == 3
        assert stats["unique_users"] == 2
        assert stats["max_sessions"] == 10


class TestSessionManagerSingleton:
    """Tests du singleton."""

    def test_singleton_returns_same_instance(self):
        """Test que get_session_manager retourne la même instance."""
        manager1 = get_session_manager()
        manager2 = get_session_manager()
        assert manager1 is manager2
