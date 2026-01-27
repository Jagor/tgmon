"""Message monitoring and forwarding."""

from datetime import datetime

from telethon import events
from telethon.tl.types import Message, MessageEntityMention, MessageEntityMentionName

from ..core.models import Account, Aggregator, Watch
from ..utils.rate_limiter import RateLimiter
from .client import TelegramClient
from .formatter import Formatter


class Monitor:
    """Monitor chats and forward messages to aggregator."""

    def __init__(
        self,
        account: Account,
        aggregator: Aggregator,
        watches: list[Watch],
        agg_client: TelegramClient,
    ) -> None:
        self.account = account
        self.aggregator = aggregator
        self.watches = watches

        # If account is the same as aggregator account, reuse agg_client
        if account.name == agg_client.account.name:
            self.client = agg_client
            self._owns_client = False
        else:
            self.client = TelegramClient(account)
            self._owns_client = True

        self.agg_client = agg_client
        self.rate_limiter = RateLimiter(min_delay=0.2, max_delay=0.3)
        self.formatter = Formatter()

        self._running = False
        self._watch_chat_ids: set[int] = set()
        self._agg_entity = None
        self._resolved_chats: dict[int, tuple[int, str]] = {}  # watch.id -> (chat_id, chat_title)
        self._resolved_aggregator: tuple[int, str] | None = None  # (chat_id, chat_title)
        self._me = None  # Current user info
        self._my_user_id: int | None = None
        self._my_username: str | None = None

    async def start(self) -> None:
        """Start monitoring."""
        # Only connect if we own the client (not shared with agg_client)
        if self._owns_client:
            await self.client.connect()

            if not await self.client.is_authorized():
                raise RuntimeError(f"Account '{self.account.name}' is not authorized")

        # Get current user info for mention detection
        self._me = await self.client.get_me()
        self._my_user_id = self._me.id
        self._my_username = self._me.username.lower() if self._me.username else None

        # Resolve aggregator entity
        self._agg_entity = await self.agg_client.get_entity(self.aggregator.chat_ref)
        agg_chat_id = self._agg_entity.id
        agg_chat_title = self.formatter.get_chat_name(self._agg_entity)
        if self.aggregator.chat_id != agg_chat_id or self.aggregator.chat_title != agg_chat_title:
            self._resolved_aggregator = (agg_chat_id, agg_chat_title)

        # Resolve and cache watched chat IDs
        for watch in self.watches:
            try:
                entity = await self.client.get_entity(watch.chat_ref)
                chat_id = entity.id
                chat_title = self.formatter.get_chat_name(entity)
                self._watch_chat_ids.add(chat_id)

                # Store resolved chat info for later db update
                if watch.chat_id != chat_id or watch.chat_title != chat_title:
                    self._resolved_chats[watch.id] = (chat_id, chat_title)

                print(f"  Watching: {chat_title} (ID: {chat_id})")
            except Exception as e:
                print(f"  Failed to resolve {watch.chat_ref}: {e}")

        if not self._watch_chat_ids:
            raise RuntimeError("No valid chats to watch")

        # Register event handler
        self.client.add_event_handler(
            self._on_new_message,
            events.NewMessage(chats=list(self._watch_chat_ids)),
        )

        self._running = True
        print(f"Monitor started for '{self.account.name}'")

    def get_resolved_chats(self) -> dict[int, tuple[int, str]]:
        """Get dict of watch_id -> (chat_id, chat_title) for db update."""
        return self._resolved_chats

    def get_resolved_aggregator(self) -> tuple[int, str] | None:
        """Get resolved aggregator (chat_id, chat_title) if changed."""
        return self._resolved_aggregator

    async def stop(self) -> None:
        """Stop monitoring."""
        self._running = False

        try:
            self.client.remove_event_handler(
                self._on_new_message,
                events.NewMessage(chats=list(self._watch_chat_ids)),
            )
        except Exception:
            pass

        # Only disconnect if we own the client
        if self._owns_client:
            await self.client.disconnect()

        print(f"Monitor stopped for '{self.account.name}'")

    async def _get_mention_type(self, message: Message) -> str | None:
        """Check if message mentions current user or is a reply to their message.

        Returns:
            - "mention" if @username mention
            - "reply" if reply to user's message
            - None if not relevant
        """
        # Check for @username mention in entities
        if message.entities:
            for entity in message.entities:
                if isinstance(entity, MessageEntityMention):
                    # Extract mentioned username from message text
                    start = entity.offset
                    end = entity.offset + entity.length
                    mentioned = message.text[start:end].lstrip('@').lower()
                    if self._my_username and mentioned == self._my_username:
                        return "mention"
                elif isinstance(entity, MessageEntityMentionName):
                    # Direct user ID mention
                    if entity.user_id == self._my_user_id:
                        return "mention"

        # Check if this is a reply to my message
        if message.reply_to and message.reply_to.reply_to_msg_id:
            try:
                reply_msg = await self.client.client.get_messages(
                    message.chat_id,
                    ids=message.reply_to.reply_to_msg_id
                )
                if reply_msg and reply_msg.sender_id == self._my_user_id:
                    return "reply"
            except Exception:
                pass

        return None

    async def _on_new_message(self, event: events.NewMessage.Event) -> None:
        """Handle new message event."""
        if not self._running:
            return

        message: Message = event.message

        # Only forward if message mentions me or is reply to my message
        mention_type = await self._get_mention_type(message)
        if not mention_type:
            return

        chat = await event.get_chat()
        sender = await event.get_sender()

        try:
            await self._forward_message(message, chat, sender, mention_type)
        except Exception as e:
            print(f"Error forwarding message: {e}")

    async def _forward_message(self, message: Message, chat, sender, mention_type: str) -> None:
        """Forward message to aggregator."""
        await self.rate_limiter.wait()

        chat_name = self.formatter.get_chat_name(chat)
        sender_name = self.formatter.get_sender_name(sender)
        message_link = self.formatter.get_message_link(chat, message.id)
        media_type = self.formatter.get_media_type(message)

        # Get account full name (first + last) and ID
        account_parts = []
        if self._me.first_name:
            account_parts.append(self._me.first_name)
        if self._me.last_name:
            account_parts.append(self._me.last_name)
        account_name = " ".join(account_parts) if account_parts else (self._me.username or self.account.name)

        html = self.formatter.format_mention_notification_html(
            chat=chat,
            chat_name=chat_name,
            message_link=message_link,
            sender=sender,
            sender_name=sender_name,
            text=message.text,
            media_type=media_type,
            mention_type=mention_type,
            mentioned_account_name=account_name,
            mentioned_account_id=self._my_user_id,
        )

        await self.agg_client.send_message(
            self._agg_entity,
            html,
            parse_mode='html',
            link_preview=False,
        )

        timestamp = datetime.now().strftime("%H:%M:%S")
        icon = "@" if mention_type == "mention" else "<<"
        print(f"[{timestamp}] {icon} {mention_type} from {sender_name} in {chat_name}")
