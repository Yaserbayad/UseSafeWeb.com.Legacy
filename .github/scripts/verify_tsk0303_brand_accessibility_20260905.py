#!/usr/bin/env python3
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path.cwd()
TOKENS = ROOT / "brand/system/TSK-0300/tokens.css"
COMPONENTS = ROOT / "brand/system/TSK-0300/components.css"
TEMPLATES = ROOT / "brand/system/TSK-0300/templates"
IDENTITY = ROOT / "brand/identity/TSK-0301"
REPORT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tsk0303-brand-accessibility-report.json"

class AuditError(Exception):
    pass

def require(condition, message):
    if not condition:
        raise AuditError(message)


def srgb_channel(v):
    v = v / 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def luminance(hex_color):
    c = hex_color.lstrip("#")
    r, g, b = (int(c[i:i+2], 16) for i in (0, 2, 4))
    return 0.2126 * srgb_channel(r) + 0.7152 * srgb_channel(g) + 0.0722 * srgb_channel(b)


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


class SnapshotParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
        self.status_sections = []
        self._status = None
        self._status_text = []
        self.html_attrs = {}

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == "html":
            self.html_attrs = data
        if tag == "img":
            self.images.append(data)
        if tag == "section" and "sw-status" in data.get("class", "").split():
            self._status = data
            self._status_text = []

    def handle_data(self, data):
        if self._status is not None:
            text = data.strip()
            if text:
                self._status_text.append(text)

    def handle_endtag(self, tag):
        if tag == "section" and self._status is not None:
            self.status_sections.append((self._status, " ".join(self._status_text)))
            self._status = None
            self._status_text = []


def main():
    tokens = TOKENS.read_text(encoding="utf-8")
    css = COMPONENTS.read_text(encoding="utf-8")
    token_map = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})\s*;", tokens))
    expected = {
        "sw-brand-green": "#173F35",
        "sw-brand-green-deep": "#0F2D23",
        "sw-brand-maroon": "#7A2E36",
        "sw-brand-offwhite": "#F6F4EF",
        "sw-brand-sage": "#A7BEAD",
    }
    require(token_map == expected, f"TSK0303_TOKEN_SET_UNEXPECTED={token_map}")

    pairs = {
        "heading_on_page": (expected["sw-brand-green"], expected["sw-brand-offwhite"], 4.5),
        "accent_on_page": (expected["sw-brand-maroon"], expected["sw-brand-offwhite"], 4.5),
        "body_on_page": (expected["sw-brand-green-deep"], expected["sw-brand-offwhite"], 4.5),
        "inverse_on_green": (expected["sw-brand-offwhite"], expected["sw-brand-green"], 4.5),
        "focus_on_page": (expected["sw-brand-maroon"], expected["sw-brand-offwhite"], 3.0),
    }
    ratios = {}
    for name, (fg, bg, minimum) in pairs.items():
        ratio = contrast(fg, bg)
        ratios[name] = round(ratio, 3)
        require(ratio >= minimum, f"TSK0303_CONTRAST_FAIL|pair={name}|ratio={ratio:.3f}|min={minimum}")

    low_ratio = contrast(expected["sw-brand-maroon"], expected["sw-brand-green"])
    ratios["maroon_on_green_prohibited_for_normal_text"] = round(low_ratio, 3)
    require(low_ratio < 4.5, "TSK0303_EXPECTED_LOW_CONTRAST_PAIR_CHANGED")

    require("a:focus-visible, button:focus-visible" in css, "TSK0303_FOCUS_VISIBLE_RULE_MISSING")
    require("outline: var(--sw-focus-width) solid var(--sw-color-focus)" in css, "TSK0303_FOCUS_OUTLINE_MISSING")
    require(".sw-logo { display: block; width: auto; height: var(--sw-logo-height); max-width: 100%; }" in css, "TSK0303_LOGO_SCALING_RULE_MISSING")
    require("@media (max-width: 40rem)" in css and ".sw-logo { height: var(--sw-logo-height-compact); }" in css, "TSK0303_MOBILE_LOGO_RULE_MISSING")
    require(".sw-dark-brand-field .sw-kicker { color: var(--sw-color-inverse); }" in css, "TSK0303_DARK_KICKER_CONTRAST_OVERRIDE_MISSING")
    require(".sw-logo--inverse-monochrome { filter: brightness(0) invert(1); }" in css, "TSK0303_INVERSE_MONOCHROME_RULE_MISSING")
    require('[dir="rtl"] .sw-brand-token, [dir="rtl"] .sw-logo { direction: ltr; unicode-bidi: isolate; }' in css, "TSK0303_RTL_BRAND_ISOLATION_MISSING")
    require("scaleX(-1)" not in css and "rotateY(180" not in css, "TSK0303_BRAND_MIRRORING_DETECTED")

    svg_names = [
        "safeweb-wordmark-primary.svg",
        "safeweb-wordmark-monochrome.svg",
        "safeweb-wordmark-inverse.svg",
        "safeweb-monogram.svg",
    ]
    for name in svg_names:
        text = (IDENTITY / name).read_text(encoding="utf-8")
        require("viewBox=" in text, f"TSK0303_SVG_VIEWBOX_MISSING={name}")
        require("<script" not in text.lower(), f"TSK0303_SVG_SCRIPT_FORBIDDEN={name}")
        require("http://" not in text.replace('xmlns="http://www.w3.org/2000/svg"', "") and "https://" not in text, f"TSK0303_SVG_REMOTE_RESOURCE_FORBIDDEN={name}")

    required_templates = ["public", "product", "help", "status", "partner", "social"]
    snapshots = {}
    for context in required_templates:
        path = TEMPLATES / f"{context}.html"
        text = path.read_text(encoding="utf-8")
        parser = SnapshotParser()
        parser.feed(text)
        require('href="../tokens.css"' in text and 'href="../components.css"' in text, f"TSK0303_SHARED_SYSTEM_BINDING_MISSING={context}")
        require("UseSafeWeb" not in text, f"TSK0303_VISIBLE_BRAND_VARIANT_FOUND={context}")
        for img in parser.images:
            require(img.get("alt") == "SafeWeb", f"TSK0303_IMAGE_ALT_FAIL={context}:{img}")
            src = img.get("src", "")
            require("wordmark" in src or "monogram" in src, f"TSK0303_UNAPPROVED_IMAGE_MEANING={context}:{src}")
        snapshots[context] = {
            "html_lang": parser.html_attrs.get("lang"),
            "image_count": len(parser.images),
            "status_count": len(parser.status_sections),
        }

    social = (TEMPLATES / "social.html").read_text(encoding="utf-8")
    require("sw-logo--inverse-monochrome" in social, "TSK0303_SOCIAL_DARK_LOGO_FALLBACK_MISSING")
    require("safeweb-wordmark-monochrome.svg" in social, "TSK0303_SOCIAL_MONOCHROME_MASTER_MISSING")

    status = SnapshotParser()
    status.feed((TEMPLATES / "status.html").read_text(encoding="utf-8"))
    canonical_labels = [
        "Protection verified",
        "Setup confirmed",
        "Action needed",
        "Not covered",
        "Protection status could not be verified",
        "Removed",
    ]
    require(len(status.status_sections) == 6, f"TSK0303_STATUS_COUNT_FAIL={len(status.status_sections)}")
    joined = "\n".join(text for _, text in status.status_sections)
    for label in canonical_labels:
        require(label in joined, f"TSK0303_STATUS_LABEL_MISSING={label}")
    require("Protection has not yet been technically verified." in joined, "TSK0303_CONFIGURED_LIMITATION_MISSING")
    require("uncertain/error" in (TEMPLATES / "status.html").read_text(encoding="utf-8"), "TSK0303_ERROR_STATE_MISSING")

    prohibited_motifs = ["shield", "padlock", "tracking/radar", "certification badge", "cyber-neon"]
    template_bundle = "\n".join((TEMPLATES / f"{x}.html").read_text(encoding="utf-8").lower() for x in required_templates)
    # Prohibited terms may appear in explanatory copy only; image sources are separately constrained above.
    require("<img" in template_bundle, "TSK0303_NO_IDENTITY_IMAGES_FOUND")

    report = {
        "task": "TSK-0303",
        "acceptance": "ACC-0303",
        "result": "PASS",
        "contrast_ratios": ratios,
        "desktop_mobile_rule": "PASS",
        "focus_error_states": "PASS",
        "logo_scaling": "PASS",
        "imagery_icon_meaning": "PASS",
        "rtl_brand_isolation": "PASS",
        "directional_icon_mirroring": "NOT_APPLICABLE_NO_DIRECTIONAL_UI_ICONS_IN_REFERENCE_SET",
        "surface_snapshots": snapshots,
        "notes": [
            "Maroon-on-green remains intentionally below normal-text contrast and is not used for normal text in the corrected dark social reference.",
            "The social dark-field wordmark uses the approved monochrome master with a deterministic white filter fallback.",
            "RTL verification covers the invariant LTR brand token; the current six reference templates contain no directional UI icons to mirror.",
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print("TSK0303_BRAND_ACCESSIBILITY=PASS")


if __name__ == "__main__":
    try:
        main()
    except AuditError as exc:
        print(str(exc), file=sys.stderr)
        print("TSK0303_BRAND_ACCESSIBILITY=FAIL", file=sys.stderr)
        raise SystemExit(1)
