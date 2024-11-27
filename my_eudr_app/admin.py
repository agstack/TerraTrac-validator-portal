from django.contrib import admin

from eudr_backend.models import EUDRCollectionSiteModel, EUDRFarmBackupModel, EUDRSharedMapAccessCodeModel, EUDRUploadedFilesModel, EUDRUserModel, WhispAPISetting, EUDRFarmModel

admin.site.register(
    [
        EUDRUserModel,
        EUDRFarmModel,
        EUDRUploadedFilesModel,
        EUDRCollectionSiteModel,
        EUDRFarmBackupModel,
        EUDRSharedMapAccessCodeModel,
        WhispAPISetting
    ]
)
