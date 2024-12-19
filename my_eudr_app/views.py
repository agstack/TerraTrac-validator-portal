from django.shortcuts import redirect, render
from django.contrib import messages
from rest_framework.decorators import permission_classes
from rest_framework.permissions import IsAuthenticated

from eudr_backend.util_classes import IsSuperUser


@permission_classes([IsAuthenticated])
def index(request):
    if request.user.is_anonymous:
        return redirect('login')

    active_page = "index"

    return render(request, "index.html", {"active_page": active_page, 'user': request.user})


@permission_classes([IsAuthenticated])
def validator(request):
    if request.user.is_anonymous:
        return redirect('login')

    active_page = "validator"

    return render(request, "validator.html", {"active_page": active_page, 'user': request.user})


@permission_classes([IsAuthenticated])
def validated_files(request):
    if request.user.is_anonymous:
        return redirect('login')

    active_page = "validated_files"

    return render(request, "validated_files.html", {"active_page": active_page, 'user': request.user})


@permission_classes([IsAuthenticated])
def map(request):
    if request.user.is_anonymous:
        return redirect('login')

    active_page = "map"

    return render(request, "map.html", {"active_page": active_page, 'user': request.user})


def shared_map(request):
    if request.user.is_anonymous:
        return redirect('login')

    active_page = "shared_map"

    return render(request, "shared_map.html", {"active_page": active_page, 'user': request.user})


@permission_classes([IsSuperUser])
def users(request):
    if request.user.is_anonymous:
        return redirect('login')

    active_page = "users"

    return render(request, "users.html", {"active_page": active_page, 'user': request.user})


@permission_classes([IsSuperUser])
def backups(request):
    if request.user.is_anonymous:
        return redirect('login')

    active_page = "backups"

    return render(request, "backups.html", {"active_page": active_page, 'user': request.user})


@permission_classes([IsSuperUser])
def backup_details(request):
    if request.user.is_anonymous:
        return redirect('login')

    active_page = "backup_details"

    return render(request, "backup_details.html", {"active_page": active_page, 'user': request.user})


@permission_classes([IsSuperUser])
def all_uploaded_files(request):
    if request.user.is_anonymous:
        return redirect('login')

    active_page = "uploads"

    return render(request, "uploads.html", {"active_page": active_page, 'user': request.user})


@permission_classes([IsAuthenticated])
def profile(request):
    if request.user.is_anonymous:
        return redirect('login')

    if request.method == 'POST':
        user = request.user
        user.first_name = request.POST.get('first_name')
        user.last_name = request.POST.get('last_name')
        user.email = request.POST.get('email')
        user.save()
        messages.success(request, 'Profile updated successfully.')
        return redirect('profile')
    return render(request, 'profile.html')
