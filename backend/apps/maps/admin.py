from django.contrib import admin

from .models import (
    Country,
    Province,
    Coast,
    ProvinceAdjacency,
)


admin.site.register(Country)
admin.site.register(Province)
admin.site.register(Coast)
admin.site.register(ProvinceAdjacency)