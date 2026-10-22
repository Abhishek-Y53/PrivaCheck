import time
from typing import List

from playwright.async_api import Page

from backend.schemas.core import Observation


class DOMCollector:
    """
    Collects only DOM data required by the compliance checks.

    Responsible for:
    - Forms and form controls
    - Buttons and consent controls
    - Visible page text
    - CMP-related script sources
    - Visual/layout information needed for dark-pattern and cookie-wall checks

    Does not perform compliance analysis.
    """

    def __init__(self, page: Page, source_url: str):
        self.page = page
        self.source_url = source_url

    async def collect_forms(self) -> List[Observation]:
        """
        Collect form structure and controls without collecting input values.
        """

        forms = await self.page.evaluate(
            """
            () => {
                return Array.from(document.querySelectorAll("form")).map(form => ({
                    action: form.action,
                    method: form.method.toUpperCase(),

                    controls: Array.from(
                        form.querySelectorAll("input, select, textarea")
                    ).map(control => {

                        const label =
                            control.labels && control.labels.length > 0
                                ? Array.from(control.labels)
                                    .map(label => label.innerText.trim())
                                    .join(" ")
                                : "";

                        return {
                            tag: control.tagName.toLowerCase(),
                            type: control.type || null,
                            name: control.name || null,
                            id: control.id || null,
                            required: control.required,
                            checked:
                                control.type === "checkbox" ||
                                control.type === "radio"
                                    ? control.checked
                                    : null,
                            label: label
                        };
                    })
                }));
            }
            """
        )

        return [
            Observation(
                category="dom_form",
                source_url=self.source_url,
                timestamp=time.time(),
                data=form
            )
            for form in forms
        ]

    async def collect_buttons(self) -> List[Observation]:
        """
        Collect button information required for consent and visual checks.
        """

        buttons = await self.page.evaluate(
            """
            () => {
                return Array.from(
                    document.querySelectorAll(
                        "button, input[type='button'], input[type='submit']"
                    )
                )
                .filter(button => {
                    const style = window.getComputedStyle(button);
                    return style.display !== "none" &&
                           style.visibility !== "hidden";
                })
                .map(button => {

                    const style = window.getComputedStyle(button);
                    const rect = button.getBoundingClientRect();

                    return {
                        text: (
                            button.innerText ||
                            button.value ||
                            button.getAttribute("aria-label") ||
                            ""
                        ).trim(),

                        id: button.id || null,
                        class_name:
                            typeof button.className === "string"
                                ? button.className
                                : null,

                        role: button.getAttribute("role"),
                        aria_label: button.getAttribute("aria-label"),

                        visible: rect.width > 0 && rect.height > 0,

                        position: {
                            x: rect.x,
                            y: rect.y,
                            width: rect.width,
                            height: rect.height
                        },

                        styles: {
                            background_color: style.backgroundColor,
                            color: style.color,
                            font_size: style.fontSize,
                            font_weight: style.fontWeight,
                            opacity: style.opacity
                        }
                    };
                });
            }
            """
        )

        return [
            Observation(
                category="dom_button",
                source_url=self.source_url,
                timestamp=time.time(),
                data=button
            )
            for button in buttons
        ]

    async def collect_inputs(self) -> List[Observation]:
        """
        Collect input metadata required for checkbox, password,
        age-gate and special-category checks.
        """

        inputs = await self.page.evaluate(
            """
            () => {
                return Array.from(
                    document.querySelectorAll(
                        "input, select, textarea"
                    )
                ).map(input => {

                    const label =
                        input.labels && input.labels.length > 0
                            ? Array.from(input.labels)
                                .map(label => label.innerText.trim())
                                .join(" ")
                            : "";

                    return {
                        tag: input.tagName.toLowerCase(),
                        type: input.type || null,
                        name: input.name || null,
                        id: input.id || null,
                        required: input.required,

                        checked:
                            input.type === "checkbox" ||
                            input.type === "radio"
                                ? input.checked
                                : null,

                        label: label
                    };
                });
            }
            """
        )

        return [
            Observation(
                category="dom_input",
                source_url=self.source_url,
                timestamp=time.time(),
                data=input_data
            )
            for input_data in inputs
        ]

    async def collect_visible_text(self) -> List[Observation]:
        """
        Collect visible page text required for detecting
        DSAR, erasure, objection, DPO and supervisory-authority information.
        """

        text = await self.page.locator("body").inner_text()

        text = " ".join(text.split())

        if not text:
            return []

        return [
            Observation(
                category="dom_visible_text",
                source_url=self.source_url,
                timestamp=time.time(),
                data={
                    "text": text
                }
            )
        ]

    async def collect_scripts(self) -> List[Observation]:
        """
        Collect script sources needed for detecting known CMP platforms.
        """

        scripts = await self.page.evaluate(
            """
            () => Array.from(document.scripts)
                .map(script => script.src)
                .filter(src => src)
            """
        )

        if not scripts:
            return []

        return [
            Observation(
                category="dom_scripts",
                source_url=self.source_url,
                timestamp=time.time(),
                data={
                    "src": src
                }
            )
            for src in scripts
        ]

    async def collect_layout_state(self) -> List[Observation]:
        """
        Collect only the layout information required for cookie/tracking
        wall detection.
        """

        layout = await self.page.evaluate(
            """
            () => {

                const bodyStyle = window.getComputedStyle(document.body);

                const fixedElements = Array.from(
                    document.querySelectorAll("*")
                )
                .filter(element => {
                    const style = window.getComputedStyle(element);
                    const rect = element.getBoundingClientRect();

                    return (
                        style.position === "fixed" &&
                        rect.width > 0 &&
                        rect.height > 0
                    );
                })
                .map(element => {
                    const style = window.getComputedStyle(element);
                    const rect = element.getBoundingClientRect();

                    return {
                        tag: element.tagName.toLowerCase(),
                        id: element.id || null,
                        class_name:
                            typeof element.className === "string"
                                ? element.className
                                : null,
                        z_index: style.zIndex,
                        opacity: style.opacity,
                        width: rect.width,
                        height: rect.height
                    };
                });

                const consentRelatedFixedElementCount = fixedElements.filter(
                    element =>
                        /cookie|consent|privacy|cmp|preference|overlay/i.test(
                            `${element.id || ""} ${element.class_name || ""}`
                        )
                ).length;

                return {
                    body_overflow: bodyStyle.overflow,
                    body_overflow_x: bodyStyle.overflowX,
                    body_overflow_y: bodyStyle.overflowY,
                    fixed_elements: fixedElements,
                    fixed_element_count: fixedElements.length,
                    consent_related_fixed_element_count:
                        consentRelatedFixedElementCount
                };
            }
            """
        )

        return [
            Observation(
                category="dom_layout",
                source_url=self.source_url,
                timestamp=time.time(),
                data=layout
            )
        ]

    async def collect_all(self) -> List[Observation]:
        """
        Collect all DOM data required by the compliance layer.
        """

        forms = await self.collect_forms()
        buttons = await self.collect_buttons()
        inputs = await self.collect_inputs()
        text = await self.collect_visible_text()
        scripts = await self.collect_scripts()
        layout = await self.collect_layout_state()

        return (
            forms
            + buttons
            + inputs
            + text
            + scripts
            + layout
        )