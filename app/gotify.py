import httpx
from app.config import config, get_httpx_client_kwargs


async def send_gotify(title: str, message: str, priority: int = 5) -> bool:
    """Send a Gotify notification if configured."""
    if not config.gotify.url or not config.gotify.token:
        return False

    try:
        url = f"{config.gotify.url.rstrip('/')}/message"
        async with httpx.AsyncClient(timeout=10, **get_httpx_client_kwargs()) as client:
            resp = await client.post(
                url,
                headers={"X-Gotify-Key": config.gotify.token},
                data={"title": title, "message": message, "priority": priority},
            )
            return resp.status_code == 200
    except Exception:
        return False


async def test_gotify_connection() -> tuple[bool, str]:
    """Test Gotify connection and send a test notification."""
    if not config.gotify.url or not config.gotify.token:
        return False, "Gotify URL or token not configured"

    try:
        url = f"{config.gotify.url.rstrip('/')}/message"
        async with httpx.AsyncClient(timeout=10, **get_httpx_client_kwargs()) as client:
            resp = await client.post(
                url,
                headers={"X-Gotify-Key": config.gotify.token},
                data={
                    "title": "Music Organizer - Test",
                    "message": "Это тестовое уведомление от Music Organizer. Если вы видите это сообщение - уведомления работают корректно!",
                    "priority": 5,
                },
            )
            if resp.status_code == 200:
                return True, "Notification sent successfully!"
            else:
                return False, f"HTTP {resp.status_code}: {resp.text}"
    except httpx.ConnectError as e:
        return False, f"Connection error: {str(e)}"
    except Exception as e:
        return False, f"Error: {str(e)}"
