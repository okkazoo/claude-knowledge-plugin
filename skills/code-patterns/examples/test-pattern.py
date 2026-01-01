# Test Pattern: Standard pytest structure
# Use for: All tests, follow Arrange/Act/Assert pattern

import pytest
from unittest.mock import Mock, patch

from app.services import UserService
from app.models import User


class TestUserService:
    """Tests for UserService."""

    @pytest.fixture
    def user_service(self):
        """Create a UserService instance for testing."""
        return UserService()

    @pytest.fixture
    def sample_user(self):
        """Create a sample user for testing."""
        return User(
            id=1,
            email="test@example.com",
            name="Test User"
        )

    # ==================== GET USER ====================

    def test_get_user_returns_user_when_exists(self, user_service, sample_user):
        """Should return user when user exists."""
        # Arrange
        user_service.repository = Mock()
        user_service.repository.find_by_id.return_value = sample_user

        # Act
        result = user_service.get_user(1)

        # Assert
        assert result == sample_user
        user_service.repository.find_by_id.assert_called_once_with(1)

    def test_get_user_returns_none_when_not_exists(self, user_service):
        """Should return None when user doesn't exist."""
        # Arrange
        user_service.repository = Mock()
        user_service.repository.find_by_id.return_value = None

        # Act
        result = user_service.get_user(999)

        # Assert
        assert result is None

    # ==================== CREATE USER ====================

    def test_create_user_saves_and_returns_user(self, user_service):
        """Should save user and return it."""
        # Arrange
        user_data = {"email": "new@example.com", "name": "New User"}
        user_service.repository = Mock()
        user_service.repository.save.return_value = User(id=1, **user_data)

        # Act
        result = user_service.create_user(user_data)

        # Assert
        assert result.email == "new@example.com"
        assert result.id == 1

    def test_create_user_raises_on_duplicate_email(self, user_service):
        """Should raise error when email already exists."""
        # Arrange
        user_service.repository = Mock()
        user_service.repository.find_by_email.return_value = User(id=1, email="exists@example.com")

        # Act & Assert
        with pytest.raises(ValueError, match="Email already exists"):
            user_service.create_user({"email": "exists@example.com"})

    # ==================== EXTERNAL SERVICES ====================

    @patch('app.services.user_service.send_email')
    def test_create_user_sends_welcome_email(self, mock_send_email, user_service):
        """Should send welcome email after user creation."""
        # Arrange
        user_service.repository = Mock()
        user_service.repository.save.return_value = User(id=1, email="test@example.com")

        # Act
        user_service.create_user({"email": "test@example.com"})

        # Assert
        mock_send_email.assert_called_once_with(
            to="test@example.com",
            template="welcome"
        )
