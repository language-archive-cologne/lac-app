from django import template

from lacos.storage.utils.acl_display import format_agent_uri_for_display

register = template.Library()


@register.filter
def acl_agent_display(uri):
    """Display an ACL agent URI in human-readable short form."""
    return format_agent_uri_for_display(uri)
