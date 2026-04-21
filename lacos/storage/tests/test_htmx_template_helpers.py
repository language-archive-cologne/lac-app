from lacos.common.mixins.htmx_template_helpers import HtmxTemplateHelperMixin


def test_render_message_template_escapes_html():
    helper = HtmxTemplateHelperMixin()

    rendered = str(helper.render_message_template('<img src=x onerror=alert(1)>', level="error"))

    assert "<img" not in rendered
    assert "&lt;img src=x onerror=alert(1)&gt;" in rendered
