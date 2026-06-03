import logging
import apprise

logger = logging.getLogger(__name__)

async def send_notification(title: str, body: str, notification_urls: str | None) -> bool:
    """Send a notification asynchronously using Apprise.
    
    Args:
        title: Notification title
        body: Notification body/message
        notification_urls: Comma or space-separated Apprise URLs
        
    Returns:
        True if all notifications sent successfully, False otherwise
    """
    if not notification_urls:
        return False
        
    # Apprise urls can be comma or space separated. We'll replace commas with spaces and split.
    urls = [url.strip() for url in notification_urls.replace(',', ' ').split() if url.strip()]
    if not urls:
        return False
        
    try:
        apobj = apprise.AsyncApprise()
        for url in urls:
            apobj.add(url)
            
        success = await apobj.async_notify(
            title=title,
            body=body,
        )
        if not success:
            logger.warning("One or more notifications failed to send via Apprise.")
        return success
    except Exception as e:
        logger.error(f"Exception while sending notification: {e}")
        return False
