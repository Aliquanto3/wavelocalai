# src/core/session/session_manager.py
"""
Gestionnaire de sessions pour le multi-tenant.
Isole les données et l'état entre les utilisateurs.
"""

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """Session utilisateur."""

    id: str
    user_id: str | None
    created_at: datetime
    last_activity: datetime
    data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, timeout_minutes: int = 60) -> bool:
        """Vérifie si la session a expiré."""
        expiry_time = self.last_activity + timedelta(minutes=timeout_minutes)
        return datetime.now() > expiry_time

    def touch(self) -> None:
        """Met à jour le timestamp de dernière activité."""
        self.last_activity = datetime.now()

    def get(self, key: str, default: Any = None) -> Any:
        """Récupère une valeur de la session."""
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Définit une valeur dans la session."""
        self.data[key] = value
        self.touch()

    def delete(self, key: str) -> bool:
        """Supprime une valeur de la session."""
        if key in self.data:
            del self.data[key]
            self.touch()
            return True
        return False

    def clear(self) -> None:
        """Vide toutes les données de la session."""
        self.data.clear()
        self.touch()


class SessionManager:
    """
    Gestionnaire centralisé des sessions.

    Fonctionnalités :
    - Création et gestion des sessions
    - Isolation des données par utilisateur
    - Expiration automatique
    - Thread-safe
    """

    def __init__(
        self,
        session_timeout_minutes: int = 60,
        max_sessions: int = 1000,
        cleanup_interval_minutes: int = 15,
    ):
        """
        Initialise le gestionnaire de sessions.

        Args:
            session_timeout_minutes: Durée d'inactivité avant expiration
            max_sessions: Nombre maximum de sessions simultanées
            cleanup_interval_minutes: Intervalle de nettoyage automatique
        """
        self._sessions: dict[str, Session] = {}
        self._user_sessions: dict[str, set[str]] = {}  # user_id -> session_ids
        self._lock = threading.RLock()
        self._timeout_minutes = session_timeout_minutes
        self._max_sessions = max_sessions
        self._cleanup_interval = cleanup_interval_minutes
        self._last_cleanup = datetime.now()

    def create_session(
        self,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Session:
        """
        Crée une nouvelle session.

        Args:
            user_id: Identifiant utilisateur optionnel
            metadata: Métadonnées de la session

        Returns:
            Nouvelle session créée
        """
        with self._lock:
            # Nettoyage périodique
            self._maybe_cleanup()

            # Vérifier la limite de sessions
            if len(self._sessions) >= self._max_sessions:
                self._cleanup_expired()
                if len(self._sessions) >= self._max_sessions:
                    raise RuntimeError(f"Nombre maximum de sessions atteint ({self._max_sessions})")

            session_id = str(uuid.uuid4())
            now = datetime.now()

            session = Session(
                id=session_id,
                user_id=user_id,
                created_at=now,
                last_activity=now,
                data={},
                metadata=metadata or {},
            )

            self._sessions[session_id] = session

            # Indexer par user_id si fourni
            if user_id:
                if user_id not in self._user_sessions:
                    self._user_sessions[user_id] = set()
                self._user_sessions[user_id].add(session_id)

            logger.debug(f"Session created: {session_id} for user {user_id}")
            return session

    def get_session(self, session_id: str) -> Session | None:
        """
        Récupère une session par son ID.

        Args:
            session_id: ID de la session

        Returns:
            Session ou None si non trouvée/expirée
        """
        with self._lock:
            session = self._sessions.get(session_id)

            if session is None:
                return None

            if session.is_expired(self._timeout_minutes):
                self._remove_session(session_id)
                return None

            session.touch()
            return session

    def get_or_create_session(
        self,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> Session:
        """
        Récupère une session existante ou en crée une nouvelle.

        Args:
            session_id: ID de session existante (optionnel)
            user_id: ID utilisateur pour la nouvelle session

        Returns:
            Session existante ou nouvelle
        """
        if session_id:
            session = self.get_session(session_id)
            if session:
                return session

        return self.create_session(user_id=user_id)

    def get_user_sessions(self, user_id: str) -> list[Session]:
        """
        Récupère toutes les sessions d'un utilisateur.

        Args:
            user_id: ID de l'utilisateur

        Returns:
            Liste des sessions actives
        """
        with self._lock:
            session_ids = self._user_sessions.get(user_id, set()).copy()
            sessions = []

            for session_id in session_ids:
                session = self.get_session(session_id)
                if session:
                    sessions.append(session)

            return sessions

    def delete_session(self, session_id: str) -> bool:
        """
        Supprime une session.

        Args:
            session_id: ID de la session

        Returns:
            True si supprimée, False si non trouvée
        """
        with self._lock:
            return self._remove_session(session_id)

    def delete_user_sessions(self, user_id: str) -> int:
        """
        Supprime toutes les sessions d'un utilisateur.

        Args:
            user_id: ID de l'utilisateur

        Returns:
            Nombre de sessions supprimées
        """
        with self._lock:
            session_ids = self._user_sessions.get(user_id, set()).copy()
            count = 0

            for session_id in session_ids:
                if self._remove_session(session_id):
                    count += 1

            return count

    def _remove_session(self, session_id: str) -> bool:
        """Supprime une session (interne, sans lock)."""
        session = self._sessions.pop(session_id, None)

        if session:
            if session.user_id and session.user_id in self._user_sessions:
                self._user_sessions[session.user_id].discard(session_id)
                if not self._user_sessions[session.user_id]:
                    del self._user_sessions[session.user_id]

            logger.debug(f"Session removed: {session_id}")
            return True

        return False

    def _cleanup_expired(self) -> int:
        """Nettoie les sessions expirées (interne, sans lock)."""
        expired_ids = [
            sid
            for sid, session in self._sessions.items()
            if session.is_expired(self._timeout_minutes)
        ]

        for session_id in expired_ids:
            self._remove_session(session_id)

        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired sessions")

        return len(expired_ids)

    def _maybe_cleanup(self) -> None:
        """Effectue un nettoyage si l'intervalle est dépassé."""
        now = datetime.now()
        if now - self._last_cleanup > timedelta(minutes=self._cleanup_interval):
            self._cleanup_expired()
            self._last_cleanup = now

    def get_stats(self) -> dict[str, Any]:
        """Retourne les statistiques du gestionnaire."""
        with self._lock:
            active_sessions = sum(
                1 for s in self._sessions.values() if not s.is_expired(self._timeout_minutes)
            )

            return {
                "total_sessions": len(self._sessions),
                "active_sessions": active_sessions,
                "unique_users": len(self._user_sessions),
                "max_sessions": self._max_sessions,
                "timeout_minutes": self._timeout_minutes,
            }


# Instance singleton
_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    """Retourne l'instance singleton du gestionnaire de sessions."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
