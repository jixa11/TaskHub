# -*- coding: utf-8 -*-
"""Fourth round of on-site findings for R12: dropdown rows and chat direction."""
import pathlib
import re
import unittest

from _paths import ROOT, SRC, project_file  # noqa: E402


def src(name):
    return project_file(name).read_text(encoding="utf-8")


def rule(css, selector):
    """Body of the first rule written exactly as `selector{...}`."""
    m = re.search(r"(?:^|[}\s])%s\{([^}]*)\}" % re.escape(selector), css)
    if not m:
        raise AssertionError("rule not found: " + selector)
    return m.group(1)


class DropdownRowTests(unittest.TestCase):
    def test_option_list_is_not_a_flex_container(self):
        # A flex column let client engines that resolve min-height:auto to
        # zero squeeze a long list until the rows overlapped each other.
        body = rule(src("ui.html"), ".sel-pop-list")
        self.assertIn("display:block", body)
        self.assertNotIn("flex", body)

    def test_rows_cannot_be_squeezed(self):
        body = rule(src("ui.html"), ".sel-opt")
        self.assertIn("display:block", body)
        self.assertIn("flex:none", body)
        self.assertRegex(body, r"min-height:\d+px")

    def test_popup_itself_is_block(self):
        html = src("ui.html")
        self.assertIn("display:block", rule(html, ".sel-pop.open"))
        self.assertNotIn("flex-direction", rule(html, ".sel-pop"))

    def test_rows_are_visually_separated(self):
        self.assertIn(".sel-opt+.sel-opt{border-top:", src("ui.html"))


class ChatDirectionTests(unittest.TestCase):
    def test_page_is_rtl(self):
        self.assertIn('<html dir="rtl"', src("ui.html"))

    def test_own_messages_start_on_the_right(self):
        css = src("v8_ui.css")
        mine = rule(css, ".v8-msg-row.mine")
        other = rule(css, ".v8-msg-row.other")
        # In an RTL page flex-start is the right-hand edge.
        self.assertIn("justify-content:flex-start", mine)
        self.assertNotIn("row-reverse", mine)
        # The other side is mirrored so its avatar sits on the outer edge.
        self.assertIn("flex-direction:row-reverse", other)
        self.assertIn("justify-content:flex-start", other)

    def test_grouped_follow_up_leaves_room_on_the_avatar_side(self):
        css = src("v8_ui.css")
        self.assertNotIn(".v8-msg-row.other.grouped{padding-inline-start", css)
        self.assertIn(".v8-msg-row.other.grouped{padding-inline-end:40px}", css)
        self.assertIn(".v8-msg-row.other.grouped{padding-inline-end:34px}", css)

    def test_bubble_tails_point_at_the_sender(self):
        css = src("v8_ui.css")
        # border-radius order: top-left top-right bottom-right bottom-left
        other = re.search(r"\n\.v8-message\{position:relative;[^}]*border-radius:([^;]*);", css)
        mine = re.search(r"\n\.v8-message\.mine\{background:linear-gradient[^}]*border-radius:([^;}]*)", css)
        self.assertEqual(other.group(1), "14px 14px 14px 5px")
        self.assertEqual(mine.group(1), "14px 14px 5px 14px")

    def test_each_message_picks_its_own_direction(self):
        # Persian stays right-to-left; a Finglish or English line gets its
        # punctuation in the right place instead of being scrambled.
        js = src("v8_ui.js")
        self.assertNotIn('<div class="v8-message-text">', js)
        self.assertIn('<div class="v8-message-text" dir="auto">', js)


if __name__ == "__main__":
    unittest.main()
