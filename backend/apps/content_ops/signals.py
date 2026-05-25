from __future__ import annotations

import logging

from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.content_ops.models import PodcastEpisode

logger = logging.getLogger("apps.content_ops")


@receiver(post_delete, sender=PodcastEpisode)
def delete_episode_audio_file(sender: type, instance: PodcastEpisode, **kwargs: object) -> None:
    """Delete the physical audio file when a PodcastEpisode is deleted."""
    if instance.audio_file:
        try:
            instance.audio_file.delete(save=False)
        except Exception:
            logger.warning("Failed to delete audio file for episode %s", instance.pk, exc_info=True)
