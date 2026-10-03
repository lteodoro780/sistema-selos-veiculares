from django.contrib import admin

from .models import PlateCorrectionRule, PlatePassage


@admin.register(PlatePassage)
class PlatePassageAdmin(admin.ModelAdmin):
    list_display = (
        "captured_at", "raw_plate", "plate", "plate_format", "match_method",
        "movement", "vehicle", "person", "camera_name", "manual_corrected_by",
    )
    list_filter = (
        "movement", "plate_format", "match_method", "matched_automatically", "camera_name",
    )
    search_fields = (
        "raw_plate", "plate", "vehicle__placa", "person__nome_preferido",
        "person__first_name", "person__last_name",
    )
    readonly_fields = ("created_at", "manual_corrected_at", "manual_corrected_by")


@admin.register(PlateCorrectionRule)
class PlateCorrectionRuleAdmin(admin.ModelAdmin):
    list_display = ("raw_plate", "corrected_plate", "camera_ip", "active", "created_by", "updated_at")
    list_filter = ("active", "camera_ip")
    search_fields = ("raw_plate", "corrected_plate", "camera_ip")
    readonly_fields = ("created_at", "updated_at")
