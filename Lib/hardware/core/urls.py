from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("processor/", views.processor, name="processor"),
    path(
        "details/processor/<slug:slug>/",
        views.processor_detail,
        name="processor_detail",
    ),
    path("ram/", views.ram, name="ram"),
    path("vga/", views.vga, name="vga"),
    path("psu/", views.psu, name="psu"),
    path("ssd/", views.ssd, name="ssd"),
    path('rekomendasi/', views.rekomendasi_view, name='rekomendasi'),
    path('rekomendasi/pc/', views.rekomendasi_pc_view, name='rekomendasi_pc'),
    path('rekomendasi/laptop/', views.rekomendasi_laptop_view, name='rekomendasi_laptop'),
    path('run-scraper/', views.run_scraper, name='run_scraper'),
    path('download-excel/', views.download_excel, name='download_excel'),
    path("pelajarilebihlanjut/", views.pelajarilebihlanjut, name="pelajarilebihlanjut"),
    path("loginpage/", views.loginpage, name="loginpage"),
    path('local-image/', views.serve_local_image, name='serve_local_image'),
]
