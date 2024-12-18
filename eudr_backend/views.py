import json
from django.http import HttpResponse
from django.utils import timezone
import pandas as pd
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
import boto3
from shapely import Polygon
from eudr_backend import settings
from eudr_backend.async_tasks import async_create_farm_data
from eudr_backend.models import EUDRCollectionSiteModel, EUDRFarmBackupModel, EUDRSharedMapAccessCodeModel, EUDRFarmModel, EUDRUploadedFilesModel
from datetime import timedelta
from eudr_backend.tasks import update_geoid
from eudr_backend.util_classes import IsSuperUser
from eudr_backend.utils import extract_data_from_file, flatten_multipolygon_coordinates, generate_access_code, handle_failed_file_entry, store_failed_file_in_s3, transform_csv_to_json, transform_db_data_to_geojson
from eudr_backend.validators import validate_csv, validate_geojson
from .serializers import (
    EUDRCollectionSiteModelSerializer,
    EUDRFarmBackupModelSerializer,
    EUDRFarmModelSerializer,
    EUDRUploadedFilesModelSerializer,
    EUDRUserModelSerializer,
)
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication


@swagger_auto_schema(
    method="post",
    operation_summary="Create a new user",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "first_name": openapi.Schema(type=openapi.TYPE_STRING),
            "last_name": openapi.Schema(type=openapi.TYPE_STRING),
            "username": openapi.Schema(type=openapi.TYPE_STRING),
            "password": openapi.Schema(type=openapi.TYPE_STRING),
            "email": openapi.Schema(type=openapi.TYPE_STRING),
        },
        default={
            "first_name": "John",
            "last_name": "Doe",
            "username": "johndoe",
            "password": "password",
            "email": "johndoe@gmail.com",
        },
    ),
    responses={
        201: openapi.Response(
            description="User created successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "first_name": openapi.Schema(type=openapi.TYPE_STRING),
                    "last_name": openapi.Schema(type=openapi.TYPE_STRING),
                    "username": openapi.Schema(type=openapi.TYPE_STRING),
                    "is_active": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    "date_joined": openapi.Schema(type=openapi.TYPE_STRING),
                    "is_staff": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    "is_superuser": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                },
            ),
            examples={
                "application/json": {
                    "id": 1,
                    "first_name": "John",
                    "last_name": "Doe",
                    "username": "johndoe",
                    "is_active": True,
                    "date_joined": "2021-09-09T12:00:00",
                    "is_staff": False,
                    "is_superuser": False,
                },
            },
        ),
        400: openapi.Response(
            description="Bad request",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "first_name": openapi.Schema(type=openapi.TYPE_OBJECT),
                    "last_name": openapi.Schema(type=openapi.TYPE_OBJECT),
                    "username": openapi.Schema(type=openapi.TYPE_OBJECT),
                    "password": openapi.Schema(type=openapi.TYPE_OBJECT),
                    "email": openapi.Schema(type=openapi.TYPE_OBJECT),
                },
            ),
            examples={
                "application/json": {
                    "first_name": ["This field is required."],
                    "last_name": ["This field is required."],
                    "username": ["This field is required."],
                    "password": ["This field is required."],
                    "email": ["This field is required."],
                },
            },
        ),
    },
    tags=["User Management"]
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_user(request):
    serializer = EUDRUserModelSerializer(data=request.data)

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method="get",
    operation_summary="Retrieve all users",
    responses={
        200: openapi.Response(
            description="Users retrieved successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "first_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "last_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "username": openapi.Schema(type=openapi.TYPE_STRING),
                        "is_active": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        "date_joined": openapi.Schema(type=openapi.TYPE_STRING),
                        "is_staff": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                        "is_superuser": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    },
                ),
            ),
            examples={
                "application/json": [
                    {
                        "id": 1,
                        "first_name": "John",
                        "last_name": "Doe",
                        "username": "johndoe",
                        "is_active": True,
                        "date_joined": "2021-09-09T12:00:00",
                        "is_staff": False,
                        "is_superuser": False,
                    },
                    {
                        "id": 2,
                        "first_name": "Jane",
                        "last_name": "Doe",
                        "username": "janedoe",
                        "is_active": True,
                        "date_joined": "2021-09-09T12:00:00",
                        "is_staff": False,
                        "is_superuser": False,
                    },
                ],
            },
        ),
    },
    tags=["User Management"]
)
@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsSuperUser])
def retrieve_users(request):
    data = User.objects.all().order_by("-date_joined")
    serializer = EUDRUserModelSerializer(data, many=True)
    return Response(serializer.data)


@swagger_auto_schema(
    method="get",
    operation_summary="Retrieve a user",
    responses={
        200: openapi.Response(
            description="User retrieved successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "first_name": openapi.Schema(type=openapi.TYPE_STRING),
                    "last_name": openapi.Schema(type=openapi.TYPE_STRING),
                    "username": openapi.Schema(type=openapi.TYPE_STRING),
                    "is_active": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    "date_joined": openapi.Schema(type=openapi.TYPE_STRING),
                    "is_staff": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    "is_superuser": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                },
            ),
            examples={
                "application/json": {
                    "id": 1,
                    "first_name": "John",
                    "last_name": "Doe",
                    "username": "johndoe",
                    "is_active": True,
                    "date_joined": "2021-09-09T12:00:00",
                    "is_staff": False,
                    "is_superuser": False,
                },
            },
        ),
        400: openapi.Response(
            description="Bad request",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
            examples={
                "application/json": {
                    "error": "User does not exist",
                },
            },
        ),
    },
    tags=["User Management"]
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retrieve_user(request, pk):
    try:
        user = User.objects.get(id=pk)
        serializer = EUDRUserModelSerializer(user, many=False)
        return Response(serializer.data)
    except User.DoesNotExist:
        return Response({'error': 'User does not exist'}, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method="put",
    operation_summary="Update a user",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "first_name": openapi.Schema(type=openapi.TYPE_STRING),
            "last_name": openapi.Schema(type=openapi.TYPE_STRING),
            "username": openapi.Schema(type=openapi.TYPE_STRING),
            "email": openapi.Schema(type=openapi.TYPE_STRING),
        },
        default={
            "first_name": "John",
            "last_name": "Doe",
            "username": "johndoe",
            "email": "johndoes@gmail.com",
        },
    ),
    responses={
        200: openapi.Response(
            description="User updated successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "first_name": openapi.Schema(type=openapi.TYPE_STRING),
                    "last_name": openapi.Schema(type=openapi.TYPE_STRING),
                    "username": openapi.Schema(type=openapi.TYPE_STRING),
                    "is_active": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    "date_joined": openapi.Schema(type=openapi.TYPE_STRING),
                    "is_staff": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    "is_superuser": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                },
            ),
            examples={
                "application/json": {
                    "id": 1,
                    "first_name": "John",
                    "last_name": "Doe",
                    "username": "johndoe",
                    "is_active": True,
                    "date_joined": "2021-09-09T12:00:00",
                    "is_staff": False,
                    "is_superuser": False,
                },
            },
        ),
        400: openapi.Response(
            description="Bad request",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "first_name": openapi.Schema(type=openapi.TYPE_OBJECT),
                    "last_name": openapi.Schema(type=openapi.TYPE_OBJECT),
                    "username": openapi.Schema(type=openapi.TYPE_OBJECT),
                    "email": openapi.Schema(type=openapi.TYPE_OBJECT),
                },
            ),
            examples={
                "application/json": {
                    "first_name": ["This field is required."],
                    "last_name": ["This field is required."],
                    "username": ["This field is required."],
                    "email": ["This field is required."],
                },
            },
        ),
        403: openapi.Response(
            description="Forbidden",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
            examples={
                "application/json": {
                    "error": "You do not have permission to perform this action",
                },
            },
        ),
    },
    tags=["User Management"]
)
@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_user(request, pk):
    try:
        user = User.objects.get(id=pk)

        # only superusers or the user themselves can update their details
        if not request.user.is_superuser and request.user.id != user.id:
            return Response({'error': 'You do not have permission to perform this action'}, status=status.HTTP_403_FORBIDDEN)

        if 'username' not in request.data:
            request.data['username'] = user.username

        serializer = EUDRUserModelSerializer(instance=user, data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except User.DoesNotExist:
        return Response({'error': 'User does not exist'}, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method="delete",
    operation_summary="Delete a user",
    responses={
        204: openapi.Response(
            description="User deleted successfully",
        ),
        403: openapi.Response(
            description="Forbidden",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
            examples={
                "application/json": {
                    "error": "You do not have permission to perform this action",
                },
            },
        ),
        404: openapi.Response(
            description="Not found",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
            examples={
                "application/json": {
                    "error": "User does not exist",
                },
            },
        ),
    },
    tags=["User Management"]
)
@api_view(["DELETE"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsSuperUser])
def delete_user(request, pk):
    if not request.user.is_superuser:
        return Response({'error': 'You do not have permission to perform this action'}, status=status.HTTP_403_FORBIDDEN)

    try:
        user = User.objects.get(id=pk)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    except User.DoesNotExist:
        return Response({'error': 'User does not exist'}, status=status.HTTP_404_NOT_FOUND)


@swagger_auto_schema(
    method="post",
    operation_summary="Create farm data",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "format": openapi.Schema(type=openapi.TYPE_STRING),
            "file": openapi.Schema(type=openapi.TYPE_FILE),
            "data": openapi.Schema(type=openapi.TYPE_OBJECT),
        },
        default={
            "format": "geojson",
            "data": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [
                                        -88.89236191114519,
                                        13.755668940781419
                                    ],
                                    [
                                        -88.8926974442857,
                                        13.755104779826965
                                    ],
                                    [
                                        -88.89247298437891,
                                        13.75509578920503
                                    ],
                                    [
                                        -88.89219298771054,
                                        13.755071065061344
                                    ],
                                    [
                                        -88.89218141761236,
                                        13.755028359593808
                                    ],
                                    [
                                        -88.89216753349395,
                                        13.754920472063688
                                    ],
                                    [
                                        -88.89206571662912,
                                        13.754913729091172
                                    ],
                                    [
                                        -88.89202869231488,
                                        13.754877766569706
                                    ],
                                    [
                                        -88.89192224741056,
                                        13.75484854701638
                                    ],
                                    [
                                        -88.89188753711551,
                                        13.754882261884418
                                    ],
                                    [
                                        -88.89179729034885,
                                        13.754853042331618
                                    ],
                                    [
                                        -88.89177877819144,
                                        13.75476763131023
                                    ],
                                    [
                                        -88.89175100995566,
                                        13.7547631359933
                                    ],
                                    [
                                        -88.89173249779824,
                                        13.754821575117731
                                    ],
                                    [
                                        -88.89161216877602,
                                        13.754808089166758
                                    ],
                                    [
                                        -88.891538120147,
                                        13.75478786023993
                                    ],
                                    [
                                        -88.89236191114519,
                                        13.755668940781419
                                    ]
                                ]
                            ]
                        },
                        "properties": {
                            "farmer_name": "John Doe",
                            "farm_size": 4,
                            "collection_site": "Site A",
                            "farm_village": "Village A",
                            "farm_district": "District A",
                            "latitude": 0,
                            "longitude": 0,
                        },
                    }
                ]
            },
        },
    ),
    responses={
        201: openapi.Response(
            description="File/data processed successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "message": openapi.Schema(type=openapi.TYPE_STRING),
                    "file_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                },
            ),
            examples={
                "application/json": {
                    "message": "File/data processed successfully",
                    "file_id": 1,
                },
            },
        ),
        400: openapi.Response(
            description="Bad request",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
            examples={
                "application/json": {
                    "error": "Either a file or data is required",
                },
            },
        ),
    },
    tags=["Farm Data Management"]
)
@api_view(["POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def create_farm_data(request):
    data_format = request.data.get('format', "geojson") if isinstance(
        request.data, dict) else "geojson"
    raw_data = json.loads(request.data) if isinstance(
        request.data, str) else request.data
    raw_data = raw_data.get('data') if 'data' in raw_data else raw_data
    file = request.FILES.get('file')

    # Validate that either file or raw_data is provided
    if not file and not raw_data:
        return Response({'error': 'Either a file or data is required'}, status=status.HTTP_400_BAD_REQUEST)

    # Determine the data source (file or raw_data)
    if file:
        file_name = file.name.split('.')[0]
        # Custom function to read data from file if needed
        raw_data = extract_data_from_file(file, data_format)
    else:
        file_name = "uploaded_data"

    # Validate the format
    if not data_format or not raw_data:
        return Response({'error': 'Format and data are required'}, status=status.HTTP_400_BAD_REQUEST)
    elif data_format == 'geojson':
        errors = validate_geojson(raw_data)
    elif data_format == 'csv':
        errors = validate_csv(raw_data)
    else:
        return Response({'error': 'Unsupported format'}, status=status.HTTP_400_BAD_REQUEST)

    if errors:
        # Custom function to handle S3 upload
        store_failed_file_in_s3(file, request.user, file_name)
        return Response({'errors': errors}, status=status.HTTP_400_BAD_REQUEST)

    if data_format == 'csv':
        raw_data = transform_csv_to_json(raw_data)

    # Combine file_name and format for database entry
    file_data = {
        "file_name": f"{file_name}.{data_format}",
        "uploaded_by": request.user.username if request.user.is_authenticated else "admin",
    }
    file_serializer = EUDRUploadedFilesModelSerializer(data=file_data)

    if file_serializer.is_valid():
        if not EUDRUploadedFilesModel.objects.filter(
            file_name=file_data["file_name"],
            uploaded_by=request.user.username if request.user.is_authenticated else "admin"
        ).exists():
            file_serializer.save()
        file_id = EUDRUploadedFilesModel.objects.get(
            file_name=file_data["file_name"],
            uploaded_by=request.user.username if request.user.is_authenticated else "admin"
        ).id

        errors, _ = async_to_sync(async_create_farm_data)(
            raw_data, file_id)
        if errors:
            # Custom function to handle failed file entries
            handle_failed_file_entry(file_serializer, file, request.user)
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
    else:
        # Custom function to handle failed file entries
        handle_failed_file_entry(file_serializer, file, request.user)
        return Response({'error': 'File serialization failed'}, status=status.HTTP_400_BAD_REQUEST)

    # Proceed with other operations...
    update_geoid(repeat=60,
                 user_id=request.user.username if request.user.is_authenticated else "admin")
    return Response({'message': 'File/data processed successfully', 'file_id': file_id}, status=status.HTTP_201_CREATED)


@swagger_auto_schema(
    method="post",
    operation_summary="Sync farm data",
    request_body=openapi.Schema(
        type=openapi.TYPE_ARRAY,
        items=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "device_id": openapi.Schema(type=openapi.TYPE_STRING),
                "collection_site": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "name": openapi.Schema(type=openapi.TYPE_STRING),
                        "phone_number": openapi.Schema(type=openapi.TYPE_STRING),
                        "email": openapi.TYPE_STRING,
                        "latitude": openapi.Schema(type=openapi.TYPE_STRING),
                        "longitude": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
                "farms": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "remote_id": openapi.Schema(type=openapi.TYPE_STRING),
                            "farmer_name": openapi.Schema(type=openapi.TYPE_STRING),
                            "farm_size": openapi.Schema(type=openapi.TYPE_INTEGER),
                            "farm_village": openapi.Schema(type=openapi.TYPE_STRING),
                            "farm_district": openapi.Schema(type=openapi.TYPE_STRING),
                            "latitude": openapi.Schema(type=openapi.TYPE_STRING),
                            "longitude": openapi.Schema(type=openapi.TYPE_STRING),
                            "polygon": openapi.Schema(
                                type=openapi.TYPE_ARRAY,
                                items=openapi.Schema(
                                    type=openapi.TYPE_ARRAY,
                                    items=openapi.Schema(
                                        type=openapi.TYPE_NUMBER)
                                )
                            ),
                            "polygon_type": openapi.Schema(type=openapi.TYPE_STRING),
                        },
                    ),
                ),
            },
            default={
                "device_id": "device_1",
                "collection_site": {
                    "name": "Site A",
                    "phone_number": "1234567890",
                    "email": "janedoe@gmail.com",
                    "latitude": "-1.62883139933721",
                    "longitude": "29.9898212498949",
                },
                "farms": [
                    {
                        "remote_id": "farm_1",
                        "farmer_name": "John Doe",
                        "farm_size": 4,
                        "farm_village": "Village A",
                        "farm_district": "District A",
                        "latitude": "-1.62883139933721",
                        "longitude": "29.9898212498949",
                        "polygon": [[41.8781, 87.6298], [41.8781, 87.6299]],
                        "polygon_type": "Polygon",
                    },
                ],
            },
        ),
    ),
    responses={
        200: openapi.Response(
            description="Farm data synced successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "synced_remote_ids": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(type=openapi.TYPE_STRING)
                    ),
                },
            ),
            examples={
                "application/json": {
                    "synced_remote_ids": ["farm_1", "farm_2"],
                },
            },
        ),
        400: openapi.Response(
            description="Bad request",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
            examples={
                "application/json": {
                    "error": "Either a file or data is required",
                },
            },
        ),
    },
    tags=["Farm Data Management"]
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sync_farm_data(request):
    sync_results = []
    data = request.data
    for entry in data:
        # Check or create collection site
        site_data = entry.get('collection_site')
        # append device_id to site_data
        site_data['device_id'] = entry.get("device_id")
        site, created = EUDRCollectionSiteModel.objects.update_or_create(
            name=site_data['name'],
            defaults=site_data
        )

        # Sync farms
        for farm_data in entry.get('farms', []):
            farm_data['site_id'] = site
            farm, farm_created = EUDRFarmBackupModel.objects.update_or_create(
                remote_id=farm_data.get('remote_id'),
                defaults=farm_data
            )
            sync_results.append(farm.remote_id)

    return Response({"synced_remote_ids": sync_results}, status=status.HTTP_200_OK)


@swagger_auto_schema(
    method="post",
    operation_summary="Restore farm data",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "device_id": openapi.Schema(type=openapi.TYPE_STRING),
            "phone_number": openapi.Schema(type=openapi.TYPE_STRING),
            "email": openapi.Schema(type=openapi.TYPE_STRING),
        },
        default={
            "device_id": "device_1",
            "phone_number": "1234567890",
            "email": "mamadoe@gmail.com",
        },
    ),
    responses={
        200: openapi.Response(
            description="Farm data restored successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "device_id": openapi.Schema(type=openapi.TYPE_STRING),
                        "collection_site": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "name": openapi.Schema(type=openapi.TYPE_STRING),
                                "phone_number": openapi.Schema(type=openapi.TYPE_STRING),
                                "email": openapi.Schema(type=openapi.TYPE_STRING),
                                "latitude": openapi.Schema(type=openapi.TYPE_STRING),
                                "longitude": openapi.Schema(type=openapi.TYPE_STRING),
                            },
                        ),
                        "farms": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "remote_id": openapi.Schema(type=openapi.TYPE_STRING),
                                    "farmer_name": openapi.Schema(type=openapi.TYPE_STRING),
                                    "farm_size": openapi.Schema(type=openapi.TYPE_INTEGER),
                                    "farm_village": openapi.Schema(type=openapi.TYPE_STRING),
                                    "farm_district": openapi.Schema(type=openapi.TYPE_STRING),
                                    "latitude": openapi.Schema(type=openapi.TYPE_STRING),
                                    "longitude": openapi.Schema(type=openapi.TYPE_STRING),
                                    "polygon": openapi.Schema(
                                        type=openapi.TYPE_ARRAY,
                                        items=openapi.Schema(
                                            type=openapi.TYPE_ARRAY,
                                            items=openapi.Schema(
                                                type=openapi.TYPE_NUMBER)
                                        )
                                    ),
                                    "polygon_type": openapi.Schema(type=openapi.TYPE_STRING),
                                },
                            ),
                        ),
                    },
                ),
            ),
            examples={
                "application/json": [
                    {
                        "device_id": "device_1",
                        "collection_site": {
                            "name": "Site A",
                            "phone_number": "1234567890",
                            "email": "johndoe@gmail.com",
                            "latitude": "-1.62883139933721",
                            "longitude": "29.9898212498949",
                            "farms": [
                                {
                                    "remote_id": "farm_1",
                                    "farmer_name": "John Doe",
                                    "farm_size": 4,
                                    "farm_village": "Village A",
                                    "farm_district": "District A",
                                    "latitude": "-1.62883139933721",
                                    "longitude": "29.9898212498949",
                                    "polygon": [[41.8781, 87.6298], [41.8781, 87.6299]],
                                    "polygon_type": "Polygon",
                                },
                            ],
                        },
                    },
                ],
            },
        ),
    },
    tags=["Farm Data Management"]
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def restore_farm_data(request):
    device_id = request.data.get("device_id")
    phone_number = request.data.get("phone_number")
    email = request.data.get("email")

    collection_sites = []

    # Query based on priority: device_id, phone_number, or email
    if device_id:
        collection_sites = EUDRCollectionSiteModel.objects.filter(
            device_id=device_id)
    elif phone_number:
        collection_sites = EUDRCollectionSiteModel.objects.filter(
            phone_number=phone_number)
    elif email:
        collection_sites = EUDRCollectionSiteModel.objects.filter(email=email)

    if not collection_sites:
        return Response([], status=status.HTTP_200_OK)

    # Prepare the restore data in the required format
    restore_data = []

    for site in collection_sites:
        # Fetch all farms linked to this collection site
        farms = EUDRFarmBackupModel.objects.filter(site_id=site.id)
        farm_data = EUDRFarmBackupModelSerializer(farms, many=True).data

        # Construct the structure with the collection site and farms
        restore_data.append({
            "device_id": site.device_id,
            "collection_site": EUDRCollectionSiteModelSerializer(site).data,
            "farms": farm_data
        })

    return Response(restore_data, status=status.HTTP_200_OK)


@swagger_auto_schema(
    method="put",
    operation_summary="Update farm data",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "farmer_name": openapi.Schema(type=openapi.TYPE_STRING),
            "farm_size": openapi.Schema(type=openapi.TYPE_INTEGER),
            "collection_site": openapi.Schema(type=openapi.TYPE_STRING),
            "farm_village": openapi.Schema(type=openapi.TYPE_STRING),
            "farm_district": openapi.Schema(type=openapi.TYPE_STRING),
            "latitude": openapi.Schema(type=openapi.TYPE_STRING),
            "longitude": openapi.Schema(type=openapi.TYPE_STRING),
            "polygon": openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_NUMBER)
                )
            ),
            "polygon_type": openapi.Schema(type=openapi.TYPE_STRING),
        },
        default={
            "farmer_name": "John Doe",
            "farm_size": 4,
            "collection_site": "Site A",
            "farm_village": "Village A",
            "farm_district": "District A",
            "latitude": -1.62883139933721,
            "longitude": 29.9898212498949,
            "polygon": [[41.8781, 87.6298], [41.8781, 87.6299]],
            "polygon_type": "Polygon",
        },
    ),
    responses={
        200: openapi.Response(
            description="Farm data updated successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "farmer_name": openapi.Schema(type=openapi.TYPE_STRING),
                    "farm_size": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "collection_site": openapi.Schema(type=openapi.TYPE_STRING),
                    "farm_village": openapi.Schema(type=openapi.TYPE_STRING),
                    "farm_district": openapi.Schema(type=openapi.TYPE_STRING),
                    "latitude": openapi.Schema(type=openapi.TYPE_STRING),
                    "longitude": openapi.Schema(type=openapi.TYPE_STRING),
                    "polygon": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_NUMBER)
                        )
                    ),
                    "polygon_type": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
            examples={
                "application/json": {
                    "id": 1,
                    "farmer_name": "John Doe",
                    "farm_size": 4,
                    "collection_site": "Site A",
                    "farm_village": "Village A",
                    "farm_district": "District A",
                    "latitude": -1.62883139933721,
                    "longitude": 29.9898212498949,
                    "polygon": [[41.8781, 87.6298], [41.8781, 87.6299]],
                    "polygon_type": "Polygon",
                },
            },
        ),
        400: openapi.Response(
            description="Bad request",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "farmer_name": openapi.Schema(type=openapi.TYPE_OBJECT),
                    "farm_size": openapi.Schema(type=openapi.TYPE_OBJECT),
                    "collection_site": openapi.Schema(type=openapi.TYPE_OBJECT),
                    "farm_village": openapi.Schema(type=openapi.TYPE_OBJECT),
                    "farm_district": openapi.Schema(type=openapi.TYPE_OBJECT),
                    "latitude": openapi.Schema(type=openapi.TYPE_OBJECT),
                    "longitude": openapi.Schema(type=openapi.TYPE_OBJECT),
                    "polygon": openapi.Schema(type=openapi.TYPE_OBJECT),
                    "polygon_type": openapi.Schema(type=openapi.TYPE_OBJECT),
                },
            ),
            examples={
                "application/json": {
                    "farmer_name": ["This field is required."],
                    "farm_size": ["This field is required."],
                    "collection_site": ["This field is required."],
                    "farm_village": ["This field is required."],
                    "farm_district": ["This field is required."],
                    "latitude": ["This field is required."],
                    "longitude": ["This field is required."],
                    "polygon": ["This field is required."],
                    "polygon_type": ["This field is required."],
                },
            },
        ),
    },
    tags=["Farm Data Management"]
)
@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_farm_data(request, pk):
    farm_data = EUDRFarmModel.objects.get(id=pk)
    serializer = EUDRFarmModelSerializer(instance=farm_data, data=request.data)

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method="post",
    operation_summary="Revalidate farm data",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "file_id": openapi.Schema(type=openapi.TYPE_STRING),
        },
    ),
    responses={
        201: openapi.Response(
            description="Farm data revalidated successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "message": openapi.Schema(type=openapi.TYPE_STRING),
                    "file_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                },
            ),
            examples={
                "application/json": {
                    "message": "Farm data revalidated successfully",
                    "file_id": 1,
                },
            },
        ),
        400: openapi.Response(
            description="Bad request",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
            examples={
                "application/json": {
                    "error": "File ID is required",
                },
            },
        ),
    },
    tags=["Farm Data Management"]
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def revalidate_farm_data(request):
    file_id = request.data.get("file_id")

    # if file_id is not provided, return an error
    if not file_id:
        return Response({'error': 'File ID is required'}, status=status.HTTP_400_BAD_REQUEST)

    # get all the data belonging to the file_ids
    data = EUDRFarmModel.objects.filter(
        file_id=file_id).order_by("-updated_at")
    serializer = EUDRFarmModelSerializer(data, many=True)

    # format the data to geojson format and send to whisp API for processing
    raw_data = transform_db_data_to_geojson(serializer.data)

    # combine file_name and format to save in the database with dummy uploaded_by. then retrieve the file_id
    if (serializer.data):
        errors, created_data = async_to_sync(async_create_farm_data)(
            raw_data, file_id)
        if errors:
            # delete the file if there are errors
            EUDRUploadedFilesModel.objects.get(id=file_id).delete()
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
    else:
        return Response({'error': 'No data found'}, status=status.HTTP_400_BAD_REQUEST)

    return Response(created_data, status=status.HTTP_201_CREATED)


@swagger_auto_schema(
    method="get",
    operation_summary="Retrieve farm data",
    responses={
        200: openapi.Response(
            description="Farm data retrieved successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "farmer_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "farm_size": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "collection_site": openapi.Schema(type=openapi.TYPE_STRING),
                        "farm_village": openapi.Schema(type=openapi.TYPE_STRING),
                        "farm_district": openapi.Schema(type=openapi.TYPE_STRING),
                        "latitude": openapi.Schema(type=openapi.TYPE_STRING),
                        "longitude": openapi.Schema(type=openapi.TYPE_STRING),
                        "polygon": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_ARRAY,
                                items=openapi.Schema(
                                    type=openapi.TYPE_NUMBER)
                            )
                        ),
                        "polygon_type": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
        ),
    },
    tags=["Farm Data Management"]
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retrieve_farm_data(request):
    files = EUDRUploadedFilesModel.objects.filter(
        uploaded_by=request.user.username if request.user.is_authenticated else "admin"
    ) if not request.user.is_staff else EUDRUploadedFilesModel.objects.all()
    filesSerializer = EUDRUploadedFilesModelSerializer(files, many=True)

    data = EUDRFarmModel.objects.filter(
        file_id__in=[file["id"] for file in filesSerializer.data]
    ).order_by("-updated_at")

    serializer = EUDRFarmModelSerializer(data, many=True)

    return Response(serializer.data)


@swagger_auto_schema(
    method="get",
    operation_summary="Retrieve overlapping farm data",
    responses={
        200: openapi.Response(
            description="Overlapping farm data retrieved successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "farmer_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "farm_size": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "collection_site": openapi.Schema(type=openapi.TYPE_STRING),
                        "farm_village": openapi.Schema(type=openapi.TYPE_STRING),
                        "farm_district": openapi.Schema(type=openapi.TYPE_STRING),
                        "latitude": openapi.Schema(type=openapi.TYPE_STRING),
                        "longitude": openapi.Schema(type=openapi.TYPE_STRING),
                        "polygon": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_ARRAY,
                                items=openapi.Schema(
                                    type=openapi.TYPE_NUMBER)
                            )
                        ),
                        "polygon_type": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
        ),
    },
    tags=["Farm Data Management"]
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retrieve_overlapping_farm_data(request, pk):
    files = EUDRUploadedFilesModel.objects.filter(
        id=pk) if not request.user.is_staff else EUDRUploadedFilesModel.objects.all()

    filesSerializer = EUDRUploadedFilesModelSerializer(files, many=True)

    farms = EUDRFarmModel.objects.filter(
        file_id=filesSerializer.data[0].get("id")
    ).order_by("-updated_at")

    farmSerializer = EUDRFarmModelSerializer(farms, many=True)

    overLaps = []
    farms = farmSerializer.data

    for farm in farms:
        # Assuming farm data has 'farmer_name', 'latitude', 'longitude', 'farm_size', and 'polygon' fields
        polygon = flatten_multipolygon_coordinates(
            farm['polygon']) if farm['polygon_type'] == 'MultiPolygon' else farm['polygon']
        if 'polygon' in farm and len(polygon) == 1:
            polygon = flatten_multipolygon_coordinates(farm['polygon'])

            if polygon:
                farm_polygon = Polygon(polygon[0])
                is_overlapping = any(farm_polygon.overlaps(
                    Polygon(other_farm['polygon'][0])) for other_farm in farms)
                overLaps.append(farm) if is_overlapping else None

    return Response(overLaps)


@swagger_auto_schema(
    method="get",
    operation_summary="Retrieve user farm data",
    responses={
        200: openapi.Response(
            description="User farm data retrieved successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "farmer_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "farm_size": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "collection_site": openapi.Schema(type=openapi.TYPE_STRING),
                        "farm_village": openapi.Schema(type=openapi.TYPE_STRING),
                        "farm_district": openapi.Schema(type=openapi.TYPE_STRING),
                        "latitude": openapi.Schema(type=openapi.TYPE_STRING),
                        "longitude": openapi.Schema(type=openapi.TYPE_STRING),
                        "polygon": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_ARRAY,
                                items=openapi.Schema(
                                    type=openapi.TYPE_NUMBER)
                            )
                        ),
                        "polygon_type": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
        ),
    },
    tags=["Farm Data Management"]
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retrieve_user_farm_data(request, pk):
    users = User.objects.filter(id=pk)
    files = EUDRUploadedFilesModel.objects.filter(
        uploaded_by=users.values()[0].get("username")
    )
    filesSerializer = EUDRUploadedFilesModelSerializer(files, many=True)

    data = EUDRFarmModel.objects.filter(
        file_id__in=[file["id"] for file in filesSerializer.data]
    ).order_by("-updated_at")

    serializer = EUDRFarmModelSerializer(data, many=True)

    return Response(serializer.data)


@swagger_auto_schema(
    method="get",
    operation_summary="Retrieve all synced farm data",
    responses={
        200: openapi.Response(
            description="All synced farm data retrieved successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "farmer_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "farm_size": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "collection_site": openapi.Schema(type=openapi.TYPE_STRING),
                        "farm_village": openapi.Schema(type=openapi.TYPE_STRING),
                        "farm_district": openapi.Schema(type=openapi.TYPE_STRING),
                        "latitude": openapi.Schema(type=openapi.TYPE_STRING),
                        "longitude": openapi.Schema(type=openapi.TYPE_STRING),
                        "polygon": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_ARRAY,
                                items=openapi.Schema(
                                    type=openapi.TYPE_NUMBER)
                            )
                        ),
                        "polygon_type": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
        ),
    },
    tags=["Farm Data Management"]
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retrieve_all_synced_farm_data(request):
    data = EUDRFarmBackupModel.objects.all().order_by("-updated_at")

    serializer = EUDRFarmBackupModelSerializer(data, many=True)

    return Response(serializer.data)


@swagger_auto_schema(
    method="get",
    operation_summary="Retrieve all synced farm data by collection site",
    responses={
        200: openapi.Response(
            description="All synced farm data retrieved successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "farmer_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "farm_size": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "collection_site": openapi.Schema(type=openapi.TYPE_STRING),
                        "farm_village": openapi.Schema(type=openapi.TYPE_STRING),
                        "farm_district": openapi.Schema(type=openapi.TYPE_STRING),
                        "latitude": openapi.Schema(type=openapi.TYPE_STRING),
                        "longitude": openapi.Schema(type=openapi.TYPE_STRING),
                        "polygon": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_ARRAY,
                                items=openapi.Schema(
                                    type=openapi.TYPE_NUMBER)
                            )
                        ),
                        "polygon_type": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
        ),
    },
    tags=["Farm Data Management"]
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retrieve_all_synced_farm_data_by_cs(request, pk):
    data = EUDRFarmBackupModel.objects.filter(
        site_id=pk
    ).order_by("-updated_at")

    serializer = EUDRFarmBackupModelSerializer(data, many=True)

    return Response(serializer.data)


@swagger_auto_schema(
    method="get",
    operation_summary="Retrieve collection sites",
    responses={
        200: openapi.Response(
            description="Collection sites retrieved successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "name": openapi.Schema(type=openapi.TYPE_STRING),
                        "phone_number": openapi.Schema(type=openapi.TYPE_STRING),
                        "email": openapi.Schema(type=openapi.TYPE_STRING),
                        "latitude": openapi.Schema(type=openapi.TYPE_STRING),
                        "longitude": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
            examples={
                "application/json": [
                    {
                        "id": 1,
                        "name": "Site A",
                        "phone_number": "1234567890",
                        "email": "johndoe@gmail.com",
                        "latitude": "-1.62883139933721",
                        "longitude": "29.9898212498949",
                        "updated_at": "2021-09-09T12:00:00",
                        "created_at": "2021-09-09T12:00:00",
                    },
                    {
                        "id": 2,
                        "name": "Site B",
                        "phone_number": "0987654321",
                        "email": "janedoe@gmail.com",
                        "latitude": "-1.62883139933721",
                        "longitude": "29.9898212498949",
                        "updated_at": "2021-09-09T12:00:00",
                        "created_at": "2021-09-09T12:00:00",
                    },
                ],
            },
        ),
    },
    tags=["Farm Data Management"]
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retrieve_collection_sites(request):
    data = EUDRCollectionSiteModel.objects.all().order_by("-updated_at")

    serializer = EUDRCollectionSiteModelSerializer(data, many=True)

    return Response(serializer.data)


@swagger_auto_schema(
    method="get",
    operation_summary="Retrieve map data",
    responses={
        200: openapi.Response(
            description="Map data retrieved successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "farmer_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "farm_size": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "collection_site": openapi.Schema(type=openapi.TYPE_STRING),
                        "farm_village": openapi.Schema(type=openapi.TYPE_STRING),
                        "farm_district": openapi.Schema(type=openapi.TYPE_STRING),
                        "latitude": openapi.Schema(type=openapi.TYPE_STRING),
                        "longitude": openapi.Schema(type=openapi.TYPE_STRING),
                        "polygon": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_ARRAY,
                                items=openapi.Schema(
                                    type=openapi.TYPE_NUMBER)
                            )
                        ),
                        "polygon_type": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
        ),
    },
    tags=["Farm Data Management"]
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retrieve_map_data(request):
    files = EUDRUploadedFilesModel.objects.filter(
        uploaded_by=request.user.username if request.user.is_authenticated else "admin"
    )
    filesSerializer = EUDRUploadedFilesModelSerializer(files, many=True)

    data = EUDRFarmModel.objects.filter(
        file_id__in=[file["id"] for file in filesSerializer.data]
    ).order_by("-updated_at") if not request.user.is_staff else EUDRFarmModel.objects.all().order_by("-updated_at")

    serializer = EUDRFarmModelSerializer(data, many=True)

    return Response(serializer.data)


@swagger_auto_schema(
    method="get",
    operation_summary="Retrieve farm detail",
    responses={
        200: openapi.Response(
            description="Farm data retrieved successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "farmer_name": openapi.Schema(type=openapi.TYPE_STRING),
                    "farm_size": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "collection_site": openapi.Schema(type=openapi.TYPE_STRING),
                    "farm_village": openapi.Schema(type=openapi.TYPE_STRING),
                    "farm_district": openapi.Schema(type=openapi.TYPE_STRING),
                    "latitude": openapi.Schema(type=openapi.TYPE_STRING),
                    "longitude": openapi.Schema(type=openapi.TYPE_STRING),
                    "polygon": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_NUMBER)
                        )
                    ),
                    "polygon_type": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
        ),
    },
    tags=["Farm Data Management"]
)
@api_view(["GET"])
def retrieve_farm_detail(request, pk):
    data = EUDRFarmModel.objects.get(id=pk)
    serializer = EUDRFarmModelSerializer(data, many=False)
    return Response(serializer.data)


@swagger_auto_schema(
    method="get",
    operation_summary="Retrieve farm data from file ID",
    responses={
        200: openapi.Response(
            description="Farm data retrieved successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "farmer_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "farm_size": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "collection_site": openapi.Schema(type=openapi.TYPE_STRING),
                        "farm_village": openapi.Schema(type=openapi.TYPE_STRING),
                        "farm_district": openapi.Schema(type=openapi.TYPE_STRING),
                        "latitude": openapi.Schema(type=openapi.TYPE_STRING),
                        "longitude": openapi.Schema(type=openapi.TYPE_STRING),
                        "polygon": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_ARRAY,
                                items=openapi.Schema(
                                    type=openapi.TYPE_NUMBER)
                            )
                        ),
                        "polygon_type": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
        ),
    },
    tags=["Farm Data Management"]
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retrieve_farm_data_from_file_id(request, pk):
    data = EUDRFarmModel.objects.filter(file_id=pk)
    serializer = EUDRFarmModelSerializer(data, many=True)
    return Response(serializer.data)


@swagger_auto_schema(
    method="get",
    operation_summary="Retrieve files",
    responses={
        200: openapi.Response(
            description="All files retrieved successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "file_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "uploaded_by": openapi.Schema(type=openapi.TYPE_STRING),
                        "updated_at": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
            examples={
                "application/json": [
                    {
                        "id": 1,
                        "file_name": "file_1.geojson",
                        "uploaded_by": "johndoe",
                        "updated_at": "2021-09-09T12:00:00",
                    },
                    {
                        "id": 2,
                        "file_name": "file_2.csv",
                        "uploaded_by": "janedoe",
                        "updated_at": "2021-09-09T12:00:00",
                    },
                ],
            },
        ),
    },
    tags=["Files Management"]
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retrieve_files(request):
    data = None
    if request.user.is_authenticated:
        # Filter by the authenticated user's username
        data = EUDRUploadedFilesModel.objects.filter(
            uploaded_by=request.user.username).order_by("-updated_at") if not request.user.is_staff else EUDRUploadedFilesModel.objects.all().order_by("-updated_at")
    else:
        # Retrieve all records if no authenticated user
        data = EUDRUploadedFilesModel.objects.all().order_by("-updated_at")
    serializer = EUDRUploadedFilesModelSerializer(data, many=True)
    return Response(serializer.data)


@swagger_auto_schema(
    method="get",
    operation_summary="Retrieve all files",
    responses={
        200: openapi.Response(
            description="All files retrieved successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "file_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "uploaded_by": openapi.Schema(type=openapi.TYPE_STRING),
                        "updated_at": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
            ),
            examples={
                "application/json": [
                    {
                        "id": 1,
                        "file_name": "file_1.geojson",
                        "uploaded_by": "johndoe",
                        "updated_at": "2021-09-09T12:00:00",
                    },
                    {
                        "id": 2,
                        "file_name": "file_2.csv",
                        "uploaded_by": "janedoe",
                        "updated_at": "2021-09-09T12:00:00",
                    },
                ],
            },
        ),
        400: openapi.Response(
            description="Bad request",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
            examples={
                "application/json": {
                    "error": "An error occurred",
                },
            },
        ),
    },
    tags=["Files Management"]
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retrieve_s3_files(request):
    try:
        # Retrieve all files from all directories in the S3 bucket
        s3 = boto3.client('s3', aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                          aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY)
        response = s3.list_objects_v2(Bucket=settings.AWS_STORAGE_BUCKET_NAME)
        # get file urls and date uploaded
        files = []
        count = 0
        for content in response.get('Contents', []):
            file = {
                'id': count,
                'file_name': content.get('Key').split("/")[1].split("_", 1)[1],
                'last_modified': content.get('LastModified'),
                'size': content.get('Size') / 1024,
                'url': f"{settings.AWS_S3_BASE_URL}{content.get('Key')}",
                'uploaded_by': content.get('Key').split("/")[1].split("_")[0],
                'category': content.get('Key').split("/")[0],
            }
            files.append(file)
            count += 1

        return Response(files)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method="get",
    operation_summary="Retrieve file",
    responses={
        200: openapi.Response(
            description="File retrieved successfully",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "file_name": openapi.Schema(type=openapi.TYPE_STRING),
                    "uploaded_by": openapi.Schema(type=openapi.TYPE_STRING),
                    "updated_at": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
            examples={
                "application/json": {
                    "id": 1,
                    "file_name": "file_1.geojson",
                    "uploaded_by": "johndoe",
                    "updated_at": "2021-09-09T12:00:00",
                },
            },
        ),
        404: openapi.Response(
            description="File not found",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
            examples={
                "application/json": {
                    "error": "File not found",
                },
            },
        ),
    },
    tags=["Files Management"]
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def retrieve_file(request, pk):
    try:
        data = EUDRUploadedFilesModel.objects.get(id=pk)
        serializer = EUDRUploadedFilesModelSerializer(data, many=False)
        return Response(serializer.data)
    except EUDRUploadedFilesModel.DoesNotExist:
        return Response({"error": "File not found"}, status=status.HTTP_404_NOT_FOUND)


@swagger_auto_schema(
    method="get",
    operation_summary="Download template file",
    responses={
        200: openapi.Response(
            description="File downloaded successfully",
            content={
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "access_code": {"type": "string"},
                            "map_link": {"type": "string"},
                        },
                    },
                    "examples": {
                        "application/json": {
                            "access_code": "123456",
                            "map_link": "https://example.com/map/share/?file-id=123456&access-code=123456",
                        },
                    },
                },
            },
        ),
        400: openapi.Response(
            description="Bad request",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
            examples={
                "application/json": {
                    "error": "Format parameter is missing or incorrect",
                },
            },
        ),
    }, manual_parameters=[openapi.Parameter(
        name="file_format",
        in_=openapi.IN_QUERY,
        type=openapi.TYPE_STRING,
        required=True,
        description="File format to download (csv or geojson)",
    )],
    security=[],
    tags=["Files Management"]
)
@api_view(["GET"])
def download_template(request):
    file_format = request.query_params.get("file_format", None)

    if not file_format:
        return Response({"error": "Format parameter is missing or incorrect"}, status=400)

    # Create a sample template dataframe
    data = {
        "farmer_name": "John Doe",
        "farm_size": 4,
        "collection_site": "Site A",
        "farm_village": "Village A",
        "farm_district": "District A",
        "latitude": "-1.62883139933721",
        "longitude": "29.9898212498949",
        "polygon": "[[41.8781, 87.6298], [41.8781, 87.6299]]",
    }

    df = pd.DataFrame([data])

    timestamp_str = timezone.now().strftime("%Y-%m-%d-%H-%M-%S")

    # GeoJSON format will depend on your specific data structure
    # This is just an example
    geojson_data = {"type": "FeatureCollection", "features": [
        {
            "type": "Feature",
            "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [41.8781, 87.6298],
                            [41.8781, 87.6299],
                        ]
                    ]
            },
            "properties": {
                "farmer_name": "John Doe",
                "farm_size": 4,
                "collection_site": "Site A",
                "farm_village": "Village A",
                "farm_district": "District A",
                "latitude": "-1.62883139933721",
                "longitude": "29.9898212498949",
            },
        }
    ]}

    if file_format == "csv":
        response = HttpResponse(content_type="text/csv")
        filename = f"terratrac-upload-template-{timestamp_str}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        df.to_csv(response, index=False)
    elif file_format == "geojson":
        response = HttpResponse(content_type="application/json")
        filename = f"terratrac-upload-template-{timestamp_str}.geojson"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response.write(json.dumps(geojson_data))
    else:
        return Response({"error": "Invalid format"}, status=status.HTTP_400_BAD_REQUEST)

    return response


@swagger_auto_schema(
    method="post",
    operation_summary="Generate map link",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "file-id": openapi.Schema(type=openapi.TYPE_STRING),
        },
    ),
    responses={
        200: openapi.Response(
            description="Map link generated successfully",
            content={
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "access_code": {"type": "string"},
                            "map_link": {"type": "string"},
                        },
                    },
                    "examples": {
                        "application/json": {
                            "access_code": "123456",
                            "map_link": "https://example.com/map/share/?file-id=123456&access-code=123456",
                        },
                    },
                },
            },
        ),
        400: openapi.Response(
            description="Bad request",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "error": openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
            examples={
                "application/json": {
                    "error": "File ID is required",
                },
            },
        ),
    },
    tags=["Farm Data Management"]
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_map_link(request):
    fileId = request.data.get("file-id")
    try:
        shared_map_access = EUDRSharedMapAccessCodeModel.objects.get(
            file_id=fileId)
        if shared_map_access.valid_until >= timezone.now():
            access_code = shared_map_access.access_code
        else:
            raise EUDRSharedMapAccessCodeModel.DoesNotExist
    except EUDRSharedMapAccessCodeModel.DoesNotExist:
        access_code = generate_access_code()
        valid_until = timezone.now() + timedelta(days=90)
        shared_map_access = EUDRSharedMapAccessCodeModel.objects.create(
            file_id=fileId,
            access_code=access_code,
            valid_until=valid_until
        )

    map_link = f"""{request.scheme}://{request.get_host()
                                       }/map/share/?file-id={fileId}&access-code={access_code}"""

    return Response({"access_code": access_code, "map_link": map_link}, status=status.HTTP_200_OK)
