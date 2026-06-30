from django.db import models


class Band(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=45)
    central_lambda = models.FloatField()

    class Meta:
        db_table = 'Band'
        verbose_name_plural = "Bands" # Good practice for plural names

    def __str__(self):
        return self.name

class Instrument(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=45)

    class Meta:
        db_table = 'Instrument'
        verbose_name_plural = "Instruments"

    def __str__(self):
        return self.name

class Project(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=128)

    class Meta:
        db_table = 'Project'
        verbose_name_plural = "Projects"

    def __str__(self):
        return self.name if self.name else f"Project {self.id}"


class Lvl2CalStatus(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=45)

    class Meta:
        db_table = 'Lvl2Cal_Status'
        verbose_name_plural = "Lvl2 Cal Statuses"

    def __str__(self):
        return self.name

class Image(models.Model):
    id = models.AutoField(primary_key=True)
    instrument = models.ForeignKey(Instrument, on_delete=models.CASCADE)
    band = models.ForeignKey(Band, on_delete=models.CASCADE)
    ra = models.FloatField()
    decl = models.FloatField()
    obs_start = models.DateTimeField()
    mjd_avg = models.FloatField(null=True)
    exp_time = models.FloatField()
    target_name = models.CharField(max_length=128)
    base_filename = models.CharField(max_length=255, unique=True)

    class Meta:
        db_table = 'Image'
        verbose_name_plural = "Images"

    def __str__(self):
        return self.target_name

class Lvl2Cal(models.Model):
    id = models.AutoField(primary_key=True)
    image = models.OneToOneField(Image, on_delete=models.CASCADE)
    current_file_ext = models.CharField(max_length=128)
    lvl2cal_status = models.ForeignKey(Lvl2CalStatus, on_delete=models.CASCADE)
    poly = models.TextField(null=True, blank=True)
    plate_scale = models.FloatField()

    class Meta:
        db_table = 'Lvl2Cal'
        verbose_name_plural = "Lvl2 Cals"

    def __str__(self):
        return "Lvl2 Cal: %s" % self.image.base_filename

class Lvl3DiffStatus(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=45, null=True, blank=True)

    class Meta:
        db_table = 'Lvl3Diff_Status'
        verbose_name_plural = "Lvl3 Diff Statuses"

    def __str__(self):
        return self.name if self.name else f"Lvl3 Diff Status {self.id}"

class Lvl3MosaicStatus(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=45, null=True, blank=True)

    class Meta:
        db_table = 'Lvl3Mosaic_Status'
        verbose_name_plural = "Lvl3 Mosaic Statuses"

    def __str__(self):
        return self.name if self.name else f"Lvl3 Mosaic Status {self.id}"

class Tile(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=45)
    ra = models.FloatField()
    decl = models.FloatField()
    delta_ra = models.FloatField()
    delta_decl = models.FloatField()
    coord_sys = models.IntegerField() # Assuming INT translates to IntegerField
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    poly = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'Tile'
        verbose_name_plural = "Tiles"

    def __str__(self):
        return self.name

class Epoch(models.Model):
    id = models.AutoField(primary_key=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    start_mjd = models.FloatField(null=True)
    end_mjd = models.FloatField(null=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    tile = models.ForeignKey(Tile, on_delete=models.CASCADE)
    band = models.ForeignKey(Band, on_delete=models.CASCADE)

    class Meta:
        db_table = 'Epoch'
        verbose_name_plural = "Epochs"

    def __str__(self):
        return f"Epoch {self.id} for Project {self.project.name}"

class Lvl3Mosaic(models.Model):
    id = models.AutoField(primary_key=True)
    tile = models.ForeignKey(Tile, on_delete=models.CASCADE)
    epoch = models.ForeignKey(Epoch, on_delete=models.CASCADE)
    band = models.ForeignKey(Band, on_delete=models.CASCADE)
    instrument = models.ForeignKey(Instrument, on_delete=models.CASCADE)
    target_plate_scale = models.FloatField()
    filename = models.CharField(max_length=128, unique=True)
    lvl3mosaic_status = models.ForeignKey(Lvl3MosaicStatus, on_delete=models.CASCADE)
    # poly = models.TextField(null=True, blank=True)
    moc_str = models.TextField(null=True, blank=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)

    class Meta:
        db_table = 'Lvl3Mosaic'
        verbose_name_plural = "Lvl3 Mosaics"

        unique_together = 'instrument', 'tile', 'epoch', 'band', 'project'

    def __str__(self):
        return self.filename

# class Lvl2Cal_Lvl3Mosaic(models.Model):
#     id = models.AutoField(primary_key=True)
#     lvl2cal = models.ForeignKey(Lvl2Cal, on_delete=models.CASCADE)
#     lvl3mosaic = models.ForeignKey(Lvl3Mosaic, on_delete=models.CASCADE)
#
#     class Meta:
#         db_table = 'Lvl2Cal_Lvl3Mosaic'
#         verbose_name_plural = "Lvl2 Cals in Lvl3 Mosaics"
#
#     def __str__(self):
#         return f"Lvl3 {self.lvl3mosaic.filename} - Lvl2 {self.lvl2cal.image.base_filename}"
class Lvl2Cal_Epoch(models.Model):
    id = models.AutoField(primary_key=True)
    lvl2cal = models.ForeignKey(Lvl2Cal, on_delete=models.CASCADE)
    epoch = models.ForeignKey(Epoch, on_delete=models.CASCADE)

    class Meta:
        db_table = 'Lvl2Cal_Epoch'
        verbose_name_plural = "Lvl2 Cals in Epoch"

    def __str__(self):
        return f"Epoch ID {self.epoch.id} - Lvl2 {self.lvl2cal.image.base_filename}"

class Lvl3Diff(models.Model):
    id = models.AutoField(primary_key=True)
    lvl3_ref = models.ForeignKey(Lvl3Mosaic, on_delete=models.CASCADE, related_name='diff_as_reference')
    lvl3_sci = models.ForeignKey(Lvl3Mosaic, on_delete=models.CASCADE, related_name='diff_as_science')
    filename = models.CharField(max_length=128)
    lvl3diff_status = models.ForeignKey(Lvl3DiffStatus, on_delete=models.CASCADE)

    class Meta:
        db_table = 'Lvl3Diff'
        verbose_name_plural = "Lvl3 Diffs"

    def __str__(self):
        return self.filename

# class PipeStep(models.Model):
#     id = models.AutoField(primary_key=True)
#     name = models.CharField(max_length=45)
#     depends_on = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='dependents')
#
#     class Meta:
#         db_table = 'PipeStep'
#         verbose_name_plural = "Pipe Steps"
#
#     def __str__(self):
#         return self.name
#
# class PipeStepParam(models.Model):
#     id = models.AutoField(primary_key=True)
#     pipestep = models.ForeignKey(PipeStep, on_delete=models.CASCADE)
#     name = models.CharField(max_length=45)
#     key = models.CharField(max_length=128, null=True, blank=True)
#     value = models.CharField(max_length=128, null=True, blank=True)
#
#     class Meta:
#         db_table = 'PipeStep_Param'
#         verbose_name_plural = "Pipe Step Params"
#
#     def __str__(self):
#         return f"{self.pipestep.name} - {self.name}"
#
# class PipeStepStatus(models.Model):
#     id = models.AutoField(primary_key=True)
#     name = models.CharField(max_length=45)
#
#     class Meta:
#         db_table = 'PipeStep_Status'
#         verbose_name_plural = "Pipe Step Statuses"
#
#     def __str__(self):
#         return self.name
#
# class RunConfigStatus(models.Model):
#     id = models.AutoField(primary_key=True)
#     name = models.CharField(max_length=45)
#
#     class Meta:
#         db_table = 'RunConfig_Status'
#         verbose_name_plural = "Run Config Statuses"
#
#     def __str__(self):
#         return self.name
#
# class RunConfig(models.Model):
#     id = models.AutoField(primary_key=True)
#     project = models.ForeignKey(Project, on_delete=models.CASCADE)
#     instrument = models.ForeignKey(Instrument, on_delete=models.SET_NULL, null=True, blank=True)
#     band = models.ForeignKey(Band, on_delete=models.SET_NULL, null=True, blank=True)
#     tile = models.ForeignKey(Tile, on_delete=models.SET_NULL, null=True, blank=True)
#     lvl3_mosaic = models.ForeignKey(Lvl3Mosaic, on_delete=models.SET_NULL, null=True, blank=True)
#     lvl3_diff = models.ForeignKey(Lvl3Diff, on_delete=models.SET_NULL, null=True, blank=True)
#     image = models.ForeignKey(Image, on_delete=models.SET_NULL, null=True, blank=True)
#     run_status = models.ForeignKey(RunConfigStatus, on_delete=models.CASCADE)
#
#     class Meta:
#         db_table = 'RunConfig'
#         verbose_name_plural = "Run Configs"
#
#     def __str__(self):
#         return f"RunConfig {self.id} for Project {self.project.name}"
#
# class PipeStepStepStatus(models.Model):
#     id = models.AutoField(primary_key=True)
#     pipestep = models.ForeignKey(PipeStep, on_delete=models.CASCADE)
#     step_status = models.ForeignKey(PipeStepStatus, on_delete=models.CASCADE)
#     run_config = models.ForeignKey(RunConfig, on_delete=models.CASCADE)
#
#     class Meta:
#         db_table = 'PipeStep_StepStatus'
#         verbose_name_plural = "Pipe Step Step Statuses"
#
#     def __str__(self):
#         return f"{self.pipestep.name} - {self.step_status.name} ({self.run_config.id})"
#
# class RunConfigPipeStep(models.Model):
#     id = models.AutoField(primary_key=True)
#     run_config = models.ForeignKey(RunConfig, on_delete=models.CASCADE)
#     pipestep = models.ForeignKey(PipeStep, on_delete=models.CASCADE)
#
#     class Meta:
#         db_table = 'RunConfig_PipeStep'
#         verbose_name_plural = "Run Config Pipe Steps"
#
#     def __str__(self):
#         return f"RunConfig {self.run_config.id} - PipeStep {self.pipestep.name}"

# class TileImage(models.Model):
#     id = models.AutoField(primary_key=True)
#     tile = models.ForeignKey(Tile, on_delete=models.CASCADE)
#     image = models.ForeignKey(Image, on_delete=models.CASCADE)
#
#     class Meta:
#         db_table = 'Tile_Image'
#         verbose_name_plural = "Tile Images"
#
#     def __str__(self):
#         return f"Tile {self.tile.name} - Image {self.image.target_name}"

class TileLvl2Cal(models.Model):
    id = models.AutoField(primary_key=True)
    tile = models.ForeignKey(Tile, on_delete=models.CASCADE)
    lvl2cal = models.ForeignKey(Lvl2Cal, on_delete=models.CASCADE)

    class Meta:
        db_table = 'Tile_Lvl2Cal'
        verbose_name_plural = "Tile - Lvl2 Cals"

    def __str__(self):
        return f"Tile {self.tile.name} - Lvl2Cal {self.lvl2cal.image.base_filename}"