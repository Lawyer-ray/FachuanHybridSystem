from django.contrib import admin

from apps.content_ops.models import ContentTask, GeneratedArticle, PodcastEpisode


@admin.register(ContentTask)
class ContentTaskAdmin(admin.ModelAdmin):
    list_display = ["id", "mode", "keyword", "voice", "status", "progress", "created_at"]
    list_filter = ["mode", "status", "voice"]
    search_fields = ["keyword", "source_title", "case_summary"]
    readonly_fields = ["q_task_id", "started_at", "finished_at", "created_at", "updated_at"]


@admin.register(GeneratedArticle)
class GeneratedArticleAdmin(admin.ModelAdmin):
    list_display = ["id", "task", "title", "review_status", "llm_model", "created_at"]
    list_filter = ["review_status"]
    search_fields = ["title", "content"]
    readonly_fields = ["llm_model", "token_usage", "created_at", "updated_at"]


@admin.register(PodcastEpisode)
class PodcastEpisodeAdmin(admin.ModelAdmin):
    list_display = ["id", "task", "voice", "review_status", "duration_seconds", "file_size_bytes", "created_at"]
    list_filter = ["review_status", "voice"]
    readonly_fields = ["audio_file", "duration_seconds", "file_size_bytes", "created_at", "updated_at"]
