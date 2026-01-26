"""Message formatter for aggregator."""

import copy
import re
from telethon import utils as tl_utils
from telethon.tl.types import (
    Message,
    MessageMediaPhoto,
    MessageMediaDocument,
    MessageMediaWebPage,
    DocumentAttributeSticker,
    DocumentAttributeVideo,
    DocumentAttributeAudio,
    DocumentAttributeFilename,
    User,
    Chat,
    Channel,
    MessageEntityTextUrl,
    MessageEntityBlockquote,
    InputMessageEntityMentionName,
    InputUser,
)


class Formatter:
    """Format messages for aggregator."""

    @staticmethod
    def utf16_len(text: str) -> int:
        """Get length of string in UTF-16 code units (as Telegram counts)."""
        return len(text.encode('utf-16-le')) // 2

    @staticmethod
    def get_sender_name(sender) -> str:
        """Get sender display name."""
        if sender is None:
            return "Unknown"

        if isinstance(sender, User):
            parts = []
            if sender.first_name:
                parts.append(sender.first_name)
            if sender.last_name:
                parts.append(sender.last_name)
            return " ".join(parts) if parts else sender.username or "Unknown"

        if isinstance(sender, (Chat, Channel)):
            return sender.title or "Unknown"

        return "Unknown"

    @staticmethod
    def get_chat_name(chat) -> str:
        """Get chat display name."""
        if isinstance(chat, (Chat, Channel)):
            return chat.title or "Unknown"
        return "Unknown"

    @staticmethod
    def get_message_link(chat, message_id: int) -> str | None:
        """Get message link (works for both public and private chats)."""
        if isinstance(chat, Channel):
            if chat.username:
                return f"https://t.me/{chat.username}/{message_id}"
            else:
                # Private channel/group: use c/ format
                return f"https://t.me/c/{chat.id}/{message_id}"
        elif isinstance(chat, Chat):
            # Regular group (not supergroup) - no direct link available
            return None
        return None

    @staticmethod
    def get_chat_link(chat) -> str | None:
        """Get link to chat/channel."""
        if isinstance(chat, Channel):
            if chat.username:
                return f"https://t.me/{chat.username}"
            else:
                # Private channel: use c/ format
                # In Telethon, channel IDs are positive but for t.me/c/ links
                # we use the ID directly (Telethon already gives us the correct ID)
                return f"https://t.me/c/{chat.id}"
        return None

    @staticmethod
    def escape_html(text: str) -> str:
        """Escape HTML special characters."""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    @staticmethod
    def convert_markdown_links_to_html(text: str) -> str:
        """Convert Markdown links [text](url) to HTML <a> tags.

        Specifically handles tg://user?id= links for mentions.
        """
        # Pattern for [text](url)
        pattern = r'\[([^\]]+)\]\((tg://user\?id=\d+)\)'

        def replace_link(match):
            link_text = Formatter.escape_html(match.group(1))
            url = match.group(2)
            return f'<a href="{url}">{link_text}</a>'

        return re.sub(pattern, replace_link, text)

    @staticmethod
    def text_to_html(text: str) -> str:
        """Convert message text to HTML, handling mentions."""
        # First convert markdown links to HTML
        result = Formatter.convert_markdown_links_to_html(text)
        # Then escape remaining HTML chars (but not the links we just created)
        # Actually we need different approach - escape first, then convert
        return result

    @staticmethod
    def prepare_content_html(text: str) -> str:
        """Prepare message content for HTML output.

        Escapes HTML but preserves/converts markdown mention links.
        """
        # Pattern for [text](tg://user?id=...)
        pattern = r'\[([^\]]+)\]\((tg://user\?id=\d+)\)'

        # Find all markdown links first
        links = []
        for match in re.finditer(pattern, text):
            links.append({
                'full': match.group(0),
                'text': match.group(1),
                'url': match.group(2),
                'start': match.start(),
                'end': match.end()
            })

        # If no links, just escape and return
        if not links:
            return Formatter.escape_html(text)

        # Build result, escaping text between links
        result = []
        pos = 0
        for link in links:
            # Add escaped text before this link
            if link['start'] > pos:
                result.append(Formatter.escape_html(text[pos:link['start']]))
            # Add HTML link
            link_text = Formatter.escape_html(link['text'])
            result.append(f'<a href="{link["url"]}">{link_text}</a>')
            pos = link['end']

        # Add remaining text
        if pos < len(text):
            result.append(Formatter.escape_html(text[pos:]))

        return ''.join(result)

    @staticmethod
    def format_mention_notification_html(
        chat,
        chat_name: str,
        message_link: str | None,
        sender,
        sender_name: str,
        text: str | None,
        media_type: str | None,
        mention_type: str = "mention",  # "mention", "reply"
        mentioned_account_name: str | None = None,
        mentioned_account_id: int | None = None,
    ) -> str:
        """Format mention notification as HTML.

        Format:
        <icon> <a href="profile">Account Name</a> | <a href="group">Chat Name</a>
        От: <a href="tg://user?id=123">Sender Name</a>
        <blockquote>message text</blockquote>

        Icons:
        - 🔔 for mention
        - ↩️ for reply
        """
        escape = Formatter.escape_html

        # Icon based on mention type
        icons = {
            "mention": "🔔",
            "reply": "↩️",
        }
        icon = icons.get(mention_type, "🔔")

        # Account name (who was mentioned) with profile link
        account_text = escape(mentioned_account_name or "Unknown")
        if mentioned_account_id:
            account_part = f'<a href="tg://user?id={mentioned_account_id}">{account_text}</a>'
        else:
            account_part = account_text

        # Chat name with link to group
        chat_text = escape(chat_name)
        chat_link = Formatter.get_chat_link(chat)  # Link to group, not message

        if chat_link:
            chat_part = f'<a href="{chat_link}">{chat_text}</a>'
        else:
            chat_part = chat_text

        # Sender with profile link
        sender_text = escape(sender_name)
        if isinstance(sender, User) and sender.id:
            sender_part = f'<a href="tg://user?id={sender.id}">{sender_text}</a>'
        else:
            sender_part = sender_text

        # Message link (separate, if available)
        link_part = ""
        if message_link:
            link_part = f' (<a href="{message_link}">сообщение</a>)'

        # Message content
        if text:
            content = Formatter.prepare_content_html(text)
        elif media_type:
            media_labels = {
                "photo": "[Фото]",
                "video": "[Видео]",
                "video_note": "[Видеосообщение]",
                "voice": "[Голосовое сообщение]",
                "audio": "[Аудио]",
                "sticker": "[Стикер]",
                "document": "[Документ]",
                "media": "[Медиа]",
            }
            content = media_labels.get(media_type, "[Медиа]")
        else:
            content = "[Пустое сообщение]"

        # Build final HTML
        result = f"{icon} {account_part} | {chat_part}{link_part}\n"
        result += f"От: {sender_part}\n"
        result += f"<blockquote>{content}</blockquote>"

        return result

    @staticmethod
    def get_media_type(message: Message) -> str | None:
        """Determine media type from message."""
        if not message.media:
            return None

        if isinstance(message.media, MessageMediaPhoto):
            return "photo"

        if isinstance(message.media, MessageMediaDocument):
            doc = message.media.document
            if doc:
                for attr in doc.attributes:
                    if isinstance(attr, DocumentAttributeSticker):
                        return "sticker"
                    if isinstance(attr, DocumentAttributeVideo):
                        if getattr(attr, "round_message", False):
                            return "video_note"
                        return "video"
                    if isinstance(attr, DocumentAttributeAudio):
                        if getattr(attr, "voice", False):
                            return "voice"
                        return "audio"
                    if isinstance(attr, DocumentAttributeFilename):
                        return "document"
                return "document"

        if isinstance(message.media, MessageMediaWebPage):
            return None  # Web preview, not actual media

        return "media"

    @staticmethod
    def shift_entities(entities: list | None, offset: int) -> list:
        """Shift entities by offset (in UTF-16 code units) to account for added header."""
        if not entities:
            return []

        shifted = []
        for entity in entities:
            entity_copy = copy.copy(entity)
            entity_copy.offset += offset
            shifted.append(entity_copy)
        return shifted

    @staticmethod
    def format_message(
        sender_name: str,
        text: str | None,
        media_type: str | None,
        link: str | None,
        entities: list | None = None,
    ) -> tuple[str, list]:
        """Format message for aggregator.

        Format:
        • <SENDER>

        <TEXT or media description>

        Link: https://t.me/... (only for public chats)

        Returns:
            Tuple of (formatted_text, shifted_entities)
        """
        header = f"• {sender_name}\n\n"

        if text:
            content = text
            shifted_entities = Formatter.shift_entities(entities, len(header))
        elif media_type:
            media_labels = {
                "photo": "[Фото]",
                "video": "[Видео]",
                "video_note": "[Видеосообщение]",
                "voice": "[Голосовое сообщение]",
                "audio": "[Аудио]",
                "sticker": "[Стикер]",
                "document": "[Документ]",
                "media": "[Медиа]",
            }
            content = media_labels.get(media_type, "[Медиа]")
            shifted_entities = []
        else:
            content = "[Пустое сообщение]"
            shifted_entities = []

        result = header + content

        if link:
            result += f"\n\nСсылка: {link}"

        return result, shifted_entities

    @staticmethod
    def format_caption(
        sender_name: str,
        caption: str | None,
        link: str | None,
        entities: list | None = None,
    ) -> tuple[str, list]:
        """Format caption for media message.

        Format:
        • <SENDER>

        <CAPTION>

        Link: https://t.me/... (only for public chats)

        Returns:
            Tuple of (formatted_caption, shifted_entities)
        """
        header = f"• {sender_name}"

        if caption:
            header += "\n\n"
            result = header + caption
            shifted_entities = Formatter.shift_entities(entities, len(header))
        else:
            result = header
            shifted_entities = []

        if link:
            result += f"\n\nСсылка: {link}"

        return result, shifted_entities
