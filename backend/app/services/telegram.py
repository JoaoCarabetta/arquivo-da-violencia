"""
Telegram Notification Service

Sends notifications to a Telegram chat for:
- Job start/finish/failure events
- New deaths added to UniqueEvents
"""

from datetime import datetime
from typing import Any

import httpx
from loguru import logger

from app.config import get_settings


class TelegramNotifier:
    """Telegram bot for sending notifications."""
    
    def __init__(self):
        self.settings = get_settings()
        self.bot_token = self.settings.telegram_bot_token
        self.chat_id = self.settings.telegram_chat_id
        self.enabled = bool(self.bot_token and self.chat_id)
        
        if not self.enabled:
            logger.warning("[Telegram] Bot not configured - notifications disabled")
    
    @property
    def api_url(self) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}"
    
    async def send_message(
        self, 
        text: str, 
        parse_mode: str = "HTML",
        disable_notification: bool = False
    ) -> bool:
        """
        Send a message to the configured Telegram chat.
        
        Args:
            text: Message text (supports HTML formatting)
            parse_mode: Telegram parse mode (HTML or Markdown)
            disable_notification: If True, sends silently
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.debug(f"[Telegram] Skipping (not configured): {text[:50]}...")
            return False
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.api_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": text,
                        "parse_mode": parse_mode,
                        "disable_notification": disable_notification,
                    }
                )
                
                if response.status_code == 200:
                    logger.debug(f"[Telegram] ✅ Message sent")
                    return True
                else:
                    logger.error(f"[Telegram] ❌ Failed: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"[Telegram] ❌ Error sending message: {e}")
            return False


# Singleton instance
_notifier: TelegramNotifier | None = None


def get_notifier() -> TelegramNotifier:
    """Get the singleton TelegramNotifier instance."""
    global _notifier
    if _notifier is None:
        _notifier = TelegramNotifier()
    return _notifier


# =============================================================================
# JOB NOTIFICATIONS
# =============================================================================


async def notify_job_started(job_name: str, details: dict[str, Any] | None = None) -> None:
    """
    Notify that a job has started.
    
    Args:
        job_name: Name of the job/task
        details: Optional extra details to include
    """
    notifier = get_notifier()
    
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    message = f"🚀 <b>Job Started</b>\n\n"
    message += f"📋 <b>Task:</b> <code>{job_name}</code>\n"
    message += f"🕐 <b>Time:</b> {timestamp}\n"
    
    if details:
        message += "\n<b>Details:</b>\n"
        for key, value in details.items():
            message += f"  • {key}: {value}\n"
    
    await notifier.send_message(message, disable_notification=True)


async def notify_job_finished(
    job_name: str, 
    result: dict[str, Any] | None = None,
    duration_seconds: float | None = None
) -> None:
    """
    Notify that a job has finished successfully.
    
    Args:
        job_name: Name of the job/task
        result: Job result data
        duration_seconds: How long the job took
    """
    notifier = get_notifier()
    
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    message = f"✅ <b>Job Completed</b>\n\n"
    message += f"📋 <b>Task:</b> <code>{job_name}</code>\n"
    message += f"🕐 <b>Time:</b> {timestamp}\n"
    
    if duration_seconds is not None:
        if duration_seconds >= 60:
            minutes = int(duration_seconds // 60)
            seconds = int(duration_seconds % 60)
            message += f"⏱️ <b>Duration:</b> {minutes}m {seconds}s\n"
        else:
            message += f"⏱️ <b>Duration:</b> {duration_seconds:.1f}s\n"
    
    if result:
        message += "\n<b>Result:</b>\n"
        # Show key metrics
        for key in ["sources_created", "successful", "processed", "unique_events_created", "enriched"]:
            if key in result:
                message += f"  • {key.replace('_', ' ').title()}: {result[key]}\n"
    
    await notifier.send_message(message, disable_notification=True)


async def notify_job_failed(
    job_name: str, 
    error: str,
    details: dict[str, Any] | None = None
) -> None:
    """
    Notify that a job has failed.
    
    Args:
        job_name: Name of the job/task
        error: Error message
        details: Optional extra details
    """
    notifier = get_notifier()
    
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    message = f"❌ <b>Job Failed</b>\n\n"
    message += f"📋 <b>Task:</b> <code>{job_name}</code>\n"
    message += f"🕐 <b>Time:</b> {timestamp}\n"
    message += f"⚠️ <b>Error:</b> {error[:200]}\n"
    
    if details:
        message += "\n<b>Details:</b>\n"
        for key, value in details.items():
            message += f"  • {key}: {value}\n"
    
    # Failed jobs should not be silent
    await notifier.send_message(message, disable_notification=False)


# =============================================================================
# DEATH/UNIQUE EVENT NOTIFICATIONS
# =============================================================================


async def notify_new_death(
    unique_event_id: int,
    title: str | None,
    city: str | None,
    state: str | None,
    event_date: datetime | None,
    victim_count: int | None,
    victims_summary: str | None,
    homicide_type: str | None,
    source_count: int = 1,
) -> None:
    """
    Notify when a new death (UniqueEvent) is added.
    
    Args:
        unique_event_id: Database ID of the UniqueEvent
        title: Event title
        city: City where it occurred
        state: State (abbreviation)
        event_date: Date of the event
        victim_count: Number of victims
        victims_summary: Summary of victims
        homicide_type: Type of homicide
        source_count: Number of sources reporting this event
    """
    notifier = get_notifier()
    
    # Format date
    date_str = event_date.strftime("%d/%m/%Y") if event_date else "Data desconhecida"
    
    # Format location
    location_parts = []
    if city:
        location_parts.append(city)
    if state:
        location_parts.append(state)
    location_str = ", ".join(location_parts) if location_parts else "Local desconhecido"
    
    # Build message
    message = f"💀 <b>Nova Morte Registrada</b>\n\n"
    message += f"📍 <b>Local:</b> {location_str}\n"
    message += f"📅 <b>Data:</b> {date_str}\n"
    
    if victim_count and victim_count > 0:
        message += f"👤 <b>Vítimas:</b> {victim_count}\n"
    
    if homicide_type:
        message += f"🏷️ <b>Tipo:</b> {homicide_type}\n"
    
    if victims_summary:
        # Truncate if too long
        summary = victims_summary[:100] + "..." if len(victims_summary) > 100 else victims_summary
        message += f"\n<b>Vítima(s):</b> {summary}\n"
    
    if title:
        # Truncate title if too long
        display_title = title[:150] + "..." if len(title) > 150 else title
        message += f"\n<i>{display_title}</i>\n"
    
    message += f"\n🔗 ID: <code>{unique_event_id}</code> | {source_count} fonte(s)"
    
    # New deaths are important, don't silence
    await notifier.send_message(message, disable_notification=False)


async def notify_deaths_batch(
    count: int,
    unique_event_ids: list[int],
    cities: list[str] | None = None,
) -> None:
    """
    Notify when multiple deaths are added in a batch operation.
    
    Args:
        count: Number of new UniqueEvents created
        unique_event_ids: List of new UniqueEvent IDs
        cities: List of cities involved (optional)
    """
    if count == 0:
        return
    
    notifier = get_notifier()
    
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    message = f"💀 <b>{count} Nova(s) Morte(s) Registrada(s)</b>\n\n"
    message += f"🕐 <b>Horário:</b> {timestamp}\n"
    
    if cities:
        unique_cities = list(set(cities))[:5]  # Show max 5 cities
        cities_str = ", ".join(unique_cities)
        if len(unique_cities) < len(set(cities)):
            cities_str += f" +{len(set(cities)) - len(unique_cities)} outras"
        message += f"📍 <b>Cidades:</b> {cities_str}\n"
    
    # Show IDs
    if len(unique_event_ids) <= 5:
        ids_str = ", ".join(str(id) for id in unique_event_ids)
    else:
        ids_str = ", ".join(str(id) for id in unique_event_ids[:5]) + f" +{len(unique_event_ids) - 5}"
    
    message += f"\n🔗 IDs: <code>{ids_str}</code>"
    
    await notifier.send_message(message, disable_notification=False)


# =============================================================================
# PIPELINE SUMMARY
# =============================================================================


async def notify_pipeline_summary(
    total_sources: int,
    sources_classified: int,
    sources_downloaded: int,
    raw_events_extracted: int,
    unique_events_created: int,
    duration_seconds: float | None = None,
) -> None:
    """
    Send a summary notification after a full pipeline run.
    """
    notifier = get_notifier()
    
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    message = f"📊 <b>Pipeline Summary</b>\n\n"
    message += f"🕐 <b>Time:</b> {timestamp}\n"
    
    if duration_seconds is not None:
        if duration_seconds >= 60:
            minutes = int(duration_seconds // 60)
            seconds = int(duration_seconds % 60)
            message += f"⏱️ <b>Duration:</b> {minutes}m {seconds}s\n"
        else:
            message += f"⏱️ <b>Duration:</b> {duration_seconds:.1f}s\n"
    
    message += "\n<b>Results:</b>\n"
    message += f"  📰 Sources Found: {total_sources}\n"
    message += f"  ✓ Classified: {sources_classified}\n"
    message += f"  ⬇️ Downloaded: {sources_downloaded}\n"
    message += f"  📄 Extracted: {raw_events_extracted}\n"
    message += f"  💀 New Deaths: {unique_events_created}\n"
    
    # Only notify if there were new deaths
    disable_notification = unique_events_created == 0
    
    await notifier.send_message(message, disable_notification=disable_notification)


# =============================================================================
# TEST / HEALTH CHECK
# =============================================================================


async def send_test_message() -> bool:
    """
    Send a test message to verify the bot configuration.
    
    Returns:
        True if successful, False otherwise
    """
    notifier = get_notifier()
    
    if not notifier.enabled:
        logger.warning("[Telegram] Bot not configured")
        return False
    
    message = (
        "🤖 <b>Arquivo da Violência</b>\n\n"
        "✅ Telegram notifications are working!\n\n"
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    return await notifier.send_message(message)

