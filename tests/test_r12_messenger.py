# -*- coding: utf-8 -*-
"""Regression guards for the three messenger defects fixed in R12.

Each test pins the specific mechanism that was broken, not just the presence
of some code, so a future edit that reintroduces the bug fails here.
"""
import pathlib
import re
import unittest

from _paths import ROOT, SRC, project_file  # noqa: E402


def src(name):
    return project_file(name).read_text(encoding="utf-8")


class MessengerScrollTests(unittest.TestCase):
    """A long conversation must scroll instead of pushing the composer away."""

    def test_message_list_and_main_column_can_shrink(self):
        css = src("v8_ui.css")
        main = re.search(r"\.v8-chat-main\{([^}]*)\}", css)
        self.assertIsNotNone(main, ".v8-chat-main rule disappeared")
        self.assertIn("min-height:0", main.group(1))
        messages = re.search(r"\.v8-messages\{([^}]*)\}", css)
        self.assertIsNotNone(messages, ".v8-messages rule disappeared")
        self.assertIn("min-height:0", messages.group(1))
        self.assertRegex(messages.group(1), r"overflow-y:\s*auto")

    def test_composer_and_header_are_never_squeezed_out(self):
        css = src("v8_ui.css")
        self.assertRegex(css, r"\.v8-chat-compose\s*\{\s*flex:0 0 auto")

    def test_active_pane_keeps_its_own_min_height(self):
        # The inline style on #v8-chat-active is what lets the flex column
        # inside the grid item collapse; losing it re-breaks the layout.
        js = src("v8_ui.js")
        self.assertIn('id="v8-chat-active"', js)
        self.assertIn("min-height:0", js)


class MessengerHistoryTests(unittest.TestCase):
    """Opening an old conversation must land on the newest messages."""

    def test_initial_open_selects_the_newest_page(self):
        py = src("v8_features.py")
        # The newest page is a DESC top-N re-sorted ascending for display.
        self.assertIn("ORDER BY m.id DESC) t ORDER BY t.id ASC", py)
        self.assertIn("before_id", py)
        self.assertIn("has_more", py)

    def test_polling_path_stays_chronological(self):
        py = src("v8_features.py")
        self.assertIn("WHERE m.conversation_id=? AND m.id>? AND m.is_deleted=0", py)

    def test_ui_pages_backwards_and_keeps_scroll_anchor(self):
        js = src("v8_ui.js")
        self.assertIn("function v8ChatLoadOlder", js)
        self.assertIn("before_id:V8.chat.messages[0].id", js)
        self.assertIn("anchorTop+(box.scrollHeight-anchorHeight)", js)

    def test_render_does_not_force_scroll_to_bottom(self):
        js = src("v8_ui.js")
        render = js[js.index("function v8ChatRenderMessages"):]
        render = render[:render.index("\nfunction ")]
        # Jumping unconditionally is what made reading history impossible.
        self.assertIn("if(stick)box.scrollTop=box.scrollHeight;", render)
        self.assertNotIn("';box.scrollTop=box.scrollHeight;", render)


class MessengerUnreadTests(unittest.TestCase):
    """New messages must be visible from anywhere in the app."""

    def test_unread_summary_endpoint_exists_and_is_permission_mapped(self):
        py = src("v8_features.py")
        self.assertIn('"/api/v8/chat/unread_summary"', py)
        self.assertIn("def api_v8_chat_unread_summary", py)
        self.assertIn('"api_v8_chat_unread_summary": "chat.use"', src("rbac.py"))

    def test_unread_counts_exclude_the_readers_own_messages(self):
        py = src("v8_features.py")
        self.assertGreaterEqual(py.count("sender_user_id<>m.user_id"), 2)

    def test_watcher_runs_independently_of_the_messenger_page(self):
        js = src("v8_ui.js")
        self.assertIn("function v8ChatStartUnreadWatch", js)
        self.assertIn("v8ChatStartUnreadWatch();", js)
        watcher = js[js.index("async function v8ChatUnreadTick"):]
        watcher = watcher[:watcher.index("function v8ChatStartUnreadWatch")]
        self.assertIn("/v8/chat/unread_summary", watcher)
        # The badge must be written before anything looks at which page is
        # open: the old code only refreshed it inside the conversation-list
        # fetch, which runs solely while page 24 is active.
        before_badge = watcher[:watcher.index("v8ChatSetBadge(total)")]
        self.assertNotIn("pg24", before_badge)
        self.assertNotIn("page.active", before_badge)
        # The timer itself is unconditional, unlike v8ChatPoll's interval.
        starter = js[js.index("function v8ChatStartUnreadWatch"):]
        starter = starter[:starter.index("function v8ChatStopUnreadWatch")]
        self.assertNotIn("pg24", starter)

    def test_new_message_reaches_the_badge_and_the_alert_layer(self):
        js = src("v8_ui.js")
        self.assertIn("function v8ChatSetBadge", js)
        self.assertIn("v8-chat-badge", js)
        self.assertIn("notifyDesktop(", js)
        self.assertIn("startTitleAlert(", js)

    def test_watcher_stops_on_logout(self):
        self.assertIn("v8ChatStopUnreadWatch();", src("ui.html"))

    def test_login_backlog_does_not_trigger_an_alert_storm(self):
        js = src("v8_ui.js")
        self.assertIn("unreadSeeded", js)


if __name__ == "__main__":
    unittest.main()
