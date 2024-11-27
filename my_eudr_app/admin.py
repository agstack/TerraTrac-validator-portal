from django.contrib import admin

from eudr_backend.models import EUDRCollectionSiteModel, EUDRFarmBackupModel, EUDRSharedMapAccessCodeModel, EUDRUploadedFilesModel,  WhispAPISetting, EUDRFarmModel

admin.site.register(
    [
        EUDRFarmModel,
        EUDRUploadedFilesModel,
        EUDRCollectionSiteModel,
        EUDRFarmBackupModel,
        EUDRSharedMapAccessCodeModel,
        WhispAPISetting
    ]
)
