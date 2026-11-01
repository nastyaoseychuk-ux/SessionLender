from django.contrib import admin

from .models import (
    AuditEvent,
    Chat,
    ChatAttachment,
    ChatMembership,
    ChatMessage,
    Comment,
    Post,
    PostLike,
    Profile,
    Room,
    TemporaryCode,
)

admin.site.site_header = 'SessionLender — керування'
admin.site.site_title = 'SessionLender'
admin.site.index_title = 'Панель керування'


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('nickname', 'user', 'role', 'is_banned', 'last_seen')
    list_filter = ('role', 'is_banned')
    search_fields = ('nickname', 'user__username')
    list_editable = ('role', 'is_banned')


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by', 'created_at')
    search_fields = ('name', 'members__username')
    filter_horizontal = ('members',)
    readonly_fields = ('invite_token',)
    date_hierarchy = 'created_at'


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('author', 'room', 'caption', 'created_at')
    list_filter = ('room', 'created_at')
    search_fields = ('author__username', 'caption')
    date_hierarchy = 'created_at'


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('author', 'post', 'text', 'created_at')
    search_fields = ('author__username', 'text')
    date_hierarchy = 'created_at'


@admin.register(PostLike)
class PostLikeAdmin(admin.ModelAdmin):
    list_display = ('user', 'post', 'created_at')
    search_fields = ('user__username', 'post__caption')
    date_hierarchy = 'created_at'


class ChatMembershipInline(admin.TabularInline):
    model = ChatMembership
    extra = 0
    autocomplete_fields = ('user',)


@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ('participants_key', 'created_at', 'updated_at')
    search_fields = ('participants_key',)
    inlines = (ChatMembershipInline,)
    date_hierarchy = 'created_at'


@admin.register(ChatMembership)
class ChatMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'chat', 'last_read_at')
    search_fields = ('user__username', 'chat__participants_key')


class ChatAttachmentInline(admin.TabularInline):
    model = ChatAttachment
    extra = 0
    fields = ('kind', 'original_name', 'content_type', 'size', 'duration_seconds')
    readonly_fields = ('kind', 'original_name', 'content_type', 'size', 'duration_seconds')
    can_delete = False


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('author', 'chat', 'preview', 'created_at')
    search_fields = ('author__username', 'text')
    date_hierarchy = 'created_at'
    inlines = (ChatAttachmentInline,)


@admin.register(ChatAttachment)
class ChatAttachmentAdmin(admin.ModelAdmin):
    list_display = ('original_name', 'kind', 'message', 'size', 'created_at')
    list_filter = ('kind', 'created_at')
    search_fields = ('original_name', 'message__author__username')
    exclude = ('file',)
    readonly_fields = ('message', 'kind', 'original_name', 'content_type', 'size', 'duration_seconds', 'created_at')
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False


@admin.register(TemporaryCode)
class TemporaryCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'user', 'created_at', 'expires_at', 'used')
    list_filter = ('used',)
    search_fields = ('code', 'user__username')
    readonly_fields = ('code', 'created_at')


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'action', 'actor', 'target', 'ip_address')
    list_filter = ('action', 'created_at')
    search_fields = ('actor__username', 'target', 'detail', 'ip_address')
    readonly_fields = ('actor', 'action', 'target', 'detail', 'ip_address', 'created_at')
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
