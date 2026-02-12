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

    if admin_info.access_level == 'public':
        return True

    if not user.is_authenticated:
        return False

    if admin_info.access_level == 'academic':
        return True

    if admin_info.access_level == 'restricted':
        return admin_info.authorized_users.filter(id=user.id).exists()

    return False