from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.contrib import messages
from django.contrib.auth.models import User
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.urls import reverse
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.authtoken.models import Token
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework import status
from rest_framework.response import Response

from eudr_backend.serializers import EUDRUserModelSerializer


@swagger_auto_schema(method='post', request_body=openapi.Schema(type=openapi.TYPE_OBJECT, properties={
    'first_name': openapi.Schema(type=openapi.TYPE_STRING, description='First Name'),
    'last_name': openapi.Schema(type=openapi.TYPE_STRING, description='Last Name'),
    'username': openapi.Schema(type=openapi.TYPE_STRING, description='Username'),
    'password1': openapi.Schema(type=openapi.TYPE_STRING, description='Password'),
    'password2': openapi.Schema(type=openapi.TYPE_STRING, description='Password Confirmation')
}, default={'first_name': 'John', 'last_name': 'Doe', 'username': 'johndoe@gmail.com', 'password1': 'password', 'password2': 'password'}), security=[],
    tags=["Auth Management"], operation_summary="Endpoint that signs up a user",
    responses={
        201: openapi.Response(
            description="Successful Response",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING, description='Message'),
                    'user': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'username': openapi.Schema(type=openapi.TYPE_STRING, description='Username')
                        }
                    ),
                    'token': openapi.Schema(type=openapi.TYPE_STRING, description='Token')
                }
            ),
            examples={
                "application/json": {
                    "message": "Signup successful",
                    "user": {
                        "username": "johndoe"
                    },
                    "token": "f5b0d5e7d2b8e5d8f4e3d2b1"
                }
            },
        ),
    400: openapi.Response(
        description="Failed Response",
        schema=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'message': openapi.Schema(type=openapi.TYPE_STRING, description='Message'),
                'errors': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'username': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Items(type=openapi.TYPE_STRING, description='Error message')),
                        'password1': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Items(type=openapi.TYPE_STRING, description='Error message'))
                    }
                )
            }
        ),
        examples={
            "application/json": {
                "message": "Signup failed",
                "errors": {
                    "username": [
                        "This field is required."
                    ],
                    "password1": [
                        "This field is required."
                    ]
                }
            }})
}
)
@swagger_auto_schema(method='get', operation_summary="Endpoint that returns sign up page", security=[],
                     tags=["Auth Management"])
@api_view(['GET', 'POST'])
def signup_view(request):
    """
    Handle user signup for both HTML rendering and API requests.
    """
    if request.method == 'GET':
        # Render the signup HTML template for GET requests
        form = UserCreationForm()
        return render(request, 'auth/signup.html', {'form': form})

    if request.method == 'POST':
        # Determine request type
        data = request.data if request.content_type == 'application/json' else request.POST
        form = UserCreationForm(data)
        if form.is_valid():
            user = form.save(commit=False)
            user.first_name = data.get('first_name', '')
            user.last_name = data.get('last_name', '')
            user.email = data.get('username', '')
            user.save()

            # generate token for user
            token, _ = Token.objects.get_or_create(user=user)

            if request.content_type == 'application/json':
                return Response({
                    "message": "Signup successful",
                    "user": {"username": user.username},
                    "token": token.key
                }, status=status.HTTP_201_CREATED)
            else:
                login(request, user)
                return redirect('index')
        else:
            if request.content_type == 'application/json':
                return Response({
                    "message": "Signup failed",
                    "errors": form.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            else:
                messages.error(request, form.errors)
                return render(request, 'auth/signup.html', {'form': form, 'errors': form.errors})


@swagger_auto_schema(
    method='post',
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'username': openapi.Schema(type=openapi.TYPE_STRING, description='Username'),
            'password': openapi.Schema(type=openapi.TYPE_STRING, description='Password')
        },
        required=['username', 'password'],
        default={'username': 'johndoe', 'password': 'password'}
    ),
    responses={
        200: openapi.Response(
            description="Successful Response",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING, description='Message'),
                    'user': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'username': openapi.Schema(type=openapi.TYPE_STRING, description='Username')
                        }
                    ),
                    'token': openapi.Schema(type=openapi.TYPE_STRING, description='Token')
                }
            ),
            examples={
                "application/json": {
                    "message": "Login successful",
                    "user": {
                        "username": "johndoe"
                    },
                    "token": "f5b0d5e7d2b8e5d8f4e3d2b1"
                }
            }
        ),
        400: openapi.Response(
            description="Failed Response",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING, description='Message')
                }
            ),
            examples={
                "application/json": {
                    "message": "Invalid username or password"
                }
            }
        )
    }, security=[],
    tags=["Auth Management"],
    operation_summary="Endpoint that logs in a user"
)
@ swagger_auto_schema(method='get', operation_summary="Endpoint that returns sign up page", security=[],
                      tags=["Auth Management"])
@ api_view(['GET', 'POST'])
def login_view(request):
    """
    Handle user login for both HTML rendering and API requests.
    """
    if request.method == 'GET':
        # Render the login HTML template for GET requests
        form = AuthenticationForm()
        return render(request, 'auth/login.html', {'form': form})

    if request.method == 'POST':
        # Handle form submission for POST requests
        if request.content_type == 'application/json':
            # JSON API request
            form = AuthenticationForm(request, data=request.data)
        else:
            # Form submission (HTML POST)
            form = AuthenticationForm(request, data=request.POST)

        if form.is_valid():
            user = form.get_user()
            token = Token.objects.get_or_create(user=user)[0]
            if request.content_type == 'application/json':
                # Respond with JSON for API requests
                return Response({
                    "message": "Login successful",
                    "user": {
                        "username": user.username
                    },
                    "token": token.key
                }, status=status.HTTP_200_OK)
            else:
                login(request, user)
                # Redirect or render another page for HTML form submission
                return redirect('index')
        else:
            if request.content_type == 'application/json':
                # Respond with JSON for invalid API request
                return Response({
                    "message": "Invalid username or password"
                }, status=status.HTTP_400_BAD_REQUEST)
            else:
                messages.error(request, 'Invalid username or password')
                # Re-render the login page with form errors for HTML
                return render(request, 'auth/login.html', {'form': form})


@ login_required
@ swagger_auto_schema(method='post', request_body=openapi.Schema(type=openapi.TYPE_OBJECT, properties={
    'first_name': openapi.Schema(type=openapi.TYPE_STRING, description='First Name'),
    'last_name': openapi.Schema(type=openapi.TYPE_STRING, description='Last Name'),
    'email': openapi.Schema(type=openapi.TYPE_STRING, description='Email')
}, default={'first_name': 'John', 'last_name': 'Doe', 'email': 'johndoes@gmail.com'}),
    responses={200: openapi.Response(description="Successful Response", schema=openapi.Schema(
        type=openapi.TYPE_OBJECT, properties={'message': openapi.Schema(type=openapi.TYPE_STRING, description='Message')}))},
    tags=["User Management"], operation_summary="Endpoint that allows a user to update their password")
@ api_view(['POST'])
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            # Important to keep the user logged in
            update_session_auth_hash(request, user)
            messages.success(
                request, 'Your password was successfully updated!')
            return redirect('profile')
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'change_password.html', {'form': form})


@ login_required
def logout_view(request):
    if request.method == 'POST':
        logout(request)
        return redirect('login')


@ swagger_auto_schema(method='post', request_body=openapi.Schema(type=openapi.TYPE_OBJECT, properties={
    'email': openapi.Schema(type=openapi.TYPE_STRING, description='Email')
}, default={'email': 'johndoe@gmail.com'}), security=[],
    tags=["User Management"], operation_summary="Endpoint that sends a password reset link to a user's email", responses={
        200: openapi.Response(
            description="Successful Response",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING, description='Message')
                }
            ),
            examples={
                "application/json": {
                    "message": "A link to reset your password has been sent to your email address."
                }
            }
        ),
        400: openapi.Response(
            description="Failed Response",
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING, description='Message')
                }
            ),
            examples={
                "application/json": {
                    "message": "No user found with this email address."
                }
            }
        )
}
)
@ api_view(['POST'])
def password_reset_request(request):
    if request.method == "POST":
        password_reset_form = PasswordResetForm(request.POST)
        if password_reset_form.is_valid():
            data = password_reset_form.cleaned_data['email']
            associated_users = User.objects.filter(email=data)
            if associated_users.exists():
                for user in associated_users:
                    subject = "TerraTrav Validation Portal - Password Reset Requested"
                    email_template_name = "auth/password_reset_email.html"
                    c = {
                        "email": user.email,
                        "domain": request.get_host(),
                        "site_name": "TerraTrac Validation Portal",
                        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                        "user": user,
                        "token": default_token_generator.make_token(user),
                        "protocol": 'https' if request.is_secure() else 'http',
                    }
                    email = render_to_string(email_template_name, c)
                    send_mail(subject, message=email, html_message=email,
                              from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[user.email])

                messages.success(
                    request, 'A link to reset your password has been sent to your email address.')
                return redirect(reverse('password_reset'))
            else:
                messages.error(
                    request, 'No user found with this email address.')
                return redirect(reverse('password_reset'))

    password_reset_form = PasswordResetForm()
    return render(request, "auth/password_reset.html", {"form": password_reset_form})


@ swagger_auto_schema(method='get', security=[],
                      tags=["User Management"], operation_summary="Endpoint that allows a user to reset their password")
@ api_view(['GET'])
def password_reset_confirm(request, uidb64=None, token=None):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            form = SetPasswordForm(user, request.POST)
            if form.is_valid():
                form.save()
                messages.success(
                    request, 'Your password has been successfully reset. You can now log in with your new password.')
                return redirect('login')
        else:
            form = SetPasswordForm(user)
    else:
        messages.error(
            request, 'The password reset link is invalid or has expired.')
        return redirect('password_reset')

    return render(request, 'auth/password_reset_confirm.html', {'form': form})
