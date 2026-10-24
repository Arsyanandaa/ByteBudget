from django.contrib import admin
from .models import (
    Produk,
    Spesifikasi,
    BenchmarkGame,
    Performa,
    PerformaDetail,
    PerformaResolusi,
    Keunggulan,
)


# === Inline untuk Spesifikasi, Benchmark, dll ===
class SpesifikasiInline(admin.TabularInline):
    model = Spesifikasi
    extra = 1


class BenchmarkGameInline(admin.TabularInline):
    model = BenchmarkGame
    extra = 1


class PerformaDetailInline(admin.TabularInline):
    model = PerformaDetail
    extra = 1


class PerformaInline(admin.TabularInline):
    model = Performa
    extra = 1
    # Performa punya child → tampilkan detailnya juga
    show_change_link = True


class PerformaAdmin(admin.ModelAdmin):
    inlines = [PerformaDetailInline]
    list_display = ("name", "produk", "rate", "performance")


class PerformaResolusiInline(admin.TabularInline):
    model = PerformaResolusi
    extra = 1


class KeunggulanInline(admin.TabularInline):
    model = Keunggulan
    extra = 1


# === Produk admin utama ===
class ProdukAdmin(admin.ModelAdmin):
    list_display = ("nama", "kategori", "harga", "kegunaan", "image_path", "slug")
    search_fields = ("nama", "kategori", "kegunaan")
    list_filter = ("kategori", "kegunaan")
    inlines = [
        SpesifikasiInline,
        BenchmarkGameInline,
        PerformaInline,  # ini hanya level pertama
        PerformaResolusiInline,
        KeunggulanInline,
    ]


# === Register admin ===
admin.site.register(Produk, ProdukAdmin)
admin.site.register(Spesifikasi)
admin.site.register(BenchmarkGame)
admin.site.register(Performa, PerformaAdmin)
admin.site.register(PerformaDetail)
admin.site.register(PerformaResolusi)
admin.site.register(Keunggulan)
