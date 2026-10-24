from django.db import models
from django.utils.text import slugify


class Produk(models.Model):
    nama = models.CharField(max_length=100)
    harga = models.DecimalField(max_digits=10, decimal_places=2)
    kategori = models.CharField(max_length=50, default="Umum")  # default kategori
    deskripsi = models.TextField(default="Belum ada deskripsi")  # default deskripsi
    kegunaan = models.CharField(max_length=100, default="Umum")  # default kegunaan
    image_path = models.CharField(max_length=255, default="images/default.png")
    slug = models.SlugField(unique=True, blank=True, null=True)
    # 👉 Tambahan link marketplace
    link_tokopedia = models.URLField(
        max_length=255, default="https://www.tokopedia.com/", blank=True, null=True
    )
    link_shopee = models.URLField(
        max_length=255, default="https://shopee.co.id/", blank=True, null=True
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.nama)
            slug = base_slug
            counter = 1
            while Produk.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nama} ({self.kategori})"


# Benchmark game
class BenchmarkGame(models.Model):
    produk = models.ForeignKey(
        Produk, on_delete=models.CASCADE, related_name="benchmarks"
    )
    name = models.CharField(max_length=100)
    image = models.CharField(max_length=255)
    keterangan = models.CharField(max_length=100)
    result = models.IntegerField(default=0)  # scale 0-100

    def __str__(self):
        return f"{self.name} - {self.produk.nama}"


class Performa(models.Model):
    produk = models.ForeignKey(
        Produk, on_delete=models.CASCADE, related_name="performas"
    )
    icon = models.CharField(max_length=255)
    name = models.CharField(max_length=100)
    image = models.CharField(max_length=255)
    rate = models.CharField(max_length=50)
    performance = models.IntegerField(default=0)  # scale 0-100

    def __str__(self):
        return f"{self.name} - {self.produk.nama}"


class PerformaDetail(models.Model):
    performa = models.ForeignKey(
        Performa, on_delete=models.CASCADE, related_name="details"
    )
    name = models.CharField(max_length=100)
    detail = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.name} - {self.performa.name}"


# Performa multi resolusi
class PerformaResolusi(models.Model):
    produk = models.ForeignKey(
        Produk, on_delete=models.CASCADE, related_name="performa_resolusi"
    )
    name = models.CharField(max_length=50)  # contoh: 1080p
    deskripsi = models.CharField(max_length=255)
    detail = models.CharField(max_length=100)
    rate = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.name} - {self.produk.nama}"


# Keunggulan
class Keunggulan(models.Model):
    produk = models.ForeignKey(
        Produk, on_delete=models.CASCADE, related_name="keunggulan"
    )
    icon = models.CharField(max_length=255)
    name = models.CharField(max_length=100)
    deskripsi = models.TextField()

    def __str__(self):
        return f"{self.name} - {self.produk.nama}"


class Spesifikasi(models.Model):
    nama = models.CharField(max_length=100)
    detail = models.TextField()
    produk = models.ForeignKey(
        Produk,
        on_delete=models.CASCADE,  # kalau produk dihapus, spesifikasi ikut terhapus
        related_name="spesifikasi",  # supaya bisa diakses lewat produk.spesifikasi.all()
    )

    def __str__(self):
        return f"{self.nama} - {self.produk.nama}"
