def check_resource_access(user, resource):
    """
    Check if a user has access to a resource based on its access level.
    
    Args:
        user: The Django user object
        resource: Any model instance with an administrative_info attribute
        
    Returns:
        bool: True if the user has access, False otherwise
    """
    admin_info = resource.administrative_info
    
    # Check if resource is under embargo
    if admin_info.access_level == 'embargo':
        # Maybe allow superusers or staff to bypass embargo
        return user.is_superuser or user.is_staff
    
    # Check if resource is public
    if admin_info.access_level == 'public':
        return True
    
    # For protected and private, user must be authenticated
    if not user.is_authenticated:
        return False
    
    # All authenticated users can access protected resources
    if admin_info.access_level == 'protected':
        return True
    
    # For private resources, check if user is in authorized_users
    if admin_info.access_level == 'private':
        return admin_info.authorized_users.filter(id=user.id).exists()
    
    # Default deny
    return False