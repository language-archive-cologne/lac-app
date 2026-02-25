"""Parse IMDI XML files into a lightweight tree of ``ImdiNode`` objects."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from dataclasses import field
from pathlib import PurePosixPath

from lxml import etree

logger = logging.getLogger(__name__)

NS = "{http://www.mpi.nl/IMDI/Schema/IMDI}"
SEPARATOR = " | "
TRANSPARENT_CONTAINERS = {"MDGroup", "Actors", "Resources"}
ROOT_ELEMENT_NAMES = ("Session", "Corpus", "Catalogue")


@dataclass
class ImdiNode:
    """A single node in the IMDI metadata tree."""

    node_type: str
    label: str
    metadata: dict[str, str] = field(default_factory=dict)
    children: list[ImdiNode] = field(default_factory=list)
    corpus_link: str | None = None
    resolved_key: str | None = None


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _element_children(el: etree._Element) -> list[etree._Element]:
    return [child for child in el if isinstance(child.tag, str)]


def _is_leaf(el: etree._Element) -> bool:
    return not _element_children(el)


def _text(el: etree._Element, tag: str) -> str:
    """Return text content of a direct child element, or empty string."""
    child = el.find(f"{NS}{tag}")
    return _leaf_text(child) if child is not None else ""


def _leaf_text(el: etree._Element) -> str:
    if not _is_leaf(el):
        return ""
    return (el.text or "").strip()


def _add_metadata(metadata: dict[str, str], key: str, value: str) -> None:
    clean_value = value.strip()
    if not clean_value:
        return

    existing = metadata.get(key)
    if not existing:
        metadata[key] = clean_value
        return

    parts = existing.split(SEPARATOR)
    if clean_value not in parts:
        metadata[key] = f"{existing}{SEPARATOR}{clean_value}"


def _copy_attributes(el: etree._Element, metadata: dict[str, str]) -> None:
    for attr_name, attr_value in el.attrib.items():
        local_name = _local_name(attr_name)
        _add_metadata(metadata, f"@{local_name}", attr_value)


def _flatten_contact(el: etree._Element, metadata: dict[str, str]) -> bool:
    if _local_name(el.tag) != "Contact":
        return False

    flattened = False
    for child in _element_children(el):
        child_name = _local_name(child.tag)
        child_text = _leaf_text(child)
        if child_text:
            key = "Contact" if child_name == "Name" else f"Contact {child_name}"
            _add_metadata(metadata, key, child_text)
            flattened = True
    return flattened


def _flatten_communication_context(
    el: etree._Element,
    metadata: dict[str, str],
) -> bool:
    if _local_name(el.tag) != "CommunicationContext":
        return False

    flattened = False
    for child in _element_children(el):
        child_text = _leaf_text(child)
        if child_text:
            _add_metadata(metadata, _local_name(child.tag), child_text)
            flattened = True
    return flattened


def _flatten_languages(el: etree._Element, metadata: dict[str, str]) -> bool:
    if _local_name(el.tag) != "Languages":
        return False

    language_names = []
    for language_el in _element_children(el):
        if _local_name(language_el.tag) != "Language":
            continue

        language_name = _text(language_el, "Name")
        if language_name:
            language_names.append(language_name)

    if not language_names:
        return False

    _add_metadata(metadata, "Languages", ", ".join(language_names))
    return True


def _flatten_special_container(el: etree._Element, metadata: dict[str, str]) -> bool:
    return (
        _flatten_contact(el, metadata)
        or _flatten_communication_context(el, metadata)
        or _flatten_languages(el, metadata)
    )


def _should_be_metadata_entry(el: etree._Element) -> bool:
    if _local_name(el.tag) == "CorpusLink":
        return False
    return _is_leaf(el) and not el.attrib


def _default_label(node_type: str) -> str:
    defaults = {
        "Session": "Unnamed Session",
        "Corpus": "Unnamed Corpus",
        "Catalogue": "Unnamed Catalogue",
        "Actor": "Unknown Actor",
    }
    return defaults.get(node_type, node_type)


def _determine_label(
    node_type: str,
    metadata: dict[str, str],
    el: etree._Element,
) -> str:
    if node_type == "CorpusLink":
        name_attr = (el.get("Name") or "").strip()
        if name_attr:
            return name_attr
        path_value = (_leaf_text(el) or metadata.get("Path") or "").strip()
        if path_value:
            return PurePosixPath(path_value).name or path_value
        return "CorpusLink"

    for key in ("Name", "Title", "ResourceLink", "Id", "Code", "Type"):
        candidate = metadata.get(key)
        if candidate:
            return candidate

    own_value = _leaf_text(el)
    if own_value:
        return own_value

    return _default_label(node_type)


def _parse_container_children(container: etree._Element) -> list[ImdiNode]:
    nodes: list[ImdiNode] = []
    for child in _element_children(container):
        child_name = _local_name(child.tag)
        if child_name in TRANSPARENT_CONTAINERS:
            nodes.extend(_parse_container_children(child))
            continue
        nodes.append(_parse_element(child))
    return nodes


def _parse_element(el: etree._Element) -> ImdiNode:
    node_type = _local_name(el.tag)
    metadata: dict[str, str] = {}
    _copy_attributes(el, metadata)

    children: list[ImdiNode] = []

    for child in _element_children(el):
        if _flatten_special_container(child, metadata):
            continue

        child_name = _local_name(child.tag)
        if _should_be_metadata_entry(child):
            _add_metadata(metadata, child_name, _leaf_text(child))
            continue

        if child_name in TRANSPARENT_CONTAINERS:
            children.extend(_parse_container_children(child))
            continue

        children.append(_parse_element(child))

    own_text = _leaf_text(el)
    if own_text and "Value" not in metadata and node_type != "CorpusLink":
        _add_metadata(metadata, "Value", own_text)

    corpus_link = None
    if node_type == "CorpusLink":
        corpus_link = own_text
        if corpus_link:
            _add_metadata(metadata, "Path", corpus_link)

    return ImdiNode(
        node_type=node_type,
        label=_determine_label(node_type, metadata, el),
        metadata=metadata,
        children=children,
        corpus_link=corpus_link,
    )


def _select_root_element(tree: etree._Element) -> etree._Element | None:
    type_map = {
        "SESSION": "Session",
        "CORPUS": "Corpus",
        "CATALOGUE": "Catalogue",
    }

    metatranscript_type = (tree.get("Type") or "").upper()
    preferred = type_map.get(metatranscript_type)
    if preferred:
        preferred_element = tree.find(f"{NS}{preferred}")
        if preferred_element is not None:
            return preferred_element

    for element_name in ROOT_ELEMENT_NAMES:
        root_element = tree.find(f"{NS}{element_name}")
        if root_element is not None:
            return root_element
    return None


def parse_imdi(xml_bytes: bytes) -> ImdiNode | None:
    """Parse IMDI XML bytes and return the root ``ImdiNode`` (or ``None`` on error)."""
    try:
        parser = etree.XMLParser(
            resolve_entities=False,
            no_network=True,
            load_dtd=False,
            recover=False,
            huge_tree=False,
        )
        tree = etree.fromstring(xml_bytes, parser=parser)  # noqa: S320
    except (etree.XMLSyntaxError, TypeError, ValueError):
        logger.warning("Failed to parse IMDI XML", exc_info=True)
        return None

    root_element = _select_root_element(tree)
    if root_element is None:
        logger.warning(
            "IMDI XML has no recognizable Session, Corpus, or Catalogue element",
        )
        return None

    root_node = _parse_element(root_element)
    for attr_name, attr_value in tree.attrib.items():
        attr_key = f"METATRANSCRIPT @{_local_name(attr_name)}"
        _add_metadata(root_node.metadata, attr_key, attr_value)

    return root_node
