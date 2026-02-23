import ast
import re
from django import template
from django.utils.html import conditional_escape, mark_safe
from django.utils.safestring import SafeString
from django.template.defaultfilters import stringfilter

from lacos.explorer.identifier_display import format_identifier_html
from lacos.explorer.media_utils import (
    determine_media_type,
    is_annotation_file as media_utils_is_annotation_file,
    is_media_type as media_utils_is_media_type,
)

register = template.Library()

FACET_PARAM_NAMES = {
    "keyword", "language", "year", "country", "region", "provider", "access", "license",
    "topic", "collection",
}


@register.simple_tag(takes_context=True)
def facet_toggle_url(context, facet_name, value):
    """Toggle a facet value on/off in the current URL. Resets page param."""
    request = context["request"]
    params = request.GET.copy()

    current = params.getlist(facet_name)
    if value in current:
        current.remove(value)
    else:
        current.append(value)

    params.setlist(facet_name, current)
    params.pop("page", None)

    return f"?{params.urlencode()}" if params else "?"


@register.simple_tag(takes_context=True)
def facet_remove_url(context, facet_name, value):
    """Remove a specific facet value from the current URL. Resets page param."""
    request = context["request"]
    params = request.GET.copy()

    current = params.getlist(facet_name)
    if value in current:
        current.remove(value)
    params.setlist(facet_name, current)
    params.pop("page", None)

    return f"?{params.urlencode()}" if params else "?"


@register.simple_tag(takes_context=True)
def clear_all_filters_url(context):
    """Remove all facet params and q, keep sort/order only."""
    request = context["request"]
    params = request.GET.copy()

    for key in list(params.keys()):
        if key in FACET_PARAM_NAMES or key in ("q", "page"):
            del params[key]

    return f"?{params.urlencode()}" if params else "?"


@register.simple_tag(takes_context=True)
def facet_sort_url(context, sort_field):
    """Build sort URL preserving all facet/search params. Toggles order."""
    request = context["request"]
    params = request.GET.copy()

    current_sort = params.get("sort", "name")
    current_order = params.get("order", "asc")

    if current_sort == sort_field:
        new_order = "desc" if current_order == "asc" else "asc"
    else:
        new_order = "asc"

    params["sort"] = sort_field
    params["order"] = new_order
    params.pop("page", None)

    return f"?{params.urlencode()}"

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


@register.filter
def media_type(resource):
    """
    Return a normalized media type string for the supplied resource.
    """
    if not resource:
        return ""

    detected = determine_media_type(
        getattr(resource, "mime_type", None),
        getattr(resource, "file_name", None),
    )
    return detected or ""


@register.filter
def creator_identifier_display(creator):
    """Return formatted HTML for a creator's name identifier."""
    return mark_safe(
        format_identifier_html(
            getattr(creator, "name_identifier", None),
            getattr(creator, "name_identifier_type", None),
        )
    )


@register.filter
def is_media_type(resource, target_type: str) -> bool:
    """
    Convenience filter to check whether a resource matches a specific media type.
    """
    if not resource or not target_type:
        return False

    return media_utils_is_media_type(
        getattr(resource, "mime_type", None),
        getattr(resource, "file_name", None),
        target_type,
    )


@register.filter
def is_annotation(resource) -> bool:
    """Return True when the resource is an ELAN annotation file (.eaf/.elan)."""
    if not resource:
        return False
    return media_utils_is_annotation_file(
        getattr(resource, "mime_type", None),
        getattr(resource, "file_name", None),
    )


@register.filter
def file_extension(resource):
    """Return the uppercased file extension from a resource's file_name (e.g. 'WAV')."""
    file_name = getattr(resource, "file_name", None) or ""
    if "." in file_name:
        return file_name.rsplit(".", 1)[-1].upper()
    return ""


@register.filter
@stringfilter
def render_search_snippet(text):
    """Render search snippets while allowing only <mark> tags."""
    if not text:
        return ""

    escaped = conditional_escape(text)
    rendered = escaped.replace("&lt;mark&gt;", "<mark>").replace("&lt;/mark&gt;", "</mark>")
    return mark_safe(rendered)


@register.filter
def split_csv(value):
    """Split a comma-separated string into trimmed values."""
    if not value:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


@register.filter
def normalize_role(value):
    """Normalize role values that may be stored as list-like strings."""
    if not value:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item).strip() for item in value if str(item).strip())

    text = str(value).strip()
    if not text:
        return ""

    try:
        parsed = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return text

    if isinstance(parsed, (list, tuple)):
        return ", ".join(str(item).strip() for item in parsed if str(item).strip())
    return str(parsed).strip()


@register.filter
def highlight_query(text, query):
    """Highlight literal query matches in plain text, escaping other HTML."""
    text = text or ""
    query = (query or "").strip()
    escaped = conditional_escape(text)
    if not query:
        return mark_safe(escaped)

    pattern = re.compile(re.escape(query), flags=re.IGNORECASE)
    rendered = pattern.sub(lambda match: f"<mark>{match.group(0)}</mark>", str(escaped))
    return mark_safe(rendered)


def _tokenize_query(query: str) -> list[str]:
    return [token.lower() for token in query.split() if token.strip()]


def _text_matches_query(text: str, tokens: list[str]) -> bool:
    if not text or not tokens:
        return False
    lowered = text.lower()
    words = re.findall(r"\w+", lowered)
    return any(token in lowered or any(word.startswith(token) for word in words) for token in tokens)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


@register.filter
def collection_match_reasons(collection, query):
    """Infer matched collection fields for advanced search display."""
    tokens = _tokenize_query((query or "").strip())
    if not tokens:
        return ""

    reasons: list[str] = []
    if _text_matches_query(getattr(collection, "identifier", ""), tokens):
        reasons.append("identifier")

    gi = getattr(collection, "get_general_info", None)
    if gi:
        if _text_matches_query(getattr(gi, "display_title", ""), tokens):
            reasons.append("title")
        if _text_matches_query(getattr(gi, "description", ""), tokens):
            reasons.append("description")
        location = getattr(gi, "location", None)
        if location:
            if _text_matches_query(getattr(location, "location_name", ""), tokens):
                reasons.append("location")
            if (
                _text_matches_query(getattr(location, "country_name", ""), tokens)
                or _text_matches_query(getattr(location, "country_facet", ""), tokens)
            ):
                reasons.append("country")
        object_languages = getattr(gi, "object_languages", None)
        if object_languages and any(
            _text_matches_query(getattr(lang, "name", ""), tokens)
            or _text_matches_query(getattr(lang, "display_name", ""), tokens)
            for lang in object_languages.all()
        ):
            reasons.append("language")

    pub = getattr(collection, "get_publication_info", None)
    if pub:
        if _text_matches_query(getattr(pub, "data_provider", ""), tokens):
            reasons.append("data provider")
        if any(
            _text_matches_query(getattr(creator, "family_name", ""), tokens)
            or _text_matches_query(getattr(creator, "given_name", ""), tokens)
            for creator in pub.creators.all()
        ):
            reasons.append("creator")
        if any(
            _text_matches_query(getattr(contributor, "family_name", ""), tokens)
            or _text_matches_query(getattr(contributor, "given_name", ""), tokens)
            or _text_matches_query(getattr(contributor, "contributor_display_name", ""), tokens)
            or _text_matches_query(getattr(contributor, "role", ""), tokens)
            for contributor in pub.contributors.all()
        ):
            reasons.append("contributor")

    return ", ".join(_dedupe(reasons) or ["metadata"])


@register.filter
def bundle_match_reasons(bundle, query):
    """Infer matched bundle fields for advanced search display."""
    tokens = _tokenize_query((query or "").strip())
    if not tokens:
        return ""

    reasons: list[str] = []
    if _text_matches_query(getattr(bundle, "identifier", ""), tokens):
        reasons.append("identifier")

    gi = getattr(bundle, "get_general_info", None)
    if gi:
        if _text_matches_query(getattr(gi, "display_title", ""), tokens):
            reasons.append("title")
        if _text_matches_query(getattr(gi, "description", ""), tokens):
            reasons.append("description")
        location = getattr(gi, "location", None)
        if location:
            if (
                _text_matches_query(getattr(location, "country_name", ""), tokens)
                or _text_matches_query(getattr(location, "country_facet", ""), tokens)
            ):
                reasons.append("country")
        object_languages = getattr(gi, "object_languages", None)
        if object_languages and any(
            _text_matches_query(getattr(lang, "name", ""), tokens)
            or _text_matches_query(getattr(lang, "display_name", ""), tokens)
            for lang in object_languages.all()
        ):
            reasons.append("language")

    si = getattr(bundle, "get_structural_info", None)
    if si and getattr(si, "is_member_of_collection", None):
        parent = si.is_member_of_collection
        if _text_matches_query(getattr(parent, "identifier", ""), tokens):
            reasons.append("parent collection identifier")
        parent_gi = getattr(parent, "get_general_info", None)
        if parent_gi and _text_matches_query(getattr(parent_gi, "display_title", ""), tokens):
            reasons.append("parent collection title")

    pub = getattr(bundle, "get_publication_info", None)
    if pub:
        if _text_matches_query(getattr(pub, "data_provider", ""), tokens):
            reasons.append("data provider")
        if any(
            _text_matches_query(getattr(creator, "family_name", ""), tokens)
            or _text_matches_query(getattr(creator, "given_name", ""), tokens)
            for creator in pub.creators.all()
        ):
            reasons.append("creator")
        if any(
            _text_matches_query(getattr(contributor, "family_name", ""), tokens)
            or _text_matches_query(getattr(contributor, "given_name", ""), tokens)
            or _text_matches_query(getattr(contributor, "role", ""), tokens)
            or (
                getattr(contributor, "contributor_name", None)
                and (
                    _text_matches_query(
                        getattr(contributor.contributor_name, "contributor_family_name", ""),
                        tokens,
                    )
                    or _text_matches_query(
                        getattr(contributor.contributor_name, "contributor_given_name", ""),
                        tokens,
                    )
                )
            )
            for contributor in pub.contributors.all()
        ):
            reasons.append("contributor")

    return ", ".join(_dedupe(reasons) or ["metadata"])
