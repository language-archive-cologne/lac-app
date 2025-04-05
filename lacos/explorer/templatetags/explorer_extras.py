import re
from django import template
from django.utils.html import mark_safe
from django.utils.safestring import SafeString
from django.template.defaultfilters import stringfilter

register = template.Library()

@register.filter
@stringfilter
def urlize_text(text):
    """
    Convert plain text URLs and DOIs in the text to clickable links.
    """
    if not text:
        return ""
    
    # If text is already marked safe, don't process it again
    if isinstance(text, SafeString):
        return text
    
    # Define patterns
    doi_pattern = r'https?://doi.org/10\.\d{4,}/[a-zA-Z0-9./-]+|doi:10\.\d{4,}/[a-zA-Z0-9./-]+|10\.\d{4,}/[a-zA-Z0-9./-]+'
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
    
    # Combined pattern to find all URLs and DOIs
    pattern = f'({doi_pattern}|{url_pattern})'
    
    # Process all matches
    def replace_match(match):
        url = match.group(0)
        
        # Handle DOIs
        if url.startswith('10.'):
            full_url = f'https://doi.org/{url}'
        elif url.startswith('doi:'):
            full_url = f'https://doi.org/{url[4:]}'
        # Handle URLs without protocol
        elif url.startswith('www.'):
            full_url = f'https://{url}'
        else:
            full_url = url
            
        return f'<a href="{full_url}" target="_blank" class="text-blue-600 hover:underline">{url}</a>'
    
    # Use a single regex operation to find and replace all URLs
    result = re.sub(pattern, replace_match, text, flags=re.IGNORECASE)
    
    return mark_safe(result) 