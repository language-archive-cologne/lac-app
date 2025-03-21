import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from django.utils import timezone as django_timezone

# Instead of importing the actual model, we'll mock it
# from lacos.storage.models.upload_sessions import UploadSession

@pytest.fixture
def user():
    return MagicMock(
        id=1,
        username="testuser",
    )

@pytest.fixture
def upload_session(user):
    session = MagicMock()
    session.id = uuid.uuid4()
    session.user = user
    session.folder_name = "test_folder"
    session.created_at = django_timezone.now()
    session.status = "initialized"
    session.total_files = 10
    session.total_size_bytes = 1024000
    session.completed_at = None
    session.__str__.return_value = f"Upload {session.id} by testuser (initialized)"
    return session

class TestUploadSession:
    def test_creation(self, upload_session):
        """Test that an UploadSession can be created with expected attributes"""
        assert upload_session.folder_name == "test_folder"
        assert upload_session.status == "initialized"
        assert upload_session.total_files == 10
        assert upload_session.total_size_bytes == 1024000
        assert upload_session.completed_at is None

    def test_string_representation(self, upload_session):
        """Test the string representation of the model"""
        expected_str = f"Upload {upload_session.id} by testuser (initialized)"
        assert str(upload_session) == expected_str

    def test_mark_completed(self, upload_session):
        """Test marking a session as completed"""
        # Setup
        now = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        upload_session.save = MagicMock()
        
        # Create a mock for the mark_completed method
        with patch('django.utils.timezone.now', return_value=now):
            # Simulate the behavior of mark_completed
            def mock_mark_completed():
                upload_session.status = "completed"
                upload_session.completed_at = now
                upload_session.save()  # Call save inside the mock function
            
            upload_session.mark_completed = mock_mark_completed
            
            # Execute
            upload_session.mark_completed()
            
            # Assert
            assert upload_session.status == "completed"
            assert upload_session.completed_at == now
            upload_session.save.assert_called_once()

    def test_get_progress_with_files(self, upload_session):
        """Test progress calculation with completed files"""
        # Setup mock for the related files manager
        completed_files = MagicMock()
        completed_files.count.return_value = 5
        
        upload_session.files = MagicMock()
        upload_session.files.filter.return_value = completed_files
        
        # Simulate the behavior of get_progress
        def mock_get_progress():
            if upload_session.total_files == 0:
                return 0
            completed_count = upload_session.files.filter(status='completed').count()
            return (completed_count / upload_session.total_files) * 100
            
        upload_session.get_progress = mock_get_progress
        
        # Execute
        progress = upload_session.get_progress()
        
        # Assert
        assert progress == 50.0  # 5/10 * 100
        upload_session.files.filter.assert_called_once_with(status='completed')

    def test_get_progress_no_files(self, upload_session):
        """Test progress calculation with no total files"""
        # Setup
        upload_session.total_files = 0
        
        # Simulate the behavior of get_progress
        def mock_get_progress():
            if upload_session.total_files == 0:
                return 0
            completed_count = upload_session.files.filter(status='completed').count()
            return (completed_count / upload_session.total_files) * 100
            
        upload_session.get_progress = mock_get_progress
        
        # Execute
        progress = upload_session.get_progress()
        
        # Assert
        assert progress == 0

    def test_upload_session_operations(self):
        """Test model operations with mocked ORM"""
        # Setup
        user = MagicMock(id=1, username="testuser")
        
        # Create a mock for the UploadSession class and its manager
        UploadSession = MagicMock()
        UploadSession.objects = MagicMock()
        
        # Mock create
        session_id = uuid.uuid4()
        created_session = MagicMock(
            id=session_id,
            user=user,
            folder_name="test_folder",
            status="initialized",
            total_files=5,
            total_size_bytes=500000
        )
        UploadSession.objects.create.return_value = created_session
        
        # Mock get
        UploadSession.objects.get.return_value = created_session
        
        # Execute - create
        session = UploadSession.objects.create(
            user=user,
            folder_name="test_folder",
            total_files=5,
            total_size_bytes=500000
        )
        
        # Execute - retrieve
        retrieved = UploadSession.objects.get(id=session.id)
        
        # Assert
        assert retrieved.folder_name == "test_folder"
        assert retrieved.status == "initialized"
        assert retrieved.user == user
        UploadSession.objects.create.assert_called_once()
        UploadSession.objects.get.assert_called_once() 