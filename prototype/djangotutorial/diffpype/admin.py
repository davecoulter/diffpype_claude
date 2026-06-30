from django.contrib import admin

# Register your models here.
from diffpype.models import *

admin.site.register(Band)
admin.site.register(Instrument)
admin.site.register(Project)
admin.site.register(Epoch)
admin.site.register(Lvl2Cal)
admin.site.register(Lvl2CalStatus)
# admin.site.register(Lvl2Cal_Lvl3Mosaic)
admin.site.register(Lvl2Cal_Epoch)
admin.site.register(Image)
admin.site.register(Lvl3DiffStatus)
admin.site.register(Lvl3MosaicStatus)
admin.site.register(Tile)
admin.site.register(Lvl3Mosaic)
admin.site.register(Lvl3Diff)
# admin.site.register(PipeStep)
# admin.site.register(PipeStepParam)
# admin.site.register(PipeStepStatus)
# admin.site.register(RunConfigStatus)
# admin.site.register(RunConfig)
# admin.site.register(PipeStepStepStatus)
# admin.site.register(RunConfigPipeStep)
# admin.site.register(TileImage)
admin.site.register(TileLvl2Cal)