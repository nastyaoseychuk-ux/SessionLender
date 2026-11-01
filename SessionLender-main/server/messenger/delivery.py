"""A relay outage must not undo or hide an already committed database write."""

import asyncio
import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def relay(events):
    try:
        layer = get_channel_layer()
        if layer is None:
            return

        async def send():
            await asyncio.wait_for(
                asyncio.gather(
                    *(layer.group_send(group, event) for group, event in events)
                ),
                timeout=1.5,
            )

        async_to_sync(send)()
    except Exception:
        logger.exception("Realtime relay failed; database data remains committed.")
