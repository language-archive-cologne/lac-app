from django import forms


class DaisyFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_widget_classes()

    def _apply_widget_classes(self) -> None:
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.Textarea):
                css_class = "textarea textarea-bordered textarea-sm w-full"
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                css_class = "select select-bordered select-sm w-full"
            elif isinstance(widget, forms.CheckboxInput):
                css_class = "checkbox"
            else:
                css_class = "input input-bordered input-sm w-full"

            existing = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{existing} {css_class}".strip()
